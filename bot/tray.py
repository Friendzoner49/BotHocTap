"""Chạy bot dưới khay hệ thống. Bấm vào biểu tượng để bật/tắt cửa sổ xem log. Chạy bằng pythonw (không cửa sổ)."""
import ctypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pystray
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "bot.log"
NO_WINDOW = 0x08000000
NEW_CONSOLE = 0x00000010

# chỉ cho chạy 1 bản
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "BotHocTapTray")
if ctypes.windll.kernel32.GetLastError() == 183:
    sys.exit(0)

if LOG.exists() and LOG.stat().st_size > 2_000_000:
    LOG.write_text("", encoding="utf-8")

state = {"bot": None, "viewer": None, "stop": False}


def start_bot():
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONUTF8="1")
    out = open(LOG, "ab")
    state["bot"] = subprocess.Popen([str(PY), "-X", "utf8", str(ROOT / "bot" / "main.py")], cwd=str(ROOT),
                                    stdout=out, stderr=subprocess.STDOUT, env=env, creationflags=NO_WINDOW)


def kill_bot():
    b = state["bot"]
    if b and b.poll() is None:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(b.pid)], creationflags=NO_WINDOW,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def watchdog():
    """Bot chết (mạng/VPN rớt, lỗi) thì chờ 10 giây rồi chạy lại."""
    while not state["stop"]:
        b = state["bot"]
        if b is None or b.poll() is not None:
            time.sleep(10)
            if not state["stop"]:
                start_bot()
        time.sleep(2)


TITLE = "BotHocTap (bấm để xem log)"


def net_watch():
    """Đọc net_state.json do bot ghi: đang mất kết nối Telegram > 90 giây thì đổi chữ biểu tượng và hiện thông báo Windows (1 lần mỗi đợt)."""
    import json
    told = None
    while not state["stop"]:
        time.sleep(30)
        icon = state.get("icon")
        if icon is None:
            continue
        try:
            d = json.loads((ROOT / "net_state.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        down, now = d.get("down_since"), time.time()
        if down and now - down > 90 and now - d.get("last_fail", 0) < 300:
            since = time.strftime("%H:%M", time.localtime(down))
            icon.title = f"BotHocTap ⚠ mất kết nối Telegram từ {since}"[:120]
            if told != down:
                told = down
                try:
                    icon.notify(f"Từ {since}: {d.get('err', '')}. Bot sẽ tự nối lại và báo trên Telegram khi có mạng.",
                                "BotHocTap mất kết nối Telegram")
                except Exception:
                    pass
        elif icon.title != TITLE:
            icon.title = TITLE


def toggle_viewer(icon=None, item=None):
    v = state["viewer"]
    if v and v.poll() is None:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(v.pid)], creationflags=NO_WINDOW,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        state["viewer"] = None
        return
    state["viewer"] = subprocess.Popen([str(PY), "-X", "utf8", str(ROOT / "bot" / "tail_log.py")],
                                       cwd=str(ROOT), creationflags=NEW_CONSOLE)


def restart(icon=None, item=None):
    kill_bot()  # watchdog sẽ tự chạy lại


def quit_app(icon, item):
    state["stop"] = True
    kill_bot()
    v = state["viewer"]
    if v and v.poll() is None:
        v.kill()
    icon.stop()


def main():
    start_bot()
    threading.Thread(target=watchdog, daemon=True).start()
    menu = pystray.Menu(
        pystray.MenuItem("Xem/ẩn log", toggle_viewer, default=True),
        pystray.MenuItem("Chạy lại bot", restart),
        pystray.MenuItem("Thoát", quit_app))
    icon = pystray.Icon("BotHocTap", Image.open(ROOT / "Logo_tron.png").convert("RGBA").resize((64, 64)), TITLE, menu)
    state["icon"] = icon
    threading.Thread(target=net_watch, daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()
