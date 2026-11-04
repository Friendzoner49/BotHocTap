"""Cửa sổ xem log bot (mở từ khay hệ thống)."""
import time
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "bot.log"
print("=== BotHocTap log (bấm lại biểu tượng ở khay để đóng cửa sổ này) ===\n", flush=True)
with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    for line in f.readlines()[-40:]:
        print(line, end="")
    while True:
        line = f.readline()
        if line:
            print(line, end="", flush=True)
        else:
            time.sleep(0.5)
