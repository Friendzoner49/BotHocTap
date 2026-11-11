"""Sổ nợ nhỏ của chủ bot (tạm thời, KHÔNG ghi vào wiki): file cong_no.json cạnh bot, nằm ngoài Git.
Một dòng nhập: «Bình nợ 13k» (Bình nợ tôi 13.000) hoặc «nợ Bình 13k» / «tôi nợ Bình 13k» (tôi nợ Bình).
Tiền tệ mặc định VND, đổi trong phần sửa: USD / RUB / VND."""
import json
import re
import time
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "cong_no.json"
CURS = ("USD", "RUB", "VND")
_CUR_WORDS = {"usd": "USD", "$": "USD", "đô": "USD", "dollar": "USD", "rub": "RUB", "₽": "RUB", "rúp": "RUB", "rup": "RUB",
              "vnd": "VND", "vnđ": "VND", "đ": "VND", "đồng": "VND"}
_AMT = re.compile(r"(\d+(?:[.,]\d+)*)\s*(k|nghìn|ngàn|tr|triệu|m)?\s*(usd|\$|đô|dollar|rub|₽|rúp|rup|vnd|vnđ|đồng|đ)?(?=\s|$)", re.I)  # chữ thừa phía sau (vd «từ hôm qua») bị bỏ qua
ME = r"(?:tôi|tao|tớ|tui|tau|mình|bố\s*mày|bố\s*m|bố(?:\s*đây)?|ông\s*đây|ông\s*mày)"  # cách «tôi» tự xưng, kể cả thân mật/thô
VERB = r"(?:nợ|thiếu|vay|mượn)"
NOT_NAME = re.compile(rf"^(?:{ME}|mày|ai|nó|hắn|ổng|bả|ảnh|chị ấy|anh ấy)$", re.I)
LEND = re.compile(rf"^cho\s+(?P<name>.+?)\s+(?:vay|mượn)\s+(?P<amt>\d.*)$", re.I)              # cho Minh vay 80k → Minh nợ tôi
BORROW = re.compile(rf"^(?P<name>.+?)\s+cho\s+{ME}\s+(?:vay|mượn)\s+(?P<amt>\d.*)$", re.I)     # Minh cho tao vay 80k → tôi nợ Minh
OWE_ME = re.compile(rf"^(?P<name>.+?)\s+{VERB}\s+(?:{ME}\s+)?(?P<amt>\d.*)$", re.I)           # Minh nợ tao 80k / Minh vay 80k
ASP = r"(?:\s+(?:đã|vừa|mới|đang|sẽ))*"
I_OWE = re.compile(rf"^(?:(?:{ME}){ASP}\s+)?{VERB}\s+(?P<name>.+?)\s+(?P<amt>\d.*)$", re.I)        # tao nợ Minh 80k / nợ Minh 80k / vay Minh 80k


ASPECT = re.compile(r"\s+(?:đã|vừa|mới|có|đang|sẽ|vừa mới|mới vừa)$", re.I)   # «Mai đã trả…» → tên là «Mai»
SUSPECT = re.compile(r"\b(?:đã|vừa|mới|đang|sẽ|chưa|rồi|xong|trả|hôm|qua|nay|nợ|vay|mượn|thiếu)\b", re.I)  # tên chứa từ này = hiểu nhầm câu → để Gemini xử lý


HONOR = re.compile(r"^(?:anh|chị|em|bạn|cô|chú|bác|ông|bà|cậu|dì|thím|thằng|con|bé)\s+", re.I)


def key(name: str) -> str:
    """Tên để so khớp: bỏ xưng hô đầu («anh Hùng» = «Hùng»), không phân biệt hoa thường."""
    return HONOR.sub("", name.strip()).casefold()


def parse_amount(s: str):
    """«13k» → (13000, None); «1,5tr» → (1500000, None); «13.000» → (13000, None); «200 usd» → (200, 'USD'). Không hiểu → None."""
    m = _AMT.match(s.strip())
    if not m:
        return None
    num, mult, cur = m.group(1), (m.group(2) or "").lower(), (m.group(3) or "").lower()
    if mult:
        v = float(num.replace(",", "."))
        v *= 1000 if mult in ("k", "nghìn", "ngàn") else 1_000_000
    elif re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", num):  # 13.000 = mười ba nghìn
        v = float(re.sub(r"[.,]", "", num))
    else:
        v = float(num.replace(",", "."))
    return int(round(v)), (_CUR_WORDS.get(cur) if cur else None)


NOTE_SPLIT = re.compile(r"\.(?!\d)|\n")  # dấu chấm (không phải dấu chấm ngăn số như 13.000) hoặc xuống dòng → phần sau là ghi chú


def split_note(text: str):
    """«Bình nợ 13k. tiền cơm» → ('Bình nợ 13k', 'tiền cơm'). Không có dấu chấm/xuống dòng → không có ghi chú."""
    m = NOTE_SPLIT.search(text)
    if not m:
        return text.strip(), ""
    return text[:m.start()].strip(), text[m.end():].strip(" .,;:\n\t")[:200]


