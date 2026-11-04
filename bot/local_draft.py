"""Bản nháp ghi chú bằng AI cục bộ (Ollama qwen2.5vl:7b, miễn phí, không tốn Claude).
- File có chữ: tóm tắt từng khúc → ghép thành bản nháp tiếng Việt.
- PDF scan (không có chữ): chuyển trang thành ảnh, qwen đọc chữ (OCR) rồi mới tóm tắt.
Claude chỉ chỉnh sửa bản nháp, không đọc lại toàn bộ nguồn."""
import base64
import io
import json
import subprocess
import time
import urllib.request
from pathlib import Path

OLLAMA = "http://localhost:11434"
MODEL = "qwen2.5vl:7b"
PART = 9000          # ký tự mỗi khúc gửi cho qwen
MAX_OCR_PAGES = 60

NOTE_PROMPT = (
    "Bạn là người viết ghi chú học tập. Dưới đây là một đoạn tài liệu (tiếng Nga hoặc tiếng Anh) của môn học mạng máy tính. "
    "Viết ghi chú bằng TIẾNG VIỆT, dạng gạch đầu dòng: khái niệm chính, các bước làm theo thứ tự, và mọi lệnh/cấu hình/địa chỉ IP "
    "chép NGUYÊN VĂN trong khối ```. Không bịa, không thêm kiến thức ngoài đoạn. Nếu đoạn không có nội dung học thuật, trả lời đúng một chữ: BỎ.\n\n"
    "ĐOẠN TÀI LIỆU:\n{text}")


def ensure_ollama():
    try:
        urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3)
        return True
    except Exception:
        pass
    try:
        subprocess.Popen(["ollama", "serve"], creationflags=0x08000000)
    except Exception:
        return False
    for _ in range(30):
        time.sleep(2)
        try:
            urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3)
            return True
        except Exception:
            pass
    return False


def generate(prompt, images=None, num_ctx=8192):
    body = {"model": MODEL, "prompt": prompt, "stream": False, "options": {"num_ctx": num_ctx, "temperature": 0.2}}
    if images:
        body["images"] = images
    req = urllib.request.Request(OLLAMA + "/api/generate", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=600).read())["response"].strip()


def ocr_pdf(path: Path) -> str:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path))
    out = []
    for i in range(min(len(pdf), MAX_OCR_PAGES)):
        img = pdf[i].render(scale=1.4).to_pil().convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        txt = generate("Chép lại chính xác toàn bộ chữ trên ảnh này (giữ nguyên ngôn ngữ gốc). Nếu có sơ đồ, mô tả ngắn một dòng.",
                       [base64.b64encode(buf.getvalue()).decode()], 4096)
        out.append(f"[tr.{i + 1}]\n{txt}")
    return "\n".join(out)


def draft_from_text(text: str) -> str:
    text = " ".join(text.split()) if len(text) < 400 else text
    parts, cur = [], ""
    for para in text.split("\n"):
        if len(cur) + len(para) > PART and cur:
            parts.append(cur)
            cur = ""
        cur += para + "\n"
    if cur.strip():
        parts.append(cur)
    notes = []
    for p in parts:
        r = generate(NOTE_PROMPT.format(text=p))
        if r.strip() and r.strip() != "BỎ":
            notes.append(r)
    return "\n\n".join(notes)
