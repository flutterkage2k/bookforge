"""스타일 팩의 한국어 이름 — CLI·웹 UI가 공유하는 단일 정본.

스타일 폴더 이름(practical…)은 코드·경로에 박혀 있어 그대로 두고, 사람이 고르는
자리에서는 한국어 이름을 쓴다. `--style 실용`처럼 한국어로도 지정할 수 있다.
"""

STYLES = {
    "practical": ("실용", "따라 하면 결과가 나오는 활용서 · 단계별 가이드 · 용어집"),
    "insight": ("리포트", "기술 동향·인사이트 리포트 · 데이터 브리핑"),
    "academic": ("학술", "학술 단행본 · 연구 개론 · 이론서"),
    "essay": ("에세이", "산문집 · 회고 · 문학적인 글"),
    "business": ("비즈니스", "컨설팅 리포트 · 시장 분석 · 전략 백서"),
    "magazine": ("매거진", "트렌드북 · 큐레이션 · 룩북"),
}

KO_TO_KEY = {ko: key for key, (ko, _) in STYLES.items()}


def resolve(name: str) -> str:
    """'practical'이든 '실용'이든 스타일 폴더 이름으로 되돌린다."""
    n = (name or "").strip()
    if n in STYLES:
        return n
    if n in KO_TO_KEY:
        return KO_TO_KEY[n]
    raise ValueError(f"모르는 스타일: {name} — 가능한 값: {', '.join(choices())}")


def choices() -> list[str]:
    return [f"{ko}({key})" for key, (ko, _) in STYLES.items()]


def label(key: str) -> str:
    ko, _ = STYLES.get(key, (key, ""))
    return f"{ko} ({key})"


def demo():
    assert resolve("practical") == "practical"
    assert resolve("실용") == "practical"
    assert resolve(" 매거진 ") == "magazine"
    assert label("essay") == "에세이 (essay)"
    for bad in ("", "잡지", "Practical"):
        try:
            resolve(bad)
            raise AssertionError("allowed: " + bad)
        except ValueError:
            pass
    print("demo ok")


if __name__ == "__main__":
    demo()
