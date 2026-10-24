import os
import sys
import json
import asyncio
from datetime import datetime, timezone, timedelta
from bson import ObjectId

# Ensure backend root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

DATA_DIR = os.path.join(BASE_DIR, "data")
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

from app.database.config import connect_to_mongo, close_mongo_connection, db_instance, Collections
from app.schemas.common_schema import CompanyStatus, JobStatus
from app.services.vector_engine import compress_jd_data
from scripts.sync_bge_embeddings import generate_deterministic_embedding

BENCHMARK_EXTRA_JOBS = {
    "fpt": [
        {
            "title": "Lead Solution Architect (Cloud & Microservices)",
            "level": "Lead", "yoe": 6.0, "sal_min": 50000000, "sal_max": 80000000,
            "status": JobStatus.OPEN.value, "days_offset": 30,
            "req_skills": ["cloud architecture", "aws", "microservices", "kubernetes", "system design"],
            "pref_skills": ["azure", "terraform", "kafka", "devops"],
            "knockout": ["cloud architecture", "aws"],
            "desc": "Chịu trách nhiệm thiết kế kiến trúc giải pháp tổng thể cho các dự án quy mô lớn của khách hàng toàn cầu tại FPT Software. Tư vấn lộ trình chuyển dịch hạ tầng lên Cloud (AWS/Azure) và giám sát việc áp dụng kiến trúc Microservices hiệu năng cao.",
            "reqs": "- Tối thiểu 6 năm kinh nghiệm trong phát triển phần mềm, trong đó ít nhất 2 năm ở vị trí Solution Architect.\n- Sở hữu chứng chỉ AWS Solutions Architect Professional hoặc tương đương.\n- Nắm vững các mô hình distributed systems, high availability, resilience pattern.",
            "benefits": "- Gói đãi ngộ 50 - 80 triệu VNĐ/tháng + Performance Bonus.\n- Cơ hội on-site tại Mỹ, Nhật Bản, châu Âu.\n- FPT Care cho bản thân và gia đình."
        },
        {
            "title": "Frontend ReactJS / Next.js Specialist",
            "level": "Middle", "yoe": 2.5, "sal_min": 22000000, "sal_max": 35000000,
            "status": JobStatus.OPEN.value, "days_offset": 25,
            "req_skills": ["reactjs", "typescript", "next.js", "tailwind css", "redux"],
            "pref_skills": ["graphql", "web performance", "jest", "storybook"],
            "knockout": ["reactjs", "typescript"],
            "desc": "Phát triển giao diện ứng dụng web hiện đại, tối ưu hóa hiệu năng render và trải nghiệm người dùng (Core Web Vitals). Phối hợp chặt chẽ với đội ngũ UI/UX Designer và Backend API Team.",
            "reqs": "- Tối thiểu 2.5 năm kinh nghiệm thực chiến với ReactJS, Next.js và TypeScript.\n- Am hiểu SSR/SSG, State Management (Zustand, Redux Toolkit).\n- Tư duy thẩm mỹ tốt, kỹ năng viết CSS hiện đại với Tailwind.",
            "benefits": "- Mức lương: 22 - 35 triệu VNĐ/tháng.\n- Thưởng dự án định kỳ, hỗ trợ thi chứng chỉ quốc tế."
        },
        {
            "title": "Embedded C/C++ Automotive Engineer",
            "level": "Senior", "yoe": 4.0, "sal_min": 30000000, "sal_max": 48000000,
            "status": JobStatus.CLOSED.value, "days_offset": -20,
            "req_skills": ["c++", "embedded c", "autosar", "can bus", "rtos"],
            "pref_skills": ["linux embedded", "git", "python scripting"],
            "knockout": ["embedded c", "c++"],
            "desc": "Phát triển phần mềm điều khiển cho các hệ thống ECU ô tô thông minh đạt chuẩn AUTOSAR. Viết driver điều khiển ngoại vi, tích hợp giao thức truyền thông CAN, LIN, Ethernet.",
            "reqs": "- Tối thiểu 4 năm kinh nghiệm lập trình C/C++ cho các hệ thống nhúng (Embedded Systems).\n- Am hiểu kiến trúc AUTOSAR và quy trình phát triển chuẩn ISO 26262.",
            "benefits": "- Mức lương thỏa thuận 30 - 48 triệu VNĐ/tháng.\n- Đã chốt danh sách ứng viên đợt 1."
        }
    ],
    "vng": [
        {
            "title": "Staff AI / ML Research Engineer (NLP & LLMs)",
            "level": "Senior", "yoe": 5.0, "sal_min": 45000000, "sal_max": 75000000,
            "status": JobStatus.OPEN.value, "days_offset": 45,
            "req_skills": ["nlp", "pytorch", "llm", "transformers", "python"],
            "pref_skills": ["huggingface", "deepspeed", "rag", "langchain"],
            "knockout": ["nlp", "llm"],
            "desc": "Nghiên cứu, huấn luyện và fine-tune các mô hình ngôn ngữ lớn (LLMs), tối ưu hóa pipeline RAG phục vụ hàng triệu người dùng hệ sinh thái Zalo và ZaloPay tại VNG.",
            "reqs": "- Tối thiểu 5 năm kinh nghiệm về Machine Learning / Deep Learning, chuyên sâu về NLP.\n- Có bài báo tại các hội nghị uy tín (ACL, EMNLP, NeurIPS) hoặc kinh nghiệm triển khai LLM thực tế.",
            "benefits": "- Mức lương 45 - 75 triệu VNĐ/tháng + Thưởng ESOP VNG hấp dẫn.\n- Làm việc tại VNG Campus chuẩn quốc tế, hồ bơi, phòng gym, bữa ăn miễn phí."
        },
        {
            "title": "DevOps / SRE Platform Engineer (Kubernetes, Hybrid Cloud)",
            "level": "Middle", "yoe": 3.0, "sal_min": 28000000, "sal_max": 45000000,
            "status": JobStatus.OPEN.value, "days_offset": 15,
            "req_skills": ["kubernetes", "docker", "terraform", "ci/cd", "linux"],
            "pref_skills": ["prometheus", "grafana", "istio", "aws", "golang"],
            "knockout": ["kubernetes", "docker"],
            "desc": "Vận hành và mở rộng hạ tầng Cloud Native cho hệ thống game online và fintech có lưu lượng hàng chục nghìn RPS. Tự động hóa CI/CD pipeline và tối ưu chi phí hạ tầng.",
            "reqs": "- Tối thiểu 3 năm kinh nghiệm thực chiến quản trị Kubernetes Cluster trên production.\n- Thành thạo Infrastructure as Code (Terraform) và hệ thống giám sát Prometheus/Grafana.",
            "benefits": "- Lương 28 - 45 triệu VNĐ/tháng + Performance bonus 3-5 tháng lương/năm."
        },
        {
            "title": "Game Producer / LiveOps Specialist",
            "level": "Middle", "yoe": 2.5, "sal_min": 25000000, "sal_max": 38000000,
            "status": JobStatus.CLOSED.value, "days_offset": -15,
            "req_skills": ["game design", "liveops", "data analytics", "monetization"],
            "pref_skills": ["unity", "sql", "jira"],
            "knockout": ["game design"],
            "desc": "Quản lý vòng đời vận hành game mobile (LiveOps), thiết kế sự kiện in-game, phân tích phễu doanh thu và hành vi game thủ nhằm tối ưu hóa ARPU và Retention rate.",
            "reqs": "- Tối thiểu 2.5 năm kinh nghiệm làm LiveOps hoặc Game Producer cho các tựa game nổi tiếng.\n- Đam mê sâu sắc với ngành công nghiệp game và am hiểu thị trường game ĐNA.",
            "benefits": "- Lương 25 - 38 triệu + Thưởng KPI doanh thu game vượt mức cam kết."
        }
    ],
    "viettel": [
        {
            "title": "5G Core Network & Telecom Cloud Engineer",
            "level": "Senior", "yoe": 4.5, "sal_min": 35000000, "sal_max": 60000000,
            "status": JobStatus.OPEN.value, "days_offset": 30,
            "req_skills": ["5g core", "telecom", "openstack", "linux", "networking"],
            "pref_skills": ["k8s telecom", "wireshark", "nfv", "python"],
            "knockout": ["5g core", "telecom"],
            "desc": "Tham gia nghiên cứu, làm chủ công nghệ mạng lõi 5G Core (5GC) Make in Vietnam của Tập đoàn Viettel. Thiết kế kiến trúc mạng ảo hóa NFV và triển khai trên hạ tầng Telco Cloud.",
            "reqs": "- Tốt nghiệp ĐH chuyên ngành Điện tử viễn thông, CNTT.\n- Tối thiểu 4.5 năm kinh nghiệm trong ngành viễn thông di động (4G/5G Core).\n- Nắm vững các chuẩn 3GPP Release 15/16/17.",
            "benefits": "- Mức lương 35 - 60 triệu VNĐ/tháng.\n- Thưởng sáng kiến ý tưởng công nghệ lên đến hàng trăm triệu đồng.\n- Môi trường nghiên cứu đỉnh cao, cơ sở vật chất dẫn đầu Việt Nam."
        },
        {
            "title": "SOC Tier 2 Cyber Security Analyst",
            "level": "Middle", "yoe": 2.5, "sal_min": 24000000, "sal_max": 38000000,
            "status": JobStatus.OPEN.value, "days_offset": 20,
            "req_skills": ["soc", "siem", "incident response", "network security", "wireshark"],
            "pref_skills": ["splunk", "edr", "ceh", "cisp"],
            "knockout": ["soc", "siem"],
            "desc": "Giám sát, phân tích và ứng cứu sự cố an ninh mạng 24/7 cho hạ tầng mạng trọng yếu quốc gia và khách hàng doanh nghiệp tại Trung tâm An ninh mạng Viettel (VCS).",
            "reqs": "- Tối thiểu 2.5 năm kinh nghiệm làm việc tại SOC.\n- Thành thạo các hệ thống SIEM (Splunk, Elastic, QRadar).\n- Sở hữu chứng chỉ CEH, Security+ hoặc tương đương.",
            "benefits": "- Lương 24 - 38 triệu VNĐ/tháng + Phụ cấp ca kíp, thưởng dự án an toàn thông tin."
        },
        {
            "title": "IoT Hardware Firmware Developer",
            "level": "Middle", "yoe": 2.0, "sal_min": 20000000, "sal_max": 32000000,
            "status": JobStatus.CLOSED.value, "days_offset": -30,
            "req_skills": ["firmware", "c/c++", "stm32", "lora", "ble"],
            "pref_skills": ["pcb design", "altium", "freertos"],
            "knockout": ["firmware", "stm32"],
            "desc": "Lập trình firmware cho các thiết bị công tơ điện thông minh, cảm biến giám sát nông nghiệp công nghệ cao và thiết bị định vị GPS do Viettel sản xuất.",
            "reqs": "- Tối thiểu 2 năm kinh nghiệm lập trình vi điều khiển ARM Cortex-M (STM32, ESP32).\n- Hiểu biết sâu về các giao thức không dây tầm xa LoRa, NB-IoT.",
            "benefits": "- Thu nhập 20 - 32 triệu VNĐ/tháng.\n- Đã đủ số lượng hồ sơ phỏng vấn."
        }
    ],
    "vnpt": [
        {
            "title": "Enterprise Cloud Solutions Consultant",
            "level": "Senior", "yoe": 4.0, "sal_min": 32000000, "sal_max": 52000000,
            "status": JobStatus.OPEN.value, "days_offset": 25,
            "req_skills": ["cloud consulting", "smart city", "saas", "presales", "enterprise architecture"],
            "pref_skills": ["government it", "proposal writing", "presentation"],
            "knockout": ["cloud consulting", "presales"],
            "desc": "Tư vấn thiết kế giải pháp Chuyển đổi số, Hạ tầng Điện toán đám mây Smart Cloud và Trung tâm điều hành thông minh (IOC) cho các Sở ban ngành và tập đoàn lớn.",
            "reqs": "- Tối thiểu 4 năm kinh nghiệm làm Presales/Solution Consultant mảng Enterprise IT.\n- Kỹ năng thuyết trình, bảo vệ giải pháp trước Hội đồng thẩm định cấp cao.",
            "benefits": "- Lương 32 - 52 triệu/tháng + Thưởng hoa hồng dự án chuyển đổi số.\n- Chế độ đãi ngộ Tập đoàn nhà nước vững mạnh, bảo hiểm toàn diện."
        },
        {
            "title": "Big Data Platform Engineer (Spark, Hadoop, Kafka)",
            "level": "Middle", "yoe": 3.0, "sal_min": 26000000, "sal_max": 42000000,
            "status": JobStatus.OPEN.value, "days_offset": 18,
            "req_skills": ["big data", "apache spark", "kafka", "hadoop", "sql"],
            "pref_skills": ["airflow", "scala", "hive", "clickhouse"],
            "knockout": ["big data", "apache spark"],
            "desc": "Xây dựng và tối ưu hóa hệ thống Data Pipeline xử lý dữ liệu viễn thông hàng chục Terabyte mỗi ngày phục vụ phân tích cước và cá nhân hóa trải nghiệm khách hàng.",
            "reqs": "- Tối thiểu 3 năm kinh nghiệm làm Big Data Engineer.\n- Thành thạo Apache Spark, Kafka streaming và cơ sở dữ liệu phân tán ClickHouse/Cassandra.",
            "benefits": "- Lương 26 - 42 triệu VNĐ/tháng + Thưởng thành tích xuất sắc quý."
        },
        {
            "title": "Chuyên viên Quản trị Hệ thống CSDL Oracle (Oracle DBA)",
            "level": "Senior", "yoe": 5.0, "sal_min": 35000000, "sal_max": 50000000,
            "status": JobStatus.CLOSED.value, "days_offset": -10,
            "req_skills": ["oracle dba", "rac", "dataguard", "performance tuning", "pl/sql"],
            "pref_skills": ["goldengate", "exadata", "linux redhat"],
            "knockout": ["oracle dba", "rac"],
            "desc": "Quản trị, sao lưu dự phòng và tối ưu hóa hiệu năng cụm cơ sở dữ liệu Oracle RAC quy mô cực lớn đảm bảo tính sẵn sàng 99.999% cho hệ thống tính cước viễn thông.",
            "reqs": "- Tối thiểu 5 năm làm Oracle DBA, có chứng chỉ OCP hoặc OCM.\n- Nắm chắc công nghệ Oracle DataGuard, ASM, RMAN.",
            "benefits": "- Mức lương 35 - 50 triệu VNĐ/tháng."
        }
    ],
    "momo": [
        {
            "title": "Senior Payment Backend Engineer (Golang / High Concurrency)",
            "level": "Senior", "yoe": 4.0, "sal_min": 38000000, "sal_max": 65000000,
            "status": JobStatus.OPEN.value, "days_offset": 30,
            "req_skills": ["golang", "microservices", "redis", "kafka", "grpc"],
            "pref_skills": ["high throughput", "payment gateway", "mongodb", "distributed tracing"],
            "knockout": ["golang", "microservices"],
            "desc": "Phát triển các core service thanh toán điện tử, ví MoMo xử lý hàng triệu giao dịch mỗi ngày. Đảm bảo giao dịch an toàn tuyệt đối, độ trễ p99 dưới 50ms.",
            "reqs": "- Tối thiểu 4 năm kinh nghiệm Backend, trong đó có ít nhất 2 năm lập trình Golang.\n- Nắm vững các nguyên lý ACID, Saga Pattern, Idempotency trong hệ thống thanh toán tài chính.",
            "benefits": "- Lương 38 - 65 triệu VNĐ/tháng + Performance bonus 3-6 tháng lương.\n- Gói bảo hiểm sức khỏe cao cấp Liberty cho cả gia đình."
        },
        {
            "title": "Risk & Fraud Detection Data Scientist",
            "level": "Middle", "yoe": 3.0, "sal_min": 30000000, "sal_max": 50000000,
            "status": JobStatus.OPEN.value, "days_offset": 22,
            "req_skills": ["machine learning", "fraud detection", "python", "xgboost", "sql"],
            "pref_skills": ["graph neural network", "feature engineering", "flink"],
            "knockout": ["machine learning", "python"],
            "desc": "Xây dựng các mô hình Machine Learning dự đoán và ngăn chặn gian lận giao dịch ví điện tử theo thời gian thực (Real-time Fraud Detection).",
            "reqs": "- Tối thiểu 3 năm kinh nghiệm Data Science trong lĩnh vực FinTech, Banking hoặc E-Commerce.\n- Am hiểu kỹ thuật xử lý dữ liệu bất cân bằng (Imbalanced Data) và mô hình phân loại rủi ro.",
            "benefits": "- Lương 30 - 50 triệu VNĐ/tháng + Thưởng dự án chống gian lận thành công."
        },
        {
            "title": "Mobile iOS Developer (Swift / SwiftUI)",
            "level": "Middle", "yoe": 2.5, "sal_min": 24000000, "sal_max": 38000000,
            "status": JobStatus.CLOSED.value, "days_offset": -25,
            "req_skills": ["swift", "ios", "swiftui", "combine", "clean architecture"],
            "pref_skills": ["modular architecture", "ci/cd fastlane", "unit test"],
            "knockout": ["swift", "ios"],
            "desc": "Tham gia phát triển các tính năng Super App MoMo trên hệ điều hành iOS. Tối ưu bộ nhớ, kích thước ứng dụng và tốc độ khởi động app.",
            "reqs": "- Tối thiểu 2.5 năm kinh nghiệm lập trình iOS với Swift.\n- Có ứng dụng tự phát triển hoặc tham gia nhóm phát triển đã release trên App Store.",
            "benefits": "- Mức lương 24 - 38 triệu/tháng. Đã tuyển đủ chỉ tiêu đợt này."
        }
    ]
}

