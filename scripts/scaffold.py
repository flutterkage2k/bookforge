#!/usr/bin/env python3
"""bookforge scaffold: create a new book project directory.

Usage: python3 scaffold.py <book_dir> --style practical --title "제목" \
         [--subtitle S] [--length short|standard|long] [--author A] [--brand "#hex"] \
         [--images vector|generated|none]
Creates book.json, outline.json (stub), chapters/, assets/, diagrams/, qc/.
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from styles_ko import STYLES, choices, resolve  # noqa: E402

def main():
    p = argparse.ArgumentParser()
    p.add_argument("book_dir")
    p.add_argument("--style", required=True, metavar="STYLE",
                   help="스타일 — " + " / ".join(choices()) + " (한국어 이름도 됩니다)")
    p.add_argument("--title", required=True)
    p.add_argument("--subtitle", default=None)
    p.add_argument("--length", default="short", metavar="LENGTH",
                   help="분량 — 짧게(short) / 보통(standard) / 길게(long)")
    p.add_argument("--author", default="bookforge")
    p.add_argument("--brand", default=None)
    p.add_argument("--date", default=None)
    p.add_argument("--images", default="vector", metavar="IMAGES",
                   help="이미지 정책 — 벡터(vector) / 생성(generated) / 없음(none)")
    a = p.parse_args()
    try:
        a.style = resolve(a.style)
    except ValueError as e:
        p.error(str(e))
    LENGTH_KO = {"짧게": "short", "보통": "standard", "길게": "long"}
    IMAGES_KO = {"벡터": "vector", "생성": "generated", "없음": "none"}
    a.length = LENGTH_KO.get(a.length, a.length)
    a.images = IMAGES_KO.get(a.images, a.images)
    if a.length not in ("short", "standard", "long"):
        p.error(f"모르는 분량: {a.length} — 짧게(short) / 보통(standard) / 길게(long)")
    if a.images not in ("vector", "generated", "none"):
        p.error(f"모르는 이미지 정책: {a.images} — 벡터(vector) / 생성(generated) / 없음(none)")

    d = Path(a.book_dir).resolve()
    (d / "chapters").mkdir(parents=True, exist_ok=True)
    (d / "assets").mkdir(exist_ok=True)
    (d / "diagrams").mkdir(exist_ok=True)  # 도해 사이드카(fig-NN.json) — references/diagrams.md
    (d / "qc").mkdir(exist_ok=True)        # 콘택트시트 등 검수 산출물

    book = {"title": a.title, "subtitle": a.subtitle, "author": a.author,
            "style": a.style, "length": a.length, "images": a.images}
    if a.brand:
        book["brand"] = a.brand
    if a.date:
        book["date"] = a.date
    (d / "book.json").write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")

    outline = {"chapters": [
        {"file": "ch-01.md", "title": "1장 제목",
         "summary": "장 요약 1~2문장 (도비라에 실림)",
         "toc_line": "목차 전용 완결 카피 한 줄 (없으면 summary 앞 40자가 잘려 실림)"},
    ]}
    op = d / "outline.json"
    if not op.exists():
        op.write_text(json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK scaffold: {d}  [{STYLES[a.style][0]}({a.style})]")

if __name__ == "__main__":
    main()
