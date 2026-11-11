"""Bảng số liệu YouTube hằng ngày (10:00) cho các kênh trong YT_CHANNELS (mặc định 2 kênh của chủ). Không cần khóa API, không đăng nhập:
lấy số công khai bằng yt-dlp (người đăng ký, lượt xem từng video), tự lưu ảnh chụp mỗi ngày để tính tăng/giảm.
Không có giờ xem/doanh thu (cần đăng nhập YouTube Analytics, làm sau nếu muốn)."""
import json
import os
import shutil
import subprocess
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "youtube_stats.json"  # {ngày: {kênh: {name, subs, videos: {id: [tiêu đề, lượt xem]}}}}; gitignore
CHANNELS = [c.strip().lstrip("@") for c in os.environ.get("YT_CHANNELS", "").split(",") if c.strip()]
KEEP_DAYS = 90
N_VIDEOS = 50


def _exe() -> str:
    return shutil.which("yt-dlp") or str(Path.home() / "AppData" / "Local" / "Python" / "pythoncore-3.14-64" / "Scripts" / "yt-dlp.exe")


def fetch(handle: str) -> dict:
    r = subprocess.run([_exe(), "--flat-playlist", "-J", "--no-warnings", "--playlist-end", str(N_VIDEOS),
                        f"https://www.youtube.com/@{handle}/videos"], capture_output=True, text=True, encoding="utf-8", timeout=240)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError((r.stderr or "yt-dlp lỗi")[-200:])
    d = json.loads(r.stdout)
    vids = {e["id"]: [e.get("title") or "", int(e.get("view_count") or 0)] for e in d.get("entries", []) if e and e.get("id")}
    return {"name": d.get("channel") or d.get("uploader") or handle, "subs": d.get("channel_follower_count"), "videos": vids}


def load() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(h: dict):
    for k in sorted(h)[:-KEEP_DAYS]:
        h.pop(k)
    FILE.write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")


def _d(n, unit=""):
    if n is None:
        return "?"
    return f"{n:,}".replace(",", ".") + unit


def _delta(n):
    return "" if n is None else (f" ({'+' if n >= 0 else '−'}{abs(n):,})".replace(",", ".") if n else " (±0)")


def spark(vals: list) -> str:
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    bars = "▁▂▃▄▅▆▇█"
    return "".join(bars[0 if hi == lo else int((v - lo) / (hi - lo) * 7)] for v in vals[-14:])


def newest(handle: str):
    """Chi tiết video MỚI NHẤT (tuổi, lượt xem, thích, bình luận) bằng yt-dlp; lỗi thì None."""
    try:
        r = subprocess.run([_exe(), "-J", "--no-warnings", "--playlist-items", "1", f"https://www.youtube.com/@{handle}/videos"],
                           capture_output=True, text=True, encoding="utf-8", timeout=180)
        e = json.loads(r.stdout)["entries"][0]
        ud = e.get("upload_date")
        age = (date.today() - date(int(ud[:4]), int(ud[4:6]), int(ud[6:]))).days if ud else None
        return {"id": e.get("id"), "title": e.get("title") or "", "age_days": age, "views": int(e.get("view_count") or 0),
                "likes": e.get("like_count"), "comments": e.get("comment_count")}
    except Exception:
        return None


