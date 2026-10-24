"""
Script sinh Lịch sử Đơn hàng / Giao dịch (orders collection) chân thực cho toàn bộ
Doanh nghiệp và Ứng viên có gói cước trên hệ thống Verisem.
Đồng bộ trường order_id trên collection subscriptions.
"""
import asyncio
import random
from datetime import datetime, timezone, timedelta
from bson import ObjectId

from app.database.config import db_instance, connect_to_mongo, close_mongo_connection, Collections
from app.services.domain.subscription_service import SubscriptionService, OWNER_COMPANY, OWNER_APPLICANT

async def seed_orders():
    await connect_to_mongo()
    db = db_instance.db
    now = datetime.now(timezone.utc)
    
    print("=== BẮT ĐẦU KHỞI TẠO DỮ LIỆU LỊCH SỬ GIAO DỊCH / ĐƠN HÀNG (ORDERS) ===")
    
    # 1. Tải danh mục plans
    plans_by_code = {}
    plans_by_id = {}
    async for p in db[Collections.SUBSCRIPTION_PLANS].find({}):
        p["id"] = str(p["_id"])
        plans_by_code[p.get("plan_code")] = p
        plans_by_id[str(p["_id"])] = p

    # 2. Lấy toàn bộ HR Users để map created_by cho Company
    hr_users_map = {}
    async for u in db[Collections.USERS].find({"role": {"$in": ["hr_owner", "hr_member"]}}):
        c_id = u.get("company_id")
        if c_id and (c_id not in hr_users_map or u.get("role") == "hr_owner"):
            hr_users_map[c_id] = str(u["_id"])

    # 3. Quét các subscription active
    subs_cursor = db[Collections.SUBSCRIPTIONS].find({"status": "active"})
    active_subs = await subs_cursor.to_list(length=500)
    print(f"Tìm thấy {len(active_subs)} active subscriptions cần sinh đơn hàng...")

    orders_to_insert = []
    sub_updates = []
    
    # Danh sách gói topup mẫu
    hr_topup_codes = ["hr_topup_500", "hr_topup_1500", "hr_topup_5000", "hr_topup_100"]
    app_topup_codes = ["app_topup_50", "app_topup_150", "app_topup_400"]

    for idx, sub in enumerate(active_subs):
        owner_type = sub["owner_type"]
        owner_id = sub["owner_id"]
        plan_code = sub.get("plan_code")
        plan = plans_by_code.get(plan_code) or plans_by_id.get(str(sub.get("plan_id")))
        
        if not plan:
            continue

        created_by = hr_users_map.get(owner_id) if owner_type == OWNER_COMPANY else owner_id
        if not created_by:
            created_by = owner_id

        period_start = sub.get("period_start") or now - timedelta(days=15)
        if period_start.tzinfo is None:
            period_start = period_start.replace(tzinfo=timezone.utc)

        order_id = ObjectId()
        order_code = SubscriptionService._generate_order_code()
        created_at = period_start - timedelta(minutes=random.randint(2, 6))
        expires_at = created_at + timedelta(minutes=15)
        
        snapshot = SubscriptionService.build_plan_snapshot(plan)
        amount = int(plan.get("current_price", 0))

        main_order = {
            "_id": order_id,
            "order_code": order_code,
            "owner_type": owner_type,
            "owner_id": owner_id,
            "created_by": created_by,
            "plan_id": str(plan["_id"]),
            "plan_snapshot": snapshot,
            "amount": amount,
            "status": "paid",
            "sepay_tx_id": f"SPX{random.randint(100000000, 999999999)}",
            "paid_amount": amount,
            "paid_at": period_start,
            "created_at": created_at,
            "expires_at": expires_at,
        }
        orders_to_insert.append(main_order)
        sub_updates.append((sub["_id"], str(order_id)))

        # Sinh thêm đơn hàng phụ (topup hoặc đơn cũ) để lịch sử giao dịch sống động
        # A. Đơn Top-up nạp thêm credit AI (~30% doanh nghiệp và ~35% ứng viên)
        if (owner_type == OWNER_COMPANY and idx % 3 == 0) or (owner_type == OWNER_APPLICANT and idx % 3 == 1):
            topup_code = random.choice(hr_topup_codes if owner_type == OWNER_COMPANY else app_topup_codes)
            topup_plan = plans_by_code.get(topup_code)
            if topup_plan:
                topup_amount = int(topup_plan.get("current_price", 0))
                topup_paid_at = period_start + timedelta(days=random.randint(2, 8))
                if topup_paid_at > now:
                    topup_paid_at = now - timedelta(hours=random.randint(1, 24))
                topup_created_at = topup_paid_at - timedelta(minutes=random.randint(2, 5))
                topup_order = {
                    "_id": ObjectId(),
                    "order_code": SubscriptionService._generate_order_code(),
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "created_by": created_by,
                    "plan_id": str(topup_plan["_id"]),
                    "plan_snapshot": SubscriptionService.build_plan_snapshot(topup_plan),
                    "amount": topup_amount,
                    "status": "paid",
                    "sepay_tx_id": f"SPX{random.randint(100000000, 999999999)}",
                    "paid_amount": topup_amount,
                    "paid_at": topup_paid_at,
                    "created_at": topup_created_at,
                    "expires_at": topup_created_at + timedelta(minutes=15),
                }
                orders_to_insert.append(topup_order)

        # B. Đơn hết hạn (expired) do người dùng bấm thử nhưng không thanh toán (~15% tài khoản)
        if idx % 7 == 0:
            exp_code = "hr_enterprise_yearly" if owner_type == OWNER_COMPANY else "app_vip_yearly"
            exp_plan = plans_by_code.get(exp_code)
            if exp_plan:
                exp_created_at = period_start - timedelta(days=random.randint(10, 25))
                exp_order = {
                    "_id": ObjectId(),
                    "order_code": SubscriptionService._generate_order_code(),
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "created_by": created_by,
                    "plan_id": str(exp_plan["_id"]),
                    "plan_snapshot": SubscriptionService.build_plan_snapshot(exp_plan),
                    "amount": int(exp_plan.get("current_price", 0)),
                    "status": "expired",
                    "sepay_tx_id": None,
                    "paid_amount": None,
                    "paid_at": None,
                    "created_at": exp_created_at,
                    "expires_at": exp_created_at + timedelta(minutes=15),
                }
                orders_to_insert.append(exp_order)

    # 4. Chèn vào MongoDB
    print(f"Chuẩn bị chèn tổng cộng {len(orders_to_insert)} bản ghi Orders / Giao dịch vào MongoDB...")
    # Xoá các đơn test cũ nếu có
    await db[Collections.ORDERS].delete_many({})
    
    if orders_to_insert:
        await db[Collections.ORDERS].insert_many(orders_to_insert)
        print(f"✅ Đã chèn thành công {len(orders_to_insert)} Orders!")

    # 5. Cập nhật order_id cho subscriptions
    for sub_id, o_id in sub_updates:
        await db[Collections.SUBSCRIPTIONS].update_one(
            {"_id": sub_id},
            {"$set": {"order_id": o_id}}
        )
    print(f"✅ Đã đồng bộ order_id cho {len(sub_updates)} Active Subscriptions!")

    # 6. Kiểm tra lại dữ liệu
    total_orders = await db[Collections.ORDERS].count_documents({})
    paid_orders = await db[Collections.ORDERS].count_documents({"status": "paid"})
    expired_orders = await db[Collections.ORDERS].count_documents({"status": "expired"})
    
    print("\n--- TỔNG KẾT DỮ LIỆU ORDERS ---")
    print(f"Tổng số Orders trong DB: {total_orders}")
    print(f" - Đã thanh toán (paid) : {paid_orders}")
    print(f" - Hết hạn (expired)    : {expired_orders}")
    
    # Thử lấy đơn hàng của 1 công ty mẫu
    sample_sub = active_subs[0]
    sample_orders = await db[Collections.ORDERS].find({"owner_id": sample_sub["owner_id"]}).to_list(10)
    print(f"\nDemo Orders của Owner {sample_sub['owner_type']}:{sample_sub['owner_id']} (có {len(sample_orders)} đơn):")
    for so in sample_orders:
        print(f" - [{so['order_code']}] Gói: {so['plan_snapshot']['name']} | {so['amount']:,}đ | Status: {so['status']} | Date: {so['created_at'].strftime('%Y-%m-%d %H:%M')}")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_orders())
