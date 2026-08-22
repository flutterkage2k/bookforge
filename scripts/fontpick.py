#!/usr/bin/env python3
"""bookforge 폰트 고르기 — 컴퓨터에 깔린 폰트를 언어별로 지정한다.

    python3 scripts/fontpick.py list [--lang ko|ja|en] [--all]
    python3 scripts/fontpick.py set <book_dir> [--ko 가족이름] [--ja …] [--en …] [--clear]

지정 결과는 book.json의 "fonts"에 들어가고, 빌드가 언어별 폰트 스택을 만든다.
  ko  한글 · 기본 본문
  ja  일본어(가나·한자)
  en  영문·숫자

거부 규칙 (조판 사고를 미리 막는다):
  - 임베드 금지 폰트(OS/2 fsType 2)는 PDF에 넣을 수 없다 → 선택 불가.
  - HTML 트랙(리포트·매거진)은 .ttf만 받는다. .otf(CFF)는 Chromium이 Type3로
    떨어뜨려 G2가 실패하고, .ttc(모음집)는 @font-face가 못 읽는다.
  - 지정한 언어의 표본 글자를 실제로 갖고 있는지 확인한다(없으면 조용한 폴백).
"""
import argparse
import json
import struct
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
FONT_DIRS = [
    SKILL / "assets" / "fonts",
    Path.home() / "Library" / "Fonts",
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
    Path("/usr/share/fonts"),
    Path.home() / ".local" / "share" / "fonts",
]
# 언어 판정 표본 — 그 언어를 조판할 때 반드시 필요한 글자들
SAMPLES = {
    "ko": "한글밝",
    "ja": "あカ働間飲",
    "en": "AZaz09",
}
HTML_STYLES = {"insight", "magazine"}  # tokens.json engine == "html"


def _tables(buf: bytes, off: int = 0) -> dict:
    """sfnt 테이블 디렉터리 → {tag: (offset, length)}."""
    num = struct.unpack_from(">H", buf, off + 4)[0]
    out = {}
    for i in range(num):
        p = off + 12 + i * 16
        tag, _, o, ln = struct.unpack_from(">4sIII", buf, p)
        out[tag.decode("latin-1")] = (o, ln)
    return out


def _family(buf: bytes, tables: dict) -> str | None:
    if "name" not in tables:
        return None
    o, _ = tables["name"]
    count, str_off = struct.unpack_from(">HH", buf, o + 2)
    best = {}
    for i in range(count):
        p = o + 6 + i * 12
        plat, enc, lang, nid, ln, so = struct.unpack_from(">HHHHHH", buf, p)
        if nid not in (1, 16):
            continue
        raw = buf[o + str_off + so: o + str_off + so + ln]
        try:
            txt = raw.decode("utf-16-be") if plat == 3 else raw.decode("mac-roman")
        except Exception:
            continue
        txt = txt.strip()
        if txt:
            best.setdefault(nid, txt)
    return best.get(16) or best.get(1)


def _weight(buf: bytes, tables: dict) -> int:
    if "OS/2" not in tables:
        return 400
    o, _ = tables["OS/2"]
    return struct.unpack_from(">H", buf, o + 4)[0]


def _fstype(buf: bytes, tables: dict) -> int:
    if "OS/2" not in tables:
        return 0
    o, _ = tables["OS/2"]
    return struct.unpack_from(">H", buf, o + 8)[0]


def _cmap_chars(buf: bytes, tables: dict, chars: str) -> bool:
    """format 4·12 서브테이블만 읽어 모든 표본 글자가 있는지 본다."""
    if "cmap" not in tables:
        return False
    o, _ = tables["cmap"]
    n = struct.unpack_from(">H", buf, o + 2)[0]
    subs = []
    for i in range(n):
        plat, enc, sub = struct.unpack_from(">HHI", buf, o + 4 + i * 8)
        if (plat, enc) in ((3, 1), (3, 10), (0, 3), (0, 4), (0, 6)):
            subs.append(o + sub)
    need = {ord(c) for c in chars}
    found = set()
    for s in subs:
        fmt = struct.unpack_from(">H", buf, s)[0]
        if fmt == 4:
            segx2 = struct.unpack_from(">H", buf, s + 6)[0]
            seg = segx2 // 2
            ends = struct.unpack_from(f">{seg}H", buf, s + 14)
            starts = struct.unpack_from(f">{seg}H", buf, s + 16 + segx2)
            deltas = struct.unpack_from(f">{seg}h", buf, s + 16 + segx2 * 2)
            ro_off = s + 16 + segx2 * 3
            ranges = struct.unpack_from(f">{seg}H", buf, ro_off)
            for cp in need - found:
                if cp > 0xFFFF:
                    continue
                for i in range(seg):
                    if starts[i] <= cp <= ends[i]:
                        if ranges[i] == 0:
                            gid = (cp + deltas[i]) & 0xFFFF
                        else:
                            gp = ro_off + i * 2 + ranges[i] + (cp - starts[i]) * 2
                            if gp + 2 > len(buf):
                                gid = 0
                            else:
                                gid = struct.unpack_from(">H", buf, gp)[0]
                                if gid:
                                    gid = (gid + deltas[i]) & 0xFFFF
                        if gid:
                            found.add(cp)
                        break
        elif fmt == 12:
            ngroups = struct.unpack_from(">I", buf, s + 12)[0]
            for g in range(ngroups):
                st, en, gi = struct.unpack_from(">III", buf, s + 16 + g * 12)
                for cp in need - found:
                    if st <= cp <= en and gi:
                        found.add(cp)
        if need <= found:
            return True
    return need <= found


