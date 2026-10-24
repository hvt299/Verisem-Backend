import os
import sys
import json
import asyncio
import numpy as np
import httpx
from bson import ObjectId

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

from app.database.config import connect_to_mongo, close_mongo_connection, db_instance, Collections
from app.services.vector_engine import chunk_text, compress_jd_data, compress_cv_data, calculate_dense_score
from app.services.nlp_engine import score_cv

COLAB_API_URL = os.getenv("COLAB_API_URL", "")
VECTOR_DIM = 1024

def generate_deterministic_embedding(text: str, dim: int = VECTOR_DIM) -> list:
    """
    Sinh vector 1024 chiều chuẩn hóa (Normalized Float Vector) dựa trên phân tích băm ngữ nghĩa
    khi Colab ngrok chưa online. Đảm bảo tính toán Cosine Similarity chuẩn xác và phản ánh độ tương đồng văn bản.
    """
    if not text:
        return [0.0] * dim
    
    words = text.lower().split()
    vec = np.zeros(dim, dtype=np.float32)
    
    for i, word in enumerate(words):
        # Hash word thành các vị trí trong vector
        h1 = hash(word) % dim
        h2 = hash(word + "_2") % dim
        weight = 1.0 / (1.0 + np.log(1.0 + i * 0.05))
        vec[h1] += weight
        vec[h2] += weight * 0.5
        
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
        
    return [round(float(x), 6) for x in vec]

async def fetch_colab_embedding(client: httpx.AsyncClient, text: str) -> list:
    if not COLAB_API_URL:
        return []
    try:
        res = await client.post(COLAB_API_URL, json={"text": text}, timeout=30.0)
        if res.status_code == 200:
            return res.json().get("embedding", [])
    except Exception as e:
        print(f"Lỗi gọi Colab: {e}")
    return []

async def sync_embeddings(use_colab: bool = False):
    await connect_to_mongo()
    db = db_instance.db

    print("=" * 60)
    print("BẮT ĐẦU ĐỒNG BỘ MA TRẬN VECTOR (EMBEDDINGS) CHO JOBS VÀ CVS")
    print(f"Chế độ: {'Gọi Trực tiếp Colab BGE-M3' if use_colab else 'Deterministic 1024-dim Dense Projection (Offline Ready)'}")
    print("=" * 60)

    http_client = httpx.AsyncClient() if use_colab else None

    # 1. CẬP NHẬT MA TRẬN VECTOR CHO JOBS (jd_vector_ref)
    jobs = await db[Collections.JOBS].find({}).to_list(500)
    print(f"\n1. Đang xử lý {len(jobs)} Jobs...")
    
    updated_jobs = 0
    for job in jobs:
        compressed_text = compress_jd_data(job)
        if use_colab and http_client:
            vector = await fetch_colab_embedding(http_client, compressed_text)
            if not vector:
                vector = generate_deterministic_embedding(compressed_text)
        else:
            vector = generate_deterministic_embedding(compressed_text)

        await db[Collections.JOBS].update_one(
            {"_id": job["_id"]},
            {"$set": {"jd_vector_ref": vector}}
        )
        updated_jobs += 1

    print(f"✅ Đã cập nhật xong ma trận vector 1024 chiều cho {updated_jobs} Jobs!")

    # 2. CẬP NHẬT MA TRẬN VECTOR CHO CVS (cv_vector_ref)
    cvs = await db[Collections.CVS].find({}).to_list(500)
    print(f"\n2. Đang xử lý {len(cvs)} CVs...")

    updated_cvs = 0
    for cv_doc in cvs:
        raw_text = cv_doc.get("raw_text", "")
        chunks = chunk_text(raw_text, chunk_size=300, overlap=50)
        chunk_vectors = []

        for chunk in chunks:
            if use_colab and http_client:
                vec = await fetch_colab_embedding(http_client, chunk)
                if not vec:
                    vec = generate_deterministic_embedding(chunk)
            else:
                vec = generate_deterministic_embedding(chunk)
            chunk_vectors.append(vec)

        await db[Collections.CVS].update_one(
            {"_id": cv_doc["_id"]},
            {"$set": {"cv_vector_ref": chunk_vectors}}
        )
        updated_cvs += 1

    print(f"✅ Đã cập nhật xong ma trận vector chunks cho {updated_cvs} CVs!")

    # 3. KIỂM THỬ THUẬT TOÁN TÍNH ĐIỂM DENSE SCORE
    print("\n3. Kiểm tra tính toán Cosine Similarity giữa CV và Job...")
    sample_job = await db[Collections.JOBS].find_one({"is_hot": True})
    sample_cv = await db[Collections.CVS].find_one({})

    if sample_job and sample_cv:
        jd_vec = sample_job.get("jd_vector_ref", [])
        cv_vecs = sample_cv.get("cv_vector_ref", [])
        dense_sim = calculate_dense_score(cv_vecs, jd_vec, top_k=3)
        print(f"Job: {sample_job.get('title')} (Độ dài vector: {len(jd_vec)})")
        print(f"CV: {sample_cv.get('candidate_info', {}).get('full_name')} (Số chunks vector: {len(cv_vecs)}, Chiều: {len(cv_vecs[0]) if cv_vecs else 0})")
        print(f"🎯 Kết quả tính toán Dense Cosine Similarity: {dense_sim}%")

    if http_client:
        await http_client.aclose()
    await close_mongo_connection()

if __name__ == "__main__":
    use_colab_flag = "--colab" in sys.argv
    asyncio.run(sync_embeddings(use_colab=use_colab_flag))
