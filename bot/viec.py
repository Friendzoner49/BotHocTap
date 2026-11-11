"""Danh sách việc cần làm, lưu trong MỘT file Markdown (mở được bằng Obsidian), không tốn tiền, không cần AI.
Ba nhãn: Gấp (hạn 2 ngày), Quan trọng (hạn 4 ngày, còn ≤ 2 ngày thì tự lên Gấp), Để sau (hỏi lại sau 7 ngày).
Mỗi việc một dòng:  - [ ] #3 Làm Работа 5 · thêm 2026-11-04 · hạn 2026-11-06   (Để sau: «· hỏi lại 2026-11-11»)
Bạn sửa tay trong Obsidian cũng được; dòng thiếu ngày thì coi như thêm hôm nay."""
import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import wikilink  # noqa: E402
_wiki = os.environ.get("WIKI_DIR")
FILE = (Path(_wiki) / "wiki" / "projects" / "bothoctap" / "viec-can-lam.md") if _wiki else ROOT / "viec_can_lam.md"
COUNT = ROOT / "viec_dem.json"          # {id: {"hoan": số lần bấm «Chưa» buổi tối, "hoi": số lần hoãn «Để sau»}}
HISTORY = ROOT / "viec_lich_su.jsonl"   # mỗi việc đã xong (lúc dọn): ngày, tên, nhãn; dùng cho báo cáo cuối tuần
LABELS = {"gap": "Gấp", "quantrong": "Quan trọng", "desau": "Để sau"}
DEFAULT_DAYS = {"gap": 2, "quantrong": 4, "desau": 7}
HEAD = ("---\ntype: tasks\nproject: bothoctap\nupdated: {d}\nsources: []\n---\n# Việc cần làm\n"
        "Hub: [[bothoctap]]. Bot Telegram nhắc 9h sáng và hỏi lại buổi tối với việc Gấp; tích [x] khi xong (bot hoặc Obsidian đều được), sáng hôm sau bot xóa các dòng đã tích.\n\n")
ITEM = re.compile(r"^- \[([ xX])\] #(\d+) (.*?)(?: · thêm (\d{4}-\d\d-\d\d))?(?: · (?:hạn|hỏi lại) (\d{4}-\d\d-\d\d))?(?: · 🔗 (.+?))?\s*$")


def _d(s: str | None, default: date) -> date:
    try:
        return date.fromisoformat(s) if s else default
    except ValueError:
        return default


def load() -> list[dict]:
    """[{id, text, label, added, due}] theo thứ tự trong file."""
    if not FILE.exists():
        return []
    items, label = [], None
    for ln in FILE.read_text(encoding="utf-8").splitlines():
        h = re.match(r"^##\s+(.+?)\s*$", ln)
        if h:
            label = next((k for k, v in LABELS.items() if v.casefold() == h.group(1).casefold()), None)
            continue
        m = ITEM.match(ln)
        if m and label:
            today = date.today()
            added = _d(m.group(4), today)
            items.append({"id": int(m.group(2)), "text": m.group(3).strip(), "label": label, "added": added,
                          "done": m.group(1).lower() == "x", "link": (m.group(6) or "").strip(),
                          "due": _d(m.group(5), added + timedelta(days=DEFAULT_DAYS[label]))})
    return items


def save(items: list[dict]):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    out = [HEAD.format(d=date.today().isoformat())]
    for key, name in LABELS.items():
        out.append(f"## {name}\n")
        for it in sorted((i for i in items if i["label"] == key), key=lambda i: i["due"]):
            tag = "hỏi lại" if key == "desau" else "hạn"
            out.append(f"- [{'x' if it.get('done') else ' '}] #{it['id']} {it['text']} · thêm {it['added']} · {tag} {it['due']}"
                       + (f" · 🔗 {it['link']}" if it.get("link") else "") + "\n")
        out.append("\n")
    FILE.write_text("".join(out), encoding="utf-8")


