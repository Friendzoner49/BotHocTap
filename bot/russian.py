"""Bài tiếng Nga giao tiếp mỗi sáng (nhét vào tin 9:00). Gemini soạn theo chủ đề của ngày, tránh cụm đã học (ru_state.json),
thứ Tư/thứ Sáu lấy thuật ngữ từ CHÍNH bài giảng của chủ (đoạn ngẫu nhiên trong chỉ mục), Chủ nhật ôn lại tuần. Dữ liệu cá nhân, gitignore."""
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "ru_state.json"
KEEP = 150

THEMES = {
    0: ("trường đại học: hỏi giảng viên, xin nhắc lại, xin lùi hạn, hẹn gặp (nói «вы» lịch sự)", False),
    1: ("phòng lab và nộp bài: báo đã làm xong, xin kiểm tra, bảo vệ lab, sửa lỗi theo yêu cầu", False),
    2: ("thuật ngữ chuyên ngành từ bài giảng của bạn", True),
    3: ("đời sống hằng ngày ở Nga: cửa hàng, phương tiện, nhờ giúp đỡ, hỏi đường", False),
    4: ("thuật ngữ chuyên ngành từ bài giảng của bạn", True),
    5: ("cuối tuần thoải mái: rủ bạn đi chơi, ăn uống, xem phim, trò chuyện", False),  # thứ Bảy: bài nhẹ (3 mục, không hội thoại)
    6: (None, False),  # Chủ nhật: ôn lại
}


BAD = re.compile("[\u0300\u0301\u0306\u0308ґєіїҐЄІЇѓќ\u0600-\u06FF\u4e00-\u9fff]")  # dấu kết hợp, chữ Ukraina, Ả Rập, Hán: dấu hiệu Gemini viết hỏng tiếng Nga
VERIFY = ("Bạn là người Nga bản ngữ chấm bài. Kiểm tra từng câu/cụm tiếng Nga dưới đây: chính tả, ngữ pháp, độ tự nhiên. Sửa nếu sai; GIỮ NGUYÊN định dạng, số thứ tự, "
          "bản dịch tiếng Việt (chỉ sửa bản dịch và cách đọc nếu bạn đổi câu Nga). Trọng âm viết bằng cách VIẾT HOA nguyên âm (извинИте), KHÔNG dùng dấu kết hợp. "
          "Chỉ trả lại bài đã sửa, không giải thích.\n\n")


MIXED = re.compile("[A-Za-z][А-Яа-яЁё]|[А-Яа-яЁё][A-Za-z]")  # chữ Latinh lẫn trong một từ Nga (vd «кOфе» với O Latinh): lỗi giả chữ


def _bad(t: str) -> bool:
    t = unicodedata.normalize("NFC", t)
    return bool(BAD.search(t) or MIXED.search(t))


def _items(t: str) -> int:
    return len(re.findall(r"^\s*\d+[.)]\s", t, re.M))


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"used": []}


def lesson(ask, source=None, today: date | None = None) -> str:
    """ask(prompt) → văn bản hoặc None; source() → (môn, đoạn chữ bài giảng) hoặc None. Trả '' nếu không soạn được (tin sáng bỏ qua phần này)."""
    today = today or date.today()
    d = _load()
    if d.get("last") == today.isoformat() and d.get("text"):
        return d["text"]  # gọi lại trong ngày (vd gửi bù/thử lại): giữ nguyên bài, không đổi
    theme, from_lectures = THEMES[today.weekday()]
    if theme is None:
        old = d.get("used", [])[-7:]
        if not old:
            return ""
        text = "🇷🇺 Tiếng Nga — ôn lại tuần (nhẩm nghĩa trước khi nhìn bản dịch):\n" + "\n".join(f"  {x}" for x in old)
        return _store(d, today, text, [])
    used = "; ".join(x.split(" — ")[0] for x in d.get("used", [])[-40:]) or "(chưa có)"
    light = today.weekday() == 5
    head = ("Bạn là giáo viên tiếng Nga cho sinh viên Việt Nam năm cuối ngành CNTT đang học tại Nga (trình độ A2–B1). Tạo bài ngắn để đọc lúc ngủ dậy. ")
    if light:
        shape = "Cuối tuần nên bài NHẸ: đúng 3 mục đánh số 1–3, KHÔNG có hội thoại, tổng dưới 450 ký tự. "
    else:
        shape = "Gồm đúng 5 mục đánh số 1–5, rồi 1 hội thoại 2 câu «А: … / Б: …» có dịch tiếng Việt ngay sau; tổng dưới 1000 ký tự. "
    base = (head + shape + "Mỗi mục MỘT dòng theo mẫu: «Русская фраза — nghĩa tiếng Việt — cách đọc bằng chữ Latinh». Trọng âm: VIẾT HOA nguyên âm có trọng âm (cả trong câu Nga lẫn cách đọc, vd извинИте / izvinIte); TUYỆT ĐỐI không dùng dấu kết hợp, không dùng chữ Ukraina/Ả Rập/Hán; chỉ dùng chữ Nga, chữ Latinh, tiếng Việt. "
            "Phải là câu người Nga dùng thật; nói với giảng viên dùng «вы». "
            f"KHÔNG lặp các cụm đã học: {used}. Không markdown, không emoji." + chr(10) + chr(10))
    if from_lectures:
        src = source() if source else None
        if not src:
            theme, from_lectures = THEMES[0][0], False
        else:
            subj, chunk = src
            theme = f"thuật ngữ chuyên ngành lấy từ bài giảng môn {subj}"
            base += (f"CHỦ ĐỀ: {theme}. Dưới đây là một đoạn trong bài giảng của sinh viên. Chọn 5 thuật ngữ/cụm tiếng Nga quan trọng trong đoạn "
                     "(nếu đoạn viết tiếng Việt thì chọn thuật ngữ chuyên ngành tiếng Nga tương ứng nội dung); hội thoại cuối là câu hỏi sinh viên hỏi giảng viên về một thuật ngữ đó.\n\nĐOẠN:\n"
                     + chunk[:1800])
    if not from_lectures:
        base += f"CHỦ ĐỀ: {theme}."
    out = None
    for _ in range(3):  # Gemini hay chèn ký tự hỏng vào tiếng Nga: kiểm tra, hỏng thì xin lại
        t = ask(base)
        if t and not _bad(t) and _items(t) >= (3 if light else 5):
            out = t.strip().replace("**", "")
            break
    if not out:
        return ""  # thà bỏ phần tiếng Nga hôm nay còn hơn gửi câu sai
    chk = ask(VERIFY + out)  # lượt 2: «người Nga bản ngữ» soát chính tả/ngữ pháp
    if chk and not _bad(chk) and _items(chk) == _items(out):
        out = chk.strip().replace("**", "")
    lines = [re.sub(r"^\d+[.)]\s*", "", ln.strip()) for ln in out.splitlines() if re.match(r"^\s*\d+[.)]\s", ln)]
    text = f"🇷🇺 Tiếng Nga hôm nay — {theme.split(':')[0]}\n{out}"
    return _store(d, today, text, lines)


