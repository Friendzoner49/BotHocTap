"""Lập chỉ mục tài liệu môn học (PDF/DOCX/PPTX/MD/TXT) và tìm đoạn liên quan. Chỉ ĐỌC từ COURSE_DIR."""
import collections
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path

import numpy as np
from google import genai
from google.genai import types

logging.getLogger("pypdf").setLevel(logging.ERROR)
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # model bge-m3 đã tải sẵn; tránh tự tải bản mới làm hỏng bộ nhớ đệm

ROOT = Path(__file__).resolve().parent.parent
import kfind  # noqa: E402  (fold: bỏ dấu/hoa thường cho tìm từ khóa)
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
NLC = chr(10)

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
            # bài gốc đã nạp (raw\done): trang wiki nguồn chỉ tóm tắt/nêu tên, nội dung đầy đủ nằm ở đây
            rawdone = root.parent / "raw" / "done"
            if rawdone.exists():
                for p in sorted(rawdone.glob("*.md")):
                    yield p, name, "raw/done/" + p.name
            # luật và hướng dẫn của kho (nằm ngoài wiki\) để bot trả lời đúng về ingest/query/lint
            for fn, shown in (("CLAUDE.md", "wiki/_schema-CLAUDE.md"), ("HUONG_DAN.md", "wiki/_huong-dan.md")):
                f = root.parent / fn
                if f.exists():
                    yield f, name, shown


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


def wiki_sections(p: Path):
    """Trang wiki (Markdown): cắt theo ĐỀ MỤC thay vì 1200 ký tự bất kể ý. Mỗi đoạn mở đầu bằng «Tên trang > Đề mục > …» (và chủ đề từ tags)
    để cả tìm theo nghĩa lẫn theo từ khóa biết đoạn thuộc trang/mục nào. Mục quá ngắn (<350 ký tự) được gộp với mục kế."""
    t = p.read_text(encoding="utf-8", errors="ignore")
    tags = ""
    if t.startswith("---"):
        end = t.find(NLC + "---", 3)
        if end > 0:
            m = re.search(r"^tags:\s*\[(.*?)\]", t[3:end], re.M)
            tags = m.group(1).strip() if m else ""
            t = t[end + 4:]
    title, stack, buf, secs = p.stem, [], [], []

    def flush():
        txt = NLC.join(buf).strip()
        if txt:
            secs.append((" > ".join(stack) or title, txt))
        buf.clear()

    for line in t.splitlines():
        m = re.match(r"^(#{1,4})\s+(.*\S)", line)
        if m:
            flush()
            lvl = len(m.group(1))
            if lvl == 1 and not secs and not stack:
                title = m.group(2).strip()
            stack[:] = stack[:lvl - 1] + [m.group(2).strip()]
        else:
            buf.append(line)
    flush()
    merged = []
    for pos, txt in secs:
        if merged and len(merged[-1][1]) < 350:
            merged[-1] = (merged[-1][0], merged[-1][1] + NLC + f"[{pos}] " + txt)
        else:
            merged.append((pos, txt))
    out = []
    for i, (pos, txt) in enumerate(merged):
        head = f"{title} > {pos}" if pos != title else title
        out.append((pos, head + (f" (chủ đề: {tags})" if tags and i == 0 else "") + NLC + txt))
    return out or [("", t)]


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
    """Chỉ lập lại file mới/đổi (theo kích thước + ngày sửa). File đã xong được giữ nguyên.
    Giữ khóa «index» dùng chung với tiến trình khác (bot ↔ weekly.py): bên đến sau chờ tối đa 30 phút, không ghi chồng chỉ mục."""
    import proclock
    with proclock.hold("index", wait=1800, busy_msg="Chỉ mục đang được lập ở tiến trình khác quá 30 phút, bỏ qua lần này."):
        return _build_index(course_dir, log)


