"""Dọn dẹp tự động ngày 28 hằng tháng (viec_loop gọi). CHỈ động vào: file tạm/đệm của chính bot, bản sao tạm do bot sinh, và vài loại rác chắc chắn
trong thư mục môn học (khóa Office ~$*, Thumbs.db, desktop.ini, *.tmp). KHÔNG xóa: video/âm thanh/slide/ghi chú/script của bạn, wiki, chỉ mục,
conspect_out, sổ nợ, việc cần làm, bản gốc nào cả. dry=True chỉ liệt kê."""
import os
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAY = 86400


def _old(p: Path, days: float) -> bool:
    try:
        return time.time() - p.stat().st_mtime > days * DAY
    except OSError:
        return False


def _size(p: Path) -> int:
    try:
        if p.is_dir():
            return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        return p.stat().st_size
    except OSError:
        return 0


def _rm(p: Path, dry: bool) -> int:
    n = _size(p)
    if dry:
        return n
    try:
        if p.is_dir():
            import shutil
            shutil.rmtree(p)
        else:
            p.unlink()
        return n
    except OSError:  # đang mở/khóa: để lần sau
        return 0


def run(course_dir: Path | None = None, dry: bool = False) -> str:
    freed, notes = 0, []

    def take(label, paths, days):
        nonlocal freed
        n = k = 0
        for p in paths:
            if _old(p, days):
                b = _rm(p, dry)
                if b or not p.exists():
                    n += b
                    k += 1
        if k:
            freed += n
            notes.append(f"{label}: {k} mục ({n / 1048576:.1f} MB)")

    take("Bản PDF chuyển tạm cho NotebookLM (>30 ngày)", list((ROOT / "nb_convert").glob("*")), 30)
    take("Chữ trích tạm của báo cáo tuần (>30 ngày)", [p for p in (ROOT / "reports").glob("*-texts")], 30)
    take("Báo cáo tuần cũ (>180 ngày)", list((ROOT / "reports").glob("20*.md")), 180)
    take("Yêu cầu duyệt từ xa bỏ dở", list((ROOT / "decisions").glob("req-*")), 1)
    take("Tin báo tạm của hook Claude (>1 ngày)", list(Path(tempfile.gettempdir()).glob("claude_notify_*.txt")), 1)
    aw = ROOT / "away.json"
    if aw.exists():
        try:
            import json
            if float(json.loads(aw.read_text(encoding="utf-8")).get("until", 0)) < time.time():
                freed += _rm(aw, dry)
        except Exception:
            pass
    log = ROOT / "bot.log"  # nhật ký lớn quá 5 MB: giữ 1 MB cuối
    if log.exists() and log.stat().st_size > 5 * 1048576 and not dry:
        try:
            data = log.read_bytes()[-1048576:]
            log.write_bytes(data[data.find(b"\n") + 1:])
            notes.append("bot.log: cắt còn 1 MB cuối")
        except OSError:
            pass
    if course_dir and course_dir.exists():
        junk = []
        for pat in ("~$*", "Thumbs.db", "desktop.ini", "*.tmp"):
            junk += [p for p in course_dir.rglob(pat) if p.is_file() and ".claude" not in p.parts]
        n = k = 0
        for p in junk:
            if _old(p, 7):
                b = _rm(p, dry)
                if b or not p.exists():
                    n += b
                    k += 1
        if k:
            freed += n
            notes.append(f"Rác trong thư mục môn học (khóa Office ~$, Thumbs.db, desktop.ini, .tmp): {k} file")
    head = f"🧹 Dọn dẹp tháng{' (chạy thử, chưa xóa gì)' if dry else ''}: " + (f"giải phóng khoảng {freed / 1048576:.1f} MB." if notes else "không có gì cần dọn.")
    return head + ("\n" + "\n".join("• " + x for x in notes) if notes else "") + "\nKhông đụng tới video, ghi chú, wiki, sổ nợ hay việc cần làm của bạn."