RU_V, LAT_V = "аеёиоуыэюяАЕЁИОУЫЭЮЯ", "aeiouyAEIOUY"
LAT_ACC = dict(zip("aeiouy", "áéíóúý"))
ACUTE = "́"


def _stress_word(w: str, mid: bool, cyr: bool) -> str:
    """«ИзвинИте» → «Извини́те», «раБОту» → «рабо́ту», «izvinIte» → «izviníte». Gemini đánh trọng âm bằng chữ HOA (vì dấu kết hợp
    nó hay viết hỏng); bot tự đổi sang dấu trọng âm chuẩn. Chữ hoa đầu câu giữ nguyên; phụ âm bị viết hoa nhầm thì hạ xuống."""
    vowels = RU_V if cyr else LAT_V
    ups = [i for i, c in enumerate(w) if c.isupper()]
    if not ups:
        return w
    inner = [i for i in ups if i > 0 and w[i] in vowels]
    first_cap = w[0].isupper()
    if not inner and first_cap and mid and w[0] in vowels and len(w) > 1:
        inner = [0]  # «Этого» giữa câu = trọng âm ở chữ đầu
    if not inner and len(ups) == len(w) and len(w) > 1:
        return w  # viết tắt (ПК, SQL)
    st = inner[0] if inner else None
    out = []
    for i, c in enumerate(w):
        keep_cap = i == 0 and first_cap and not (mid and st == 0)
        ch = c if keep_cap else c.lower()
        if i == st:
            ch = (LAT_ACC.get(ch, ch) if not cyr else ch + ACUTE) if not (cyr and ch in "ёЁ") else ch
        out.append(ch)
    return "".join(out)


def _stress(s: str) -> str:
    out, mid = [], False
    for tok in re.split(r"(\s+)", s):
        if not tok.strip():
            out.append(tok)
            continue
        m = re.match(r"^([«(\"'“]*)([A-Za-zА-Яа-яЁё'-]+)(.*)$", tok)
        if m:
            cyr = bool(re.search("[А-Яа-яЁё]", m.group(2)))
            tok = m.group(1) + "-".join(_stress_word(p, mid or i > 0, cyr) for i, p in enumerate(m.group(2).split("-"))) + m.group(3)
        out.append(tok)
        mid = not re.search(r"[.!?:]$|^[—–-]$", tok)
    return "".join(out)


def pretty(text: str) -> str:
    """Trình bày cho điện thoại: mỗi mục 3 dòng (câu Nga / nghĩa / cách đọc), hội thoại xuống dòng phần dịch, dấu trọng âm chuẩn."""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        m = re.match(r"^(\d+[.)])\s*(.+)$", s)
        num, body = (m.group(1), m.group(2)) if m else ("", s)
        parts = [p.strip() for p in re.split(r"\s+[—–]\s+", body)]
        if len(parts) == 3 and re.search("[А-Яа-яЁё]", parts[0]) and not s.startswith("🇷🇺"):
            out += [f"{num or '•'} {_stress(parts[0])}", f"    ➜ {parts[1]}", f"    🔈 {_stress(parts[2])}", ""]
            continue
        dm = re.match(r"^([АБAB]):\s*(.+?)\s*\(([^()]+)\)\s*$", s)
        if dm:  # «А: câu Nga (dịch)»
            out += [f"{dm.group(1)}: {_stress(dm.group(2))}", f"    ➜ {dm.group(3)}"]
            continue
        out.append(_stress(s) if re.search("[А-Яа-яЁё]", s) and not s.startswith("🇷🇺") else s)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _store(d: dict, today: date, text: str, lines: list) -> str:
    d["used"] = (d.get("used", []) + lines)[-KEEP:]
    d["last"], d["text"] = today.isoformat(), text
    STATE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return text
