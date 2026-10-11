# Thiết kế lại luồng Đăng ký gói & Credit

> Trạng thái: **Đã triển khai giai đoạn 0–2 (+ một phần giai đoạn 3) – cần review**. Xem mục 10.
> Phạm vi: Backend (`CV-Ranking-Backend`) + phần Billing của Frontend (`CV-Ranking-Web`)

## 1. Bối cảnh

Hệ thống bán 3 loại sản phẩm:

| Loại | Đối tượng | Bản chất |
|---|---|---|
| Gói HR | Cả công ty dùng chung | Thuê bao theo kỳ (tháng/năm): mở khóa tính năng + tặng credit mỗi kỳ |
| Gói Ứng viên | Từng ứng viên | Thuê bao theo kỳ: mở khóa tính năng + tặng credit mỗi kỳ |
| Gói lẻ (Top-up) | HR hoặc Ứng viên | Mua credit một lần để dùng các tính năng AI (sinh câu hỏi phỏng vấn, chấm điểm CV, …) |

Hiện tại cả 3 loại đang dùng chung một cách lưu trữ, dẫn đến nhiều lỗi về tiền và quyền lợi của khách hàng.

## 2. Hiện trạng

### 2.1. Dữ liệu

Toàn bộ trạng thái gói nằm trực tiếp trên `companies` / `applicant_profiles`:

```
current_plan_id, current_period_start, current_period_end, credits_remaining
```

- Không có bảng **đơn hàng / thanh toán**. Webhook SePay nhận tiền là cộng thẳng.
- Không có bảng **thuê bao**. Chỉ biết gói hiện tại, không có lịch sử.
- Credit là **một con số duy nhất**. Credit của gói và credit mua lẻ bị cộng chung, không biết nguồn và hạn của từng phần.
- `quota_transactions` chỉ là log ghi *sau khi* cộng/trừ, không phải nguồn sự thật. Log và số dư có thể lệch nhau.
- Gói lẻ được nhận diện gián tiếp qua `billing_cycle_days == 0 && current_price > 0`.

### 2.2. Lỗi đang tồn tại

| # | Lỗi | Vị trí | Hậu quả |
|---|---|---|---|
| 1 | Mua gói lẻ ghi đè `current_plan_id` và đặt `current_period_end = None` | `subscription_router.py` – `sepay_webhook` | Đang dùng gói Pro, mua thêm credit thì **mất gói Pro** |
| 2 | Kiểm tra hạ cấp so `tier_level` cả với gói lẻ | `subscription_router.py` – `create_checkout_session` | **Không mua được gói lẻ** khi gói chính còn hạn |
| 3 | Hết hạn gói thì `credits_remaining = 0` | `middleware/subscription.py` | **Mất cả credit mua lẻ** đã trả tiền |
| 4 | Nội dung CK `UPGRADE <id> HR_PRO`. Nhiều ngân hàng bỏ ký tự `_` | `sepay_webhook` (regex) | Khách đã trả tiền nhưng **gói không được kích hoạt** |
| 5 | Không lưu mã giao dịch SePay, trả về `{"status": "success"}` thay vì `{"success": true}` theo tài liệu SePay (cần xác nhận lại) | `sepay_webhook` | SePay gửi lại webhook thì **credit bị cộng trùng** |
| 6 | `SEPAY_WEBHOOK_TOKEN` rỗng thì webhook không xác thực | `sepay_webhook` | Ai cũng có thể gọi API để tự nâng cấp miễn phí |
| 7 | Gia hạn cùng gói đặt `period_start = now` | `sepay_webhook` | Mất số ngày còn lại của kỳ cũ |
| 8 | Logic hết hạn chỉ có cho công ty, và chỉ chạy khi gọi route có `require_tier`/`require_credits` | `middleware/subscription.py` | Gói ứng viên không bao giờ hết hạn |
| 9 | Không tìm thấy chỗ nào trừ `credits_remaining` của ứng viên | – | Credit ứng viên hiện không có tác dụng |
| 10 | Code HR và ứng viên bị lặp thành hai nhánh `if hr / elif applicant` ở nhiều nơi | router, middleware, auth_service | Khó bảo trì, sửa chỗ này quên chỗ kia |

Frontend (`components/billing/CheckoutModal.tsx`):

