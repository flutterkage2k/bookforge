#!/usr/bin/env python3
"""bookforge 웹 UI — 브라우저에서 스캐폴드·집필·빌드·게이트·미리보기.

    python3 scripts/webui.py [books_root] [--port 8765]

books_root(기본 ./books) 아래의 책 프로젝트를 목록으로 띄우고, 원고를 편집하고,
build.py / qc_gate.py / contact_sheet.py 를 같은 인터프리터로 실행한다.
127.0.0.1 에만 바인드한다 — 인증이 없으므로 외부에 열지 않는다.
"""
import argparse
import http.server
import json
import mimetypes
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fontpick  # noqa: E402
from styles_ko import STYLES as STYLE_KO  # noqa: E402
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
CHAPTER_RE = re.compile(r"^ch-[0-9]{2,3}\.md$")
STYLES = list(STYLE_KO)
ROOT = Path("books")

PAGE = """<!doctype html><meta charset=utf-8><title>bookforge</title>
<style>
 body{font:14px/1.6 -apple-system,sans-serif;margin:0;display:flex;height:100vh}
 #side{width:230px;border-right:1px solid #ddd;padding:12px;overflow:auto}
 #main{flex:1;display:flex;flex-direction:column;min-width:0}
 #bar{padding:8px 12px;border-bottom:1px solid #ddd;display:flex;gap:8px;align-items:center}
 #body{flex:1;display:flex;min-height:0}
 #edit{flex:1;display:flex;flex-direction:column;min-width:0}
 textarea{flex:1;font:12px/1.5 ui-monospace,monospace;border:0;border-top:1px solid #eee;padding:10px;resize:none}
 #view{width:44%;border-left:1px solid #ddd;display:flex;flex-direction:column}
 iframe{flex:1;border:0}
 pre{margin:0;padding:8px;background:#f6f7f8;font:11px/1.45 ui-monospace,monospace;
     max-height:170px;overflow:auto;white-space:pre-wrap}
 button{padding:5px 10px}
 a.f{display:block;padding:2px 4px;color:#1a5fb4;text-decoration:none;cursor:pointer}
 a.f.on{background:#e8f0fa;font-weight:600}
 h4{margin:14px 0 4px;font-size:12px;color:#666;letter-spacing:.05em}
</style>
<div id=side>
  <h4>책 목록</h4><div id=books></div>
  <h4>새 책 만들기</h4>
  <input id=nname placeholder="폴더 이름(영문)" style="width:100%">
  <input id=ntitle placeholder="제목" style="width:100%;margin-top:4px">
  <select id=nstyle style="width:100%;margin-top:4px"></select>
  <button style="margin-top:6px;width:100%" onclick=create()>스캐폴드</button>
  <h4>폰트 (언어별)</h4>
  <div style="font-size:12px;color:#666" id=curfonts>—</div>
  <select id=flang style="width:100%;margin-top:4px">
    <option value=ko>한국어</option><option value=ja>일본어</option><option value=en>영문·숫자</option>
  </select>
  <select id=ffam style="width:100%;margin-top:4px"><option>불러오는 중…</option></select>
  <div style="display:flex;gap:4px;margin-top:4px">
    <button style="flex:1" onclick=setFont()>지정</button>
    <button style="flex:1" onclick=clearFont()>해제</button>
  </div>
  <h4>파일</h4><div id=files></div>
</div>
<div id=main>
  <div id=bar>
    <b id=cur>—</b>
    <button onclick=save()>저장</button>
    <button onclick="run('build')">빌드</button>
    <button onclick="run('qc')">게이트</button>
    <button onclick="run('sheet')">시각검수</button>
    <span id=stat style="color:#666"></span>
  </div>
  <div id=body>
    <div id=edit><textarea id=ta spellcheck=false></textarea><pre id=log>실행 로그</pre></div>
    <div id=view>
      <div style="padding:6px 8px;border-bottom:1px solid #eee">
        <a id=pdflink href="#" target=_blank>PDF 새 탭으로 열기</a>
        <span id=gates style="color:#666;margin-left:8px"></span>
      </div>
      <div id=shots style="flex:1;overflow:auto;background:#eef0f2;padding:8px"></div>
    </div>
  </div>
</div>
<script>
let book=null, file=null;
const $=i=>document.getElementById(i);
$('nstyle').innerHTML=%STYLES%.map(s=>`<option value="${s[0]}">${s[1]}</option>`).join('');
const api=(u,d)=>fetch(u,d&&{method:'POST',body:JSON.stringify(d)}).then(r=>r.json());
async function boot(){
  const b=await api('/api/books');
  $('books').innerHTML=b.books.map(n=>`<a class=f onclick="open_('${n}')">${n}</a>`).join('')||'<i>없음</i>';
}
async function open_(n){
  book=n; $('cur').textContent=n;
  const d=await api('/api/book?name='+n);
  $('files').innerHTML=d.files.map(f=>`<a class=f onclick="load('${f}')">${f}</a>`).join('');
  $('pdflink').href='/pdf?name='+n+'&t='+Date.now();
  $('curfonts').textContent=d.fonts && Object.keys(d.fonts).length
    ? Object.entries(d.fonts).map(([k,v])=>`${k}: ${v}`).join(' · ') : '동봉 폰트 사용 중';
  $('gates').textContent=d.gates?(d.gates.pass?'게이트 PASS':'게이트 FAIL')+' · '+d.gates.pages+'쪽':'미빌드';
  $('shots').innerHTML=d.shots.map(s=>`<img src="/qc?name=${n}&page=${s}&t=${Date.now()}" style="width:100%;margin-bottom:8px;box-shadow:0 1px 4px #0003">`).join('')||'<i>시각검수를 눌러 페이지 이미지를 만드세요</i>';
  load(d.files.find(f=>f.startsWith('chapters/'))||d.files[0]);
}
async function load(f){
  file=f;
  [...document.querySelectorAll('#files .f')].forEach(a=>a.classList.toggle('on',a.textContent==f));
  const d=await api('/api/file?name='+book+'&path='+encodeURIComponent(f));
  $('ta').value=d.text; $('stat').textContent=f;
}
async function save(){
  const r=await api('/api/file',{name:book,path:file,text:$('ta').value});
  $('stat').textContent=r.ok?'저장됨':'실패: '+r.error;
}
async function loadFonts(){
  const lang=$('flang').value;
  $('ffam').innerHTML='<option>불러오는 중…</option>';
  const d=await api('/api/fonts?lang='+lang);
  $('ffam').innerHTML=d.fonts.map(f=>`<option value="${f.family}">${f.family} (${f.format})</option>`).join('')
    || '<option value="">쓸 수 있는 폰트 없음</option>';
}
$('flang').onchange=loadFonts;
async function setFont(){
  if(!book){ $('log').textContent='먼저 책을 고르세요'; return; }
  const r=await api('/api/font',{name:book,lang:$('flang').value,family:$('ffam').value});
  $('log').textContent=r.out||r.error; open_(book);
}
async function clearFont(){
  if(!book) return;
  const r=await api('/api/font',{name:book,clear:true});
  $('log').textContent=r.out||r.error; open_(book);
}
async function create(){
  const r=await api('/api/new',{name:$('nname').value,title:$('ntitle').value,style:$('nstyle').value});
  $('log').textContent=r.out||r.error;
  await boot(); if(!r.error) open_($('nname').value);
}
async function run(cmd){
  $('log').textContent='실행 중…';
  const r=await api('/api/run',{name:book,cmd:cmd});
  $('log').textContent=r.out||r.error;
  open_(book);
}
boot(); loadFonts();
</script>
"""


