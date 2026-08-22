#!/usr/bin/env python3
"""스타일 6종이 전부 빌드되는지 확인한다.

theme.typ가 깨져도 그 스타일로 책을 만들기 전에는 드러나지 않는다.
실제로 있었던 사고: code-theme 한 줄이 set text(...) 인자 목록 안으로 들어가
academic·essay가, import 누락으로 academic·essay·business가 빌드 불가였다.

    python3 tests/smoke_styles.py
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLES = ["실용", "리포트", "학술", "에세이", "비즈니스", "매거진"]

# 조판 경로를 넓게 밟도록: 본문·소제목·목록·인용·표·코드를 한 번씩 쓴다.
# 코드 블록이 있어야 set raw(theme:) 경로가 실제로 평가된다.
CHAPTER = """# 1장 제목

첫 문단입니다. 조판이 도는지만 보는 원고라 내용에 뜻은 없습니다.

## 소제목

- 첫째 항목
- 둘째 항목

> 인용 한 줄.

| 항목 | 값 |
|---|---|
| 가 | 1 |

```python
x = 1  # set raw(theme:) 경로를 밟기 위한 코드 블록
```

마지막 문단입니다.
"""


def build(style: str, work: Path) -> tuple[bool, str]:
    book = work / style
    scaffold = [sys.executable, str(ROOT / "scripts/scaffold.py"), str(book),
                "--style", style, "--title", f"{style} 연기 검사", "--length", "짧게"]
    r = subprocess.run(scaffold, capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        return False, (r.stdout + r.stderr).strip()

    # scaffold는 outline.json만 만든다 — 조판이 돌 만큼의 원고를 채워 넣는다
    (book / "chapters").mkdir(exist_ok=True)
    (book / "chapters/ch-01.md").write_text(CHAPTER, encoding="utf-8")

    for argv in (
        [sys.executable, str(ROOT / "scripts/build.py"), str(book)],
    ):
        r = subprocess.run(argv, capture_output=True, text=True, cwd=ROOT)
        if r.returncode != 0:
            tail = (r.stdout + r.stderr).strip().splitlines()
            return False, "\n    ".join(tail[-6:])
    return (book / "draft/book.pdf").exists(), "PDF가 생기지 않았습니다"


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="bf-smoke-"))
    failed = []
    try:
        for style in STYLES:
            ok, why = build(style, work)
            print(f"{'OK  ' if ok else 'FAIL'} {style}" + ("" if ok else f"\n    {why}"))
            if not ok:
                failed.append(style)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if failed:
        print(f"\n실패 {len(failed)}종: {' '.join(failed)}")
        return 1
    print(f"\n{len(STYLES)}종 전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