- Đồng hồ 10 phút bị reset mỗi khi component cha render lại, do effect phụ thuộc vào `onClose` truyền dạng inline. Ở trang `/pricing` chỉ cần cuộn trang là reset.
- Phát hiện thanh toán thành công bằng cách so sánh "credit tăng lên". Gói 0 credit sẽ không bao giờ báo thành công.

## 3. Mục tiêu

1. Tách rõ **thuê bao** (quyền lợi theo kỳ) và **credit** (số dư tiêu hao).
2. Mỗi lần thanh toán là một **đơn hàng** có mã riêng, xử lý **idempotent**.
3. Credit có **nguồn và hạn riêng**. Hết hạn gói không ảnh hưởng credit mua lẻ.
4. HR và ứng viên dùng **chung một logic**, chỉ khác `owner_type`.
5. Số dư có thể đối soát được với sổ cái.

## 4. Thiết kế đề xuất

### 4.1. Khái niệm "Owner"

Mọi bản ghi gói/credit đều gắn với một owner:

```
owner_type: "company" | "applicant"
owner_id  : company_id  (HR)  |  user_id  (ứng viên)
```

### 4.2. `subscription_plans` (sửa)

Thêm field `plan_type` để không phải đoán loại gói từ giá và chu kỳ:

```jsonc
{
  "plan_code": "hr_pro_monthly",
  "plan_type": "subscription",       // "subscription" | "topup"   ← MỚI
  "target_audience": "hr",           // "hr" | "applicant"
  "tier_level": 2,                   // chỉ có ý nghĩa với subscription
  "current_price": 499000,
  "billing_cycle_days": 30,          // subscription: 30/365 ; topup: không dùng
  "credits_granted": 500,            // ← MỚI, gộp monthly_ai_credits / ai_credits
  "credit_validity_days": null,      // ← MỚI, chỉ cho topup: null = không hết hạn
  "features": { ... },               // giữ nguyên, chỉ dùng cho subscription
  "is_active": true
}
```

### 4.3. `orders` (mới)

Mỗi lần bấm "Thanh toán" tạo một đơn.

```jsonc
{
  "_id": ObjectId,
  "order_code": "CVR7K2M9QXA",       // unique, chỉ gồm A-Z0-9 → an toàn với mọi ngân hàng
  "owner_type": "company",
  "owner_id": "...",
  "created_by": "<user_id>",
  "plan_id": "...",
  "plan_snapshot": {                 // chụp lại giá & quyền lợi tại thời điểm mua
    "plan_code": "...", "plan_type": "...", "price": 499000,
    "billing_cycle_days": 30, "credits_granted": 500, "credit_validity_days": null
  },
  "amount": 499000,
  "status": "pending",               // pending | paid | cancelled | expired
  "sepay_tx_id": null,               // unique (sparse) → chống xử lý trùng
  "paid_amount": null,
  "paid_at": null,
  "created_at": ISODate,
  "expires_at": ISODate              // chỉ để UI ẩn QR; tiền về muộn vẫn được xử lý
}
```

Index: `order_code` unique, `sepay_tx_id` unique sparse, `(owner_type, owner_id, created_at)`.

### 4.4. `subscriptions` (mới)

```jsonc
{
  "_id": ObjectId,
  "owner_type": "company",
  "owner_id": "...",
  "plan_id": "...",
  "order_id": "...",                 // null với gói free / admin cấp
  "status": "active",                // active | expired | replaced | cancelled
  "period_start": ISODate,
  "period_end": ISODate,
  "created_at": ISODate
}
```

- Mỗi owner có tối đa **1 subscription `active`**. Đảm bảo bằng partial unique index trên `(owner_type, owner_id)` với `status = "active"`.
- **Không có subscription active thì dùng gói free** (`hr_free` / `app_free`). Không cần tạo bản ghi cho gói free.
- Quy tắc khi mua:

  | Trường hợp | Xử lý |
  |---|---|
  | Chưa có gói / gói đã hết hạn | Tạo mới, `period_start = now` |
  | **Gia hạn** cùng gói | Kéo dài `period_end += cycle` (cộng dồn từ `period_end` cũ) |
  | **Nâng cấp** (tier cao hơn) | Gói cũ `replaced`. Tạo gói mới, `period_start = now` |
  | **Hạ cấp** khi gói cũ còn hạn | Chặn (giữ như hiện tại), xem *Câu hỏi mở #2* |

