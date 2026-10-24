"""
Script sinh Nhật ký Sử dụng Credit AI (quota_transactions collection) chân thực
cho Doanh nghiệp và Ứng viên trên hệ thống Verisem.
Đảm bảo tính toán số dư balance_after chính xác và đồng bộ với credit_grants.
"""
import asyncio
import random
from datetime import datetime, timezone, timedelta
from bson import ObjectId

from app.database.config import db_instance, connect_to_mongo, close_mongo_connection, Collections
from app.services.domain.subscription_service import SubscriptionService, OWNER_COMPANY, OWNER_APPLICANT

async def seed_credit_transactions():
    await connect_to_mongo()
    db = db_instance.db
    now = datetime.now(timezone.utc)

    print("=== BẮT ĐẦU KHỞI TẠO DỮ LIỆU NHẬT KÝ SỬ DỤNG CREDIT AI (QUOTA_TRANSACTIONS) ===")

    # 1. Tải danh mục plans
    plans_by_code = {}
    async for p in db[Collections.SUBSCRIPTION_PLANS].find({}):
        p["id"] = str(p["_id"])
        plans_by_code[p.get("plan_code")] = p

    # 2. Lấy HR users map
    hr_users_map = {}
    async for u in db[Collections.USERS].find({"role": {"$in": ["hr_owner", "hr_member"]}}):
        c_id = u.get("company_id")
        if c_id:
            if c_id not in hr_users_map:
                hr_users_map[c_id] = []
            hr_users_map[c_id].append(str(u["_id"]))

    # 3. Lấy toàn bộ subscriptions active
    subs = await db[Collections.SUBSCRIPTIONS].find({"status": "active"}).to_list(500)
    print(f"Tìm thấy {len(subs)} active subscriptions để tạo lịch sử tiêu hao Credit...")

    # Xóa dữ liệu cũ nếu có
    await db[Collections.QUOTA_TRANSACTIONS].delete_many({})

    tx_to_insert = []
    grant_updates = []

    # Định nghĩa các hoạt động tiêu hao cho Company
    comp_ai_actions = [
        ("AI_CV_SCORING", -1),
        ("AI_CV_SCORING", -1),
        ("AI_CV_SCORING", -1),
        ("AI_INTERVIEW_GEN", -5),
        ("AI_JD_PARSING", -2),
        ("AI_CANDIDATE_MATCH", -1),
    ]

    # Định nghĩa các hoạt động tiêu hao cho Applicant
    app_ai_actions = [
        ("AI_CV_SCORING", -1),
        ("AI_CV_SCORING", -1),
        ("AI_COVER_LETTER", -2),
    ]

    for sub in subs:
        owner_type = sub["owner_type"]
        owner_id = sub["owner_id"]
        plan_code = sub.get("plan_code")
        plan = plans_by_code.get(plan_code)
        if not plan:
            continue

        p_start = sub.get("period_start") or (now - timedelta(days=20))
        if p_start.tzinfo is None:
            p_start = p_start.replace(tzinfo=timezone.utc)

        # Quyết định actor_id
        if owner_type == OWNER_COMPANY:
            actors = hr_users_map.get(owner_id, [owner_id])
        else:
            actors = [owner_id]

        initial_credits = SubscriptionService.get_plan_credits(plan)
        if initial_credits <= 0:
            initial_credits = 50 if owner_type == OWNER_APPLICANT else 500

        running_balance = initial_credits
        curr_time = p_start

        # Giao dịch 1: Cấp credit khi mua/kích hoạt gói
        tx_to_insert.append({
            "_id": ObjectId(),
            "owner_type": owner_type,
            "owner_id": owner_id,
            "actor_id": actors[0],
            "delta": initial_credits,
            "reason": f"PURCHASE_{plan_code}",
            "balance_after": running_balance,
            "grant_id": None,
            "order_id": sub.get("order_id"),
            "company_id": owner_id if owner_type == OWNER_COMPANY else None,
            "user_id": actors[0] if owner_type == OWNER_COMPANY else owner_id,
            "action_type": f"PURCHASE_{plan_code}",
            "credit_cost": -initial_credits,
            "created_at": curr_time,
        })

        # Kiểm tra xem owner này có đơn hàng Topup nào không
        topup_orders = await db[Collections.ORDERS].find({
            "owner_id": owner_id,
            "plan_snapshot.plan_type": "topup",
            "status": "paid"
        }).to_list(10)

        # Tạo chuỗi hoạt động AI
        actions_pool = comp_ai_actions if owner_type == OWNER_COMPANY else app_ai_actions
        num_actions = random.randint(4, 9) if owner_type == OWNER_COMPANY else random.randint(2, 5)

        time_step = max(timedelta(hours=4), (now - curr_time) / (num_actions + len(topup_orders) + 1))

        # Nếu có đơn topup, chèn vào giữa dòng thời gian
        topup_inserted = False

        for a_idx in range(num_actions):
            curr_time += time_step + timedelta(minutes=random.randint(10, 50))
            if curr_time > now:
                curr_time = now - timedelta(minutes=random.randint(5, 60))

            # Giữa chu kỳ nếu có topup thì cộng credit
            if not topup_inserted and topup_orders and a_idx >= num_actions // 2:
                for t_order in topup_orders:
                    t_credits = t_order.get("plan_snapshot", {}).get("credits_granted", 100)
                    t_code = t_order.get("plan_snapshot", {}).get("plan_code", "topup")
                    running_balance += t_credits
                    tx_to_insert.append({
                        "_id": ObjectId(),
                        "owner_type": owner_type,
                        "owner_id": owner_id,
                        "actor_id": random.choice(actors),
                        "delta": t_credits,
                        "reason": f"PURCHASE_{t_code}",
                        "balance_after": running_balance,
                        "grant_id": None,
                        "order_id": str(t_order["_id"]),
                        "company_id": owner_id if owner_type == OWNER_COMPANY else None,
                        "user_id": random.choice(actors) if owner_type == OWNER_COMPANY else owner_id,
                        "action_type": f"PURCHASE_{t_code}",
                        "credit_cost": -t_credits,
                        "created_at": curr_time,
                    })
                topup_inserted = True

            action_type, delta = random.choice(actions_pool)
            cost = abs(delta)

            if running_balance - cost < 0:
                break

            running_balance -= cost
            actor = random.choice(actors)

            tx_to_insert.append({
                "_id": ObjectId(),
                "owner_type": owner_type,
                "owner_id": owner_id,
                "actor_id": actor,
                "delta": delta,
                "reason": action_type,
                "balance_after": running_balance,
                "grant_id": None,
                "order_id": None,
                "company_id": owner_id if owner_type == OWNER_COMPANY else None,
                "user_id": actor if owner_type == OWNER_COMPANY else owner_id,
                "action_type": action_type,
                "credit_cost": cost,
                "created_at": curr_time,
            })

        # Cập nhật số dư cuối cùng vào credit_grants và companies / applicant_profiles
        grant_updates.append((owner_type, owner_id, running_balance))

    # 4. Ghi transactions vào MongoDB
    if tx_to_insert:
        await db[Collections.QUOTA_TRANSACTIONS].insert_many(tx_to_insert)
        print(f"✅ Đã nạp thành công {len(tx_to_insert)} bản ghi Nhật ký Sử dụng Credit AI (quota_transactions)!")

    # 5. Đồng bộ số dư chuẩn xác với credit_grants
    for o_type, o_id, final_bal in grant_updates:
        await db[Collections.CREDIT_GRANTS].update_one(
            {"owner_type": o_type, "owner_id": o_id},
            {"$set": {"amount_remaining": final_bal}}
        )
        if o_type == OWNER_COMPANY:
            await db[Collections.COMPANIES].update_one(
                {"_id": ObjectId(o_id)},
                {"$set": {"credits_remaining": final_bal}}
            )
        else:
            await db[Collections.APPLICANT_PROFILES].update_one(
                {"user_id": o_id},
                {"$set": {"credits_remaining": final_bal}}
            )
    print(f"✅ Đã đồng bộ số dư khả dụng (amount_remaining) cho {len(grant_updates)} tài khoản!")

    # 6. Kiểm tra mẫu
    total_tx = await db[Collections.QUOTA_TRANSACTIONS].count_documents({})
    print(f"\nTổng số transactions trong DB: {total_tx}")

    sample_txs = await db[Collections.QUOTA_TRANSACTIONS].find({"owner_id": subs[0]["owner_id"]}).sort("created_at", -1).to_list(10)
    print(f"\nDemo Nhật ký Credit của Company {subs[0]['owner_id']} (gồm {len(sample_txs)} lượt):")
    for stx in sample_txs:
        c_cost = stx.get('delta')
        c_str = f"+{c_cost}" if c_cost > 0 else f"{c_cost}"
        print(f" - [{stx['created_at'].strftime('%Y-%m-%d %H:%M')}] {stx['action_type']} | {c_str} Credit | Số dư: {stx['balance_after']}")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_credit_transactions())
