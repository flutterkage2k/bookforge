// bookforge style: practical — 실용·활용서 (견본: NIA 핵심용어집 실측 기반)
// This file is snapshotted into <book>/typeset/_style/ next to base.typ + meta.json.
#import "base.typ": *
#let code-font = ((name: "DejaVu Sans Mono", covers: regex("[A-Za-z0-9]")), "Pretendard")

#let meta = json("meta.json")

#let theme-tokens = default-tokens + (
  trim: (w: 153mm, h: 225mm),
  margin: (top: 20mm, bottom: 18mm, left: 17mm, right: 15mm),
  brand: rgb(meta.at("brand", default: "#1a5fb4")),
  brand-light: rgb(meta.at("brand_light", default: "#e8f0fa")),
  ink: rgb("#20242a"),
  muted: rgb("#6b7480"),
  // 정체성: 서술(읽는 글)은 명조, 조작·라벨·수치(하는 글)는 고딕 — STYLE.md §정체성.
  // 본문 내 숫자·라틴은 Pretendard(고딕)로 분리해 "수치는 고딕" 계약을 문장 안에서도 지킨다.
  body-font: lang-fonts(meta, ((name: "Pretendard", covers: regex("[A-Za-z0-9%]")), "Noto Serif KR")),
  sans-font: lang-fonts(meta, ("Pretendard", "Noto Serif KR")),
  display-font: lang-fonts(meta, ("Pretendard", "Noto Serif KR")),
  body-size: 9.8pt,       // 명조 9.8pt / 행송 18.28pt (KoPub바탕PL 9.8/19 실측 대체 — STYLE.md)
  // pitch 18.28pt = 판면 187mm(530pt) ÷ 정수 29행. Typst leading은 글리프 높이를 뺀
  // 잔여 간격이라 환산 필요: 실측 0.865em→15.62pt 기준 역산 1.137em ≈ 18.28pt.
  body-leading: 1.137em,
  heading2-size: 11.3pt,  // STYLE 폰트 스택: 소제목 Bold 11.3pt / brand
  heading3-size: 9.5pt,   // 하위 소제목 SemiBold 9.5pt (지면 위계 5단 상한 준수)
)

#let TT = theme-tokens
#let grid-pitch = 18.28pt  // 기준선 격자 1행 — 소제목·블록 여백은 이 배수로 스냅

// ---- STYLE.md 컬러 토큰 (brand 계열만 주제색 교체, 나머지는 고정) -----------
#let c-brand = TT.brand
#let c-pale = TT.brand-light            // brand-pale  — 목차 필 바탕
#let c-deep = TT.brand.darken(30%)      // brand-deep  — 밝은 바탕 위 브랜드 글자
#let c-high = rgb("#BDD756")            // highlight   — 브랜드 색면 위 라벨 (고정)
#let c-rule = rgb("#D9DCDE")            // rule        — 점 리더·괘선 (고정)