def parse_due(s: str) -> date | None:
    """«7/11», «07/11/2026», «2026-11-07», «hôm nay», «mai», «mốt», «3 ngày» → date; không hiểu thì None."""
    s, today = s.strip().lower(), date.today()
    if not re.fullmatch(r"[\d/.\-\s]+|\d+\s*ngày", s):  # chữ tự nhiên («thứ sáu tuần sau», «mùng 10»…) → bộ tìm cụm ngày
        w = parse_in_text(s)
        if w:
            return w
    fixed ={"hôm nay": 0, "nay": 0, "mai": 1, "ngày mai": 1, "mốt": 2, "ngày mốt": 2, "ngày kia": 2}
    if s in fixed:
        return today + timedelta(days=fixed[s])
    m = re.fullmatch(r"(\d+)\s*ngày", s)
    if m:
        return today + timedelta(days=int(m.group(1)))
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    try:
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?", s)
        if m:
            y = int(m.group(3)) if m.group(3) else today.year
            y += 2000 if y < 100 else 0
            d = date(y, int(m.group(2)), int(m.group(1)))
            return d.replace(year=y + 1) if (not m.group(3) and (today - d).days > 60) else d  # quên ghi năm: ngày đã qua lâu → năm sau
    except ValueError:
        return None
    return None


WEEKDAYS = ["Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy", "Chủ nhật"]
_WD = {"hai": 0, "2": 0, "ba": 1, "3": 1, "tư": 2, "4": 2, "năm": 3, "5": 3, "sáu": 4, "6": 4, "bảy": 5, "7": 5}


def day_name(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d.strftime('%d/%m')}"


def parse_in_text(text: str) -> date | None:
    """Tìm cụm ngày trong câu tự nhiên: «thứ sáu tuần sau», «thứ bảy tuần tới», «chủ nhật», «mùng 10», «ngày 15/11»,
    «mai», «mốt», «3 ngày nữa», «2 tuần nữa», «cuối tuần». Tuần tính từ thứ hai đến chủ nhật. Không thấy thì None."""
    s, today = text.lower(), date.today()
    monday = today - timedelta(days=today.weekday())
    m = re.search(r"(?:thứ\s*(hai|ba|tư|năm|sáu|bảy|[2-7])|(chủ\s*nhật|\bcn\b))(?:\s*(tuần\s*(?:sau|tới|này|nay|trước)))?", s)
    if m:
        wd = 6 if m.group(2) else _WD[m.group(1)]
        week = (m.group(3) or "")
        if re.search(r"sau|tới", week):
            return monday + timedelta(days=7 + wd)
        if re.search(r"này|nay", week):
            return monday + timedelta(days=wd)
        if "trước" in week:
            return monday + timedelta(days=wd - 7)
        d = monday + timedelta(days=wd)  # không nói tuần: lần sắp tới (kể cả hôm nay)
        return d if d >= today else d + timedelta(days=7)
    m = re.search(r"(\d{1,2})\s*(?:/|\.|-)\s*(\d{1,2})(?:\s*(?:/|\.|-)\s*(\d{2,4}))?", s)
    if m:
        d = parse_due(m.group(0).replace(" ", ""))
        if d:
            return d
    m = re.search(r"(?:mùng|mồng|ngày)\s*(\d{1,2})(?:\s*tháng\s*(\d{1,2}))?", s)
    if m and 1 <= int(m.group(1)) <= 31:
        day, mon = int(m.group(1)), int(m.group(2) or 0)
        try:
            if mon:
                d = date(today.year, mon, day)
                return d if (today - d).days <= 60 else date(today.year + 1, mon, day)
            d = date(today.year, today.month, day)
            if d < today:  # «mùng 10» đã qua tháng này → tháng sau
                y, mo = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
                d = date(y, mo, day)
            return d
        except ValueError:
            return None
    m = re.search(r"(\d+)\s*(ngày|tuần)\s*(?:nữa|tới|sau)", s)
    if m:
        return today + timedelta(days=int(m.group(1)) * (7 if m.group(2) == "tuần" else 1))
    if "cuối tuần" in s:
        return monday + timedelta(days=5)
    if re.search(r"hôm nay|\bnay\b|tối nay|sáng nay", s):
        return today
    if re.search(r"ngày kia|\bmốt\b", s):
        return today + timedelta(days=2)
    if re.search(r"\bmai\b|ngày mai", s):
        return today + timedelta(days=1)
    return None


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):  # ngày 31 sang tháng ngắn → lùi về cuối tháng
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return d


