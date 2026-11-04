"""Lập chỉ mục tài liệu môn học (PDF/DOCX/PPTX/MD/TXT) và tìm đoạn liên quan. Chỉ ĐỌC từ COURSE_DIR."""
import hashlib
import json
import logging
import os
import time
from pathlib import Path

import numpy as np
from google import genai
from google.genai import types

logging.getLogger("pypdf").setLevel(logging.ERROR)
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # model bge-m3 đã tải sẵn; tránh tự tải bản mới làm hỏng bộ nhớ đệm

ROOT = Path(__file__).resolve().parent.parent
from dotenv import load_dotenv  # noqa: E402  (cần WIKI_DIR từ .env ngay khi import)
load_dotenv(ROOT / ".env")
INDEX_DIR = ROOT / "index_local"  # chỉ mục cũ (Gemini, 768 chiều) ở thư mục index\ — không dùng nữa
EMBED_MODEL = "BAAI/bge-m3"  # chạy cục bộ trên GPU, miễn phí, không hạn mức
DIM = 1024
CHUNK = 1200
OVERLAP = 150
EXTS = {".pdf", ".docx", ".pptx", ".md", ".txt", ".sql", ".py", ".cpp", ".ino"}
OCR_DIR = ROOT / "ocr_cache"  # chữ OCR của PDF scan (ocr_scans.py), mỗi trang một dòng JSON
EXTRA_ROOTS = [(Path(os.environ["WIKI_DIR"]) / "wiki", "Wiki")] if os.environ.get("WIKI_DIR") else []  # nguồn ngoài thư mục môn học (chỉ đọc)
SKIP_NAMES = {"CLAUDE.md", "GEMINI.md", "AGENTS.md"}

_client = None


def client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(timeout=60_000))
    return _client


def key_of(p: Path) -> str:
    return hashlib.md5(str(p).encode()).hexdigest()


def iter_all(course_dir: Path):
    """(đường dẫn, môn, tên hiển thị) của tài liệu môn học + các nguồn phụ (wiki)."""
    for p in iter_files(course_dir):
        yield p, subject_of(course_dir, p), str(p.relative_to(course_dir))
    for root, name in EXTRA_ROOTS:
        if root.exists():
            for p in sorted(root.rglob("*.md")):
                yield p, name, "wiki/" + p.relative_to(root).as_posix()


def subject_of(course_dir: Path, p: Path) -> str:
    rel = p.relative_to(course_dir).parts
    return rel[1] if len(rel) >= 3 else (rel[0] if len(rel) >= 2 else "(gốc)")


def iter_files(course_dir: Path):
    for p in sorted(course_dir.rglob("*")):
        if (p.is_file() and p.suffix.lower() in EXTS and p.name not in SKIP_NAMES
                and ".claude" not in p.parts):
            yield p


def extract(p: Path):
    """Trả về list (nhãn_vị_trí, văn_bản)."""
    ext = p.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        pages = [(f"tr.{i}", pg.extract_text() or "") for i, pg in enumerate(PdfReader(str(p)).pages, 1)]
        if sum(len(t.strip()) for _, t in pages) < 200:  # PDF scan: dùng chữ OCR nếu đã có
            cf = OCR_DIR / f"{key_of(p)}.jsonl"
            if cf.exists():
                pages = [(f"tr.{r['page']}", r["text"]) for r in map(json.loads, cf.read_text(encoding="utf-8").splitlines())]
        return pages
    if ext == ".docx":
        import docx
        d = docx.Document(str(p))
        text = "\n".join(x.text for x in d.paragraphs)
        for t in d.tables:
            for row in t.rows:
                text += "\n" + " | ".join(c.text for c in row.cells)
        return [("", text)]
    if ext == ".pptx":
        from pptx import Presentation
        out = []
        for i, s in enumerate(Presentation(str(p)).slides, 1):
            out.append((f"slide {i}", "\n".join(sh.text_frame.text for sh in s.shapes if sh.has_text_frame)))
        return out
    return [("", p.read_text(encoding="utf-8", errors="ignore"))]


