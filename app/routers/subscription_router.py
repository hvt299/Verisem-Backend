from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.middleware.rate_limit import limiter
import os
import urllib.parse
from app.services.nlp_engine import GLOBAL_SYSTEM_SETTINGS

from app.core.security import get_current_user, CurrentUser
from app.schemas.common_schema import UserRole
from app.schemas.subscription_plan_schema import TargetAudience
from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
from app.repositories.quota_transaction_repository import QuotaTransactionRepository
from app.services.domain.subscription_service import SubscriptionService, OWNER_COMPANY, as_aware

router = APIRouter(prefix="/api/v1/subscriptions", tags=["Billing & Subscriptions"])

@router.get("/plans")
async def get_active_plans(target: TargetAudience):
    plans = await SubscriptionPlanRepository.find_many({
        "target_audience": target.value,
        "is_active": True
    }, sort=[("current_price", 1)])
    for plan in plans:
        plan["plan_type"] = SubscriptionService.get_plan_type(plan)
        plan["credits_granted"] = SubscriptionService.get_plan_credits(plan)
    return {"status": "success", "data": plans}

@router.get("/my-plan")
async def get_my_plan(current_user: CurrentUser = Depends(get_current_user)):
    if current_user.role == UserRole.ADMIN.value:
        return {"status": "success", "data": {
            "entity_type": "admin",
            "entity_id": current_user.id,
            "current_plan": "Quản trị viên (Unlimited)",
            "current_plan_code": "admin_vip",
            "credits_remaining": 9999999,
            "period_start": None,
            "period_end": None
        }}

    owner_type, owner_id = SubscriptionService.resolve_owner(current_user)
    return {"status": "success", "data": await SubscriptionService.get_plan_summary(owner_type, owner_id)}

@router.get("/transactions")
async def get_transactions(current_user: CurrentUser = Depends(get_current_user)):
    owner_type, owner_id = SubscriptionService.resolve_owner(current_user)
    # Dữ liệu cũ chưa có owner_type/owner_id → đọc thêm theo company_id / user_id
    legacy_query = {"company_id": owner_id} if owner_type == OWNER_COMPANY else {"user_id": owner_id, "company_id": None}
    query = {"$or": [{"owner_type": owner_type, "owner_id": owner_id}, legacy_query]}

    transactions = await QuotaTransactionRepository.find_many(query, sort=[("created_at", -1)], limit=100)
    for tx in transactions:
        tx["id"] = tx.get("id") or str(tx.pop("_id", ""))
        tx["created_at"] = as_aware(tx.get("created_at"))

    return {"status": "success", "data": transactions}

@router.post("/checkout/{plan_code}")
@limiter.limit("20/day")
async def create_checkout_session(request: Request, response: Response, plan_code: str, current_user: CurrentUser = Depends(get_current_user)):
    plan = await SubscriptionPlanRepository.find_one({"plan_code": plan_code, "is_active": True})
    if not plan:
        raise HTTPException(status_code=404, detail="Gói cước không tồn tại hoặc đã ngừng bán")
    if plan.get("current_price", 0) <= 0:
        raise HTTPException(status_code=400, detail="Gói miễn phí đã được kích hoạt mặc định")

    owner_type, owner_id = SubscriptionService.resolve_owner(current_user)
    if SubscriptionService.owner_type_for_audience(plan.get("target_audience")) != owner_type:
        detail = "Gói cước này chỉ dành cho Doanh nghiệp" if plan.get("target_audience") == "hr" else "Gói cước này chỉ dành cho Ứng viên"
        raise HTTPException(status_code=403, detail=detail)

    await SubscriptionService.assert_can_purchase(plan, owner_type, owner_id)
    order = await SubscriptionService.create_order(plan, owner_type, owner_id, created_by=current_user.id)

    payment_config = GLOBAL_SYSTEM_SETTINGS.get("payment_config", {})
    bank_id = payment_config.get("bank_id", "MB")
    account_no = payment_config.get("account_no", "0123456789")
    account_name = payment_config.get("account_name", "CONG TY ATS")
    template = payment_config.get("template", "compact2")

    # Nội dung CK = mã đơn hàng (chỉ gồm A-Z0-9 nên không bị ngân hàng cắt ký tự)
    transfer_content = order["order_code"]
    amount = order["amount"]

    encoded_content = urllib.parse.quote(transfer_content)
    encoded_name = urllib.parse.quote(account_name)
    qr_url = f"https://img.vietqr.io/image/{bank_id}-{account_no}-{template}.png?amount={amount}&addInfo={encoded_content}&accountName={encoded_name}"

    return {
        "status": "success",
        "data": {
            "order_code": order["order_code"],
            "plan_code": plan_code,
            "amount": amount,
            "transfer_content": transfer_content,
            "bank_account": account_no,
            "bank_name": bank_id,
            "account_name": account_name,
            "qr_url": qr_url,
            "expires_at": order["expires_at"]
        }
    }

@router.get("/orders")
async def list_my_orders(current_user: CurrentUser = Depends(get_current_user)):
    owner_type, owner_id = SubscriptionService.resolve_owner(current_user)
    orders = await SubscriptionService.list_owner_orders(owner_type, owner_id)
    return {"status": "success", "data": [SubscriptionService.present_order(o) for o in orders]}

@router.get("/orders/{order_code}")
async def get_my_order(order_code: str, current_user: CurrentUser = Depends(get_current_user)):
    owner_type, owner_id = SubscriptionService.resolve_owner(current_user)
    order = await SubscriptionService.get_owner_order(order_code, owner_type, owner_id)
    return {"status": "success", "data": SubscriptionService.present_order(order)}

@router.post("/webhook/sepay")
async def sepay_webhook(request: Request):
    # Fail closed: chưa cấu hình token thì từ chối toàn bộ
    sepay_token = os.getenv("SEPAY_WEBHOOK_TOKEN", "")
    auth_header = request.headers.get("Authorization", "")
    if not sepay_token or auth_header not in (f"Bearer {sepay_token}", f"Apikey {sepay_token}"):
        raise HTTPException(status_code=401, detail="Xác thực Webhook thất bại. Request không hợp lệ.")

    payload = await request.json()
    return await SubscriptionService.handle_sepay_webhook(payload)

@router.post("/dev/simulate-payment/{order_code}")
async def simulate_payment(order_code: str, current_user: CurrentUser = Depends(get_current_user)):
    # Chỉ bật ở môi trường Dev/Test để kích hoạt đơn hàng mà không cần chuyển khoản thật
    if os.getenv("ENABLE_PAYMENT_SIMULATION", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="Not Found")

    owner_type, owner_id = SubscriptionService.resolve_owner(current_user)
    order = await SubscriptionService.get_owner_order(order_code, owner_type, owner_id)
    success, message = await SubscriptionService.mark_order_paid(order, actor_id=current_user.id, sepay_tx_id=f"SIMULATED_{order['order_code']}")
    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"status": "success", "message": f"[Giả lập] {message}"}