// ---- cover: STYLE 「표지 문법」 자산 0컷 대안(견본1형) --------------------------
// 파스텔 단색 배경 + 리본 배너 부제(높이 8mm, 좌우 화살 꼬리) + 중앙 정렬 주제목
// (주제목 중 한 단어만 brand 색 1.6배) + 하단 중앙 발행처 락업.
#let make-cover(meta) = {
  let t = TT
  let title-size = 78pt                  // STYLE: 표지 주제목 Black 78pt / 자간 −4%
  let words = meta.title.split(" ")
  let emph = words.last()                // brand 1.6배 확대 대상 = 표제 마지막 단어(핵심어)
  let head = words.slice(0, words.len() - 1).join(" ")
  let band-h = 8mm
  let band-w = 96mm
  let band-y = 56mm
  page(margin: 0mm, header: none, footer: none, fill: c-pale, {
    set par(justify: false, first-line-indent: 0em)
    set text(font: t.display-font, fill: t.ink)
    // 리본(꼬리+본체+부제) — 부제가 없으면 통째로 그리지 않는다(빈 파란 띠·떠 있는 꼬리 방지)
    let sub = meta.at("subtitle", default: none)
    if sub != none and str(sub).trim() != "" {
      place(top + left, dx: 153mm / 2 - band-w / 2 - 6mm, dy: band-y + 1.6mm,
        polygon(fill: c-deep, (0mm, 0mm), (8mm, 0mm), (8mm, band-h), (0mm, band-h), (2.6mm, band-h / 2)))
      place(top + left, dx: 153mm / 2 + band-w / 2 - 2mm, dy: band-y + 1.6mm,
        polygon(fill: c-deep, (0mm, 0mm), (8mm, 0mm), (5.4mm, band-h / 2), (8mm, band-h), (0mm, band-h)))
      place(top + center, dy: band-y,
        box(width: band-w, height: band-h, fill: c-brand,
          align(center + horizon,
            text(size: 12.5pt, weight: "bold", fill: white, tracking: 0.02em, sub))))
    }
    // 주제목 — 중앙 정렬, 마지막 단어만 brand 1.6배 (행 충돌 방지: stack으로 명시 간격)
    let title-top = band-y + band-h + 14mm
    let safe-w = 153mm - 2 * 14mm      // 좌우 안전 여백
    let make-title(s) = block(width: safe-w,
      stack(dir: ttb, spacing: calc.max(6mm, s * 0.42),
        ..if head != "" {
          (align(center, text(size: s, weight: "black", tracking: -0.04em,
            keep-words(head))),)
        } else { () },
        align(center, text(size: s * 1.6, weight: "black", tracking: -0.04em,
          fill: c-brand, emph))))
    // 급수 자동 축소: 78pt는 짧은 제목 기준값이다. 긴 제목·긴 단어를 그대로 그리면
    // 강조 단어(1.6배)가 판면을 넘어 G3(오버플로)로 떨어진다 — 실측: 5단어 제목에서 재현.
    context {
      let s = title-size
      let fits(sz) = {
        let m = measure(make-title(sz))
        let w = measure(text(size: sz * 1.6, weight: "black", tracking: -0.04em, emph)).width
        m.height <= 96mm and w <= safe-w
      }
      while s > 24pt and not fits(s) { s = s - 2pt }
      let title-block = make-title(s)
      place(top + center, dy: title-top, title-block)
      // 저자 — 제목 블록 실측 하단 아래로 밀어 배치(긴 제목이 여러 행으로 흐를 때 충돌 방지)
      if "author" in meta {
        place(top + center,
          dy: calc.max(178mm, title-top + measure(title-block).height + 8mm),
          text(size: 10pt, {
            text(weight: "bold", meta.author)
            text(weight: "regular", " 지음")
          }))
      }
    }
    // 발행처 락업 — 하단 중앙
    place(bottom + center, dy: -12mm, {
      let imprint = if opt(meta, "publisher") != none { opt(meta, "publisher") }
                    else { opt(meta, "author") }
      if imprint != none {
        align(center, {
          rect(width: 12mm, height: 0.8pt, fill: c-brand)
          v(2.4mm, weak: true)
          text(size: 9pt, weight: "semibold", tracking: 0.14em, upper(imprint))
        })
      }
    })
  })
}

// ---- chapter opener: full-bleed brand page, giant number --------------------
#let practical-opener(n, title, summary, t) = {
  full-bleed(t, block(fill: t.brand, width: 100%, height: 100%, inset: (x: 20mm, y: 24mm), {
    set text(fill: white, font: t.display-font)
    text(size: 9pt, tracking: 0.18em, weight: "semibold", fill: white.transparentize(30%), "CHAPTER")
    v(4pt)
    text(size: 70pt, weight: "black", numpad(n))
    v(1.6em)
    line(length: 34%, stroke: 1pt + white.transparentize(45%))
    v(1.4em)
    text(size: 22pt, weight: "bold", keep-words(title))
    if summary != none {
      v(2em)
      set text(size: 10pt, weight: "regular", fill: white.transparentize(12%))
      set par(leading: 0.95em, justify: false)
      block(width: 80%, summary)
    }
  }))
}

