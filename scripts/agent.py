#!/usr/bin/env python3
"""bookforge 자동 집필 — 목차·원고를 Claude Code(claude CLI)에게 맡긴다.

    python3 scripts/agent.py research <book_dir> [--topic "주제"]
    python3 scripts/agent.py outline  <book_dir>
    python3 scripts/agent.py chapter  <book_dir> ch-01.md
    python3 scripts/agent.py all      <book_dir>
    python3 scripts/agent.py fix      <book_dir> [--rounds 6]
    python3 scripts/agent.py diagrams <book_dir> [--figs 3]
    python3 scripts/agent.py auto     <book_dir>   # 조사→목차→집필→도해→통과까지 한 번에

이 스킬의 집필 주체는 스크립트가 아니라 에이전트다. 웹 UI에서도 같은 일을 하려면
로컬에 설치된 `claude`를 헤드리스(-p)로 부르는 수밖에 없다 — 그 다리를 놓는 파일이다.
(사용자의 Claude Code 구독으로 실행된다. 없으면 CLI 설치 안내를 내고 멈춘다.)

산출물은 stdout으로 받아 이 스크립트가 파일에 쓴다. 에이전트에게 쓰기 권한을 주지
않으므로, 프롬프트가 무엇을 하든 건드릴 수 있는 파일은 여기서 정한 것뿐이다.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent

# 스타일별 집필 브리프 — STYLE.md 전문을 넣으면 프롬프트가 비대해진다. 집필에 실제로
# 영향을 주는 항목(정체성·구성·지면 요소)만 요약해 둔다.
BRIEF = {
    "practical": ("따라 하면 결과가 나오는 실용서. 반복 단위(패턴·절차)를 장으로 묶는다. "
                  "각 장은 규칙 → 예시 → 적용 순서. 표와 콜아웃을 적극적으로 쓴다.",
                  (2000, 3000)),
    "insight": ("기술 동향 리포트. 1장은 요약 성격, 이후 본론, 마지막은 시사점. "
                "단정보다 근거. 표·콜아웃으로 근거를 정리한다.", (1800, 2600)),
    "academic": ("학술 개론서. 서론(문제 제기) → 본론(논점) → 결론. 절 제목에는 번호를 "
                 "직접 쓰지 않는다(조판이 자동으로 붙인다). 정의는 info 콜아웃으로.", (2000, 2800)),
    "essay": ("산문. 표·불릿을 최소화하고 문단과 인용(>)으로 흐른다. 1인칭 관찰과 "
              "생각의 전개가 중심. 콜아웃은 쓰지 않거나 아주 드물게.", (1200, 1800)),
    "business": ("컨설팅 백서. 장 제목은 완결 문장(액션 타이틀). 한 문단은 8행 이내로 "
                 "짧게 끊는다. 표·콜아웃을 3면마다 하나 이상 배치한다.", (1600, 2200)),
    "magazine": ("잡지 피처. 각 장은 서로 다른 각도의 기사. 짧은 문단과 소제목, "
                 "풀퀘트(::: pull)를 장마다 한 번 넣는다.", (900, 1400)),
}
CHAPTERS = {"short": (5, 7), "standard": (8, 12), "long": (14, 20)}

CONTRACT = """쓸 수 있는 문법은 다음뿐이다.
- 첫 줄은 `# {장 제목}` 하나. 목차의 제목과 정확히 같아야 한다.
- `## 절 제목`, `### 항 제목`
- 문단, `**굵게**`, 불릿(`- `), 번호 목록, `> 인용`
- GFM 표: `| 열 | 열 |` (헤더 구분선 필수)
- 콜아웃: 줄 맨 앞에 `::: tip 제목` … 새 줄에 `:::` (종류 info·tip·warn·quote·pull)
금지:
- 이미지·도해 삽입(`![...]`)
- 전체를 코드펜스(```)로 감싸기
- 자료에 없는 수치·통계·연도·기관명·인용문 (지어내면 게이트 G10이 잡는다)
- 콜아웃에만 등장하는 숫자 (본문에도 같은 수치가 있어야 한다)
- AI 자기언급, 과장, "결론적으로" 같은 상투구"""


def die(msg: str):
    print(f"AGENT FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


MODEL = "sonnet"  # 조사·집필·수정 모두 sonnet으로 충분하다(--model로 교체 가능)


def claude(prompt: str, timeout: int = 900, tools: str | None = None) -> str:
    """헤드리스 claude 호출. tools를 주지 않으면 도구 없이 텍스트만 받는다."""
    exe = shutil.which("claude")
    if not exe:
        die("`claude` 명령을 찾지 못했습니다. Claude Code를 설치하면 자동 집필이 켜집니다.")
    argv = [exe, "-p", prompt, "--output-format", "text", "--model", MODEL]
    if tools:
        argv += ["--allowed-tools", tools]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=str(SKILL))
    except subprocess.TimeoutExpired:
        die(f"claude 응답이 {timeout}초를 넘었습니다.")
    if p.returncode != 0:
        die("claude 실행 실패:\n" + (p.stderr or p.stdout)[:800])
    out = p.stdout.strip()
    if not out:
        die("claude가 빈 응답을 돌려줬습니다.")
    return out


def load(book_dir: Path):
    book = json.loads((book_dir / "book.json").read_text(encoding="utf-8"))
    style = book.get("style", "practical")
    if style not in BRIEF:
        die(f"모르는 스타일: {style}")
    research = ""
    rp = book_dir / "research.md"
    if rp.exists():
        research = rp.read_text(encoding="utf-8").strip()
    return book, style, research


def strip_fence(text: str) -> str:
    """모델이 전체를 코드펜스로 감싸면 벗긴다."""
    m = re.match(r"^```[a-zA-Z]*\n(.*)\n```$", text.strip(), re.S)
    return m.group(1).strip() if m else text.strip()


def as_chapter(text: str) -> str | None:
    """응답에서 원고 부분만 꺼낸다 — 앞머리 인사말이 붙어 오는 경우가 잦다."""
    text = strip_fence(text)
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            return "\n".join(lines[i:]).strip()
    return None


def cmd_research(book_dir: Path, topic: str | None, web: bool = False,
                 max_queries: int = 6, today: str = ""):
    book, style, _ = load(book_dir)
    subject = topic or book.get("title") or book_dir.name
    if web:
        return _research_web(book_dir, subject, max_queries, today)
    prompt = f"""주제 「{subject}」로 한국어 단행본을 쓰기 위한 조사 노트를 작성한다.

너의 지식만으로 쓴다. 확실하지 않은 것은 쓰지 말고, 애매하면 "확인 필요"로 표시한다.
수치·통계·연도·기관명은 출처를 함께 댈 수 있는 것만 적는다. 없으면 일반 원리로 서술한다.

마크다운으로 다음 항목을 채운다(설명·인사말 없이 노트만 출력):
## 핵심 개념
## 구조·분류
## 실제 사례
## 자주 오해하는 지점
## 확인 필요 (내가 확신하지 못하는 것)

분량은 1,500자 안팎."""
    text = strip_fence(claude(prompt))
    out = book_dir / "research.md"
    prev = out.read_text(encoding="utf-8").strip() if out.exists() else ""
    merged = (prev + "\n\n---\n\n" + text).strip() if prev else text
    out.write_text(merged + "\n", encoding="utf-8")
    print(f"OK research: {out} ({len(merged)}자)")


def _research_web(book_dir: Path, subject: str, max_queries: int, today: str):
    """검색은 '지금 확인해야만 하는 것'에만 쓴다.

    무작정 많이 긁으면 비용만 늘고 정확도는 안 오른다. 그래서 두 단계로 묶는다.
    ① 검색 없이, 확인이 필요한 질문을 최대 N개 뽑는다(개념 설명은 질문에서 제외 —
       그건 모델 지식으로 충분하고 시간이 지나도 안 변한다).
    ② 질문 하나당 검색 한 번. 결과에서 답 문장만 취하고 출처 URL과 확인일을 붙인다.
    상한은 질문 수 하나로 통제된다 — 검색 N회, 그 이상은 없다.
    """
    prompt = f"""주제 「{subject}」로 한국어 단행본을 쓰기 위한 조사 노트를 만든다.
오늘 날짜는 {today}이다.

작업 순서를 반드시 지켜라.

1단계(검색 금지). 이 주제에서 **시간이 지나면 변하는 사실**만 골라 확인 질문을
최대 {max_queries}개 만든다. 다음에 해당하는 것만 질문으로 삼는다:
가격·요금·한도, 버전·릴리스, 정책·약관, 통계·점유율, 날짜·일정, 조직·제품명 변경.
개념 정의·원리·역사처럼 변하지 않는 것은 질문으로 만들지 않는다(네 지식으로 쓴다).

2단계. 질문 하나당 웹 검색을 **한 번씩만** 한다. 검색 횟수는 질문 수를 넘지 않는다.
결과에서 답에 해당하는 문장만 취한다. 못 찾으면 "확인 실패"로 남기고 다음으로 넘어간다.

3단계. 아래 형식의 마크다운만 출력한다(설명·인사말 금지, 2,500자 이내).

## 확인된 사실
- 사실 한 줄. (출처: URL, 확인 {today})

## 개념 정리
(검색 없이 네 지식으로 쓰는 부분. 정의·구조·원리)

## 실제 사례

## 자주 오해하는 지점

## 확인 필요
- 검색으로도 확정하지 못한 것. 저자가 직접 확인해야 하는 항목."""
    text = strip_fence(claude(prompt, timeout=1800, tools="WebSearch"))
    out = book_dir / "research.md"
    prev = out.read_text(encoding="utf-8").strip() if out.exists() else ""
    merged = (prev + "\n\n---\n\n" + text).strip() if prev else text
    out.write_text(merged + "\n", encoding="utf-8")
    n = text.count("출처:")
    print(f"OK research(web): {out} ({len(merged)}자, 출처 표기 {n}건, 검색 상한 {max_queries}회)")


def cmd_outline(book_dir: Path):
    book, style, research = load(book_dir)
    brief, _ = BRIEF[style]
    lo, hi = CHAPTERS.get(book.get("length", "short"), (5, 7))
    prompt = f"""한국어 단행본의 목차를 설계한다. JSON만 출력한다(설명·코드펜스 금지).

제목: {book.get('title')}
부제: {book.get('subtitle') or '(없음)'}
스타일: {style} — {brief}
장 수: {lo}~{hi}개

아래는 저자가 모은 자료다. 목차는 이 자료가 뒷받침할 수 있는 범위에서만 설계한다.
자료에 없는 주제를 장으로 만들지 않는다.
--- 자료 시작 ---
{research or '(자료 없음 — 일반적으로 통용되는 내용만으로 설계한다)'}
--- 자료 끝 ---

출력 형식:
{{"chapters": [{{"title": "장 제목", "summary": "장 도비라에 실릴 1~2문장", "toc_line": "목차에 실릴 완결된 한 줄"}}]}}

규칙:
- title은 장 번호를 포함하지 않는다.
- summary는 그 장이 답하는 질문을 담는다.
- toc_line은 40자 이내의 완결 문구.
- 장 순서는 독자가 읽는 순서다. 앞 장이 뒷 장의 전제가 되게 배열한다."""
    raw = strip_fence(claude(prompt))
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        die("목차 JSON을 찾지 못했습니다:\n" + raw[:400])
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        die(f"목차 JSON 파싱 실패: {e}\n{raw[:400]}")
    chapters = data.get("chapters") or []
    if not chapters:
        die("목차가 비었습니다.")
    rows, made = [], []
    for i, c in enumerate(chapters, 1):
        title = (c.get("title") or "").strip()
        if not title:
            continue
        f = f"ch-{i:02d}.md"
        rows.append({"file": f, "title": title,
                     "summary": (c.get("summary") or "").strip(),
                     "toc_line": (c.get("toc_line") or "").strip()})
        p = book_dir / "chapters" / f
        if not p.exists():
            p.write_text(f"# {title}\n\n", encoding="utf-8")
            made.append(f)
    (book_dir / "outline.json").write_text(
        json.dumps({"chapters": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK outline: {len(rows)}장" + (f" · 새 원고 {len(made)}개" if made else ""))


def cmd_chapter(book_dir: Path, filename: str):
    book, style, research = load(book_dir)
    brief, (lo, hi) = BRIEF[style]
    outline = json.loads((book_dir / "outline.json").read_text(encoding="utf-8"))["chapters"]
    ch = next((c for c in outline if c["file"] == filename), None)
    if not ch:
        die(f"목차에 없는 파일: {filename}")
    idx = outline.index(ch) + 1
    toc = "\n".join(f"{i}. {c['title']} — {c.get('summary','')}" for i, c in enumerate(outline, 1))
    prompt = f"""한국어 단행본의 한 장을 쓴다. 마크다운 원고만 출력한다(설명·인사말 금지).

책 제목: {book.get('title')}
스타일: {style} — {brief}
전체 목차:
{toc}

이번에 쓸 장: {idx}장 「{ch['title']}」
이 장의 요약(도비라에 실림): {ch.get('summary','')}
분량: {lo}~{hi}자

아래는 저자가 모은 자료다. 사실·수치·사례는 이 자료 안에서만 가져온다.
--- 자료 시작 ---
{research or '(자료 없음 — 일반적으로 통용되는 내용만 쓴다. 수치는 쓰지 않는다)'}
--- 자료 끝 ---

{CONTRACT}

구성 지침:
- 첫 문단은 이 장이 다루는 문제를 세우고, 마지막 문단은 다음 장으로 넘어가는 정리를 한다.
- 절({'##'})은 2~4개. 각 절은 규칙이나 기준을 먼저 제시하고 예로 검증한다.
- 앞뒤 장과 내용이 겹치지 않게 한다."""
    text = as_chapter(claude(prompt))
    if not text:
        die("응답에서 '# 제목'으로 시작하는 원고를 찾지 못했습니다.")
    first = text.splitlines()[0].strip()
    if first[2:].strip() != ch["title"]:
        text = f"# {ch['title']}\n" + "\n".join(text.splitlines()[1:])
    (book_dir / "chapters" / filename).write_text(text.rstrip() + "\n", encoding="utf-8")
    print(f"OK chapter: {filename} ({len(text)}자)")


def _outline_is_stub(book_dir: Path) -> bool:
    """scaffold가 넣어 둔 자리표시자('1장 제목')는 목차가 아니다."""
    p = book_dir / "outline.json"
    if not p.exists():
        return True
    chapters = json.loads(p.read_text(encoding="utf-8")).get("chapters") or []
    return not chapters or all("장 제목" in (c.get("title") or "") for c in chapters)


def cmd_all(book_dir: Path):
    if _outline_is_stub(book_dir):
        cmd_outline(book_dir)
    outline = json.loads((book_dir / "outline.json").read_text(encoding="utf-8"))["chapters"]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as ex:  # 장 7개를 순차로 부르면 7~10분 걸린다
        list(ex.map(lambda c: cmd_chapter(book_dir, c["file"]), outline))
    print(f"OK all: {len(outline)}장 집필 완료 — 이제 빌드하세요.")



# 한 행에 들어가는 글자 수(스타일 판면 실측 근사) — 게이트가 말하는 "몇 행"을
# 원고에서 조절할 "몇 자"로 바꾸는 데 쓴다.
CHARS_PER_LINE = {"practical": 35, "insight": 33, "academic": 31,
                  "essay": 26, "business": 36, "magazine": 28}


def _chapter_of(page: int, starts: list) -> str | None:
    """페이지 번호 → 그 페이지가 속한 장의 파일명."""
    cur = None
    for start, f in starts:
        if start <= page:
            cur = f
        else:
            break
    return cur


def _fix_plan(book_dir: Path, style: str) -> list:
    """gate-report + PDF 북마크 → [(파일명, 글자수 증감, 사유)] 계획.

    게이트는 '몇 행 모자라다'까지만 말한다. 그 행을 어느 장에서 만들지는
    장 시작 쪽번호로 역산해야 한다 — 그 역산이 이 함수다.
    """
    import pymupdf
    report = json.loads((book_dir / "gate-report.json").read_text(encoding="utf-8"))
    gates, metrics = report["gates"], report["metrics"]
    outline = json.loads((book_dir / "outline.json").read_text(encoding="utf-8"))["chapters"]
    doc = pymupdf.open(book_dir / "draft" / "book.pdf")
    titles = {c["title"]: c["file"] for c in outline}
    starts = sorted((t[2], titles[t[1]]) for t in doc.get_toc() if t[0] == 1 and t[1] in titles)
    doc.close()
    if not starts:
        die("PDF 북마크에서 장 시작 쪽을 찾지 못했습니다.")
    cap = max((p["lines"] for p in metrics["pages"]), default=30)
    cpl = CHARS_PER_LINE.get(style, 33)
    plan = {}

    def add(page, lines, why):
        f = _chapter_of(page, starts)
        if not f:
            return
        delta = int(lines * cpl)
        if f in plan:  # 같은 장에 요구가 겹치면 큰 쪽을 남긴다
            if abs(plan[f][0]) >= abs(delta):
                return
        plan[f] = (delta, why)

    # 장별 본문 행수 — 흡수예산(pagination.md §4) 판정에 쓴다
    by_page = {p["page"]: p for p in metrics["pages"]}
    bounds = {}
    for i, (start, f) in enumerate(starts):
        end = starts[i + 1][0] - 1 if i + 1 < len(starts) else max(by_page)
        bounds[f] = (start, end)

    for tail in gates.get("G7-TAIL", {}).get("tails", []):
        pg, reach, lines = tail["page"], tail["reach"], tail["lines"]
        f = _chapter_of(pg, starts)
        span = bounds.get(f, (pg, pg))
        ch_lines = sum(by_page[p]["lines"] for p in range(span[0], span[1] + 1) if p in by_page)
        # 흡수예산: 꼬리가 장 전체의 2.2% 이내면 앞으로 당겨 없애는 편이 싸다.
        # 그 밖이면 늘려서 채우되, 반 면 넘게 늘려야 하면 그것도 줄이는 쪽이 싸다(실측: 늘리기는 진동한다).
        need = (0.88 - reach) * cap
        if lines < 6 or lines <= 0.022 * ch_lines or need > 0.5 * cap:
            add(pg, -(lines + 3), f"장 끝 면 {lines}행({reach:.2f}) — 앞 면으로 당겨 없앤다")
        elif reach < 0.75:
            add(pg, need, f"장 끝 면 채움 {reach:.2f} — 0.88까지 올린다")
    for u in gates.get("G7-MID", {}).get("underfull", []):
        add(u["page"], (0.95 - u["reach"]) * cap, f"장 중간 면 {u['page']}이 {u['reach']:.2f}로 비어 있음")
    # 제목이 면 끝에 홀로 남은 경우 — 앞 문단을 조금 늘려 제목을 다음 면으로 밀어낸다
    for v in gates.get("G9", {}).get("violations", []):
        m = re.match(r"p(\d+):", v)
        if m:
            add(int(m.group(1)), 3, f"면 끝에 제목이 홀로 남음({v[:40]})")
    out = []
    for f, (d, why) in plan.items():
        cur = len((book_dir / "chapters" / f).read_text(encoding="utf-8"))
        d = int(max(-0.3 * cur, min(0.3 * cur, d)))  # 한 회차에 ±30%까지만 — 3배로 부푸는 사고 방지
        if abs(d) >= 30:
            out.append((f, d, why))
    return out


def cmd_fix(book_dir: Path, rounds: int):
    """빌드 → 게이트 → 실패한 장 분량 조절을 통과할 때까지 반복한다."""
    book, style, _ = load(book_dir)
    history: dict[str, int] = {}
    for r in range(1, rounds + 1):
        b = subprocess.run([sys.executable, str(SKILL / "scripts/build.py"), str(book_dir)],
                           capture_output=True, text=True, timeout=3600)
        if b.returncode != 0:
            die("빌드 실패:\n" + (b.stderr or b.stdout)[-800:])
        q = subprocess.run([sys.executable, str(SKILL / "scripts/qc_gate.py"), str(book_dir)],
                           capture_output=True, text=True, timeout=3600)
        out = (q.stdout + q.stderr).strip()
        if q.returncode == 0:
            print(f"[{r}회차] 게이트 통과")
            print(out.splitlines()[-1] if out else "")
            return
        fails = [l for l in out.splitlines() if l.startswith("FAIL")]
        print(f"[{r}회차] 실패 {len(fails)}건: " + " / ".join(f[:60] for f in fails[:3]))
        plan = _fix_plan(book_dir, style)
        for i, (f, d, why) in enumerate(plan):
            prev = history.get(f)
            if prev is not None and (prev > 0) == (d > 0) and abs(prev) > 0:
                # 같은 방향으로 또 밀라고 나왔다 = 지난 회차가 안 먹혔다는 뜻. 반대로,
                # 그리고 절반 폭으로 간다(같은 폭으로 뒤집으면 두 상태를 오간다 — 실측).
                flip = -abs(d) if d > 0 else abs(d)
                plan[i] = (f, int(flip / 2) or flip, why + " (반대 방향으로 절반만)")
            elif prev is not None and (prev > 0) != (d > 0):
                # 방향이 바뀌었다 = 지난 조절이 지나쳤다. 폭을 줄여 수렴시킨다.
                plan[i] = (f, int(d / 2) or d, why + " (지난 회차를 지나쳐 절반만)")
        if not plan:
            codes = sorted({re.match(r"FAIL ([A-Z0-9-]+)", f).group(1)
                            for f in fails if re.match(r"FAIL ([A-Z0-9-]+)", f)})
            die("이 실패는 원고 분량 조절로 고칠 수 없습니다: " + ", ".join(codes) + "\n"
                + "\n".join(fails) + "\n\n"
                "G3(판면 밖 넘침)은 표가 너무 넓거나 긴 코드·URL이 원인입니다 — 그 표의 열을 줄이세요.\n"
                "G14-C(대비)·G2(폰트)는 원고가 아니라 스타일 설정 문제입니다.\n"
                "G10(수치 날조)은 콜아웃의 숫자를 본문에도 넣거나 콜아웃에서 지우세요.")
        def fix_one(item):
            f, delta, why = item
            path = book_dir / "chapters" / f
            text = path.read_text(encoding="utf-8")
            verb = f"약 {delta}자 늘려" if delta > 0 else f"약 {abs(delta)}자 줄여"
            prompt = f"""아래는 한국어 단행본의 한 장이다. 조판 결과 다음 문제가 생겼다.

문제: {why}
할 일: 본문을 {verb}라.

지키기:
- 첫 줄 `# 제목`과 절 구조는 그대로 둔다.
- 늘릴 때는 이미 있는 주장에 예·조건·반례를 덧붙인다. 새 주제를 만들지 않는다.
- 줄일 때는 같은 말을 두 번 하는 문장, 수식어, 곁가지 예를 먼저 지운다.
- 표·콜아웃은 유지한다. 마크다운 원고만 출력한다(설명 금지).

--- 원고 시작 ---
{text}
--- 원고 끝 ---"""
            new = as_chapter(claude(prompt))
            if not new:
                return f"  {f}: 응답에서 원고를 찾지 못해 건너뜀"
            path.write_text(new.rstrip() + "\n", encoding="utf-8")
            history[f] = delta
            return f"  {f}: {len(text)}자 → {len(new)}자 ({why})"

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=3) as ex:  # 순차로 돌리면 회차당 7~10분
            for line in ex.map(fix_one, plan):
                print(line, flush=True)
    die(f"{rounds}회차까지 통과하지 못했습니다. 원고를 직접 손보세요.")



# ── 도해 ──────────────────────────────────────────────────────
# 실제로 통과시켜 본 antv 템플릿만 남긴다. 카탈로그에는 113종이 있지만 좁은 판형에서
# 8pt 하한을 넘기지 못하는 것이 많다(references/diagram-ledger.json).
ANTV_SAFE = """- sequence-steps-simple : 3~4단계 절차. data.sequences = [{label, desc}]. 라벨 6자 이내
- sequence-timeline-simple : 세로 타임라인. data.sequences. 세로로 길어 bf.width는 twothirds 권장
- list-row-simple-horizontal-arrow : 가로 3~4항목. data.sequences
- list-column-simple-vertical-arrow : 세로 3~4항목. data.lists
- compare-binary-horizontal-simple-vs : 두 갈래 대비. data.compares = [{label, children:[{label, desc}]}]"""

AUTHORED_RULES = """직접 그리는 SVG 규칙(어기면 빌드가 거부한다):
- 색은 토큰만 쓴다: {{brand}} {{ink}} {{muted}} {{rule}} {{paper}} — 다른 색값 금지
- <text>로 쓴다. 회전·세로쓰기 금지. 텍스트끼리 겹치면 실패
- font-size는 viewBox 단위로 12 이상, viewBox 폭은 %VBMAX% 이하 (8pt 하한 환산)
- 커넥터는 직각만(가로선+세로선). 대각선 금지. 화살촉은 <path>로 직접 그린다
- 노드 9개·화살표 12개 이내. 넘으면 도해를 나눈다
- 한자(漢字)는 쓰지 않는다. 한글·가나·영문·숫자만
- 외부 링크·이미지·스타일시트 참조 금지, <svg> 하나로 자립"""


def _diagram_plan(book_dir: Path, style: str, limit: int) -> list:
    """어느 장에 어떤 도해가 필요한지 본문을 읽고 정한다."""
    outline = json.loads((book_dir / "outline.json").read_text(encoding="utf-8"))["chapters"]
    digest = []
    for c in outline:
        p = book_dir / "chapters" / c["file"]
        if p.exists():
            digest.append(f"### {c['file']} — {c['title']}\n" + p.read_text(encoding="utf-8")[:1200])
    prompt = f"""아래는 한국어 단행본의 각 장 앞부분이다. 그림(도해)이 실제로 이해를 돕는 자리를
최대 {limit}곳 고른다. JSON만 출력한다.

고르는 기준:
- 순서·절차, 갈래 판단, 구성 요소의 관계처럼 **글로 읽으면 머리에 안 그려지는 것**만 고른다.
- 이미 표로 정리된 내용은 고르지 않는다(표가 더 낫다).
- 한 장에 하나까지. 장식용 그림은 만들지 않는다.

track 선택:
- "antv" : 3~4단계 절차, 가로/세로 항목 나열, 두 갈래 대비
- "authored" : 분기가 있는 흐름도, 역할별 처리 경로(스위밍레인), 구성 요소 연결도

출력:
{{"figs": [{{"file": "ch-02.md", "track": "antv", "title": "도해 제목",
  "what": "무엇을 보여야 하는지 한 문장", "anchor": "이 문장 바로 뒤에 넣어라(본문에서 그대로 복사한 한 문장)"}}]}}

--- 본문 시작 ---
{chr(10).join(digest)[:12000]}
--- 본문 끝 ---"""
    raw = strip_fence(claude(prompt))
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        die("도해 계획 JSON을 찾지 못했습니다:\n" + raw[:300])
    figs = json.loads(m.group(0)).get("figs") or []
    return figs[:limit]


def _make_antv(book_dir: Path, fig: dict, name: str, width: str, retry_note: str = "") -> str:
    prompt = f"""AntV Infographic DSL 사이드카를 만든다. JSON만 출력한다.

도해 제목: {fig['title']}
보여야 할 것: {fig['what']}

쓸 수 있는 템플릿(이 목록 밖은 빌드가 거부한다):
{ANTV_SAFE}

출력 형식:
{{"kind": "antv", "bf": {{"width": "{width}", "icons": false}},
 "dsl": ["infographic <템플릿명>", "data", "  title 제목", "  <데이터키>",
         "    - label 라벨", "      desc 설명", "..."]}}

규칙:
- 항목은 3~4개. 라벨은 6자 이내, desc는 12자 이내(글자가 8pt 밑으로 내려가면 실패한다).
- 들여쓰기는 예시 그대로 2칸/4칸/6칸.
- 본문에 없는 수치를 만들지 않는다.{retry_note}"""
    raw = strip_fence(claude(prompt))
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("사이드카 JSON을 찾지 못함")
    sidecar = json.loads(m.group(0))
    # 세로형 템플릿은 전폭으로 두면 면을 통째로 먹는다(실측: 타임라인 1개가 1면 점유,
    # 캡션이 러닝푸터와 겹침). 폭을 2/3로 줄이면 높이도 같이 줄어든다.
    first = (sidecar.get("dsl") or [""])[0]
    if any(k in first for k in ("timeline", "list-column", "roadmap", "pyramid")):
        sidecar.setdefault("bf", {})["width"] = "twothirds"
    (book_dir / "diagrams" / f"{name}.json").write_text(
        json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")
    return "antv"


def _make_authored(book_dir: Path, fig: dict, name: str, width: str, vbmax: int,
                   retry_note: str = "") -> str:
    prompt = f"""SVG 도해를 직접 그린다. SVG 코드만 출력한다(설명·코드펜스 금지).

도해 제목: {fig['title']}
보여야 할 것: {fig['what']}

{AUTHORED_RULES.replace('%VBMAX%', str(vbmax))}

형태 지침:
- 제목을 맨 위 가운데 <text>로 넣는다(font-size 15 안팎).
- 상자는 <rect rx="6">, 채움은 {{{{paper}}}} 또는 {{{{rule}}}}, 강조 상자만 {{{{brand}}}}(글자는 {{{{paper}}}}).
- 상자 안 설명은 12~13, 제목줄은 14~15.
- 분기가 있으면 "예/아니오" 라벨을 선에서 6단위 이상 띄워 붙인다.
{retry_note}"""
    svg = strip_fence(claude(prompt))
    i = svg.find("<svg")
    if i < 0:
        raise ValueError("SVG를 찾지 못함")
    svg = svg[i:svg.rfind("</svg>") + 6]
    (book_dir / "diagrams" / f"{name}.svg").write_text(svg, encoding="utf-8")
    (book_dir / "diagrams" / f"{name}.json").write_text(
        json.dumps({"kind": "authored", "bf": {"width": width}}, ensure_ascii=False),
        encoding="utf-8")
    return "authored"


def _insert_ref(book_dir: Path, fig: dict, name: str) -> bool:
    """본문에 이미지 참조를 단독 문단으로 끼운다(G0: 텍스트와 섞이면 실패)."""
    p = book_dir / "chapters" / fig["file"]
    if not p.exists():
        return False
    text = p.read_text(encoding="utf-8")
    ref = f'![{fig["title"]}](../assets/{name}.svg "출처: 본문 정리")'
    if ref in text:
        return True
    anchor = (fig.get("anchor") or "").strip()
    if anchor and anchor in text:
        text = text.replace(anchor, anchor + "\n\n" + ref, 1)
    else:
        # 앵커를 못 찾으면 마지막 절 앞에 둔다 — 장 끝(요점 콜아웃)보다는 위여야 한다.
        i = text.rfind("\n## ")
        if i < 0:
            return False
        text = text[:i] + "\n\n" + ref + text[i:]
    p.write_text(text, encoding="utf-8")
    return True


def cmd_diagrams(book_dir: Path, limit: int):
    book, style, _ = load(book_dir)
    if style == "essay":
        print("에세이 스타일은 무이미지가 원칙이라 도해를 넣지 않습니다.")
        return
    if book.get("images") == "none":
        book["images"] = "vector"
        (book_dir / "book.json").write_text(json.dumps(book, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
        print("book.json images: none → vector (도해를 쓰려면 필요)")
    tokens = json.loads((SKILL / "styles" / style / "tokens.json").read_text(encoding="utf-8"))
    dg = tokens.get("diagram") or die(f"{style} 스타일은 도해를 지원하지 않습니다")
    (book_dir / "diagrams").mkdir(exist_ok=True)
    plan = _diagram_plan(book_dir, style, limit)
    if not plan:
        print("도해가 필요한 자리를 찾지 못했습니다.")
        return
    used = len(list((book_dir / "diagrams").glob("fig-*.json")))
    made = []
    for k, fig in enumerate(plan, 1):
        name = f"fig-{used + k:02d}"
        width = "full"
        mm = dg["widths"]["twothirds" if width == "twothirds" else "full"]
        vbmax = int(mm * 2.835 * 12 / 8)  # font-size 12 기준 viewBox 폭 상한
        for attempt in (1, 2):
            try:
                note = "" if attempt == 1 else f"\n지난 시도가 이 이유로 거부됐다: {err}\n항목 수를 줄이고 라벨을 더 짧게 하라."
                if fig.get("track") == "antv":
                    _make_antv(book_dir, fig, name, width, note)
                else:
                    _make_authored(book_dir, fig, name, width, vbmax, note)
            except ValueError as e:
                print(f"  {name}: {e}")
                break
            r = subprocess.run(["node", str(SKILL / "scripts/render_diagrams.mjs"),
                                str(book_dir), "--style", style],
                               capture_output=True, text=True, timeout=900,
                               env={**os.environ, "NODE_PATH": subprocess.run(
                                   ["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()})
            if r.returncode == 0:
                if _insert_ref(book_dir, fig, name):
                    made.append(f"{name} ({fig['file']}, {fig.get('track')}) — {fig['title']}")
                break
            err = (r.stderr or r.stdout).strip().splitlines()[-1][:300]
            print(f"  {name}: 렌더 거부 — {err}")
            if attempt == 2:  # 두 번 실패하면 흔적을 지운다 (빌드를 막지 않도록)
                for ext in (".json", ".svg"):
                    (book_dir / "diagrams" / f"{name}{ext}").unlink(missing_ok=True)
    print(f"OK diagrams: {len(made)}개" + ("\n  " + "\n  ".join(made) if made else ""))


def cmd_auto(book_dir: Path, rounds: int, web: bool = False,
             max_queries: int = 6, today: str = "", figs: int = 0):
    """주제만 있는 상태에서 통과본까지 — 조사 → 목차 → 집필 → (빌드·검사·수정) 반복."""
    rp = book_dir / "research.md"
    if not rp.exists() or len(rp.read_text(encoding="utf-8").strip()) < 40:
        print("[1/4] 조사 노트 작성")
        cmd_research(book_dir, None, web, max_queries, today)
    else:
        print("[1/4] 자료가 이미 있어 조사는 건너뜁니다")
    if _outline_is_stub(book_dir):
        print("[2/4] 목차 설계")
        cmd_outline(book_dir)
    else:
        print("[2/4] 목차가 이미 있어 건너뜁니다")
    print("[3/4] 장별 집필")
    outline = json.loads((book_dir / "outline.json").read_text(encoding="utf-8"))["chapters"]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(lambda c: cmd_chapter(book_dir, c["file"]), outline))
    if figs:
        print("[4/5] 도해 생성")
        cmd_diagrams(book_dir, figs)
    print("[5/5] 빌드·검사·수정 반복")
    cmd_fix(book_dir, rounds)


def demo():
    """프롬프트 조립·응답 처리 자체 점검 (claude 호출 없음)."""
    assert strip_fence("```md\n# 제목\n본문\n```") == "# 제목\n본문"
    assert strip_fence("# 제목\n본문") == "# 제목\n본문"
    assert set(BRIEF) == {"practical", "insight", "academic", "essay", "business", "magazine"}
    for style, (brief, rng) in BRIEF.items():
        assert brief and rng[0] < rng[1], style
    assert "지어내면" in CONTRACT and "코드펜스" in CONTRACT
    starts = [(4, "ch-01.md"), (7, "ch-02.md"), (11, "ch-03.md")]
    assert _chapter_of(4, starts) == "ch-01.md"
    assert _chapter_of(6, starts) == "ch-01.md"
    assert _chapter_of(11, starts) == "ch-03.md"
    assert _chapter_of(3, starts) is None
    assert as_chapter("네, 원고입니다.\n\n# 제목\n본문") == "# 제목\n본문"
    assert as_chapter("```md\n# 제목\n본문\n```") == "# 제목\n본문"
    assert as_chapter("제목이 없는 응답") is None
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp); (d / "chapters").mkdir()
        ch = d / "chapters" / "ch-01.md"
        ch.write_text("# 제목\n\n앵커 문장이다.\n\n## 절1\n\n본문\n\n## 요점\n\n끝\n")
        assert _insert_ref(d, {"file": "ch-01.md", "title": "그림", "anchor": "앵커 문장이다."}, "fig-01")
        body = ch.read_text()
        assert "앵커 문장이다.\n\n![그림](../assets/fig-01.svg" in body, body
        assert _insert_ref(d, {"file": "ch-01.md", "title": "둘", "anchor": "없는 문장"}, "fig-02")
        body = ch.read_text()
        assert body.index("![둘]") < body.index("## 요점"), "마지막 절 앞에 들어가야 한다"
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "outline.json").write_text(json.dumps({"chapters": [{"title": "1장 제목"}]}))
        assert _outline_is_stub(d), "자리표시자 목차를 실제 목차로 봤다"
        (d / "outline.json").write_text(json.dumps({"chapters": [{"title": "빛부터 바꾼다"}]}))
        assert not _outline_is_stub(d)
    print("demo ok")


def main():
    global MODEL
    ap = argparse.ArgumentParser(description="목차·원고를 claude CLI에게 맡긴다")
    ap.add_argument("task", choices=["research", "outline", "chapter", "all", "diagrams", "fix", "auto", "selfcheck"])
    ap.add_argument("book_dir", nargs="?")
    ap.add_argument("target", nargs="?")
    ap.add_argument("--topic")
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--model", default=MODEL, help="claude 모델 (기본 sonnet)")
    ap.add_argument("--web", action="store_true", help="조사 단계에서 웹 검색으로 사실 확인")
    ap.add_argument("--max-queries", type=int, default=6, help="웹 검색 최대 횟수(=질문 수)")
    ap.add_argument("--today", default="", help="확인일로 기록할 날짜 (YYYY-MM-DD)")
    ap.add_argument("--figs", type=int, default=3, help="자동 생성할 도해 최대 개수")
    if "--selfcheck" in sys.argv[1:]:   # 다른 스크립트와 같은 형태도 받는다
        return demo()
    a = ap.parse_args()
    MODEL = a.model
    if a.task == "selfcheck":
        return demo()
    if not a.book_dir:
        ap.error("book_dir가 필요합니다")
    d = Path(a.book_dir).resolve()
    if not (d / "book.json").exists():
        die(f"책 폴더가 아닙니다: {d}")
    (d / "chapters").mkdir(exist_ok=True)
    if a.task == "research":
        cmd_research(d, a.topic, a.web, a.max_queries, a.today)
    elif a.task == "outline":
        cmd_outline(d)
    elif a.task == "auto":
        cmd_auto(d, a.rounds, a.web, a.max_queries, a.today, a.figs)
    elif a.task == "diagrams":
        cmd_diagrams(d, a.figs)
    elif a.task == "fix":
        cmd_fix(d, a.rounds)
    elif a.task == "chapter":
        if not a.target:
            ap.error("chapter 작업에는 파일명이 필요합니다 (예: ch-01.md)")
        cmd_chapter(d, a.target)
    else:
        cmd_all(d)


if __name__ == "__main__":
    main()
