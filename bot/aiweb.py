"""/nhapai: đọc link chia sẻ của AI web (ChatGPT, Claude, Gemini, Qwen…) → chữ + giờ câu đầu/câu cuối nếu trang có ghi.
Không gọi AI. Trang cần đăng nhập/JavaScript thì báo chủ chép chữ rồi dán (không tự động hóa trình duyệt)."""
import re
import time
import urllib.error
import urllib.request
from datetime import datetime

import docread

HOSTS = {"chatgpt.com": "chatgpt", "chat.openai.com": "chatgpt", "claude.ai": "claude", "gemini.google.com": "gemini", "g.co": "gemini",
         "qwen": "qwen", "deepseek.com": "deepseek", "grok.com": "grok", "perplexity.ai": "perplexity", "notebooklm.google.com": "notebooklm"}
MAX_SPAN = 12 * 3600  # cuộc chat kéo dài hơn 12 giờ (mở lại hôm sau) thì không coi là một buổi học → hỏi bằng nút
_KEYS = r"create_time|created_at|createdAt"  # chỉ giờ TẠO tin (giờ cập nhật/chia sẻ/timestamp chung làm số phút phình ra)
_EPOCH = re.compile(r'\\?"(?:' + _KEYS + r')\\?"\s*:\s*\\?"?(\d{13}|\d{10}(?:\.\d+)?)')
_ISO = re.compile(r'\\?"(?:' + _KEYS + r')\\?"\s*:\s*\\?"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)')


def ai_of_url(url: str) -> str:
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    for k, v in HOSTS.items():
        if k in host:
            return v
    return ""


def times_in(html: str) -> list:
    """Mọi mốc thời gian (giây epoch) ghi trong dữ liệu của trang, chỉ giữ mốc hợp lý (2020 → mai)."""
    out = []
    for s in _EPOCH.findall(html):
        v = float(s) / (1000 if len(s) == 13 else 1)
        out.append(v)
    for s in _ISO.findall(html):
        try:
            out.append(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
        except ValueError:
            pass
    lo, hi = datetime(2020, 1, 1).timestamp(), time.time() + 86400
    return sorted(v for v in out if lo <= v <= hi)


def span(ts: list):
    """(giờ câu đầu, giờ câu cuối) nếu có ≥ 2 mốc và cách nhau 1 phút – 12 giờ; không thì None (bot hỏi bằng nút)."""
    if len(ts) < 2:
        return None
    a, b = ts[0], ts[-1]
    return (a, b) if 60 <= b - a <= MAX_SPAN else None


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": docread.UA, "Accept-Language": "vi,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read(8_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("Trang này chặn bot đọc (cần đăng nhập). Mở link, bấm Copy câu trả lời rồi dán vào đây.")
        if e.code in (404, 410):
            raise RuntimeError("Link hỏng hoặc đã tắt chia sẻ. Kiểm tra lại link, hoặc chép chữ rồi dán vào đây.")
        raise RuntimeError(f"Trang trả lỗi {e.code}. Thử lại sau, hoặc chép chữ rồi dán vào đây.")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("Không mở được link (mạng/VPN rớt?). Thử lại sau, hoặc chép chữ rồi dán vào đây.")
    title, text = docread.html_to_text(html)
    if len(text) < 300:
        raise RuntimeError("Trang này chỉ hiện chữ khi mở bằng trình duyệt (cần JavaScript/đăng nhập), bot không đọc được. "
                           "Mở link, bấm Copy câu trả lời rồi dán vào đây.")
    sp = span(times_in(html))
    return {"title": title or url, "text": text, "ai": ai_of_url(url), "start": sp[0] if sp else None, "end": sp[1] if sp else None}
