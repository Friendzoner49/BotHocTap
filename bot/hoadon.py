"""Gửi hóa đơn 705bot cho khách qua Telegram từ bot này. Dùng ĐÚNG hàm của app 705bot (cầu nối hoadon_bridge.py, chạy bằng python của 705bot).
Không tạo/sửa hóa đơn; chỉ đọc danh sách và gọi hàm gửi sau khi chủ bấm ✅."""
import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path

PY = Path(os.environ.get("APP705_DIR", "705bot")) / ".venv" / "Scripts" / "python.exe"
BRIDGE = Path(__file__).resolve().parent / "hoadon_bridge.py"


def _run(*args, timeout=60):
    if not PY.exists():
        raise RuntimeError("Không thấy python của app 705bot (thư mục .venv của 705bot).")
    r = subprocess.run([str(PY), "-X", "utf8", str(BRIDGE), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "lỗi")[-300:])
    return json.loads(r.stdout)


def recent(n=40):
    return _run("list", n)


def preview(inv_id: int) -> str:
    return _run("preview", inv_id)["text"]


def send(inv_id: int) -> dict:
    return _run("send", inv_id, timeout=90)


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


INTENT = re.compile(r"\b(gửi|gui|send)\b.{0,25}\b(hóa đơn|hoa don|hđ|hd|bill)\b", re.I)


def is_intent(text: str) -> bool:
    return bool(INTENT.search(text)) or bool(INTENT.search(fold(text)))


def pick(text: str, rows: list):
    """Từ câu «gửi hóa đơn cho Lan», «gửi hóa đơn #14», «gửi hóa đơn mới nhất» → (danh sách khớp, lý do)."""
    m = re.search(r"#\s*(\d+)|\b(?:số|so)\s*(\d+)", text, re.I)
    if m:
        i = int(m.group(1) or m.group(2))
        return [r for r in rows if r["id"] == i], f"#{i}"
    t = fold(text)
    t = re.sub(r"\b(gui|hoa don|hd|bill|cho|khach|cua|giup|toi|minh|nhe|nha|di|ngay|hom nay|hom qua|moi nhat|gan nhat)\b", " ", t)
    name = re.sub(r"\s+", " ", t).strip()
    if not name:
        return [r for r in rows if r["status"] == "finalized" and not r["sent"]][:6], "chưa gửi"
    return [r for r in rows if name in fold(r["customer"])][:6], name
