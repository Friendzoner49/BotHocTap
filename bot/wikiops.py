"""Dùng chung cho /capnhat (main.py) và cập nhật hằng tuần (weekly.py): bộ đếm + lời nhắc kiểm tra/dọn wiki (lint),
và hàng chờ MÂU THUẪN: Claude ghi hai ý đối nghịch ra wiki/_mau-thuan.json, chủ bấm nút trên Telegram, bot tự sửa bằng mã (không gọi Claude)."""
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINT_STATE = ROOT / "lint_state.json"  # {"since": số nguồn đã nạp từ lần kiểm tra wiki gần nhất}
LINT_EVERY = 10  # đủ 10 nguồn mới tự kiểm tra wiki (đúng quy ước trong CLAUDE.md của kho)
MT_REL = "wiki/_mau-thuan.json"  # nằm trong kho (có git), không phải .md nên không vào chỉ mục của bot
MT_RULE = (
    "MÂU THUẪN (hai ý đối nghịch nhau về cùng một điều): KHÔNG tự chọn, KHÔNG hỏi bằng chữ. Giữ nguyên cả hai ý trong trang kèm `⚠ Mâu thuẫn:` "
    f"rồi thêm một mục vào danh sách `cho` của file `{MT_REL}` (JSON; chưa có thì tạo: {{\"cho\": [], \"giu_ca_hai\": []}}; giữ nguyên các mục đang có). "
    "Mỗi mục: {\"chu_de\": \"tên ngắn\", \"y1\": \"ý 1, kèm nguồn và ngày\", \"y2\": \"ý 2, kèm nguồn và ngày\", "
    "\"giu_y1\": [{\"file\": \"wiki/….md\", \"cu\": \"đoạn NGUYÊN VĂN đang có trong file\", \"moi\": \"đoạn thay thế\"}], \"giu_y2\": [như trên]}. "
    "`giu_y1` là mọi chỗ cần sửa nếu tôi chọn ý 1 (xóa ý 2 và dấu ⚠ Mâu thuẫn ở mọi trang có nó), `giu_y2` ngược lại. `cu` phải chép đúng từng ký tự, "
    "đủ dài để chỉ xuất hiện MỘT lần trong file; `moi` có thể rỗng. Ghi TẤT CẢ mâu thuẫn tìm thấy, không giới hạn số. "
    "Mâu thuẫn có `chu_de` nằm trong `giu_ca_hai` là tôi đã chọn giữ cả hai: không ghi lại. "
)
LINT_PROMPT = (
    "Chạy tự động, không có người trả lời giữa chừng. Đọc CLAUDE.md của kho rồi làm quy trình Lint: mâu thuẫn và khẳng định lỗi thời, "
    "trang mồ côi và link hỏng, khái niệm có ở từ 2 dự án trở lên mà chưa có trang, dòng chức năng thiếu nguồn, trang thiếu trong index.md. "
    "Tự sửa những chỗ an toàn (thêm vào index, sửa link, thêm trích dẫn), phần còn lại chỉ báo. "
    "DỌN (mục Cleanup trong CLAUDE.md của kho; bản trước khi dọn đã được commit vào git nên xóa hẳn khỏi trang, không chuyển sang file lưu trữ): "
    "(1) đoạn trùng nguyên văn hoặc cùng một ý ở nhiều trang: giữ ở trang hợp nhất, trang khác thay bằng liên kết [[…]]; "
    "(2) điều tôi ĐÃ xác nhận/đã chọn (dấu ⚠ đã gỡ, mục 🔄 đã thành ✅, quyết định mới ghi rõ thay quyết định cũ): xóa bản cũ, phương án bị loại "
    "và phần kể lại quá trình, chỉ giữ trạng thái hiện tại kèm nguồn; dòng 🗑 Đã bỏ và dòng quyết định đã bị thay, cũ hơn 30 ngày: xóa; "
    "(3) log.md: các mục cũ hơn 30 ngày gộp thành MỘT dòng mỗi tháng `## [YYYY-MM] tóm tắt | N mục` kèm vài chữ nội dung chính. "
    "Không chắc là trùng hay đã được xác nhận thì ĐỂ NGUYÊN. Không đụng raw/, templates/, trang trong wiki/agent/ do máy sinh. "
    + MT_RULE +
    "Soát lại các mục đang nằm trong `cho`: mục nào `cu` không còn khớp trang (trang đã đổi) thì viết lại cho khớp, mâu thuẫn đã hết thì bỏ mục đó. "
    "Ghi mục `lint` vào log.md (đã dọn gì, bao nhiêu dòng). KHÔNG dùng git. Chỉ ghi dưới wiki/, index.md, log.md. "
    "Cuối cùng tóm tắt tiếng Việt tối đa 8 dòng: đã sửa gì, đã xóa gì, có bao nhiêu mâu thuẫn chờ tôi bấm chọn."
)


