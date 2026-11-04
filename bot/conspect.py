"""Tạo conspect viết tay (giải thích tiếng Việt + tóm tắt tiếng Nga) từ đề bài + tài liệu.
Lấy nguồn: file đính kèm, hoặc các mục «8.6, 8.7» của quyển sách nêu trong đề (tìm trong COURSE_DIR), hoặc đoạn tìm theo nghĩa.
Mô hình: Ollama cục bộ (CONSPECT_MODEL, mặc định gemma4:12b); chưa có thì dùng Gemini (do main.py gọi)."""
import json
import re
import urllib.request
from pathlib import Path

import rag

PROMPT = (Path(__file__).resolve().parent / "conspect_prompt.txt").read_text(encoding="utf-8")
MAX_SRC = 60_000  # ký tự nguồn gửi cho mô hình cục bộ (≈ 24k token tiếng Nga)
OLLAMA = "http://localhost:11434"

SEC_RE = re.compile(r"(?<![\d.])(\d{1,2}\.\d{1,2})(?![\d.]*\d)\.?(?:\s+([A-Za-zА-Яа-яЁё]{4,}))?")
PAGES_RE = re.compile(r"(\d+)\s*(?:страниц|стр\b|trang|pages?)", re.I)


def wanted_pages(assign: str) -> int:
    m = PAGES_RE.search(assign)
    return int(m.group(1)) if m else 0


def sections_in(assign: str) -> list[tuple[str, str]]:
    """[(«8.6», «Представления»), ...]: số mục + chữ đầu tên mục (để phân biệt với số bài tập kiểu «8.6.»)."""
    seen, out = set(), []
    for m in SEC_RE.finditer(assign):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            out.append((m.group(1), m.group(2) or ""))
    return out


def _page_chunks(pdf: Path) -> dict[int, str]:
    """Chữ từng trang lấy từ chỉ mục (đã trích sẵn, không phải đọc lại PDF 80 MB)."""
    mf = rag.INDEX_DIR / f"{rag.key_of(pdf)}.json"
    pages: dict[int, str] = {}
    if mf.exists():
        for ch in json.loads(mf.read_text(encoding="utf-8"))["chunks"]:
            m = re.match(r"tr\.(\d+)", ch["pos"] or "")
            if m:
                n = int(m.group(1))
                pages[n] = pages.get(n, "") + " " + ch["text"]
    return pages


def _heading_page(pages: dict[int, str], sec: str, after: int = 0, title: str = ""):
    tail = re.escape(title) if title else r"[А-ЯA-Z][^.\n]{2,60}"
    pat = re.compile(r"(?<![\d.])" + re.escape(sec) + r"\.?\s+" + tail, re.I)
    for n in sorted(pages):
        if n <= after or n < 15:  # bỏ qua mục lục đầu sách
            continue
        for m in pat.finditer(pages[n]):
            if not re.match(r"[^\n]{0,60}?\.{4,}", pages[n][m.start():m.end() + 70]):  # dòng mục lục có dấu chấm dẫn
                return n
    return None


def book_sections(pdf: Path, secs: list[tuple[str, str]]):
    """Chữ các mục (từ mục đầu đến hết mục cuối) trong sách; trả (text, mô tả) hoặc (None, lý do)."""
    pages = _page_chunks(pdf)
    if not pages:
        return None, "sách chưa có trong chỉ mục"
    start = _heading_page(pages, secs[0][0], 0, secs[0][1])
    if not start:
        return None, f"không thấy mục {secs[0][0]} trong sách"
    major, minor = (int(x) for x in secs[-1][0].split("."))
    last = _heading_page(pages, secs[-1][0], start - 1, secs[-1][1]) or start
    nxt = _heading_page(pages, f"{major}.{minor + 1}", last) or _heading_page(pages, f"{major + 1}.1", last)
    end = min(nxt or last + 8, start + 30)
    from pypdf import PdfReader
    rd = PdfReader(str(pdf))
    parts = [(rd.pages[p - 1].extract_text() or "") for p in range(start, min(end, len(rd.pages)) + 1)]
    first = re.search(r"(?<![\d.])" + re.escape(secs[0][0]) + r"\.?\s+" + re.escape(secs[0][1]), parts[0], re.I)
    if first:
        parts[0] = parts[0][first.start():]  # bỏ phần cuối mục trước nằm cùng trang
    if nxt and end == nxt:
        cut = re.search(r"(?<![\d.])(?:" + str(major) + r"\." + str(minor + 1) + "|" + str(major + 1) + r"\.1)\.?\s+[А-ЯA-Z]", parts[-1])
        if cut:
            parts[-1] = parts[-1][:cut.start()]
    text = "\n".join(f"[tr.{start + i}]\n{t}" for i, t in enumerate(parts))
    return text, f"{pdf.name}, tr.{start}–{end} (mục {', '.join(x[0] for x in secs)})"


def ollama_has(model: str) -> bool:
    try:
        tags = json.loads(urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3).read())["models"]
        return any(t["name"] == model or t["name"].split(":")[0] == model for t in tags)
    except Exception:
        return False


def user_prompt(assign: str, source: str, pages: int, limit: int = MAX_SRC) -> str:
    return (f"ĐỀ BÀI:\n{assign}\n\nSố trang conspect tối thiểu: {pages or 6}\n\n"
            f"NGUỒN (trích từ tài liệu):\n{source[:limit]}")


def run_openrouter(model: str, assign: str, source: str, pages: int) -> str:
    """OpenRouter (API tương thích OpenAI). Mô hình :free có ngữ cảnh ~32K nên cắt nguồn còn 40.000 ký tự."""
    import os
    body = {"model": model, "temperature": 0.3, "max_tokens": 8000,
            "messages": [{"role": "system", "content": PROMPT},
                         {"role": "user", "content": user_prompt(assign, source, pages, 40_000)}]}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json",
                                  "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]})
    d = json.loads(urllib.request.urlopen(req, timeout=600).read())
    return (d["choices"][0]["message"]["content"] or "").strip()


def split_result(res: str):
    """(phần 1 tiếng Việt để đọc trong chat, phần 2 conspect để lưu file .md)."""
    m = re.search(r"^#{0,3}\s*PHẦN 2\b", res, re.M)
    if not m:
        return res, ""
    return res[:m.start()].strip(), res[m.start():].strip()


def run_ollama(model: str, assign: str, source: str, pages: int) -> str:
    body = {"model": model, "stream": False, "think": False,
            "options": {"num_ctx": 32768, "temperature": 0.3},
            "messages": [{"role": "system", "content": PROMPT},
                         {"role": "user", "content": user_prompt(assign, source, pages)}]}
    req = urllib.request.Request(OLLAMA + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=1800).read())["message"]["content"].strip()