_FONTS = {}


def _font_cache() -> dict:
    """폰트 스캔은 수백 개 파일을 읽는다 — 프로세스 수명 동안 한 번만."""
    if not _FONTS:
        _FONTS.update(fontpick.scan())
    return _FONTS


def books_root() -> Path:
    return ROOT


def book_dir(name: str) -> Path:
    if not NAME_RE.match(name or ""):
        raise ValueError("bad book name")
    d = books_root() / name
    if not (d / "book.json").exists():
        raise ValueError("no such book")
    return d


def safe_file(name: str, rel: str) -> Path:
    """편집 허용 대상은 book.json · outline.json · chapters/ch-NN.md 뿐."""
    d = book_dir(name)
    rel = (rel or "").replace("\\", "/")
    if rel in ("book.json", "outline.json"):
        return d / rel
    if rel.startswith("chapters/") and CHAPTER_RE.match(rel.split("/", 1)[1]):
        return d / rel
    raise ValueError("path not allowed: " + rel)


def listing(name: str) -> dict:
    d = book_dir(name)
    files = ["book.json", "outline.json"]
    files += sorted("chapters/" + p.name for p in (d / "chapters").glob("ch-*.md"))
    shots = sorted(p.name for p in (d / "qc").glob("p*.png"))
    report = d / "gate-report.json"
    gates = None
    if report.exists():
        g = json.loads(report.read_text())
        gates = {"pass": g.get("pass"), "pages": g.get("gates", {}).get("G1", {}).get("pages")}
    book = json.loads((d / "book.json").read_text())
    fonts = {k: v["family"] for k, v in (book.get("fonts") or {}).items()}
    return {"files": files, "gates": gates, "shots": shots, "fonts": fonts}


def run_script(name: str, cmd: str) -> dict:
    d = book_dir(name)
    if cmd == "build":
        argv = [sys.executable, str(SKILL / "scripts/build.py"), str(d)]
    elif cmd == "qc":
        argv = [sys.executable, str(SKILL / "scripts/qc_gate.py"), str(d)]
    elif cmd == "sheet":
        pdf = next(iter(sorted((d / "final").glob("*.pdf"))), d / "draft/book.pdf")
        argv = [sys.executable, str(SKILL / "scripts/contact_sheet.py"), str(pdf),
                str(d / "qc"), "--dpi", "90", "--pages", "1,2,3,4,5"]
    else:
        raise ValueError("unknown cmd")
    p = subprocess.run(argv, capture_output=True, text=True, timeout=900)
    return {"out": (p.stdout + p.stderr).strip() or "(출력 없음)", "code": p.returncode}


