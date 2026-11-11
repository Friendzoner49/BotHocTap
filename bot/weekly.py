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
REINDEX_FLAG = ROOT / "reindex_request.flag"  # weekly ghi, bot đọc rồi xóa
INGEST_MARK = ROOT / "weekly_ingest.marker"  # có trong lúc Claude nạp wiki; còn sót lại = lần trước bị ngắt giữa chừng
OUTBOX = ROOT / "outbox.jsonl"  # tin chưa gửi được vì mất mạng; main.py gửi bù rồi xóa
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
    # Không tự lập chỉ mục ở đây (sẽ nạp bản bge-m3 thứ hai cạnh bot, RAM 16 GB không đủ): ghi cờ REINDEX ở cuối, bot (đang giữ sẵn model) tự lập.
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
    if old is not None and new:  # file MỚI của môn có notebook (notebook_mon.json) → đưa lên NotebookLM; lỗi không làm hỏng bước khác
        try:
            import nlmsync
            nb = nlmsync.sync(COURSE_DIR, new)
            if nb:
                msg += chr(10) + nb
        except Exception as e:
            msg += chr(10) + f"NotebookLM: lỗi ({type(e).__name__})."
    notify(msg)
    if WIKI_DIR is None:  # không có vault Obsidian → chỉ lập chỉ mục + báo cáo, không gọi Claude
        return
    # Bước 1 — NGOÀI khóa wiki: trích chữ/OCR tài liệu môn mới/đổi (có thể hàng chục phút). /capnhat không đụng thư mục môn nên không cần khóa.
    texts = ROOT / "reports" / f"{today}-texts"
    listing = []
    if old is not None and (new or changed):
        texts.mkdir(exist_ok=True)
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
    # Bước 2 — lấy khóa «wiki» dùng chung với bot (/capnhat, nút mâu thuẫn): chờ tối đa 30 phút nếu bot đang ghi kho.
    # Inbox chỉ đọc SAU khi giữ khóa → bài /capnhat vừa lấy đi không bị nạp lại. Không cần try/finally: tiến trình kết thúc là HĐH tự nhả khóa.
    import proclock
    lk = proclock.Lock("wiki")
    if not lk.acquire(wait=1800, poll=15):
        notify("Cập nhật tuần: kho wiki bận quá 30 phút (bot đang /capnhat?), bỏ qua phần nạp wiki lần này. Gõ /capnhat để nạp.")
        ask_conflicts()
        return
    if proclock.orphan_claude(WIKI_DIR):
        lk.release()
        notify("Cập nhật tuần: còn một lượt Claude cũ đang chạy trong kho wiki (có thể do bot bị tắt giữa chừng). "
               "Bỏ qua phần nạp wiki để không ghi chồng; khởi động lại máy hoặc chờ nó xong rồi gõ /capnhat.")
        ask_conflicts()
        return
    if INGEST_MARK.exists():  # lần trước tắt máy/sập giữa lúc Claude nạp wiki: các bài này có thể đã nạp một phần
        notify("⚠ Lần cập nhật tuần trước bị ngắt giữa lúc nạp wiki. Các bài sau có thể đã được nạp một phần, lần này sẽ nạp lại "
               "(Claude cập nhật trang có sẵn, ít khi tạo trùng). Nếu thấy trang trùng thì gõ /capnhat để bước dọn gộp lại:\n"
               + INGEST_MARK.read_text(encoding="utf-8")[:1500])
    inbox = sorted((WIKI_DIR / "raw" / "inbox").glob("*.md"))  # mọi bài/ghi chú trong inbox (Web Clipper, Obsidian, /capnhat <nội dung>)
    if listing or miss or inbox:
        INGEST_MARK.write_text(f"{today}: " + (", ".join(nf.name for nf in inbox) or "chỉ tài liệu môn"), encoding="utf-8")
        texts.mkdir(exist_ok=True)
        for j, nf in enumerate(inbox, 1):
            (texts / f"inbox-{j:02d}.txt").write_text(f"BÀI/GHI CHÚ TRONG INBOX ({nf.name}):\n" + nf.read_text(encoding="utf-8"), encoding="utf-8")
            listing.append(f"- inbox-{j:02d}.txt = bài/ghi chú trong raw/inbox ({nf.name})")
        (texts / "_DANH_SACH.txt").write_text("\n".join(listing), encoding="utf-8")
        if run_claude(ROOT / "reports" / f"{today}.md", texts):
            done = WIKI_DIR / "raw" / "done"
            done.mkdir(exist_ok=True)
            for nf in inbox:  # đã đưa vào wiki → chuyển sang done (đúng quy ước vault)
                if not nf.exists():
                    continue
                dest = done / nf.name
                if dest.exists():
                    dest = done / f"{nf.stem}-{time.strftime('%Y%m%d%H%M%S')}{nf.suffix}"
                nf.replace(dest)
            lint_after(len(inbox) + len(new) + len(changed))
        INGEST_MARK.unlink(missing_ok=True)  # tới đây là xong (thành công hoặc Claude báo lỗi có kiểm soát), không phải sập giữa chừng
    lk.release()
    ask_conflicts()


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
            notify("Claude cập nhật wiki bị lỗi (thường do mất mạng), xem reports\\" + today + "-claude.md. "
                   "Bài trong inbox vẫn còn nguyên: gõ /capnhat để nạp ngay, hoặc chờ lần chạy tuần sau.")
            return False
        subprocess.run(["git", "add", "-A"], cwd=WIKI_DIR)
        subprocess.run(["git", "commit", "-m", f"ingest: cập nhật hằng tuần {today}\n\n"
                        "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"], cwd=WIKI_DIR)
        notify("Claude đã cập nhật wiki:\n" + out[-1500:])
        return True
    except Exception as e:
        notify(f"Không chạy được Claude Code ({type(e).__name__}). Bạn có thể gọi tay: «ingest tài liệu mới vào wiki».")
        return False


