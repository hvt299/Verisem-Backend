import os
import sys
import uuid
import random
import asyncio
from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load environment
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path)

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017/verisem")

TICKETS_DATA = [
    # TECH BUG
    {
        "category": "tech_bug",
        "subject": "Lỗi không tải được CV định dạng PDF có dung lượng > 5MB",
        "description": "Khi tôi chọn file CV PDF dung lượng 5.2MB để tải lên, hệ thống báo lỗi 'File size exceeds limit' và tự động hủy tải lên. Xin hướng dẫn cách khắc phục hoặc nâng giới hạn dung lượng.",
        "days_ago": 28,
        "status": "resolved",
        "admin_notes": "Đã nâng giới hạn dung lượng upload lên 10MB và tối ưu nén tệp client-side.",
        "reply_message": "Chào bạn, hệ thống đã được cập nhật cho phép tải lên tệp CV có dung lượng tối đa 10MB. Bạn có thể thử tải lại tệp nhé!"
    },
    {
        "category": "tech_bug",
        "subject": "Gặp lỗi font tiếng Việt khi AI trích xuất thông tin học vấn từ CV",
        "description": "CV của tôi tạo bằng font Times New Roman tiếng Việt, nhưng khi AI đọc xong thì tên trường Đại học Bách Khoa bị lỗi hiển thị thành các ký tự lạ.",
        "days_ago": 25,
        "status": "resolved",
        "admin_notes": "Cập nhật pipeline OCR và font parser hỗ trợ chuẩn UTF-8 đa bảng mã tiếng Việt.",
        "reply_message": "Cảm ơn bạn đã phản hồi. Đội ngũ kỹ thuật đã tối ưu bộ bóc tách ngôn ngữ tiếng Việt (UTF-8). Hồ sơ của bạn đã được cập nhật thông tin chuẩn xác."
    },
    {
        "category": "tech_bug",
        "subject": "Không nhận được mã OTP xác thực email khi đổi mật khẩu tài khoản",
        "description": "Tôi đã bấm gửi mã xác thực 3 lần qua email đăng ký nhưng trong hộp thư đến và thư rác đều không nhận được mã OTP.",
        "days_ago": 21,
        "status": "resolved",
        "admin_notes": "Kiểm tra Brevo log: email bị delay do hàng đợi cao điểm. Đã gửi lại mã thành công.",
        "reply_message": "Hệ thống email đã khôi phục bình thường và gửi lại mã OTP cho bạn. Vui lòng kiểm tra lại hòm thư."
    },
    {
        "category": "tech_bug",
        "subject": "Lỗi hiển thị thanh cuộn khi xem preview CV trên trình duyệt Safari macOS",
        "description": "Khi xem trước bản PDF CV trên MacBook sử dụng trình duyệt Safari 17, thanh cuộn tài liệu bị mất và không thể trượt xuống các trang dưới.",
        "days_ago": 18,
        "status": "in_progress",
        "admin_notes": "Frontend dev đang tái hiện lỗi trên Safari Webkit để fix CSS overflow.",
        "reply_message": "Chào bạn, đội ngũ kỹ thuật đã ghi nhận lỗi hiển thị trên Safari và đang hoàn tất bản vá CSS. Chúng tôi sẽ thông báo ngay khi triển khai."
    },
    {
        "category": "tech_bug",
        "subject": "Nút 'Chấp nhận Offer' không phản hồi trên giao diện điện thoại di động",
        "description": "Tôi nhận được thư mời tuyển dụng từ công ty, nhưng khi mở trên điện thoại iPhone thì bấm nút 'Chấp nhận Offer' không có phản hồi gì.",
        "days_ago": 14,
        "status": "resolved",
        "admin_notes": "Lỗi z-index modal che touch event trên mobile. Đã deploy hotfix.",
        "reply_message": "Chào bạn, lỗi trên thiết bị di động đã được khắc phục. Bạn có thể tải lại trang và xác nhận nhận offer thành công rồi nhé!"
    },
    {
        "category": "tech_bug",
        "subject": "Lỗi 403 Forbidden khi tải xuống danh sách ứng viên xuất file Excel",
        "description": "Tài khoản HR Member của tôi được phân công quản lý tin tuyển dụng nhưng khi bấm 'Xuất Excel ứng viên' thì báo lỗi 403 không có quyền.",
        "days_ago": 9,
        "status": "in_progress",
        "admin_notes": "Kiểm tra phân quyền: HR Member cần permission export_candidates từ HR Owner.",
        "reply_message": "Chào bạn, tính năng xuất Excel yêu cầu quyền từ HR Owner của công ty bạn. Chúng tôi đang kiểm tra lại cấu hình phân quyền này."
    },
    {
        "category": "tech_bug",
        "subject": "Hệ thống AI gợi ý điểm phù hợp bị treo ở trạng thái 99%",
        "description": "Tôi vừa đăng tin tuyển dụng mới và nộp 5 CV mẫu, nhưng vòng quay tính điểm AI match score cứ đứng mãi ở 99% không trả kết quả.",
        "days_ago": 2,
        "status": "open",
        "admin_notes": "Cần kiểm tra worker Celery / Redis queue xử lý vector embedding.",
        "reply_message": None
    },

    # BILLING
    {
        "category": "billing",
        "subject": "Yêu cầu xuất hóa đơn điện tử VAT cho gói đăng ký HR Pro",
        "description": "Công ty chúng tôi vừa thanh toán gói HR Pro 1 năm trị giá 12.000.000đ. Nhờ ban quản trị xuất hóa đơn VAT theo thông tin công ty đính kèm.",
        "days_ago": 26,
        "status": "resolved",
        "admin_notes": "Đã tạo hóa đơn điện tử e-invoice và gửi về email kế toán công ty.",
        "reply_message": "Kính gửi quý công ty, hóa đơn điện tử số HD-2026-1029 đã được phát hành và gửi tới email kế toán của bạn. Xin cảm ơn!"
    },
    {
        "category": "billing",
        "subject": "Đã thanh toán gói Pro qua QR SePay nhưng tài khoản chưa được kích hoạt",
        "description": "Tôi đã quét mã VietQR ngân hàng lúc 10h sáng nay mã đơn hàng ORDER-928192, tiền đã trừ nhưng tài khoản vẫn báo đang dùng gói Free.",
        "days_ago": 22,
        "status": "resolved",
        "admin_notes": "Webhook SePay bị trễ 5 phút do ngắt quãng kết nối mạng. Đã kích hoạt thủ công cho khách hàng.",
        "reply_message": "Chào bạn, giao dịch của bạn đã được đối soát thành công và gói HR Pro đã được kích hoạt ngay lập tức kèm 1 tháng ưu đãi bù đắp."
    },
    {
        "category": "billing",
        "subject": "Thắc mắc về chính sách hoàn tiền gói tin tuyển dụng chưa sử dụng",
        "description": "Chúng tôi đã mua thêm 3 lượt đăng tin nổi bật nhưng dự án tuyển dụng bị hoãn. Chúng tôi có thể bảo lưu hoặc hoàn lại số tiền này không?",
        "days_ago": 19,
        "status": "resolved",
        "admin_notes": "Đã chuyển đổi lượt đăng tin sang Credit hạn dùng vô thời hạn cho công ty.",
        "reply_message": "Chào bạn, chúng tôi đã chuyển 3 lượt tin thành tín dụng tuyển dụng có giá trị vĩnh viễn trong tài khoản để công ty sử dụng cho các dự án sau."
    },
    {
        "category": "billing",
        "subject": "Cần nâng cấp từ gói HR Starter lên gói Doanh nghiệp HR Enterprise",
        "description": "Công ty chúng tôi quy mô mở rộng thêm 5 chi nhánh nên cần gói Enterprise không giới hạn số lượng HR Member và tính năng ATS nâng cao.",
        "days_ago": 15,
        "status": "in_progress",
        "admin_notes": "Bộ phận kinh doanh B2B đang liên hệ để tư vấn bảng giá chiết khấu Enterprise.",
        "reply_message": "Chào quý công ty, chuyên viên phụ trách giải pháp doanh nghiệp của Verisem sẽ liên hệ qua điện thoại trong hôm nay để hỗ trợ trực tiếp."
    },
    {
        "category": "billing",
        "subject": "Tài khoản bị trừ tiền 2 lần do mạng chập chờn khi quét mã QR",
        "description": "Hệ thống báo timeout nên tôi quét lại mã lần 2, kiểm tra biến động số dư ngân hàng thì thấy bị trừ 2 lần cùng một mã đơn.",
        "days_ago": 11,
        "status": "resolved",
        "admin_notes": "Đã kiểm tra đối soát sao kê ngân hàng và thực hiện lệnh hoàn tiền giao dịch trùng.",
        "reply_message": "Chào bạn, giao dịch trùng lặp đã được hoàn trả lại tài khoản ngân hàng của bạn. Bạn vui lòng kiểm tra thông báo biến động số dư nhé."
    },
    {
        "category": "billing",
        "subject": "Hỏi về số lượng lượt lọc AI còn lại trong chu kỳ tháng hiện tại",
        "description": "Tôi muốn biết tài khoản công ty còn lại bao nhiêu lượt AI Matching và ngày gia hạn chu kỳ tiếp theo là ngày nào?",
        "days_ago": 5,
        "status": "waiting_for_user",
        "admin_notes": "Đã hướng dẫn khách hàng xem tab Quản lý Gói cước trong phần Cài đặt Doanh nghiệp.",
        "reply_message": "Chào bạn, bạn có thể kiểm tra trực tiếp số dư AI Matching tại trang Cài đặt > Gói cước. Vui lòng phản hồi nếu bạn cần thêm thông tin nhé."
    },
    {
        "category": "billing",
        "subject": "Hỏi về bảng giá chiết khấu khi thanh toán theo năm cho Start-up",
        "description": "Chúng tôi là công ty khởi nghiệp công nghệ dưới 2 năm, liệu có chương trình học bổng hoặc voucher ưu đãi gói HR Pro hàng năm không?",
        "days_ago": 1,
        "status": "open",
        "admin_notes": None,
        "reply_message": None
    },

    # KYC
    {
        "category": "kyc",
        "subject": "Gửi bổ sung Giấy phép đăng ký kinh doanh và CCCD người đại diện",
        "description": "Tôi gửi bổ sung ảnh chụp bản gốc GPĐKKD có dấu đỏ và CCCD 2 mặt của Giám đốc để hoàn thiện thủ tục xác minh doanh nghiệp.",
        "days_ago": 27,
        "status": "resolved",
        "admin_notes": "Đã đối chiếu cổng thông tin đăng ký doanh nghiệp quốc gia: Hợp lệ. Đã duyệt KYC.",
        "reply_message": "Chào bạn, hồ sơ pháp lý của công ty bạn đã được duyệt thành công. Huy hiệu Doanh nghiệp Xác thực (Verified) đã được gắn vào trang công ty."
    },
    {
        "category": "kyc",
        "subject": "Thời gian phê duyệt hồ sơ doanh nghiệp mới thường mất bao lâu?",
        "description": "Chúng tôi đã gửi hồ sơ KYC từ chiều hôm qua, hiện đang cần đăng tin tuyển gấp trong ngày mai. Mong được hỗ trợ duyệt sớm.",
        "days_ago": 23,
        "status": "resolved",
        "admin_notes": "Hồ sơ đầy đủ, đã duyệt ưu tiên trong vòng 2 giờ.",
        "reply_message": "Chào bạn, hồ sơ của bạn đã được ưu tiên kiểm tra và phê duyệt ngay lúc này. Bạn đã có thể đăng tin tuyển dụng bình thường."
    },
    {
        "category": "kyc",
        "subject": "Cần thay đổi tên pháp nhân công ty do sáp nhập doanh nghiệp",
        "description": "Công ty TNHH Giải pháp Phần mềm ABC vừa đổi tên thành Công ty Cổ phần Công nghệ ABC Việt Nam. Nhờ hỗ trợ cập nhật lại tên hiển thị.",
        "days_ago": 17,
        "status": "in_progress",
        "admin_notes": "Đang chờ khách hàng gửi quyết định thay đổi nội dung đăng ký doanh nghiệp mới nhất.",
        "reply_message": "Chào bạn, bạn vui lòng đính kèm bản scan Giấy phép đăng ký kinh doanh mới nhất để ban quản trị tiến hành cập nhật tên pháp nhân."
    },
    {
        "category": "kyc",
        "subject": "Hồ sơ xác thực KYC bị từ chối với lý do ảnh chụp bị mờ",
        "description": "Tôi nhận được thông báo hồ sơ KYC bị từ chối. Tôi đã chụp lại bản scan rõ nét độ phân giải cao 300dpi, nhờ BQT xem xét lại.",
        "days_ago": 12,
        "status": "resolved",
        "admin_notes": "Ảnh scan mới đạt tiêu chuẩn rõ nét. Đã phê duyệt xác thực.",
        "reply_message": "Chào bạn, hồ sơ mới gửi đã đạt tiêu chuẩn thẩm định. Chúng tôi đã chính thức kích hoạt trạng thái Đã xác thực cho tài khoản."
    },
    {
        "category": "kyc",
        "subject": "Hỏi về thủ tục xác thực doanh nghiệp có vốn đầu tư nước ngoài (FDI)",
        "description": "Văn phòng đại diện của công ty mẹ tại Singapore chưa có giấy phép kinh doanh Việt Nam thì cần cung cấp giấy tờ gì để xác thực?",
        "days_ago": 8,
        "status": "waiting_for_user",
        "admin_notes": "Đã gửi hướng dẫn hồ sơ pháp lý: Giấy phép lập văn phòng đại diện hoặc Giấy chứng nhận đầu tư.",
        "reply_message": "Chào bạn, với văn phòng đại diện bạn chỉ cần cung cấp Giấy phép thành lập VPĐD do Sở Công Thương cấp. Vui lòng gửi lại qua email này nhé."
    },
    {
        "category": "kyc",
        "subject": "Xác nhận quyền sở hữu tên miền công ty và email doanh nghiệp",
        "description": "Tôi muốn xác minh email @fpt.com để nhận huy hiệu Doanh nghiệp công nghệ đã được chứng thực tên miền.",
        "days_ago": 3,
        "status": "open",
        "admin_notes": None,
        "reply_message": None
    },

    # OTHER
    {
        "category": "other",
        "subject": "Góp ý cải thiện giao diện lọc ứng viên theo mức lương mong muốn",
        "description": "Hiện tại bộ lọc lương chỉ có các mốc cố định. Nếu có thể nhập khoảng tùy chỉnh Min - Max bằng thanh trượt thì sẽ tiện dụng hơn rất nhiều.",
        "days_ago": 29,
        "status": "resolved",
        "admin_notes": "Chuyển feedback cho bộ phận Product Design. Đã ghi nhận vào Roadmap Q4.",
        "reply_message": "Cảm ơn đóng góp rất hữu ích của bạn! Đội ngũ phát triển đã đưa tính năng thanh trượt khoảng lương tùy chỉnh vào lộ trình nâng cấp."
    },
    {
        "category": "other",
        "subject": "Hỏi về tài liệu hướng dẫn tích hợp API tuyển dụng vào hệ thống nội bộ",
        "description": "Bộ phận IT công ty chúng tôi muốn đồng bộ danh sách ứng viên từ Verisem về hệ thống ERP nhân sự nội bộ qua REST API. Xin tài liệu Swagger/API docs.",
        "days_ago": 24,
        "status": "resolved",
        "admin_notes": "Đã gửi link Swagger documentation và API token cho đối tác.",
        "reply_message": "Chào bạn, tài liệu API chuẩn RESTful và hướng dẫn xác thực Bearer token đã được gửi tới email kỹ thuật của bạn. Chúc bạn tích hợp suôn sẻ!"
    },
    {
        "category": "other",
        "subject": "Đề xuất thêm bộ lọc ứng viên theo khu vực quận/huyện chi tiết",
        "description": "Chúng tôi cần tuyển nhân viên giao hàng và bán hàng theo từng quận cụ thể tại TP.HCM. Rất mong hệ thống hỗ trợ lọc sâu đến cấp Quận/Huyện.",
        "days_ago": 20,
        "status": "resolved",
        "admin_notes": "Đã phát triển hệ thống Administrative Units 3 cấp (Tỉnh/Thành, Quận/Huyện, Phường/Xã).",
        "reply_message": "Chào bạn, hệ thống Verisem đã tích hợp đầy đủ bộ lọc địa giới hành chính 3 cấp toàn quốc. Bạn có thể sử dụng ngay trong phần tìm kiếm ứng viên."
    },
    {
        "category": "other",
        "subject": "Tư vấn thiết lập quy trình phỏng vấn nhiều vòng cho phòng ban Kỹ thuật",
        "description": "Chúng tôi muốn cài đặt luồng phỏng vấn gồm 3 vòng: Phỏng vấn sơ loại HR, Phỏng vấn Kỹ thuật Tech Lead, và Phỏng vấn Văn hóa với CEO.",
        "days_ago": 16,
        "status": "in_progress",
        "admin_notes": "Chuyên gia tuyển dụng của Verisem đang soạn tài liệu mẫu quy trình tuyển dụng phù hợp.",
        "reply_message": "Chào bạn, chuyên viên hỗ trợ đã liên hệ để tư vấn thiết lập phễu tuyển dụng tùy chỉnh cho các vòng phỏng vấn của công ty bạn."
    },
    {
        "category": "other",
        "subject": "Hỏi về tính năng tự động gửi email cảm ơn khi ứng viên nộp hồ sơ",
        "description": "Làm thế nào để tùy chỉnh mẫu email tự động phản hồi cho ứng viên ngay khi họ nhấn nộp hồ sơ trên hệ thống?",
        "days_ago": 10,
        "status": "resolved",
        "admin_notes": "Đã hướng dẫn thiết lập mẫu email thông báo tự động trong tab Cài đặt Tuyển dụng.",
        "reply_message": "Chào bạn, bạn có thể vào Cài đặt > Mẫu Email Thông báo để soạn thảo nội dung email phản hồi tự động gửi tới ứng viên nhé."
    },
    {
        "category": "other",
        "subject": "Khiếu nại tin tuyển dụng có dấu hiệu mạo danh thương hiệu",
        "description": "Tôi phát hiện có tài khoản đăng tin tuyển dụng lấy logo và tên thương hiệu Shopee nhưng yêu cầu ứng viên nạp tiền làm nhiệm vụ. Cần gỡ bỏ khẩn cấp.",
        "days_ago": 6,
        "status": "closed",
        "admin_notes": "Đã kiểm tra và khóa vĩnh viễn tài khoản gian lận, hạ tin vi phạm trong vòng 15 phút.",
        "reply_message": "Cảm ơn bạn đã kịp thời cảnh báo! Ban quản trị đã khóa vĩnh viễn tài khoản giả mạo và bảo vệ quyền lợi cộng đồng người tìm việc."
    },
    {
        "category": "other",
        "subject": "Gợi ý bổ sung chế độ giao diện tối (Dark mode) khi đọc tài liệu",
        "description": "Nhiều khi tôi đọc CV vào buổi tối bị chói mắt. Rất mong hệ thống hỗ trợ dark mode toàn diện trên tất cả các trang.",
        "days_ago": 3,
        "status": "resolved",
        "admin_notes": "Hệ thống đã nâng cấp Dark Mode toàn diện theo chuẩn Design System mới.",
        "reply_message": "Chào bạn, tính năng chuyển đổi Light / Dark mode đã có mặt tại thanh công cụ góc trên màn hình. Mời bạn trải nghiệm thử nhé!"
    },
    {
        "category": "other",
        "subject": "Yêu cầu xóa tài khoản và dữ liệu cá nhân theo chính sách quyền riêng tư",
        "description": "Tôi đã tìm được việc làm chính thức và mong muốn hệ thống ẩn hồ sơ cũng như xóa thông tin liên hệ cá nhân khỏi danh sách công khai.",
        "days_ago": 0,
        "status": "open",
        "admin_notes": None,
        "reply_message": None
    }
]

