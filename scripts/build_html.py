#!/usr/bin/env python3
"""bookforge HTML engine: md -> themed HTML -> Chromium print (2-pass TOC).

Theme contract (styles/<style>/):
  theme.css   — full print stylesheet (@page, tokens via :root, component classes)
  theme.html  — python str.Template page skeleton with $title $subtitle $author
                $date $brand $toc $body $fonts_dir placeholders
Chapter markers: each chapter opener embeds an invisible ⟦chNN⟧ marker; pass 1
extracts real page numbers with PyMuPDF, injects them into .tocpg spans, pass 2
prints the final PDF.
"""
import json, os, re, subprocess, sys
from html import escape as _esc
from pathlib import Path
from string import Template

try:  # PyMuPDF 1.24+ 신 모듈명, 구버전은 fitz만 제공
    import pymupdf as fitz
except ImportError:
    import fitz
from markdown_it import MarkdownIt

MD = MarkdownIt("commonmark", {"html": True, "typographer": True}) \
    .enable("table").enable("strikethrough")

CALLOUT_RE = re.compile(r"^:::\s*(info|tip|warn|quote|stat|pull)\s*(.*)$")

def md_to_html(md: str, book_dir: Path | None = None, ch_idx: int | None = None) -> str:
    """markdown subset -> html, with ::: callout directive support."""
    out, lines, buf = [], md.split("\n"), []
    def flush():
        if buf:
            out.append(MD.render("\n".join(buf)))
            buf.clear()
    i = 0
    while i < len(lines):
        m = CALLOUT_RE.match(lines[i].strip())
        if m:
            flush()
            kind, title = m.group(1), m.group(2).strip()
            body, i = [], i + 1
            while i < len(lines) and lines[i].strip() != ":::":
                body.append(lines[i]); i += 1
            i += 1
            if kind == "pull":
                ls = [l.strip() for l in body if l.strip()]
                quote_t = ls[0] if ls else ""
                speaker = ls[1] if len(ls) > 1 else ""
                sp = f'<div class="pull-speaker">{speaker}</div>' if speaker else ""
                out.append(f'<section class="pullquote"><div class="pull-text">{quote_t}</div>{sp}</section>')
            elif kind == "stat":
                ls = [l.strip() for l in body if l.strip()]
                value = ls[0] if ls else ""
                label = ls[1] if len(ls) > 1 else ""
                out.append(f'<div class="stat"><span class="stat-value">{value}</span>'
                           f'<span class="stat-label">{label}</span></div>')
            else:
                t = f'<div class="callout-title">{title}</div>' if title else ""
                out.append(f'<div class="callout callout-{kind}">{t}{MD.render(chr(10).join(body))}</div>')
        else:
            buf.append(lines[i]); i += 1
    flush()
    html = "\n".join(out)
    # 이미지 문단 -> figure/figcaption (alt=캡션, title="출처: …")
    # 그림 캡션 계약(STYLE 캡션 규약): 장별 자동 번호 `그림 n-m` 라벨을 앞에 단다
    # (표 캡션 tbl-caption의 `표 n-m.`과 동일 문법 — 한 책 안에서 캡션 문법 통일).
    fig_no = [0]
    def fig(m):
        src, alt, title = m.group("src"), m.group("alt") or "", m.group("title") or ""
        cap = alt
        if title:
            cap = f"{cap} · {title}" if cap else title
        if cap and ch_idx is not None:
            fig_no[0] += 1
            cap = f'<span class="fig-label">그림 {ch_idx}-{fig_no[0]}</span> {cap}'
        c = f"<figcaption>{cap}</figcaption>" if cap else ""
        # SVG 도해는 <img src> 대신 원문 인라인 — SVG-as-image 모드는 외부 @font-face를
        # 차단해 도해 <text>가 폴백 폰트로 렌더되므로.
        if book_dir and src.endswith(".svg") and src.startswith("../assets/"):
            svg = inline_svg(book_dir, src)
            if svg:
                # 사이드카 bf.width=twothirds — 세로형 도해가 전폭으로 부풀어 면을
                # 통째로 먹는 것을 막는다 (HTML 트랙은 float가 없어 폭이 유일한 레버)
                fig_style = ""
                sidecar = book_dir / "diagrams" / (Path(src).stem + ".json")
                if sidecar.exists():
                    bf = json.loads(sidecar.read_text(encoding="utf-8")).get("bf", {})
                    if bf.get("width") == "twothirds":
                        fig_style = ' style="width:66%;margin-left:auto;margin-right:auto"'
                return f'<figure class="svgfig"{fig_style}>{svg}{c}</figure>'
        return f'<figure><img src="{src}" alt="{alt}">{c}</figure>'
    html = re.sub(
        r'<p><img src="(?P<src>[^"]+)" alt="(?P<alt>[^"]*)"(?: title="(?P<title>[^"]*)")?\s*/?></p>',
        fig, html)
    return html