def scan_file(path: Path) -> dict | None:
    try:
        buf = path.read_bytes()
    except OSError:
        return None
    if len(buf) < 12:
        return None
    tag = buf[:4]
    if tag == b"ttcf":
        fmt, off = "ttc", struct.unpack_from(">I", buf, 12)[0]
    elif tag == b"OTTO":
        fmt, off = "otf", 0
    elif tag in (b"\x00\x01\x00\x00", b"true"):
        fmt, off = "ttf", 0
    else:
        return None
    try:
        tables = _tables(buf, off)
        fam = _family(buf, tables)
        if not fam:
            return None
        return {
            "family": fam,
            "path": str(path),
            "format": fmt,
            "weight": _weight(buf, tables),
            "embeddable": not (_fstype(buf, tables) & 0x0002),
            "langs": [lg for lg, s in SAMPLES.items() if _cmap_chars(buf, tables, s)],
        }
    except Exception:
        return None


def scan(dirs=None) -> dict:
    """가족 이름 → 대표 항목 (같은 가족의 굵기 파일은 하나로 묶는다)."""
    out = {}
    for d in dirs or FONT_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if p.suffix.lower() not in (".ttf", ".otf", ".ttc"):
                continue
            info = scan_file(p)
            if not info:
                continue
            entry = {"path": info["path"], "weight": info["weight"], "format": info["format"]}
            cur = out.get(info["family"])
            rank = {"ttf": 0, "otf": 1, "ttc": 2}
            if cur is None:
                info["files"] = [entry]
                out[info["family"]] = info
            else:
                cur["files"].append(entry)
                # 같은 가족이면 ttf > otf > ttc 순으로 대표를 고른다(HTML 트랙 호환 우선)
                if rank[info["format"]] < rank[cur["format"]]:
                    info["files"] = cur["files"]
                    out[info["family"]] = info
    return out


def typst_families(dirs) -> set:
    """Typst가 실제로 인식하는 가족 이름 — 이름 규칙이 폰트마다 달라(Paperlogy는
    'Paperlogy 4'처럼 굵기별로 쪼개진다) 엔진에 직접 물어보는 편이 정확하다."""
    import subprocess
    names = set()
    for d in dirs:
        try:
            r = subprocess.run(["typst", "fonts", "--font-path", str(d), "--ignore-system-fonts"],
                               capture_output=True, text=True, timeout=60)
            names |= {ln.strip() for ln in r.stdout.splitlines() if ln.strip()}
        except (OSError, subprocess.SubprocessError):
            return set()  # typst 없음 — 검증 생략(빌드에서 다시 걸린다)
    return names


def cmd_list(args):
    fonts = scan()
    rows = []
    for fam, f in sorted(fonts.items()):
        if args.lang and args.lang not in f["langs"]:
            continue
        if not args.all and (not f["embeddable"] or not f["langs"]):
            continue
        rows.append(f)
    print(f"{'가족 이름':38} {'형식':5} {'언어':10} {'임베드':6} 경로")
    for f in rows:
        langs = "·".join(f["langs"]) or "-"
        print(f"{f['family'][:36]:38} {f['format']:5} {langs:10} "
              f"{'가능' if f['embeddable'] else '금지':6} {f['path']}")
    print(f"\n{len(rows)}개 — HTML 트랙(리포트·매거진)은 ttf만 쓸 수 있습니다.")


