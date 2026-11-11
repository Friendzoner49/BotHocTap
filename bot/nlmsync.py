"""Đưa file MỚI của môn học lên notebook NotebookLM tương ứng (weekly.py gọi). Môn không có trong notebook_mon.json thì bỏ qua.
Chỉ thêm, không xóa/sửa nguồn cũ; bỏ qua file trùng tên đã có trong notebook."""
import fnmatch
import json
import logging
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "notebook_mon.json"  # {tên thư mục môn: id notebook}; cá nhân, không đưa lên Git
OK_EXTS = {".pdf", ".txt", ".md", ".docx", ".pptx", ".mp3", ".m4a"}
MAX_MB = 200
MAX_SOURCES = 50  # ⚠ giới hạn nguồn mỗi notebook (gói miễn phí), chưa kiểm chứng


def _nlm(args, timeout=200):
    exe = shutil.which("nlm") or str(Path.home() / ".local" / "bin" / "nlm.exe")
    r = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", timeout=timeout, cwd=ROOT / "claude_cwd")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "nlm lỗi")[:300])
    return r.stdout


def subject_of(rel: str):
    parts = Path(rel).parts
    return parts[1] if len(parts) > 2 else (parts[0] if len(parts) > 1 else None)


def plan(course_dir: Path, rels: list):
    """Trả {môn: (id, [đường dẫn cần thêm], [bỏ qua + lý do])}."""
    if not MAP.exists():
        return {}
    mp = json.loads(MAP.read_text(encoding="utf-8"))
    out = {}
    for rel in rels:
        sub = subject_of(rel)
        if sub not in mp:
            continue
        cfg = mp[sub]
        nid = cfg if isinstance(cfg, str) else cfg["id"]
        skip = [] if isinstance(cfg, str) else cfg.get("skip_dirs", [])
        if sub not in out:
            out[sub] = [nid, [], [], None]
        p = course_dir / rel
        ent = out[sub]
        if any(fnmatch.fnmatch(d.lower(), pat.lower()) for d in Path(rel).parts[2:-1] for pat in skip):
            continue  # thư mục bị loại (vd bài lab của sinh viên khác)
        ext = p.suffix.lower()
        if ext not in OK_EXTS:
            ent[2].append((p.name, "định dạng không nhận"))
        elif not p.exists():
            continue
        elif p.stat().st_size > MAX_MB * 1048576:
            ent[2].append((p.name, f"nặng >{MAX_MB} MB"))
        else:
            ent[1].append(p)
    return out


def titles(nid: str) -> set:
    txt = _nlm(["source", "list", nid], 90)
    try:
        return {s["title"] for s in json.loads(txt)}
    except Exception:
        return set()


def sync(course_dir: Path, rels: list, dry=False) -> str:
    """Trả đoạn tóm tắt để đưa vào tin Telegram ('' nếu không có gì)."""
    msgs = []
    for sub, (nid, files, skipped, _) in plan(course_dir, rels).items():
        try:
            have = titles(nid)
            todo = [p for p in files if p.name not in have]
            dup = len(files) - len(todo)
            if len(have) + len(todo) > MAX_SOURCES:
                skipped += [(p.name, "notebook đầy") for p in todo[MAX_SOURCES - len(have):]]
                todo = todo[:max(0, MAX_SOURCES - len(have))]
            ok = 0
            for p in todo:
                if dry:
                    ok += 1
                    continue
                try:
                    _nlm(["source", "add", nid, "--file", str(p), "--wait"], 900)
                    ok += 1
                except Exception as e:
                    logging.exception("nlm add lỗi")
                    skipped.append((p.name, "lỗi: " + str(e)[:60]))
            if ok or dup or skipped:
                m = f"NotebookLM «{sub}»: {'sẽ thêm' if dry else 'đã thêm'} {ok} file"
                if dup:
                    m += f", {dup} đã có sẵn"
                if skipped:
                    m += f", bỏ qua {len(skipped)} (" + "; ".join(f"{n}: {w}" for n, w in skipped[:3]) + ")"
                msgs.append(m)
        except Exception as e:
            msgs.append(f"NotebookLM «{sub}»: lỗi ({str(e)[:80]}). Kiểm tra «nlm login».")
    return "\n".join(msgs)
