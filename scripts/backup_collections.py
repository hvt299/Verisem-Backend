import os
import sys
import json
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv(r"D:\Verisem\Verisem-Backend\.env")

MONGO_URL = os.getenv("MONGO_URL")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "verisem")

# 25 collections to be wiped
COLLECTIONS_TO_WIPE = [
    "users", "companies", "departments", "applicant_profiles",
    "jobs", "cvs", "cover_letters", "applications",
    "orders", "subscriptions", "quota_transactions", "credit_grants", "promotions",
    "saved_jobs", "saved_companies", "talent_pools", "matching_preferences", "company_reviews",
    "interviews", "interview_feedbacks", "reports", "support_tickets",
    "notifications", "audit_logs", "refresh_tokens"
]

async def run_backup():
    client = AsyncIOMotorClient(MONGO_URL)
    db_name = MONGO_URL.split("?")[0].split("/")[-1] if "/" in MONGO_URL.split("?")[0].split("//")[-1] else MONGO_DB_NAME
    db = client.get_default_database(db_name)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(r"D:\Verisem\Verisem-Backend\backups", f"backup_pre_reset_{timestamp_str}")
    os.makedirs(backup_dir, exist_ok=True)
    print(f"=== BẮT ĐẦU SAO LƯU DỮ LIỆU VÀO: {backup_dir} ===")

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database_name": db.name,
        "collections": {}
    }

    for coll_name in COLLECTIONS_TO_WIPE:
        docs = await db[coll_name].find({}).to_list(None)
        doc_count = len(docs)
        
        # Serialize docs
        clean_docs = []
        for d in docs:
            # Convert ObjectId to str
            d["_id"] = str(d["_id"])
            clean_docs.append(d)

        file_path = os.path.join(backup_dir, f"{coll_name}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(clean_docs, f, ensure_ascii=False, indent=2, default=str)

        manifest["collections"][coll_name] = {
            "count": doc_count,
            "file": os.path.basename(file_path),
            "size_bytes": os.path.getsize(file_path)
        }
        print(f"✅ Đã sao lưu: {coll_name:<22} -> {doc_count:>5} documents ({os.path.getsize(file_path)} bytes)")

    # Save manifest
    manifest_path = os.path.join(backup_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 HOÀN TẤT SAO LƯU 25 COLLECTIONS! File Manifest: {manifest_path}")
    client.close()
    return backup_dir

if __name__ == "__main__":
    asyncio.run(run_backup())
