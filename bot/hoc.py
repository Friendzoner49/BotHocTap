"""Nhật ký thời gian học: /hoc <chủ đề> bắt đầu bấm giờ, nút ⏹ Xong kết thúc, rồi chấm mức hiểu 1–5. Mục đích: có số thật (phút/chủ đề, độ hiểu)
để sau này bot tự xếp lịch học. Dữ liệu cá nhân: hoc_state.json + hoc_nhat_ky.jsonl (gitignore, không sửa tay)."""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import wikilink

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "hoc_state.json"
LOG = ROOT / "hoc_nhat_ky.jsonl"
CAP_MIN = 180  # quá 3 giờ liền: nghi quên bấm Xong → hỏi lại


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d: dict):
    STATE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def subject_of(text: str) -> str:
    """Môn đoán từ chữ (dùng bảng tên môn của wikilink); không đoán được thì «»."""
    link = wikilink.find(text).strip("[]")
    return link.split("-")[0].upper() if link else ""


def current():
    return _load().get("cur")


def pending():
    return _load().get("pending")


def start(topic: str) -> dict:
    cur = {"topic": topic.strip()[:120], "subject": subject_of(topic), "start": time.time()}
    d = _load()
    d["cur"] = cur
    _save(d)
    return cur


def minutes_running(cur: dict) -> int:
    return int((time.time() - cur["start"]) / 60)


def stop():
    """Kết thúc phiên đang chạy → chuyển sang «chờ chấm mức hiểu». Trả về bản ghi chờ, hoặc None nếu không có phiên."""
    d = _load()
    cur = d.pop("cur", None)
    if not cur:
        return None
    raw = max(1, minutes_running(cur))
    d["pending"] = {**cur, "raw_min": raw, "minutes": raw, "check": raw > CAP_MIN, "end": time.time()}
    _save(d)
    return d["pending"]


def fix_minutes(minutes: int | None):
    """Sau nút «quên bấm Xong»: ghi đúng số phút chọn, hoặc None = bỏ bản ghi."""
    d = _load()
    p = d.get("pending")
    if not p:
        return None
    if minutes is None:
        d.pop("pending")
        _save(d)
        return None
    p["minutes"], p["check"] = int(minutes), False
    _save(d)
    return p


def finish(rating):
    """Ghi bản ghi chờ vào nhật ký (rating 1–5 hoặc None)."""
    d = _load()
    p = d.pop("pending", None)
    if not p:
        return None
    rec = {"ngay": datetime.fromtimestamp(p["start"]).strftime("%Y-%m-%d"), "gio_bat_dau": datetime.fromtimestamp(p["start"]).strftime("%H:%M"),
           "mon": p["subject"], "chu_de": p["topic"], "phut": p["minutes"], "hieu": rating}
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    _save(d)
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