def _build_index(course_dir: Path, log=print):
    INDEX_DIR.mkdir(exist_ok=True)
    keep, changed = set(), []
    files = list(iter_all(course_dir))
    for n, (p, subj, rel) in enumerate(files, 1):
        st = p.stat()
        key = key_of(p)
        meta_f, vec_f = INDEX_DIR / f"{key}.json", INDEX_DIR / f"{key}.npy"
        is_wiki = subj == "Wiki" and p.suffix.lower() == ".md"
        ver = 2 if is_wiki else 1  # 2 = trang wiki cắt theo đề mục
        keep.add(key)
        if meta_f.exists() and vec_f.exists():
            m = json.loads(meta_f.read_text(encoding="utf-8"))
            ocr_now = (OCR_DIR / f"{key}.done").exists()
            if m["size"] == st.st_size and m["mtime"] == int(st.st_mtime) and m.get("ocr", False) == ocr_now and m.get("v", 1) == ver:
                continue
        ocr_now = (OCR_DIR / f"{key}.done").exists()
        try:
            parts = wiki_sections(p) if is_wiki else extract(p)
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
            meta_f.write_text(json.dumps({"size": st.st_size, "mtime": int(st.st_mtime), "chunks": [], "ocr": ocr_now, "v": ver}), encoding="utf-8")
            np.save(vec_f, np.zeros((0, DIM), dtype=np.float32))
            continue
        vecs = embed([f"{c['subject']} / {c['file']}\n{c['text']}" for c in chunks], "RETRIEVAL_DOCUMENT")
        np.save(vec_f, vecs)
        meta_f.write_text(json.dumps({"size": st.st_size, "mtime": int(st.st_mtime), "chunks": chunks, "ocr": ocr_now, "v": ver},
                                     ensure_ascii=False), encoding="utf-8")
        changed.append(rel)
        log(f"[{n}/{len(files)}] {rel}: {len(chunks)} đoạn")
    for f in INDEX_DIR.glob("*"):  # xóa chỉ mục của file đã bị xóa khỏi ổ H
        if f.stem not in keep:
            f.unlink()
    return changed


STOP_VI = set("la cua va cac cho trong mot nhung duoc khong the nao gi nay do khi de co voi tu den o it nhieu thi se da dang bi nhu hay hoac vi sao lam ai".split())


def toks(text: str) -> list:
    """Từ khóa để tìm theo chữ: bỏ dấu, hoa thường; thêm cặp từ khi một vế là số («stk 03» → «stk_03») để mã bài/lab khớp đúng."""
    w = [x for x in kfind.fold(text).split() if x not in STOP_VI and (len(x) > 1 or x.isdigit())]
    return w + [f"{a}_{b}" for a, b in zip(w, w[1:]) if a.isdigit() or b.isdigit()]