def _typesetline(book: dict, style: str) -> str:
    """판권면 조판·서체 표기. templates/base.typ colophon-fonts와 같은 규칙:
    typesetter 비우면 조판 문구를 빼고, 서체는 실제 본문 서체를 적는다."""
    ts = book.get("typesetter", "bookforge")
    face = ((book.get("fonts") or {}).get("ko") or {}).get("family")
    if not face:
        face = {"magazine": "Pretendard", "insight": "Noto Serif KR"}.get(style, "Pretendard")
    head = f"{ts}로 조판 · " if ts else ""
    return f"{head}본문 서체 {face}"


def inline_svg(book_dir, src: str):
    """assets의 SVG를 원문으로 읽어 폭 100% 스타일로 돌려준다. 없으면 None."""
    svg_path = book_dir / "assets" / src[len("../assets/"):]
    if not svg_path.exists():
        return None
    svg = svg_path.read_text(encoding="utf-8")
    svg = re.sub(r"^<!--bf:dsl=[^>]*-->\n?", "", svg)
    svg = re.sub(r'(<svg\b[^>]*?)\s+style="[^"]*"', r"\1", svg, count=1)
    return re.sub(r"<svg\b", '<svg style="width:100%;height:auto"', svg, count=1)


def apply_user_fonts(css: str, book: dict) -> str:
    """book.json "fonts"(언어별 사용자 폰트)를 테마 CSS의 폰트 변수 앞에 끼운다.

    스택 순서는 en → ja → ko. 앞 폰트에 없는 글자는 브라우저가 다음으로 넘기므로
    unicode-range 없이도 언어별 분담이 성립한다(영문 폰트에는 한자·한글이 없다).
    테마마다 변수 이름이 달라(--han/--serif/--display…) 이름 목록으로 훑는다.
    HTML 트랙은 .ttf만 받는다 — fontpick.py가 지정 시점에 이미 거른다.
    """
    fonts = book.get("fonts") or {}
    if not fonts:
        return css
    # 일본어 폰트에는 한글이 있는 경우가 많다(범CJK 계열). 범위를 안 걸면 본문 한글까지
    # 일본어 폰트가 먹어 Typst 트랙(lang-fonts는 ja를 가나·한자로 한정)과 결과가 갈린다.
    JA_RANGE = ("U+3000-303F,U+3040-30FF,U+31F0-31FF,U+3400-4DBF,U+4E00-9FFF,"
                "U+F900-FAFF,U+FF66-FF9D")
    faces, families = [], []
    for lang in ("en", "ja", "ko"):
        spec = fonts.get(lang)
        if not spec:
            continue
        fam = spec["family"]
        families.append(f'"{fam}"')
        rng = f"unicode-range:{JA_RANGE};" if lang == "ja" else ""
        for f in spec.get("files", []):
            if f.get("format") != "ttf":
                continue
            faces.append(f'@font-face{{font-family:"{fam}";'
                         f'src:url("{Path(f["path"]).as_uri()}");'
                         f'font-weight:{f.get("weight", 400)};font-style:normal;{rng}}}')
    if not families:
        return css
    pre = ", ".join(families) + ", "
    # --num은 숫자용(Barlow·Gmarket Sans)이다. 영문 폰트를 고르지 않았다면 건드리지 않는다.
    vars_ = "han|disp|serif|sans|display" + ("|num" if "en" in fonts else "")
    css = re.sub(rf"(--(?:{vars_})\s*:\s*)", r"\g<1>" + pre, css)
    return "\n".join(faces) + "\n" + css


