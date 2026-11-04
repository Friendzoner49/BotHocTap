"""Đặt mật khẩu đăng nhập cho điện thoại khác. Chạy bằng set_password.bat."""
import getpass
import json
from pathlib import Path

import bcrypt

pw = getpass.getpass("Mật khẩu mới (gõ không hiện chữ): ")
if len(pw) < 8:
    raise SystemExit("Mật khẩu phải từ 8 ký tự trở lên.")
if pw != getpass.getpass("Nhập lại: "):
    raise SystemExit("Hai lần nhập không khớp.")
h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
(Path(__file__).resolve().parent.parent / "password.json").write_text(json.dumps({"hash": h}), encoding="utf-8")
print("Đã lưu. Khởi động lại bot để áp dụng.")