# Industry job templates for diverse domain roles
INDUSTRY_TEMPLATES = {
    "it": [
        {"title": "Senior React / NodeJS Fullstack Developer", "level": "Senior", "yoe": 4.0, "sal_min": 30000000, "sal_max": 50000000, "req_skills": ["react", "node.js", "typescript", "postgresql"], "pref_skills": ["docker", "aws"], "knockout": ["react", "node.js"], "desc": "Phát triển ứng dụng Web quy mô lớn với React và NodeJS microservices.", "reqs": "- 4 năm kinh nghiệm fullstack.\n- Thành thạo TypeScript.", "benefits": "- Lương 30 - 50M + KPI."},
        {"title": "Quality Assurance Automation Engineer", "level": "Middle", "yoe": 2.5, "sal_min": 20000000, "sal_max": 35000000, "req_skills": ["selenium", "cypress", "automation test", "python"], "pref_skills": ["ci/cd", "postman"], "knockout": ["automation test"], "desc": "Xây dựng automation test framework kiểm thử tự động API và Web UI.", "reqs": "- 2.5 năm làm QA Automation.", "benefits": "- Lương 20 - 35M."}
    ],
    "sales": [
        {"title": "Chuyên viên Quản lý Khách hàng Doanh nghiệp (B2B Sales Specialist)", "level": "Middle", "yoe": 2.0, "sal_min": 18000000, "sal_max": 32000000, "req_skills": ["b2b sales", "negotiation", "crm", "lead generation"], "pref_skills": ["presentation"], "knockout": ["b2b sales"], "desc": "Tìm kiếm, thiết lập quan hệ và đàm phán hợp đồng cung ứng với đối tác doanh nghiệp lớn.", "reqs": "- 2 năm kinh nghiệm Sales B2B.\n- Kỹ năng đàm phán xuất sắc.", "benefits": "- Lương cứng 18 - 32M + Hoa hồng."},
        {"title": "Key Account Manager (KAM) Kênh Đại lý Toàn quốc", "level": "Senior", "yoe": 4.0, "sal_min": 28000000, "sal_max": 45000000, "req_skills": ["key account", "channel management", "b2b sales"], "pref_skills": ["leadership"], "knockout": ["key account"], "desc": "Quản lý và phát triển hệ thống đại lý phân phối trên toàn quốc.", "reqs": "- 4 năm làm KAM.", "benefits": "- Lương 28 - 45M + Thưởng doanh số."}
    ],
    "marketing": [
        {"title": "Chuyên viên Digital Marketing & Performance Media", "level": "Middle", "yoe": 2.0, "sal_min": 20000000, "sal_max": 35000000, "req_skills": ["digital marketing", "facebook ads", "google ads", "seo"], "pref_skills": ["content marketing"], "knockout": ["digital marketing"], "desc": "Lên kế hoạch và thực thi các chiến dịch quảng cáo đa kênh tối ưu CPA/CPL.", "reqs": "- 2 năm quản lý ngân sách 100M+/tháng.", "benefits": "- Lương 20 - 35M + Thưởng KPI."},
        {"title": "Brand Marketing Specialist & Content Strategist", "level": "Middle", "yoe": 2.5, "sal_min": 18000000, "sal_max": 30000000, "req_skills": ["brand marketing", "copywriting", "creative strategy"], "pref_skills": ["pr"], "knockout": ["brand marketing"], "desc": "Định vị thương hiệu, xây dựng câu chuyện truyền thông và triển khai chiến dịch định vị.", "reqs": "- 2.5 năm làm Brand Marketing.", "benefits": "- Lương 18 - 30M."}
    ],
    "finance_banking": [
        {"title": "Chuyên viên Thẩm định Tín dụng & Quản trị Rủi ro", "level": "Middle", "yoe": 2.5, "sal_min": 20000000, "sal_max": 32000000, "req_skills": ["credit analysis", "risk management", "financial reporting"], "pref_skills": ["banking"], "knockout": ["credit analysis"], "desc": "Thẩm định hồ sơ tín dụng doanh nghiệp, phân tích báo cáo tài chính và phòng ngừa rủi ro.", "reqs": "- 2.5 năm thẩm định ngân hàng.", "benefits": "- Lương 20 - 32M + Thưởng quý."},
        {"title": "Chuyên viên Phân tích Đầu tư Tài chính (Investment Analyst)", "level": "Senior", "yoe": 4.0, "sal_min": 30000000, "sal_max": 50000000, "req_skills": ["financial modeling", "investment analysis", "valuation"], "pref_skills": ["cfa"], "knockout": ["financial modeling"], "desc": "Xây dựng mô hình định giá doanh nghiệp, phân tích thị trường vốn và lập báo cáo đầu tư.", "reqs": "- 4 năm làm phân tích tài chính/chứng khoán.", "benefits": "- Lương 30 - 50M."}
    ],
    "accounting_auditing": [
        {"title": "Chuyên viên Kế toán Tổng hợp & Thuế (General Accountant)", "level": "Middle", "yoe": 2.5, "sal_min": 18000000, "sal_max": 28000000, "req_skills": ["financial reporting", "tax accounting", "excel", "misa"], "pref_skills": ["auditing"], "knockout": ["tax accounting"], "desc": "Lập báo cáo tài chính, kê khai quyết toán thuế và đối chiếu số liệu định kỳ.", "reqs": "- 2.5 năm kế toán tổng hợp.", "benefits": "- Lương 18 - 28M."}
    ],
    "hr_admin_legal": [
        {"title": "Chuyên viên Tuyển dụng Cao cấp (Senior Talent Acquisition)", "level": "Senior", "yoe": 3.0, "sal_min": 22000000, "sal_max": 35000000, "req_skills": ["talent acquisition", "headhunting", "interviewing"], "pref_skills": ["employer branding"], "knockout": ["talent acquisition"], "desc": "Tuyển dụng nhân sự cấp cao và các vị trí trọng yếu, xây dựng thương hiệu tuyển dụng.", "reqs": "- 3 năm làm Talent Acquisition.", "benefits": "- Lương 22 - 35M."}
    ],
    "logistics": [
        {"title": "Chuyên viên Điều phối Vận tải & Chuỗi cung ứng (Logistics Coordinator)", "level": "Middle", "yoe": 2.0, "sal_min": 16000000, "sal_max": 26000000, "req_skills": ["supply chain", "freight forwarding", "customs clearance"], "pref_skills": ["incoterms"], "knockout": ["freight forwarding"], "desc": "Điều phối vận tải hàng hóa xuất nhập khẩu, làm thủ tục hải quan và kiểm soát chi phí.", "reqs": "- 2 năm làm Logistics.", "benefits": "- Lương 16 - 26M."}
    ],
    "manufacturing": [
        {"title": "Kỹ sư Quản lý Chất lượng Sản xuất (QA/QC Engineer)", "level": "Middle", "yoe": 2.5, "sal_min": 18000000, "sal_max": 28000000, "req_skills": ["quality control", "iso 9001", "kaizen", "5s"], "pref_skills": ["six sigma"], "knockout": ["quality control"], "desc": "Giám sát chất lượng dây chuyền sản xuất và nguyên vật liệu đầu vào.", "reqs": "- 2.5 năm làm QA/QC sản xuất.", "benefits": "- Lương 18 - 28M."}
    ],
    "healthcare": [
        {"title": "Dược sĩ Chuyên môn / Trình dược viên Bệnh viện (Medical Representative)", "level": "Middle", "yoe": 2.0, "sal_min": 18000000, "sal_max": 30000000, "req_skills": ["pharmacology", "medical sales", "communication"], "pref_skills": ["hospital networking"], "knockout": ["pharmacology"], "desc": "Giới thiệu sản phẩm dược phẩm chuyên khoa tới các bệnh viện và nhà thuốc uy tín.", "reqs": "- Tốt nghiệp Dược/Y khoa, 2 năm kinh nghiệm.", "benefits": "- Lương 18 - 30M + Hoa hồng."}
    ],
    "education": [
        {"title": "Chuyên viên Phát triển Chương trình Đào tạo (Instructional Designer)", "level": "Middle", "yoe": 2.5, "sal_min": 18000000, "sal_max": 28000000, "req_skills": ["curriculum design", "e-learning", "pedagogy"], "pref_skills": ["lms"], "knockout": ["curriculum design"], "desc": "Thiết kế bài giảng e-learning tương tác và phát triển khung năng lực học tập chuẩn quốc tế.", "reqs": "- 2.5 năm thiết kế chương trình giáo dục.", "benefits": "- Lương 18 - 28M."}
    ],
    "customer_service": [
        {"title": "Trưởng nhóm Vận hành Dịch vụ Khách hàng (Customer Care Lead)", "level": "Middle", "yoe": 2.5, "sal_min": 18000000, "sal_max": 28000000, "req_skills": ["customer support", "call center", "problem solving", "crm"], "pref_skills": ["leadership"], "knockout": ["customer support"], "desc": "Giám sát đội ngũ CSKH đa kênh, nâng cao chỉ số hài lòng khách hàng CSAT/NPS.", "reqs": "- 2.5 năm làm CSKH, 1 năm làm Team Lead.", "benefits": "- Lương 18 - 28M."}
    ],
    "real_estate": [
        {"title": "Chuyên viên Tư vấn Đầu tư Bất động sản Nghỉ dưỡng & Cao cấp", "level": "Middle", "yoe": 2.0, "sal_min": 15000000, "sal_max": 30000000, "req_skills": ["real estate sales", "investment advisory", "negotiation"], "pref_skills": ["high net worth"], "knockout": ["real estate sales"], "desc": "Tư vấn danh mục đầu tư bất động sản phân khúc cao cấp cho khách hàng VIP.", "reqs": "- 2 năm kinh nghiệm BĐS.", "benefits": "- Lương cứng 15 - 30M + Hoa hồng khủng."}
    ]
}

