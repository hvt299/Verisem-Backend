"""
Công cụ cập nhật URL Cloudinary cho CV và Cover Letter
Sử dụng khi bạn đã tạo xong file PDF trên TopCV và tải lên Cloudinary.

Cách sử dụng:
1. Cách 1: Cập nhật đơn lẻ cho 1 ứng viên qua email:
   python scripts/update_cloudinary_urls.py --email hoanglong.tech@gmail.com --cv-url https://res.cloudinary.com/.../cv.pdf --cl-url https://res.cloudinary.com/.../cl.pdf

2. Cách 2: Cập nhật hàng loạt từ file JSON (data/cloudinary_urls_mapping.json):
   python scripts/update_cloudinary_urls.py --batch data/cloudinary_urls_mapping.json
"""

import os
import sys
import json
import asyncio
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

from app.database.config import connect_to_mongo, close_mongo_connection, db_instance, Collections

async def update_single(email: str, cv_url: str = None, cl_url: str = None):
    await connect_to_mongo()
    db = db_instance.db
    email = email.lower().strip()

    user = await db[Collections.USERS].find_one({"email": email})
    if not user:
        print(f"❌ Không tìm thấy người dùng có email: {email}")
        await close_mongo_connection()
        return

    user_id_str = str(user["_id"])
    print(f"Đang cập nhật link Cloudinary cho ứng viên: {user.get('full_name')} ({email})")

    if cv_url:
        res_cv = await db[Collections.CVS].update_many(
            {"owner_user_id": user_id_str},
            {"$set": {"file_url": cv_url}}
        )
        res_app = await db[Collections.APPLICATIONS].update_many(
            {"applicant_user_id": user_id_str},
            {"$set": {"cv_snapshot.file_url": cv_url}}
        )
        print(f"✅ Đã cập nhật CV URL vào {res_cv.modified_count} bản ghi CVS và {res_app.modified_count} bản ghi APPLICATIONS.")

    if cl_url:
        res_cl = await db[Collections.COVER_LETTERS].update_many(
            {"owner_user_id": user_id_str},
            {"$set": {"file_url": cl_url}}
        )
        print(f"✅ Đã cập nhật Cover Letter URL vào {res_cl.modified_count} bản ghi COVER_LETTERS.")

    await close_mongo_connection()

async def update_batch(file_path: str):
    await connect_to_mongo()
    db = db_instance.db

    if not os.path.exists(file_path):
        print(f"❌ Không tìm thấy file {file_path}")
        await close_mongo_connection()
        return

    with open(file_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    print(f"Đang xử lý cập nhật hàng loạt cho {len(mapping)} ứng viên...")
    success_count = 0

    for item in mapping:
        email = item.get("email", "").lower().strip()
        cv_url = item.get("cv_url")
        cl_url = item.get("cl_url")

        user = await db[Collections.USERS].find_one({"email": email})
        if not user:
            print(f"⚠️ Không tìm thấy: {email}")
            continue

        user_id_str = str(user["_id"])
        if cv_url:
            await db[Collections.CVS].update_many({"owner_user_id": user_id_str}, {"$set": {"file_url": cv_url}})
            await db[Collections.APPLICATIONS].update_many({"applicant_user_id": user_id_str}, {"$set": {"cv_snapshot.file_url": cv_url}})

        if cl_url:
            await db[Collections.COVER_LETTERS].update_many({"owner_user_id": user_id_str}, {"$set": {"file_url": cl_url}})

        success_count += 1

    print(f"✅ Hoàn tất cập nhật hàng loạt cho {success_count}/{len(mapping)} ứng viên!")
    await close_mongo_connection()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update Cloudinary URLs for CVs & Cover Letters")
    parser.add_argument("--email", help="Email của ứng viên cần cập nhật")
    parser.add_argument("--cv-url", help="Link PDF CV trên Cloudinary")
    parser.add_argument("--cl-url", help="Link PDF Cover Letter trên Cloudinary")
    parser.add_argument("--batch", help="Đường dẫn file JSON chứa danh sách link hàng loạt")

    args = parser.parse_args()
    if args.batch:
        asyncio.run(update_batch(args.batch))
    elif args.email:
        asyncio.run(update_single(args.email, args.cv_url, args.cl_url))
    else:
        parser.print_help()
