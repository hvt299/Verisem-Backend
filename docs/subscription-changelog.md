# Thay đổi chức năng Đăng ký gói (Billing v2)

> Nhánh: `feat/theanh/subscription-test-tools` (BE commit `b793ec3`, FE commit `f9c1641`)
> Lý do thay đổi và thiết kế chi tiết: [subscription-redesign.md](subscription-redesign.md)

File này liệt kê **những gì đã khác so với trước** để review và test. Mỗi mục ghi rõ: trước đây thế nào, bây giờ thế nào.

---

## 1. Thay đổi người dùng nhìn thấy

### 1.1. Mua gói lẻ (nạp credit)
| | Trước | Bây giờ |
|---|---|---|
| Đang dùng Pro, mua gói lẻ | Bị chặn với thông báo "Không thể hạ cấp" | **Mua được** |
| Sau khi mua gói lẻ | Gói hiện tại bị **ghi đè** thành gói lẻ, mất gói Pro | Gói hiện tại **giữ nguyên**, chỉ cộng thêm credit |
| Đang dùng Free, mua gói lẻ | Gói chuyển thành gói lẻ, quyền lợi của gói Free bị sai | Vẫn là gói Free, chỉ cộng thêm credit |

### 1.2. Gói hết hạn
| | Trước | Bây giờ |
|---|---|---|
| Credit khi gói hết hạn | **Toàn bộ** credit về 0, kể cả credit mua lẻ | Chỉ credit của gói hết hạn. **Credit mua lẻ được giữ lại** |
| Gói của ứng viên | Không bao giờ hết hạn | Hết hạn đúng ngày, rồi tự về gói Free |

### 1.3. Gia hạn và nâng cấp
| | Trước | Bây giờ |
|---|---|---|
| Mua lại đúng gói đang dùng | Hạn tính lại từ hôm nay, **mất số ngày còn lại** | **Cộng dồn** vào hạn cũ (ví dụ còn 10 ngày, mua thêm 30 ngày thì được 40 ngày) |
| Nâng lên gói cao hơn | Ghi đè gói | Gói mới bắt đầu từ hôm nay. Credit của gói cũ vẫn dùng được tới khi gói cũ hết hạn |
| Hạ xuống gói thấp hơn khi gói hiện tại còn hạn | Báo lỗi bằng toast nhỏ ở dưới màn hình | Hiện **popup** gồm tên gói hiện tại, ngày hết hạn và tên gói muốn mua |

### 1.4. Thanh toán qua QR
| | Trước | Bây giờ |
|---|---|---|
| Nội dung chuyển khoản | `UPGRADE <id 24 ký tự> HR_PRO` | Mã đơn ngắn, ví dụ `CVR7K2M9QXA` |
| Ngân hàng tự bỏ ký tự `_` | Không kích hoạt được gói dù khách đã trả tiền | Không còn lỗi này, vì mã đơn chỉ gồm chữ và số |
| Đồng hồ 10 phút trong modal | Bị reset về 10:00 mỗi khi cuộn trang hoặc chuyển tab | Đếm theo giờ hết hạn của đơn trên server, không bị reset |
| Nhận biết đã thanh toán | So sánh xem credit có tăng không, nên gói 0 credit thì không bao giờ báo thành công | Kiểm tra trạng thái đơn hàng mỗi 5 giây |

### 1.5. Trang Billing (HR và ứng viên)
- **Chi tiết credit:** dưới tổng số credit có thêm các dòng như "120 credit theo gói · hết hạn 10/11/2026" hay "500 credit mua lẻ · không hết hạn".
- **Lịch sử đơn hàng** (mới): gồm thời gian, mã đơn, gói, số tiền và trạng thái (Đã thanh toán, Chờ thanh toán, Hết hạn, Thiếu tiền - chờ xử lý).
- **Sổ cái giao dịch:** nhãn mới gồm "Mua gói: …", "Admin cấp gói: …", "Hoàn credit: …", "Credit gói Miễn phí".

### 1.6. Hoàn credit khi AI lỗi (mới)
- **Sinh câu hỏi phỏng vấn AI:** nếu AI lỗi thì **hoàn lại toàn bộ credit** và báo "Credit đã được hoàn lại".
- **Chấm điểm CV hàng loạt:** **hoàn credit cho các CV xử lý lỗi**. Ví dụ chấm 10 CV mà lỗi 2 thì được hoàn credit của 2 CV đó.

