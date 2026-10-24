import os
import sys

# Ensure UTF-8 stdout
sys.stdout.reconfigure(encoding='utf-8')

import argparse
import asyncio
from datetime import datetime, timezone
from bson import ObjectId

# Ensure backend root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

from app.core.security import get_password_hash, verify_password
from app.database.config import connect_to_mongo, close_mongo_connection, db_instance, Collections
from app.schemas.common_schema import UserRole

async def create_user_internal(email: str, password: str, full_name: str, role: str, company_id: str = None, job_title_internal: str = None):
    await connect_to_mongo()
    db = db_instance.db

    email_clean = email.strip().lower()
    existing = await db[Collections.USERS].find_one({"email": email_clean})
    if existing:
        print(f"❌ Lỗi: Email '{email_clean}' đã tồn tại trong hệ thống (ID: {existing.get('_id')})!")
        await close_mongo_connection()
        return None

    hashed_pwd = get_password_hash(password)
    now = datetime.now(timezone.utc)
    user_id = str(ObjectId())

    user_doc = {
        "_id": ObjectId(user_id),
        "email": email_clean,
        "full_name": full_name.strip(),
        "hashed_password": hashed_pwd,
        "role": role,
        "company_id": company_id if role in ["hr_owner", "hr_member"] else None,
        "department_id": None,
        "job_title_internal": job_title_internal,
        "is_verified": True,
        "email_verified_at": now,
        "is_active": True,
        "created_at": now,
        "updated_at": now
    }

    await db[Collections.USERS].insert_one(user_doc)
    print(f"✅ Tạo thành công User: {full_name} | Email: {email_clean} | Role: {role} | ID: {user_id}")

    # If applicant, also create applicant_profile
    if role == UserRole.APPLICANT.value:
        free_plan = await db[Collections.SUBSCRIPTION_PLANS].find_one({"plan_code": "app_free"})
        plan_id = str(free_plan["_id"]) if free_plan else None
        
        profile_doc = {
            "_id": ObjectId(),
            "user_id": user_id,
            "headline": "Ứng viên tìm việc",
            "desired_job_titles": [],
            "expected_salary_min": None,
            "expected_salary_max": None,
            "currency": "VND",
            "current_location": None,
            "preferred_locations": [],
            "willing_to_relocate": False,
            "current_plan_id": plan_id,
            "credits_remaining": 0,
            "is_searchable": True,
            "created_at": now,
            "updated_at": now
        }
        await db[Collections.APPLICANT_PROFILES].insert_one(profile_doc)
        print(f"   ↳ Đã tạo kèm applicant_profile cho user_id: {user_id}")

    await close_mongo_connection()
    return user_id

def main():
    parser = argparse.ArgumentParser(description="Verisem Admin CLI Tool")
    parser.add_argument("--hash", type=str, help="Sinh chuỗi hash chuẩn xác cho mật khẩu")
    parser.add_argument("--verify", nargs=2, metavar=("PASSWORD", "HASH"), help="Xác thực mật khẩu với chuỗi hash")
    parser.add_argument("--create-user", action="store_true", help="Tạo user mới")
    parser.add_argument("--email", type=str, help="Email người dùng")
    parser.add_argument("--password", type=str, help="Mật khẩu thô")
    parser.add_argument("--name", type=str, help="Họ và tên")
    parser.add_argument("--role", type=str, choices=["admin", "hr_owner", "hr_member", "applicant"], default="applicant", help="Vai trò người dùng")
    parser.add_argument("--company-id", type=str, default=None, help="Company ID (nếu là HR)")
    parser.add_argument("--title", type=str, default=None, help="Chức danh nội bộ")

    args = parser.parse_args()

    if args.hash:
        hashed = get_password_hash(args.hash)
        print("\n--- BĂM MẬT KHẨU CHUẨN (Bcrypt + SHA256) ---")
        print(f"Mật khẩu thô: {args.hash}")
        print(f"Chuỗi Hash : {hashed}")
        return

    if args.verify:
        pwd, h = args.verify
        matched = verify_password(pwd, h)
        print("\n--- KẾT QUẢ XÁC THỰC MẬT KHẨU ---")
        print(f"Mật khẩu : {pwd}")
        print(f"Khớp hash: {'✅ HỢP LỆ (True)' if matched else '❌ SAI MẬT KHẨU (False)'}")
        return

    if args.create_user:
        if not args.email or not args.password or not args.name:
            print("❌ Lỗi: Cần cung cấp đầy đủ --email, --password và --name khi tạo user!")
            return
        asyncio.run(create_user_internal(args.email, args.password, args.name, args.role, args.company_id, args.title))
        return

    parser.print_help()

if __name__ == "__main__":
    main()
