# Hướng dẫn nối bot với Google Drive (làm một lần, khoảng 10 phút)

Kết quả: sau khi `/find`, bấm nút «☁ n» thì file (kể cả file trên 50 MB mà Telegram không gửi được) được tải lên Drive của bạn, thư mục **BotHocTap**, bot trả lại đường link. Chỉ chủ bot dùng được. Bot chỉ thấy các file do chính nó tải lên (quyền `drive.file`), không đọc được phần còn lại của Drive.

## Phần 1. Tạo thông tin đăng nhập trên Google Cloud
1. Mở https://console.cloud.google.com và đăng nhập bằng tài khoản Google bạn muốn lưu file.
2. Thanh trên cùng, bấm ô chọn dự án → **Dự án mới** (New project) → đặt tên `BotHocTap` → **Tạo**. Chọn dự án vừa tạo.
3. Menu trái: **APIs & Services → Library**. Gõ `Google Drive API`, bấm vào kết quả, bấm **Enable**.
4. Menu trái: **APIs & Services → OAuth consent screen** (hoặc «Google Auth platform»). Bấm **Get started**:
   - App name: `BotHocTap`; User support email: email của bạn → Next.
   - Audience: chọn **External** → Next.
   - Contact email: email của bạn → Next → đồng ý → **Create**.
5. Vào mục **Audience**, **KHÔNG bấm Publish app** (nút này bị mờ nếu chưa có URL trang chủ và chính sách bảo mật; app cá nhân không cần). Giữ trạng thái **Testing**, kéo xuống **Test users → Add users** → nhập đúng email Google bạn dùng để lưu file → **Save**. Thiếu bước này Google sẽ chặn đăng nhập.
   - Đánh đổi: ở chế độ Testing, Google có thể hủy đăng nhập sau khoảng 7 ngày. Khi bot báo «Cần đăng nhập Google lại», bấm đúp `dang_nhap_drive.bat` (30 giây). ⚠ Chưa kiểm chứng riêng cho quyền `drive.file`.
   - Quyền `drive.file` không thuộc nhóm nhạy cảm nên thường không cần Google duyệt; lúc đăng nhập sẽ có màn «Google hasn't verified this app» → bấm **Advanced → Go to BotHocTap (unsafe)**. Đây là app của chính bạn nên bình thường.
6. Mục **Data Access** → **Add or remove scopes** → tìm và tick `.../auth/drive` (dòng «See, edit, create, and delete all of your Google Drive files») → **Update** → **Save**. (Cần quyền đầy đủ này để ghi vào thư mục có sẵn; bot chỉ tải lên, không đọc/xóa. Cập nhật 04/11: trước đó là `drive.file`.)
   - Muốn gửi vào một thư mục cụ thể: thêm vào `.env` dòng `DRIVE_FOLDER_ID=<id>` (id là đoạn sau `/folders/` trong link thư mục). Tài khoản đăng nhập phải có quyền chỉnh sửa thư mục đó. Không thêm dòng này thì bot tạo thư mục «BotHocTap».
7. Mục **Clients** (hoặc APIs & Services → Credentials) → **Create client** (Create credentials → OAuth client ID):
   - Application type: **Desktop app**; Name: `BotHocTap` → **Create**.
   - Bấm **Download JSON** (biểu tượng tải xuống).
8. Đổi tên file vừa tải thành **`credentials.json`** và chép vào thư mục của bot (cùng chỗ với `run_bot.bat`).
   - Không gửi file này cho ai, không đưa lên GitHub (`.gitignore` đã chặn `.env`; nếu sau này đẩy public, nhớ chặn cả `credentials.json` và `drive_token.json`).

## Phần 2. Đăng nhập một lần
1. Chạy `dang_nhap_drive.bat` (bấm đúp).
2. Trình duyệt mở ra: chọn tài khoản Google → nếu có cảnh báo chưa xác minh thì **Advanced → Go to BotHocTap** → **Continue/Allow**.
3. Cửa sổ đen báo «Đã đăng nhập Google Drive xong». Thư mục của bot có thêm `drive_token.json`.

## Phần 3. Dùng
Khởi động lại bot (thoát khay hệ thống, mở `BotHocTap.lnk`). Trên Telegram: `/find <từ khóa>` → bấm «☁ n» ở hàng nút dưới. Nếu thấy «Cần đăng nhập Google lại», chạy lại `dang_nhap_drive.bat`.
