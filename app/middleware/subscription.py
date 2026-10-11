from fastapi import Depends, HTTPException, Request

from app.core.security import require_hr, CurrentUser
from app.services.domain.subscription_service import SubscriptionService, OWNER_COMPANY


async def get_company_plan_features(company_id: str) -> dict:
    return await SubscriptionService.get_features(OWNER_COMPANY, company_id)


def require_tier(feature_key: str):
    async def dependency(current_user: CurrentUser = Depends(require_hr)):
        features = await get_company_plan_features(current_user.company_id)
        if not features.get(feature_key, False):
            raise HTTPException(
                status_code=403,
                detail=f"Gói cước hiện tại không hỗ trợ tính năng này. Vui lòng nâng cấp (Upsell)."
            )
        return current_user
    return dependency


def get_action_cost(action_type: str) -> int:
    from app.services.nlp_engine import GLOBAL_SYSTEM_SETTINGS

    # Bắt buộc đọc từ DB/Memory
    actual_cost = GLOBAL_SYSTEM_SETTINGS.get("action_costs", {}).get(action_type)
    if actual_cost is None:
        raise HTTPException(
            status_code=503,
            detail=f"Hệ thống đang thiếu cấu hình bảng giá cho '{action_type}'. Chưa thể thực hiện lúc này."
        )
    return actual_cost


async def charge_company_credits(current_user: CurrentUser, action_type: str, cost: int):
    parts = await SubscriptionService.consume_credits(OWNER_COMPANY, current_user.company_id, current_user.id, cost, action_type)
    if parts is None:
        raise HTTPException(
            status_code=402,
            detail=f"Tài khoản không đủ Credit AI (cần {cost} credits cho {action_type}). Vui lòng nạp thêm."
        )
    return parts


async def refund_company_credits(current_user: CurrentUser, parts: list, action_type: str, amount: int = None):
    await SubscriptionService.refund_credits(OWNER_COMPANY, current_user.company_id, current_user.id, parts,
                                             reason=f"REFUND_{action_type}", amount=amount)


def require_credits(action_type: str):
    async def dependency(request: Request, current_user: CurrentUser = Depends(require_hr)):
        actual_cost = get_action_cost(action_type)

        # Trạm gác thông minh: Nếu miễn phí (cost = 0), cho qua luôn không cần đụng DB
        if actual_cost == 0:
            return current_user

        parts = await charge_company_credits(current_user, action_type, actual_cost)
        # Lưu lại phần đã trừ để endpoint có thể hoàn credit khi AI xử lý thất bại
        request.state.credit_charge = {"action_type": action_type, "parts": parts}
        return current_user
    return dependency


async def refund_charged_credits(request: Request, current_user: CurrentUser):
    charge = getattr(request.state, "credit_charge", None)
    if charge and charge.get("parts"):
        await refund_company_credits(current_user, charge["parts"], charge["action_type"])
        request.state.credit_charge = None
