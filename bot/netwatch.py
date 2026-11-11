"""Theo dõi kết nối tới Telegram: ghi lúc mất/có lại mạng vào net_state.json (khay hệ thống đọc file này để báo trên PC),
giải thích lỗi bằng tiếng Việt. Không dùng mạng, không dùng AI."""
import json
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "net_state.json"  # gitignore; bot tự ghi, không sửa tay
NOTIFY_MIN = 120  # mất kết nối ngắn hơn (giây) thì chỉ ghi lại, không nhắn
_lock = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d: dict):
    try:
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)
    except Exception:
        pass


def is_network(err) -> bool:
    """Lỗi do mạng/máy chủ Telegram (không phải lỗi mã của bot)."""
    names = {c.__name__ for c in type(err).__mro__}
    if names & {"BadRequest", "Forbidden", "ChatMigrated", "RetryAfter", "InvalidToken"}:
        return False  # trong python-telegram-bot các lỗi này là lớp con của NetworkError nhưng KHÔNG phải mất mạng
    s = f"{type(err).__name__} {err}"
    return bool(names & {"NetworkError", "TimedOut", "ConnectError", "ConnectTimeout", "ReadTimeout", "ReadError",
                         "WriteError", "RemoteProtocolError", "ProxyError", "PoolTimeout", "ConnectionError"}) \
        or any(x in s for x in ("Bad Gateway", "Gateway Timeout", "Service Unavailable", "502", "504"))


def explain(err) -> str:
    s = f"{type(err).__name__} {err}" if not isinstance(err, str) else err
    if "Conflict" in s:
        return "Có 2 bản bot cùng chạy (run_bot.bat và khay cùng lúc?)"
    if "Bad Gateway" in s or "502" in s or "Service Unavailable" in s or "Gateway Timeout" in s:
        return "Máy chủ Telegram lỗi tạm thời (Bad Gateway), không phải lỗi máy bạn"
    if "Timeout" in s or "TimedOut" in s or "timed out" in s.lower():
        return "Telegram phản hồi quá lâu (mạng chậm/chập chờn)"
    if "Connect" in s or "NetworkError" in s or "Proxy" in s:
        return "Không kết nối được tới máy chủ Telegram (mạng hoặc VPN rớt, hoặc Telegram bị chặn)"
    return s.split(":")[0][:80]


def mark_fail(err):
    now = time.time()
    with _lock:
        d = _load()
        if not d.get("down_since"):
            d["down_since"] = now
            d["count"] = 0
        d["count"] = d.get("count", 0) + 1
        d["err"] = explain(err)
        d["err_raw"] = type(err).__name__ if not isinstance(err, str) else err[:60]
        d["last_fail"] = now
        _save(d)


def mark_ok():
    """Gọi khi vừa nói chuyện được với Telegram. Trả về đợt mất kết nối vừa kết thúc (dict) nếu có, không thì None."""
    now = time.time()
    with _lock:
        d = _load()
        closed = None
        if d.get("down_since"):
            closed = {"from": d["down_since"], "to": now, "err": d.get("err", ""), "count": d.get("count", 0)}
            d["last_outage"] = closed
            d["history"] = ([closed] + d.get("history", []))[:10]
            d["down_since"] = None
            d["count"] = 0
            _save(d | {"last_ok": now})
        elif now - d.get("last_ok", 0) >= 60:  # không ghi đĩa liên tục
            d["last_ok"] = now
            _save(d)
        return closed


def mark_start():
    with _lock:
        d = _load()
        d["started"] = time.time()
        _save(d)


def hm(ts: float) -> str:
    t = time.localtime(ts)
    return time.strftime("%H:%M" if time.strftime("%d%m") == time.strftime("%d%m", t) else "%H:%M %d/%m", t)


def dur(secs: float) -> str:
    m = int(secs // 60)
    return f"{m // 60} giờ {m % 60} phút" if m >= 60 else (f"{m} phút" if m else f"{int(secs)} giây")


def outage_msg(o: dict) -> str:
    return (f"⚠ Bot vừa MẤT KẾT NỐI Telegram từ {hm(o['from'])} đến {hm(o['to'])} ({dur(o['to'] - o['from'])}).\n"
            f"Lý do: {o['err']}.\n"
            "Tin bạn gửi trong lúc đó: Telegram giữ lại và bot đang trả lời bù ngay bây giờ (nếu chưa thấy trả lời, gửi lại). "
            "Nhắc việc bị lỡ sẽ được gửi bù.")


def summary() -> str:
    d, now = _load(), time.time()
    out = []
    if d.get("down_since"):
        out.append(f"🔴 Đang mất kết nối Telegram từ {hm(d['down_since'])} ({dur(now - d['down_since'])}): {d.get('err', '')}")
    else:
        out.append("🟢 Kết nối Telegram: tốt" + (f" (kiểm tra gần nhất {hm(d['last_ok'])})" if d.get("last_ok") else ""))
    if d.get("started"):
        out.append(f"Bot chạy từ: {hm(d['started'])}")
    for o in d.get("history", [])[:3]:
        out.append(f"• Mất kết nối {hm(o['from'])} → {hm(o['to'])} ({dur(o['to'] - o['from'])}): {o['err']}")
    return "\n".join(out)