def run(today: str | None = None, summarize=None, ideas=None):
    """Lấy số hôm nay cho mọi kênh, lưu ảnh chụp, trả về (văn bản, số kênh lỗi). Mọi kênh lỗi → ném lỗi để vòng nhắc thử lại.
    summarize(facts) → đoạn nhận xét ngắn (Gemini); lỗi/None thì dùng gợi ý theo luật cố định."""
    today = today or date.today().isoformat()
    h = load()
    snap, errs = {}, []
    for ch in CHANNELS:
        try:
            snap[ch] = fetch(ch)
        except Exception as e:
            errs.append(f"{ch}: {str(e)[:80]}")
    if not snap:
        raise RuntimeError("Không lấy được kênh nào: " + "; ".join(errs))
    h.setdefault(today, {}).update(snap)
    prev_days = [k for k in sorted(h) if k < today]
    save(h)
    out = [f"📺 YouTube {date.fromisoformat(today).strftime('%d/%m/%Y')}", ""]
    for ch, now in snap.items():
        prev = next((h[k][ch] for k in reversed(prev_days) if ch in h[k]), None)
        pday = next((k for k in reversed(prev_days) if ch in h[k]), None)
        gap = (date.fromisoformat(today) - date.fromisoformat(pday)).days if pday else 0
        ref = "hôm qua" if gap == 1 else f"{gap} ngày trước"
        out.append(f"▶ {now['name']} (@{ch})")
        dsub = (now["subs"] - prev["subs"]) if prev and prev.get("subs") is not None and now["subs"] is not None else None
        hist = [h[k][ch]["subs"] for k in sorted(h) if ch in h[k]]
        out.append(f"  👥 Người đăng ký: {_d(now['subs'])}{_delta(dsub)}" + (f" so với {ref}" if dsub is not None else "") + (f"   {spark(hist)}" if spark(hist) else ""))
        facts = {"kenh": now["name"], "nguoi_dang_ky": now["subs"], "dang_ky_thay_doi_so_voi_" + ref.replace(" ", "_"): dsub}
        dtot = None
        if prev:
            same = [k for k in now["videos"] if k in prev["videos"]]
            newv = [k for k in now["videos"] if k not in prev["videos"]]
            dtot = sum(now["videos"][k][1] - prev["videos"][k][1] for k in same) + sum(now["videos"][k][1] for k in newv)
            facts["luot_xem_tang_trong_" + ref.replace(" ", "_")] = dtot
            out.append(f"  👁 Lượt xem {len(now['videos'])} video gần nhất: {_d(sum(v[1] for v in now['videos'].values()))}" + _delta(dtot))
        nw = newest(ch)
        vstat = None
        if nw:
            ids = list(now["videos"])
            gained = (nw["views"] - prev["videos"][nw["id"]][1]) if prev and nw["id"] in prev["videos"] else None
            nw["tang_tu_lan_truoc"] = gained
            age = "" if nw["age_days"] is None else f" · {nw['age_days']} ngày tuổi"
            out.append(f"  🆕 Video mới nhất: {nw['title'][:52]}{age}")
            out.append(f"     Hiện có {_d(nw['views'])} xem" + (f" ({'+' if gained >= 0 else '−'}{abs(gained)} so với {ref})" if gained is not None else "") + " (số công khai, cập nhật tức thì)")
            try:
                import ytanalytics as ya
                vstat = ya.video(ch, nw["id"], nw["age_days"]) if (ya.has_token(ch) and (nw["age_days"] or 0) >= 1) else None  # đăng hôm nay: Analytics chưa có số
            except Exception:
                vstat = None
            if vstat:
                t = vstat["tong"]
                v = max(int(t["views"]), 1)
                nw["tuong_tac"] = {"tong_luot_xem": int(t["views"]), "thich": int(t["likes"]), "binh_luan": int(t["comments"]), "chia_se": int(t["shares"]),
                                   "dang_ky_tu_video": int(t["subscribersGained"]), "thich_tren_100_xem": round(int(t["likes"]) * 100 / v, 1),
                                   "xem_tb_phan_tram_video": round(float(t["averageViewPercentage"] or 0)), "gio_xem": round(float(t["estimatedMinutesWatched"]) / 60, 1),
                                   "3_ngay_gan_nhat": [{"ngay": d["day"], "luot_xem": int(d["views"]), "thich": int(d["likes"]), "binh_luan": int(d["comments"]),
                                                        "xem_tb_phan_tram": round(float(d["averageViewPercentage"] or 0))} for d in vstat["ngay"]],
                                   "nguon_nguoi_xem": [f"{n} {p}%" for n, _, p in vstat["nguon"]]}
                out.append(f"     Tương tác từ lúc đăng (Analytics, trễ 1–2 ngày): {_d(int(t['views']))} xem · 👍 {int(t['likes'])} · 💬 {int(t['comments'])} · 🔁 {int(t['shares'])} · +{int(t['subscribersGained'])} đăng ký · xem TB {round(float(t['averageViewPercentage'] or 0))}% video")
                if vstat["ngay"]:
                    out.append("     3 ngày gần nhất: " + " · ".join(f"{d['day'][8:]}/{d['day'][5:7]}: {int(d['views'])} xem, 👍{int(d['likes'])}, 💬{int(d['comments'])}" for d in vstat["ngay"]))
                if vstat["nguon"]:
                    out.append("     Người xem đến từ: " + ", ".join(f"{n} {p}%" for n, _, p in vstat["nguon"]))
            else:
                why = "video vừa đăng hôm nay, Analytics chưa có số" if (nw["age_days"] or 0) < 1 else "chưa có số tương tác chi tiết: cần đăng nhập YouTube Analytics"
                out.append(f"     ({why})")
            facts["video_moi_nhat"] = {k: v for k, v in nw.items() if k != "id"}
        a_text, a_data = analytics_block(ch, with_tips=False)
        if a_data:
            c, p = a_data["cur"], a_data["prev"]
            facts["analytics_7_ngay"] = {"luot_xem": c["views"], "luot_xem_7_ngay_truoc": p["views"], "gio_xem": round(c["estimatedMinutesWatched"] / 60, 1),
                                         "xem_tb_phan_tram_video": round(c.get("averageViewPercentage") or 0), "dang_ky_rong": int(c["subscribersGained"] - c["subscribersLost"]),
                                         "ngay_tu_video_cuoi": a_data.get("days_since_upload")}
        out.append(a_text)
        txt = None
        if summarize:
            try:
                txt = summarize(facts)
            except Exception:
                txt = None
        if txt:
            out.append("  🤖 Nhận xét: " + txt.strip())
        elif a_data:
            import ytanalytics as ya
            out += ["  💡 " + t for t in ya.tips(a_data)]
        if ideas and a_data:  # tuyến nội dung nên làm tiếp (chỉ khi có số Analytics từng video)
            try:
                it = ideas(ch, now["name"])
            except Exception:
                it = None
            out.append("  💡 Tuyến nội dung nên làm tiếp:")
            if it:
                out += ["     " + ln.strip() for ln in it.strip().splitlines() if ln.strip()][:2]  # tối đa 2 tuyến/kênh để cả bảng vừa MỘT tin
            else:
                out.append("     (chưa tạo được hôm nay: Gemini bận, bảng 10:00 ngày mai sẽ có)")
        out.append("")
    if errs:
        out.append("⚠ Không lấy được: " + "; ".join(errs))
    return "\n".join(out).strip(), len(errs)


