"""Đề xuất tuyến nội dung tiếp theo cho một kênh: gom số THẬT của từng video (YouTube Analytics, ~90 ngày) rồi để Gemini đề xuất.
Lưu ý: YouTube Studio «Hỏi Studio» không có API công khai nên không nối trực tiếp được; bot dùng cùng nguồn số (Analytics của chính kênh) + Gemini."""
import json
import re
from datetime import date, timedelta

import ytanalytics as ya

DAYS = 90
MAXV = 30
M = "views,averageViewPercentage,estimatedMinutesWatched,likes,comments,shares,subscribersGained"


def _dur(iso: str) -> int:
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    h, mi, s = (int(x or 0) for x in m.groups()) if m else (0, 0, 0)
    return h * 3600 + mi * 60 + s


def data(handle: str, today: date | None = None) -> dict:
    """Bảng video của kênh trong DAYS ngày gần nhất: tiêu đề, ngày đăng, độ dài, xem, % xem TB, thích, bình luận, chia sẻ, đăng ký."""
    today = today or date.today()
    an = ya._svc(handle, "youtubeAnalytics", "v2")
    r = an.reports().query(ids="channel==MINE", startDate=(today - timedelta(days=DAYS)).isoformat(), endDate=today.isoformat(),
                           metrics=M, dimensions="video", sort="-views", maxResults=MAXV).execute()
    rows = r.get("rows") or []
    if not rows:
        return {"videos": []}
    yt = ya._svc(handle, "youtube", "v3")
    info = yt.videos().list(part="snippet,contentDetails", id=",".join(x[0] for x in rows)).execute()
    meta = {i["id"]: i for i in info.get("items", [])}
    keys = M.split(",")
    out = []
    for x in rows:
        i = meta.get(x[0])
        if not i:
            continue
        v = dict(zip(keys, x[1:]))
        views = max(int(v["views"]), 1)
        out.append({"tieu_de": i["snippet"]["title"], "ngay_dang": i["snippet"]["publishedAt"][:10], "do_dai_phut": round(_dur(i["contentDetails"]["duration"]) / 60, 1),
                    "luot_xem": int(v["views"]), "xem_tb_phan_tram": round(float(v["averageViewPercentage"] or 0)),
                    "thich_tren_100_xem": round(int(v["likes"]) * 100 / views, 1), "binh_luan": int(v["comments"]), "chia_se": int(v["shares"]),
                    "dang_ky_moi": int(v["subscribersGained"])})
    return {"videos": out}


PROMPT = ("Bạn là cố vấn nội dung YouTube cho chủ một kênh nhỏ. Dưới đây là SỐ THẬT từ YouTube Analytics của kênh «{name}» ({n} video có số trong {days} ngày, "
          "xếp theo lượt xem giảm dần). Hãy đề xuất 4 TUYẾN NỘI DUNG tiếp theo nên làm, mỗi tuyến theo mẫu: «Tên tuyến — gợi ý 2 tiêu đề video — Vì sao: nêu số cụ thể "
          "của các video đã chạy tốt/kém — Cách làm: 1 câu (độ dài, mở đầu, hình thức)». Quy tắc: chỉ dựa vào số trong JSON; nhận ra mẫu chung của các video chạy tốt "
          "(chủ đề, độ dài, % xem TB, đăng ký mới) và của video kém; nếu mẫu dữ liệu quá ít (dưới 5 video hoặc lượt xem quá thấp) thì nói rõ là còn ít dữ liệu, "
          "đề xuất mang tính thử nghiệm; không bịa xu hướng thị trường, không hứa kết quả; viết số bằng chữ số; tiếng Việt thân mật, xưng «bạn», không markdown, "
          "mỗi tuyến một đoạn ngắn đánh số 1–4.\n\nSỐ LIỆU: ")


PROMPT_SHORT = ("Bạn là cố vấn nội dung YouTube cho chủ một kênh nhỏ. Dưới đây là SỐ THẬT từ YouTube Analytics của kênh «{name}» ({n} video có số trong {days} ngày, "
                "xếp theo lượt xem giảm dần). Đề xuất đúng 2 TUYẾN NỘI DUNG nên làm tiếp, mỗi tuyến đúng MỘT dòng đánh số 1–2 theo mẫu: "
                "«Tên tuyến (1 tiêu đề gợi ý) — vì sao: số cụ thể của video chạy tốt/kém — độ dài nên làm». Chỉ dựa vào số trong JSON; dữ liệu ít (dưới 5 video hoặc "
                "lượt xem quá thấp) thì ghi «thử nghiệm»; không bịa xu hướng; viết số bằng chữ số; tiếng Việt, không markdown, không emoji; mỗi dòng dưới 220 ký tự, ngắn gọn, không giải thích dài.\n\nSỐ LIỆU: ")


def ideas(handle: str, name: str, summarize, short: bool = False) -> str:
    d = data(handle)
    vids = d["videos"]
    if len(vids) < 2:
        return f"Kênh «{name}» chưa đủ video có số liệu trong {DAYS} ngày để đề xuất (cần ít nhất 2 video)."
    if short:
        return summarize(PROMPT_SHORT.format(name=name, n=len(vids), days=DAYS) + json.dumps(vids, ensure_ascii=False)) or ""
    txt = summarize(PROMPT.format(name=name, n=len(vids), days=DAYS) + json.dumps(vids, ensure_ascii=False))
    top = vids[0]
    head = f"💡 Tuyến nội dung tiếp theo cho «{name}» (dựa trên {len(vids)} video, {DAYS} ngày; nhiều xem nhất: {top['tieu_de'][:40]} — {top['luot_xem']} xem, xem TB {top['xem_tb_phan_tram']}%)"
    return head + "\n\n" + (txt or "Gemini đang bận, thử lại sau ít phút.")
