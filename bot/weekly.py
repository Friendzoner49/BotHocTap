"""Cập nhật hằng tuần (Task Scheduler chạy thứ Hai 15:00). Không cần Claude, không tốn tiền.
1) lập chỉ mục tài liệu mới/đổi  2) so với tuần trước, liệt kê file mới/đổi/xóa
3) tóm tắt câu hỏi tuần qua (câu nào tài liệu không trả lời được)  4) ghi reports\\<ngày>.md và nhắn Telegram.
Việc viết lại ghi chú wiki vẫn do bạn gọi Claude («ingest») — báo cáo này cho biết cần làm gì."""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")
import rag  # noqa: E402

COURSE_DIR = Path(os.environ["COURSE_DIR"])
WIKI_DIR = Path(os.environ["WIKI_DIR"]) if os.environ.get("WIKI_DIR") else None  # vault Obsidian (tùy chọn)
STATE = ROOT / "weekly_state.json"
today = time.strftime("%Y-%m-%d")
lines = []


def log(s):
    print(s, flush=True)


def main():
    if not COURSE_DIR.exists():
        notify("Cập nhật hằng tuần bị bỏ qua: không thấy thư mục môn học (ổ chứa tài liệu chưa gắn?).")
        return
    # trạng thái tuần trước
    old = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else None
    now = {str(p.relative_to(COURSE_DIR)): [p.stat().st_size, int(p.stat().st_mtime)] for p in rag.iter_files(COURSE_DIR)}
    rag.build_index(COURSE_DIR, log=log)
    new = changed = gone = []
    if old is not None:
        new = sorted(set(now) - set(old))
        gone = sorted(set(old) - set(now))
        changed = sorted(k for k in now if k in old and now[k] != old[k])
    STATE.write_text(json.dumps(now, ensure_ascii=False), encoding="utf-8")

    # câu hỏi 7 ngày qua
    qs, miss = 0, []
    qf = ROOT / "questions.jsonl"
    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - 7 * 86400))
    if qf.exists():
        for ln in qf.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r["ts"][:10] >= cutoff:
                qs += 1
                if r.get("no_info"):
                    miss.append(r)

    rep = [f"# Báo cáo tuần {today}", ""]
    if old is None:
        rep += [f"Lần đầu chạy: đã ghi nhận {len(now)} file làm mốc. Từ tuần sau sẽ báo file mới/đổi.", ""]
    else:
        rep += [f"## File mới ({len(new)})"] + [f"- {x}" for x in new] + [""]
        rep += [f"## File đã sửa ({len(changed)})"] + [f"- {x}" for x in changed] + [""]
        rep += [f"## File đã xóa ({len(gone)})"] + [f"- {x}" for x in gone] + [""]
    rep += [f"## Câu hỏi 7 ngày qua: {qs}", f"Trong đó tài liệu không trả lời được: {len(miss)}"]
    rep += [f"- ({r['ts']}) [{r.get('subject') or 'tất cả'}] {r['q']}" for r in miss[-30:]]
    rep += ["", "## Việc nên làm",
            "- Có file mới/đổi → mở Claude và nói: «ingest tài liệu mới của môn học vào wiki» để cập nhật ghi chú.",
            "- Có câu hỏi không trả lời được → thiếu tài liệu hoặc ghi chú; bổ sung rồi hỏi lại bot."]
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / f"{today}.md").write_text("\n".join(rep), encoding="utf-8")

    msg = f"Cập nhật tuần {today}: đã lập chỉ mục."
    if old is not None:
        msg += f" File mới {len(new)}, đã sửa {len(changed)}, đã xóa {len(gone)}."
        if new or changed:
            msg += " Nói với Claude «ingest tài liệu mới vào wiki» để cập nhật ghi chú."
    msg += f" Câu hỏi tuần qua: {qs} (không trả lời được: {len(miss)})."
    notify(msg)
    if WIKI_DIR is None:  # không có vault Obsidian → chỉ lập chỉ mục + báo cáo, không gọi Claude
        return
    inbox = sorted((WIKI_DIR / "raw" / "inbox").glob("note-*.md"))  # ghi chú nhanh từ /note
    if (old is not None and (new or changed or miss)) or inbox:
        texts = ROOT / "reports" / f"{today}-texts"
        texts.mkdir(exist_ok=True)
        listing = []
        for i, rel in enumerate(new + changed, 1):
            try:
                body = "\n".join(f"\n[{pos}]\n{t}" for pos, t in rag.extract(COURSE_DIR / rel))
            except Exception as e:
                body = f"(không trích được chữ: {type(e).__name__})"
            if len(body.strip()) < 200 and rel.lower().endswith(".pdf"):  # PDF scan: dùng qwen cục bộ đọc chữ từ ảnh
                try:
                    import local_draft
                    if local_draft.ensure_ollama():
                        body = local_draft.ocr_pdf(COURSE_DIR / rel)
                except Exception as e:
                    body += f"\n(OCR cục bộ lỗi: {type(e).__name__})"
            (texts / f"{i:03d}.txt").write_text(f"FILE: {rel}\n{body}", encoding="utf-8")
            listing.append(f"- {i:03d}.txt = {rel}")
        for j, nf in enumerate(inbox, 1):
            (texts / f"note-{j:02d}.txt").write_text(f"GHI CHÚ NHANH ({nf.name}):\n" + nf.read_text(encoding="utf-8"), encoding="utf-8")
            listing.append(f"- note-{j:02d}.txt = ghi chú nhanh của chủ (từ /note)")
        (texts / "_DANH_SACH.txt").write_text("\n".join(listing), encoding="utf-8")
        if run_claude(ROOT / "reports" / f"{today}.md", texts):
            done = WIKI_DIR / "raw" / "done"
            done.mkdir(exist_ok=True)
            for nf in inbox:  # đã đưa vào wiki → chuyển sang done (đúng quy ước vault)
                nf.replace(done / nf.name)


