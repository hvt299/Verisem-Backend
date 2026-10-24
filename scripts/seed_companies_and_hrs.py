import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta
from bson import ObjectId

# Ensure backend root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Set UTF-8
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

from app.core.security import get_password_hash
from app.database.config import connect_to_mongo, close_mongo_connection, db_instance, Collections
from app.schemas.common_schema import UserRole, CompanyStatus

SIZE_MAPPING = {
    "1000+ nhân sự": "1000+",
    "1000+": "1000+",
    "501-1000 nhân sự": "201-1000",
    "201-500 nhân sự": "201-1000",
    "201-1000": "201-1000",
    "100-200 nhân sự": "51-200",
    "51-100 nhân sự": "51-200",
    "51-200": "51-200",
    "1-50 nhân sự": "1-50",
    "1-50": "1-50"
}

# 25 Industries x 5 Companies = 125 Companies Definition
COMPANIES_DATA = [
    # 1. it (Công nghệ Thông tin)
    {"code": "it", "name": "Công ty TNHH Phần mềm FPT (FPT Software)", "tax": "0100756812-001", "size": "1000+ nhân sự", "slug": "fpt", "web": "https://fpt-software.com", "loc": ("01", "Hà Nội")},
    {"code": "it", "name": "Công ty Cổ phần VNG (VNG Corporation)", "tax": "0303456789-001", "size": "1000+ nhân sự", "slug": "vng", "web": "https://vng.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "it", "name": "Tổng Công ty Giải pháp Doanh nghiệp Viettel (Viettel Solutions)", "tax": "0100109106-001", "size": "1000+ nhân sự", "slug": "viettel", "web": "https://solutions.viettel.vn", "loc": ("01", "Hà Nội")},
    {"code": "it", "name": "Công ty TNHH NashTech Việt Nam", "tax": "0302001111-001", "size": "1000+ nhân sự", "slug": "nashtech", "web": "https://nashtechglobal.com", "loc": ("79", "Hồ Chí Minh")},
    {"code": "it", "name": "Công ty Cổ phần Giải pháp Thanh toán Việt Nam (VNPAY)", "tax": "0102182292-001", "size": "1000+ nhân sự", "slug": "vnpay", "web": "https://vnpay.vn", "loc": ("01", "Hà Nội")},

    # 2. sales (Kinh doanh/Bán hàng)
    {"code": "sales", "name": "Công ty Cổ phần Hàng tiêu dùng Masan (Masan Consumer)", "tax": "0302017440-001", "size": "1000+ nhân sự", "slug": "masan", "web": "https://masanconsumer.com", "loc": ("79", "Hồ Chí Minh")},
    {"code": "sales", "name": "Công ty TNHH Quốc tế Unilever Việt Nam", "tax": "0300800100-001", "size": "1000+ nhân sự", "slug": "unilever", "web": "https://unilever.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "sales", "name": "Công ty TNHH Nestlé Việt Nam", "tax": "3600235305-001", "size": "1000+ nhân sự", "slug": "nestle", "web": "https://nestle.com.vn", "loc": ("75", "Đồng Nai")},
    {"code": "sales", "name": "Công ty TNHH Procter & Gamble Việt Nam (P&G)", "tax": "3700234123-001", "size": "1000+ nhân sự", "slug": "pg", "web": "https://pg.com", "loc": ("74", "Bình Dương")},
    {"code": "sales", "name": "Tập đoàn Sunhouse Việt Nam", "tax": "0101567890-001", "size": "501-1000 nhân sự", "slug": "sunhouse", "web": "https://sunhouse.com.vn", "loc": ("01", "Hà Nội")},

    # 3. marketing (Marketing/PR/Quảng cáo)
    {"code": "marketing", "name": "Công ty TNHH Dentsu Việt Nam", "tax": "0300800555-001", "size": "501-1000 nhân sự", "slug": "dentsu", "web": "https://dentsu.com", "loc": ("79", "Hồ Chí Minh")},
    {"code": "marketing", "name": "Công ty TNHH Ogilvy & Mather Việt Nam", "tax": "0301432123-001", "size": "201-500 nhân sự", "slug": "ogilvy", "web": "https://ogilvy.com", "loc": ("79", "Hồ Chí Minh")},
    {"code": "marketing", "name": "Công ty TNHH Hakuhodo Việt Nam", "tax": "0302567891-001", "size": "201-500 nhân sự", "slug": "hakuhodo", "web": "https://hakuhodo.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "marketing", "name": "Công ty Cổ phần VCCorp", "tax": "0101871142-001", "size": "1000+ nhân sự", "slug": "vccorp", "web": "https://vccorp.vn", "loc": ("01", "Hà Nội")},
    {"code": "marketing", "name": "Công ty TNHH Truyền thông T&A Ogilvy", "tax": "0304987654-001", "size": "100-200 nhân sự", "slug": "taogilvy", "web": "https://ta-ogilvy.com", "loc": ("79", "Hồ Chí Minh")},

    # 4. customer_service (Chăm sóc khách hàng/Vận hành)
    {"code": "customer_service", "name": "Công ty Cổ phần Bellsystem24 Việt Nam", "tax": "0101987654-001", "size": "1000+ nhân sự", "slug": "bellsystem24", "web": "https://bell24vn.com", "loc": ("01", "Hà Nội")},
    {"code": "customer_service", "name": "Công ty TNHH Minh Phúc (MP Telecom)", "tax": "0101234567-001", "size": "1000+ nhân sự", "slug": "mptelecom", "web": "https://mptelecom.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "customer_service", "name": "Tập đoàn Hoa Sao (Teleperformance Vietnam)", "tax": "0102345678-001", "size": "1000+ nhân sự", "slug": "hoasao", "web": "https://teleperformance.com", "loc": ("01", "Hà Nội")},
    {"code": "customer_service", "name": "Công ty Cổ phần Base Enterprise (Base.vn)", "tax": "0107567890-001", "size": "201-500 nhân sự", "slug": "basevn", "web": "https://base.vn", "loc": ("01", "Hà Nội")},
    {"code": "customer_service", "name": "Công ty TNHH Concentrix Services Việt Nam", "tax": "0313456789-001", "size": "1000+ nhân sự", "slug": "concentrix", "web": "https://concentrix.com", "loc": ("79", "Hồ Chí Minh")},

    # 5. hr_admin_legal (Nhân sự/Hành chính/Pháp chế)
    {"code": "hr_admin_legal", "name": "Tập đoàn Navigos Group (VietnamWorks)", "tax": "0302876543-001", "size": "501-1000 nhân sự", "slug": "navigos", "web": "https://vietnamworks.com", "loc": ("79", "Hồ Chí Minh")},
    {"code": "hr_admin_legal", "name": "Công ty TNHH Adecco Việt Nam", "tax": "0310987654-001", "size": "201-500 nhân sự", "slug": "adecco", "web": "https://adecco.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "hr_admin_legal", "name": "Công ty TNHH ManpowerGroup Việt Nam", "tax": "0305678901-001", "size": "201-500 nhân sự", "slug": "manpower", "web": "https://manpower.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "hr_admin_legal", "name": "Công ty Cổ phần Kết nối Nhân tài (Talentnet)", "tax": "0304567892-001", "size": "201-500 nhân sự", "slug": "talentnet", "web": "https://talentnet.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "hr_admin_legal", "name": "Công ty TNHH CareerBuilder Việt Nam (CareerViet)", "tax": "0303890123-001", "size": "201-500 nhân sự", "slug": "careerviet", "web": "https://careerviet.vn", "loc": ("79", "Hồ Chí Minh")},

    # 6. labor (Lao động phổ thông)
    {"code": "labor", "name": "Tập đoàn Pouyuen Việt Nam", "tax": "0301456780-001", "size": "1000+ nhân sự", "slug": "pouyuen", "web": "https://pouchen.com", "loc": ("79", "Hồ Chí Minh")},
    {"code": "labor", "name": "Tập đoàn Khoa học Kỹ thuật Hồng Hải (Foxconn VN)", "tax": "2400345678-001", "size": "1000+ nhân sự", "slug": "foxconn", "web": "https://foxconn.com.vn", "loc": ("24", "Bắc Giang")},
    {"code": "labor", "name": "Công ty TNHH Luxshare-ICT Việt Nam", "tax": "2400876543-001", "size": "1000+ nhân sự", "slug": "luxshare", "web": "https://luxshare-ict.com", "loc": ("24", "Bắc Giang")},
    {"code": "labor", "name": "Công ty TNHH Nissei Electric Việt Nam", "tax": "0302345671-001", "size": "1000+ nhân sự", "slug": "nissei", "web": "https://nissei-el.co.jp", "loc": ("79", "Hồ Chí Minh")},
    {"code": "labor", "name": "Tổng Công ty May Nhà Bè (NBC)", "tax": "0300398765-001", "size": "1000+ nhân sự", "slug": "maynhabe", "web": "https://nhabe.com.vn", "loc": ("79", "Hồ Chí Minh")},

    # 7. finance (Tài chính/Ngân hàng/Bảo hiểm)
    {"code": "finance", "name": "Ngân hàng TMCP Ngoại thương Việt Nam (Vietcombank)", "tax": "0100112437-001", "size": "1000+ nhân sự", "slug": "vietcombank", "web": "https://vietcombank.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "finance", "name": "Ngân hàng TMCP Kỹ Thương Việt Nam (Techcombank)", "tax": "0100230800-001", "size": "1000+ nhân sự", "slug": "techcombank", "web": "https://techcombank.com", "loc": ("01", "Hà Nội")},
    {"code": "finance", "name": "Ngân hàng TMCP Quân Đội (MB Bank)", "tax": "0100283873-001", "size": "1000+ nhân sự", "slug": "mbbank", "web": "https://mbbank.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "finance", "name": "Ngân hàng TMCP Việt Nam Thịnh Vượng (VPBank)", "tax": "0100233583-001", "size": "1000+ nhân sự", "slug": "vpbank", "web": "https://vpbank.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "finance", "name": "Tập đoàn Bảo Việt (Bao Viet Holdings)", "tax": "0100111761-001", "size": "1000+ nhân sự", "slug": "baoviet", "web": "https://baoviet.com.vn", "loc": ("01", "Hà Nội")},

    # 8. realestate (Bất động sản)
    {"code": "realestate", "name": "Công ty Cổ phần Vinhomes (Tập đoàn Vingroup)", "tax": "0103023679-001", "size": "1000+ nhân sự", "slug": "vinhomes", "web": "https://vinhomes.vn", "loc": ("01", "Hà Nội")},
    {"code": "realestate", "name": "Công ty Cổ phần Tập đoàn Đất Xanh", "tax": "0303104343-001", "size": "1000+ nhân sự", "slug": "datxanh", "web": "https://datxanh.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "realestate", "name": "Tập đoàn Đầu tư Địa ốc No Va (Novaland Group)", "tax": "0301449876-001", "size": "1000+ nhân sự", "slug": "novaland", "web": "https://novaland.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "realestate", "name": "Công ty Cổ phần Đầu tư và Kinh doanh Nhà Khang Điền", "tax": "0304876543-001", "size": "501-1000 nhân sự", "slug": "khangdien", "web": "https://khangdien.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "realestate", "name": "Tập đoàn Hưng Thịnh (Hung Thinh Corp)", "tax": "0305678123-001", "size": "1000+ nhân sự", "slug": "hungthinh", "web": "https://hungthinhcorp.com.vn", "loc": ("79", "Hồ Chí Minh")},

    # 9. construction (Xây dựng)
    {"code": "construction", "name": "Công ty Cổ phần Xây dựng Coteccons", "tax": "0303443233-001", "size": "1000+ nhân sự", "slug": "coteccons", "web": "https://coteccons.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "construction", "name": "Công ty Cổ phần Tập đoàn Xây dựng Hòa Bình", "tax": "0301987654-001", "size": "1000+ nhân sự", "slug": "hoabinh", "web": "https://hbcg.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "construction", "name": "Công ty Cổ phần Phục Hưng Holdings", "tax": "0101123456-001", "size": "501-1000 nhân sự", "slug": "phuchung", "web": "https://phuchung.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "construction", "name": "Tổng Công ty CP Xuất nhập khẩu và Xây dựng VN (Vinaconex)", "tax": "0100105398-001", "size": "1000+ nhân sự", "slug": "vinaconex", "web": "https://vinaconex.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "construction", "name": "Công ty Cổ phần Đầu tư Xây dựng Newtecons", "tax": "0303123456-001", "size": "501-1000 nhân sự", "slug": "newtecons", "web": "https://newtecons.vn", "loc": ("79", "Hồ Chí Minh")},

    # 10. accounting (Kế toán/Kiểm toán/Thuế)
    {"code": "accounting", "name": "Công ty TNHH PwC Việt Nam (PricewaterhouseCoopers)", "tax": "0300456789-001", "size": "501-1000 nhân sự", "slug": "pwc", "web": "https://pwc.com/vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "accounting", "name": "Công ty TNHH Deloitte Việt Nam", "tax": "0100112345-001", "size": "501-1000 nhân sự", "slug": "deloitte", "web": "https://deloitte.com/vn", "loc": ("01", "Hà Nội")},
    {"code": "accounting", "name": "Công ty TNHH Ernst & Young Việt Nam (EY)", "tax": "0300890123-001", "size": "501-1000 nhân sự", "slug": "ey", "web": "https://ey.com/vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "accounting", "name": "Công ty TNHH KPMG Việt Nam", "tax": "0301234567-001", "size": "501-1000 nhân sự", "slug": "kpmg", "web": "https://kpmg.com/vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "accounting", "name": "Công ty TNHH Grant Thornton Việt Nam", "tax": "0100234567-001", "size": "201-500 nhân sự", "slug": "grantthornton", "web": "https://grantthornton.com.vn", "loc": ("01", "Hà Nội")},

    # 11. manufacturing (Sản xuất)
    {"code": "manufacturing", "name": "Công ty TNHH Sản xuất và Kinh doanh VinFast", "tax": "0201801234-001", "size": "1000+ nhân sự", "slug": "vinfast", "web": "https://vinfastauto.com", "loc": ("31", "Hải Phòng")},
    {"code": "manufacturing", "name": "Công ty Cổ phần Tập đoàn Trường Hải (THACO)", "tax": "4000345678-001", "size": "1000+ nhân sự", "slug": "thaco", "web": "https://thacogroup.vn", "loc": ("49", "Quảng Nam")},
    {"code": "manufacturing", "name": "Công ty Cổ phần Sữa Việt Nam (Vinamilk)", "tax": "0300588569-001", "size": "1000+ nhân sự", "slug": "vinamilk", "web": "https://vinamilk.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "manufacturing", "name": "Công ty Cổ phần Tập đoàn Hòa Phát", "tax": "0900189284-001", "size": "1000+ nhân sự", "slug": "hoaphat", "web": "https://hoaphat.com.vn", "loc": ("33", "Hưng Yên")},
    {"code": "manufacturing", "name": "Công ty TNHH Samsung Electronics Việt Nam (SEV)", "tax": "2300345678-001", "size": "1000+ nhân sự", "slug": "samsung", "web": "https://samsung.com/vn", "loc": ("27", "Bắc Ninh")},

    # 12. education (Giáo dục/Đào tạo)
    {"code": "education", "name": "Công ty Cổ phần Giáo dục YOLA", "tax": "0309819876-001", "size": "501-1000 nhân sự", "slug": "yola", "web": "https://yola.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "education", "name": "Tổ hợp Công nghệ Giáo dục TOPICA (Topica Edtech)", "tax": "0102876543-001", "size": "501-1000 nhân sự", "slug": "topica", "web": "https://topica.edu.vn", "loc": ("01", "Hà Nội")},
    {"code": "education", "name": "Hệ thống Anh văn Hội Việt Mỹ (VUS)", "tax": "0302345678-001", "size": "1000+ nhân sự", "slug": "vus", "web": "https://vus.edu.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "education", "name": "Tập đoàn Giáo dục Nguyễn Hoàng (NHG)", "tax": "0304567890-001", "size": "1000+ nhân sự", "slug": "nguyenhoang", "web": "https://nhg.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "education", "name": "Công ty TNHH Một thành viên Giáo dục Vinschool", "tax": "0106123456-001", "size": "1000+ nhân sự", "slug": "vinschool", "web": "https://vinschool.edu.vn", "loc": ("01", "Hà Nội")},

    # 13. retail_lifestyle (Bán lẻ/Dịch vụ đời sống)
    {"code": "retail_lifestyle", "name": "Công ty Cổ phần Vàng Bạc Đá Quý Phú Nhuận (PNJ)", "tax": "0300521758-001", "size": "1000+ nhân sự", "slug": "pnj", "web": "https://pnj.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "retail_lifestyle", "name": "Công ty Cổ phần Đầu tư Thế Giới Di Động (MWG)", "tax": "0303217354-001", "size": "1000+ nhân sự", "slug": "mwg", "web": "https://mwg.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "retail_lifestyle", "name": "Công ty Cổ phần Dịch vụ Thương mại Tổng hợp WinCommerce", "tax": "0104918404-001", "size": "1000+ nhân sự", "slug": "wincommerce", "web": "https://winmart.vn", "loc": ("01", "Hà Nội")},
    {"code": "retail_lifestyle", "name": "Công ty Cổ phần Bán lẻ Kỹ thuật số FPT (FPT Retail)", "tax": "0311527384-001", "size": "1000+ nhân sự", "slug": "fptretail", "web": "https://fptshop.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "retail_lifestyle", "name": "Tập đoàn Central Retail Việt Nam (GO! / Big C)", "tax": "0312345670-001", "size": "1000+ nhân sự", "slug": "centralretail", "web": "https://centralretail.com.vn", "loc": ("79", "Hồ Chí Minh")},

    # 14. media_publishing (Phim/Truyền hình/Báo chí/Xuất bản)
    {"code": "media_publishing", "name": "Công ty TNHH CJ CGV Việt Nam", "tax": "0303675432-001", "size": "1000+ nhân sự", "slug": "cgv", "web": "https://cgv.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "media_publishing", "name": "Công ty Cổ phần Phim Thiên Ngân (Galaxy Cinema)", "tax": "0303124567-001", "size": "501-1000 nhân sự", "slug": "galaxy", "web": "https://galaxycine.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "media_publishing", "name": "Trung tâm Sản xuất Phim truyền hình - Đài Truyền hình VN (VFC)", "tax": "0101234599-001", "size": "501-1000 nhân sự", "slug": "vtv", "web": "https://vtv.vn", "loc": ("01", "Hà Nội")},
    {"code": "media_publishing", "name": "Công ty Cổ phần Dịch vụ Trực tuyến FPT (FPT Online - VnExpress)", "tax": "0305045911-001", "size": "501-1000 nhân sự", "slug": "vnexpress", "web": "https://vnexpress.net", "loc": ("79", "Hồ Chí Minh")},
    {"code": "media_publishing", "name": "Nhà xuất bản Kim Đồng", "tax": "0100115678-001", "size": "201-500 nhân sự", "slug": "nxbkimdong", "web": "https://nxbkimdong.com.vn", "loc": ("01", "Hà Nội")},

    # 15. electronics_telecom (Điện/Điện tử/Viễn thông)
    {"code": "electronics_telecom", "name": "Tập đoàn Bưu chính Viễn thông Việt Nam (VNPT)", "tax": "0100684378-001", "size": "1000+ nhân sự", "slug": "vnpt", "web": "https://vnpt.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "electronics_telecom", "name": "Tổng Công ty Viễn thông MobiFone", "tax": "0100686209-001", "size": "1000+ nhân sự", "slug": "mobifone", "web": "https://mobifone.vn", "loc": ("01", "Hà Nội")},
    {"code": "electronics_telecom", "name": "Công ty Cổ phần Viễn thông FPT (FPT Telecom)", "tax": "0101778163-001", "size": "1000+ nhân sự", "slug": "fpttelecom", "web": "https://fpt.vn", "loc": ("01", "Hà Nội")},
    {"code": "electronics_telecom", "name": "Công ty TNHH LG Electronics Việt Nam", "tax": "0200234567-001", "size": "1000+ nhân sự", "slug": "lgelectronics", "web": "https://lg.com/vn", "loc": ("31", "Hải Phòng")},
    {"code": "electronics_telecom", "name": "Công ty TNHH Panasonic Việt Nam", "tax": "0101345678-001", "size": "1000+ nhân sự", "slug": "panasonic", "web": "https://panasonic.com/vn", "loc": ("01", "Hà Nội")},

    # 16. logistics (Logistics/Thu mua/Kho/Vận tải)
    {"code": "logistics", "name": "Tổng Công ty Cổ phần Bưu chính Viettel (Viettel Post)", "tax": "0104093672-001", "size": "1000+ nhân sự", "slug": "viettelpost", "web": "https://viettelpost.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "logistics", "name": "Công ty Cổ phần Dịch vụ Giao Hàng Nhanh (GHN Express)", "tax": "0311907295-001", "size": "1000+ nhân sự", "slug": "ghn", "web": "https://ghn.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "logistics", "name": "Công ty Cổ phần Gemadept (Gemadept Logistics)", "tax": "0301156789-001", "size": "1000+ nhân sự", "slug": "gemadept", "web": "https://gemadept.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "logistics", "name": "Tổng Công ty Tân Cảng Sài Gòn (Saigon Newport Corporation)", "tax": "0300634567-001", "size": "1000+ nhân sự", "slug": "tancang", "web": "https://saigonnewport.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "logistics", "name": "Công ty TNHH Chuyển Phát Nhanh DHL-VNPT (DHL Express VN)", "tax": "0304567123-001", "size": "501-1000 nhân sự", "slug": "dhl", "web": "https://dhl.com/vn", "loc": ("79", "Hồ Chí Minh")},

    # 17. consulting (Tư vấn chuyên môn)
    {"code": "consulting", "name": "Công ty TNHH McKinsey & Company Việt Nam", "tax": "0309123456-001", "size": "100-200 nhân sự", "slug": "mckinsey", "web": "https://mckinsey.com/vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "consulting", "name": "Boston Consulting Group Việt Nam (BCG)", "tax": "0311234567-001", "size": "100-200 nhân sự", "slug": "bcg", "web": "https://bcg.com", "loc": ("79", "Hồ Chí Minh")},
    {"code": "consulting", "name": "Công ty TNHH Bain & Company Việt Nam", "tax": "0317890123-001", "size": "51-100 nhân sự", "slug": "bain", "web": "https://bain.com", "loc": ("79", "Hồ Chí Minh")},
    {"code": "consulting", "name": "Công ty TNHH NielsenIQ Việt Nam", "tax": "0302345987-001", "size": "201-500 nhân sự", "slug": "nielsen", "web": "https://nielseniq.com", "loc": ("79", "Hồ Chí Minh")},
    {"code": "consulting", "name": "Công ty TNHH Mercer Việt Nam (Mercer Talent Consulting)", "tax": "0312456781-001", "size": "51-100 nhân sự", "slug": "mercer", "web": "https://mercer.com", "loc": ("79", "Hồ Chí Minh")},

    # 18. healthcare (Dược/Y tế/Sức khoẻ/Công nghệ sinh học)
    {"code": "healthcare", "name": "Công ty Cổ phần Dược Hậu Giang (DHG Pharma)", "tax": "1800156801-001", "size": "1000+ nhân sự", "slug": "dhgpharma", "web": "https://dhgpharma.com.vn", "loc": ("92", "Cần Thơ")},
    {"code": "healthcare", "name": "Công ty Cổ phần Traphaco", "tax": "0100108656-001", "size": "1000+ nhân sự", "slug": "traphaco", "web": "https://traphaco.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "healthcare", "name": "Công ty Cổ phần Bệnh viện Đa khoa Tâm Anh", "tax": "0107890123-001", "size": "1000+ nhân sự", "slug": "tamanh", "web": "https://tamanhhospital.vn", "loc": ("01", "Hà Nội")},
    {"code": "healthcare", "name": "Công ty Cổ phần Bệnh viện Đa khoa Quốc tế Vinmec", "tax": "0105890123-001", "size": "1000+ nhân sự", "slug": "vinmec", "web": "https://vinmec.com", "loc": ("01", "Hà Nội")},
    {"code": "healthcare", "name": "Công ty Cổ phần Dược phẩm Pharmacity", "tax": "0311781234-001", "size": "1000+ nhân sự", "slug": "pharmacity", "web": "https://pharmacity.vn", "loc": ("79", "Hồ Chí Minh")},

    # 19. design (Thiết kế)
    {"code": "design", "name": "Sun Life Creative & Brand Studio", "tax": "0312456799-001", "size": "100-200 nhân sự", "slug": "sunlifecreative", "web": "https://sunlife.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "design", "name": "Dentsu Creative Vietnam", "tax": "0315678912-001", "size": "100-200 nhân sự", "slug": "dentsucreative", "web": "https://dentsucreative.com", "loc": ("79", "Hồ Chí Minh")},
    {"code": "design", "name": "Công ty Cổ phần Thiết kế & Truyền thông RIO Creative", "tax": "0106789012-001", "size": "51-100 nhân sự", "slug": "riocreative", "web": "https://rio.vn", "loc": ("01", "Hà Nội")},
    {"code": "design", "name": "Curnon Creative & Product Design", "tax": "0107890456-001", "size": "51-100 nhân sự", "slug": "curnon", "web": "https://curnonwatch.com", "loc": ("01", "Hà Nội")},
    {"code": "design", "name": "Ogilvy One Worldwide Vietnam", "tax": "0308901234-001", "size": "100-200 nhân sự", "slug": "ogilvyone", "web": "https://ogilvy.com", "loc": ("79", "Hồ Chí Minh")},

    # 20. hospitality (Nhà hàng/Khách sạn/Du lịch)
    {"code": "hospitality", "name": "Tổng Công ty Du lịch Sài Gòn (Saigontourist Group)", "tax": "0300625203-001", "size": "1000+ nhân sự", "slug": "saigontourist", "web": "https://saigontourist.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "hospitality", "name": "Công ty Cổ phần Thương mại Dịch vụ Cổng Vàng (Golden Gate Group)", "tax": "0102721191-001", "size": "1000+ nhân sự", "slug": "goldengate", "web": "https://ggg.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "hospitality", "name": "Công ty Cổ phần Đầu tư Thương mại Quốc tế Mặt Trời Đỏ (Redsun ITI)", "tax": "0102634567-001", "size": "1000+ nhân sự", "slug": "redsun", "web": "https://redsun-iti.vn", "loc": ("01", "Hà Nội")},
    {"code": "hospitality", "name": "Công ty Cổ phần Vinpearl", "tax": "4200456789-001", "size": "1000+ nhân sự", "slug": "vinpearl", "web": "https://vinpearl.com", "loc": ("56", "Khánh Hòa")},
    {"code": "hospitality", "name": "Tập đoàn Khách sạn & Nghỉ dưỡng Sun Hospitality (Sun Group)", "tax": "0400890123-001", "size": "1000+ nhân sự", "slug": "sunhospitality", "web": "https://sungroup.com.vn", "loc": ("48", "Đà Nẵng")},

    # 21. energy_agriculture (Năng lượng/Môi trường/Nông nghiệp)
    {"code": "energy_agriculture", "name": "Tập đoàn Điện lực Việt Nam (EVN)", "tax": "0100100079-001", "size": "1000+ nhân sự", "slug": "evn", "web": "https://evn.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "energy_agriculture", "name": "Tập đoàn Dầu khí Quốc gia Việt Nam (Petrovietnam - PVN)", "tax": "0100150619-001", "size": "1000+ nhân sự", "slug": "petrovietnam", "web": "https://pvn.vn", "loc": ("01", "Hà Nội")},
    {"code": "energy_agriculture", "name": "Công ty Cổ phần Chăn nuôi C.P. Việt Nam", "tax": "3600224423-001", "size": "1000+ nhân sự", "slug": "cpvietnam", "web": "https://cp.com.vn", "loc": ("75", "Đồng Nai")},
    {"code": "energy_agriculture", "name": "Công ty Cổ phần Tập đoàn Lộc Trời", "tax": "1600192345-001", "size": "1000+ nhân sự", "slug": "loctroi", "web": "https://loctroi.vn", "loc": ("89", "An Giang")},
    {"code": "energy_agriculture", "name": "Công ty Cổ phần Tập đoàn Giống cây trồng Việt Nam (Vinaseed)", "tax": "0100106789-001", "size": "501-1000 nhân sự", "slug": "vinaseed", "web": "https://vinaseed.com.vn", "loc": ("01", "Hà Nội")},

    # 22. driver (Tài xế/Vận tải hành khách)
    {"code": "driver", "name": "Công ty TNHH Grab Việt Nam", "tax": "0312650437-001", "size": "1000+ nhân sự", "slug": "grab", "web": "https://grab.com/vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "driver", "name": "Công ty Cổ phần Be Group", "tax": "0108256789-001", "size": "1000+ nhân sự", "slug": "begroup", "web": "https://be.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "driver", "name": "Công ty Cổ phần Tập đoàn Mai Linh", "tax": "0302345670-001", "size": "1000+ nhân sự", "slug": "mailinh", "web": "https://mailinh.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "driver", "name": "Công ty Cổ phần Di chuyển Xanh và Thông minh (GSM - Xanh SM)", "tax": "0110278901-001", "size": "1000+ nhân sự", "slug": "xanhsm", "web": "https://xanhsm.com", "loc": ("01", "Hà Nội")},
    {"code": "driver", "name": "Công ty Cổ phần Ánh Dương Việt Nam (Vinasun Taxi)", "tax": "0302035531-001", "size": "1000+ nhân sự", "slug": "vinasun", "web": "https://vinasuntaxi.com", "loc": ("79", "Hồ Chí Minh")},

    # 23. translation (Biên phiên dịch)
    {"code": "translation", "name": "Công ty Cổ phần Dịch thuật Dịch Số", "tax": "0106234567-001", "size": "51-100 nhân sự", "slug": "dichso", "web": "https://dichso.com", "loc": ("01", "Hà Nội")},
    {"code": "translation", "name": "Công ty TNHH Dịch thuật Expertrans BPO", "tax": "0102890123-001", "size": "100-200 nhân sự", "slug": "expertrans", "web": "https://expertrans.com", "loc": ("01", "Hà Nội")},
    {"code": "translation", "name": "Công ty TNHH Dịch thuật Việt Uy Tín", "tax": "0312567890-001", "size": "100-200 nhân sự", "slug": "vietuytin", "web": "https://vietuytin.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "translation", "name": "Công ty TNHH Dịch thuật Tomato Media", "tax": "0107890124-001", "size": "100-200 nhân sự", "slug": "tomatomedia", "web": "https://tomatotranslation.com", "loc": ("01", "Hà Nội")},
    {"code": "translation", "name": "Công ty Dịch thuật và Phiên dịch Á Châu", "tax": "0105678901-001", "size": "51-100 nhân sự", "slug": "dichthuatachau", "web": "https://dichthuatachau.com", "loc": ("01", "Hà Nội")},

    # 24. law (Luật/Pháp lý)
    {"code": "law", "name": "Công ty Luật TNHH YKVN", "tax": "0101890123-001", "size": "100-200 nhân sự", "slug": "ykvn", "web": "https://ykvn-law.com", "loc": ("01", "Hà Nội")},
    {"code": "law", "name": "Công ty Luật Hợp danh VILAF (Vietnam International Law Firm)", "tax": "0301456781-001", "size": "100-200 nhân sự", "slug": "vilaf", "web": "https://vilaf.com.vn", "loc": ("79", "Hồ Chí Minh")},
    {"code": "law", "name": "Công ty Luật Baker & McKenzie Việt Nam", "tax": "0300678901-001", "size": "100-200 nhân sự", "slug": "bakermckenzie", "web": "https://bakermckenzie.com", "loc": ("79", "Hồ Chí Minh")},
    {"code": "law", "name": "Công ty Luật LNT & Partners", "tax": "0310123456-001", "size": "51-100 nhân sự", "slug": "lntpartners", "web": "https://lntpartners.com", "loc": ("79", "Hồ Chí Minh")},
    {"code": "law", "name": "Công ty Cổ phần LuatVietnam (Luật Việt Nam)", "tax": "0103456789-001", "size": "100-200 nhân sự", "slug": "luatvietnam", "web": "https://luatvietnam.vn", "loc": ("01", "Hà Nội")},

    # 25. other (Nhóm nghề khác)
    {"code": "other", "name": "Liên minh Hợp tác xã Việt Nam (VCA)", "tax": "0100109999-001", "size": "1000+ nhân sự", "slug": "vca", "web": "https://vca.org.vn", "loc": ("01", "Hà Nội")},
    {"code": "other", "name": "Tập đoàn Dệt May Việt Nam (Vinatex)", "tax": "0100100008-001", "size": "1000+ nhân sự", "slug": "vinatex", "web": "https://vinatex.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "other", "name": "Tổng Công ty Giấy Việt Nam (Vinapaco)", "tax": "2600100123-001", "size": "1000+ nhân sự", "slug": "vinapaco", "web": "https://vinapaco.com.vn", "loc": ("25", "Phú Thọ")},
    {"code": "other", "name": "Tập đoàn Hóa chất Việt Nam (Vinachem)", "tax": "0100100057-001", "size": "1000+ nhân sự", "slug": "vinachem", "web": "https://vinachem.com.vn", "loc": ("01", "Hà Nội")},
    {"code": "other", "name": "Tổng Công ty Hàng hải Việt Nam (VIMC)", "tax": "0100100024-001", "size": "1000+ nhân sự", "slug": "vimc", "web": "https://vimc.co", "loc": ("01", "Hà Nội")}
]

async def seed_companies_and_hr():
    await connect_to_mongo()
    db = db_instance.db
    now = datetime.now(timezone.utc)

    # 1. Fetch Subscription Plans
    plans_by_code = {}
    async for p in db[Collections.SUBSCRIPTION_PLANS].find({"target_audience": "hr"}):
        plans_by_code[p.get("plan_code")] = p

    plan_enterprise = plans_by_code.get("hr_enterprise_yearly")
    plan_pro = plans_by_code.get("hr_pro_monthly")
    plan_growth = plans_by_code.get("hr_growth_monthly")
    plan_free = plans_by_code.get("hr_free")

    print(f"Bắt đầu khởi tạo 125 Doanh nghiệp và 500 Tài khoản HR...")

    # Standard shared password for test HR accounts
    hr_password = "HR@Verisem2026!"
    hashed_hr_password = get_password_hash(hr_password)

    companies_to_insert = []
    users_to_insert = []
    subscriptions_to_insert = []
    credit_grants_to_insert = []

    for index, comp in enumerate(COMPANIES_DATA):
        comp_id = str(ObjectId())
        owner_id = str(ObjectId())
        slug = comp["slug"]
        ind_code = comp["code"]

        # Status distribution:
        # Index 0-79 (80 cty ~64%): verified
        # Index 80-104 (25 cty ~20%): pending_verification
        # Index 105-116 (12 cty ~10%): suspended
        # Index 117-124 (8 cty ~6%): rejected
        if index < 80:
            status = CompanyStatus.VERIFIED.value
            rejection_reason = None
            verified_at = now - timedelta(days=60)
        elif index < 105:
            status = CompanyStatus.PENDING_VERIFICATION.value
            rejection_reason = None
            verified_at = None
        elif index < 117:
            status = CompanyStatus.SUSPENDED.value
            rejection_reason = "Tạm khóa do có nghi vấn khiếu nại thông tin tuyển dụng"
            verified_at = None
        else:
            status = CompanyStatus.REJECTED.value
            rejection_reason = "Giấy tờ đăng ký kinh doanh và Mã số thuế không khớp với cơ sở dữ liệu quốc gia"
            verified_at = None

        # Plan distribution:
        # Index % 4 == 0 -> Enterprise
        # Index % 4 == 1 -> Pro
        # Index % 4 == 2 -> Growth
        # Index % 4 == 3 -> Free
        mod = index % 4
        if mod == 0 and plan_enterprise:
            plan_id = str(plan_enterprise["_id"])
            credits = 4800
            p_start = now - timedelta(days=30)
            p_end = now + timedelta(days=335)
        elif mod == 1 and plan_pro:
            plan_id = str(plan_pro["_id"])
            credits = 1450
            p_start = now - timedelta(days=10)
            p_end = now + timedelta(days=20)
        elif mod == 2 and plan_growth:
            plan_id = str(plan_growth["_id"])
            credits = 420
            p_start = now - timedelta(days=5)
            p_end = now + timedelta(days=25)
        else:
            plan_id = str(plan_free["_id"]) if plan_free else None
            credits = 0
            p_start = now - timedelta(days=60)
            p_end = None

        comp_doc = {
            "_id": ObjectId(comp_id),
            "name": comp["name"],
            "tax_code": comp["tax"],
            "industries": [ind_code],
            "size": SIZE_MAPPING.get(comp["size"], comp["size"]),
            "website": comp["web"],
            "location": {
                "country": "Việt Nam",
                "version": "new",
                "province_code": comp["loc"][0],
                "province_name": comp["loc"][1]
            },
            "description": f"<p>{comp['name']} là doanh nghiệp hàng đầu trong lĩnh vực {ind_code.upper()}, tiên phong đổi mới sáng tạo và phát triển nguồn nhân lực chất lượng cao.</p>",
            "logo_url": "",
            "banner_url": "",
            "gallery_urls": ["", "", ""],
            "benefits": ["Thưởng tháng 13 & KPIs", "Bảo hiểm sức khỏe cao cấp", "Cung cấp thiết bị làm việc", "Khám sức khỏe định kỳ", "Du lịch hàng năm"],
            "status": status,
            "rejection_reason": rejection_reason,
            "owner_user_id": owner_id,
            "current_plan_id": plan_id,
            "current_period_start": p_start,
            "current_period_end": p_end,
            "credits_remaining": credits,
            "view_count": 150 + index * 5,
            "profile_view_count": 80 + index * 3,
            "follower_count": 35 + index * 2,
            "save_count": 20 + index,
            "avg_rating": round(4.2 + (index % 8) * 0.1, 1),
            "review_count": 5 + (index % 15),
            "verified_at": verified_at,
            "created_at": now - timedelta(days=60),
            "updated_at": now
        }
        comp_doc["billing_migrated_at"] = now
        companies_to_insert.append(comp_doc)

        if mod != 3 and plan_id:
            chosen_plan = plan_enterprise if mod == 0 else (plan_pro if mod == 1 else plan_growth)
            subscriptions_to_insert.append({
                "owner_type": "company",
                "owner_id": comp_id,
                "plan_id": plan_id,
                "plan_code": chosen_plan.get("plan_code"),
                "order_id": None,
                "status": "active",
                "period_start": p_start,
                "period_end": p_end,
                "created_at": p_start,
                "migrated": True,
            })
            if credits > 0:
                credit_grants_to_insert.append({
                    "owner_type": "company",
                    "owner_id": comp_id,
                    "source": "legacy",
                    "source_ref": None,
                    "amount_granted": credits,
                    "amount_remaining": credits,
                    "expires_at": p_end,
                    "created_at": p_start,
                })

        # 1 HR Owner
        owner_email = f"owner.{slug}@verisem.vn"
        owner_doc = {
            "_id": ObjectId(owner_id),
            "email": owner_email,
            "full_name": f"HR Director - {comp['name'][:25]}",
            "hashed_password": hashed_hr_password,
            "role": UserRole.HR_OWNER.value,
            "company_id": comp_id,
            "department_id": None,
            "job_title_internal": "Trưởng phòng Nhân sự (HR Director)",
            "is_verified": True,
            "email_verified_at": now,
            "is_active": True,
            "created_at": now - timedelta(days=60),
            "updated_at": now
        }
        users_to_insert.append(owner_doc)

        # 3 HR Members
        member_titles = [
            ("recruiter_lead", "Trưởng nhóm Tuyển dụng (Talent Acquisition Lead)"),
            ("senior_recruiter", "Chuyên viên Tuyển dụng Cao cấp (Senior Recruiter)"),
            ("hrbp", "Đối tác Nhân sự Doanh nghiệp (HR Business Partner)")
        ]
        for m_idx, (m_prefix, m_title) in enumerate(member_titles, start=1):
            m_id = str(ObjectId())
            m_email = f"member{m_idx}.{slug}@verisem.vn"
            m_doc = {
                "_id": ObjectId(m_id),
                "email": m_email,
                "full_name": f"{m_title.split('(')[0].strip()} - {comp['name'][:15]}",
                "hashed_password": hashed_hr_password,
                "role": UserRole.HR_MEMBER.value,
                "company_id": comp_id,
                "department_id": None,
                "job_title_internal": m_title,
                "is_verified": True,
                "email_verified_at": now,
                "is_active": True,
                "created_at": now - timedelta(days=50),
                "updated_at": now
            }
            users_to_insert.append(m_doc)

    print(f"Chuẩn bị chèn {len(companies_to_insert)} Companies và {len(users_to_insert)} HR Users vào MongoDB...")

    # Insert into database in batches
    if companies_to_insert:
        await db[Collections.COMPANIES].insert_many(companies_to_insert)
        print(f"✅ Đã nạp thành công {len(companies_to_insert)} Doanh nghiệp!")

    if users_to_insert:
        await db[Collections.USERS].insert_many(users_to_insert)
        print(f"✅ Đã nạp thành công {len(users_to_insert)} Tài khoản HR (125 Owner + 375 Member)!")

    if subscriptions_to_insert:
        await db[Collections.SUBSCRIPTIONS].insert_many(subscriptions_to_insert)
        print(f"✅ Đã nạp thành công {len(subscriptions_to_insert)} Active Subscriptions cho Doanh nghiệp!")

    if credit_grants_to_insert:
        await db[Collections.CREDIT_GRANTS].insert_many(credit_grants_to_insert)
        print(f"✅ Đã nạp thành công {len(credit_grants_to_insert)} Credit Grants cho Doanh nghiệp!")

    # Verify counts
    total_companies = await db[Collections.COMPANIES].count_documents({})
    total_users = await db[Collections.USERS].count_documents({})
    print(f"\n--- TỔNG KẾT SAU KHI NẠP ---")
    print(f"Total Companies trong DB: {total_companies}")
    print(f"Total Users trong DB    : {total_users} (1 Super Admin + 125 HR Owner + 375 HR Member)")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_companies_and_hr())