def scaffold(name: str, title: str, style: str) -> dict:
    if not NAME_RE.match(name or ""):
        raise ValueError("bad book name")
    if style not in STYLES:
        raise ValueError("bad style")
    argv = [sys.executable, str(SKILL / "scripts/scaffold.py"), str(books_root() / name),
            "--style", style, "--title", title or name, "--length", "short"]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    return {"out": (p.stdout + p.stderr).strip(), "code": p.returncode}


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, "application/json; charset=utf-8",
                   json.dumps(obj, ensure_ascii=False).encode())

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        one = lambda k: (q.get(k) or [""])[0]
        try:
            if u.path == "/":
                pairs = [[k, f"{ko} ({k})"] for k, (ko, _) in STYLE_KO.items()]
                page = PAGE.replace("%STYLES%", json.dumps(pairs, ensure_ascii=False))
                return self._send(200, "text/html; charset=utf-8", page.encode())
            if u.path == "/api/books":
                names = sorted(p.parent.name for p in books_root().glob("*/book.json"))
                return self._json({"books": names})
            if u.path == "/api/book":
                return self._json(listing(one("name")))
            if u.path == "/api/file":
                return self._json({"text": safe_file(one("name"), one("path")).read_text()})
            if u.path == "/api/fonts":
                lang = one("lang") or "ko"
                if lang not in fontpick.SAMPLES:
                    raise ValueError("bad lang")
                out = [{"family": f["family"], "format": f["format"]}
                       for f in _font_cache().values()
                       if f["embeddable"] and lang in f["langs"]]
                return self._json({"fonts": sorted(out, key=lambda x: x["family"])})
            if u.path == "/pdf":
                d = book_dir(one("name"))
                pdf = next(iter(sorted((d / "final").glob("*.pdf"))), d / "draft/book.pdf")
                if not pdf.exists():
                    return self._send(404, "text/plain; charset=utf-8", "아직 빌드 전".encode())
                return self._send(200, "application/pdf", pdf.read_bytes())
            if u.path == "/qc":
                d = book_dir(one("name"))
                img = d / "qc" / Path(one("page")).name
                if not img.exists():
                    return self._send(404, "text/plain", b"no image")
                return self._send(200, mimetypes.guess_type(img.name)[0] or "image/png",
                                  img.read_bytes())
            self._send(404, "text/plain", b"not found")
        except Exception as e:  # 잘못된 이름·경로는 400으로 되돌려준다
            self._json({"error": str(e)}, 400)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}")
            if u.path == "/api/file":
                safe_file(data["name"], data["path"]).write_text(data["text"])
                return self._json({"ok": True})
            if u.path == "/api/font":
                d = book_dir(data["name"])
                argv = [sys.executable, str(SKILL / "scripts/fontpick.py"), "set", str(d)]
                argv += ["--clear"] if data.get("clear") else \
                        [f"--{data['lang']}", data["family"]]
                p = subprocess.run(argv, capture_output=True, text=True, timeout=300)
                return self._json({"out": (p.stdout + p.stderr).strip(), "code": p.returncode})
            if u.path == "/api/run":
                return self._json(run_script(data["name"], data["cmd"]))
            if u.path == "/api/new":
                return self._json(scaffold(data.get("name"), data.get("title"),
                                           data.get("style")))
            self._send(404, "text/plain", b"not found")
        except Exception as e:
            self._json({"error": str(e)}, 400)

    def log_message(self, *a):
        pass


def demo():
    """경로 가드 자체 점검 — 편집 허용 목록 밖은 전부 거부해야 한다."""
    global ROOT
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ROOT = Path(tmp)
        d = ROOT / "demo"
        (d / "chapters").mkdir(parents=True)
        (d / "book.json").write_text("{}")
        assert safe_file("demo", "chapters/ch-01.md").name == "ch-01.md"
        assert safe_file("demo", "outline.json").name == "outline.json"
        for bad in ("../../etc/passwd", "chapters/../book.json", "chapters/x.md",
                    "final/nuance.pdf", ""):
            try:
                safe_file("demo", bad)
                raise AssertionError("allowed: " + bad)
            except ValueError:
                pass
        for bad_name in ("../x", "de mo", ""):
            try:
                book_dir(bad_name)
                raise AssertionError("allowed: " + bad_name)
            except ValueError:
                pass
    print("demo ok")


def main():
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("books_root", nargs="?", default="books")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        return demo()
    ROOT = Path(a.books_root).resolve()
    ROOT.mkdir(parents=True, exist_ok=True)
    print(f"bookforge web UI → http://127.0.0.1:{a.port}  (books: {ROOT})")
    http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