def chunk_text(text: str):
    text = " ".join(text.split())
    i = 0
    while i < len(text):
        yield text[i:i + CHUNK]
        i += CHUNK - OVERLAP


_model = None


def embed(texts, task):
    """Embedding cục bộ bằng bge-m3 (không cần mạng/API). task giữ lại cho tương thích."""
    global _model
    if _model is None:
        import torch
        from sentence_transformers import SentenceTransformer
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _model = SentenceTransformer(EMBED_MODEL, device=dev)
        _model.max_seq_length = 512
        if dev == "cuda":
            _model.half()
    return np.asarray(_model.encode(texts, batch_size=32, normalize_embeddings=True,
                                    show_progress_bar=False), dtype=np.float32)


def build_index(course_dir: Path, log=print):
    """Chỉ lập lại file mới/đổi (theo kích thước + ngày sửa). File đã xong được giữ nguyên."""
    INDEX_DIR.mkdir(exist_ok=True)
    keep, changed = set(), []
    files = list(iter_all(course_dir))
    for n, (p, subj, rel) in enumerate(files, 1):
        st = p.stat()
        key = key_of(p)
        meta_f, vec_f = INDEX_DIR / f"{key}.json", INDEX_DIR / f"{key}.npy"
        keep.add(key)
        if meta_f.exists() and vec_f.exists():
            m = json.loads(meta_f.read_text(encoding="utf-8"))
            ocr_now = (OCR_DIR / f"{key}.done").exists()
            if m["size"] == st.st_size and m["mtime"] == int(st.st_mtime) and m.get("ocr", False) == ocr_now:
                continue
        ocr_now = (OCR_DIR / f"{key}.done").exists()
        try:
            parts = extract(p)
        except Exception as e:
            log(f"[{n}/{len(files)}] BỎ QUA {rel}: {str(e)[:80]}")
            continue
        chunks = []
        for pos, txt in parts:
            for c in chunk_text(txt):
                if len(c.strip()) > 40:
                    chunks.append({"subject": subj, "file": rel, "pos": pos, "text": c})
        if not chunks:
            log(f"[{n}/{len(files)}] không có chữ (ảnh scan?): {rel}")
            meta_f.write_text(json.dumps({"size": st.st_size, "mtime": int(st.st_mtime), "chunks": [], "ocr": ocr_now}), encoding="utf-8")
            np.save(vec_f, np.zeros((0, DIM), dtype=np.float32))
            continue
        vecs = embed([f"{c['subject']} / {c['file']}\n{c['text']}" for c in chunks], "RETRIEVAL_DOCUMENT")
        np.save(vec_f, vecs)
        meta_f.write_text(json.dumps({"size": st.st_size, "mtime": int(st.st_mtime), "chunks": chunks, "ocr": ocr_now},
                                     ensure_ascii=False), encoding="utf-8")
        changed.append(rel)
        log(f"[{n}/{len(files)}] {rel}: {len(chunks)} đoạn")
    for f in INDEX_DIR.glob("*"):  # xóa chỉ mục của file đã bị xóa khỏi ổ H
        if f.stem not in keep:
            f.unlink()
    return changed


class Index:
    def __init__(self):
        self.chunks, vs = [], []
        for mf in INDEX_DIR.glob("*.json"):
            vf = mf.with_suffix(".npy")
            if not vf.exists():
                continue
            ch = json.loads(mf.read_text(encoding="utf-8"))["chunks"]
            if ch:
                self.chunks += ch
                vs.append(np.load(vf))
        self.vecs = np.vstack(vs) if vs else np.zeros((0, DIM), dtype=np.float32)
        self.subjects = sorted({c["subject"] for c in self.chunks})

    def search(self, query: str, subject: str | None = None, k: int = 20):
        if not len(self.chunks):
            return []
        q = embed([query], "RETRIEVAL_QUERY")[0]
        scores = self.vecs @ q
        if subject:
            mask = np.array([c["subject"] == subject for c in self.chunks])
            scores = np.where(mask, scores, -1)
        top = np.argsort(-scores)[:k]
        return [self.chunks[i] for i in top if scores[i] > 0]
