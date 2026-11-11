"""YouTube Analytics (số của CHỦ kênh: lượt xem, giờ xem, thời lượng xem, người đăng ký ròng, top video) + vài gợi ý ngắn.
Mỗi kênh đăng nhập MỘT lần (dang_nhap_youtube.bat) bằng đúng tài khoản/kênh đó; token riêng yt_token_<kênh>.json (không đưa lên Git).
Chỉ đọc (youtube.readonly + yt-analytics.readonly); không có quyền đăng/xóa/sửa gì trên kênh."""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRED = ROOT / "credentials.json"  # cùng ứng dụng Google Cloud «bothoctap» với Drive (cần bật 2 API: YouTube Analytics + YouTube Data v3)
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly", "https://www.googleapis.com/auth/yt-analytics.readonly"]
LAG = 2  # Analytics trễ ~2 ngày: cửa sổ 7 ngày kết thúc cách hôm nay 2 ngày


class NeedLogin(Exception):
    pass


def token_path(handle: str) -> Path:
    return ROOT / f"yt_token_{handle}.json"


def stamp_path(handle: str) -> Path:
    return ROOT / f"yt_login_{handle}.txt"


def login_age_days(handle: str):
    try:
        return (__import__("time").time() - int(stamp_path(handle).read_text(encoding="utf-8"))) / 86400
    except Exception:
        return None


def has_token(handle: str) -> bool:
    return token_path(handle).exists()