def suggest_same(text: str) -> date | None:
    """«tuần sau» → cùng thứ tuần sau (+7 ngày); «tháng sau/tới» → cùng ngày tháng sau; «năm sau/tới» → cùng ngày năm sau.
    Cụm có cuối/đầu/giữa (vd «giữa tháng sau») để Gemini đoán, nên trả None."""
    s, today = text.lower(), date.today()
    if re.search(r"(?:cuối|đầu|giữa)\s*(?:tuần|tháng|năm|kỳ)", s):
        return None
    if re.search(r"tuần\s*(?:sau|tới)", s):
        return today + timedelta(days=7)
    if re.search(r"tháng\s*(?:sau|tới)", s):
        return _add_months(today, 1)
    if re.search(r"năm\s*(?:sau|tới)", s):
        return _add_months(today, 12)
    return None


def label_for(due: date | None) -> str:
    """Có hạn chót: còn ≤ 2 ngày → Gấp, ngược lại Quan trọng; không có hạn → Để sau."""
    if due is None:
        return "desau"
    return "gap" if (due - date.today()).days <= 2 else "quantrong"


def add(text: str, due: date | None = None) -> dict:
    items = load()
    today = date.today()
    label = label_for(due)
    it = {"id": max([i["id"] for i in items], default=0) + 1, "text": text.strip().replace("\n", " "), "label": label,
          "added": today, "due": due or today + timedelta(days=DEFAULT_DAYS["desau"]), "link": wikilink.find(text)}  # [[trang môn]] cho Obsidian
    items.append(it)
    save(items)
    return it


def remove(item_id: int) -> dict | None:
    items = load()
    gone = next((i for i in items if i["id"] == item_id), None)
    if gone:
        save([i for i in items if i["id"] != item_id])
        _forget([item_id])
    return gone


def update(item_id: int, **kw) -> dict | None:
    items = load()
    it = next((i for i in items if i["id"] == item_id), None)
    if it:
        if "text" in kw and "link" not in kw:
            kw["link"] = wikilink.find(kw["text"])  # đổi tên việc thì gắn lại liên kết môn
        it.update(kw)
        save(items)
    return it


def promote() -> list[dict]:
    """Quan trọng còn ≤ 2 ngày → Gấp. Trả về danh sách việc vừa được nâng."""
    items, moved = load(), []
    for it in items:
        if it["label"] == "quantrong" and not it.get("done") and (it["due"] - date.today()).days <= 2:
            it["label"] = "gap"
            moved.append(it)
    if moved:
        save(items)
    return moved


def checkin_due() -> list[dict]:
    """Việc «Để sau» đến hạn hỏi lại (đủ 7 ngày)."""
    return [i for i in load() if i["label"] == "desau" and not i.get("done") and i["due"] <= date.today()]


def toggle(item_id: int) -> dict | None:
    items = load()
    it = next((i for i in items if i["id"] == item_id), None)
    if it:
        it["done"] = not it.get("done")
        save(items)
    return it