### 4.5. `credit_grants` (mới): các "ví" credit

Mỗi lần được cộng credit thì tạo một grant riêng, có hạn riêng.

```jsonc
{
  "_id": ObjectId,
  "owner_type": "company",
  "owner_id": "...",
  "source": "subscription",          // subscription | topup | admin | free | legacy
  "source_ref": "<subscription_id | order_id>",
  "amount_granted": 500,
  "amount_remaining": 500,
  "expires_at": ISODate | null,      // subscription: = period_end ; topup: theo credit_validity_days
  "created_at": ISODate
}
```

- **Số dư khả dụng** = tổng `amount_remaining` của các grant còn hạn (`expires_at` null hoặc > now).
- **Trừ credit**: lấy grant **sắp hết hạn nhất trước** (`expires_at` tăng dần, null xếp cuối), tức là dùng credit của gói trước rồi mới tới credit mua lẻ.
- **Hết hạn** chỉ là grant bị bỏ qua khi tính số dư. Không cần job xoá về 0, và không bao giờ đụng vào credit mua lẻ.

### 4.6. `quota_transactions` (sửa): sổ cái

Giữ collection, chuẩn hoá lại để đối soát được:

```jsonc
{
  "owner_type": "company", "owner_id": "...", "user_id": "...",
  "delta": -5,                       // + cộng, - trừ
  "reason": "AI_INTERVIEW_GEN",      // hoặc PURCHASE, REFUND, EXPIRE, ADMIN_ADJUST
  "grant_id": "...", "order_id": null,
  "balance_after": 495,
  "created_at": ISODate
}
```

Khi gọi AI thất bại sau khi đã trừ credit thì ghi một dòng `REFUND` và cộng trả vào grant cũ.

### 4.7. Tính nguyên tử khi trừ credit

Một lần trừ có thể chạm nhiều grant, ví dụ cần 10 mà grant A chỉ còn 3 thì phải lấy thêm 7 từ grant B. Có 2 lựa chọn:

- **(A) MongoDB transaction** (`motor` `start_session` + `with_transaction`): đúng và gọn, nhưng **cần MongoDB replica set** (Atlas có sẵn; local cần chạy `--replSet`).
- **(B) Không dùng transaction**: trừ từng grant bằng `update_one({amount_remaining: {$gte: x}}, {$inc: -x})`, nếu thất bại giữa chừng thì hoàn lại các bước đã trừ.

Đề xuất **(A)**, xem *Câu hỏi mở #1*.

## 5. Luồng xử lý

### 5.1. Checkout

```
FE  POST /api/v1/subscriptions/checkout/{plan_code}
BE  1. Kiểm tra plan active, đúng target_audience, đúng quyền người mua
    2. Nếu subscription và là hạ cấp khi gói cũ còn hạn → 400
       (topup: bỏ qua bước này)
    3. Tạo order (status=pending, order_code ngẫu nhiên)
    4. Trả về { order_code, amount, qr_url, bank info, expires_at }
       Nội dung CK = order_code  (VD: "CVR7K2M9QXA")
```

### 5.2. Webhook SePay

```
1. Bắt buộc có SEPAY_WEBHOOK_TOKEN. Không cấu hình thì từ chối hết (fail closed)
2. Bỏ qua nếu transferType != "in"
3. Tìm order_code bằng regex  CVR[A-Z0-9]{8}  trong transactionContent
4. Không thấy order → log để đối soát thủ công, trả {"success": true}
5. Đã có order khác cùng sepay_tx_id → trả {"success": true} (idempotent)
6. Order đã paid → trả {"success": true}
7. paid_amount < amount → đánh dấu cần xử lý tay, không kích hoạt
8. Trong một transaction:
     - order.status = paid, ghi sepay_tx_id, paid_at, paid_amount
     - subscription: tạo / gia hạn / nâng cấp theo bảng 4.4
                     + tạo credit_grant(source=subscription, expires_at=period_end)
     - topup:        tạo credit_grant(source=topup)
     - ghi quota_transactions (reason=PURCHASE)
9. Trả {"success": true}  ← đúng định dạng SePay yêu cầu
```

