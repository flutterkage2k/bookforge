#!/usr/bin/env python3
"""bookforge build: render a book project to draft/book.pdf.

Usage: python3 build.py <book_dir>
Reads  <book_dir>/book.json + outline.json + chapters/*.md
Route  style -> engine (typst | html) from styles/<style>/tokens.json ("engine").
Output <book_dir>/draft/book.pdf   (never writes final/ — that is qc_gate's job)
"""
import json, os, shutil, subprocess, sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
FONTS = SKILL / "assets" / "fonts"

def die(msg: str):
    print(f"BUILD FAIL: {msg}", file=sys.stderr)
    sys.exit(1)

def load(book_dir: Path):
    book = json.loads((book_dir / "book.json").read_text(encoding="utf-8"))
    outline = json.loads((book_dir / "outline.json").read_text(encoding="utf-8"))
    style = book.get("style") or die("book.json: style missing")
    style_dir = SKILL / "styles" / style
    if not style_dir.exists():
        die(f"unknown style: {style}")
    tokens = json.loads((style_dir / "tokens.json").read_text(encoding="utf-8"))
    return book, outline, style_dir, tokens

def render_diagrams(book_dir: Path, book: dict):
    """P1.5 도해 프리렌더: diagrams/fig-*.json -> assets/fig-*.svg (+labels.json).

    images 정책(book.json)은 여기서 살아 있는 스위치가 된다 —
    "none"이면 도해 존재 자체가 계약 위반, "vector"(기본)면 프리렌더 실행.
    """
    dg = book_dir / "diagrams"
    if not dg.exists() or not sorted(dg.glob("fig-*.json")):
        return
    if book.get("images") == "none":
        die('book.json images="none"인데 diagrams/에 도해 사이드카가 있음')
    env = dict(os.environ)
    env["NODE_PATH"] = subprocess.run(["npm", "root", "-g"], capture_output=True,
                                      text=True).stdout.strip()
    r = subprocess.run(["node", str(SKILL / "scripts" / "render_diagrams.mjs"),
                        str(book_dir), "--style", book["style"]],
                       capture_output=True, text=True, env=env)
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.returncode != 0:
        die("diagram prerender:\n" + (r.stderr or r.stdout))

def build_typst(book_dir: Path, book: dict, outline: dict, style_dir: Path):
    sys.path.insert(0, str(SKILL / "scripts"))
    from md2typ import convert_chapter

    ts = book_dir / "typeset"
    style_snap = ts / "_style"
    chap_out = ts / "chapters"
    for d in (style_snap, chap_out, book_dir / "draft"):
        d.mkdir(parents=True, exist_ok=True)

    shutil.copy(SKILL / "templates" / "base.typ", style_snap / "base.typ")
    shutil.copy(SKILL / "assets" / "code-theme.tmTheme", style_snap / "code-theme.tmTheme")
    shutil.copy(style_dir / "theme.typ", style_snap / "theme.typ")
    meta = dict(book)
    for name in ("cover-art.png", "cover.png", "cover.jpg"):
        if (book_dir / "assets" / name).exists():
            meta["_cover_art"] = f"../../assets/{name}"
            break
    (style_snap / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    # refit-params.json: 장별 자간 미세조정(pagination.md §5 L2, refit.py가 산출)
    refit = {}
    rp = book_dir / "refit-params.json"
    if rp.exists():
        refit = json.loads(rp.read_text(encoding="utf-8"))

    includes = []
    for ch in outline["chapters"]:
        src = book_dir / "chapters" / ch["file"]
        if not src.exists():
            die(f"chapter file missing: {src}")
        dst = chap_out / (src.stem + ".typ")
        convert_chapter(src, dst, ch["title"], ch.get("summary"))
        prm = refit.get(src.stem, {})
        if prm.get("tracking_em"):
            head, _, rest = dst.read_text(encoding="utf-8").partition("\n")
            dst.write_text(f"{head}\n#set text(tracking: {prm['tracking_em']}em)\n{rest}",
                           encoding="utf-8")
        includes.append(f'#include "chapters/{dst.name}"')

    main = "\n".join([
        '#import "_style/theme.typ": *',
        "#show: book.with(meta: meta, tokens: theme-tokens, cover: make-cover(meta), toc: true)",
        *includes,
        "#colophon(meta, TT)",
    ])
    (ts / "main.typ").write_text(main, encoding="utf-8")

    out = book_dir / "draft" / "book.pdf"
    cmd = ["typst", "compile", "--root", str(book_dir),
           "--font-path", str(FONTS)]
    # book.json "fonts" — 사용자가 고른 폰트의 폴더를 검색 경로에 더한다.
    # --ignore-system-fonts는 그대로 둔다: 지정한 폴더만 열리고, 그 밖의 시스템 폰트로
    # 조용히 폴백하는 일은 계속 막힌다(폴백 사고가 재현 불가 산출물을 만든다).
    for spec in (book.get("fonts") or {}).values():
        d = spec.get("dir")
        if d and d not in cmd:
            cmd += ["--font-path", d]
    cmd += ["--ignore-system-fonts", str(ts / "main.typ"), str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die("typst compile:\n" + r.stderr)
    print(f"OK draft: {out}")

def build_html(book_dir: Path, book: dict, outline: dict, style_dir: Path):
    from build_html import build as html_build  # scripts/build_html.py
    html_build(book_dir, book, outline, style_dir, SKILL)

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 scripts/build.py <book_dir>")
    book_dir = Path(sys.argv[1]).resolve()
    book, outline, style_dir, tokens = load(book_dir)
    # 재빌드 시작 = 이전 final/ 무효화. final/은 이번 산출물이 게이트를 통과한
    # 뒤에만 다시 생긴다 (qc_gate FAIL 경로의 제거와 이중 방어).
    stale = book_dir / "final" / f"{book_dir.name}.pdf"
    if stale.exists():
        stale.unlink()
        print(f"재빌드: 이전 final 무효화 -> {stale}")
    render_diagrams(book_dir, book)
    engine = tokens.get("engine", "typst")
    if engine == "typst":
        build_typst(book_dir, book, outline, style_dir)
    elif engine == "html":
        sys.path.insert(0, str(SKILL / "scripts"))
        build_html(book_dir, book, outline, style_dir)
    else:
        die(f"unknown engine: {engine}")

if __name__ == "__main__":
    main()
