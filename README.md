# BotHocTap — trợ lý Telegram ôn bài chạy trên chính máy tính của bạn

Bot Telegram cá nhân: hỏi đáp trên tài liệu học (PDF, Word, PowerPoint, ghi chú…) bằng chỉ mục tìm kiếm chạy cục bộ,
tìm và gửi file, ghi nhớ hội thoại, giải bài tập thành conspect, hỏi NotebookLM, và (chỉ cho chủ bot) nhờ Claude
tìm file / chạy lệnh trên máy với nút **Duyệt** trên Telegram.

> Dự án cá nhân, giao diện tiếng Việt. Không có dữ liệu thật trong repo: mật khẩu, khóa API, tài liệu và chỉ mục đều nằm ngoài Git.

## Tính năng chính
- Hỏi đáp theo tài liệu (embedding cục bộ `BAAI/bge-m3`, trả lời bằng Gemini hoặc `/model claude`).
- `/find`, nút «Gửi», tải file lớn lên Google Drive (thư mục chỉ định).
- `/conspect <đề bài>`: giải thích tiếng Việt + conspect tiếng Nga dạng file `.md`.
- `/notebook`, `/nbadd`, `/nbsrc`, `/nbnew`: dùng NotebookLM qua `nlm`.
- `/agent`: Claude (`claude -p`) tìm file bằng lời; chủ bot có phiên liên tục có nhớ và có thể đề xuất lệnh PowerShell, **mỗi lệnh phải bấm ✅ Chạy**.
- `/memory`: bộ nhớ dài hạn, tự tóm tắt khi đầy.
- `/viec`: việc cần làm (file Markdown, mở được bằng Obsidian): hạn tự nhiên («thứ sáu tuần sau», «mùng 10»), tự chia Gấp / Quan trọng / Để sau, nhắc 9h sáng, hỏi lại tối, báo cáo tuần Chủ nhật, tích xong và sửa ngay trong Telegram, tự gắn `[[trang môn]]` (cấu hình `wikilink_mon.json`, xem file `.example`). Dán đề bài hoặc gửi ảnh/file kèm `/viec` để bot tự rút việc.
- `/no` hoặc gõ thẳng «Giang nợ 13k»: sổ nợ tạm (USD/RUB/VND, ghi chú sau dấu chấm), tạo việc trả/nhắc nợ.
- `/screen`, `/open`, `/status`, `/note` (chỉ chủ).
- Cập nhật hằng tuần (`bot/weekly.py`, Task Scheduler): lập chỉ mục file mới, báo cáo, nhắn Telegram.

## Cần chuẩn bị
| Thứ | Dùng để | Bắt buộc |
|---|---|---|
| Windows 10/11, Python 3.11+ | chạy bot | có |
| Token bot từ @BotFather, ID Telegram của bạn | bot + nhận diện chủ | có |
| Khóa Gemini API (miễn phí) | trả lời | có |
| GPU NVIDIA + torch CUDA | tăng tốc embedding (CPU vẫn chạy, chậm) | không |
| [Claude Code](https://claude.com/claude-code) đã đăng nhập | `/agent`, `/model claude`, cập nhật tuần | không |
| `nlm` (notebooklm-mcp-cli) đã `nlm login` | NotebookLM | không |
| Ollama + `qwen2.5vl` | OCR PDF scan | không |
| Google Cloud OAuth (`credentials.json`) | Drive (xem `HUONG_DAN_DRIVE.md`) | không |
| Microsoft Word | tự đổi `.doc` sang PDF khi đẩy lên NotebookLM | không |

## Cài trên máy mới
1. Cài Python, Git. Tải repo: `git clone <địa-chỉ-repo> BotHocTap` rồi `cd BotHocTap`.
2. Tạo môi trường và cài thư viện:
   ```
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
   Có GPU NVIDIA: cài torch CUDA từ https://pytorch.org (chọn bản CUDA phù hợp) **trước** bước `pip install -r`.
3. Chép `.env.example` thành `.env` và điền (token, ID, khóa Gemini, `COURSE_DIR`…). `.env` không bao giờ đưa lên Git.
4. Đặt mật khẩu cho người dùng khác: chạy `set_password.bat` (chủ bot không cần mật khẩu).
5. Lập chỉ mục tài liệu: chạy `index_course.bat` (lần đầu tải model bge-m3 ~2 GB, sau đó chạy offline).
6. Chạy bot: `run_bot.bat` (hoặc `.venv\Scripts\python.exe bot\tray.py` để có biểu tượng khay hệ thống).
7. (Tùy chọn) Drive: làm theo `HUONG_DAN_DRIVE.md`. NotebookLM: `nlm login`. Claude: `claude` rồi đăng nhập.
8. (Tùy chọn) Cập nhật hằng tuần: tạo tác vụ Task Scheduler chạy `.venv\Scripts\python.exe -X utf8 bot\weekly.py` thứ Hai 15:00.

## Mang dữ liệu cũ sang máy mới
Những thứ này **không** nằm trong Git; chép tay (USB/ổ mạng riêng tư) nếu muốn giữ nguyên:
- `.env`, `password.json` — bí mật, đừng gửi qua kênh công khai.
- `credentials.json` (Google Cloud). `drive_token.json` có thể bỏ, chạy `dang_nhap_drive.bat` đăng nhập lại.
- `index_local\` và `ocr_cache\` — chép để khỏi lập chỉ mục và OCR lại (nhớ giữ cùng đường dẫn tài liệu `COURSE_DIR`, nếu khác thì chạy lại `index_course.bat`).
- `memory\` — bộ nhớ của bot. `questions.jsonl`, `weekly_state.json` — nhật ký cho báo cáo tuần.
- Thư mục tài liệu (`COURSE_DIR`) và vault wiki (`WIKI_DIR`) nếu dùng.

## Bảo mật (đọc trước khi dùng `/agent`)
- Chỉ ID Telegram trong `MY_TELEGRAM_ID` là chủ. Người lạ không nhận được phản hồi.
- Lệnh trên máy chỉ chạy sau khi chủ bấm ✅ Chạy; lệnh chạy được mọi nơi, hãy đọc kỹ trước khi duyệt.
- Dùng `claude -p` bằng gói đăng ký của chính bạn là dùng cá nhân; không cho người khác dùng đường này.
- Giữ `.env`, `password.json`, `credentials.json`, `drive_token.json` ngoài Git (đã nằm trong `.gitignore`).
