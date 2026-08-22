# bookforge

**주제 한 줄 → 상업도서급 전자책 PDF.** Claude Code와 OpenAI Codex 양쪽에서 동작하는 에이전트 스킬입니다.

[English](README.en.md)

표지·리더선 목차·장 도비라·러닝 헤드·판권면까지 실제 단행본의 해부 구조를 갖춘 PDF를 만듭니다. 콘텐츠는 마크다운으로만 쓰고, 조판은 6개 스타일 팩과 스크립트가 전담하며, 품질은 QC 게이트가 물리적으로 강제합니다 — 게이트를 통과하지 못한 PDF는 `final/`에 존재할 수 없습니다. 페이지를 어떻게 나누고, 채우고, 비우는지는 상업 단행본 실측에 기반한 배치 규칙서([references/pagination.md](references/pagination.md))가 정하며, 밀도 게이트가 "이유 없는 비움"과 "억지 채움"을 수치로 잡아냅니다.

**v2.0.0**: 본문 요점 시각화와 시퀀스·상태머신·ER·스위밍레인 같은 기술도해를 에이전트가 직접 벡터로 짜 넣는 도해 트랙이 새로 생겼고, 목차·도비라·본문 대비까지 자기일관성을 검사하는 게이트가 늘었으며, 동봉 폰트가 전량 TrueType으로 바뀌어 Chromium 렌더에서 Type3 폴백이 0건이 됐습니다. 아래에서 순서대로 다룹니다.

*데모 영상은 v2.0.0 GitHub Release 첨부 자산으로 게시됩니다 — 릴리스 발행 후 이 자리에 임베드됩니다.*

## 예시 9종 — 전부 이 스킬이 만든 실물입니다

여섯 스타일 중 `practical`·`insight`·`business` 세 스타일은 도해 트랙이 주인공인 신작을 하나씩 더해 총 아홉 권입니다. 각 표지를 클릭하면 PDF 전문이 열립니다.

| | | |
|:---:|:---:|:---:|
| [![practical](examples/showcase/practical-prompt-patterns-cover.png)](examples/practical-prompt-patterns.pdf) | [![insight](examples/showcase/insight-ondevice-ai-cover.png)](examples/insight-ondevice-ai.pdf) | [![academic](examples/showcase/academic-game-theory-cover.png)](examples/academic-game-theory.pdf) |
| **practical** 실용·활용서<br>『바로 쓰는 프롬프트 패턴 24』 45쪽 | **insight** 기술 리포트<br>『온디바이스 AI 2026』 28쪽 | **academic** 학술·논문형<br>『게임이론의 기초』 36쪽 |
| [![essay](examples/showcase/essay-evening-sentences-cover.png)](examples/essay-evening-sentences.pdf) | [![business](examples/showcase/business-sme-ai-cover.png)](examples/business-sme-ai.pdf) | [![magazine](examples/showcase/magazine-trend-brief-cover.png)](examples/magazine-trend-brief.pdf) |
| **essay** 미니멀 에세이<br>『퇴근길의 문장들』 32쪽 | **business** 컨설팅 백서<br>『중소기업 AI 도입 전략』 28쪽 | **magazine** 트렌드 매거진<br>『TREND BRIEF』 25쪽 |
| [![insight](examples/showcase/insight-agent-protocols-cover.png)](examples/insight-agent-protocols.pdf) | [![practical](examples/showcase/practical-home-server-cover.png)](examples/practical-home-server.pdf) | [![business](examples/showcase/business-automation-redesign-cover.png)](examples/business-automation-redesign.pdf) |
| **insight** 도해 중심<br>『AI 에이전트 프로토콜 2026』 32쪽 | **practical** 도해 중심<br>『나만의 홈 서버』 39쪽 | **business** 도해 중심<br>『업무 자동화 재설계』 31쪽 |

## 도해 트랙 — v2의 주인공

본문 도해는 에이전트가 사이드카 파일로 선언하고, 빌드가 정규화·검증까지 마쳐 벡터로 얹습니다. 두 트랙으로 나뉩니다.

