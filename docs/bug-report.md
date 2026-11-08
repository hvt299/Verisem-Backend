# Báo cáo lỗi hệ thống (BE + FE)

> Ngày rà soát: 11/10/2026
> Phạm vi: toàn bộ `CV-Ranking-Backend/app` và các phần logic chính của `CV-Ranking-Web` (middleware, auth, API client, hooks, các trang render nội dung người dùng).
> Code được rà là nhánh `feat/theanh/subscription-test-tools`, tức là đã gồm billing mới. Các lỗi billing cũ đã sửa xem tại [subscription-redesign.md](subscription-redesign.md).

## Cách rà soát

- Đọc code từng router, service và repository.
- Phân tích tĩnh: `pyflakes`, kèm script tự viết để tìm lời gọi tới **method repository không tồn tại** và **giá trị Enum không tồn tại**.
- Các lỗi đều được xác định bằng cách đọc code, **chưa chạy để tái hiện**, trừ phần billing đã có test riêng. Lỗi nào phụ thuộc môi trường deploy được đánh dấu **(cần xác nhận)**.

## Tổng quan

| Mức độ | Số lỗi | Ý nghĩa |
|---|---|---|
| 🔴 Nghiêm trọng | 2 | Lỗ hổng bảo mật, chiếm được tài khoản hoặc dữ liệu công ty khác |
| 🟠 Cao | 13 | Chức năng bị crash, chạy sai hoàn toàn, hoặc mất dữ liệu / mất doanh thu |
| 🟡 Trung bình | 14 | Sai logic, phân quyền lỏng, ảnh hưởng một phần người dùng |
| ⚪ Thấp | 10 | Khó chịu, không nhất quán, rủi ro nhỏ |

**Nên sửa trước:** BUG-01, BUG-02, BUG-03, BUG-04, BUG-05, BUG-08.

---

## 🔴 Nghiêm trọng

### BUG-01: Stored XSS qua mô tả job và mô tả công ty
- **Vị trí:**
  - FE: `components/jobs/JobDetailsContent.tsx:23,35,47`, `app/(public)/jobs/[id]/page.tsx:265,277,289,301`, `app/(public)/companies/[id]/page.tsx:244`, `components/jobs/detail/TabJobInfo.tsx:21`
  - BE: `job_router.py` (create/update job), `company_router.py:192` (description)
- **Mô tả:** HTML do HR nhập (từ CKEditor hoặc gọi thẳng API) được lưu nguyên vào DB, rồi render bằng `dangerouslySetInnerHTML` mà **không qua bước lọc nào**. Cả BE lẫn FE đều không dùng thư viện sanitize.
- **Hậu quả:** HR chèn `<img src=x onerror=...>` vào mô tả job. Mọi người mở trang job công khai, kể cả admin, sẽ chạy script đó. Token đăng nhập lại nằm trong cookie **không có `httpOnly`** (`store/useAuthStore.ts:106`), nên script đọc được token và chiếm được tài khoản.
- **Hướng sửa:**
  - Lọc HTML ở BE khi lưu (ví dụ dùng `nh3` hoặc `bleach` với whitelist thẻ của CKEditor).
  - Thêm `DOMPurify` ở FE trước khi render.
  - Về lâu dài, chuyển token sang cookie `httpOnly` do BE set.

### BUG-02: HR có thể chuyển job sang công ty khác
- **Vị trí:** `job_router.py:211` và `:237` (`update_job`)
- **Mô tả:** `update_data = job_update.model_dump()` lấy cả `company_id` từ request (field bắt buộc trong `JobCreateEnterprise`), rồi `$set` thẳng vào job. `scope_filter` chỉ kiểm tra job cũ thuộc công ty mình, không chặn việc đổi `company_id`.
- **Hậu quả:** HR gửi `company_id` của công ty khác thì job (kèm đơn ứng tuyển) bị chuyển sang công ty đó: dữ liệu lẫn giữa các công ty, và có thể đăng job dưới tên công ty khác đã được xác thực.
- **Hướng sửa:** luôn ghi đè `update_data["company_id"] = existing_job["company_id"]`, hoặc bỏ `company_id` khỏi schema update.

---

## 🟠 Cao