class Index:
    K1, B = 1.4, 0.75

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
        self.subj = np.array([c["subject"] for c in self.chunks])
        self.sig = f"{len(self.chunks)}-{max((f.stat().st_mtime_ns for f in INDEX_DIR.glob('*.json')), default=0)}"  # đổi khi chỉ mục đổi (làm hết hạn bộ nhớ đệm câu trả lời)
        self._build_bm25()
        self._build_links()

    def _build_bm25(self):
        """Chỉ mục từ khóa trong bộ nhớ (BM25): bổ sung cho tìm theo nghĩa, bắt đúng tên riêng, mã bài, số."""
        post, lens = collections.defaultdict(list), np.zeros(len(self.chunks), dtype=np.float32)
        for i, c in enumerate(self.chunks):
            t = toks(c["text"]) + toks(c["file"]) * 3  # tên file/thư mục lặp 3 lần: gõ đúng tên trang là lên đầu
            lens[i] = len(t)
            for term, n in collections.Counter(t).items():
                post[term].append((i, n))
        n_doc = max(len(self.chunks), 1)
        self.avg = float(lens.mean()) if len(lens) else 1.0
        self.lens = lens
        self.post = {}
        for term, lst in post.items():
            ids = np.fromiter((x[0] for x in lst), dtype=np.int32, count=len(lst))
            tf = np.fromiter((x[1] for x in lst), dtype=np.float32, count=len(lst))
            self.post[term] = (ids, tf, float(np.log(1 + (n_doc - len(lst) + 0.5) / (len(lst) + 0.5))))

    def _build_links(self):
        """Đồ thị liên kết của wiki: trang A có [[B]] thì B là «hàng xóm» của A (đi theo liên kết khi trả lời)."""
        self.by_file, self.links = collections.defaultdict(list), collections.defaultdict(set)
        for i, c in enumerate(self.chunks):
            self.by_file[c["file"]].append(i)
            if c["subject"] == "Wiki":
                for t in re.findall(r"\[\[([^\]|#]+)", c["text"]):
                    self.links[c["file"]].add(t.strip().casefold())
        self.stem2file = {Path(f).stem.casefold(): f for f in self.by_file if f.startswith("wiki/") and not Path(f).stem.startswith("_")}

    def neighbors(self, out: list, dense: np.ndarray, n: int, min_cos: float = 0.45) -> list:
        """Trang được các trang tìm thấy trỏ tới (ưu tiên nhiều trang cùng trỏ, rồi giống câu hỏi hơn): lấy đoạn mở đầu của nó."""
        top = []
        for h in out:
            if h["file"] not in top:
                top.append(h["file"])
        have = set(top)
        votes = collections.Counter()
        for f in top[:3]:
            for t in self.links.get(f, ()):
                nf = self.stem2file.get(t)
                if nf and nf not in have:
                    votes[nf] += 1
        cand = []
        for nf, v in votes.items():
            best = max(float(dense[i]) for i in self.by_file[nf])
            if best >= min_cos:
                cand.append((-v, -best, nf))
        res = []
        for _, nb, nf in sorted(cand)[:n]:
            i = self.by_file[nf][0]
            res.append(dict(self.chunks[i], score=-nb, rrf=0.0, via="link"))
        return res

    def bm25(self, query: str) -> np.ndarray:
        sc = np.zeros(len(self.chunks), dtype=np.float32)
        for term in set(toks(query)):
            e = self.post.get(term)
            if e:
                ids, tf, idf = e
                sc[ids] += idf * tf * (self.K1 + 1) / (tf + self.K1 * (1 - self.B + self.B * self.lens[ids] / self.avg))
        return sc

    def search(self, query: str, subject: str | None = None, k: int = 20):
        if not len(self.chunks):
            return []
        q = embed([query], "RETRIEVAL_QUERY")[0]
        scores = self.vecs @ q
        if subject:
            scores = np.where(self.subj == subject, scores, -1)
        top = np.argsort(-scores)[:k]
        return [dict(self.chunks[i], score=float(scores[i])) for i in top if scores[i] > 0]

    def search2(self, query: str, subject: str | None = None, k: int = 10, per_file: int = 3, w_kw: float = 0.4, fb: float = 0.3, name_w: float = 0.03, expand: int = 1):
        """Lai: tìm theo nghĩa (bge-m3) + theo từ khóa (BM25), trộn bằng RRF; trang có nhiều đoạn khớp được cộng điểm; tối đa per_file đoạn mỗi file
        để câu trả lời thấy nhiều nguồn khác nhau. `score` vẫn là độ giống nghĩa (0-1) để dòng giải thích độ khớp dùng được."""
        if not len(self.chunks):
            return []
        q = embed([query], "RETRIEVAL_QUERY")[0]
        dense = self.vecs @ q
        kw = self.bm25(query)
        if subject:
            m = self.subj == subject
            dense, kw = np.where(m, dense, -1), np.where(m, kw, 0)
        rrf = collections.defaultdict(float)
        for r, i in enumerate(np.argsort(-dense)[:60]):
            rrf[int(i)] += 1 / (60 + r)
        for r, i in enumerate(np.argsort(-kw)[:60]):
            if kw[i] > 0:
                rrf[int(i)] += w_kw / (60 + r)
        best_file = collections.defaultdict(float)
        for i, v in rrf.items():
            f = self.chunks[i]["file"]
            best_file[f] = max(best_file[f], v)
        qt = set(toks(query))
        stem_hit = {}
        for f in best_file:  # gõ gần đúng tên trang («lab 5» ↔ qtht-lab-5.md): cộng điểm theo tỉ lệ từ của tên trang có trong câu hỏi
            st = set(toks(Path(f).stem))
            r = len(st & qt) / len(st) if st else 0
            stem_hit[f] = r if r >= 0.6 else 0.0
        final = {i: v + fb * best_file[self.chunks[i]["file"]] + name_w * stem_hit[self.chunks[i]["file"]] for i, v in rrf.items()}
        out, count = [], collections.Counter()
        for i in sorted(final, key=lambda j: -final[j]):
            f = self.chunks[i]["file"]
            if count[f] >= per_file or dense[i] <= 0 and kw[i] <= 0:
                continue
            count[f] += 1
            out.append(dict(self.chunks[i], score=float(max(dense[i], 0)), rrf=float(final[i])))
            if len(out) >= k:
                break
        if expand and out:
            out += self.neighbors(out, dense, expand)
        return out