### 1.7. Trang Admin › Gói cước
- **Nút "Cấp gói thủ công"** (mới): nhập email HR hoặc ứng viên, chọn gói, số ngày (để trống là theo chu kỳ của gói, nhập 0 là không hết hạn) và ghi chú. Thao tác này được ghi vào Audit Log.
- **Form sửa gói** có thêm 3 trường:
  - **Loại gói:** Thuê bao theo kỳ hoặc Gói lẻ.
  - **Số credit được cộng.**
  - **Hạn dùng credit:** chỉ áp dụng cho gói lẻ, để trống là không hết hạn.

### 1.8. Giả lập thanh toán (chỉ dùng ở môi trường dev)
- Modal QR có thêm nút **"[DEV] Giả lập thanh toán thành công"**. Bấm nút này là đơn được kích hoạt ngay, không cần chuyển khoản.
- Nút chỉ hiện khi bật biến môi trường (xem mục 4). **Trên production nút bị ẩn, và API trả về 404.**

---

## 2. Thay đổi API

### 2.1. API mới
| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/api/v1/subscriptions/orders` | Lịch sử đơn hàng của tài khoản (100 đơn gần nhất) |
| GET | `/api/v1/subscriptions/orders/{order_code}` | Trạng thái của một đơn hàng, dùng để FE kiểm tra định kỳ |
| POST | `/api/v1/subscriptions/dev/simulate-payment/{order_code}` | Giả lập thanh toán. Chỉ có khi `ENABLE_PAYMENT_SIMULATION=true` |
| POST | `/api/v1/admin/subscriptions/grant` | Admin cấp gói. Body gồm `email`, `plan_code`, `days?`, `note?` |

### 2.2. API thay đổi
| Endpoint | Thay đổi |
|---|---|
| `POST /subscriptions/checkout/{plan_code}` | Tạo đơn hàng. Response thêm `order_code`, `plan_code`, `expires_at`. `transfer_content` giờ chính là `order_code`. Gói giá 0 trả về 400 |
| `POST /subscriptions/webhook/sepay` | Viết lại hoàn toàn, xem mục 3.2 |
| `GET /subscriptions/my-plan` | Giữ nguyên các field cũ. Thêm `tier_level` và `credits: { total, breakdown[] }` |
| `GET /subscriptions/plans` | Mỗi gói có thêm `plan_type` (`subscription` hoặc `topup`) và `credits_granted` |
| `GET /subscriptions/transactions` | Đọc được cả dữ liệu cũ lẫn dữ liệu mới. `created_at` có múi giờ UTC |
| `GET /admin/subscriptions/plans` | Có thêm `plan_type` và `credits_granted` |
| `PATCH /admin/subscriptions/plans/{id}` | Nhận thêm `plan_type`, `credits_granted`, `credit_validity_days` |

### 2.3. Lỗi khi hạ cấp gói
Trước đây `detail` là một chuỗi. Bây giờ API vẫn trả HTTP 400 nhưng `detail` là object:
```json
{
  "code": "PLAN_DOWNGRADE_BLOCKED",
  "message": "Không thể hạ cấp (Downgrade) ...",
  "current_plan": "HR Pro",
  "current_period_end": "2026-11-10T14:07:43+00:00",
  "target_plan": "HR Growth"
}
```
Nếu có client nào khác đang đọc `detail` dạng chuỗi thì cần sửa theo.

---

## 3. Thay đổi bên trong (BE)

### 3.1. Dữ liệu

Billing v2 thêm **3 collection mới** và thêm field cho **2 collection có sẵn**. Mọi bản ghi đều gắn với một chủ sở hữu (owner):
- `owner_type = "company"`, `owner_id = company_id`: gói và credit dùng chung cho cả công ty (HR).
- `owner_type = "applicant"`, `owner_id = user_id`: gói và credit của từng ứng viên.

#### `orders` (mới): đơn hàng
Mỗi lần người dùng bấm thanh toán thì tạo 1 đơn.

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `order_code` | string | Mã đơn, ví dụ `CVR7K2M9QXA`, cũng là nội dung chuyển khoản. **Unique** |
| `owner_type`, `owner_id` | string | Người mua |
| `created_by` | string | User bấm mua |
| `plan_id` | string | Gói được mua |
| `plan_snapshot` | object | Bản chụp giá, loại gói, số credit và chu kỳ tại thời điểm mua |
| `amount` | int | Số tiền phải trả |
| `status` | string | `pending`, `paid`, `cancelled`, `expired` |
| `sepay_tx_id` | string \| null | Mã giao dịch SePay. **Unique**, dùng để chống xử lý trùng |
| `paid_amount`, `paid_at` | int, datetime | Số tiền thực nhận và thời điểm thanh toán |
| `payment_issue` | string \| null | Ví dụ `underpaid` (thiếu tiền) hoặc `cancelled_order`, cần xử lý tay |
| `created_at`, `expires_at` | datetime | Thời điểm tạo đơn và thời điểm QR hết hạn (15 phút). Tiền về muộn vẫn được xử lý |

**Index:** `order_code` (unique), `sepay_tx_id` (unique), `(owner_type, owner_id, created_at)`

#### `subscriptions` (mới): gói thuê bao
Lưu gói đang dùng và lịch sử các gói đã dùng.

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `owner_type`, `owner_id` | string | Chủ gói |
| `plan_id`, `plan_code` | string | Gói |
| `order_id` | string \| null | Đơn hàng tạo ra gói này (`null` nếu admin cấp hoặc được chuyển từ dữ liệu cũ) |
| `status` | string | `active`, `expired`, `replaced` (bị gói khác thay), `cancelled` |
| `period_start`, `period_end` | datetime | Thời hạn (`period_end = null` là không hết hạn) |
| `migrated` | bool | `true` nếu được tạo bởi script migration |
| `created_at`, `updated_at` | datetime | |

**Index:** mỗi owner **chỉ có tối đa 1 gói `active`** (partial unique index trên `(owner_type, owner_id)` khi `status = "active"`).
Không có gói active thì tự hiểu là đang dùng gói Free (`hr_free` / `app_free`), không cần tạo bản ghi cho gói Free.

#### `credit_grants` (mới): các khoản credit
Mỗi lần được cộng credit thì tạo một khoản riêng, có nguồn và hạn riêng.

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `owner_type`, `owner_id` | string | Chủ credit |
| `source` | string | `subscription` (theo gói), `topup` (mua lẻ), `admin` (được tặng), `free` (gói Free), `legacy` (chuyển từ dữ liệu cũ) |
| `source_ref` | string \| null | ID của subscription hoặc đơn hàng tạo ra khoản này |
| `amount_granted` | int | Số credit được cộng |
| `amount_remaining` | int | Số credit còn lại |
| `expires_at` | datetime \| null | Hạn dùng (`null` là không hết hạn) |
| `created_at` | datetime | |

**Index:** `(owner_type, owner_id, expires_at)`
**Số dư** = tổng `amount_remaining` của các khoản còn hạn. Khi trừ credit, khoản sắp hết hạn được trừ trước.

#### `subscription_plans` (thêm field)
| Field mới | Kiểu | Ý nghĩa |
|---|---|---|
| `plan_type` | string | `subscription` (thuê bao theo kỳ) hoặc `topup` (gói lẻ mua credit) |
| `credits_granted` | int | Số credit được cộng mỗi lần mua hoặc mỗi kỳ. Thay cho `features.monthly_ai_credits` / `features.ai_credits` |
| `credit_validity_days` | int \| null | Chỉ áp dụng cho gói lẻ: hạn dùng credit tính theo ngày (`null` là không hết hạn) |

Với gói chưa migrate (chưa có `plan_type`), code tự suy ra: `billing_cycle_days = 0` và giá > 0 thì là `topup`.

#### `quota_transactions` (thêm field): sổ cái
| Field mới | Ý nghĩa |
|---|---|
| `owner_type`, `owner_id` | Chủ của giao dịch |
| `actor_id` | Người hoặc hệ thống thực hiện (`sepay_system`, `system`, user_id, admin_id) |
| `delta` | Số credit thay đổi: số dương là cộng, số âm là trừ |
| `reason` | Ví dụ `PURCHASE_HR_PRO`, `ADMIN_GRANT_…`, `REFUND_…`, `AI_INTERVIEW_GEN`, `FREE_PLAN_CREDITS` |
| `grant_id`, `order_id` | Liên kết tới khoản credit và đơn hàng |

Các field cũ (`company_id`, `user_id`, `action_type`, `credit_cost`, `balance_after`) **vẫn được ghi song song**, để `BillingLedger` và dữ liệu cũ vẫn đọc được.

#### Field cũ không còn dùng
Các field `current_plan_id`, `current_period_start`, `current_period_end` và `credits_remaining` trên `companies` và `applicant_profiles` **không còn được đọc hay ghi**. Chúng vẫn được giữ trong DB để rollback, và có thể xoá sau khi billing v2 chạy ổn.

Toàn bộ index được tạo tự động khi app khởi động (`connect_to_mongo` trong `app/database/config.py`).

### 3.2. Webhook SePay
| | Trước | Bây giờ |
|---|---|---|
| Chưa cấu hình token | **Ai cũng gọi được** | Từ chối mọi request (fail closed) |
| SePay gửi lại cùng một giao dịch | Credit bị **cộng trùng** | Bị bỏ qua, nhận diện theo `id` / `referenceCode` |
| Field đọc nội dung chuyển khoản | `transactionContent` | `code`, `content`, `transactionContent`, `description` |
| Chuyển khoản thiếu tiền | Bỏ qua, không lưu lại | Đánh dấu đơn `payment_issue = "underpaid"` để xử lý tay |
| Nội dung trả về | `{"status": "success"}` | `{"success": true, "message": ...}` |

### 3.3. Trừ credit
- Mọi thao tác trừ credit chạy trong **MongoDB transaction**, nên nhiều request cùng lúc không làm số dư bị âm. Đã test với 20 request đồng thời.
- Credit sắp hết hạn được trừ trước, credit không hết hạn được trừ sau cùng.
- `require_tier`, `require_credits` và chức năng chấm điểm hàng loạt đều dùng chung `SubscriptionService`. Đã bỏ hàm `CompanyRepository.deduct_ai_credits`.

### 3.4. Tạo tài khoản và công ty
- Không còn ghi `current_plan_id` và `credits_remaining` vào tài khoản mới.
- Nếu gói Free có tặng credit thì tạo một khoản credit với `source = "free"`.

### 3.5. Thống kê Admin
- Biểu đồ phân bổ gói giờ đếm theo các `subscriptions` còn hiệu lực.
- Báo cáo PRO của công ty xét theo việc công ty có subscription còn hiệu lực hay không.

---

## 4. Biến môi trường

| Biến | Nơi | Production | Dev / local |
|---|---|---|---|
| `SEPAY_WEBHOOK_TOKEN` | BE | **Bắt buộc**, khớp với token cấu hình trên SePay | Bất kỳ |
| `ENABLE_PAYMENT_SIMULATION` | BE | **Không đặt** | `true` |
| `NEXT_PUBLIC_ENABLE_PAYMENT_SIMULATION` | FE | **Không đặt** | `true` |

---

## 5. Triển khai

1. Merge BE và FE.
2. Deploy BE, sau đó **chạy migration ngay**:
   ```bash
   python -m scripts.migrate_billing_v2           # chạy thử, không ghi gì
   python -m scripts.migrate_billing_v2 --apply   # ghi thật
   ```
   Script chuyển gói đang dùng và credit hiện có sang mô hình mới. Script idempotent, chạy lại không bị ghi trùng.
3. Deploy FE.
4. Kiểm tra `SEPAY_WEBHOOK_TOKEN` trên server có khớp với SePay không.

> ⚠️ Từ lúc deploy BE tới lúc chạy migration, các tài khoản trả phí sẽ hiện là gói Free.
> ⚠️ Khách đã quét QR theo **mẫu cũ** (`UPGRADE …`) ngay trước khi deploy thì giao dịch sẽ không tự kích hoạt. Cần rà lại lịch sử SePay và dùng "Cấp gói thủ công".

---

## 6. Checklist test

- [ ] Free mua Pro: gói thành Pro, credit được cộng, lịch sử đơn hàng hiện "Đã thanh toán"
- [ ] Đang dùng Pro mua gói lẻ: **vẫn là Pro**, credit tăng, chi tiết credit hiện 2 dòng
- [ ] Đang dùng Pro mua lại Pro: hạn được cộng thêm 30 ngày
- [ ] Đang dùng Pro mua gói tier thấp hơn: hiện popup "Chưa thể hạ cấp gói"
- [ ] Mở modal QR rồi cuộn trang hoặc chuyển tab: đồng hồ không bị reset
- [ ] Gọi webhook 2 lần với cùng `id`: credit chỉ được cộng 1 lần
- [ ] Gọi webhook không có token: trả về 401
- [ ] Chuyển khoản thiếu tiền: không kích hoạt, đơn hiện "Thiếu tiền - chờ xử lý"
- [ ] Admin cấp gói cho ứng viên qua email: ứng viên thấy gói mới, Audit Log có ghi lại
- [ ] Sinh câu hỏi phỏng vấn khi AI lỗi: credit được hoàn, sổ cái có dòng "Hoàn credit"
- [ ] Production: không thấy nút [DEV], và API `/dev/simulate-payment` trả về 404

---

## 7. Chưa làm / còn tồn đọng
- Webhook chưa nhận nội dung chuyển khoản theo mẫu cũ `UPGRADE …` (xem cảnh báo ở mục 5).
- Sinh câu hỏi phỏng vấn AI vẫn trừ credit khi câu hỏi đã có sẵn trong cache.
- Chưa có tính năng nào của ứng viên trừ credit, vì chưa tính năng nào được đặt giá.
- `HR_MEMBER` vẫn mua được gói cho công ty.
- Các lỗi liên quan khác xem tại [bug-report.md](bug-report.md): BUG-11, BUG-15, BUG-22.
