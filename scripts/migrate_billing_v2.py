"""
Migration dữ liệu Billing cũ sang mô hình mới (orders / subscriptions / credit_grants).
Xem: docs/subscription-redesign.md (mục 7)

Mặc định chỉ chạy thử (dry-run), KHÔNG ghi gì vào DB:
    python -m scripts.migrate_billing_v2
Ghi thật:
    python -m scripts.migrate_billing_v2 --apply

Script idempotent: owner nào đã migrate (có `billing_migrated_at`) sẽ được bỏ qua.
Các field cũ (current_plan_id, credits_remaining, ...) được GIỮ NGUYÊN để rollback.
"""
import argparse
import asyncio
from datetime import datetime, timezone


from app.database.config import db_instance, connect_to_mongo, close_mongo_connection, Collections
from app.services.domain.subscription_service import (
    SubscriptionService, OWNER_COMPANY, OWNER_APPLICANT, FREE_PLAN_CODES, PLAN_TYPE_SUBSCRIPTION, as_aware,
)


async def migrate_plans(db, apply: bool) -> int:
    count = 0
    async for plan in db[Collections.SUBSCRIPTION_PLANS].find({"plan_type": {"$exists": False}}):
        plan["id"] = str(plan["_id"])
        update = {
            "plan_type": SubscriptionService.get_plan_type(plan),
            "credits_granted": SubscriptionService.get_plan_credits(plan),
            "credit_validity_days": None,
        }
        print(f"  [plan] {plan.get('plan_code')}: {update}")
        if apply:
            await db[Collections.SUBSCRIPTION_PLANS].update_one({"_id": plan["_id"]}, {"$set": update})
        count += 1
    return count


async def migrate_owners(db, apply: bool, collection: str, owner_type: str, stats: dict):
    now = datetime.now(timezone.utc)
    plans = {str(p["_id"]): p async for p in db[Collections.SUBSCRIPTION_PLANS].find({})}

    async for entity in db[collection].find({"billing_migrated_at": {"$exists": False}}):
        owner_id = str(entity["_id"]) if owner_type == OWNER_COMPANY else entity.get("user_id")
        if not owner_id:
            continue

        plan = plans.get(str(entity.get("current_plan_id") or ""))
        period_start = as_aware(entity.get("current_period_start")) or now
        period_end = as_aware(entity.get("current_period_end"))
        credits = int(entity.get("credits_remaining") or 0)
        actions = []

        is_paid_subscription = (
            plan is not None
            and plan.get("plan_code") != FREE_PLAN_CODES[owner_type]
            and SubscriptionService.get_plan_type({**plan, "id": str(plan["_id"])}) == PLAN_TYPE_SUBSCRIPTION
            and (period_end is None or period_end > now)
        )
        if plan is not None and not is_paid_subscription and plan.get("plan_code") != FREE_PLAN_CODES[owner_type]:
            # Gói hiện tại là gói lẻ (do lỗi ghi đè cũ) hoặc đã hết hạn → về Free
            stats["skipped_plans"].append(f"{owner_type}:{owner_id} ({plan.get('plan_code')})")

        has_active = await db[Collections.SUBSCRIPTIONS].find_one(
            {"owner_type": owner_type, "owner_id": owner_id, "status": "active"}
        )
        if is_paid_subscription and not has_active:
            actions.append(f"subscription {plan.get('plan_code')} → {period_end or 'vĩnh viễn'}")
            if apply:
                await db[Collections.SUBSCRIPTIONS].insert_one({
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "plan_id": str(plan["_id"]),
                    "plan_code": plan.get("plan_code"),
                    "order_id": None,
                    "status": "active",
                    "period_start": period_start,
                    "period_end": period_end,
                    "created_at": now,
                    "migrated": True,
                })
            stats["subscriptions"] += 1

        if credits > 0:
            # Không phân biệt được credit gói & credit mua lẻ ở dữ liệu cũ → chỉ hết hạn theo kỳ nếu có
            expires_at = period_end if is_paid_subscription else None
            actions.append(f"legacy grant {credits} credit (hết hạn: {expires_at or 'không'})")
            if apply:
                await db[Collections.CREDIT_GRANTS].insert_one({
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "source": "legacy",
                    "source_ref": None,
                    "amount_granted": credits,
                    "amount_remaining": credits,
                    "expires_at": expires_at,
                    "created_at": now,
                })
            stats["grants"] += 1
            stats["credits"] += credits

        if actions:
            print(f"  [{owner_type}] {owner_id}: " + "; ".join(actions))
        if apply:
            await db[collection].update_one({"_id": entity["_id"]}, {"$set": {"billing_migrated_at": now}})
        stats["owners"] += 1


async def main(apply: bool):
    await connect_to_mongo()
    db = db_instance.db
    print(f"=== Migration Billing v2 ({'APPLY' if apply else 'DRY-RUN'}) trên DB: {db.name} ===")

    print("\n[1] Cập nhật subscription_plans")
    plan_count = await migrate_plans(db, apply)

    stats = {"owners": 0, "subscriptions": 0, "grants": 0, "credits": 0, "skipped_plans": []}
    print("\n[2] Companies")
    await migrate_owners(db, apply, Collections.COMPANIES, OWNER_COMPANY, stats)
    print("\n[3] Applicant profiles")
    await migrate_owners(db, apply, Collections.APPLICANT_PROFILES, OWNER_APPLICANT, stats)

    print("\n=== Tổng kết ===")
    print(f"Gói cước cập nhật     : {plan_count}")
    print(f"Owner đã duyệt        : {stats['owners']}")
    print(f"Subscription tạo mới  : {stats['subscriptions']}")
    print(f"Credit grant (legacy) : {stats['grants']} ({stats['credits']} credit)")
    if stats["skipped_plans"]:
        print(f"Owner đang ở gói lẻ / gói hết hạn → về Free ({len(stats['skipped_plans'])}):")
        for item in stats["skipped_plans"]:
            print(f"  - {item}")
    if not apply:
        print("\n(Dry-run: chưa ghi gì. Thêm --apply để chạy thật.)")

    await close_mongo_connection()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Ghi thật vào DB (mặc định chỉ dry-run)")
    asyncio.run(main(parser.parse_args().apply))