### BUG-03: Các API bị crash vì gọi hàm hoặc tên không tồn tại
Kiểm tra tĩnh xác nhận các chỗ sau **chắc chắn lỗi 500** khi được gọi:

| Vị trí | Lỗi | Chức năng hỏng |
|---|---|---|
| `company_router.py:454` | `UserRepository.update_by_query` không tồn tại | Owner đổi vai trò thành viên |
| `company_router.py:472,474` | `update_by_query` không tồn tại, và `UserRole.USER` cũng không tồn tại | Owner xoá thành viên khỏi công ty |
| `admin_router.py:363` | Chưa import `BlogRepository` | Admin xoá bài blog |
| `job_router.py:35` | `ApplicationRepository.find_all` không tồn tại | Chấm điểm lại CV (xem BUG-04) |

- **Hướng sửa:**
  - Dùng `update_custom(...)` thay cho `update_by_query`.
  - Bỏ `role` ra khỏi lệnh xoá thành viên (hoặc chuyển sang role phù hợp).
  - Import `BlogRepository`.
  - Dùng `find_many` hoặc `aggregate_applications` thay cho `find_all`.

### BUG-04: Chấm điểm lại CV khi sửa JD chưa bao giờ chạy được
- **Vị trí:** `job_router.py:33-67, 253-275, 448-463`
- **Mô tả:** Có 4 vấn đề chồng lên nhau:
  1. `rescore_all_applications_for_job` crash ngay dòng đầu (BUG-03).
  2. URL QStash bị ghép sai: `f"{QSTASH_URL}{target_webhook_url}"` cho ra `https://qstash-eu-central-1.upstash.iohttps://verisem-backend.onrender.com/...` vì thiếu `/v2/publish/`. Lỗi bị nuốt trong `except`, nên **trên production không chấm lại lần nào**.
  3. Logic bị ngược: khi **còn** lượt chấm lại nhưng không có QStash thì không làm gì cả, còn khi **hết** lượt thì lại chạy chấm lại (vượt giới hạn gói).
  4. API `POST /jobs/{id}/rescore` không kiểm tra giới hạn `max_rescores_per_job`.
- **Hậu quả:** sửa JD hoặc trọng số AI nhưng điểm ứng viên vẫn là điểm cũ, trong khi số lượt chấm lại vẫn bị trừ.
- **Hướng sửa:** sửa BUG-03, đổi URL thành `f"{QSTASH_URL}/v2/publish/{target_webhook_url}"`, đảo lại điều kiện, và chỉ tăng `rescore_count` khi đã gửi được tác vụ.

### BUG-05: HR thuộc phòng ban không thấy job, CV hay đơn ứng tuyển nào
- **Vị trí:** `core/security.py:159-160` (`get_scope_filter`)
- **Mô tả:** Với `HR_MEMBER` có `department_id`, bộ lọc thêm điều kiện `department_id`. Nhưng job (`JobCreateEnterprise`), CV và đơn ứng tuyển **không bao giờ được lưu `department_id`**.
- **Hậu quả:** khi Owner phân thành viên vào một phòng ban, thành viên đó không còn thấy job, kho CV hay ứng viên nào.
- **Liên quan:** khi mời thành viên, `department_id` và `department_roles` có trong invite token (`company_router.py:261-271`) nhưng **không được lưu** khi đăng ký (`auth_service.py:94-104`).
- **Hướng sửa:** lưu `department_id` vào job khi tạo và copy sang application, hoặc bỏ điều kiện `department_id` khỏi scope và dùng `assigned_hr_ids`.

### BUG-06: Giới hạn số lần tự chấm điểm mỗi ngày của ứng viên không có tác dụng
- **Vị trí:** `applicant_router.py:511-546`
- **Mô tả:** Số lần dùng được đếm bằng audit log có `action = "APPLICANT_SELF_SCORE"`. Nhưng giá trị này thuộc `QuotaActionType` chứ không thuộc `AuditAction`, nên `AuditLogCreate` báo lỗi validate. `log_action` nuốt lỗi đó, **không ghi được log nào**, nên số đếm luôn là 0.
- **Hậu quả:** ứng viên gói Free tự chấm điểm không giới hạn, tốn tài nguyên AI.
- **Hướng sửa:** thêm `APPLICANT_SELF_SCORE` vào `AuditAction`, hoặc đếm bằng một collection riêng.

