# BotHocTap

Tiếng Việt · [English](README.md)

Trợ lý Telegram cá nhân chạy **ngay trên PC của bạn**. Bot trả lời câu hỏi về tài liệu môn học, tìm và gửi file, quản lý việc cần làm, và (sau khi nhập mật khẩu) để Claude đọc, sửa file và đề xuất lệnh trên máy tính, tất cả từ điện thoại, với lượng token Claude ít nhất có thể.

Ban đầu chỉ là bot ôn bài (RAG trên ghi chú bài giảng), sau lớn dần thành một trợ lý nhỏ. Bot thiết kế cho **một chủ**; người khác chỉ dùng được phần học tập.

> Tình trạng: dự án cá nhân, tác giả dùng hằng ngày. Phần làm ngày 05/11/2026 (chế độ Claude, chọn phiên, tìm file cả ổ, menu mới) tác giả đã thử trên Telegram thật; nút «Thêm file» của notebook mới hơn nên mới thử bằng script.

## Mục tiêu thiết kế

1. **Ít token Claude.** Mặc định Gemini (gói miễn phí) trả lời; mô hình cục bộ lo nhúng chữ và OCR; Claude chỉ chạy khi bạn chủ động vào chế độ Claude, trong việc cập nhật wiki hằng tuần, và trong `/capnhat`.
2. **Chính xác.** Câu trả lời dựa trên các đoạn lấy từ chính file của bạn, có nguồn và một dòng cho biết độ khớp.
3. **Làm được việc trên PC mà vẫn an toàn.** Điện thoại là mắt xích yếu nhất, nên chế độ mạnh cần mật khẩu, lệnh cần bấm nút, file bí mật bị chặn.
4. **Chạy được khi không còn Claude.** Hết gói Claude thì bot vẫn chạy (Gemini + chỉ mục cục bộ + file dữ liệu cục bộ).

## Hoạt động ra sao

```
Telegram ──► bot (python-telegram-bot, polling, chạy ở khay hệ thống trên PC)
              │
              ├─ đăng nhập / kiểm tra chủ ───── người lạ: im lặng
              ├─ đang ở chế độ nào? (xét TRƯỚC mọi luật đoán ý)
              │     chờ mật khẩu → phiên /capnhat → chế độ Claude → chế độ /notebook → tham số của nút «✍»
              ├─ luật câu tự nhiên: nợ («Giang nợ 13k»), việc, «tìm cho tôi file …»
              └─ còn lại: hỏi đáp (RAG)
                    câu hỏi ─► chỉ mục cục bộ (bge-m3, GPU) ─► các đoạn gần nhất
                            ─► Gemini viết câu trả lời chỉ từ các đoạn đó
                            ─► trả lời + «🔎 N đoạn, file gần nhất, độ khớp cao/vừa/thấp»
```

### Hỏi đáp (RAG)
`index_course.bat` cắt file môn học (PDF, DOCX, PPTX, văn bản, mã; PDF scan qua OCR) thành các đoạn và nhúng cục bộ bằng BAAI/bge-m3 vào `index_local/`. Wiki Obsidian cũng được lập chỉ mục. Câu hỏi được tìm đồng thời theo nghĩa (nhúng chữ) và theo từ khóa (BM25, không phân biệt dấu nên mã như «stk 03» vẫn khớp), hai bảng xếp hạng được trộn lại, trang wiki được cắt theo đề mục, có thể thêm một trang liên kết, 10 đoạn tốt nhất gửi cho Gemini (câu hỏi lặp lại được trả lời tức thì từ bộ nhớ đệm cục bộ, có nút «Hỏi lại cho mới»), Gemini chỉ dựa vào các đoạn đó để trả lời và nêu file, trang. Mỗi câu trả lời có một dòng giải thích để bạn tự đánh giá việc tìm có tốt không.

### Tìm và mở file
`kfind.py` giữ **chỉ mục tên file** trong bộ nhớ (dựng ở luồng nền) cho thư mục môn học và, với chủ, cả ổ đĩa. Tìm không phân biệt hoa thường và dấu («tu duy he thong» ra «tư duy hệ thống»). Không khớp đúng thì gợi ý tên gần giống. File bí mật (`.env`, `password.json`, token, khóa) không bao giờ hiện; người đăng nhập thường chỉ thấy thư mục môn học. `/open` từ chối các loại file chạy được.

### Chế độ Claude (chỉ chủ)
`/model claude` nối bot vào phiên Claude Code đã lưu mới nhất của dự án; `/agent` liệt kê mọi phiên trên máy (phiên ngoài ổ của bot chỉ hiện tên, không nối được) hoặc mở phiên mới. Bạn nhập **mật khẩu mỗi lần vào**; tin chứa mật khẩu bị xóa. Trong chế độ này mọi tin nhắn thường gửi vào phiên đó qua `claude -p --resume`. Claude có Read/Glob/Grep/Edit/Write trên ổ nhưng **không có công cụ chạy lệnh**: lệnh chỉ được đề xuất bằng dòng `CHẠY:`, bot hiện kèm nút ✅ Chạy / ❌ Hủy. Đọc file bí mật và sửa file dữ liệu đóng băng của bot bị chặn bằng luật quyền. Chế độ tự thoát sau 30 phút không nhắn.

Lưu ý: gõ ở VS Code và Telegram trên *cùng một* phiên cùng lúc sẽ làm lịch sử lệch nhau; và mỗi tin nhắn gửi lại toàn bộ lịch sử phiên nên phiên dài tốn nhiều token (nên nén trước).