### 5.3. Kiểm tra quyền & trừ credit

Gộp `middleware/subscription.py` và `get_applicant_plan_features` thành một service chung:

```python
get_active_subscription(owner) -> subscription | None   # tự đánh dấu expired nếu quá hạn
get_features(owner)            -> dict                    # từ subscription active, hoặc gói free
get_balance(owner)             -> int
consume_credits(owner, user_id, cost, reason) -> bool     # 4.5 + 4.7
refund_credits(...)
```

`require_tier` / `require_credits` chỉ cần gọi các hàm trên, dùng được cho cả HR và ứng viên.

### 5.4. Frontend

- `CheckoutModal` poll `GET /api/v1/subscriptions/orders/{order_code}` cho đến khi `status == "paid"`, thay vì so sánh credit.
- Sửa timer: đưa `onClose` vào ref, hoặc bọc bằng `useCallback` ở component cha, để không bị reset.
- `GET /my-plan` trả thêm phần chi tiết credit:

```jsonc
{
  "plan": { "name": "...", "plan_code": "...", "period_end": "..." },
  "credits": {
    "total": 620,
    "breakdown": [
      { "source": "subscription", "remaining": 120, "expires_at": "2026-11-11" },
      { "source": "topup",        "remaining": 500, "expires_at": null }
    ]
  }
}
```

## 6. API thay đổi

| Method | Endpoint | Thay đổi |
|---|---|---|
| POST | `/subscriptions/checkout/{plan_code}` | Tạo `order`, trả thêm `order_code`, `expires_at` |
| GET | `/subscriptions/orders/{order_code}` | **Mới**: FE dùng để poll trạng thái |
| GET | `/subscriptions/orders` | **Mới**: lịch sử đơn hàng của owner |
| POST | `/subscriptions/webhook/sepay` | Viết lại theo 5.2 |
| GET | `/subscriptions/my-plan` | Thêm `credits.breakdown` |
| GET | `/subscriptions/transactions` | Đọc theo `owner_type/owner_id` |
| POST | `/subscriptions/dev/simulate-payment/{order_code}` | **Mới**: giả lập thanh toán, chỉ bật khi `ENABLE_PAYMENT_SIMULATION=true` |
| POST | `/admin/subscriptions/grant` | **Mới**: admin cấp gói thủ công theo email |

## 7. Migration dữ liệu cũ

Viết script một lần chạy trong `scripts/`:

1. Với mỗi `company` / `applicant_profile`:
   - Có `current_plan_id` khác gói free và `current_period_end > now` thì tạo `subscription` active (`order_id = null`).
   - Có `credits_remaining > 0` thì tạo một `credit_grant` với `source = "legacy"`, `expires_at = current_period_end` (hoặc `null` nếu không có).
2. Cập nhật `plan_type` và `credits_granted` cho toàn bộ `subscription_plans`.
3. Giữ các field cũ trong một phiên bản để rollback được, sau đó mới xoá.

## 8. Kế hoạch triển khai