# ---------- Câu trả lời từ AI web (ChatGPT, Qwen, Claude Web, app Gemini…): chủ thả file vào raw/ai-web/ (hoặc nhập qua /nhapai) ----------
AIWEB_NAMES = {"chatgpt": "ChatGPT", "gpt": "ChatGPT", "openai": "ChatGPT", "qwen": "Qwen", "gemini": "Gemini (app web)",
               "claude": "Claude Web", "notebooklm": "NotebookLM", "notebook": "NotebookLM", "deepseek": "DeepSeek",
               "grok": "Grok", "perplexity": "Perplexity", "copilot": "Copilot"}
AIWEB_RULE = (
    "File tên `aiweb-*` là câu trả lời chủ chép từ một AI web (ChatGPT, Qwen, Claude Web, app Gemini…), KHÔNG phải tài liệu đã kiểm chứng: "
    "trang nguồn ghi rõ «Nguồn: AI web — <tên AI>, chưa kiểm chứng», chỉ giữ kiến thức/phương pháp dùng được, bỏ lời chào và câu hỏi lặp; "
    "khẳng định quan trọng (số liệu, giá, tính năng, ngày) đánh dấu ⚠ chưa kiểm chứng; trái với nguồn đã có trong wiki thì xử lý như MÂU THUẪN. "
)


def aiweb_name(p: Path, base: Path) -> str:
    """Đoán tên AI từ thư mục con (raw/ai-web/chatgpt/…) hoặc tên file (qwen-….md); không đoán được → «AI web»."""
    for part in [*p.relative_to(base).parts[:-1], p.stem]:
        low = part.lower()
        for k, v in AIWEB_NAMES.items():
            if low == k or low.startswith(k + "-") or low.startswith(k + "_") or low.startswith(k + " "):
                return v
    return "AI web"


def collect_ai_web(wiki_dir: Path) -> list:
    """Chuyển mọi .md/.txt trong raw/ai-web/ (kể cả thư mục con, trừ done/) thành raw/inbox/aiweb-*.md có dòng nguồn,
    rồi dời file gốc sang raw/ai-web/done/ (không xóa). Trả danh sách tên file inbox mới. Gọi khi đang giữ khóa «wiki»."""
    base = wiki_dir / "raw" / "ai-web"
    inbox, done = wiki_dir / "raw" / "inbox", base / "done"
    if not base.exists():
        return []
    made = []
    for f in sorted([*base.rglob("*.md"), *base.rglob("*.txt")]):
        if done in f.parents or f.name.lower().startswith("readme"):
            continue
        try:
            body = f.read_text(encoding="utf-8-sig", errors="replace").strip()
        except OSError:
            continue  # file đang mở/khóa: để lần sau
        if not body:
            continue
        name = aiweb_name(f, base)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in f.stem)[:50]
        rel = f.relative_to(base).as_posix()
        done.mkdir(parents=True, exist_ok=True)
        tgt = done / f.name
        if tgt.exists():
            tgt = done / f"{f.stem}-{stamp}{f.suffix}"
        try:  # dời file gốc TRƯỚC: file đang mở/khóa thì bỏ qua, lần sau lấy (không tạo bản trùng trong inbox)
            f.replace(tgt)
        except OSError:
            continue
        inbox.mkdir(parents=True, exist_ok=True)
        dst = inbox / f"aiweb-{slug}-{stamp}.md"
        dst.write_text(f"# Câu trả lời từ AI web: {name} (chưa kiểm chứng)\n\nNguồn: AI web — {name}, chủ chép lại "
                       f"(file gốc raw/ai-web/{rel}, {time.strftime('%Y-%m-%d')}).\n\n{body}\n", encoding="utf-8")
        made.append(dst.name)
    return made


def load() -> dict:
    try:
        return json.loads(LINT_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"since": 0}


def save(st: dict):
    LINT_STATE.write_text(json.dumps(st), encoding="utf-8")


# ---------- hàng chờ mâu thuẫn ----------
def mt_id(it: dict) -> str:
    return hashlib.md5((str(it.get("chu_de")) + "|" + str(it.get("y1")) + "|" + str(it.get("y2"))).encode("utf-8")).hexdigest()[:8]


def mt_load(wiki_dir: Path) -> dict:
    """{"cho": [mục hợp lệ…], "giu_ca_hai": [chủ đề…]}; file hỏng/thiếu → rỗng."""
    try:
        d = json.loads((wiki_dir / MT_REL).read_text(encoding="utf-8"))
    except Exception:
        d = {}
    if not isinstance(d, dict):
        d = {}
    cho = [it for it in (d.get("cho") or []) if isinstance(it, dict) and it.get("chu_de") and it.get("y1") and it.get("y2")]
    keep = [str(x) for x in (d.get("giu_ca_hai") or [])]
    return {"cho": cho, "giu_ca_hai": keep}