// ---- TOC (STYLE.md「목차 문법」— v2 재설계) ---------------------------------
// 헤더 밴드 42mm(우하단 r12mm, CONTENTS 백색 라벨 + 차례 표제) → 장·절 목록.
// 파트 배지는 단일 파트 책에서 허구가 되므로 제거 — 파트 구조가 실재하는 원고가
// 생기면 그때 파트 계층으로 복원한다 (구판의 "PART 01 + 책 제목 재출력" 결함 수리).
// 행 계약: 급수 고정(장 9.5 / 절 8.5pt) — 자동 축소 금지. 넘치는 제목은 행잉
// 인덴트로 줄바꿈하고 리더·쪽번호는 마지막 줄 끝에 앉는다(상업 목차 관행).
// 한 행 안의 칩·제목·쪽번호는 같은 문단 흐름 = 단일 기준선.
#let toc-band-h = 42mm
#let toc-list-y = toc-band-h + 12mm
#let toc-gutter = 11.8mm     // 2단 변형 거터
#let toc-chip-w = 11.5mm

// 점 리더 — 0.5pt 원점, 간격 2pt, rule
#let toc-leader(pad) = box(width: 1fr, inset: (x: pad),
  repeat(gap: 2pt, box(baseline: -0.85pt,
    circle(radius: 0.33pt, fill: c-rule, stroke: none))))

// 장(H1) 항목 — [CH│NN 칩] 제목 … 쪽번호 (한 문단 = 한 기준선, 랩 허용)
#let toc-ch-row(n, hd, t) = link(hd.location(),
  par(hanging-indent: toc-chip-w + 3mm, leading: 0.55em, justify: false, spacing: 0pt, {
    box(width: toc-chip-w, height: 4.7mm, fill: c-pale, radius: 1mm, baseline: 1.1mm,
      align(center + horizon, text(font: TT.sans-font, size: 6.9pt, weight: "bold",
        fill: c-deep, tracking: 0.02em, number-width: "tabular", {
          // 구분자는 도형 rect — '│'(U+2502)는 Pretendard 미커버라 4번째 서체가 폴백 임베드됨
          "CH"
          h(1.4pt)
          box(baseline: 12%, rect(width: 0.6pt, height: 6.4pt, fill: c-deep.transparentize(35%)))
          h(1.4pt)
          numpad(n)
        })))
    h(3mm)
    text(font: TT.sans-font, size: 9.5pt, weight: "regular", fill: t.ink, hd.body)
    toc-leader(2mm)
    box(text(font: TT.sans-font, size: 9.5pt, weight: "medium", fill: t.ink,
      number-width: "tabular", str(counter(page).at(hd.location()).first())))
  }))

// 절(H2) 항목 — 들여쓰기 + 제목 … 쪽번호
#let toc-sub-row(hd, t) = link(hd.location(),
  par(hanging-indent: toc-chip-w + 3mm + 2mm, leading: 0.55em, justify: false, spacing: 0pt, {
    h(toc-chip-w + 3mm)
    text(font: TT.sans-font, size: 8.5pt, weight: "light", fill: t.ink, hd.body)
    toc-leader(1.3mm)
    box(text(font: TT.sans-font, size: 8.5pt, weight: "light", fill: t.muted,
      number-width: "tabular", str(counter(page).at(hd.location()).first())))
  }))

