import os
import sys
import json
import asyncio
from datetime import datetime, timezone
from bson import ObjectId

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database.config import connect_to_mongo, close_mongo_connection, db_instance, Collections
from scripts.seed_administrative_units import seed_locations
from scripts.seed_master_data import seed_master_data
from scripts.seed_skills import seed_skills

async def seed_subscription_plans():
    db = db_instance.db
    plans_file = os.path.join(BASE_DIR, "data", "subscription_plans", "subscription_plans.json")
    if not os.path.exists(plans_file):
        print(f"Lỗi: Không tìm thấy file {plans_file}")
        return

    with open(plans_file, "r", encoding="utf-8") as f:
        plans = json.load(f)

    await db[Collections.SUBSCRIPTION_PLANS].delete_many({})
    docs_to_insert = []
    for p in plans:
        if "_id" in p:
            try:
                p["_id"] = ObjectId(p["_id"])
            except Exception:
                pass
        for date_field in ["created_at", "updated_at"]:
            if p.get(date_field) and isinstance(p[date_field], str):
                try:
                    p[date_field] = datetime.fromisoformat(p[date_field].replace("Z", "+00:00"))
                except Exception:
                    p[date_field] = datetime.now(timezone.utc)
        docs_to_insert.append(p)

    if docs_to_insert:
        await db[Collections.SUBSCRIPTION_PLANS].insert_many(docs_to_insert)
        print(f"Đã import thành công {len(docs_to_insert)} gói cước vào subscription_plans!")

async def seed_system_settings():
    db = db_instance.db
    settings_file = os.path.join(BASE_DIR, "data", "system_settings", "system_settings.json")
    if not os.path.exists(settings_file):
        print(f"Lỗi: Không tìm thấy file {settings_file}")
        return

    with open(settings_file, "r", encoding="utf-8") as f:
        settings_list = json.load(f)

    await db[Collections.SYSTEM_SETTINGS].delete_many({})
    docs_to_insert = []
    for s in settings_list:
        if "_id" in s:
            try:
                s["_id"] = ObjectId(s["_id"])
            except Exception:
                pass
        docs_to_insert.append(s)

    if docs_to_insert:
        await db[Collections.SYSTEM_SETTINGS].insert_many(docs_to_insert)
        print(f"Đã import thành công {len(docs_to_insert)} cấu hình vào system_settings!")

async def seed_all_initial_data():
    print("==================================================")
    print("BẮT ĐẦU KHỞI TẠO LẠI 6 COLLECTIONS DỮ LIỆU GỐC")
    print("==================================================")
    await connect_to_mongo()
    
    # 1. Administrative Units
    print("\n--- 1. Khởi tạo administrative_units ---")
    await seed_locations()

    # 2. Master Data (Certifications & Languages)
    print("\n--- 2. Khởi tạo languages & certifications ---")
    await seed_master_data()

    # 3. Skills
    print("\n--- 3. Khởi tạo skills ---")
    await seed_skills()

    # 4. Subscription Plans
    print("\n--- 4. Khởi tạo subscription_plans ---")
    await seed_subscription_plans()

    # 5. System Settings
    print("\n--- 5. Khởi tạo system_settings ---")
    await seed_system_settings()

    await close_mongo_connection()
    print("\n==================================================")
    print("HOÀN TẤT KHỞI TẠO 6 COLLECTIONS DỮ LIỆU BAN ĐẦU!")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(seed_all_initial_data())
