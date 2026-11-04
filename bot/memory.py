"""Bộ nhớ dài hạn của bot (chỉ ghi hội thoại của chủ). Thư mục memory\:
  digest.md  = bản tóm tắt gọn, luôn đưa vào câu hỏi (giữ vài KB)
  log.jsonl  = từng lượt hỏi-đáp thô; tra theo từ khóa lấy vài lượt liên quan
  state.json = {"mode": "", "warned": bool}; mode "continue" = chủ chọn dùng tiếp đến 15 MB
Mốc: 10 MB tự tóm tắt phần cũ · 13 MB hỏi chủ (xóa cũ / dùng tiếp) · 15 MB đầy, thôi ghi nhớ."""
import json
import re
import time
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "memory"
MB = 1048576
SOFT, WARN, HARD = 10 * MB, 13 * MB, 15 * MB
DIGEST_MAX = 8000       # ký tự tối đa của bản tóm tắt đưa vào câu hỏi
ANS_KEEP = 1500         # chỉ giữ đầu câu trả lời mỗi lượt
LOG, DIGEST, STATE = DIR / "log.jsonl", DIR / "digest.md", DIR / "state.json"


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"mode": "", "warned": False}


def _save_state(s: dict):
    DIR.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(s), encoding="utf-8")


def size() -> int:
    return sum(p.stat().st_size for p in (LOG, DIGEST) if p.exists())


def status() -> str:
    s, st = size(), _state()
    mode = "dùng tiếp đến 15 MB" if st.get("mode") == "continue" else "bình thường"
    full = " — ĐẦY, bot không ghi nhớ thêm" if s >= HARD else ""
    return f"Bộ nhớ: {s / MB:.2f} / 15 MB ({mode}){full}"


def _words(t: str) -> set:
    return {w for w in re.findall(r"\w+", t.lower()) if len(w) > 2}


def recall(question: str, k: int = 3) -> str:
    """Bản tóm tắt + k lượt cũ giống câu hỏi nhất (đếm từ chung). Trả '' nếu chưa có gì."""
    parts = []
    if DIGEST.exists():
        parts.append("TÓM TẮT NHỮNG GÌ ĐÃ NÓI TRƯỚC ĐÂY:\n" + DIGEST.read_text(encoding="utf-8")[-DIGEST_MAX:])
    if LOG.exists():
        qw, best = _words(question), []
        for ln in LOG.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(ln)
            except Exception:
                continue
            sc = len(qw & _words(e["q"] + " " + e["a"][:300]))
            if sc >= 2:
                best.append((sc, e))
        best.sort(key=lambda x: -x[0])
        for _, e in best[:k]:
            parts.append(f"[{e['t']}] Hỏi: {e['q']}\nĐáp: {e['a']}")
    return "\n\n".join(parts)


def add(q: str, a: str) -> str:
    """Ghi một lượt. Trả '' hoặc 'full' (vừa đầy) hoặc 'warn' (vừa chạm 13 MB, cần hỏi chủ)."""
    if size() >= HARD:
        return "full"
    DIR.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M"), "q": q[:1500], "a": a[:ANS_KEEP]}, ensure_ascii=False) + "\n")
    s, st = size(), _state()
    if s >= HARD:
        return "full"
    if s >= WARN and not st.get("warned") and st.get("mode") != "continue":
        st["warned"] = True
        _save_state(st)
        return "warn"
    return ""


def needs_condense() -> bool:
    return size() >= SOFT and _state().get("mode") != "continue" and not _state().get("warned")


def condense(summarize) -> str:
    """Tóm tắt nửa cũ của log (summarize(text) -> chuỗi, do main.py cấp, dùng Gemini) rồi gộp vào digest.
    Chỉ xóa phần cũ SAU KHI tóm tắt thành công."""
    lines = LOG.read_text(encoding="utf-8").splitlines()
    cut = max(1, len(lines) // 2)
    old, keep = lines[:cut], lines[cut:]
    text = "\n".join(old)
    chunks = [text[i:i + 60000] for i in range(0, len(text), 60000)]
    notes = []
    for c in chunks:
        notes.append(summarize(c))
    merged = ((DIGEST.read_text(encoding="utf-8") + "\n") if DIGEST.exists() else "") + "\n".join(notes)
    if len(merged) > DIGEST_MAX:  # digest phình → tóm tắt lại chính nó
        merged = summarize(merged)[:DIGEST_MAX]
    DIGEST.write_text(merged, encoding="utf-8")
    LOG.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    return f"Đã tóm tắt {len(old)} lượt cũ. {status()}"


def delete_old() -> str:
    """Chủ chọn «Xóa phần ký ức cũ»: bỏ nửa cũ của log; giữ digest."""
    if LOG.exists():
        lines = LOG.read_text(encoding="utf-8").splitlines()
        LOG.write_text("\n".join(lines[len(lines) // 2:]) + "\n", encoding="utf-8")
    _save_state({"mode": "", "warned": False})
    return status()


def keep_going() -> str:
    _save_state({"mode": "continue", "warned": True})
    return status()