#let practical-toc(meta, t, title: "차례") = {
  let list-w = t.trim.w - t.margin.left - t.margin.right
  let cw = (list-w - toc-gutter) / 2
  page(header: none, footer: none, margin: 0mm, fill: t.paper, {
    set par(justify: false, first-line-indent: 0em)

    // ① 헤더 밴드 — 풀블리드, 우하단 모서리만 r12mm. 라벨은 백색(브랜드 위 대비 보장).
    place(top + left, rect(width: t.trim.w, height: toc-band-h, fill: c-brand,
      stroke: none, radius: (bottom-right: 12mm)))
    place(top + left, dx: t.margin.left + 10mm, dy: 15.0mm,
      text(font: TT.sans-font, size: 8pt, weight: "bold", tracking: 0.26em,
        fill: white.transparentize(18%), "CONTENTS"))
    place(top + left, dx: t.margin.left + 10mm, dy: 20.2mm,
      text(font: TT.display-font, size: 23pt, weight: "black", tracking: -0.03em,
        fill: white, title))

    // ② 항목 — 장(H1) + 그에 속한 절(H2)을 한 그룹으로
    context {
      let groups = ()
      for hd in query(heading).filter(hd => hd.level <= 2) {
        if hd.level == 1 { groups.push((ch: hd, subs: ())) }
        else if groups.len() > 0 {
          let g = groups.pop()
          g.subs.push(hd)
          groups.push(g)
        }
      }
      if groups.len() == 0 { return }

      let group-block(i, w) = block(
        breakable: false, width: w, above: 0pt, below: 3.2mm, spacing: 0pt, {
          show link: it => text(fill: t.ink, it)   // 목차 글자에 별색 금지
          toc-ch-row(i + 1, groups.at(i).ch, t)
          for s in groups.at(i).subs { v(1.4mm); toc-sub-row(s, t) }
        })

      // 실측 균형 분할 — 랩으로 행 높이가 가변이므로 measure로 실제 높이를 잰다
      let gh = groups.enumerate().map(((i, g)) => measure(group-block(i, cw)).height + 3.2mm)
      let total-1col = groups.enumerate().map(((i, g)) =>
        measure(group-block(i, list-w)).height + 3.2mm).fold(0pt, (a, b) => a + b)
      let avail = t.trim.h - t.margin.bottom - toc-list-y

      if total-1col > avail and groups.len() > 1 {
        // 2단 변형 — 그룹 단위 균형 분할 (실측 높이 기준)
        let total = gh.fold(0pt, (a, b) => a + b)
        let k = 1
        let bd = none
        let cum = 0pt
        for i in range(1, groups.len()) {
          cum = cum + gh.at(i - 1)
          let d = calc.abs((cum - total / 2).pt())
          if bd == none or d < bd { bd = d; k = i }
        }
        let h1 = gh.slice(0, k).fold(0pt, (a, b) => a + b)
        let h2 = gh.slice(k).fold(0pt, (a, b) => a + b)
        place(top + left, dx: t.margin.left, dy: toc-list-y,
          block(width: cw, for i in range(0, k) { group-block(i, cw) }))
        place(top + left, dx: t.margin.left + cw + toc-gutter, dy: toc-list-y,
          block(width: cw, for i in range(k, groups.len()) { group-block(i, cw) }))
        place(top + left, dx: t.margin.left + cw + toc-gutter / 2, dy: toc-list-y,
          line(angle: 90deg, length: calc.max(h1, h2), stroke: 0.3pt + c-brand))
      } else {
        place(top + left, dx: t.margin.left, dy: toc-list-y,
          block(width: list-w, for i in range(0, groups.len()) { group-block(i, list-w) }))
      }
    }
  })
}

