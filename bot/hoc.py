"""Nhật ký thời gian học (hoc_nhat_ky.jsonl, dữ liệu cá nhân, gitignore, không sửa tay): mỗi lần /nhapai một cuộc chat với AI web
ghi một buổi (giờ câu đầu/cuối hoặc số phút chủ bấm). Báo cáo tuần đọc lại bằng week_summary. (/giohoc bấm giờ tay đã bỏ 12/11.)"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import wikilink

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "hoc_nhat_ky.jsonl"


def subject_of(text: str) -> str:
    """Môn đoán từ chữ (dùng bảng tên môn của wikilink); không đoán được thì «»."""
    link = wikilink.find(text).strip("[]")
    return link.split("-")[0].upper() if link else ""


def log_session(start: float, minutes: int, topic: str, source: str) -> dict:
    """Ghi một buổi học bằng AI web (/nhapai) vào cùng nhật ký: giờ câu đầu (hoặc giờ nhập trừ số phút chủ chọn), số phút, chủ đề.
    Thay cho /giohoc (đã bỏ 12/11); không có mức hiểu."""
    topic = topic.strip()[:80] or "Học bằng AI web"
    rec = {"ngay": datetime.fromtimestamp(start).strftime("%Y-%m-%d"), "gio_bat_dau": datetime.fromtimestamp(start).strftime("%H:%M"),
           "mon": subject_of(topic), "chu_de": topic, "phut": int(minutes), "hieu": None, "nguon": source}
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def records(days: int = 7) -> list:
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out = []
    if LOG.exists():
        for ln in LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get("ngay", "") >= since:
                out.append(r)
    return out


def week_summary(days: int = 7) -> str:
    rs = records(days)
    if not rs:
        return ""
    tot = sum(r["phut"] for r in rs)
    by = {}
    for r in rs:
        by.setdefault(r["mon"] or "chưa gán môn", []).append(r)
    out = [f"📚 Học tuần qua: {tot // 60} giờ {tot % 60} phút, {len(rs)} phiên"]
    for m, lst in sorted(by.items(), key=lambda kv: -sum(x["phut"] for x in kv[1])):
        rated = [x["hieu"] for x in lst if x.get("hieu")]
        out.append(f"  • {m}: {sum(x['phut'] for x in lst)} phút" + (f", hiểu TB {sum(rated) / len(rated):.1f}/5" if rated else ""))
    low = [r for r in rs if r.get("hieu") and r["hieu"] <= 2]
    if low:
        out.append("🔁 Nên học lại (hiểu ≤ 2): " + "; ".join(f"{r['chu_de']} ({r['hieu']}/5, {r['phut']} phút)" for r in low[-4:]))
    return "\n".join(out)
