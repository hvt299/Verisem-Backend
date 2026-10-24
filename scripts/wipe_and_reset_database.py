import os
import sys

# Ensure backend root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import asyncio
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv(r"D:\Verisem\Verisem-Backend\.env")

from scripts.seed_initial_master_data import seed_all_initial_data
from app.database.config import connect_to_mongo, close_mongo_connection, db_instance, Collections

COLLECTIONS_TO_WIPE = [
    "users", "companies", "departments", "applicant_profiles",
    "jobs", "cvs", "cover_letters", "applications",
    "orders", "subscriptions", "quota_transactions", "credit_grants", "promotions",
    "saved_jobs", "saved_companies", "talent_pools", "matching_preferences", "company_reviews",
    "interviews", "interview_feedbacks", "reports", "support_tickets",
    "notifications", "audit_logs", "refresh_tokens"
]

async def execute_wipe_and_reset():
    print("================================================================")
    print("BƯỚC 1: KHỞI TẠO LẠI 6 COLLECTIONS DỮ LIỆU GỐC (MASTER DATA)")
    print("================================================================")
    await seed_all_initial_data()

    print("\n================================================================")
    print("BƯỚC 2: TIẾN HÀNH XÓA SẠCH DỮ LIỆU CỦA 25 COLLECTIONS NGHIỆP VỤ")
    print("================================================================")
    await connect_to_mongo()
    db = db_instance.db

    wipe_results = {}
    for coll_name in COLLECTIONS_TO_WIPE:
        res = await db[coll_name].delete_many({})
        wipe_results[coll_name] = res.deleted_count
        print(f"🗑️ Đã làm sạch: {coll_name:<22} (đã xóa {res.deleted_count:>4} docs)")

    print("\n================================================================")
    print("BƯỚC 3: KIỂM KÊ TOÀN DIỆN TRẠNG THÁI CÁC COLLECTIONS SAU RESET")
    print("================================================================")
    
    # Check blog_posts
    blog_count = await db[Collections.BLOG_POSTS].count_documents({})
    print(f"🛡️ [BẢO LƯU 100%] blog_posts: {blog_count} documents (KHÔNG CHẠM VÀO)")

    # Check 6 master collections
    master_colls = [
        "administrative_units", "certifications", "languages", 
        "skills", "subscription_plans", "system_settings"
    ]
    print("\n--- 6 COLLECTIONS MASTER DATA (ĐÃ KHỞI TẠO LẠI) ---")
    for m in master_colls:
        cnt = await db[m].count_documents({})
        print(f"✅ {m:<22}: {cnt:>6} documents")

    print("\n--- 25 COLLECTIONS NGHIỆP VỤ (ĐÃ LÀM SẠCH VỀ 0) ---")
    for w in COLLECTIONS_TO_WIPE:
        cnt = await db[w].count_documents({})
        status = "Trống (0 docs)" if cnt == 0 else f"Lỗi ({cnt} docs)"
        print(f"🧹 {w:<22}: {cnt:>6} docs -> {status}")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(execute_wipe_and_reset())
