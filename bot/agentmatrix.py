"""Dựng wiki/agent/_so-sanh.md từ frontmatter các thẻ trong wiki/agent/: điểm chung, điểm «hợp với tôi» (trọng số ở wiki/concepts/danh-gia-he-thong-agent.md),
độ cũ (quá 90 ngày). Chạy: python bot\\agentmatrix.py"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agentscan as A  # noqa: E402

STALE_DAYS = 90
NL = chr(10)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def weights() -> dict:
    p = A.WIKI / "wiki" / "concepts" / "danh-gia-he-thong-agent.md"
    fm = A.frontmatter(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {k: (_num(v) if _num(v) is not None else 1.0) for k, v in (fm.get("trong-so") or {}).items()}


def load_cards() -> list:
    w, rows = weights(), []
    for f in sorted(A.CARD_DIR.glob("*.md")):
        if f.name.startswith("_"):
            continue
        fm = A.frontmatter(f.read_text(encoding="utf-8"))
        if fm.get("type") != "agent-system":
            continue
        d = {k: _num(v) for k, v in (fm.get("diem") or {}).items() if _num(v) is not None}
        chung = sum(d.values()) / len(d) if d else None
        wsum = sum(w.get(k, 1.0) for k in d)
        hop = sum(w.get(k, 1.0) * v for k, v in d.items()) / wsum if d and wsum else None
        try:
            days = (date.today() - date.fromisoformat(fm.get("ngay-danh-gia") or "")).days
        except ValueError:
            days = None
        rows.append({"slug": f.stem, "fm": fm, "d": d, "chung": chung, "hop": hop, "days": days})
    rows.sort(key=lambda r: (r["hop"] is None, -(r["hop"] or 0), r["slug"]))
    return rows


def build() -> Path:
    rows = load_cards()
    f = lambda x: "-" if x is None else f"{x:.1f}"  # noqa: E731
    out = ["---", "type: synthesis", f"updated: {date.today().isoformat()}", "tags: [agent, so-sanh]", "---",
           "# So sánh hệ thống AI Agent", "",
           "> Bảng này do script `bot\\agentmatrix.py` tạo, **đừng sửa tay** (sửa ở từng thẻ rồi chạy lại). Thước đo: [[danh-gia-he-thong-agent]]. "
           "«Chung» = trung bình các chiều đã chấm; «Hợp tôi» = trung bình có trọng số; «n/12» = số chiều đã có điểm. Tầng 1 = mới quét nhanh, chưa chấm. ⏰ = đánh giá cũ hơn 90 ngày.", "",
           "| Hệ thống | Loại | Tầng | Sao | Phiên bản | Đã chấm | Chung | Hợp tôi | Khuyến nghị | |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        fm = r["fm"]
        old = "⏰" if r["days"] is not None and r["days"] > STALE_DAYS else ""
        out.append(f"| [[{r['slug']}]] | {fm.get('loai') or '-'} | {fm.get('tang') or '1'} | {fm.get('sao') or '-'} | {fm.get('phien-ban') or '-'} | "
                   f"{len(r['d'])}/{len(A.DIMS)} | {f(r['chung'])} | {f(r['hop'])} | {fm.get('khuyen-nghi') or '-'} | {old} |")
    if not rows:
        out.append("| (chưa có thẻ nào) | | | | | | | | | |")
    scored = [r for r in rows if r["d"]]
    out += ["", "## Điểm từng chiều", "", "| Hệ thống | " + " | ".join(n for _, n in A.DIMS) + " |", "|---|" + "---|" * len(A.DIMS)]
    for r in scored:
        out.append(f"| [[{r['slug']}]] | " + " | ".join(f(r["d"].get(k)) for k, _ in A.DIMS) + " |")
    if not scored:
        out.append("| (chưa có thẻ nào được chấm điểm) |" + " |" * len(A.DIMS))
    p = A.CARD_DIR / "_so-sanh.md"
    A.CARD_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(NL.join(out) + NL, encoding="utf-8")
    return p


def summary(n: int = 8) -> str:
    rows = load_cards()
    if not rows:
        return "Chưa có thẻ nào. Dùng /nghiencuu <link GitHub>."
    lines = []
    for r in rows[:n]:
        fm = r["fm"]
        lines.append(f"• {fm.get('ten') or r['slug']} (tầng {fm.get('tang') or 1}): " + (f"chung {r['chung']:.1f}, hợp tôi {r['hop']:.1f}, {len(r['d'])}/12 chiều" if r["d"] else "chưa chấm điểm"))
    return "\n".join(lines)


if __name__ == "__main__":
    print(build())