async def seed_all_jobs():
    await connect_to_mongo()
    db = db_instance.db
    now = datetime.now(timezone.utc)

    # 1. Clean old jobs
    await db[Collections.JOBS].delete_many({})
    print("🧹 Đã làm sạch collection jobs cũ.")

    # 2. Load verified companies
    verified_comps = await db[Collections.COMPANIES].find(
        {"status": CompanyStatus.VERIFIED.value}
    ).to_list(200)

    print(f"🏢 Tìm thấy {len(verified_comps)} công ty đã Verified.")

    # Load plans
    plans = await db[Collections.SUBSCRIPTION_PLANS].find({}).to_list(20)
    plan_map = {str(p["_id"]): p.get("plan_code", "") for p in plans}

    # Load 5 benchmark jobs from json
    case_study_file = os.path.join(DATA_DIR, "benchmark_case_study.json")
    with open(case_study_file, "r", encoding="utf-8") as f:
        case_study_data = json.load(f)
    benchmark_jobs = case_study_data["benchmark_jobs"]

    tax_to_comp = {c.get("tax_code"): c for c in verified_comps}
    comp_slug_map = {
        "0100756812-001": "fpt",
        "0303456789-001": "vng",
        "0100109106-001": "viettel",
        "0100684378-001": "vnpt",
        "0305041490-001": "momo"
    }

    job_key_to_id = {}
    total_created = 0
    created_open = 0
    created_closed = 0

    # 3. Seed 5 Primary Benchmark Jobs
    print("\n--- 1. Tạo 5 Benchmark Jobs chính (FPT, VNG, Viettel, VNPT, Momo) ---")
    for bj in benchmark_jobs:
        comp = tax_to_comp.get(bj["company_tax"])
        if not comp:
            continue

        comp_id_str = str(comp["_id"])
        hr_creator_id = comp.get("owner_user_id")

        req_skills_formatted = [
            {"skill_id": None, "name": s, "weight": 0.8, "min_years": 1.5, "is_knockout": (s in bj.get("knockout_skills", []))}
            for s in bj["required_skills"]
        ]
        pref_skills_formatted = [
            {"skill_id": None, "name": s, "weight": 0.5, "min_years": 1.0, "is_knockout": False}
            for s in bj.get("preferred_skills", [])
        ]

        loc_detail = {
            "province_code": bj["location"]["province_code"],
            "province_name": bj["location"]["province_name"],
            "district_name": bj["location"].get("district_name", "Quận trung tâm"),
            "address_detail": bj["location"]["address_detail"]
        }

        job_doc = {
            "title": bj["title"],
            "company_id": comp_id_str,
            "company_name": bj["company_name"],
            "is_hot": True,
            "industry": bj["industry"],
            "job_level": bj["job_level"],
            "employment_type": bj["employment_type"],
            "work_mode": bj["work_mode"],
            "headcount": bj["headcount"],
            "deadline": (now + timedelta(days=30)).isoformat(),
            "probation_period": "2 tháng",
            "gender_requirement": "Không yêu cầu",
            "languages": [{"name": l, "is_knockout": False} for l in bj.get("languages", ["English"])],
            "required_skills": req_skills_formatted,
            "preferred_skills": pref_skills_formatted,
            "min_yoe": bj["min_yoe"],
            "education": bj["education"],
            "score_weights": bj["score_weights"],
            "required_certifications": [{"name": c, "is_knockout": False} for c in bj.get("certifications", [])],
            "salary": bj["salary"],
            "working_hours": "08:30 - 17:30, Thứ 2 - Thứ 6",
            "location": loc_detail,
            "description": bj["description"],
            "requirements": bj["requirements"],
            "benefits": bj["benefits"],
            "other_info": "Chào mừng các kỹ sư tài năng gia nhập cùng chúng tôi.",
            "status": JobStatus.OPEN.value,
            "created_by_user_id": hr_creator_id,
            "assigned_hr_ids": [hr_creator_id],
            "created_at": now - timedelta(days=10),
            "updated_at": now,
            "view_count": 320,
            "save_count": 45,
            "num_applications": 10,
            "jd_search_text": f"{bj['description']} {bj['requirements']} {bj['benefits']}".lower()
        }

        compressed = compress_jd_data(job_doc)
        job_doc["jd_vector_ref"] = generate_deterministic_embedding(compressed)

        res = await db[Collections.JOBS].insert_one(job_doc)
        new_job_id = str(res.inserted_id)
        job_key_to_id[bj["job_key"]] = new_job_id
        total_created += 1
        created_open += 1
        print(f"  + Benchmark Job: {bj['title'][:45]}... (ID: {new_job_id})")

    # Save benchmark mapping
    mapping_file = os.path.join(DATA_DIR, "benchmark_job_ids_mapping.json")
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(job_key_to_id, f, ensure_ascii=False, indent=2)
    print(f"✅ Đã lưu benchmark_job_ids_mapping.json")

    # 4. Seed Extra Jobs for Benchmark Companies
    print("\n--- 2. Tạo Extra Jobs cho 5 Công ty Benchmark (OPEN & CLOSED) ---")
    for tax, slug in comp_slug_map.items():
        comp = tax_to_comp.get(tax)
        if not comp:
            continue
        comp_id_str = str(comp["_id"])
        hr_creator_id = comp.get("owner_user_id")

        for item in BENCHMARK_EXTRA_JOBS.get(slug, []):
            days_offset = item.get("days_offset", 30)
            deadline_dt = now + timedelta(days=days_offset)
            status_val = item.get("status", JobStatus.OPEN.value)

            req_skills_formatted = [
                {"skill_id": None, "name": s, "weight": 0.8, "min_years": 1.5, "is_knockout": (s in item.get("knockout", []))}
                for s in item["req_skills"]
            ]
            pref_skills_formatted = [
                {"skill_id": None, "name": s, "weight": 0.5, "min_years": 1.0, "is_knockout": False}
                for s in item.get("pref_skills", [])
            ]

            loc_detail = {
                "province_code": comp.get("location", {}).get("province_code", "01"),
                "province_name": comp.get("location", {}).get("province_name", "Hà Nội"),
                "district_name": comp.get("location", {}).get("district_name", "Quận Ba Đình"),
                "address_detail": comp.get("location", {}).get("address_detail", "Văn phòng chi nhánh")
            }

            job_doc = {
                "title": item["title"],
                "company_id": comp_id_str,
                "company_name": comp.get("name"),
                "is_hot": False,
                "industry": "it",
                "job_level": item["level"],
                "employment_type": "Full-time",
                "work_mode": "Office",
                "headcount": 2,
                "deadline": deadline_dt.isoformat(),
                "probation_period": "2 tháng",
                "gender_requirement": "Không yêu cầu",
                "languages": [{"name": "English", "is_knockout": False}],
                "required_skills": req_skills_formatted,
                "preferred_skills": pref_skills_formatted,
                "min_yoe": item["yoe"],
                "education": {"min_level": "Đại học", "preferred_majors": []},
                "score_weights": {"skills_weight": 0.40, "nlp_weight": 0.20, "experience_weight": 0.30, "education_weight": 0.10},
                "required_certifications": [],
                "salary": {"min_salary": item["sal_min"], "max_salary": item["sal_max"], "currency": "VND"},
                "working_hours": "08:00 - 17:30, Thứ 2 - Thứ 6",
                "location": loc_detail,
                "description": item["desc"],
                "requirements": item["reqs"],
                "benefits": item["benefits"],
                "other_info": "Chào mừng ứng viên ứng tuyển vào môi trường chuyên nghiệp của chúng tôi.",
                "status": status_val,
                "created_by_user_id": hr_creator_id,
                "assigned_hr_ids": [hr_creator_id],
                "created_at": now - timedelta(days=abs(days_offset) + 5 if days_offset < 0 else 5),
                "updated_at": now,
                "view_count": 120 + total_created * 2,
                "save_count": 15,
                "num_applications": 0,
                "jd_search_text": f"{item['desc']} {item['reqs']} {item['benefits']}".lower()
            }

            compressed = compress_jd_data(job_doc)
            job_doc["jd_vector_ref"] = generate_deterministic_embedding(compressed)

            await db[Collections.JOBS].insert_one(job_doc)
            total_created += 1
            if status_val == JobStatus.OPEN.value:
                created_open += 1
            else:
                created_closed += 1

    # 5. Seed Multi-tier Jobs for all other verified companies
    print("\n--- 3. Tạo Jobs đa tầng cho tất cả doanh nghiệp Verified còn lại ---")
    other_comps = [c for c in verified_comps if c.get("tax_code") not in comp_slug_map]

    for comp_idx, comp in enumerate(other_comps):
        comp_id_str = str(comp["_id"])
        hr_creator_id = comp.get("owner_user_id")
        plan_code = plan_map.get(str(comp.get("current_plan_id")), "comp_free")
        primary_ind = comp.get("industries", ["it"])[0]

        # Target job counts by subscription tier
        if "enterprise" in plan_code:
            target_jobs = 4 if comp_idx % 2 == 0 else 5
        elif "pro" in plan_code:
            target_jobs = 3 if comp_idx % 2 == 0 else 4
        else:
            target_jobs = 2

        templates = INDUSTRY_TEMPLATES.get(primary_ind, INDUSTRY_TEMPLATES["it"])

        for j_idx in range(target_jobs):
            tpl = templates[j_idx % len(templates)]
            # Mix open & closed: 1 closed job for every 3-4 jobs
            if j_idx > 0 and (comp_idx + j_idx) % 3 == 0:
                status_val = JobStatus.CLOSED.value
                days_offset = - (15 + (comp_idx % 20))
            else:
                status_val = JobStatus.OPEN.value
                days_offset = 20 + (comp_idx % 25)

            deadline_dt = now + timedelta(days=days_offset)

            req_skills_formatted = [
                {"skill_id": None, "name": s, "weight": 0.8, "min_years": 1.5, "is_knockout": (s in tpl.get("knockout", []))}
                for s in tpl["req_skills"]
            ]
            pref_skills_formatted = [
                {"skill_id": None, "name": s, "weight": 0.5, "min_years": 1.0, "is_knockout": False}
                for s in tpl.get("pref_skills", [])
            ]

            loc_detail = {
                "province_code": comp.get("location", {}).get("province_code", "01"),
                "province_name": comp.get("location", {}).get("province_name", "Hà Nội"),
                "district_name": comp.get("location", {}).get("district_name", "Quận Ba Đình"),
                "address_detail": comp.get("location", {}).get("address_detail", "Văn phòng chi nhánh")
            }

            job_doc = {
                "title": tpl["title"] if j_idx == 0 else f"{tpl['title']} #{j_idx + 1}",
                "company_id": comp_id_str,
                "company_name": comp.get("name"),
                "is_hot": False,
                "industry": primary_ind,
                "job_level": tpl["level"],
                "employment_type": "Full-time",
                "work_mode": "Office",
                "headcount": 2,
                "deadline": deadline_dt.isoformat(),
                "probation_period": "2 tháng",
                "gender_requirement": "Không yêu cầu",
                "languages": [{"name": "English", "is_knockout": False}],
                "required_skills": req_skills_formatted,
                "preferred_skills": pref_skills_formatted,
                "min_yoe": tpl["yoe"],
                "education": {"min_level": "Đại học", "preferred_majors": []},
                "score_weights": {"skills_weight": 0.40, "nlp_weight": 0.20, "experience_weight": 0.30, "education_weight": 0.10},
                "required_certifications": [],
                "salary": {"min_salary": tpl["sal_min"], "max_salary": tpl["sal_max"], "currency": "VND"},
                "working_hours": "08:00 - 17:30, Thứ 2 - Thứ 6",
                "location": loc_detail,
                "description": tpl["desc"],
                "requirements": tpl["reqs"],
                "benefits": tpl["benefits"],
                "other_info": "Chào mừng ứng viên ứng tuyển vào môi trường chuyên nghiệp của chúng tôi.",
                "status": status_val,
                "created_by_user_id": hr_creator_id,
                "assigned_hr_ids": [hr_creator_id],
                "created_at": now - timedelta(days=abs(days_offset) + 5 if days_offset < 0 else 3),
                "updated_at": now,
                "view_count": 80 + total_created * 2,
                "save_count": 10 + total_created % 4,
                "num_applications": 0,
                "jd_search_text": f"{tpl['desc']} {tpl['reqs']} {tpl['benefits']}".lower()
            }

            compressed = compress_jd_data(job_doc)
            job_doc["jd_vector_ref"] = generate_deterministic_embedding(compressed)

            await db[Collections.JOBS].insert_one(job_doc)
            total_created += 1
            if status_val == JobStatus.OPEN.value:
                created_open += 1
            else:
                created_closed += 1

    print("\n" + "=" * 65)
    print(f"✅ HOÀN TẤT SEED TOÀN BỘ JOBS:")
    print(f" - Tổng số Jobs đã tạo: {total_created}")
    print(f" - Số Jobs Đang Mở (OPEN): {created_open}")
    print(f" - Số Jobs Đã Hết Hạn (CLOSED): {created_closed}")
    print("=" * 65)

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_all_jobs())
