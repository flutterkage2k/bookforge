#!/usr/bin/env python3
"""게이트 코드 한 곳 정리 — 이게 누구 문제이고, 자동 수정 대상인지.

실패했을 때 사용자가 막다른 길에 서지 않게 하려면 세 가지를 알려줘야 한다.
  1. 무엇을 봤는가
  2. 누구 문제인가 (내 원고 / 스타일 설정 / 도구 결함)
  3. 자동 수정이 손댈 수 있는 코드인가

3번이 중요하다. 「AI에게 게이트 통과까지 맡기기」가 손대지 못하는 코드인데
계속 누르고 있으면 영원히 안 끝난다 — 실제로 그런 일이 있었다(G15-PARA).

webui.py와 agent.py가 같은 표를 본다. 한쪽만 고치면 화면과 실행이 어긋난다.
"""

# 책임 구분
MANUSCRIPT = "원고"   # 사용자가 고칠 수 있다 (분량·문단·수치)
STYLE = "스타일"      # 스타일 설정 문제 — 원고를 아무리 고쳐도 안 없어진다
TOOL = "도구"         # 이 도구의 결함 — 사용자가 할 수 있는 일이 없다

# code -> (무엇을 봤는가, 할 일, 책임, 자동수정 가능)
GATES = {
    "G0":  ("도해가 단독 문단인지 · SVG 원본 검사",
            "이미지 줄 앞뒤에 빈 줄을 넣어 단독 문단으로 두세요. 같은 문단에 글이 섞이면 도해가 사라집니다.",
            MANUSCRIPT, False),
    "G1":  ("렌더 성공·판형·분량", "쪽수가 범위를 벗어나면 경고만 납니다. 원고를 늘리거나 줄이세요.", MANUSCRIPT, False),
    "G2":  ("폰트 임베드·Type3 0건", "otf 폰트가 원인입니다. 폰트 설정에서 ttf 계열로 바꾸세요.", STYLE, False),
    "G3":  ("글자가 판면 밖으로 나갔는지", "표의 열이 많거나 긴 URL·코드가 원인입니다. 그 표를 줄이세요.", MANUSCRIPT, False),
    "G4":  ("목차·북마크가 실제 쪽과 맞는지", "빌드를 다시 하세요. 계속 어긋나면 도구 결함입니다.", TOOL, False),
    "G7-TAIL":  ("장 마지막 면이 너무 비었는지", "그 장 본문을 3~5줄 단위로 늘리거나 줄이세요.", MANUSCRIPT, True),
    "G7-MID":   ("장 중간 면이 비었는지", "표·도해가 다음 면으로 밀려 생긴 구멍입니다. 앞 문단을 조절하세요.", MANUSCRIPT, True),
    "G7-DOC":   ("책 전체 꼬리 면 평균", "여러 장의 끝 면이 얕습니다. 장별 분량을 다시 설계하세요.", MANUSCRIPT, True),
    "G7-FRAME": ("판면 좌표 드리프트", "본문 첫 요소가 이미지면 문단을 먼저 두세요.", MANUSCRIPT, False),
    "G7-BLANK": ("의도치 않은 빈 면", "빈 면을 만든 블록을 앞뒤로 옮기세요.", MANUSCRIPT, False),
    "G8":  ("여백으로 억지로 채웠는지", "짧은 불릿·잦은 소제목이 원인입니다. 문장으로 합치거나 절을 병합하세요.", MANUSCRIPT, False),
    "G8-STRETCH": ("행송을 늘려 채웠는지", "같은 원인입니다. 짧은 블록을 합치세요.", MANUSCRIPT, False),
    "G9":  ("면 끝 제목 고립·widow", "제목이 면 끝에 홀로 남았습니다. 앞 문단을 늘려 밀어내세요.", MANUSCRIPT, False),
    "G9-KEEP": ("제목-본문 결속", "제목과 첫 문단이 갈라졌습니다. 앞 문단을 조절하세요.", MANUSCRIPT, False),
    # pull 인용 어긋남은 자동 수정이 손댈 수 있고(본문 문장으로 교체), 수치 날조는
    # 어느 쪽을 살릴지 사람이 정해야 한다. 한 코드 안에 두 성격이 섞여 있어
    # 자동수정 '가능'으로 표시하되 안내에 두 경우를 나눠 적는다.
    "G10": ("콜아웃 인용·수치가 본문에 실재하는지",
            "풀퀘트는 본문 문장을 그대로 복사해야 합니다(맡기기가 고칩니다). "
            "박스에만 있는 숫자는 본문에도 쓰거나 박스에서 지우세요(직접).",
            MANUSCRIPT, True),
    "G11": ("여백 사유 코드 무결성", "pageroles.json 선언과 실제 지면이 다릅니다.", TOOL, False),
    "G12": ("장 앞 빈 면", "인쇄용 백면은 전자책에서 금지입니다.", TOOL, False),
    "G13": ("도해 글자가 PDF에 실재하는지", "도해 변환에서 글자가 빠졌습니다. 빌드를 다시 하세요.", TOOL, False),
    "G14-A": ("목차 쪽번호 ↔ 실제 폴리오", "빌드를 다시 하세요. 계속 어긋나면 도구 결함입니다.", TOOL, False),
    "G14-B": ("목차 색 ↔ 장 도비라 색", "스타일 색 설정을 확인하세요.", STYLE, False),
    "G14-C": ("글자 대비(WCAG 4.5)", "배경 위 글자색이 너무 옅습니다. 원고로는 못 고칩니다.", STYLE, False),
    "G15-PARA":   ("문단 길이 상한", "한 문단이 깁니다. 8행 이내로 끊으세요.", MANUSCRIPT, True),
    "G15-RHYTHM": ("시각 요소 없는 연속 면", "표·도해·콜아웃을 3면마다 하나씩 넣으세요.", MANUSCRIPT, False),
}


def lookup(code: str):
    """정확히 일치하는 코드 → 없으면 접두(G14-Z → G14) → 그래도 없으면 도구 결함으로 본다.

    모르는 코드가 나왔다는 것 자체가 이 표가 낡았다는 뜻이므로 사용자 탓으로 돌리지 않는다.
    """
    if code in GATES:
        return GATES[code]
    head = code.split("-")[0]
    if head in GATES:
        return GATES[head]
    return (code, "이 도구가 모르는 코드입니다. 실패 정보를 저장해 개발자에게 전달하세요.", TOOL, False)


def autofixable(code: str) -> bool:
    return lookup(code)[3]


def owner(code: str) -> str:
    return lookup(code)[2]


AUTOFIX_CODES = sorted(c for c, v in GATES.items() if v[3])


if __name__ == "__main__":  # 자가 점검
    assert owner("G15-PARA") == MANUSCRIPT and autofixable("G15-PARA")
    assert owner("G14-C") == STYLE and not autofixable("G14-C")
    assert owner("G0") == MANUSCRIPT
    assert lookup("G14-Z")[2] == GATES["G14-A"][2]      # 접두 폴백
    assert owner("G4") == TOOL
    assert lookup("G99-NEW")[2] == TOOL                  # 모르는 코드는 도구 탓
    assert AUTOFIX_CODES == ["G10", "G15-PARA", "G7-DOC", "G7-MID", "G7-TAIL"]
    print("gatehelp OK — 자동 수정 가능:", ", ".join(AUTOFIX_CODES))