### BUG-07: Cập nhật đơn ứng tuyển chỉ thêm ghi chú thì bị crash
- **Vị trí:** `cv_router.py:354-360`
- **Mô tả:** Khi chỉ gửi `note_to_add` mà không đổi trạng thái, `$set` rỗng nên bị `del`. Ngay sau đó code lại gán `update_query["$set"]["updated_at"]`, gây `KeyError`, rồi bị bắt thành lỗi 500.
- **Hướng sửa:** dùng `update_query.setdefault("$set", {})["updated_at"] = ...`.

### BUG-08: Ứng viên xoá CV hoặc thư giới thiệu thì HR mất file của đơn đã nộp
- **Vị trí:** `applicant_router.py:561`, `:760`
- **Mô tả:** Đơn ứng tuyển lưu `cv_snapshot.file_url`, trỏ cùng file Cloudinary với CV trong thư viện. Khi ứng viên xoá CV khỏi thư viện, file trên Cloudinary bị xoá theo.
- **Hậu quả:** HR mở hồ sơ đã nhận thì link CV bị hỏng (nếu việc xoá trên Cloudinary chạy được, xem BUG-20).
- **Hướng sửa:** không xoá file nếu vẫn còn đơn ứng tuyển tham chiếu tới nó, hoặc copy file riêng khi nộp đơn.

### BUG-09: Gộp hồ sơ khi ứng viên xác thực email (`merge_ghost_profiles`) không chạy
- **Vị trí:** `auth_service.py:455-470`
- **Mô tả:** Có 3 lỗi cùng lúc:
  1. `CVRepository.find_all` trả về document chưa được format, nên `cv.get("id")` là `None` và lệnh update CV không tác động gì.
  2. `ApplicationRepository.find_all` không tồn tại.
  3. Truy vấn theo field `cv_id`, nhưng đơn do HR tạo không có field này (chỉ có `cv_snapshot.cv_document_id`).
- **Hậu quả:** ứng viên đã được HR tải CV lên trước đó sẽ không thấy các đơn liên quan sau khi đăng ký. Lỗi bị nuốt và chỉ in ra log.
- **Hướng sửa:** dùng `str(cv["_id"])` và `update_custom` để cập nhật hàng loạt theo `cv_snapshot.cv_document_id`.

### BUG-10: Công ty không có `owner_user_id`
- **Vị trí:** `auth_service.py:67-82` (`_create_company`). Các chỗ dùng: `company_router.py:186,246`, `admin_service.py:141`
- **Mô tả:** Field `owner_user_id` không bao giờ được gán.
- **Hậu quả:**
  - Các kiểm tra "chỉ Owner gốc" không có tác dụng: mọi HR_OWNER đều sửa được thông tin công ty và mời thành viên. Kết hợp với chức năng nâng thành viên lên Owner, Owner mới có thể hạ quyền hoặc xoá Owner gốc.
  - **Thông báo duyệt hoặc từ chối KYC không bao giờ được gửi** cho công ty.
- **Hướng sửa:** gán `owner_user_id` sau khi tạo user, và viết script bổ sung cho dữ liệu cũ.

### BUG-11: Có tính năng trả phí nhưng không được kiểm tra, có tính năng trả phí nhưng không bao giờ mở khoá
- **Vị trí:** BE: toàn bộ `app/`. FE: `hooks/useCredits.ts:41`
- **Mô tả:**
  - `can_customize_ai_weights` và `max_cv_parses_per_month` có trong cấu hình gói nhưng **BE không kiểm tra ở đâu cả**. Gói Free vẫn gửi `score_weights` hoặc parse CV không giới hạn.
  - FE đọc `subscription.features.can_use_ai_cv_review`, nhưng `/my-plan` **không trả về `features`**, nên AI Mentor **luôn bị khoá, kể cả với người đã trả tiền**.
- **Hướng sửa:** trả thêm `features` trong `/my-plan`, và kiểm tra quyền ở BE cho từng tính năng.

