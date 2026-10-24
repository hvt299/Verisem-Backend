import logging
import re
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List, Dict, Any

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.core.security import CurrentUser
from app.database.config import Collections, db_instance, get_db
from app.schemas.common_schema import UserRole
from app.repositories.subscription_plan_repository import SubscriptionPlanRepository

logger = logging.getLogger(__name__)

OWNER_COMPANY = "company"
OWNER_APPLICANT = "applicant"

PLAN_TYPE_SUBSCRIPTION = "subscription"
PLAN_TYPE_TOPUP = "topup"

ORDER_PENDING = "pending"
ORDER_PAID = "paid"
ORDER_CANCELLED = "cancelled"
ORDER_EXPIRED = "expired"

SUB_ACTIVE = "active"
SUB_EXPIRED = "expired"
SUB_REPLACED = "replaced"

ORDER_CODE_PREFIX = "CVR"
ORDER_CODE_ALPHABET = string.ascii_uppercase + string.digits
ORDER_CODE_PATTERN = re.compile(r"CVR[A-Z0-9]{8}")
ORDER_TTL_MINUTES = 15

FREE_PLAN_CODES = {OWNER_COMPANY: "hr_free", OWNER_APPLICANT: "app_free"}

# Fallback cuối cùng phòng hờ DB bị xóa nhầm gói Free
FALLBACK_FREE_FEATURES = {
    OWNER_COMPANY: {
        "max_active_jobs": 1,
        "max_job_edits": 5,
        "max_rescores_per_job": 2,
        "monthly_ai_credits": 0,
        "max_cv_parses_per_month": 20,
        "can_use_reverse_matching": False,
        "can_set_hot_job": False,
        "can_export_analytics": False,
        "can_customize_ai_weights": False,
    },
    OWNER_APPLICANT: {
        "max_cv_uploads": 2,
        "max_cover_letters_uploads": 2,
        "max_job_applies_per_day": 5,
        "max_self_scores_per_day": 3,
        "ai_credits": 0,
        "has_pro_badge": False,
        "can_use_ai_cv_review": False,
    },
}


class InsufficientCreditsError(Exception):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _owner_query(owner_type: str, owner_id: str) -> dict:
    return {"owner_type": owner_type, "owner_id": owner_id}


def _active_grant_query(owner_type: str, owner_id: str, now: datetime) -> dict:
    return {
        **_owner_query(owner_type, owner_id),
        "amount_remaining": {"$gt": 0},
        "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}],
    }


def _format(doc: Optional[dict]) -> Optional[dict]:
    if doc and "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