def build(book_dir: Path, book: dict, outline: dict, style_dir: Path, skill: Path):
    ts = book_dir / "typeset"
    ts.mkdir(exist_ok=True)
    (book_dir / "draft").mkdir(exist_ok=True)

    tokens = json.loads((style_dir / "tokens.json").read_text(encoding="utf-8"))
    key = book.get("brand") or tokens.get("brand_default", "#0E7C7B")
    r_, g_, b_ = (int(key.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    cover_img = book_dir / "assets" / "cover.png"
    if not cover_img.exists():
        cover_img = book_dir / "assets" / "cover.jpg"

    tpl = Template((style_dir / "theme.html").read_text(encoding="utf-8"))
    css = Template((style_dir / "theme.css").read_text(encoding="utf-8")).safe_substitute(
        fonts_dir=(skill / "assets" / "fonts").as_uri(),
        key_color=key,
        key_tint=f"rgba({r_},{g_},{b_},0.08)",
    )

    css = apply_user_fonts(css, book)

    # refit-params.json: 장별 자간 미세조정(pagination.md §5 L2). 주의 — inline
    # letter-spacing은 테마 기본값을 대체하므로 refit.py가 (테마 기본 + Δ) 절대값을 준다.
    refit = {}
    rp = book_dir / "refit-params.json"
    if rp.exists():
        refit = json.loads(rp.read_text(encoding="utf-8"))

    # 목차 1면 수용 상한(스타일 tokens.json). 미선언이면 무제한 = 종전 동작 보존.
    _toc_sec_max = json.loads((style_dir / "tokens.json").read_text(encoding="utf-8")).get("toc_section_max")
    _toc_sec_total = 0
    if _toc_sec_max is not None:
        for _ch in outline["chapters"]:
            _p = book_dir / "chapters" / _ch["file"]
            if _p.exists():
                _toc_sec_total += len(re.findall(r"^##\s+", _p.read_text(encoding="utf-8"), re.M))
    toc_items, sections, tocmap_items, first_pull = [], [], [], None
    for idx, ch in enumerate(outline["chapters"], 1):
        mk = f"ch{idx:02d}"
        src = book_dir / "chapters" / ch["file"]
        raw = src.read_text(encoding="utf-8")
        # strip the leading H1 (title comes from outline)
        raw = re.sub(r"^#\s+.*\n", "", raw, count=1)
        img_m = re.search(r"!\[[^\]]*\]\((\.\./assets/[^) \"]+)", raw)
        # 목차 이미지 맵(magazine $tocmap): 챕터 첫 컷 4~6장. 캡션은 해당 쪽번호만 —
        # 좌측 리스트와 같은 .tocpg[data-mk] 마크업이라 2-pass 스탬핑이 같이 채운다.
        if img_m and len(tocmap_items) < 5:
            _tsvg = inline_svg(book_dir, img_m.group(1)) if img_m.group(1).endswith(".svg") else None
            tocmap_items.append(
                "<figure>" + (_tsvg or f'<img src="{img_m.group(1)}" alt="">')
                + f'<figcaption><span class="tocpg" data-mk="{mk}">00</span></figcaption></figure>')
        if first_pull is None:
            pm = re.search(r"^::: pull\n(.+)$", raw, re.M)
            if pm:
                first_pull = pm.group(1).strip()
        # 목차 2레벨(STYLE 목차 문법): 절 제목(## …)을 수집 — 콜아웃(:::) 안 줄 제외
        sec_titles = []
        in_callout = False
        for line in raw.split("\n"):
            st = line.strip()
            if not in_callout and CALLOUT_RE.match(st):
                in_callout = True
                continue
            if in_callout:
                if st == ":::":
                    in_callout = False
                continue
            if st.startswith("## "):
                sec_titles.append(st[3:].strip())
        body_html = md_to_html(raw, book_dir, idx)
        # 절 시작 페이지 마커: 각 <h2> 안에 pgmark 삽입 (2-pass에서 실페이지 회수)
        sec_no = [0]
        def mark_h2(_m):
            sec_no[0] += 1
            return f'<h2><span class="pgmark">@@{mk}s{sec_no[0]:02d}@@</span>'
        body_html = re.sub(r"<h2>", mark_h2, body_html)
        # 표 캡션 계약: 콘텐츠가 "[표] 제목 | 자료: 출처" 문단을 준 표만 라벨을 단다.
        # 자동 필러 라벨 금지 — 캡션 없는 표는 라벨 없이 그대로 렌더된다.
        tno = [0]
        def wrap_tbl(m):
            tno[0] += 1
            title = m.group(1).strip()
            source = (m.group(2) or "").strip()
            src_html = f'<div class="tbl-source">자료: {source}</div>' if source else ""
            return (f'<div class="tablewrap"><div class="tbl-caption">'
                    f'<span class="no">표 {idx}-{tno[0]}.</span> {title}</div>'
                    f'{m.group(3)}{src_html}</div>')
        body_html = re.sub(
            r"<p>\[표\]\s*(.+?)(?:\s*\|\s*자료\s*[:：]\s*(.+?))?</p>\s*(<table>.*?</table>)",
            wrap_tbl, body_html, flags=re.S)
        # 전면 요소(풀퀘트)는 다단 chapter-body 밖으로 분리
        body_html = re.sub(
            r'(<section class="pullquote">.*?</section>)',
            r'</div>\1<div class="chapter-body">',
            body_html, flags=re.S)
        summary = ch.get("summary") or ""
        sec = (
            f'<section class="chapter" id="{mk}">\n'
            f'<div class="opener"><span class="pgmark">@@{mk}@@</span>'
            f'<div class="opener-num">{idx:02d}</div>'
            f'<h1 class="opener-title">{ch["title"]}</h1>'
            f'<p class="opener-summary">{summary}</p></div>\n'
            f'<div class="chapter-body">{body_html}</div>\n</section>')
        # 풀퀘트 분리로 생긴 빈 chapter-body 제거 (백지면 방지) — refit 주입보다 먼저
        sec = re.sub(r'<div class="chapter-body">\s*</div>', "", sec)
        prm = refit.get(Path(ch["file"]).stem, {})
        if prm.get("letter_spacing_em") is not None:
            sec = sec.replace('<div class="chapter-body">',
                              f'<div class="chapter-body" style="letter-spacing:{prm["letter_spacing_em"]}em">')
        sections.append(sec)
        # data-sum: 목차 한줄 카피. outline의 toc_line(목차 전용 완결 카피)이 있으면 그것을,
        # 없으면 summary 40자 말줄임. 속성이라 이를 쓰지 않는 테마는 무시한다.
        tsum = re.sub(r"\s+", " ", ch.get("toc_line") or summary).strip()
        if len(tsum) > 40:
            tsum = tsum[:40].rstrip(" ,.·") + "…"
        toc_items.append(
            f'<li data-sum="{_esc(tsum, quote=True)}"><span class="toc-title">{ch["title"]}</span>'
            f'<span class="toc-leader"></span>'
            f'<span class="tocpg" data-mk="{mk}">00</span></li>')
        # 2레벨(절) 엔트리 — 색 위계(1레벨 cyan / 2레벨 teal)는 테마 CSS가 결정
        # 🚨 목차 본문(.toc-body)은 position:absolute 라 넘쳐도 면이 늘어나지 않고 **다음 면 위로
        #    흘러넘쳐 장 도비라와 겹쳐 인쇄된다**(실측: 7장·56절 → p3 에서 목차와 1장 도비라 중첩).
        #    겹침은 오버플로가 아니라 중첩이라 G3·G9 가 원리적으로 못 잡는다 — 시각 검수에서만 보인다.
        #    그래서 스타일이 선언한 1면 수용 상한을 넘으면 절을 전량 생략하고 장만 싣는다.
        _crowded = _toc_sec_max is not None and (
            _toc_sec_total > _toc_sec_max or len(outline["chapters"]) >= 7)
        if _crowded and _toc_sec_total > _toc_sec_max:
            sec_titles_for_toc = []
        else:
            sec_titles_for_toc = sec_titles
        for sidx, stitle in enumerate(sec_titles_for_toc, 1):
            toc_items.append(
                f'<li class="toc-sec"><span class="toc-sec-title">{_esc(stitle)}</span>'
                f'<span class="toc-leader"></span>'
                f'<span class="tocpg" data-mk="{mk}s{sidx:02d}">00</span></li>')

    # 판권면 서체 표기 — 사용자가 고른 서체는 라이선스 조건이 제각각이라 책에 남긴다
    fonts = book.get("fonts") or {}
    label = {"ko": "한국어", "ja": "일본어", "en": "영문"}
    fontline = ""
    names = " · ".join(f'{label[k]} {fonts[k]["family"]}' for k in ("ko", "ja", "en")
                       if k in fonts)
    if names:
        fontline = (f'<p>지정 서체 — {names}<br>'
                    '지정 서체의 사용·배포 조건은 각 서체의 라이선스를 따릅니다.</p>')
    html = tpl.substitute(
        title=book.get("title", ""), subtitle=book.get("subtitle") or "",
        author=book.get("author", "bookforge"), date=book.get("date", ""),
        typesetline=_typesetline(book, style_dir.name),
        brand=key,
        cover_art=f"background-image:url('{cover_img.as_uri()}')" if cover_img.exists() else "",
        # 장 행만으로도 한 면을 넘치는 구성(실측: 7장, 22pt 제목 4개가 2행 감김)은
        # 절 생략만으로 부족하다 — toc--crowd 로 제목 급수·행간을 한 단 내린다.
        toc="<ol class=\"toc" + (" toc--crowd" if _crowded else "") + "\">" + "\n".join(toc_items) + "</ol>",
        tocmap="\n".join(tocmap_items),
        backquote=book.get("backquote") or first_pull or book.get("subtitle") or "",
        body="\n".join(sections),
        css=css,
        fontline=fontline,
    )
    page1 = ts / "book.html"
    page1.write_text(html, encoding="utf-8")

    env = dict(os.environ)
    env["NODE_PATH"] = subprocess.run(["npm", "root", "-g"], capture_output=True,
                                      text=True).stdout.strip()
    printer = skill / "scripts" / "print_pdf.mjs"
    pdf1 = ts / "pass1.pdf"
    r = subprocess.run(["node", str(printer), str(page1), str(pdf1)],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.exit("HTML pass1 print failed:\n" + r.stderr)

    # pass 1: locate markers
    doc = fitz.open(pdf1)
    pages = {}
    for pno in range(doc.page_count):
        norm = re.sub(r"\s+", "", doc[pno].get_text())
        for m in re.findall(r"@@(ch\d+(?:s\d+)?)@@", norm):
            pages.setdefault(m, pno + 1)
    doc.close()

    # 목차 쪽번호는 폴리오 기준(본문 1쪽부터 — book-anatomy.md C9). 앞부속(표지·목차)
    # 오프셋 = 첫 장 시작 절대페이지 - 1. 지면 폴리오는 decorate.py가 같은 오프셋으로 찍는다.
    folio_offset = min(pages.values()) - 1 if pages else 0
    html2 = html
    for mk, abs_page in pages.items():
        html2 = html2.replace(f'<span class="tocpg" data-mk="{mk}">00</span>',
                              f'<span class="tocpg" data-mk="{mk}">{abs_page - folio_offset}</span>')
    # pass 2에는 마커 불필요 — 잉크·텍스트 레이어 오염 방지를 위해 제거
    # (.pgmark은 absolute 포지션이라 제거해도 리플로우 없음; 북마크는 pass 1 페이지맵 사용)
    html2 = re.sub(r'<span class="pgmark">@@ch\d+(?:s\d+)?@@</span>', "", html2)
    page2 = ts / "book-final.html"
    page2.write_text(html2, encoding="utf-8")

    out = book_dir / "draft" / "book.pdf"
    r = subprocess.run(["node", str(printer), str(page2), str(out)],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.exit("HTML pass2 print failed:\n" + r.stderr)

    # PDF outline(bookmarks): Chromium print emits none — stamp from markers
    doc = fitz.open(out)
    toc = []
    for idx, ch in enumerate(outline["chapters"], 1):
        mk = f"ch{idx:02d}"
        if mk in pages:
            toc.append([1, ch["title"], pages[mk]])
    if toc:
        doc.set_toc(toc)
    doc.saveIncr()
    doc.close()

    # optional theme post-decoration (running marks, folio) via PyMuPDF
    dec = style_dir / "decorate.py"
    if dec.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("theme_decorate", dec)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        doc = fitz.open(out)
        mod.decorate(doc, {"book": book, "pages": pages,
                           "fonts_dir": skill / "assets" / "fonts"})
        doc.saveIncr()
        doc.close()
    print(f"OK draft: {out} (chapter pages: {pages})")
