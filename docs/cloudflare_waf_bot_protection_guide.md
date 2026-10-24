# 🛡️ HƯỚNG DẪN CẤU HÌNH CLOUDFLARE WAF BẢO VỆ TOÀN BỘ WEBSITE CHỐNG SPAM BOT

Tài liệu này hướng dẫn chi tiết cách thiết lập **Cloudflare Web Application Firewall (WAF)** để xác thực và chặn bot tự động trên **toàn bộ trang web Verisem** ngay tại mạng Edge (CDN) trước khi request chạm vào server.

---

## 1. Yêu cầu Tiên quyết
* Tên miền website đã được trỏ NameServer về Cloudflare.
* Bản ghi DNS (A / CNAME) của website và API đã được **BẬT đám mây màu cam ☁️ (Proxied)**.

---

## 2. Cấu hình Quy tắc Xác thực Toàn trang (Custom WAF Rule)

### Bước 1: Mở mục thiết lập WAF
1. Đăng nhập vào [Cloudflare Dashboard](https://dash.cloudflare.com/).
2. Chọn tên miền website của bạn.
3. Ở menu bên trái, chọn **Security ➔ WAF ➔ Custom rules**.
4. Bấm nút **Create rule**.

### Bước 2: Thiết lập nội dung quy tắc
* **Rule name:** `Chặn Bot Toàn Trang (Protect Entire Site)`
* **Field / Operator / Value:** Bấm vào **"Edit expression"** và dán chính xác biểu thức sau:

```text
http.request.uri.path contains "/" and not cf.client.bot
```

> ⚠️ **Ý nghĩa cực kỳ quan trọng của `not cf.client.bot`:**
> Biểu thức này sẽ áp dụng kiểm tra bot cho **tất cả mọi URL trên trang web**, **NGOẠI TRỪ các Bot tìm kiếm chính thống** (như Googlebot, Bingbot, bộ cào thẻ link Facebook/Zalo). Nhờ đó, trang web được bảo vệ 100% trước spam bot mà **KHÔNG bị tụt thứ hạng SEO hay mất index trên Google**.

* **Choose action (Hành động):** Chọn **`Managed Challenge`** (hoặc `Interactive Challenge`).
  * *Managed Challenge:* Cloudflare sẽ tự động kiểm tra dấu hiệu trình duyệt trong nền (1-2s). Người dùng thật truy cập bình thường sẽ lướt mượt mà không phải click captcha. Chỉ khi phát hiện hành vi nghi vấn của bot, Cloudflare mới bật ô tick xác thực.
* Bấm **Deploy** để kích hoạt ngay lập tức.

---

## 3. Cấu hình Rate Limiting (Chống cào dữ liệu & Brute-force API)

Để ngăn chặn bot spam gọi liên tục vào các endpoint API:
1. Vào **Security ➔ WAF ➔ Rate limiting rules ➔ Create rule**.
2. **Rule name:** `Rate Limit API Requests`
3. **Expression:** `http.request.uri.path contains "/api/v1/"`
4. **Rate limit settings:**
   * Requests: `60` requests
   * Period: `1 minute`
   * Characteristics: `IP`
5. **Action:** `Block` (hoặc `Managed Challenge`) trong thời gian `10 minutes`.
6. Bấm **Deploy**.

---

## 4. Chế độ Khẩn cấp (Under Attack Mode)

Khi phát hiện website đang bị tấn công DDoS tầng 7 (hàng chục nghìn lượt truy cập bất thường làm nghẽn server):
* Tại trang chủ Domain trên Cloudflare Dashboard:
* Ở góc trên bên phải, gạt nút **"Under Attack Mode"** sang **ON**.
* Khi đó, 100% người truy cập sẽ thấy màn hình chờ 5 giây *"Checking if the site connection is secure..."* trước khi được chuyển tiếp vào trang web.
* Khi lưu lượng trở lại bình thường, gạt về **OFF**.
