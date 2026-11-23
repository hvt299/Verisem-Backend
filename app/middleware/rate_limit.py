import os
import math
import time
import logging

import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from limits import parse as parse_limit
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.security import JWT_SECRET, ALGORITHM

load_dotenv()

logger = logging.getLogger("verisem_rate_limit")

redis_url = os.getenv("REDIS_URL", "")
rate_limit_url = redis_url if redis_url.startswith(("redis://", "rediss://", "unix://")) else "memory://"

if rate_limit_url == "memory://" and os.getenv("ENVIRONMENT", "development").lower() == "production":
    logger.warning(
        "Rate limiter đang dùng memory:// trên production: bộ đếm không chia sẻ giữa các worker/instance "
        "và bị reset khi restart. Hãy cấu hình REDIS_URL."
    )

# =====================================================================
# KEY FUNCTIONS
# - ip_key:      IP thật của client (uvicorn --proxy-headers + FORWARDED_ALLOW_IPS)
# - user_key:    user id từ JWT đã verify chữ ký (không truy vấn DB), fallback IP
# - company_key: company_id từ JWT, fallback user_key
# =====================================================================

def ip_key(request: Request) -> str:
    return f"ip:{get_remote_address(request)}"


def _token_payload(request: Request) -> dict:
    token = request.cookies.get("token")
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    if not token:
        return {}
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return {}


def user_key(request: Request) -> str:
    sub = _token_payload(request).get("sub")
    return f"user:{sub}" if sub else ip_key(request)


def company_key(request: Request) -> str:
    company_id = _token_payload(request).get("company_id")
    return f"company:{company_id}" if company_id else user_key(request)


limiter = Limiter(
    key_func=ip_key,
    storage_uri=rate_limit_url,
    default_limits=["300/minute"],
    headers_enabled=True,
    in_memory_fallback_enabled=rate_limit_url != "memory://",
    storage_options={"ssl_cert_reqs": None} if rate_limit_url.startswith("rediss://") else {},
)

# =====================================================================
# 429 HANDLER (tiếng Việt + Retry-After)
# =====================================================================

def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    retry_after = 60
    view_limit = getattr(request.state, "view_rate_limit", None)
    if view_limit:
        try:
            reset_at, _ = limiter.limiter.get_window_stats(view_limit[0], *view_limit[1])
            retry_after = max(1, math.ceil(reset_at - time.time()))
        except Exception:
            pass

    response = JSONResponse(
        status_code=429,
        content={
            "detail": f"Bạn thao tác quá nhanh. Vui lòng thử lại sau {_humanize(retry_after)}.",
            "retry_after": retry_after,
        },
    )
    response.headers["Retry-After"] = str(retry_after)
    if view_limit:
        response = request.app.state.limiter._inject_headers(response, view_limit)
    return response


def _humanize(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} giây"
    if seconds < 3600:
        return f"{math.ceil(seconds / 60)} phút"
    return f"{math.ceil(seconds / 3600)} giờ"

# =====================================================================
# BỘ ĐẾM THEO ĐỊNH DANH (email...) — dùng trong service khi khóa nằm trong body
# =====================================================================

class IdentifierThrottle:
    """Bộ đếm dùng chung storage với limiter (Redis hoặc memory)."""

    def __init__(self, namespace: str, limit: str, message: str):
        self.namespace = namespace
        self.item = parse_limit(limit)
        self.message = message

    def _id(self, identifier: str) -> str:
        return (identifier or "").strip().lower()

    def _retry_after(self, identifier: str) -> int:
        reset_at, _ = limiter.limiter.get_window_stats(self.item, self.namespace, self._id(identifier))
        return max(1, math.ceil(reset_at - time.time()))

    def _raise(self, identifier: str):
        retry_after = self._retry_after(identifier)
        raise HTTPException(
            status_code=429,
            detail=self.message.format(wait=_humanize(retry_after)),
            headers={"Retry-After": str(retry_after)},
        )

    def ensure_allowed(self, identifier: str):
        """Chặn nếu đã hết lượt, không tiêu lượt."""
        if not limiter.limiter.test(self.item, self.namespace, self._id(identifier)):
            self._raise(identifier)

    def hit(self, identifier: str):
        """Tiêu 1 lượt; chặn nếu đã hết lượt."""
        if not limiter.limiter.hit(self.item, self.namespace, self._id(identifier)):
            self._raise(identifier)

    def reset(self, identifier: str):
        try:
            limiter.limiter.clear(self.item, self.namespace, self._id(identifier))
        except Exception:
            pass


login_failure_throttle = IdentifierThrottle(
    "login_fail", "5/15minute",
    "Tài khoản tạm khóa đăng nhập do nhập sai nhiều lần. Vui lòng thử lại sau {wait}.",
)
forgot_password_throttle = IdentifierThrottle(
    "forgot_pw", "3/hour",
    "Bạn đã yêu cầu khôi phục mật khẩu quá nhiều lần. Vui lòng thử lại sau {wait}.",
)