class SubscriptionService:
    # ==========================================
    # PLAN HELPERS
    # ==========================================
    @staticmethod
    def get_plan_type(plan: dict) -> str:
        if plan.get("plan_type"):
            return plan["plan_type"]
        # Gói cũ chưa migrate: suy ra từ chu kỳ & giá
        if plan.get("billing_cycle_days", 30) == 0 and plan.get("current_price", 0) > 0:
            return PLAN_TYPE_TOPUP
        return PLAN_TYPE_SUBSCRIPTION

    @staticmethod
    def get_plan_credits(plan: dict) -> int:
        if plan.get("credits_granted") is not None:
            return int(plan["credits_granted"])
        features = plan.get("features", {}) or {}
        return int(features.get("monthly_ai_credits", features.get("ai_credits", 0)) or 0)

    @staticmethod
    def owner_type_for_audience(target_audience: str) -> str:
        return OWNER_COMPANY if target_audience == "hr" else OWNER_APPLICANT

    @staticmethod
    def resolve_owner(current_user: CurrentUser) -> Tuple[str, str]:
        if current_user.role in [UserRole.HR_OWNER.value, UserRole.HR_MEMBER.value]:
            if not current_user.company_id:
                raise HTTPException(status_code=400, detail="Tài khoản HR chưa thuộc công ty nào")
            return OWNER_COMPANY, current_user.company_id
        if current_user.role == UserRole.APPLICANT.value:
            return OWNER_APPLICANT, current_user.id
        raise HTTPException(status_code=403, detail="Tài khoản này không sử dụng gói cước")

    @classmethod
    def build_plan_snapshot(cls, plan: dict) -> dict:
        return {
            "plan_id": str(plan.get("id")),
            "plan_code": plan.get("plan_code"),
            "name": plan.get("name"),
            "plan_type": cls.get_plan_type(plan),
            "target_audience": plan.get("target_audience"),
            "tier_level": plan.get("tier_level", 0),
            "price": plan.get("current_price", 0),
            "billing_cycle_days": plan.get("billing_cycle_days", 30),
            "credits_granted": cls.get_plan_credits(plan),
            "credit_validity_days": plan.get("credit_validity_days"),
        }

    @staticmethod
    async def get_free_plan(owner_type: str) -> Optional[dict]:
        return await SubscriptionPlanRepository.find_one({"plan_code": FREE_PLAN_CODES[owner_type], "is_active": True})

    # ==========================================
    # SUBSCRIPTIONS
    # ==========================================
    @staticmethod
    async def get_active_subscription(owner_type: str, owner_id: str, session=None) -> Optional[dict]:
        db = get_db()
        sub = await db[Collections.SUBSCRIPTIONS].find_one(
            {**_owner_query(owner_type, owner_id), "status": SUB_ACTIVE}, session=session
        )
        if not sub:
            return None

        period_end = as_aware(sub.get("period_end"))
        if period_end and period_end <= utc_now():
            await db[Collections.SUBSCRIPTIONS].update_one(
                {"_id": sub["_id"], "status": SUB_ACTIVE},
                {"$set": {"status": SUB_EXPIRED, "updated_at": utc_now()}},
                session=session,
            )
            return None
        return _format(sub)

    @classmethod
    async def get_current_plan(cls, owner_type: str, owner_id: str) -> Tuple[Optional[dict], Optional[dict]]:
        """Trả về (plan, subscription). Không có subscription active → gói Free."""
        sub = await cls.get_active_subscription(owner_type, owner_id)
        if sub:
            plan = await SubscriptionPlanRepository.get_by_id(sub["plan_id"])
            if plan:
                return plan, sub
        return await cls.get_free_plan(owner_type), None

    @classmethod
    async def get_features(cls, owner_type: str, owner_id: str) -> dict:
        plan, _ = await cls.get_current_plan(owner_type, owner_id)
        if plan:
            return plan.get("features", {}) or {}
        return dict(FALLBACK_FREE_FEATURES[owner_type])

    @classmethod
    async def assert_can_purchase(cls, plan: dict, owner_type: str, owner_id: str):
        """Chặn hạ cấp khi gói hiện tại còn hạn. Gói lẻ (topup) luôn được mua."""
        if cls.get_plan_type(plan) == PLAN_TYPE_TOPUP:
            return
        current_plan, sub = await cls.get_current_plan(owner_type, owner_id)
        if not sub or not current_plan:
            return
        if plan.get("tier_level", 0) < current_plan.get("tier_level", 0):
            period_end = as_aware(sub.get("period_end"))
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "PLAN_DOWNGRADE_BLOCKED",
                    "message": "Không thể hạ cấp (Downgrade) do gói hiện tại vẫn còn hạn sử dụng. Vui lòng chờ gói cũ hết hạn để mua gói này.",
                    "current_plan": current_plan.get("name"),
                    "current_period_end": period_end.isoformat() if period_end else None,
                    "target_plan": plan.get("name"),
                }
            )

    # ==========================================
    # CREDITS
    # ==========================================
    @staticmethod
    def _sort_grants_for_consume(grants: List[dict]) -> List[dict]:
        # Hết hạn sớm nhất dùng trước, grant không hết hạn (None) dùng sau cùng
        far_future = datetime.max.replace(tzinfo=timezone.utc)
        return sorted(grants, key=lambda g: (as_aware(g.get("expires_at")) or far_future, as_aware(g.get("created_at")) or far_future))

    @staticmethod
    async def get_balance(owner_type: str, owner_id: str, session=None) -> int:
        db = get_db()
        result = await db[Collections.CREDIT_GRANTS].aggregate(
            [
                {"$match": _active_grant_query(owner_type, owner_id, utc_now())},
                {"$group": {"_id": None, "total": {"$sum": "$amount_remaining"}}},
            ],
            session=session,
        ).to_list(length=1)
        return int(result[0]["total"]) if result else 0

    @classmethod
    async def get_credit_breakdown(cls, owner_type: str, owner_id: str) -> List[dict]:
        db = get_db()
        grants = await db[Collections.CREDIT_GRANTS].find(_active_grant_query(owner_type, owner_id, utc_now())).to_list(length=200)
        return [
            {
                "grant_id": str(g["_id"]),
                "source": g.get("source"),
                "remaining": g.get("amount_remaining", 0),
                "expires_at": as_aware(g.get("expires_at")),
            }
            for g in cls._sort_grants_for_consume(grants)
        ]

    @staticmethod
    async def _record_ledger(
        owner_type: str, owner_id: str, actor_id: str, delta: int, reason: str, balance_after: int,
        grant_id: Optional[str] = None, order_id: Optional[str] = None, session=None,
    ):
        db = get_db()
        await db[Collections.QUOTA_TRANSACTIONS].insert_one(
            {
                "owner_type": owner_type,
                "owner_id": owner_id,
                "actor_id": actor_id,
                "delta": delta,
                "reason": reason,
                "grant_id": grant_id,
                "order_id": order_id,
                "balance_after": balance_after,
                # Các field cũ giữ lại để FE (BillingLedger) và dữ liệu cũ vẫn đọc được
                "company_id": owner_id if owner_type == OWNER_COMPANY else None,
                "user_id": actor_id if owner_type == OWNER_COMPANY else owner_id,
                "action_type": reason,
                "credit_cost": -delta,
                "created_at": utc_now(),
            },
            session=session,
        )

    @classmethod
    async def grant_credits(
        cls, owner_type: str, owner_id: str, amount: int, source: str, actor_id: str, reason: str,
        source_ref: Optional[str] = None, expires_at: Optional[datetime] = None,
        order_id: Optional[str] = None, session=None,
    ) -> Optional[str]:
        if amount <= 0:
            return None
        db = get_db()
        result = await db[Collections.CREDIT_GRANTS].insert_one(
            {
                **_owner_query(owner_type, owner_id),
                "source": source,
                "source_ref": source_ref,
                "amount_granted": amount,
                "amount_remaining": amount,
                "expires_at": expires_at,
                "created_at": utc_now(),
            },
            session=session,
        )
        grant_id = str(result.inserted_id)
        balance_after = await cls.get_balance(owner_type, owner_id, session=session)
        await cls._record_ledger(owner_type, owner_id, actor_id, amount, reason, balance_after,
                                 grant_id=grant_id, order_id=order_id, session=session)
        return grant_id

    @classmethod
    async def grant_free_credits(cls, owner_type: str, owner_id: str):
        """Tặng credit của gói Free khi tạo tài khoản / công ty mới."""
        free_plan = await cls.get_free_plan(owner_type)
        if not free_plan:
            return
        await cls.grant_credits(owner_type, owner_id, cls.get_plan_credits(free_plan), source="free",
                                actor_id="system", reason="FREE_PLAN_CREDITS")

    @classmethod
    async def consume_credits(cls, owner_type: str, owner_id: str, actor_id: str, cost: int, reason: str) -> Optional[List[dict]]:
        """
        Trừ credit (ưu tiên grant sắp hết hạn). Chạy trong Mongo transaction.
        Trả về danh sách phần đã trừ [{grant_id, amount}] để có thể refund, hoặc None nếu không đủ credit.
        """
        if cost <= 0:
            return []

        async def _txn(session):
            db = get_db()
            grants = await db[Collections.CREDIT_GRANTS].find(
                _active_grant_query(owner_type, owner_id, utc_now()), session=session
            ).to_list(length=200)

            if sum(g.get("amount_remaining", 0) for g in grants) < cost:
                raise InsufficientCreditsError()

            parts, need = [], cost
            for g in cls._sort_grants_for_consume(grants):
                if need <= 0:
                    break
                take = min(need, g.get("amount_remaining", 0))
                result = await db[Collections.CREDIT_GRANTS].update_one(
                    {"_id": g["_id"], "amount_remaining": {"$gte": take}},
                    {"$inc": {"amount_remaining": -take}},
                    session=session,
                )
                if result.modified_count == 0:
                    raise InsufficientCreditsError()
                parts.append({"grant_id": str(g["_id"]), "amount": take})
                need -= take

            balance_after = await cls.get_balance(owner_type, owner_id, session=session)
            await cls._record_ledger(owner_type, owner_id, actor_id, -cost, reason, balance_after,
                                     grant_id=parts[0]["grant_id"] if len(parts) == 1 else None, session=session)
            return parts

        try:
            async with await db_instance.client.start_session() as session:
                return await session.with_transaction(_txn)
        except InsufficientCreditsError:
            return None

    @classmethod
    async def refund_credits(cls, owner_type: str, owner_id: str, actor_id: str, parts: List[dict],
                             reason: str = "REFUND", amount: Optional[int] = None):
        """
        Hoàn lại credit vào đúng các grant đã trừ (VD: gọi AI thất bại).
        `amount` để hoàn một phần (hoàn ngược từ grant trừ sau cùng), bỏ trống = hoàn toàn bộ.
        """
        if amount is not None:
            remaining, partial = amount, []
            for p in reversed(parts or []):
                if remaining <= 0:
                    break
                take = min(remaining, p["amount"])
                partial.append({"grant_id": p["grant_id"], "amount": take})
                remaining -= take
            parts = partial

        total = sum(p["amount"] for p in parts or [])
        if total <= 0:
            return

        async def _txn(session):
            db = get_db()
            for p in parts:
                await db[Collections.CREDIT_GRANTS].update_one(
                    {"_id": ObjectId(p["grant_id"])}, {"$inc": {"amount_remaining": p["amount"]}}, session=session
                )
            balance_after = await cls.get_balance(owner_type, owner_id, session=session)
            await cls._record_ledger(owner_type, owner_id, actor_id, total, reason, balance_after, session=session)

        async with await db_instance.client.start_session() as session:
            await session.with_transaction(_txn)

    # ==========================================
    # ÁP DỤNG GÓI (dùng chung cho Webhook / Giả lập / Admin)
    # ==========================================
    @classmethod
    async def _apply_plan(
        cls, snapshot: dict, owner_type: str, owner_id: str, actor_id: str, reason: str,
        order_id: Optional[str] = None, cycle_days_override: Optional[int] = None,
        topup_source: str = "topup", session=None,
    ) -> str:
        db = get_db()
        now = utc_now()
        credits = int(snapshot.get("credits_granted") or 0)

        # Gói lẻ: chỉ cộng credit, KHÔNG đụng tới gói thuê bao đang dùng
        if snapshot["plan_type"] == PLAN_TYPE_TOPUP:
            validity = snapshot.get("credit_validity_days")
            expires_at = now + timedelta(days=validity) if validity else None
            await cls.grant_credits(owner_type, owner_id, credits, source=topup_source, actor_id=actor_id,
                                    reason=reason, source_ref=order_id, expires_at=expires_at,
                                    order_id=order_id, session=session)
            return f"Đã cộng {credits} credit từ gói {snapshot['plan_code']}"

        cycle_days = cycle_days_override if cycle_days_override is not None else snapshot.get("billing_cycle_days", 30)
        active = await cls.get_active_subscription(owner_type, owner_id, session=session)

        if active and active.get("plan_id") == snapshot["plan_id"]:
            # Gia hạn: cộng dồn từ period_end cũ
            old_end = as_aware(active.get("period_end"))
            new_end = None if (cycle_days == 0 or old_end is None) else old_end + timedelta(days=cycle_days)
            await db[Collections.SUBSCRIPTIONS].update_one(
                {"_id": ObjectId(active["id"])},
                {"$set": {"period_end": new_end, "order_id": order_id, "updated_at": now}},
                session=session,
            )
            sub_id, period_end, message = active["id"], new_end, f"Gia hạn thành công gói {snapshot['plan_code']}"
        else:
            if active:
                await db[Collections.SUBSCRIPTIONS].update_one(
                    {"_id": ObjectId(active["id"])},
                    {"$set": {"status": SUB_REPLACED, "updated_at": now}},
                    session=session,
                )
            period_end = None if cycle_days == 0 else now + timedelta(days=cycle_days)
            result = await db[Collections.SUBSCRIPTIONS].insert_one(
                {
                    **_owner_query(owner_type, owner_id),
                    "plan_id": snapshot["plan_id"],
                    "plan_code": snapshot["plan_code"],
                    "order_id": order_id,
                    "status": SUB_ACTIVE,
                    "period_start": now,
                    "period_end": period_end,
                    "created_at": now,
                },
                session=session,
            )
            sub_id, message = str(result.inserted_id), f"Kích hoạt thành công gói {snapshot['plan_code']}"

        await cls.grant_credits(owner_type, owner_id, credits, source="subscription", actor_id=actor_id,
                                reason=reason, source_ref=sub_id, expires_at=period_end,
                                order_id=order_id, session=session)
        return message

    @classmethod
    async def admin_grant_plan(cls, plan: dict, owner_type: str, owner_id: str, actor_id: str,
                               cycle_days_override: Optional[int] = None) -> str:
        snapshot = cls.build_plan_snapshot(plan)

        async def _txn(session):
            return await cls._apply_plan(snapshot, owner_type, owner_id, actor_id,
                                         reason=f"ADMIN_GRANT_{snapshot['plan_code'].upper()}",
                                         cycle_days_override=cycle_days_override,
                                         topup_source="admin", session=session)

        async with await db_instance.client.start_session() as session:
            return await session.with_transaction(_txn)

    # ==========================================
    # ORDERS
    # ==========================================
    @staticmethod
    def _generate_order_code() -> str:
        return ORDER_CODE_PREFIX + "".join(secrets.choice(ORDER_CODE_ALPHABET) for _ in range(8))

    @classmethod
    async def create_order(cls, plan: dict, owner_type: str, owner_id: str, created_by: str) -> dict:
        db = get_db()
        now = utc_now()
        snapshot = cls.build_plan_snapshot(plan)
        for _ in range(5):
            order = {
                "order_code": cls._generate_order_code(),
                **_owner_query(owner_type, owner_id),
                "created_by": created_by,
                "plan_id": snapshot["plan_id"],
                "plan_snapshot": snapshot,
                "amount": snapshot["price"],
                "status": ORDER_PENDING,
                "sepay_tx_id": None,
                "paid_amount": None,
                "paid_at": None,
                "created_at": now,
                "expires_at": now + timedelta(minutes=ORDER_TTL_MINUTES),
            }
            try:
                result = await db[Collections.ORDERS].insert_one(order)
                order["id"] = str(result.inserted_id)
                order.pop("_id", None)
                return order
            except DuplicateKeyError:
                continue
        raise HTTPException(status_code=500, detail="Không thể tạo mã đơn hàng, vui lòng thử lại")

    @staticmethod
    def present_order(order: dict) -> dict:
        status = order.get("status")
        expires_at = as_aware(order.get("expires_at"))
        # Chỉ để UI ẩn QR. Tiền về muộn vẫn được Webhook xử lý.
        if status == ORDER_PENDING and expires_at and expires_at <= utc_now():
            status = ORDER_EXPIRED
        snapshot = order.get("plan_snapshot", {})
        return {
            "order_code": order.get("order_code"),
            "status": status,
            "amount": order.get("amount"),
            "plan_code": snapshot.get("plan_code"),
            "plan_name": snapshot.get("name"),
            "plan_type": snapshot.get("plan_type"),
            "paid_amount": order.get("paid_amount"),
            "paid_at": as_aware(order.get("paid_at")),
            "payment_issue": order.get("payment_issue"),
            "created_at": as_aware(order.get("created_at")),
            "expires_at": expires_at,
        }

    @staticmethod
    async def get_owner_order(order_code: str, owner_type: str, owner_id: str) -> dict:
        db = get_db()
        order = await db[Collections.ORDERS].find_one({"order_code": order_code.upper(), **_owner_query(owner_type, owner_id)})
        if not order:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
        return _format(order)

    @staticmethod
    async def list_owner_orders(owner_type: str, owner_id: str, limit: int = 100) -> List[dict]:
        db = get_db()
        cursor = db[Collections.ORDERS].find(_owner_query(owner_type, owner_id)).sort("created_at", -1).limit(limit)
        return [_format(o) for o in await cursor.to_list(length=limit)]

    @classmethod
    async def mark_order_paid(cls, order: dict, actor_id: str, sepay_tx_id: Optional[str] = None,
                              paid_amount: Optional[int] = None) -> Tuple[bool, str]:
        """Chuyển đơn sang PAID và áp dụng gói trong cùng một transaction (idempotent)."""
        order_id = order["id"]
        snapshot = order["plan_snapshot"]

        async def _txn(session):
            db = get_db()
            now = utc_now()
            result = await db[Collections.ORDERS].update_one(
                {"_id": ObjectId(order_id), "status": {"$ne": ORDER_PAID}},
                {
                    "$set": {
                        "status": ORDER_PAID,
                        "sepay_tx_id": sepay_tx_id,
                        "paid_amount": paid_amount if paid_amount is not None else order.get("amount"),
                        "paid_at": now,
                        "payment_issue": None,
                    }
                },
                session=session,
            )
            if result.modified_count == 0:
                return False, "Đơn hàng đã được xử lý trước đó"
            message = await cls._apply_plan(snapshot, order["owner_type"], order["owner_id"], actor_id,
                                            reason=f"PURCHASE_{snapshot['plan_code'].upper()}",
                                            order_id=order_id, session=session)
            return True, message

        async with await db_instance.client.start_session() as session:
            return await session.with_transaction(_txn)

    # ==========================================
    # WEBHOOK SEPAY
    # ==========================================
    @classmethod
    async def handle_sepay_webhook(cls, payload: dict) -> dict:
        ok = {"success": True}

        if payload.get("transferType") != "in":
            return {**ok, "message": "Chỉ xử lý tiền vào"}

        content = " ".join(str(payload.get(k) or "") for k in ("code", "content", "transactionContent", "description")).upper()
        match = ORDER_CODE_PATTERN.search(content)
        if not match:
            logger.warning("[SePay] Không tìm thấy mã đơn trong giao dịch: %s", payload)
            return {**ok, "message": "Không tìm thấy mã đơn hàng"}

        db = get_db()
        order = _format(await db[Collections.ORDERS].find_one({"order_code": match.group(0)}))
        if not order:
            logger.warning("[SePay] Mã đơn %s không tồn tại: %s", match.group(0), payload)
            return {**ok, "message": "Mã đơn hàng không tồn tại"}

        raw_tx_id = payload.get("id") or payload.get("referenceCode")
        sepay_tx_id = str(raw_tx_id) if raw_tx_id is not None else None
        if sepay_tx_id and await db[Collections.ORDERS].find_one({"sepay_tx_id": sepay_tx_id, "status": ORDER_PAID}):
            return {**ok, "message": "Giao dịch đã được xử lý"}

        if order.get("status") == ORDER_PAID:
            return {**ok, "message": "Đơn hàng đã được thanh toán"}

        paid_amount = int(payload.get("transferAmount") or 0)
        if order.get("status") == ORDER_CANCELLED or paid_amount < order.get("amount", 0):
            issue = "cancelled_order" if order.get("status") == ORDER_CANCELLED else "underpaid"
            await db[Collections.ORDERS].update_one(
                {"_id": ObjectId(order["id"])},
                {"$set": {"payment_issue": issue, "paid_amount": paid_amount, "sepay_tx_id": sepay_tx_id}},
            )
            logger.warning("[SePay] Đơn %s cần xử lý tay (%s): %s", order["order_code"], issue, payload)
            return {**ok, "message": "Đơn hàng cần xử lý thủ công"}

        _, message = await cls.mark_order_paid(order, actor_id="sepay_system",
                                                sepay_tx_id=sepay_tx_id, paid_amount=paid_amount)
        return {**ok, "message": message}

    # ==========================================
    # TỔNG HỢP CHO API /my-plan
    # ==========================================
    @classmethod
    async def get_plan_summary(cls, owner_type: str, owner_id: str) -> dict:
        plan, sub = await cls.get_current_plan(owner_type, owner_id)
        default_name = "HR Cơ bản" if owner_type == OWNER_COMPANY else "Ứng viên Cơ bản"
        balance = await cls.get_balance(owner_type, owner_id)
        return {
            "entity_type": owner_type,
            "entity_id": owner_id,
            "current_plan": plan.get("name") if plan else default_name,
            "current_plan_code": plan.get("plan_code") if plan else FREE_PLAN_CODES[owner_type],
            "tier_level": plan.get("tier_level", 0) if plan else 0,
            "credits_remaining": balance,
            "period_start": as_aware(sub.get("period_start")) if sub else None,
            "period_end": as_aware(sub.get("period_end")) if sub else None,
            "credits": {"total": balance, "breakdown": await cls.get_credit_breakdown(owner_type, owner_id)},
            "features": plan.get("features", {}) if plan else {},
        }
