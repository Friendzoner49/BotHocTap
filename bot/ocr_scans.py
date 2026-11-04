"""OCR các PDF scan (không có chữ) bằng qwen2.5vl cục bộ, ~18 giây/trang. Chạy lại an toàn: làm tiếp từ trang đã xong.
Kết quả ở ocr_cache\<khóa>.jsonl (+ .done khi xong); rag.extract tự dùng. Sau đó chạy index_course.bat."""
import base64
import io
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
import local_draft  # noqa: E402
import rag  # noqa: E402

PROMPT = "Chép lại chính xác toàn bộ chữ trên ảnh này (giữ nguyên ngôn ngữ gốc). Nếu có sơ đồ, mô tả ngắn một dòng."


def is_scan(p: Path) -> bool:
    from pypdf import PdfReader
    try:
        return sum(len((pg.extract_text() or "").strip()) for pg in PdfReader(str(p)).pages) < 200
    except Exception:
        return False


def main():
    import pypdfium2 as pdfium
    rag.OCR_DIR.mkdir(exist_ok=True)
    scans = [p for p in rag.iter_files(Path(os.environ["COURSE_DIR"])) if p.suffix.lower() == ".pdf"
             and not (rag.OCR_DIR / f"{rag.key_of(p)}.done").exists() and is_scan(p)]
    scans.sort(key=lambda p: p.stat().st_size)  # file nhỏ trước, sách dày để cuối
    print(f"{len(scans)} PDF scan cần OCR", flush=True)
    if scans and not local_draft.ensure_ollama():
        print("Không bật được Ollama.", flush=True)
        return
    for p in scans:
        key = rag.key_of(p)
        cf = rag.OCR_DIR / f"{key}.jsonl"
        have = len(cf.read_text(encoding="utf-8").splitlines()) if cf.exists() else 0
        pdf = pdfium.PdfDocument(str(p))
        for i in range(have, len(pdf)):
            try:
                w, h = pdf[i].get_size()
                sc = min(1.4, 1800 / max(w, h, 1))  # trang quá lớn làm hết RAM → thu nhỏ
                img = pdf[i].render(scale=sc).to_pil().convert("RGB")
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=80)
                txt = local_draft.generate(PROMPT, [base64.b64encode(buf.getvalue()).decode()], 4096)
            except Exception as e:  # lỗi tạm (Ollama bận, hết RAM): ghi trang trống, không dừng cả sách
                print(f"  lỗi trang {i + 1}: {type(e).__name__}", flush=True)
                txt = ""
            with open(cf, "a", encoding="utf-8") as f:
                f.write(json.dumps({"page": i + 1, "text": txt}, ensure_ascii=False) + "\n")
            print(f"{p.name}: {i + 1}/{len(pdf)}", flush=True)
        (rag.OCR_DIR / f"{key}.done").write_text("ok")
    print("Xong OCR.", flush=True)


if __name__ == "__main__":
    main()