def login(handle: str):
    """Mở trình duyệt: đăng nhập và CHỌN ĐÚNG KÊNH @handle. Sai kênh thì bỏ token."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(CRED), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path(handle).write_text(creds.to_json(), encoding="utf-8")
    stamp_path(handle).write_text(str(int(__import__("time").time())), encoding="utf-8")  # ngày đăng nhập thật (token tự làm mới nên mtime không đúng)
    ch = my_channel(handle)
    got = (ch["snippet"].get("customUrl") or "").lstrip("@").lower()
    if got != handle.lower():
        token_path(handle).unlink(missing_ok=True)
        raise RuntimeError(f"Bạn đã chọn kênh «{ch['snippet'].get('title')}» (@{got}), không phải @{handle}. Chạy lại và chọn đúng kênh.")
    print(f"OK: @{handle} ({ch['snippet'].get('title')})")


def _creds(handle: str):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    if not has_token(handle):
        raise NeedLogin()
    c = Credentials.from_authorized_user_file(str(token_path(handle)), SCOPES)
    if not c.valid:
        try:
            c.refresh(Request())
        except RefreshError:
            raise NeedLogin()
        token_path(handle).write_text(c.to_json(), encoding="utf-8")
    return c


def _svc(handle: str, name: str, ver: str):
    from googleapiclient.discovery import build
    return build(name, ver, credentials=_creds(handle), cache_discovery=False)


def my_channel(handle: str) -> dict:
    r = _svc(handle, "youtube", "v3").channels().list(part="snippet,contentDetails", mine=True).execute()
    if not r.get("items"):
        raise RuntimeError("Tài khoản này không có kênh YouTube.")
    return r["items"][0]


METRICS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost,likes,comments"


def _totals(an, start: date, end: date) -> dict:
    r = an.reports().query(ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(), metrics=METRICS).execute()
    row = (r.get("rows") or [[0] * 8])[0]
    return dict(zip(METRICS.split(","), row))


def fetch(handle: str, today: date | None = None) -> dict:
    """{end, cur, prev, top[(tiêu đề, lượt xem)], days_since_upload}. Ném NeedLogin nếu chưa/đã hết hạn đăng nhập."""
    today = today or date.today()
    end = today - timedelta(days=LAG)
    an = _svc(handle, "youtubeAnalytics", "v2")
    cur = _totals(an, end - timedelta(days=6), end)
    prev = _totals(an, end - timedelta(days=13), end - timedelta(days=7))
    r = an.reports().query(ids="channel==MINE", startDate=(end - timedelta(days=6)).isoformat(), endDate=end.isoformat(),
                           metrics="views", dimensions="video", sort="-views", maxResults=3).execute()
    top = []
    yt = _svc(handle, "youtube", "v3")
    rows = r.get("rows") or []
    if rows:
        info = yt.videos().list(part="snippet", id=",".join(x[0] for x in rows)).execute()
        names = {i["id"]: i["snippet"]["title"] for i in info.get("items", [])}
        top = [(names.get(x[0], x[0]), int(x[1])) for x in rows]
    days = None
    try:
        ch = my_channel(handle)
        up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
        it = yt.playlistItems().list(part="contentDetails", playlistId=up, maxResults=1).execute().get("items")
        if it:
            pub = datetime.fromisoformat(it[0]["contentDetails"]["videoPublishedAt"].replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - pub).days
    except Exception:
        pass
    return {"end": end, "cur": cur, "prev": prev, "top": top, "days_since_upload": days}


SRC = {"RELATED_VIDEO": "video đề xuất", "YT_SEARCH": "tìm kiếm YouTube", "SUBSCRIBER": "trang chủ/đăng ký", "YT_CHANNEL": "trang kênh",
       "EXT_URL": "link ngoài", "NOTIFICATION": "thông báo", "PLAYLIST": "danh sách phát", "SHORTS": "Shorts", "NO_LINK_OTHER": "không rõ",
       "YT_OTHER_PAGE": "trang YouTube khác", "NO_LINK_EMBEDDED": "nhúng web", "ADVERTISING": "quảng cáo", "END_SCREEN": "màn hình cuối"}
VM = "views,likes,comments,shares,subscribersGained,estimatedMinutesWatched,averageViewPercentage"


def video(handle: str, vid: str, age_days, today: date | None = None) -> dict | None:
    """Tương tác của MỘT video từ lúc đăng: tổng + từng ngày gần nhất + nguồn người xem. Lỗi/chưa có số thì None."""
    today = today or date.today()
    try:
        an = _svc(handle, "youtubeAnalytics", "v2")
        start = today - timedelta(days=max(age_days or 0, 0) + 1)
        base = dict(ids="channel==MINE", filters=f"video=={vid}", startDate=start.isoformat(), endDate=today.isoformat())
        tot = (an.reports().query(metrics=VM, **base).execute().get("rows") or [[0] * 7])[0]
        rows = an.reports().query(metrics=VM, dimensions="day", sort="day", **base).execute().get("rows") or []
        src = an.reports().query(metrics="views", dimensions="insightTrafficSourceType", sort="-views", maxResults=4, **base).execute().get("rows") or []
    except NeedLogin:
        raise
    except Exception:
        return None
    keys = VM.split(",")
    days = [dict(zip(["day"] + keys, r)) for r in rows][-3:]
    total_views = int(tot[0])
    return {"tong": dict(zip(keys, tot)), "ngay": days,
            "nguon": [(SRC.get(k, k), int(v), round(v * 100 / total_views) if total_views else 0) for k, v in src]}


def _pct(a, b):
    return None if not b else round((a - b) * 100 / b)


def _mmss(sec) -> str:
    sec = int(sec or 0)
    return f"{sec // 60}:{sec % 60:02d}"


def tips(d: dict) -> list:
    """Tối đa 2 gợi ý ngắn, theo luật cố định (không dùng AI)."""
    out = []
    cur, prev = d["cur"], d["prev"]
    ds = d.get("days_since_upload")
    if ds is not None and ds >= 10:
        out.append(f"Đã {ds} ngày chưa đăng video mới; đăng đều đặn giúp giữ lượt xem.")
    if cur.get("averageViewPercentage") and cur["views"] >= 20 and cur["averageViewPercentage"] < 35:
        out.append(f"Người xem chỉ xem trung bình {cur['averageViewPercentage']:.0f}% video: mở đầu gọn hơn, nói ngay ý chính trong 15 giây đầu.")
    ch = _pct(cur["views"], prev["views"])
    if len(out) < 2 and ch is not None and ch <= -25:
        out.append(f"Lượt xem giảm {-ch}% so với tuần trước; xem lại video top tuần trước để làm tiếp cùng chủ đề.")
    elif len(out) < 2 and ch is not None and ch >= 25 and d["top"]:
        out.append(f"Lượt xem tăng {ch}%, «{d['top'][0][0][:40]}» đang kéo; làm tiếp phần liên quan khi còn nóng.")
    if not out:
        out.append("Số liệu ổn định; giữ nhịp đăng hiện tại.")
    return out[:2]


def text(handle: str, d: dict, tips_on: bool = True) -> str:
    cur, prev = d["cur"], d["prev"]

    def v(k):
        return int(cur.get(k) or 0)

    ch = _pct(cur["views"], prev["views"])
    arrow = "" if ch is None else f" ({'+' if ch >= 0 else '−'}{abs(ch)}% so với 7 ngày trước)"
    net = v("subscribersGained") - v("subscribersLost")
    lines = [f"  📈 7 ngày đến {d['end'].strftime('%d/%m')}: {v('views'):,} lượt xem{arrow}".replace(",", "."),
             f"  ⏱ {cur['estimatedMinutesWatched'] / 60:.1f} giờ xem · xem TB {_mmss(cur['averageViewDuration'])} ({cur.get('averageViewPercentage') or 0:.0f}% video)",
             f"  👥 Đăng ký ròng: {'+' if net >= 0 else '−'}{abs(net)} (vào {v('subscribersGained')}, ra {v('subscribersLost')}) · 👍 {v('likes')} · 💬 {v('comments')}"]
    if tips_on:
        lines += ["  💡 " + t for t in tips(d)]
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "login":
        login(sys.argv[2].lstrip("@"))
