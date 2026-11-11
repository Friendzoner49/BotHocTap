"""Cầu nối tới app 705bot (chạy bằng python của 705bot/.venv, KHÔNG bằng .venv của BotHocTap).
  list [N]        → JSON các hóa đơn gần nhất (chỉ đọc, mở DB ở chế độ read-only)
  send <id>       → gửi đúng như nút «Gửi hóa đơn cho khách (Telegram)» của app (cùng hàm, cùng mã đồng bộ)
Chỉ BotHocTap gọi `send`, và chỉ sau khi chủ bấm ✅ trên Telegram."""
import json
import os
import sqlite3
import sys
from pathlib import Path

SRC = Path(os.environ.get("APP705_DIR", "705bot")) / "src"
sys.path.insert(0, str(SRC))
from shop.db.migrate import _vn_collate  # noqa: E402
from shop.paths import bot_sync_settings, db_path  # noqa: E402


def _conn(ro: bool):
    p = Path(db_path())
    c = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True) if ro else sqlite3.connect(p)
    c.execute("PRAGMA foreign_keys = ON")
    c.create_collation("VNAME", _vn_collate)
    return c


def rows(n=30):
    c = _conn(True)
    q = ("SELECT i.id, c.name, i.invoice_date, i.status, i.telegram_sent_at, "
         "(SELECT COUNT(*) FROM telegram_customer_links l WHERE l.customer_id = i.customer_id) "
         "FROM invoices i JOIN customers c ON c.id = i.customer_id ORDER BY i.invoice_date DESC, i.id DESC LIMIT ?")
    out = []
    from shop.core.invoices import get_invoice
    for id_, name, day, st, sent, links in c.execute(q, (n,)).fetchall():
        inv = get_invoice(c, id_)
        out.append({"id": id_, "customer": name, "date": day, "status": st, "sent": bool(sent), "linked": links > 0,
                    "total": inv["total"] if inv else None})
    return out


def preview(inv_id):
    from shop.core.invoice_send import build_invoice_message
    return build_invoice_message(_conn(True), inv_id)


def send(inv_id):
    from shop.core.invoice_send import InvoiceSendError, send_invoice_to_customer
    url, secret = bot_sync_settings()
    c = _conn(False)
    try:
        return {"ok": True, "chats": send_invoice_to_customer(c, inv_id, url, secret)}
    except InvoiceSendError as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    if cmd == "list":
        r = rows(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    elif cmd == "preview":
        r = {"text": preview(int(sys.argv[2]))}
    elif cmd == "send":
        r = send(int(sys.argv[2]))
    else:
        raise SystemExit("lệnh không hợp lệ")
    print(json.dumps(r, ensure_ascii=False))
