# bookforge — 웹 UI 포크

주제 한 줄로 상업도서급 한국어 전자책 PDF를 만드는 도구입니다.
원본 [gongnyang/bookforge](https://github.com/gongnyang/bookforge)는 Claude Code·Codex에서 쓰는 **에이전트 스킬**입니다.
이 포크는 거기에 **브라우저에서 쓰는 작업창**과 **자동 집필**을 붙였습니다.

원본의 설계 문서(스타일 팩 6종, 배치 규칙서, 품질 게이트 16종)는 [README.upstream.md](README.upstream.md)에 그대로 있습니다.

```
주제 한 줄  →  조사  →  목차  →  집필  →  도해  →  빌드·검사  →  통과본 PDF
```

## 이 포크가 더한 것

| | 원본 | 이 포크 |
|---|---|---|
| 조작 | 에이전트에게 말로 지시 | + **웹 UI** (6단계 흐름) |
| 집필 | 에이전트가 대화 안에서 | + **`claude -p` 호출로 자동화** (조사·목차·집필·도해) |
| 게이트 실패 | 사람이 원고를 조절 | + **자동 수정 반복** (빌드→검사→분량 조절) |
| 폰트 | 동봉 5종 고정 | + **컴퓨터에 깔린 폰트를 언어별로 지정** |
| 도해 | 사람이 사이드카 작성 | + **본문을 읽고 자동 생성** |

### 수리한 원본 버그

작업하면서 실물 책 8권을 만들며 잡은 것들입니다.

- 인라인 코드 뒤에 괄호가 오면 빌드가 죽던 문제 (`` `a.ts`(또는 `b.ts`) `` — 한국어 문장에서 흔함)
- 코드 하이라이트 색이 대비 기준(G14-C)을 못 넘어 코드가 든 책이 통과 불가였던 문제
- 표지 제목이 길면 판면을 넘치던 문제, 부제가 없는데 빈 리본이 그려지던 문제
- 판권면이 실제 서체가 아니라 기본값을 찍던 문제
- 목차 쪽번호 검사가 앞 10자만 보고 다른 항목에 매칭되던 문제
- 매거진 스타일에서 목차 쪽번호가 전부 어긋나던 문제
- 도해 글자를 **재는 서체와 그리는 서체가 달라** 폭 계산이 틀리던 문제
- AntV 도해가 스타일 팔레트 밖 색을 그대로 내보내던 문제
- 일본어 한자가 시스템 폰트로 새어 Type3 글리프를 만들던 문제

## 필요한 것

macOS 기준입니다.

| | 용도 | 없으면 |
|---|---|---|
| Python 3.11+ | 변환·품질 검사 | 필수 |
| Typst 0.14+ | 실용·학술·에세이·비즈니스 조판 | 그 4종 못 씀 |
| Node + Playwright(Chromium) | 리포트·매거진 조판, 도해 | 그 2종·도해 못 씀 |
| Claude Code (`claude`) | 자동 조사·목차·집필·도해 | 자동화만 못 씀 (직접 쓰면 됩니다) |

```bash
git clone https://github.com/flutterkage2k/bookforge.git
cd bookforge

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

brew install typst                      # 선택: Typst 스타일 4종
npm i -g playwright && npx playwright install chromium   # 선택: HTML 스타일·도해
```

## 웹 UI

```bash
.venv/bin/python scripts/webui.py books --port 8765
```

브라우저에서 http://127.0.0.1:8765 를 엽니다. 끄려면 그 터미널에서 `Ctrl+C`.

화면이 여섯 단계로 되어 있고, **끝난 단계에는 체크가 붙습니다**(파일 상태에서 계산한 것이라 가짜 진행률이 아닙니다).

1. **책 만들기** — 제목·저자·분량, 스타일 6종을 표지·본문 견본을 보고 선택
2. **자료** — 조사한 내용을 붙여넣습니다. 「AI에게 조사 맡기기」를 누르면 대신 조사합니다
3. **목차** — 장 제목·요약 입력, 또는 「AI에게 목차 맡기기」
4. **집필** — 장별 편집, 또는 「AI에게 전체 집필 맡기기」·「AI에게 도해 넣기」
5. **빌드·검사** — 빌드 → 게이트 → 지면 이미지. 실패하면 **한국어로** 원인과 할 일을 표로 보여줍니다
6. **검수** — 전 지면을 눈으로 확인. 지면을 클릭하면 화면 높이에 맞춰 크게 보이고, 각 쪽 아래 버튼이 **그 쪽을 만든 원고**로 데려갑니다

어느 단계에서든 **「주제만 주고 전부 맡기기」** 버튼 하나로 조사부터 통과본까지 갑니다(7장 기준 15~25분).

## 명령줄

웹 UI 없이 쓸 수도 있습니다.

```bash
# 책 만들기 (한국어로 지정합니다)
python3 scripts/scaffold.py books/mybook --style 실용 --title "제목" --length 짧게

# 자동
python3 scripts/agent.py auto books/mybook              # 조사→목차→집필→도해→통과까지
python3 scripts/agent.py research books/mybook --web    # 웹 검색으로 사실 확인
python3 scripts/agent.py outline  books/mybook
python3 scripts/agent.py chapter  books/mybook ch-03.md
python3 scripts/agent.py diagrams books/mybook --figs 3
python3 scripts/agent.py fix      books/mybook          # 게이트 통과까지 반복

# 수동
python3 scripts/build.py   books/mybook     # → draft/book.pdf
python3 scripts/qc_gate.py books/mybook     # 통과 시에만 → final/책이름.pdf
python3 scripts/contact_sheet.py books/mybook/final/*.pdf books/mybook/qc

# 폰트
python3 scripts/fontpick.py list --lang ja
python3 scripts/fontpick.py set books/mybook --ko "Gmarket Sans" --ja "LINE Seed JP_TTF"
```

스타일 이름은 한국어로 씁니다: `실용` `리포트` `학술` `에세이` `비즈니스` `매거진`.

## 웹 검색 조사 — 예산을 묶어 둡니다

`--web`을 켜면 무작정 검색하지 않습니다.

1. 검색 없이, **시간이 지나면 변하는 사실**만 골라 질문을 최대 N개 만듭니다(가격·한도·버전·정책·통계·날짜).
2. 질문 하나당 검색 **한 번**. 검색 횟수는 질문 수를 넘지 않습니다.
3. 사실마다 출처 URL과 확인일을 답니다. 확정 못 한 것은 「확인 필요」로 남깁니다.

개념·원리·역사는 검색하지 않습니다 — 변하지 않고, 모델 지식으로 충분합니다.

## 주의할 것

**폰트 라이선스.** PDF에는 쓴 서체가 파일로 박혀 나갑니다. 개인 열람은 괜찮아도 **판매·인쇄물 배포에는 별도 라이선스가 필요한 서체가 많습니다.** 동봉 서체(Pretendard·Noto Serif KR·Paperlogy·Gmarket Sans·Barlow)는 OFL이라 상업 배포도 가능합니다. 직접 고른 서체는 본인이 확인해야 합니다. 실제로 쓴 서체는 판권면에 기록됩니다.

**AI가 쓴 내용은 검증이 필요합니다.** 자료에 없는 수치를 쓰지 않도록 시켰고 게이트(G10)가 콜아웃 수치를 본문과 대조하지만, 그것으로 사실 검증이 끝나지는 않습니다. 2단계에 확인된 자료를 직접 넣을수록 결과가 정확해집니다.

**서버는 이 컴퓨터 전용입니다.** 127.0.0.1에만 열리고, 다른 출처의 요청(Origin·Host 불일치)은 403으로 막습니다. 인증이 없으므로 포트를 외부에 노출하지 마세요.

**자동 집필은 되돌리기가 없습니다.** 「전체 집필 맡기기」는 기존 원고를 갈아엎습니다(확인은 묻습니다). 손으로 다듬은 원고가 있으면 `chapters/` 폴더를 먼저 복사해 두세요.

## 라이선스·출처

원본과 같은 MIT입니다. 동봉 폰트는 각 폰트의 OFL 1.1 ([고지](assets/fonts/LICENSES.md)).
원본: [gongnyang/bookforge](https://github.com/gongnyang/bookforge) — 스타일 팩·배치 규칙서·품질 게이트 설계는 전부 원본의 것입니다.
