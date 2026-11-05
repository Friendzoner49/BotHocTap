"""Dùng chung cho /capnhat (main.py) và cập nhật hằng tuần (weekly.py): bộ đếm và lời nhắc kiểm tra wiki (lint)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINT_STATE = ROOT / "lint_state.json"  # {"since": số nguồn đã nạp từ lần kiểm tra wiki gần nhất}
LINT_EVERY = 10  # đủ 10 nguồn mới tự kiểm tra wiki (đúng quy ước trong CLAUDE.md của kho)
LINT_PROMPT = (
    "Chạy tự động, không có người trả lời giữa chừng. Đọc CLAUDE.md của kho rồi làm quy trình Lint: mâu thuẫn và khẳng định lỗi thời, "
    "trang mồ côi và link hỏng, khái niệm có ở từ 2 dự án trở lên mà chưa có trang, dòng chức năng thiếu nguồn, trang thiếu trong index.md. "
    "Tự sửa những chỗ an toàn (thêm vào index, sửa link, thêm trích dẫn), phần còn lại chỉ báo. Ghi mục `lint` vào log.md. "
    "KHÔNG dùng git. Chỉ ghi dưới wiki/, index.md, log.md. Cuối cùng tóm tắt tiếng Việt tối đa 8 dòng: đã sửa gì, cần tôi quyết gì."
)


def load() -> dict:
    try:
        return json.loads(LINT_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"since": 0}


def save(st: dict):
    LINT_STATE.write_text(json.dumps(st), encoding="utf-8")