### BUG-12: Định nghĩa trùng route `saved-companies` làm lệch bộ đếm
- **Vị trí:** `applicant_router.py:567` và `:826` (POST), `:595` và `:836` (DELETE, **trùng cả path lẫn method**)
- **Mô tả:**
  - Hai route DELETE trùng nhau, nên chỉ route ở dòng 595 được dùng.
  - `POST /saved-companies/{id}` tăng `save_count`, trong khi `DELETE` (dòng 595) lại giảm `follower_count`.
- **Hậu quả:** `follower_count` bị âm, còn `save_count` chỉ tăng mà không giảm.
- **Hướng sửa:** giữ lại một bộ API duy nhất và một bộ đếm.

### BUG-13: Rate limit có thể tính theo IP của proxy (cần xác nhận)
- **Vị trí:** `middleware/rate_limit.py:12`, `Dockerfile` (lệnh `uvicorn` không có `--proxy-headers --forwarded-allow-ips`)
- **Mô tả:** BE chạy sau proxy (Render), nên `get_remote_address` có thể trả về IP của proxy thay vì IP người dùng.
- **Hậu quả:** **mọi người dùng dùng chung một giới hạn**: chỉ 5 lần đăng nhập mỗi phút và 10 lần đăng ký mỗi ngày cho toàn hệ thống.
- **Hướng sửa:** chạy uvicorn với `--proxy-headers --forwarded-allow-ips="*"`, hoặc viết `key_func` đọc `X-Forwarded-For`.

### BUG-14: Đăng nhập Google/LinkedIn kèm invite token ghi đè vai trò và công ty của tài khoản đã tồn tại
- **Vị trí:** `auth_service.py:288-296`
- **Mô tả:** User đã tồn tại, đăng nhập mạng xã hội kèm invite token thì `role` và `company_id` bị ghi đè mà không kiểm tra gì.
- **Hậu quả:** Owner của công ty A bấm link mời của công ty B thì chuyển sang B, bỏ lại A không còn Owner. Ứng viên bấm link mời thì thành HR.
- **Hướng sửa:** chỉ cho phép khi user chưa thuộc công ty nào và không phải Owner, hoặc yêu cầu xác nhận.

### BUG-15: Gói lẻ đã thanh toán theo QR cũ có thể bị bỏ qua khi deploy billing mới
- **Vị trí:** `subscription_service.py` (`handle_sepay_webhook`)
- **Mô tả:** Webhook mới chỉ nhận mã `CVR…`. Nếu khách đã quét QR cũ (`UPGRADE …`) trước khi deploy nhưng tiền về sau khi deploy, giao dịch sẽ không được xử lý.
- **Hướng sửa:** trong thời gian chuyển tiếp, cho webhook nhận thêm cú pháp cũ, hoặc rà lại lịch sử SePay rồi cấp gói thủ công.

---

## 🟡 Trung bình

### BUG-16: `except Exception` biến mọi lỗi thành 500
- **Vị trí:** `cv_router.py:427, 445, 499, 510` (đổi trạng thái đơn, xoá CV, xem kho CV, gỡ đơn)
- **Mô tả:** Các `HTTPException(404/403)` bên trong khối try cũng bị bắt lại, rồi trả về 500 với nội dung `"404: ..."`.
- **Hướng sửa:** thêm `except HTTPException: raise` trước `except Exception`.

### BUG-17: Phân quyền HR_MEMBER không chặt
- **Vị trí:** `cv_router.py:574-581`, `:431`, `:503`
- **Mô tả:**
  - Đánh dấu đã xem: **ghi dữ liệu trước**, rồi mới gọi `ensure_job_manager`.
  - Gỡ đơn và xoá CV khỏi kho: không gọi `ensure_job_manager`, nên member xoá được đơn hoặc CV của job không được phân công cho mình. Xoá CV còn xoá luôn mọi đơn dùng CV đó.
- **Hướng sửa:** kiểm tra quyền trước khi ghi, và áp dụng `ensure_job_manager` thống nhất ở mọi API.