def mt_save(wiki_dir: Path, d: dict):
    (wiki_dir / MT_REL).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def mt_text(it: dict, i: int, n: int) -> str:
    return (f"⚖ Mâu thuẫn {i}/{n}: {str(it['chu_de'])[:150]}\n\n1️⃣ {str(it['y1'])[:900]}\n\n2️⃣ {str(it['y2'])[:900]}\n\n"
            "Bạn giữ ý nào? Ý còn lại sẽ bị xóa khỏi wiki (lấy lại được từ git).")


def mt_buttons(it: dict) -> list:
    """Các hàng nút (nhãn, callback_data)."""
    k = mt_id(it)
    return [[("1️⃣ Giữ ý 1", f"mt:{k}:a"), ("2️⃣ Giữ ý 2", f"mt:{k}:b")], [("Giữ cả hai", f"mt:{k}:2"), ("⏳ Để sau", f"mt:{k}:s")]]


def _edits(wiki_dir: Path, edits) -> dict:
    """Kiểm tra TẤT CẢ chỗ sửa trước, đúng hết mới trả {đường dẫn: (nội dung mới, có CRLF)}; sai một chỗ thì báo lỗi, không sửa gì."""
    base = wiki_dir.resolve()
    out = {}
    if not isinstance(edits, list) or not edits:
        raise ValueError("mục này không kèm chỗ sửa")
    for e in edits:
        rel = str(e.get("file") or "").replace("\\", "/")
        p = (base / rel).resolve()
        inside = p.is_relative_to(base / "wiki") or p in (base / "index.md", base / "log.md")
        if not inside or p.suffix.lower() != ".md" or not p.is_file():
            raise ValueError(f"không sửa được file {rel}")
        if p not in out:
            raw = p.read_bytes().decode("utf-8")
            out[p] = [raw.replace("\r\n", "\n"), "\r\n" in raw]
        old, new = str(e.get("cu") or "").replace("\r\n", "\n"), str(e.get("moi") or "").replace("\r\n", "\n")
        if not old or out[p][0].count(old) != 1:
            raise ValueError(f"trang {rel} đã đổi so với lúc kiểm tra")
        out[p][0] = out[p][0].replace(old, new)
    return out


def mt_apply(wiki_dir: Path, key: str, choice: str) -> tuple:
    """choice: a = giữ ý 1, b = giữ ý 2, 2 = giữ cả hai, s = để sau. Trả (đã đổi kho?, câu báo tiếng Việt, số mục còn chờ)."""
    d = mt_load(wiki_dir)
    it = next((x for x in d["cho"] if mt_id(x) == key), None)
    if it is None:
        return False, "Danh sách này đã cũ (mục đã được xử lý hoặc wiki đã kiểm tra lại). Gõ /capnhat để xem các mục còn chờ.", len(d["cho"])
    name = str(it["chu_de"])[:150]
    if choice == "s":
        return False, f"⏳ Để sau: {name}. Lần cập nhật tới bot sẽ hỏi lại.", len(d["cho"])
    if choice == "2":
        d["giu_ca_hai"].append(str(it["chu_de"]))
        what = "giữ cả hai ý"
    else:
        try:
            files = _edits(wiki_dir, it.get("giu_y1" if choice == "a" else "giu_y2"))
        except ValueError as e:
            st = load()  # ép lần /capnhat (hoặc lần chạy tuần) tới kiểm tra wiki để Claude viết lại mục này cho khớp trang
            st["since"] = max(st.get("since", 0), LINT_EVERY)
            save(st)
            return False, f"⚠ Chưa sửa được «{name}»: {e}. Mục vẫn chờ; gõ /capnhat để bot soát lại rồi chọn.", len(d["cho"])
        for p, (text, crlf) in files.items():
            p.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
        what = "giữ ý 1" if choice == "a" else "giữ ý 2"
    d["cho"] = [x for x in d["cho"] if mt_id(x) != key]
    mt_save(wiki_dir, d)
    try:
        with (wiki_dir / "log.md").open("a", encoding="utf-8") as f:
            f.write(f"\n## [{time.strftime('%Y-%m-%d')}] lint | chốt mâu thuẫn: {name} → {what} (bấm nút trên Telegram)\n")
    except OSError:
        pass
    return True, f"✅ {name}: {what}. Còn {len(d['cho'])} mâu thuẫn chờ bạn chọn.", len(d["cho"])