def lint_after(n: int):
    """Cộng n nguồn vừa nạp vào bộ đếm chung với /capnhat; đủ 10 nguồn thì tự kiểm tra wiki (lint)."""
    import shutil
    import subprocess
    import wikiops
    st = wikiops.load()
    st["since"] = st.get("since", 0) + n
    if st["since"] >= wikiops.LINT_EVERY:
        exe = shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude.exe")
        try:
            subprocess.run(["git", "add", "-A"], cwd=WIKI_DIR)  # mốc khôi phục: bước dọn xóa hẳn khỏi trang, bản cũ chỉ còn trong git
            subprocess.run(["git", "commit", "-m", f"trước khi dọn wiki {today} (mốc khôi phục)"], cwd=WIKI_DIR)
            r = subprocess.run([exe, "-p", wikiops.LINT_PROMPT, "--model", "sonnet", "--permission-mode", "acceptEdits",
                                "--allowedTools", "Read", "Glob", "Grep", "Edit", "Write",
                                "--settings", '{"disableAllHooks":true}'],
                               cwd=WIKI_DIR, capture_output=True, text=True, encoding="utf-8", timeout=3 * 3600)
            if r.returncode == 0:
                subprocess.run(["git", "add", "-A"], cwd=WIKI_DIR)
                subprocess.run(["git", "commit", "-m", f"lint: kiểm tra và dọn wiki hằng tuần {today}\n\n"
                                "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"], cwd=WIKI_DIR)
                st["since"] = 0
                notify("Đã kiểm tra và dọn wiki (đủ 10 nguồn; bản trước khi dọn nằm trong git của kho):\n" + (r.stdout or "").strip()[-1500:])
            else:
                notify("Kiểm tra wiki bị lỗi, sẽ thử lại lần sau. Hoặc gõ /capnhat trên Telegram.")
        except Exception as e:
            notify(f"Không chạy được kiểm tra wiki ({type(e).__name__}). Gõ /capnhat trên Telegram để thử lại.")
    wikiops.save(st)


def ask_conflicts():
    """Sau MỖI lần cập nhật tuần: gửi mọi mâu thuẫn còn chờ kèm nút; bot đang chạy (main.py, on_mt) xử lý lúc chủ bấm."""
    import wikiops
    cho = wikiops.mt_load(WIKI_DIR)["cho"]
    for i, it in enumerate(cho, 1):
        kb = {"inline_keyboard": [[{"text": lab, "callback_data": data} for lab, data in row] for row in wikiops.mt_buttons(it)]}
        notify(wikiops.mt_text(it, i, len(cho)), kb)


def notify(text, kb=None):
    try:
        data = urllib.parse.urlencode({"chat_id": os.environ["MY_TELEGRAM_ID"], "text": text,
                                       **({"reply_markup": json.dumps(kb)} if kb else {})}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
                               data, timeout=30)
    except Exception as e:  # mất mạng/VPN lúc chạy (như 09/11): cất vào hộp chờ, bot (main.py, outbox_flush) gửi bù khi có mạng lại
        log(f"Không nhắn được Telegram: {type(e).__name__}; đã cất vào hộp chờ để bot gửi bù")
        try:
            with OUTBOX.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": time.strftime("%d/%m %H:%M"), "text": text, "kb": kb}, ensure_ascii=False) + "\n")
        except OSError:
            pass


def request_reindex():
    """Ghi cờ cho bot: bot thấy cờ là tự lập chỉ mục bằng model đã nạp (net_loop kiểm 30 giây/lần; bot tắt thì làm khi bật lại)."""
    try:
        tmp = REINDEX_FLAG.with_suffix(".tmp")
        tmp.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
        tmp.replace(REINDEX_FLAG)
    except OSError as e:
        log(f"Không ghi được cờ lập chỉ mục: {type(e).__name__}")


if __name__ == "__main__":
    try:
        main()
        request_reindex()
    except Exception as e:  # không để lộ token trong log
        log(f"Lỗi: {type(e).__name__}: {str(e)[:200]}")
        notify("Cập nhật hằng tuần bị lỗi (xem weekly.log trong thư mục bot). Thường do mạng/VPN hoặc hết hạn mức Gemini; sẽ thử lại tuần sau.")
