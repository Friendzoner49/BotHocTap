"""Liệt kê các phiên Claude Code đã lưu trên máy (C:\\Users\\<tên>\\.claude\\projects\\*\\*.jsonl): chỉ đọc đầu file để lấy
thư mục làm việc (cwd), câu mở đầu và giờ dùng gần nhất. Không sửa, không xóa phiên."""
import json
import re
import time
from pathlib import Path

BASE = Path.home() / ".claude" / "projects"
HEAD_BYTES = 1_000_000  # chỉ đọc đầu file (phiên dài hàng chục MB; câu đầu có thể kèm ảnh vài trăm KB)
LIVE_SECS = 600       # dùng trong 10 phút qua = có thể đang mở trong cửa sổ khác


def _text_of(msg) -> str:
    c = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    return ""


def _head(path: Path) -> dict:
    cwd, title = "", ""
    try:
        with open(path, "rb") as f:
            raw = f.read(HEAD_BYTES)
        for line in raw.decode("utf-8", "ignore").splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue  # dòng cuối bị cắt dở
            cwd = cwd or d.get("cwd") or ""
            if title or d.get("type") != "user" or d.get("isMeta") or d.get("isSidechain"):
                continue
            t = re.sub(r"<([\w-]+)[^>]*>.*?</\1>", "", _text_of(d.get("message")), flags=re.S).strip()  # bỏ khối <system-reminder>…
            if not t or t.startswith("<") or "local-command" in t[:60]:
                continue
            title = re.sub(r"\s+", " ", t)[:70]
            if cwd and title:
                break
    except Exception:
        pass
    return {"cwd": cwd, "title": title}


def in_drive(cwd: str, root: Path) -> bool:
    """Thư mục làm việc của phiên có nằm trong ổ chứa bot (K:) không; phiên ngoài ổ này chỉ để xem."""
    return bool(cwd) and cwd[:2].casefold() == str(root.anchor)[:2].casefold()


def list_sessions(root: Path, limit: int = 40) -> list:
    """Các phiên mới dùng gần nhất (mọi dự án trên máy), mới nhất trước."""
    try:
        files = sorted(BASE.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    except Exception:
        return []
    now = time.time()
    out = []
    for p in files:
        h = _head(p)
        m = p.stat().st_mtime
        cwd = h["cwd"]
        out.append({"id": p.stem, "path": str(p), "cwd": cwd, "project": Path(cwd).name if cwd else p.parent.name, "title": h["title"] or "(chưa có câu hỏi)",
                    "mtime": m, "ago": now - m, "live": now - m < LIVE_SECS, "ok": in_drive(cwd, root)})
    return out


def newest_for(root: Path, project: str) -> dict | None:
    """Phiên mới nhất của một dự án (vd. «BotHocTap», là phiên VS Code đang làm việc)."""
    for s in list_sessions(root, limit=15):
        if s["ok"] and s["project"].casefold() == project.casefold():
            return s
    return None


def ago_text(secs: float) -> str:
    if secs < 90:
        return "vừa xong"
    if secs < 5400:
        return f"{int(secs // 60)} phút trước"
    if secs < 129600:
        return f"{int(secs // 3600)} giờ trước"
    return f"{int(secs // 86400)} ngày trước"


def find_path(sid: str) -> str:
    """Đường dẫn file phiên theo ID (tìm trong mọi dự án)."""
    for p in BASE.glob(f"*/{sid}.jsonl"):
        return str(p)
    return ""


def context_tokens(path: str, tail_bytes: int = 600_000) -> int:
    """Số token ngữ cảnh ở lượt trả lời gần nhất (input + cache), đọc từ cuối file; 0 nếu không đọc được. Đó là cỡ bị gửi lại mỗi tin nhắn."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            raw = f.read()
        for line in reversed(raw.decode("utf-8", "ignore").splitlines()):
            try:
                u = (json.loads(line).get("message") or {}).get("usage")
            except Exception:
                continue
            if isinstance(u, dict) and "input_tokens" in u:
                return int(u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0))
    except Exception:
        pass
    return 0