// ---- 마스터 래퍼: base.book()에서 TOC만 교체 --------------------------------
#let book(meta: (:), tokens: (:), cover: none, toc: true, toc-title: "차례",
          toc-cols: 1, body) = {
  let t = merged(tokens)

  set document(title: meta.at("title", default: "무제"), author: meta.at("author", default: "bookforge"))
  set page(
    width: t.trim.w, height: t.trim.h,
    margin: (top: t.margin.top, bottom: t.margin.bottom, left: t.margin.left, right: t.margin.right),
    fill: t.paper,
    // 러닝 시스템 = 러닝푸터만 (STYLE.md §러닝 — 기본 판형에서 러닝헤드는 쓰지 않는다).
    // 좌 = 유닛 라벨(CH NN · 장제목) muted / 우 = 쪽번호 Bold brand, 우측(바깥) 정렬.
    footer: context {
      let pn = counter(page).get().first()
      let prev = query(heading.where(level: 1).before(here()))
      set text(font: t.sans-font, size: 7.5pt, fill: t.muted, tracking: 0.04em)
      if prev.len() > 0 {
        // heading numbering이 none이라 counter는 0 — 실재 헤딩 수로 서수 산출
        let idx = prev.len()
        text(weight: "semibold", fill: t.brand, "CH " + numpad(idx))
        h(2mm)
        prev.last().body
      }
      h(1fr)
      text(size: 8pt, weight: "bold", fill: t.brand, number-width: "tabular", str(pn))
    },
    header: none,
  )
  set text(font: t.body-font, size: t.body-size, fill: t.ink, lang: "ko", region: "KR")
  set raw(theme: code-theme)
  set text(costs: (orphan: 100%, widow: 100%, runt: 200%))
  // STYLE B-1: 첫 줄 들여쓰기 없음, 단락 간격은 격자 1행으로 대체 —
  // spacing = leading + pitch ⇒ 문단 사이 기준선 거리 = 정확히 2행(격자 유지)
  set par(justify: true, leading: t.body-leading, spacing: t.body-leading + grid-pitch)

  // 소제목(md ##) = STYLE 「소제목 H3」: Bold 11.3pt / brand, 위 2행·아래 1행 격자 스냅
  // (아래 여백은 다음 행 어센트 ~6pt를 빼야 실측 간격이 정확히 1행 = 18.28pt가 된다)
  show heading.where(level: 2): it => {
    v(2 * grid-pitch, weak: true)
    block(sticky: true, text(font: t.sans-font, size: t.heading2-size, weight: "bold",
      fill: t.brand, tracking: -0.02em, it.body))
    v(grid-pitch - 6pt, weak: true)
  }
  show heading.where(level: 3): it => {
    v(1 * grid-pitch, weak: true)
    block(sticky: true, {
      box(baseline: -0.12em, circle(radius: 2.2pt, fill: t.brand))
      h(6pt)
      text(font: t.sans-font, size: t.heading3-size, weight: "semibold", fill: c-deep, it.body)
    })
    v(0.5 * grid-pitch, weak: true)
  }
  set heading(numbering: none)

  show quote.where(block: true): it => block(
    inset: (left: 1.2em, y: 0.3em),
    stroke: (left: 2pt + t.brand.transparentize(50%)),
    text(fill: t.ink.transparentize(15%), it.body))
  // "하는 글"(조작 절차·항목)은 고딕 — 서술 명조와 서체로 역할 분리 (STYLE.md §정체성)
  set list(marker: ([•], [–]), indent: 0.5em)
  set enum(indent: 0.5em)
  show list: set text(font: t.sans-font, size: 9.2pt)
  show enum: set text(font: t.sans-font, size: 9.2pt)
  show raw.where(block: true): it => block(
    width: 100%, fill: luma(247), radius: 4pt, inset: 9pt, breakable: true,
    text(font: code-font, size: 8pt, it))
  show raw.where(block: false): it => box(fill: luma(243), radius: 2pt, inset: (x: 3pt, y: 1pt), text(font: code-font, size: 0.92em, it))
  // STYLE 표 규약: 세로 괘선 없음, 헤더 = brand-pale 필 + 하단 brand 0.5pt + brand-deep 글자,
  // 본문행 하단 0.3pt rule. 표 폭 = 판면 폭(md2typ이 (1fr,)*n 컬럼으로 강제).
  set table(
    stroke: (x, y) => if y == 0 { (bottom: 0.5pt + c-brand) } else { (bottom: 0.3pt + c-rule) },
    inset: (x: 7pt, y: 5pt),
  )
  show table: it => {
    set text(size: 8.4pt, font: t.sans-font)
    it
  }
  show table.cell.where(y: 0): it => text(weight: "bold", fill: c-deep, it)
  set table(fill: (x, y) => if y == 0 { c-pale } else { none })
  show figure.where(kind: table): set figure.caption(position: top)
  // 그림 캡션: 1컷 좌측 정렬 (급수·색은 bookfig가 지정 — ▲ + Light 7.5pt / ink)
  show figure.caption: it => block(width: 100%, align(left, it))
  show link: it => text(fill: t.brand, it)

  if cover != none { cover }
  title-page(meta, t)
  if toc { practical-toc(meta, t, title: toc-title) }
  counter(page).update(1)

  body
}

// ---- baked helpers for converter output ------------------------------------
#let bf-chapter(title, summary: none) = chapter(title, summary: summary, t: TT, opener: practical-opener)
#let bf-callout(kind: "info", title: none, body) = callout(kind: kind, title: title, t: TT, body)
#let bf-stat(value, label) = stat(value, label, t: TT)
#let bf-fig(path, caption: none, source: none, width: 100%) = bookfig(path, caption: caption, source: source, width: width, t: TT)
#let bf-tbl(caption: none, source: none, body) = bf-tbl-base(caption: caption, source: source, t: TT, body)