async def seed():
    print(f"Connecting to MongoDB at: {MONGO_URL[:30]}...")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client.get_default_database()

    # Get admin user
    admin_user = await db.users.find_one({"role": "admin"})
    admin_id = str(admin_user["_id"]) if admin_user else "6ad7c1d7d2623ce816f48901"

    # Get other users (applicants / hr)
    users = await db.users.find({"role": {"$ne": "admin"}}).to_list(100)
    print(f"Found {len(users)} users in database.")

    # Clean existing support tickets (if any) or append
    existing_count = await db.support_tickets.count_documents({})
    print(f"Current tickets count: {existing_count}")

    now = datetime.now(timezone.utc)
    new_tickets = []

    for idx, item in enumerate(TICKETS_DATA):
        # Pick a random user or fallback
        if users:
            picked_user = users[idx % len(users)]
            user_id = str(picked_user["_id"])
            full_name = picked_user.get("full_name") or picked_user.get("name") or f"Người dùng {idx + 1}"
            email = picked_user.get("email") or f"user{idx+1}@verisem.vn"
        else:
            user_id = None
            full_name = f"Nguyễn Văn {chr(65 + idx % 26)}"
            email = f"customer{idx+1}@gmail.com"

        created_at = now - timedelta(days=item["days_ago"], hours=random.randint(1, 12), minutes=random.randint(0, 59))
        updated_at = created_at + timedelta(hours=random.randint(1, 6))

        # Unique Ticket number: ATS-TIMESTAMP-HEX
        timestamp_hex = hex(int(created_at.timestamp()))[2:].upper()
        random_hex = str(uuid.uuid4())[:4].upper()
        ticket_number = f"ATS-{timestamp_hex}-{random_hex}"

        ticket_doc = {
            "ticket_number": ticket_number,
            "full_name": full_name,
            "email": email,
            "category": item["category"],
            "subject": item["subject"],
            "description": item["description"],
            "user_id": user_id,
            "status": item["status"],
            "created_at": created_at,
            "updated_at": updated_at,
            "deleted_at": None
        }

        if item.get("admin_notes"):
            ticket_doc["admin_notes"] = item["admin_notes"]

        if item.get("reply_message"):
            ticket_doc["reply_message"] = item["reply_message"]
            ticket_doc["last_replied_at"] = updated_at

        if item["status"] in ["resolved", "closed"]:
            ticket_doc["resolved_by_admin_id"] = admin_id
            ticket_doc["resolved_at"] = updated_at

        new_tickets.append(ticket_doc)

    if new_tickets:
        result = await db.support_tickets.insert_many(new_tickets)
        print(f"Successfully inserted {len(result.inserted_ids)} support tickets!")

    # Verify counts
    total = await db.support_tickets.count_documents({})
    print(f"Total tickets in DB now: {total}")

    # Summary by status
    status_counts = await db.support_tickets.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]).to_list(10)
    print("Tickets by status:", status_counts)

    # Summary by category
    cat_counts = await db.support_tickets.aggregate([
        {"$group": {"_id": "$category", "count": {"$sum": 1}}}
    ]).to_list(10)
    print("Tickets by category:", cat_counts)

    client.close()

if __name__ == "__main__":
    asyncio.run(seed())