1. **antv** — 순서·비교·계층·수치 추이 같은 요점 시각화는 `diagrams/fig-NN.json`에 AntV Infographic DSL로 선언합니다. 렌더러는 저장소에 커밋된 벤더 번들(`vendor/antv-ssr.bundle.mjs`, `@antv/infographic` 0.2.19 고정)로 SSR하고, 원본 출력의 `<foreignObject>` 텍스트를 네이티브 `<text>`로 변환(fo2text)해 Typst(usvg)에서 텍스트가 조용히 사라지는 사고를 막습니다.
2. **authored** — AntV 카탈로그가 커버하지 못하는 기술도해 11계열(시퀀스·상태머신·ER·스위밍레인·간트·레이더·벤·산점도·조직도·루프·권한 매트릭스)은 에이전트가 SVG를 직접 그립니다. `diagrams/fig-NN.svg` + 사이드카 `{"kind":"authored"}`를 두면 빌드가 폰트 베이크·팔레트 강제·라벨 겹침 검사·최소 8pt 하한까지 정규화해 `assets/fig-NN.svg`로 산출합니다. 커넥터 규칙·복잡도 예산·타입 라우팅은 [cathrynlavery/diagram-design](https://github.com/cathrynlavery/diagram-design)(MIT)의 명세를 한국어 조판·Pretendard·팔레트 토큰·게이트 체계에 맞게 재서술해 흡수한 [references/diagrams.md](references/diagrams.md)가 정본입니다(템플릿·코드는 가져오지 않음 — 한글 미지원·판형 하한 충돌 실측).

두 트랙 모두 렌더 전 G0(SVG 소스 검사)·렌더 후 G13(도해 라벨이 PDF 실텍스트로 존재하는지)으로 물리 검증됩니다. 아래는 실제 예시 3권에서 뽑은 authored SVG입니다.

| insight — 계층(트리) | business — 스위밍레인 | practical — 플로우차트 |
|:---:|:---:|:---:|
| ![](examples/showcase/insight-agent-protocols-page6.png) | ![](examples/showcase/business-automation-redesign-page9.png) | ![](examples/showcase/practical-home-server-page12.png) |

### 목차 정합(G14)도 같은 세대 작업입니다

목차 쪽번호가 실제 폴리오와 어긋나거나, 목차 색이 장 도비라와 다른 계열이면 "다른 책 같은 목차"가 됩니다. G14가 이 자기일관성과 텍스트 대비 하한을 전 면 스캔으로 잡습니다 — 아래 두 권의 목차가 실제 통과본입니다.

| insight — 사이드 밴드·폴리오 | business — 인디케이터·챕터 넘버 |
|:---:|:---:|
| ![](examples/showcase/insight-agent-protocols-toc.png) | ![](examples/showcase/business-automation-redesign-toc.png) |

## 내지 미리보기

| practical — 콜아웃·절차 지면 | business — 표·데이터 근거 | magazine — 이미지·풀퀘트 면 |
|:---:|:---:|:---:|
| ![](examples/showcase/practical-prompt-patterns-page9.png) | ![](examples/showcase/business-sme-ai-page9.png) | ![](examples/showcase/magazine-trend-brief-page6.png) |

| academic — 정의 박스·절 위계 | essay — 여백 낙차형 지면 | insight — narrow 측정 표 |
|:---:|:---:|:---:|
| ![](examples/showcase/academic-game-theory-page11.png) | ![](examples/showcase/essay-evening-sentences-page6.png) | ![](examples/showcase/insight-ondevice-ai-page10.png) |

## 스타일 6종

각 스타일은 실제 상업 출판물을 계측·증류한 규칙서(`styles/*/STYLE.md`)를 갖습니다 — 판형 mm, 폰트 pt, 행간 %, 컬러 토큰, 지면 템플릿, 금지 사항까지.

| 스타일 | 정체성 | 판형 | 엔진 |
|---|---|---|---|
| `practical` | IT·실용 활용서. 서술은 명조(Noto Serif KR)로 낮게 깔고 조작·라벨·수치는 고딕(Pretendard)으로 세워 "읽는 글"과 "하는 글"을 서체로 분리한다 | 153×225 | Typst |
| `insight` | 기술 동향 리포트 (연구기관 인사이트) | 182×257 | HTML→Chromium |
| `academic` | 학술 단행본 (신국판·3선표·절 번호 위계) | 153×225 | Typst |
| `essay` | 미니멀 에세이 (사륙판·먹 1도+포인트 1색) | 128×188 | Typst |
| `business` | 컨설팅 백서 (navy 시스템·액션 타이틀·키 스탯) | 200×280 | Typst |
| `magazine` | 트렌드 매거진 (에디토리얼 그리드·풀퀘트 면) | 200×265 | HTML→Chromium |

## 설치

```bash
git clone https://github.com/gongnyang/bookforge.git
cd bookforge

# Claude Code + Codex 양쪽에 심링크 (둘 다 심링크 공식 지원)
ln -sfn "$PWD" ~/.claude/skills/bookforge
ln -sfn "$PWD" ~/.codex/skills/bookforge
ln -sfn "$PWD" ~/.agents/skills/bookforge
```

요구 사항 (스킬이 실행 전 자체 점검):

- **Typst 0.14+** — `practical`·`academic`·`essay`·`business`
- **Python 3 + PyMuPDF + markdown-it-py** — 변환·QC 게이트 (`pip install pymupdf markdown-it-py`)
- **전역 Playwright(Chromium)** — `insight`·`magazine` **그리고 도해(diagrams/)를 쓰는 모든 책**(도해 프리렌더는 Typst 스타일에서도 Chromium 하네스를 거친다) — `npm i -g playwright && npx playwright install chromium`. 빌드는 **전역** `npm root -g`에서 playwright를 해석하므로 프로젝트 로컬 설치로는 안 잡힌다
- **도해(diagrams/)를 쓰는 책만** — 렌더러는 저장소에 커밋된 벤더 번들(`vendor/antv-ssr.bundle.mjs`, `@antv/infographic` 0.2.19 고정)을 쓴다. **`npm ci`는 불필요** — npm 레지스트리가 사라져도 재현된다. 번들이 유실됐을 때만 스킬 폴더에서 `npm ci && node vendor/build-bundle.mjs`로 복구

폰트는 OFL 5종(Pretendard·Noto Serif KR·Paperlogy·Gmarket Sans·Barlow)이 **전량 TrueType(TTF)**으로 레포에 동봉되어 바로 렌더됩니다 — Chromium print-to-PDF는 CFF(.otf) 서브셋을 못 해 페이지마다 글리프를 벡터로 다시 그리는 Type3로 조용히 폴백한다(실측: 동일 본문 기준 OTF는 Type3 오브젝트 19개, 변환한 TTF는 Type0 서브셋 1개·Type3 0개). G2 게이트가 이 Type3 0건을 하드 조건으로 강제한다 — [라이선스 고지](assets/fonts/LICENSES.md).

## 사용법

에이전트에게 말하면 됩니다:

```
"온디바이스 AI 동향을 insight 스타일 전자책으로 만들어줘"     ← topic 모드: 조사→목차→집필→조판
"이 원고(draft.docx)를 에세이집 PDF로 조판해줘"               ← manuscript 모드: 인제스트→조판
```

스킬이 모드를 감지하고 스타일·분량을 정해 끝까지 진행합니다. 도해가 필요한 장은 `diagrams/fig-NN.json`(antv) 또는 `diagrams/fig-NN.svg`(authored)을 두면 빌드 단계에서 자동으로 프리렌더됩니다. 수동 실행도 가능합니다:

```bash
python3 scripts/scaffold.py mybook --style essay --title "제목" --length short
# chapters/*.md 와 outline.json 작성 후
python3 scripts/build.py mybook        # → draft/book.pdf (도해가 있으면 여기서 자동 프리렌더)
python3 scripts/qc_gate.py mybook      # 게이트 통과 시에만 → final/mybook.pdf
```

## 품질 게이트

`final/`은 게이트 스크립트만이 만들 수 있습니다:

| 게이트 | 검사 |
|---|---|
| G0 | (렌더 전) 도해 SVG 소스 — `foreignObject` 잔존·텍스트 부재·외부 참조·단독 문단 위반·사이드카 무결성·아이콘 탈락 차단 |
| G1 | 렌더 성공 + 판형(`tokens.trim_mm`) 대조 + 분량 프리셋 범위(WARN — `--strict-pages`만 HARD) |
| G2 | 폰트 전량 임베드 + **Type3 글리프 0** |
| G3 | 본문 bbox 오버플로 0 (허용오차 1.5pt) |
| G4 | 목차·북마크 ↔ 실제 장 시작 쪽 정합 |
| G6 | 콘택트시트 시각 검수 — 에이전트가 실물 페이지를 눈으로 확인 |
| G7 | 밀도 — 판면 드리프트·의도치 않은 빈 페이지·꼬리 미달·중간 공백 (reach/ink/gap) |
| G8 | 공기 채움(행간·자간을 늘려 억지로 채운 흔적) 탐지 |
| G9 | 면 끝 제목 고립·widow (단일단 스타일) |
| G10 | (렌더 전) 콜아웃·인용·스탯 수치가 챕터 본문에 실재 — 날조 차단 |
| G11 | `pageroles.json`(의도된 여백 사유 코드) 무결성 |
| G12 | 장 시작 직전 필러 백면 0 (단면 전자책에 인쇄 관습의 recto 맞춤 금지) |
| G13 | (렌더 후) 도해 라벨이 PDF 실텍스트로 존재 — SVG→PDF 변환 중 텍스트 드롭 최종 포착 |
| G14 | 목차·디자인 정합 — A 인쇄 목차 쪽번호↔실제 폴리오 자기일관 / B 목차↔장 도비라 색상(hue) 계열 정합 / C 유채색 텍스트 배경 대비 WCAG 하한(대형 3:1, 그 외 4.5:1) |
| G15 | 지면 리듬 (`business` 스타일 한정, 실측 근거 있는 곳만 강제) — 단락 8행 초과 차단 / 시각 요소 없는 연속 본문 면 상한 |

기준 수치와 대응법은 [references/pagination.md](references/pagination.md)가, 도해 트랙의 작성 계약은 [references/diagrams.md](references/diagrams.md)가 정본이다.

## 구조

```
SKILL.md            라우터 (모드 감지 → 파이프라인 → 서브 문서 포인터)
modes/              topic.md · manuscript.md
styles/<6종>/       STYLE.md(규칙서) + theme.typ|theme.css + tokens.json
templates/base.typ  Typst 공통 북 프리미티브
vendor/             antv-ssr.bundle.mjs(커밋된 AntV SSR 번들 — 오프라인 재현성) + build-bundle.mjs
scripts/            scaffold · build · qc_gate · tocgate(G14) · contact_sheet · convert_fonts(TTF 전환) · fetch_fonts · ingest_docx
references/         생성 아트 정책 · 배치 규칙서(pagination.md) · 도해 계약(diagrams.md) · 오케스트레이션 · 스타일 팩 확장 가이드
examples/           예시 9권 PDF + 쇼케이스 36컷
```

생성 이미지 정책: 표지·본문 아트는 **무텍스트 생성 이미지**만 사용하고, 모든 글자는 조판 레이어가 벡터로 얹습니다. 생성 이미지가 실린 책은 캡션·판권면에 표기합니다.

## 라이선스

코드·문서: MIT. 동봉 폰트: 각 폰트의 OFL 1.1 ([고지](assets/fonts/LICENSES.md)). 예시 PDF 9종은 스킬 데모 산출물입니다.
