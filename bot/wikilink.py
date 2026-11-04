"""Tự gắn liên kết [[trang wiki]] vào việc cần làm, theo tên môn học (và số lab/работа nếu có).
Cấu hình môn nằm trong wikilink_mon.json cạnh thư mục bot (không đưa lên Git; xem wikilink_mon.example.json).
Chỉ ĐỌC danh sách trang trong thư mục wiki; chỉ gắn trang có thật. Không dùng AI. Thiếu file cấu hình thì không gắn gì."""
import json
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "wikilink_mon.json"
_NUM = re.compile(r"(?<!\w)(lab(?:oratory)?|лаб\w*|работ\w*|rabota|bài tập|bai tap|bài)\s*(?:số|so|№|#)?\s*(\d{1,2})(?!\d)", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return "".join(c for c in s if not unicodedata.combining(c))


def _config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return None


def _pages(cfg) -> set:
    w = os.environ.get("WIKI_DIR")
    d = Path(w) / cfg.get("dir", "wiki") if w else None
    return {p.stem for p in d.glob("*.md")} if d and d.exists() else set()


def _specific(prefix: str, kind: str, n: int, pages: set):
    """Trang lab/работа đúng số: «x-lab-5-6» chứa 5 và 6; «x-soho-rabota-5»."""
    for p in sorted(pages):
        if not p.startswith(prefix + "-"):
            continue
        if kind in ("rabota", "any") and re.search(rf"rabota-{n}$", p):
            return p
        if kind in ("lab", "any"):
            m = re.search(r"-lab-(\d+)(?:-(\d+))?$", p)
            if m and int(m.group(1)) <= n <= int(m.group(2) or m.group(1)):
                return p
    return None


def find(text: str) -> str:
    """Trả '[[trang]]' hoặc ''. Môn xuất hiện sớm nhất trong câu được chọn.
    Tên gọi bắt đầu bằng «!» (vd «!BI») chỉ khớp khi viết đúng hoa/thường và đứng riêng một từ."""
    cfg = _config()
    if not cfg:
        return ""
    pages = _pages(cfg)
    if not pages:
        return ""
    t = norm(text)
    best = None
    for s in cfg.get("subjects", {}).values():
        for a in s.get("aliases", []):
            if a.startswith("!"):
                m = re.search(rf"(?<!\w){re.escape(a[1:])}(?!\w)", text)
            else:
                a = norm(a)
                m = re.search(rf"(?<!\w){re.escape(a)}" + (r"(?!\w)" if len(a) <= 3 else ""), t)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), s["prefix"], s.get("hub", ""))
    if not best:
        return ""
    _, prefix, hub = best
    mn = _NUM.search(text)
    if mn:
        w = norm(mn.group(1))
        kind = "rabota" if "rabot" in w or w.startswith("работ") else "lab" if w.startswith(("lab", "лаб")) else "any"
        page = _specific(prefix, kind, int(mn.group(2)), pages)
        if page:
            return f"[[{page}]]"
    return f"[[{hub}]]" if hub in pages else ""
