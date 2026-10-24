import os
import sys
import json
import asyncio
from datetime import datetime, timezone, timedelta
from bson import ObjectId

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

DATA_DIR = os.path.join(BASE_DIR, "data")
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

from app.core.security import get_password_hash
from app.database.config import connect_to_mongo, close_mongo_connection, db_instance, Collections
from app.schemas.common_schema import UserRole

APPLICANT_DEFAULT_PASSWORD = "Applicant@Verisem2026!"

async def seed_applicants():
    await connect_to_mongo()
    db = db_instance.db
    now = datetime.now(timezone.utc)

    print("--- BẮT ĐẦU KHỞI TẠO 50 TÀI KHOẢN APPLICANT & APPLICANT PROFILES ---")

    # 1. Đọc dữ liệu case study
    case_study_file = os.path.join(DATA_DIR, "benchmark_case_study.json")
    with open(case_study_file, "r", encoding="utf-8") as f:
        case_study_data = json.load(f)
    candidates = case_study_data.get("candidates", [])
    print(f"Đã nạp {len(candidates)} ứng viên từ file case study.")

    # 2. Lấy danh sách gói cước applicant
    plans = await db[Collections.SUBSCRIPTION_PLANS].find({"target_audience": "applicant"}).to_list(100)
    plans_by_code = {p.get("plan_code"): p for p in plans}
    print(f"Đã tìm thấy {len(plans)} gói cước applicant trong subscription_plans.")

    # 3. Xóa các applicant cũ nếu có
    # Tìm các user role applicant
    applicant_users = await db[Collections.USERS].find({"role": UserRole.APPLICANT.value}).to_list(500)
    applicant_ids = [u["_id"] for u in applicant_users]
    applicant_id_strs = [str(uid) for uid in applicant_ids]

    if applicant_ids:
        del_profiles = await db[Collections.APPLICANT_PROFILES].delete_many({"user_id": {"$in": applicant_id_strs}})
        del_users = await db[Collections.USERS].delete_many({"_id": {"$in": applicant_ids}})
        await db[Collections.SUBSCRIPTIONS].delete_many({"owner_type": "applicant", "owner_id": {"$in": applicant_id_strs}})
        await db[Collections.CREDIT_GRANTS].delete_many({"owner_type": "applicant", "owner_id": {"$in": applicant_id_strs}})
        print(f"Đã xóa {del_users.deleted_count} users applicant cũ và {del_profiles.deleted_count} profiles cũ (kèm subscriptions & credit grants).")

    # Mã hóa mật khẩu chuẩn
    hashed_pwd = get_password_hash(APPLICANT_DEFAULT_PASSWORD)

    users_to_insert = []
    candidates_with_user_id = []

    for cand in candidates:
        user_id = ObjectId()
        cand["mongo_user_id"] = str(user_id)
        candidates_with_user_id.append(cand)

        user_doc = {
            "_id": user_id,
            "email": cand["email"].lower().strip(),
            "hashed_password": hashed_pwd,
            "full_name": cand["name"],
            "phone": cand["phone"],
            "role": UserRole.APPLICANT.value,
            "company_id": None,
            "is_verified": True,
            "is_active": True,
            "created_at": now - timedelta(days=30),
            "updated_at": now
        }
        users_to_insert.append(user_doc)

    if users_to_insert:
        await db[Collections.USERS].insert_many(users_to_insert)
        print(f"✅ Đã tạo thành công {len(users_to_insert)} tài khoản User (Role: APPLICANT)!")

    # 4. Tạo 50 Applicant Profiles + Subscriptions + Credit Grants (Billing v2)
    profiles_to_insert = []
    subscriptions_to_insert = []
    credit_grants_to_insert = []
    for cand in candidates_with_user_id:
        user_id_str = cand["mongo_user_id"]
        plan_code = cand.get("plan_code", "app_free")
        matched_plan = plans_by_code.get(plan_code) or plans_by_code.get("app_free")

        plan_id = str(matched_plan["_id"]) if matched_plan else None
        features = matched_plan.get("features", {}) if matched_plan else {}
        ai_credits = features.get("ai_credits", 0)

        loc_info = cand.get("location", {})
        prov_code = loc_info.get("province_code", "01")
        prov_name = "Hà Nội" if prov_code == "01" else "Hồ Chí Minh"
        dist_name = loc_info.get("district_name", "Quận Cầu Giấy")
        addr_detail = loc_info.get("address", "")

        loc_detail = {
            "province_code": prov_code,
            "province_name": prov_name,
            "district_name": dist_name,
            "address_detail": addr_detail
        }

        profile_doc = {
            "user_id": user_id_str,
            "headline": cand.get("headline", ""),
            "desired_job_titles": [cand.get("desired_job_title", "")],
            "expected_salary_min": int(cand.get("target_score", 50)) * 400000,
            "expected_salary_max": int(cand.get("target_score", 50)) * 600000,
            "currency": "VND",
            "current_location": loc_detail,
            "preferred_locations": [loc_detail],
            "willing_to_relocate": False,
            "availability_date": None,
            "linkedin": f"https://linkedin.com/in/{cand['email'].split('@')[0]}",
            "portfolio": [f"https://github.com/{cand['email'].split('@')[0]}"],
            "industry_specific_data": {
                "highest_degree": cand["education"].get("degree"),
                "grad_school": cand["education"].get("school"),
                "years_experience": cand.get("yoe", 0.0)
            },
            "primary_cv_document_id": None, # Sẽ gán sau khi seed CVs ở task 3.4
            "external_cv_links": [],
            "is_searchable": True,
            "current_plan_id": plan_id,
            "current_period_start": now - timedelta(days=15),
            "current_period_end": now + timedelta(days=15),
            "credits_remaining": ai_credits,
            "hr_view_count": int(cand.get("target_score", 50)) * 2,
            "search_appearance_count": int(cand.get("target_score", 50)) * 5,
            "created_at": now - timedelta(days=30),
            "updated_at": now
        }
        profiles_to_insert.append(profile_doc)

        if matched_plan and matched_plan.get("plan_code") != "app_free":
            subscriptions_to_insert.append({
                "owner_type": "applicant",
                "owner_id": user_id_str,
                "plan_id": plan_id,
                "plan_code": matched_plan.get("plan_code"),
                "order_id": None,
                "status": "active",
                "period_start": now - timedelta(days=15),
                "period_end": now + timedelta(days=15),
                "created_at": now - timedelta(days=15),
                "migrated": True,
            })
            if ai_credits > 0:
                credit_grants_to_insert.append({
                    "owner_type": "applicant",
                    "owner_id": user_id_str,
                    "source": "legacy",
                    "source_ref": None,
                    "amount_granted": ai_credits,
                    "amount_remaining": ai_credits,
                    "expires_at": now + timedelta(days=15),
                    "created_at": now - timedelta(days=15),
                })

    if profiles_to_insert:
        await db[Collections.APPLICANT_PROFILES].insert_many(profiles_to_insert)
        print(f"✅ Đã tạo thành công {len(profiles_to_insert)} hồ sơ Applicant Profiles đầy đủ thông tin và khớp gói cước!")

    if subscriptions_to_insert:
        await db[Collections.SUBSCRIPTIONS].insert_many(subscriptions_to_insert)
        print(f"✅ Đã tạo thành công {len(subscriptions_to_insert)} Active Subscriptions cho Applicant!")

    if credit_grants_to_insert:
        await db[Collections.CREDIT_GRANTS].insert_many(credit_grants_to_insert)
        print(f"✅ Đã tạo thành công {len(credit_grants_to_insert)} Credit Grants cho Applicant!")

    # Lưu lại mapping candidate user_id để task 3.4 dùng nộp CV
    cand_user_mapping = {c["email"]: c["mongo_user_id"] for c in candidates_with_user_id}
    mapping_file = os.path.join(DATA_DIR, "candidate_user_ids_mapping.json")
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(cand_user_mapping, f, ensure_ascii=False, indent=2)
    print(f"✅ Đã lưu mapping Candidate User IDs vào: {mapping_file}")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_applicants())