### NotebookLM
`/notebook` chọn một notebook; sau đó mọi tin thường được gửi **nguyên văn** vào khung chat của notebook đó (qua công cụ `nlm`), nên bạn đối chiếu được với giao diện web. Các nút dưới khung chat cho xem nguồn của notebook, thêm file (gõ tên hoặc gửi file từ điện thoại) hoặc thoát chế độ.

### Các phần khác
| Phần | Làm gì |
|---|---|
| `/viec` (`viec.py`) | Việc cần làm lưu thành file Markdown trong wiki; nhãn gấp/quan trọng theo hạn, nhắc 9:00, báo cáo tuần; dán đề (chữ, ảnh, file) thì Gemini rút việc. |
| sổ nợ (`congno.py`) | Sổ nợ nói tự nhiên («Giang nợ 13k», «Giang trả 5k»), JSON cục bộ, cố ý không ghi vào wiki hay Git. |
| `/conspect` (`conspect.py`) | Giải thích + conspect tiếng Nga từ đề bài và sách đã lập chỉ mục. |
| `/capnhat` | Một phiên: Claude nạp bài trong inbox wiki, kiểm tra wiki mỗi 10 nguồn, **hỏi bạn ngay trong chat và nhớ câu trả lời**, bạn bấm «Xong» để lưu và lập lại chỉ mục. |
| `weekly.py` | Việc thứ Hai 15:00 (Task Scheduler): nạp file môn mới vào wiki, tổng hợp câu hỏi chưa trả lời được. |
| `memory.py` | Bộ nhớ dài hạn các câu hỏi-đáp của chủ, tự tóm tắt khi đạt 10 MB. |
| Drive | Đưa file tìm được lên Google Drive (`drive.py`). |
| `/nghiencuu` (`agentscan.py`, `agentmatrix.py`) | Nghiên cứu các hệ thống AI Agent khác: dán link GitHub, bot tạo thẻ đánh giá nháp (thông tin repo + tóm tắt README, không chạy mã), sau đó chấm 12 chiều có bằng chứng và gộp vào bảng so sánh. |
| Tiện dùng | Thanh nút cố định ở đáy (Menu + các nhóm), nút «Gần đây» cho `/find` và `/open`, hiện cỡ phiên trước khi nối chế độ Claude và nút 🗜 tóm tắt phiên sang phiên mới. |

## Mô hình an toàn

| Ai | Làm được |
|---|---|
| Người lạ | không gì cả, bot im lặng |
| Đăng nhập bằng mật khẩu (30 phút) | hỏi đáp, `/find` và tải file trong thư mục môn, `/conspect`, Drive, `/agent` chỉ đọc |
| Chủ (ID Telegram trong `.env`) | tất cả trên và trên cả ổ, `/open`, `/screen`, `/status`, `/notebook`, nợ, việc, `/capnhat` |
| Chủ + mật khẩu (chế độ Claude) | Claude sửa file trên ổ; lệnh vẫn phải bấm ✅ |

Quy tắc khác: `CLAUDE*.md`, dữ liệu cá nhân và chỉ mục không bao giờ đưa lên Git; `.env` chứa mọi khóa và đường dẫn; chữ lấy từ file hay trang web được coi là dữ liệu, không bao giờ là chỉ dẫn.

## Cài đặt

Windows 10/11, Python 3.12+, nên có GPU NVIDIA để nhúng chữ (CPU vẫn chạy, chậm hơn).

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # điền giá trị
set_password.bat              # mật khẩu cho thiết bị khác và chế độ Claude
index_course.bat              # lập chỉ mục cục bộ
run_bot.bat                   # hoặc: .venv\Scripts\python bot\tray.py  (khay hệ thống)
```
Tùy chọn: công cụ `claude` (chế độ Claude, `/capnhat`, việc hằng tuần), `nlm` (NotebookLM), Ollama (mô hình conspect cục bộ), khóa Google Drive (`HUONG_DAN_DRIVE.md`).

## Lệnh
`/menu` mở nút theo nhóm (nút Menu xanh của Telegram liệt kê cùng các nhóm). Mục «▶» chạy ngay rồi hiện nút bước tiếp theo; mục «✍» chờ tin nhắn kế tiếp làm tham số. `/help` được sinh từ chính menu nên không bao giờ lệch.

## Cấu trúc
```
bot/main.py      xử lý lệnh, chế độ, menu       bot/kfind.py     chỉ mục tên file, gợi ý gần đúng
bot/rag.py       chỉ mục + tìm kiếm             bot/sessions.py  phiên Claude đã lưu (chỉ đọc)
bot/viec.py      việc cần làm                   bot/congno.py    sổ nợ
bot/conspect.py  ghi chú học                    bot/wikiops.py   lời nhắc wiki dùng chung
bot/weekly.py    việc hằng tuần                 bot/tray.py      chạy ở khay hệ thống
```

## Giới hạn đã biết
- Chỉ Windows (dùng `os.startfile`, PowerShell, Task Scheduler); chưa thử trên macOS hay Linux.
- Gói Gemini miễn phí có giới hạn; khi bị hạn chế bot báo bằng lời thường.
- Chế độ Claude phụ thuộc công cụ `claude` và định dạng phiên của Claude Code.
- Một chủ duy nhất; không có cơ sở dữ liệu nhiều người dùng.