### BUG-18: Token xác thực email dùng được như access token, đổi mật khẩu không thu hồi token
- **Vị trí:** `auth_service.py:140`, `core/security.py:63`
- **Mô tả:**
  - Mọi loại token (đăng nhập, xác thực email, mời thành viên) đều ký chung `JWT_SECRET` và không có claim `type`. `get_current_user` chỉ kiểm tra `sub`, nên link xác thực email (hạn 1 ngày) dùng được làm Bearer token, kể cả khi tài khoản chưa xác thực.
  - Đổi hoặc đặt lại mật khẩu không vô hiệu hoá các token đã cấp trước đó (hạn 24 giờ).
- **Hướng sửa:** thêm claim `type` và kiểm tra khi decode. Thêm `token_version` hoặc `password_changed_at` để thu hồi token cũ.

### BUG-19: Xác thực chữ ký QStash bỏ qua (fail-open) khi thiếu key
- **Vị trí:** `core/security.py:182`
- **Mô tả:** Nếu thiếu `QSTASH_CURRENT_SIGNING_KEY`, API `/jobs/internal/webhook/rescore` cho bất kỳ ai gọi.
- **Hậu quả:** người ngoài có thể kích hoạt chấm lại hàng loạt cho mọi job, tốn tài nguyên.
- **Hướng sửa:** từ chối request (fail closed) khi chưa cấu hình key.

### BUG-20: Cloudinary: upload chặn event loop, xoá file có thể không chạy (cần xác nhận)
- **Vị trí:** `storage_service.py:25`, `:50`
- **Mô tả:**
  - `cloudinary.uploader.upload` là hàm đồng bộ nhưng được gọi trong hàm `async`, nên **toàn bộ server bị đứng** trong lúc upload file.
  - `destroy(..., resource_type="auto")`: theo những gì mình biết, API destroy của Cloudinary không hỗ trợ `"auto"`. Nếu đúng vậy thì file không bao giờ bị xoá, và CV đã xoá vẫn truy cập công khai được qua URL.
- **Hướng sửa:** bọc bằng `await asyncio.to_thread(...)`. Khi xoá, lấy đúng `resource_type` (`image` hoặc `raw`) từ URL. Nên dùng `type="authenticated"` cho CV.

### BUG-21: Email bị chèn HTML
- **Vị trí:** `email_service.py` (các template dùng `.format`), `:396`
- **Mô tả:** Tên người dùng, `custom_message` của HR, tên công ty, … được chèn thẳng vào HTML mà không escape.
- **Hậu quả:** chèn được link hoặc nội dung giả mạo vào email gửi từ domain hệ thống (phishing).
- **Hướng sửa:** `html.escape()` mọi giá trị do người dùng nhập.

### BUG-22: Bị trừ credit nhưng không được hoàn khi request thất bại
- **Vị trí:** `cv_router.py:80` (upload CV), `:151` (ghép CV), `:594` (AI interview), `:680` (discover)
- **Mô tả:**
  - Credit bị trừ ở dependency, **trước khi** kiểm tra file, job hoặc CV trùng. Các lỗi 400/404 sau đó không hoàn credit.
  - AI interview vẫn trừ credit khi trả về câu hỏi đã có sẵn trong cache.
  - Admin qua được `require_hr_or_admin` nhưng `require_credits` dùng `require_hr`, nên **admin bị 403** ở API AI interview.
- **Hướng sửa:** trừ credit sau khi kiểm tra xong, hoặc dùng `refund_charged_credits` (đã có sẵn) ở các nhánh lỗi. Miễn phí khi dùng cache.

### BUG-23: Gói có quyền "job nổi bật" vẫn không đặt được khi sửa job
- **Vị trí:** `job_router.py:214-215`
- **Mô tả:** Khi sửa job, `is_hot` luôn bị bỏ với mọi user không phải admin, kể cả khi gói có `can_set_hot_job`.

### BUG-24: API công khai làm lộ thông tin nội bộ của công ty
- **Vị trí:** `company_schema.py:78-81` (`CompanyResponse` dùng cho `/companies/public/*`), `applicant_router.py:846-855` (`/saved-companies/list` trả nguyên document)
- **Mô tả:** Các API này trả về `current_plan_id`, `credits_remaining`, `current_period_end`, … cho người ngoài.
- **Hướng sửa:** tạo một schema public riêng.

