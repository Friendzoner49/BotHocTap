"""«Chế độ tôi ra ngoài»: khi bật, hook của Claude Code (~/.claude/scripts/remote_decide.py) chuyển câu xin phép/câu hỏi về Telegram.
Giao tiếp qua file trong thư mục decisions (hook ghi req-*.json và giữ nhịp bằng mtime; bot ghi req-*.answer). Chỉ chủ bấm được."""
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AWAY = ROOT / "away.json"
DIR = ROOT / "decisions"
FRESH = 8  # giây: hook coi là còn sống nếu req-*.json được chạm trong 8 giây


def away_until() -> float:
    try:
        return float(json.loads(AWAY.read_text(encoding="utf-8")).get("until", 0))
    except Exception:
        return 0.0


def is_away() -> bool:
    return time.time() < away_until()


def set_away(hours: float):
    AWAY.write_text(json.dumps({"until": time.time() + hours * 3600, "since": time.time()}), encoding="utf-8")


def clear_away():
    AWAY.unlink(missing_ok=True)


def left_text() -> str:
    m = int((away_until() - time.time()) / 60)
    return f"{m // 60} giờ {m % 60} phút" if m >= 60 else f"{max(m, 0)} phút"


def pending() -> list:
    """Các yêu cầu còn sống (hook đang chờ). File cũ không còn nhịp (hook đã chết do bạn trả lời trên máy) bị xóa."""
    out = []
    if not DIR.exists():
        return out
    for f in DIR.glob("req-*.json"):
        try:
            if time.time() - f.stat().st_mtime > 30:
                f.unlink(missing_ok=True)
                f.with_suffix(".answer").unlink(missing_ok=True)
                continue
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return out


def alive(rid: str) -> bool:
    f = DIR / f"req-{rid}.json"
    try:
        return time.time() - f.stat().st_mtime < FRESH
    except OSError:
        return False


def answer(rid: str, data: dict) -> bool:
    """Ghi câu trả lời cho hook. False nếu hook không còn chờ (đã xử lý trên máy hoặc hết hạn)."""
    if not alive(rid):
        return False
    tmp = DIR / f"req-{rid}.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(DIR / f"req-{rid}.answer")
    return True