| Giai đoạn | Nội dung | Ghi chú |
|---|---|---|
| 0 – Hotfix | Lỗi #1, #2, #3, #6 trên code hiện tại + sửa timer FE | Chạy được ngay, chưa đổi schema |
| 1 | Thêm `orders` + viết lại checkout/webhook (lỗi #4, #5) | FE đổi sang poll theo `order_code` |
| 2 | Thêm `subscriptions` + `credit_grants`, service chung, migration | Bỏ dần các field cũ |
| 3 | Áp dụng trừ credit cho ứng viên, refund khi AI lỗi, trang lịch sử đơn hàng | |

## 9. Câu hỏi mở (cần thống nhất)

1. **Mongo transaction**: môi trường deploy có replica set không? Nếu không thì dùng phương án (B) ở mục 4.7.
2. **Hạ cấp**: tiếp tục chặn, hay cho phép *lên lịch* để gói mới bắt đầu khi gói cũ hết hạn?
3. **Nâng cấp giữa kỳ**: có quy đổi (prorate) số ngày còn lại của gói cũ không, hay bỏ luôn?
4. **Credit của gói** khi hết kỳ: mất hẳn (đề xuất), hay cho cộng dồn sang kỳ sau?
5. **Credit mua lẻ** có hạn không? Ví dụ 12 tháng, hoặc `null` là vĩnh viễn.
6. **Quyền mua cho công ty**: chỉ `HR_OWNER`, hay cả `HR_MEMBER`?
7. **Chuyển khoản thiếu/thừa tiền**: xử lý tay qua trang admin, hay tự hoàn/ghi có?

## 10. Ghi chú triển khai

### Đã làm
- **Giai đoạn 0–2**: `orders`, `subscriptions`, `credit_grants` + `SubscriptionService` dùng chung (`app/services/domain/subscription_service.py`). Checkout, webhook, `my-plan`, `require_tier`, `require_credits`, analytics, đăng ký tài khoản đều đã chuyển sang dùng service.
- **Transaction**: dùng phương án (A), MongoDB transaction (Atlas là replica set).
- **Webhook SePay**: đọc mã đơn từ các field `code`, `content`, `transactionContent`, `description`. Chống trùng theo `id` / `referenceCode`. Luôn trả `{"success": true}`. Chưa cấu hình `SEPAY_WEBHOOK_TOKEN` thì từ chối toàn bộ.
- **Giai đoạn 3 (một phần)**: hoàn credit khi sinh câu hỏi phỏng vấn AI thất bại, và hoàn phần credit của các CV lỗi khi chấm điểm hàng loạt. API + UI lịch sử đơn hàng.
- **Công cụ test**: nút "[DEV] Giả lập thanh toán" trong CheckoutModal, và chức năng "Cấp gói thủ công" trong trang Admin › Gói cước.
- **Câu hỏi mở** đang theo đề xuất mặc định: chặn hạ cấp, không prorate, credit gói hết theo kỳ, credit mua lẻ không hết hạn (trừ khi gói có `credit_validity_days`), `HR_MEMBER` vẫn được mua, chuyển khoản thiếu tiền thì đánh dấu `payment_issue = "underpaid"` để xử lý tay.

### Khác với thiết kế ban đầu
- Thêm `source = "free"` cho credit tặng khi tạo tài khoản / công ty mới.
- `/my-plan` vẫn giữ các key phẳng cũ (`current_plan_code`, `credits_remaining`, `period_end`, …) để không phải sửa các component FE đang dùng. Chỉ thêm `credits.breakdown`.
- `quota_transactions` ghi cả field mới (`owner_type`, `owner_id`, `delta`, `reason`, …) lẫn field cũ (`company_id`, `user_id`, `action_type`, `credit_cost`) để `BillingLedger` và dữ liệu cũ vẫn đọc được.

### Chưa làm
- **Trừ credit cho ứng viên**: hiện chưa có tính năng nào của ứng viên được cấu hình giá trong `action_costs`. Khi cần, chỉ việc gọi `SubscriptionService.consume_credits(OWNER_APPLICANT, ...)`.
- **Xoá các field cũ** trên `companies` / `applicant_profiles`: giữ lại để rollback, xoá sau khi chạy ổn.
- Endpoint `GET /applications/{id}/ai-interview` vẫn trừ credit cả khi trả về câu hỏi đã cache. Cần thống nhất xem có nên miễn phí trường hợp này không.

### Biến môi trường
| Biến | Nơi | Ý nghĩa |
|---|---|---|
| `SEPAY_WEBHOOK_TOKEN` | BE | **Bắt buộc** để webhook hoạt động |
| `ENABLE_PAYMENT_SIMULATION` | BE | `true` để bật API giả lập thanh toán. **Không bật trên production** |
| `NEXT_PUBLIC_ENABLE_PAYMENT_SIMULATION` | FE | `true` để hiện nút giả lập trong CheckoutModal |

### Triển khai lên môi trường thật
1. Deploy BE (app tự tạo index cho 3 collection mới khi khởi động).
2. Chạy thử migration: `python -m scripts.migrate_billing_v2` và đọc kỹ phần tổng kết.
3. Chạy thật: `python -m scripts.migrate_billing_v2 --apply`. Script idempotent, chạy lại không bị ghi trùng.
4. Deploy FE.

Lưu ý: từ lúc deploy BE đến lúc chạy migration, các tài khoản đang dùng gói trả phí sẽ tạm thời hiện là gói Free. Nên chạy migration ngay sau khi deploy.