def parse(text: str):
    """«Bình nợ 13k» → {'name','dir','amount','cur'}; dir = 'owe_me' (người đó nợ tôi) hoặc 'i_owe' (tôi nợ). Không khớp → None."""
    t, note = split_note(text.strip())
    if len(t) > 80:
        return None
    for rx, direction in ((LEND, "owe_me"), (BORROW, "i_owe"), (I_OWE, "i_owe"), (OWE_ME, "owe_me")):
        m = rx.match(t)
        if m:
            a = parse_amount(m.group("amt"))
            name = m.group("name").strip(" ,.:;")
            if a and a[0] > 0 and name and len(name) <= 40 and not NOT_NAME.match(name) and not SUSPECT.search(name):
                return {"name": name, "dir": direction, "amount": a[0], "cur": a[1] or "VND", "note": note}
    return None


def load() -> list:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save(rows: list):
    FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def add(name: str, direction: str, amount: int, cur: str = "VND", note: str = "") -> tuple:
    """Cộng dồn nếu đã có cùng người + chiều + tiền tệ. Trả (dòng, số tiền trước đó hoặc 0)."""
    rows = load()
    same = next((r for r in rows if key(r["name"]) == key(name) and r["dir"] == direction and r["cur"] == cur), None)
    if same:
        before = same["amount"]
        same["amount"] += amount
        if note:
            same["note"] = f"{same['note']}; {note}" if same.get("note") else note
        save(rows)
        return same, before
    row = {"id": max([r["id"] for r in rows], default=0) + 1, "name": name, "dir": direction, "amount": amount, "cur": cur,
           "note": note, "added": time.strftime("%Y-%m-%d")}
    rows.append(row)
    save(rows)
    return row, 0


def get(row_id: int):
    return next((r for r in load() if r["id"] == row_id), None)


def update(row_id: int, **kw):
    rows = load()
    r = next((r for r in rows if r["id"] == row_id), None)
    if r:
        r.update(kw)
        save(rows)
    return r


def remove(row_id: int):
    rows = load()
    gone = next((r for r in rows if r["id"] == row_id), None)
    if gone:
        save([r for r in rows if r["id"] != row_id])
    return gone


def fmt(amount: int, cur: str) -> str:
    return f"{amount:,}".replace(",", ".") + f" {cur}"


def task_text(r: dict, day: str) -> str:
    """Nội dung việc tạo từ một khoản nợ."""
    money = fmt(r["amount"], r["cur"]) + (f" ({r['note']})" if r.get("note") else "")
    if r["dir"] == "i_owe":
        return f"Trả nợ {r['name']} {money} vào {day}"
    return f"Nhắc {r['name']} trả {money} vào {day}"


ALL = r"(?:hết|xong|đủ|sạch)"
I_PAY = re.compile(rf"^(?:(?:{ME}){ASP}\s+)?trả\s+(?:nợ\s+)?(?P<name>.+?)\s+(?P<amt>\d.*|{ALL}(?:\s.*)?)$", re.I)       # tao trả Bình 5k / trả Bình hết
PAY_ME = re.compile(rf"^(?P<name>.+?)\s+trả\s+(?:nợ\s+)?(?:{ME}\s+)?(?P<amt>\d.*|{ALL}(?:\s.*)?)$", re.I)           # Bình trả tao 5k / Bình trả hết


def parse_pay(text: str):
    """«Bình trả 5k» → {'name','dir':'owe_me','amount':5000,'cur':None}; «tao trả Bình hết» → dir 'i_owe', amount None (= trả hết).
    Chỉ nhận dạng cú pháp; việc khớp với khoản nợ có thật do pay() kiểm tra."""
    t, _ = split_note(text.strip())
    if len(t) > 80:
        return None
    for rx, direction in ((I_PAY, "i_owe"), (PAY_ME, "owe_me")):
        m = rx.match(t)
        if not m:
            continue
        name = ASPECT.sub("", m.group("name").strip(" ,.:;"))
        if not name or len(name) > 40 or NOT_NAME.match(name) or SUSPECT.search(name):
            continue
        amt = m.group("amt").strip()
        if re.match(ALL, amt, re.I):
            return {"name": name, "dir": direction, "amount": None, "cur": None}
        a = parse_amount(amt)
        if a and a[0] > 0:
            return {"name": name, "dir": direction, "amount": a[0], "cur": a[1]}
    return None


def pay(p: dict):
    """Trừ nợ. Trả (trạng thái, dữ liệu): 'none' (không có khoản này), 'many' (nhiều tiền tệ, cần nói rõ; dữ liệu = danh sách đơn vị),
    'paid' (đã trả hết, dòng bị xóa; dữ liệu = (dòng, trả dư)), 'left' (còn nợ; dữ liệu = (dòng, số đã trả))."""
    rows = [r for r in load() if key(r["name"]) == key(p["name"]) and r["dir"] == p["dir"]]
    if p.get("cur"):
        rows = [r for r in rows if r["cur"] == p["cur"]]
    if not rows:
        return "none", None
    if len(rows) > 1 and p["amount"] is not None:
        return "many", [r["cur"] for r in rows]
    if p["amount"] is None:  # trả hết: xóa mọi khoản khớp
        for r in rows:
            remove(r["id"])
        return "paid", (rows[0], 0)
    r = rows[0]
    if p["amount"] >= r["amount"]:
        remove(r["id"])
        return "paid", (r, p["amount"] - r["amount"])
    update(r["id"], amount=r["amount"] - p["amount"])
    return "left", (get(r["id"]), p["amount"])
