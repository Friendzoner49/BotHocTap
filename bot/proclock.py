"""Khóa dùng chung giữa các TIẾN TRÌNH (bot, weekly.py) cho tài nguyên chỉ được một bên ghi một lúc:
- "wiki": kho SecondBrain (claude -p nạp/dọn wiki, nút chốt mâu thuẫn, git commit)
- "index": chỉ mục index_local (rag.build_index)
Dùng khóa file của Windows (msvcrt.locking): hệ điều hành tự nhả khi tiến trình chết, nên không có khóa «mồ côi».
Thứ tự lấy khóa luôn là wiki → index (không bao giờ ngược lại) để không kẹt chéo."""
import msvcrt
import os
import time
from contextlib import contextmanager
from pathlib import Path

LOCK_DIR = Path(__file__).resolve().parent.parent / "locks"


class Busy(Exception):
    """Tài nguyên đang bị bên khác giữ (thông điệp tiếng Việt để báo thẳng cho chủ)."""


class Lock:
    def __init__(self, name: str):
        self.name = name
        self.f = None

    def acquire(self, wait: float = 0, poll: float = 3) -> bool:
        """Thử lấy khóa, chờ tối đa `wait` giây. Lấy được → True."""
        LOCK_DIR.mkdir(exist_ok=True)
        f = open(LOCK_DIR / f"{self.name}.lock", "a+b")
        end = time.time() + wait
        while True:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                self.f = f
                return True
            except OSError:
                if time.time() >= end:
                    f.close()
                    return False
                time.sleep(poll)

    def release(self):
        if self.f:
            try:
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            self.f.close()
            self.f = None


def is_free(name: str) -> bool:
    lk = Lock(name)
    if lk.acquire(0):
        lk.release()
        return True
    return False


@contextmanager
def hold(name: str, wait: float = 0, busy_msg: str = ""):
    lk = Lock(name)
    if not lk.acquire(wait):
        raise Busy(busy_msg or f"Tài nguyên «{name}» đang được dùng, thử lại sau ít phút.")
    try:
        yield
    finally:
        lk.release()


def orphan_claude(cwd) -> list:
    """PID các `claude -p` (chạy nền, do bot/weekly mở) còn sống có thư mục làm việc là `cwd`.
    Gọi SAU khi đã giữ khóa: lúc đó lẽ ra không còn ai, có nghĩa là lượt cũ của một tiến trình đã chết vẫn đang ghi.
    Phiên Claude Code mở tay trong VS Code không bị tính (không có cờ -p)."""
    try:
        import psutil
    except ImportError:
        return []
    want = os.path.normcase(os.path.abspath(str(cwd)))
    out = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if not (p.info["name"] or "").lower().startswith("claude"):
                continue
            if "-p" not in p.cmdline():
                continue
            if os.path.normcase(os.path.abspath(p.cwd())) == want:
                out.append(p.pid)
        except Exception:
            continue
    return out
