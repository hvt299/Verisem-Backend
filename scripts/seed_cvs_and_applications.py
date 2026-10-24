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

from app.database.config import connect_to_mongo, close_mongo_connection, db_instance, Collections
from app.schemas.common_schema import ApplicationSource, ApplicationStatus

CLOUDINARY_BASE_URL = "https://res.cloudinary.com/dvwfbvxbb/raw/upload/v1/verisem"

async def seed_cvs_and_applications():
    await connect_to_mongo()
    db = db_instance.db
    now = datetime.now(timezone.utc)

    print("--- BẮT ĐẦU NẠP CVS, COVER LETTERS & APPLICATIONS CHO 5 JOBS TRỌNG ĐIỂM ---")

    # 1. Đọc dữ liệu case study & mapping job IDs
    case_study_file = os.path.join(DATA_DIR, "benchmark_case_study.json")
    with open(case_study_file, "r", encoding="utf-8") as f:
        case_study_data = json.load(f)
    candidates = case_study_data.get("candidates", [])
    benchmark_jobs = case_study_data.get("benchmark_jobs", [])
    b_job_by_key = {b["job_key"]: b for b in benchmark_jobs}

    mapping_file = os.path.join(DATA_DIR, "benchmark_job_ids_mapping.json")
    if not os.path.exists(mapping_file):
        print("Lỗi: Không tìm thấy file mapping job IDs. Vui lòng chạy seed_jobs.py trước.")
        await close_mongo_connection()
        return

    with open(mapping_file, "r", encoding="utf-8") as f:
        job_key_to_id = json.load(f)

    # 2. Lấy thông tin 5 Jobs từ MongoDB
    job_docs = {}
    for j_key, j_id in job_key_to_id.items():
        doc = await db[Collections.JOBS].find_one({"_id": ObjectId(j_id)})
        if doc:
            job_docs[j_key] = doc
            print(f"Đã tải Job từ DB: {doc.get('title')} (ID: {j_id})")

    # 3. Lấy thông tin 50 Applicants từ MongoDB
    candidate_emails = [c["email"].lower().strip() for c in candidates]
    applicant_users = await db[Collections.USERS].find({"email": {"$in": candidate_emails}}).to_list(100)
    user_by_email = {u["email"]: u for u in applicant_users}
    print(f"Tìm thấy {len(applicant_users)} User accounts tương ứng trong DB.")

    # 4. Xóa sạch dữ liệu cũ trong CVS, COVER_LETTERS, APPLICATIONS
    del_apps = await db[Collections.APPLICATIONS].delete_many({})
    del_cvs = await db[Collections.CVS].delete_many({})
    del_cls = await db[Collections.COVER_LETTERS].delete_many({})
    print(f"Đã làm sạch dữ liệu cũ: {del_apps.deleted_count} applications, {del_cvs.deleted_count} cvs, {del_cls.deleted_count} cover_letters.")

    # 5. Duyệt từng ứng viên để tạo CV, Cover Letter và Application
    inserted_cv_count = 0
    inserted_cl_count = 0
    inserted_app_count = 0

    for cand in candidates:
        email = cand["email"].lower().strip()
        user = user_by_email.get(email)
        if not user:
            print(f"Bỏ qua ứng viên {email}: Không tìm thấy user account")
            continue

        user_id_str = str(user["_id"])
        target_job_key = cand["target_job_key"]
        job_doc = job_docs.get(target_job_key)
        if not job_doc:
            print(f"Bỏ qua ứng viên {email}: Không tìm thấy job {target_job_key}")
            continue

        job_id_str = str(job_doc["_id"])
        company_id_str = str(job_doc["company_id"])

        # Format tên file an toàn
        safe_name = cand["name"].replace(" ", "_")
        cv_filename = f"CV_{safe_name}.pdf"
        cv_file_url = f"{CLOUDINARY_BASE_URL}/cvs/{cv_filename}"

        # 5.1 Tạo Cover Letter nếu có
        cl_id_str = None
        if cand.get("cover_letter"):
            cl_filename = f"CoverLetter_{safe_name}.pdf"
            cl_file_url = f"{CLOUDINARY_BASE_URL}/cover_letters/{cl_filename}"
            cl_doc = {
                "owner_user_id": user_id_str,
                "company_id": None,
                "display_name": f"Thư Giới Thiệu - {cand['name']}",
                "filename": cl_filename,
                "file_url": cl_file_url,
                "content": cand["cover_letter"],
                "created_at": now - timedelta(days=10)
            }
            res_cl = await db[Collections.COVER_LETTERS].insert_one(cl_doc)
            cl_id_str = str(res_cl.inserted_id)
            inserted_cl_count += 1

        # 5.2 Xây dựng raw_text phong phú cho CV (phục vụ BM25 & tìm kiếm toàn văn)
        exp_texts = []
        for exp in cand["experience"]:
            exp_texts.append(f"{exp['role']} tại {exp['company']} ({exp['period']}): {exp['projects']}. {exp['responsibilities']} Công nghệ: {exp['tech_stack']}")
        exp_combined = " \n".join(exp_texts)

        raw_text = (
            f"HỌ TÊN: {cand['name']}\n"
            f"EMAIL: {cand['email']} - SĐT: {cand['phone']} - ĐỊA CHỈ: {cand['location']['address']}\n"
            f"MỤC TIÊU NGHỀ NGHIỆP: {cand['headline']}\n"
            f"HỌC VẤN: {cand['education']['school']}, Ngành {cand['education']['major']}, Bằng {cand['education']['degree']}, Xếp loại {cand['education']['rank']} (Năm tốt nghiệp {cand['education']['grad_year']})\n"
            f"SỐ NĂM KINH NGHIỆM: {cand['yoe']} năm\n"
            f"KỸ NĂNG: {', '.join(cand['skills'])}\n"
            f"CHỨNG CHỈ: {', '.join(cand['certifications'])}\n"
            f"NGOẠI NGỮ: {', '.join(cand['languages'])}\n"
            f"KINH NGHIỆM LÀM VIỆC:\n{exp_combined}\n"
        )

        extracted_skills = [{"skill_id": None, "name": s} for s in cand["skills"]]
        skill_experience = {s: cand["yoe"] for s in cand["skills"]}

        # 5.3 Tạo bản ghi CV
        cv_doc = {
            "owner_user_id": user_id_str,
            "display_name": f"CV_{cand['name']}_{cand['desired_job_title']}.pdf",
            "is_primary": True,
            "filename": cv_filename,
            "file_url": cv_file_url,
            "raw_text": raw_text,
            "cv_vector_ref": [],
            "candidate_info": {
                "full_name": cand["name"],
                "email": cand["email"],
                "phone": cand["phone"],
                "current_location": cand["location"],
                "github": f"https://github.com/{cand['email'].split('@')[0]}",
                "linkedin": f"https://linkedin.com/in/{cand['email'].split('@')[0]}",
                "portfolio": [],
                "education_level": cand["education"]["degree"],
                "years_of_experience": cand["yoe"],
                "skill_experience": skill_experience,
                "languages": cand["languages"],
                "certifications": cand["certifications"],
                "job_hops": 1,
                "gap_months": 0,
                "fraud_analysis": {"detected": False, "penalty": 0.0}
            },
            "extracted_skills": extracted_skills,
            "created_at": now - timedelta(days=12)
        }
        res_cv = await db[Collections.CVS].insert_one(cv_doc)
        cv_id_str = str(res_cv.inserted_id)
        inserted_cv_count += 1

        # Cập nhật primary_cv_document_id vào profile ứng viên
        await db[Collections.APPLICANT_PROFILES].update_one(
            {"user_id": user_id_str},
            {"$set": {"primary_cv_document_id": cv_id_str}}
        )

        # 5.4 Tạo chi tiết Skill Matching & Top Contributing Sentences cho AI Score
        target_b_job = b_job_by_key.get(target_job_key, {})
        job_req_skills = target_b_job.get("required_skills", [])
        job_pref_skills = target_b_job.get("preferred_skills", [])
        knockout_skills = target_b_job.get("knockout_skills", [])

        skill_details = []
        for s in job_req_skills:
            matched = (s.lower() in [cs.lower() for cs in cand["skills"]])
            skill_details.append({
                "skill": s,
                "matched": matched,
                "confidence": 0.95 if matched else 0.0,
                "years_experience": cand["yoe"] if matched else 0.0,
                "is_knockout": (s in knockout_skills)
            })

        for s in job_pref_skills:
            matched = (s.lower() in [cs.lower() for cs in cand["skills"]])
            skill_details.append({
                "skill": s,
                "matched": matched,
                "confidence": 0.85 if matched else 0.0,
                "years_experience": cand["yoe"] if matched else 0.0,
                "is_knockout": False
            })

        # Câu văn dẫn chứng điểm cao nhất (explainability)
        top_sentences = []
        if cand["experience"]:
            first_exp = cand["experience"][0]
            top_sentences.append(f"{first_exp['role']} tại {first_exp['company']}: {first_exp['projects']}")
            if len(cand["experience"]) > 1:
                second_exp = cand["experience"][1]
                top_sentences.append(f"Kinh nghiệm trước: {second_exp['projects']}")
        if not top_sentences:
            top_sentences.append(f"Học vấn {cand['education']['school']} ngành {cand['education']['major']}.")

        ai_score_obj = {
            "total_score": cand["target_score"],
            "score_breakdown": {
                "skills_score": cand["score_breakdown"]["skills_score"],
                "experience_score": cand["score_breakdown"]["experience_score"],
                "education_score": cand["score_breakdown"]["education_score"],
                "nlp_score": cand["score_breakdown"]["nlp_score"],
                "penalty_score": cand["score_breakdown"]["penalty_score"]
            },
            "skill_details": skill_details,
            "top_contributing_sentences": top_sentences
        }

        # CVSnapshot
        cv_snapshot = {
            "cv_document_id": cv_id_str,
            "display_name": cv_doc["display_name"],
            "filename": cv_doc["filename"],
            "file_url": cv_doc["file_url"],
            "candidate_info": cv_doc["candidate_info"],
            "extracted_skills": extracted_skills
        }

        # 5.5 Tạo Application Record
        applied_at = now - timedelta(days=(20 - (int(cand["target_score"]) % 10)))
        app_doc = {
            "job_id": job_id_str,
            "cv_id": cv_id_str,
            "cv_snapshot": cv_snapshot,
            "company_id": company_id_str,
            "applicant_user_id": user_id_str,
            "source": ApplicationSource.APPLICANT_APPLY.value,
            "status": cand["target_status"],
            "ai_score": ai_score_obj,
            "cover_letter_id": cl_id_str,
            "applied_at": applied_at,
            "updated_at": now
        }

        if cand.get("rejection_reason"):
            app_doc["rejection_reason"] = cand["rejection_reason"]

        if cand.get("interview_schedule"):
            app_doc["interview_schedule"] = cand["interview_schedule"]

        if cand["target_status"] in [ApplicationStatus.OFFERED.value, ApplicationStatus.HIRED.value]:
            app_doc["offer_detail"] = {
                "offered_salary": int(cand["target_score"]) * 450000,
                "currency": "VND",
                "start_date": now + timedelta(days=15),
                "offer_file_url": f"{CLOUDINARY_BASE_URL}/offers/Offer_{safe_name}.pdf"
            }

        await db[Collections.APPLICATIONS].insert_one(app_doc)
        inserted_app_count += 1

    print(f"✅ Hoàn tất nạp dữ liệu!")
    print(f"- CVs tạo mới: {inserted_cv_count} bản ghi")
    print(f"- Cover Letters tạo mới: {inserted_cl_count} bản ghi")
    print(f"- Applications nạp vào 5 Jobs: {inserted_app_count} hồ sơ (Mỗi Job đúng 10 ứng viên phân tầng)")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_cvs_and_applications())