def _counts() -> dict:
    try:
        return json.loads(COUNT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def bump(item_id: int, key: str) -> int:
    c = _counts()
    c.setdefault(str(item_id), {}).setdefault(key, 0)
    c[str(item_id)][key] += 1
    COUNT.write_text(json.dumps(c), encoding="utf-8")
    return c[str(item_id)][key]


def count(item_id: int, key: str) -> int:
    return _counts().get(str(item_id), {}).get(key, 0)


def _forget(ids):
    c = _counts()
    if any(str(i) in c for i in ids):
        for i in ids:
            c.pop(str(i), None)
        COUNT.write_text(json.dumps(c), encoding="utf-8")


def purge_done() -> int:
    """Xóa các việc đã tích [x]. Trả về số việc đã xóa."""
    items = load()
    keep = [i for i in items if not i.get("done")]
    gone = [i for i in items if i.get("done")]
    if gone:
        with open(HISTORY, "a", encoding="utf-8") as f:  # nhớ việc đã xong để báo cáo tuần
            for i in gone:
                f.write(json.dumps({"ts": date.today().isoformat(), "text": i["text"], "label": i["label"],
                                    "hoan": count(i["id"], "hoan")}, ensure_ascii=False) + "\n")
        save(keep)
        _forget([i["id"] for i in gone])
    return len(gone)


def week_report() -> str:
    """Báo cáo 7 ngày qua: việc đã xong, việc còn mở theo nhãn, việc hay bị hoãn, việc quá hạn. Không dùng AI."""
    since = (date.today() - timedelta(days=7)).isoformat()
    done = []
    if HISTORY.exists():
        for ln in HISTORY.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get("ts", "") >= since:
                done.append(r)
    items = load()
    ticked = [i for i in items if i.get("done")]
    openi = [i for i in items if not i.get("done")]
    today = date.today()
    out = ["📊 Tuần qua", ""]
    n_done = len(done) + len(ticked)
    out.append(f"✅ Đã xong: {n_done} việc")
    out += [f"  • {r['text']}" for r in done[-8:]] + [f"  • {i['text']}" for i in ticked]
    out.append("")
    out.append("📌 Còn mở: " + ", ".join(f"{len([i for i in openi if i['label'] == k])} {LABELS[k]}" for k in LABELS))
    late = [i for i in openi if i["label"] != "desau" and i["due"] < today]
    if late:
        out.append("⚠ Quá hạn: " + "; ".join(f"#{i['id']} {i['text']} ({-(i['due'] - today).days} ngày)" for i in late))
    slow = [i for i in openi if count(i["id"], "hoan") >= 2 or count(i["id"], "hoi") >= 2]
    if slow:
        out.append("⏳ Hay bị hoãn: " + "; ".join(f"#{i['id']} {i['text']}" for i in slow))
    nxt = sorted([i for i in openi if i["label"] != "desau" and i["due"] >= today], key=lambda i: i["due"])[:3]
    if nxt:
        out.append("➡ Sắp tới: " + "; ".join(f"{i['text']} ({day_name(i['due'])})" for i in nxt))
    if n_done == 0 and not openi:
        return ""
    return "\n".join(out)


def left(it: dict) -> str:
    n = (it["due"] - date.today()).days
    return "quá hạn %d ngày" % -n if n < 0 else ("hôm nay" if n == 0 else "còn %d ngày" % n)


def plan_week() -> str:
    """Kế hoạch tuần tới (gửi sáng thứ Hai): quá hạn, việc theo từng ngày T2→CN, việc không hạn đáng chú ý. Không dùng AI."""
    today = date.today()
    mon = today - timedelta(days=today.weekday())
    openi = [i for i in load() if not i.get("done")]
    out = [f"🗓 Kế hoạch tuần {mon.strftime('%d/%m')} – {(mon + timedelta(days=6)).strftime('%d/%m')}", ""]
    late = [i for i in openi if i["label"] != "desau" and i["due"] < mon]
    if late:
        out.append("⚠ Quá hạn từ tuần trước:")
        out += [f"  • #{i['id']} {i['text']} ({-(i['due'] - today).days} ngày)" for i in sorted(late, key=lambda i: i["due"])]
        out.append("")
    any_day = False
    for k in range(7):
        d = mon + timedelta(days=k)
        part = [i for i in openi if i["label"] != "desau" and i["due"] == d]
        if part:
            any_day = True
            out.append(day_name(d) + (" (hôm nay)" if d == today else ""))
            out += [f"  • #{i['id']} {i['text']}" for i in part]
    if not any_day:
        out.append("Tuần này chưa có việc nào có hạn.")
    later = [i for i in openi if i["label"] != "desau" and i["due"] > mon + timedelta(days=6)]
    if later:
        nxt = sorted(later, key=lambda i: i["due"])[:3]
        out += ["", "👀 Sau tuần này: " + "; ".join(f"{i['text']} ({i['due'].strftime('%d/%m')})" for i in nxt)]
    desau = [i for i in openi if i["label"] == "desau"]
    if desau:
        out += ["", f"🟢 Để sau: {len(desau)} việc, tuần này có muốn làm việc nào không? Gõ /viec để xem."]
    out += ["", "Thêm việc cho tuần: nhắn «nộp lab 5 thứ sáu», hoặc dán đề vào /viec."]
    return "\n".join(out)