def analytics_block(ch: str, with_tips: bool = True):
    """(văn bản, dữ liệu) phần YouTube Analytics của kênh. Chưa đăng nhập/hết hạn/lỗi thì dữ liệu = None và văn bản nói cách xử lý; không làm hỏng bảng số công khai."""
    import ytanalytics as ya
    if not ya.has_token(ch):
        return f"  🔒 Chưa nối YouTube Analytics cho @{ch} (giờ xem, tăng trưởng): chạy dang_nhap_youtube.bat.", None
    try:
        d = ya.fetch(ch)
        out = ya.text(ch, d, tips_on=with_tips)
        age = ya.login_age_days(ch)
        if age is not None and age >= 5:  # ứng dụng Google ở chế độ thử nghiệm: token hết hạn sau 7 ngày
            out += chr(10) + f"  ⏰ Đăng nhập YouTube của @{ch} sắp hết hạn (đã {int(age)} ngày): chạy dang_nhap_youtube.bat để khỏi bị ngắt."
        return out, d
    except ya.NeedLogin:
        return f"  🔒 Phải đăng nhập lại YouTube Analytics cho @{ch}: chạy dang_nhap_youtube.bat (ứng dụng Google ở chế độ thử nghiệm thì hết hạn sau 7 ngày).", None
    except Exception as e:
        return f"  ⚠ Chưa lấy được YouTube Analytics cho @{ch}: {str(e)[:120]}", None


def channel_names() -> dict:
    """{kênh: tên hiển thị} lấy từ ảnh chụp gần nhất (chưa có thì dùng tên kênh)."""
    h = load()
    out = {}
    for ch in CHANNELS:
        nm = next((h[k][ch]["name"] for k in sorted(h, reverse=True) if ch in h[k] and h[k][ch].get("name")), ch)
        out[ch] = nm
    return out