def validate(fonts: dict, lang: str, family: str, style: str | None) -> dict:
    f = fonts.get(family)
    if not f:
        near = [k for k in fonts if family.lower() in k.lower()][:5]
        raise SystemExit(f"FONT FAIL: '{family}' 폰트를 못 찾았습니다."
                         + (f" 비슷한 이름: {', '.join(near)}" if near else ""))
    if not f["embeddable"]:
        raise SystemExit(f"FONT FAIL: '{family}'은 임베드 금지(fsType 2) 폰트라 PDF에 넣을 수 없습니다.")
    if lang not in f["langs"]:
        raise SystemExit(f"FONT FAIL: '{family}'에 {lang} 표본 글자({SAMPLES[lang]})가 없습니다.")
    if style not in HTML_STYLES:
        fams = typst_families({str(Path(f["path"]).parent), str(SKILL / "assets" / "fonts")})
        if fams and family not in fams:
            near = sorted(n for n in fams if n.startswith(family.split()[0]))
            raise SystemExit(
                f"FONT FAIL: Typst는 '{family}'이라는 이름으로 이 폰트를 못 찾습니다."
                + (f" 이 이름들로 지정하세요: {', '.join(near)}" if near else
                   " (굵기별로 가족이 쪼개진 폰트일 수 있습니다)"))
    if style in HTML_STYLES and f["format"] != "ttf":
        raise SystemExit(
            f"FONT FAIL: '{family}'은 .{f['format']} 입니다. "
            f"{style} 스타일(HTML 조판)은 .ttf만 받습니다 — "
            "otf는 scripts/convert_fonts.py로 변환하고, ttc는 지원하지 않습니다.")
    return f


def cmd_set(args):
    book_path = Path(args.book_dir).resolve() / "book.json"
    if not book_path.exists():
        raise SystemExit(f"FONT FAIL: {book_path} 없음")
    book = json.loads(book_path.read_text(encoding="utf-8"))
    if args.clear:
        book.pop("fonts", None)
        book_path.write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")
        print("OK: 폰트 지정 해제 — 동봉 폰트로 되돌립니다.")
        return
    picks = {k: v for k, v in (("ko", args.ko), ("ja", args.ja), ("en", args.en)) if v}
    if not picks:
        raise SystemExit("FONT FAIL: --ko/--ja/--en 중 하나는 지정해야 합니다 (해제는 --clear)")
    fonts = scan()
    chosen = dict(book.get("fonts") or {})
    for lang, fam in picks.items():
        f = validate(fonts, lang, fam, book.get("style"))
        chosen[lang] = {"family": f["family"], "dir": str(Path(f["path"]).parent),
                        "format": f["format"],
                        "files": sorted(f["files"], key=lambda x: x["weight"])}
        print(f"OK {lang}: {f['family']} ({f['format']}) {f['path']}")
    book["fonts"] = chosen
    book_path.write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")
    print("→ book.json 저장. 다시 빌드하면 적용됩니다 (쪽수가 달라질 수 있어 게이트를 다시 돌리세요).")


def demo():
    """자체 점검 — 동봉 폰트만 스캔해 파싱·판정이 도는지 본다."""
    fonts = scan([SKILL / "assets" / "fonts"])
    assert fonts, "동봉 폰트를 하나도 못 읽었다"
    pre = next((f for k, f in fonts.items() if k.startswith("Pretendard")), None)
    assert pre, f"Pretendard 없음: {list(fonts)[:5]}"
    assert pre["format"] == "ttf" and pre["embeddable"]
    assert "ko" in pre["langs"] and "en" in pre["langs"]
    assert "ja" not in pre["langs"], "Pretendard는 한자가 없어야 한다(폴백 계약의 근거)"
    paper = next((f for k, f in fonts.items() if k.startswith("Paperlogy")), None)
    assert paper and "ja" in paper["langs"], "Paperlogy는 한자를 커버해야 한다"
    try:
        validate(fonts, "ja", pre["family"], "practical")
        raise AssertionError("한자 없는 폰트를 ja로 통과시켰다")
    except SystemExit:
        pass
    try:
        validate(fonts, "ko", "없는폰트", None)
        raise AssertionError("없는 폰트를 통과시켰다")
    except SystemExit:
        pass
    print("demo ok —", len(fonts), "families")


def main():
    ap = argparse.ArgumentParser(description="컴퓨터에 깔린 폰트를 언어별로 골라 책에 지정합니다.")
    sub = ap.add_subparsers(dest="cmd")
    pl = sub.add_parser("list", help="쓸 수 있는 폰트 목록")
    pl.add_argument("--lang", choices=list(SAMPLES))
    pl.add_argument("--all", action="store_true", help="임베드 금지·언어 미매칭도 전부 표시")
    ps = sub.add_parser("set", help="책에 폰트 지정")
    ps.add_argument("book_dir")
    ps.add_argument("--ko"), ps.add_argument("--ja"), ps.add_argument("--en")
    ps.add_argument("--clear", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        return demo()
    if a.cmd == "list":
        return cmd_list(a)
    if a.cmd == "set":
        return cmd_set(a)
    ap.print_help()


if __name__ == "__main__":
    main()
