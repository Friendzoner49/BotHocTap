"""Tìm file theo TÊN trên phạm vi được phép: thư mục môn học (ai đăng nhập cũng thấy) + cả ổ chứa bot (chỉ CHỦ).
Chỉ mục tên file nằm trong bộ nhớ, dựng ở luồng nền; không đọc nội dung. Không có kết quả → gợi ý tên gần đúng."""
import difflib
import os
import re
import threading
import time
import unicodedata
from pathlib import Path

# thư mục không đưa vào chỉ mục (rác, bản cài đặt, dữ liệu của chính bot); bỏ qua ở mọi cấp
SKIP_DIRS = {"$recycle.bin", "system volume information", ".git", "node_modules", ".venv", "__pycache__", ".claude",
             "index_local", "ocr_cache", ".trash"}
# thư mục cấp 1 của ổ K: là phần mềm/bản cài, không phải tài liệu; chỉnh được bằng FIND_SKIP_DIRS trong .env (cách nhau dấu phẩy)
DEFAULT_SKIP_TOP = ("eclipse", "National Instruments LabView 2021 SP1", "javafx-sdk-25", "openjfx-25_windows-x64_bin-sdk",
                    "Programs", "OldGameVersions", "EaseUS-Todo-PCTrans-14.2.3", "TestGit")
STOP = {"gui", "cho", "toi", "minh", "file", "tep", "giup", "tim", "lay", "mo", "hay", "voi", "di", "nhe", "xem", "cai", "duoc",
        "mot", "cua", "the", "den", "tren", "may", "tinh", "nao", "dau", "o"}
_lock = threading.Lock()
_st = {"entries": [], "ts": 0.0, "building": False}


def fold(s: str) -> str:
    """Chữ thường, bỏ dấu, ký tự lạ thành khoảng trắng: «tư duy-hệ_thống» == «tu duy he thong»."""
    s = unicodedata.normalize("NFD", s).replace("đ", "d").replace("Đ", "d")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"\w+", s.casefold()))


def clean_query(q: str) -> list:
    out = []
    for w in fold(q).split():
        if w in STOP or (len(w) < 2 and not w.isdigit()):
            continue
        out.append(w)
    return out


def is_secret(p) -> bool:
    n = Path(p).name.casefold()
    return (n.startswith(".env") or n in {"password.json", "credentials.json", "drive_token.json"}
            or (n.startswith("token") and n.endswith(".json")) or n.endswith((".pem", ".key", ".pfx", ".p12"))
            or n.startswith("id_rsa") or n.startswith("secret"))


def _skip_top() -> set:
    raw = os.environ.get("FIND_SKIP_DIRS")
    names = [x.strip() for x in raw.split(",")] if raw is not None else list(DEFAULT_SKIP_TOP)
    return {x.casefold() for x in names if x}


def roots(course: Path, owner_root: Path) -> list:
    return [course, owner_root]


def build(course: Path, owner_root: Path) -> int:
    """Dựng lại chỉ mục tên file (chạy được trong luồng nền)."""
    with _lock:
        if _st["building"]:
            return len(_st["entries"])
        _st["building"] = True
    try:
        skip_top = _skip_top()
        entries, seen = [], set()
        for top in (course, owner_root):
            try:
                top_r = top.resolve()
            except Exception:
                continue
            if str(top_r) in seen or not top_r.exists():
                continue
            seen.add(str(top_r))
            for dp, dns, fns in os.walk(top_r):
                at_root = Path(dp) == top_r
                dns[:] = [d for d in dns if d.casefold() not in SKIP_DIRS and not (at_root and d.casefold() in skip_top)
                          and not (top_r != course.resolve() and (Path(dp) / d) == course.resolve())]
                for fn in fns:
                    p = os.path.join(dp, fn)
                    entries.append((fold(p), p, fold(fn)))
        _st["entries"], _st["ts"] = entries, time.time()
        return len(entries)
    finally:
        _st["building"] = False


