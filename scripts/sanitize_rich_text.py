"""
Làm sạch HTML đã lưu trong DB (chống Stored XSS) cho:
- jobs: description, requirements, benefits, other_info
- companies: description
- blog_posts: content_html

Mặc định chỉ chạy thử (dry-run), KHÔNG ghi gì vào DB:
    python -m scripts.sanitize_rich_text
Ghi thật:
    python -m scripts.sanitize_rich_text --apply
"""
import argparse
import asyncio

from app.core.html_sanitizer import sanitize_rich_html
from app.database.config import db_instance, connect_to_mongo, close_mongo_connection, Collections

TARGETS = [
    (Collections.JOBS, ["description", "requirements", "benefits", "other_info"]),
    (Collections.COMPANIES, ["description"]),
    (Collections.BLOG_POSTS, ["content_html"]),
]


async def main(apply: bool):
    await connect_to_mongo()
    db = db_instance.db
    print(f"=== Sanitize rich text ({'APPLY' if apply else 'DRY-RUN'}) trên DB: {db.name} ===")

    for collection, fields in TARGETS:
        changed = 0
        async for doc in db[collection].find({}, {f: 1 for f in fields}):
            update = {}
            for field in fields:
                value = doc.get(field)
                if isinstance(value, str):
                    cleaned = sanitize_rich_html(value)
                    if cleaned != value:
                        update[field] = cleaned
            if update:
                changed += 1
                print(f"  [{collection}] {doc['_id']}: {', '.join(update)}")
                if apply:
                    await db[collection].update_one({"_id": doc["_id"]}, {"$set": update})
        print(f"{collection}: {changed} bản ghi cần làm sạch")

    if not apply:
        print("\n(Dry-run: chưa ghi gì. Thêm --apply để chạy thật.)")
    await close_mongo_connection()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Ghi thật vào DB (mặc định chỉ dry-run)")
    asyncio.run(main(parser.parse_args().apply))