### BUG-25: Công ty đổi tên sau khi KYC mà không cần duyệt lại
- **Vị trí:** `company_router.py:192, 217-221`
- **Mô tả:** Chỉ khi đổi `tax_code` hoặc `license_file_url` thì công ty mới phải duyệt lại. Đổi `name` thì không.
- **Hậu quả:** công ty đã xác thực đổi sang tên thương hiệu khác để mạo danh.

### BUG-26: Ứng viên thấy và nộp được vào job của công ty chưa xác thực
- **Vị trí:** `applicant_router.py:60-82` (`/apply/jobs`), `:404` (apply)
- **Mô tả:** API này không lọc `CompanyStatus.VERIFIED`, trong khi `/jobs/public/list` có lọc. Hai API cho kết quả không nhất quán.

### BUG-27: Cron hạ gói không hoạt động
- **Vị trí:** `main.py:43-56`
- **Mô tả:** Cron dùng các field `subscription_expires_at` và `subscription_tier`, không còn tồn tại, nên chạy mỗi đêm mà không làm gì.
- **Hướng sửa:** xoá đi, vì billing mới đã tự xử lý hết hạn khi đọc dữ liệu.

### BUG-28: Ai cũng upload được mọi loại file
- **Vị trí:** `upload_router.py:16`
- **Mô tả:** Mọi user đã đăng nhập đều upload được file bất kỳ (HTML, SVG, exe, …) lên Cloudinary của hệ thống.
- **Hướng sửa:** whitelist MIME type và đuôi file.

### BUG-29: Tải lên file KYC mới làm công ty đã xác thực về lại trạng thái chờ duyệt
- **Vị trí:** `upload_router.py:57-60`
- **Mô tả:** Công ty đã xác thực mà tải lên lại tài liệu KYC sẽ chuyển ngay về `PENDING_VERIFICATION`, nên **không đăng được job mới** cho tới khi admin duyệt lại. URL file cũng không được lưu vào công ty.

---

## ⚪ Thấp

| ID | Vị trí | Mô tả |
|---|---|---|
| BUG-30 | `applicant_router.py:491` | Thư viện CV chỉ trả về 10 CV, dù gói cao hơn có thể cho lưu nhiều hơn |
| BUG-31 | `application_schema.py:92` | `rejection_reason` được nhận từ request nhưng không bao giờ được lưu |
| BUG-32 | `applicant_router.py:554-565` | Xoá CV đang là mặc định thì không chọn CV khác làm mặc định, nên "ứng tuyển 1 chạm" báo lỗi |
| BUG-33 | `company_router.py:331`, `job_router.py:440`, `system_router.py:88` | Lượt xem tăng lên ở mọi request, kể cả F5 hoặc bot |
| BUG-34 | `system_router.py:30-51` | Báo cáo và ticket hỗ trợ không cần đăng nhập, không giới hạn tần suất. Khi ẩn danh thì `user_id` lấy theo request gửi lên |
| BUG-35 | Nhiều router | `ObjectId(...)` với ID sai định dạng gây lỗi 500 thay vì 400 |
| BUG-36 | DB | Không có unique index cho `users.email` và cặp (`job_id`, `applicant_user_id`), nên request gửi đồng thời có thể tạo bản ghi trùng |
| BUG-37 | `auth_service.py:6` | `verify_turnstile` có viết nhưng không được gọi ở đâu, nên captcha khi đăng nhập không có tác dụng |
| BUG-38 | `interview_router.py:44-45` | Email mời phỏng vấn dùng tên công ty và vị trí giữ chỗ ("Công ty của chúng tôi") |
| BUG-39 | `applicant_router.py:245-290` | Upload CV lên Cloudinary và gọi AI xong mới kiểm tra giới hạn lần hai, nên file bị bỏ lại trên Cloudinary nếu vượt giới hạn |

---

## Ghi chú
- Mình chưa rà chi tiết từng component giao diện FE (khoảng 34 nghìn dòng), nên có thể vẫn còn lỗi hiển thị hoặc trải nghiệm chưa được ghi ở đây.
- Mình cũng chưa rà kỹ `analytics_service.py`, `nlp_engine.py` và `vector_engine.py` (phần thuật toán chấm điểm).
- Nên viết test cho các lỗi mức Cao trở lên trước khi sửa, để tránh lỗi quay lại sau này.