def ensure(course: Path, owner_root: Path, max_age: float = 3 * 3600):
    """Có chỉ mục dùng được: chưa có thì dựng ngay; cũ quá thì dựng lại ở luồng nền (vẫn dùng bản cũ)."""
    if not _st["entries"]:
        build(course, owner_root)
    elif time.time() - _st["ts"] > max_age and not _st["building"]:
        threading.Thread(target=build, args=(course, owner_root), daemon=True).start()


def rebuild_if_older(course: Path, owner_root: Path, secs: float = 120):
    """Không thấy file vừa tạo? Dựng lại (không quá một lần mỗi `secs` giây)."""
    if time.time() - _st["ts"] > secs:
        build(course, owner_root)


def _in(p: str, base: Path) -> bool:
    try:
        return Path(p).is_relative_to(base)
    except Exception:
        return False


def _scoped(course: Path, owner: bool, exts):
    cr = course.resolve()
    for fp, p, fname in _st["entries"]:
        if not owner and not _in(p, cr):
            continue
        if exts and Path(p).suffix.casefold() not in exts:
            continue
        if is_secret(p):
            continue
        yield fp, p, fname


def search(query: str, course: Path, owner_root: Path, owner: bool, exts=None, limit: int = 8) -> list:
    """Mọi từ khóa đều có trong đường dẫn (không phân biệt hoa thường/dấu). Tên file khớp nhiều từ xếp trước, rồi file nằm nông."""
    ensure(course, owner_root)
    toks = clean_query(query)
    if not toks:
        return []
    hits = []
    for fp, p, fname in _scoped(course, owner, exts):
        if all(t in fp for t in toks):
            hits.append((-sum(t in fname for t in toks), p.count(os.sep), len(fname), p))
    hits.sort()
    return [Path(h[3]) for h in hits[:limit]]


def suggest(query: str, course: Path, owner_root: Path, owner: bool, exts=None, limit: int = 6) -> list:
    """Không khớp chính xác: tên file gần đúng nhất (dấu/chính tả sai, thiếu từ). Chỉ so tên file, không so thư mục."""
    ensure(course, owner_root)
    toks = clean_query(query)
    q = " ".join(toks)
    if not q:
        return []
    cands = {}
    for fp, p, fname in _scoped(course, owner, exts):
        stem = fold(Path(p).stem)
        cands.setdefault(stem, p)
    # lọc nhanh: có chung ít nhất một từ (từ dài từ 3 ký tự) hoặc cùng tiền tố 3 chữ; nếu không được gì thì so hết
    pre = {s: p for s, p in cands.items() if any((len(t) >= 3 and (t in s or any(w.startswith(t[:3]) for w in s.split()))) for t in toks)}
    pool = pre or cands
    qs = " ".join(sorted(toks))
    sm = difflib.SequenceMatcher()
    scored = []
    for stem, p in pool.items():
        sm.set_seq2(stem)  # seq2 được cache, seq1 đổi theo từng phép so
        best = 0.0
        for a in (q, qs):
            sm.set_seq1(a)
            if sm.real_quick_ratio() < 0.4 or sm.quick_ratio() < 0.4:
                continue
            best = max(best, sm.ratio())
        b = " ".join(sorted(stem.split()))  # đảo thứ tự từ: «quyết định bothoctap» ~ «bothoctap quyết định»
        sm.set_seq2(b)
        sm.set_seq1(qs)
        best = max(best, sm.ratio())
        if best >= 0.5:
            scored.append((-best, len(stem), stem))
    scored.sort()
    return [Path(pool[s[2]]) for s in scored[:limit]]


def allowed(p, course: Path, owner_root: Path, owner: bool) -> bool:
    """File này có được gửi/mở không: là file thật, không phải file bí mật; người thường chỉ trong thư mục môn học, chủ thêm cả ổ."""
    try:
        r = Path(p).resolve()
        if not r.is_file() or is_secret(r):
            return False
        if r.is_relative_to(course.resolve()):
            return True
        return owner and r.is_relative_to(owner_root.resolve()) and not any(x.casefold() in SKIP_DIRS for x in r.parts)
    except Exception:
        return False