CLAUDE_PROMPT = """Dùng skill cap-nhat-wiki-tuan. Báo cáo tuần: {report}. Thư mục chữ đã trích: {texts}. Chạy tự động, không có người trả lời giữa chừng."""


def run_claude(report: Path, texts: Path):
    import shutil
    import subprocess
    exe = shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude.exe")
    prompt = CLAUDE_PROMPT.format(report=report, texts=texts)
    try:
        r = subprocess.run([exe, "-p", prompt, "--model", "sonnet", "--permission-mode", "acceptEdits",
                            "--allowedTools", "Read", "Glob", "Grep", "Edit", "Write", "Skill",
                            "--add-dir", str(ROOT / "reports"), "--settings", '{"disableAllHooks":true}'],
                           cwd=WIKI_DIR, capture_output=True, text=True, encoding="utf-8", timeout=3 * 3600)
        out = (r.stdout or r.stderr or "").strip()
        (ROOT / "reports" / f"{today}-claude.md").write_text(out, encoding="utf-8")
        if r.returncode != 0:
            notify("Claude cập nhật wiki bị lỗi, xem reports\\" + today + "-claude.md")
            return False
        subprocess.run(["git", "add", "-A"], cwd=WIKI_DIR)
        subprocess.run(["git", "commit", "-m", f"ingest: cập nhật hằng tuần {today}\n\n"
                        "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"], cwd=WIKI_DIR)
        notify("Claude đã cập nhật wiki:\n" + out[-1500:])
        return True
    except Exception as e:
        notify(f"Không chạy được Claude Code ({type(e).__name__}). Bạn có thể gọi tay: «ingest tài liệu mới vào wiki».")
        return False


def notify(text):
    try:
        data = urllib.parse.urlencode({"chat_id": os.environ["MY_TELEGRAM_ID"], "text": text}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
                               data, timeout=30)
    except Exception as e:
        log(f"Không nhắn được Telegram: {type(e).__name__}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # không để lộ token trong log
        log(f"Lỗi: {type(e).__name__}: {str(e)[:200]}")
        notify("Cập nhật hằng tuần bị lỗi (xem weekly.log trong thư mục bot). Thường do mạng/VPN hoặc hết hạn mức Gemini; sẽ thử lại tuần sau.")
