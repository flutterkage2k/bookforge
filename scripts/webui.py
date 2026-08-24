#!/usr/bin/env python3
"""bookforge 웹 UI — 주제에서 PDF까지 여섯 단계를 순서대로 밟는 작업창.

    python3 scripts/webui.py [books_root] [--port 8765]

단계: ① 책 만들기 ② 자료 ③ 목차 ④ 집필 ⑤ 빌드·검사 ⑥ 검수
각 단계의 완료 여부는 파일 상태에서 계산한다(가짜 진행률 없음).
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
EDITABLE = ("book.json", "outline.json", "research.md")
STYLES = list(STYLE_KO)
LENGTHS = {"short": "짧게", "standard": "보통", "long": "길게"}
# 스타일 고르기용 견본 — examples/showcase에 이미 들어 있는 실물 산출물이다.
# (새로 렌더하지 않는다: 표지 한 장을 만들려고 빌드를 돌릴 이유가 없다)
SAMPLES = {
    "practical": ("practical-prompt-patterns-cover.png", "practical-prompt-patterns-page9.png"),
    "insight": ("insight-ondevice-ai-cover.png", "insight-ondevice-ai-page10.png"),
    "academic": ("academic-game-theory-cover.png", "academic-game-theory-page11.png"),
    "essay": ("essay-evening-sentences-cover.png", "essay-evening-sentences-page6.png"),
    "business": ("business-sme-ai-cover.png", "business-sme-ai-page9.png"),
    "magazine": ("magazine-trend-brief-cover.png", "magazine-trend-brief-page6.png"),
}
ROOT = Path("books")

from gatehelp import lookup as gate_lookup, AUTOFIX_CODES, TOOL  # noqa: E402

# 오류 신고 창구. GitHub Issues를 1차로 두는 이유는 비밀값이 필요 없어서다 —
# 텔레그램·슬랙·디스코드는 보내는 쪽에 봇 토큰/웹훅이 있어야 하는데, 이 서버의 소스는
# 공개 저장소에 있으므로 토큰을 넣는 순간 누구나 그 채널에 쏠 수 있게 된다.
# 이슈는 공개다. 원고 일부가 실리므로 보내기 전에 무엇이 나가는지 반드시 보여준다.
REPORT_REPO = "flutterkage2k/bookforge"
REPORT_MAIL = "flutterkage2k@gmail.com"
URL_BODY_MAX = 4000   # 프리필 URL이 길면 브라우저·GitHub 양쪽에서 잘린다


PAGE = r"""<!doctype html><meta charset=utf-8><title>bookforge</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
 :root{
  --bg:#f6f7f9; --panel:#fff; --ink:#1b1f24; --mute:#6b7480; --line:#e3e7ec;
  --brand:#1a5fb4; --brand-soft:#eaf1fb; --ok:#1f7a4d; --ok-soft:#e8f5ee;
  --bad:#b3261e; --bad-soft:#fdecea;
 }
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);
   font:15px/1.65 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard",sans-serif}
 header{background:var(--panel);border-bottom:1px solid var(--line);padding:10px 18px;
   display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:5}
 header h1{font-size:15px;margin:0;letter-spacing:-.01em}
 header h1 span{color:var(--mute);font-weight:400}
 .wrap{display:flex;gap:18px;padding:18px;align-items:flex-start}
 aside{width:236px;flex:none}
 main{flex:1;min-width:0}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:14px}
 .card h2{font-size:15px;margin:0 0 4px}
 .card .hint{color:var(--mute);font-size:13px;margin:0 0 12px}
 .steps{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
 .step{flex:1 1 120px;background:var(--panel);border:1px solid var(--line);border-radius:10px;
   padding:9px 11px;cursor:pointer;text-align:left}
 .step b{display:block;font-size:13px}
 .step small{color:var(--mute);font-size:11px}
 .step.on{border-color:var(--brand);box-shadow:0 0 0 2px var(--brand-soft)}
 .step.done b::after{content:" ✓";color:var(--ok)}
 .booklist button{display:block;width:100%;text-align:left;padding:7px 9px;border:0;
   background:none;border-radius:8px;color:var(--ink);cursor:pointer;font-size:14px}
 .booklist button:hover{background:var(--bg)}
 .booklist button.on{background:var(--brand-soft);color:var(--brand);font-weight:600}
 label{display:block;font-size:13px;color:var(--mute);margin:10px 0 4px}
 input,select,textarea{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:8px;
   font:inherit;background:#fff;color:var(--ink)}
 textarea{font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;resize:vertical}
 button{padding:8px 14px;border:1px solid var(--line);background:#fff;border-radius:8px;
   font:inherit;cursor:pointer}
 button:hover{background:var(--bg)}
 button.primary{background:var(--brand);border-color:var(--brand);color:#fff}
 button.primary:hover{filter:brightness(1.08)}
 .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
 .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600}
 .pill.ok{background:var(--ok-soft);color:var(--ok)}
 .pill.bad{background:var(--bad-soft);color:var(--bad)}
 .pill.idle{background:var(--bg);color:var(--mute)}
 .pill.own-ms{background:var(--brand-soft);color:var(--brand)}
 .pill.own-st{background:#fff4e5;color:#9a5b00}
 .pill.own-tool{background:var(--bad-soft);color:var(--bad)}
 .verdict{margin:10px 0 14px;padding:12px 14px;border:1px solid var(--line);
   border-left:3px solid var(--brand);border-radius:8px;background:var(--panel)}
 .verdict p{margin:0 0 8px}
 .verdict button{margin-right:8px}
 .repbox{background:var(--panel);border-radius:10px;padding:16px;max-width:900px;
   width:92vw;max-height:82vh;display:flex;flex-direction:column;gap:10px}
 .repbox .warn{margin:0;padding:10px 12px;border-radius:8px;
   background:var(--bad-soft);color:var(--bad)}
 .reptext{flex:1;min-height:40vh;font-family:ui-monospace,Menlo,monospace;font-size:12px;
   line-height:1.5;border:1px solid var(--line);border-radius:8px;padding:10px;resize:vertical}
 .repbtns{display:flex;gap:8px;flex-wrap:wrap}
 table{width:100%;border-collapse:collapse;font-size:13px}
 th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
 th{color:var(--mute);font-weight:600}
 td button{white-space:nowrap;padding:6px 10px}
 #otbl td:last-child{width:1%}
 pre{margin:0;padding:10px;background:#0f1419;color:#d7dde5;border-radius:8px;
   font:12px/1.5 ui-monospace,monospace;max-height:220px;overflow:auto;white-space:pre-wrap}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}
 .grid img{width:100%;border:1px solid var(--line);border-radius:8px;background:#fff;display:block}
 .thumb{padding:0;border:0;background:none;cursor:zoom-in;width:100%}
 .thumb:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
 .styles{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px}
 .styles button{border:1px solid var(--line);border-radius:10px;padding:10px;cursor:pointer;
   background:#fff;text-align:left;font:inherit;color:inherit}
 .styles button.on{border-color:var(--brand);background:var(--brand-soft)}
 .styles b{font-size:14px}.styles small{display:block;color:var(--mute);font-size:12px;margin-top:2px}
 .styles{grid-template-columns:repeat(auto-fill,minmax(215px,1fr))}
 .samples{display:flex;gap:6px;margin-bottom:8px}
 .samples img{width:50%;border:1px solid var(--line);border-radius:6px;background:#fff;
   aspect-ratio:3/4;object-fit:contain}
 .chaps{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
 .chaps button.on{border-color:var(--brand);color:var(--brand);font-weight:600}
 .muted{color:var(--mute);font-size:13px}
 .lb{position:fixed;inset:0;background:#11151ae6;display:flex;align-items:center;
   justify-content:center;z-index:50;padding:56px 16px 16px}
 .lb img{max-height:calc(100vh - 76px);max-width:96vw;background:#fff;border-radius:6px;
   box-shadow:0 12px 40px #0007}
 .lbbar{position:fixed;top:0;left:0;right:0;height:48px;display:flex;gap:10px;align-items:center;
   padding:0 14px;background:#0b0f14;color:#fff;font-size:13px}
 .lbbar b{font-size:14px}
 .lbbar button{background:#1d242c;border-color:#2c3540;color:#fff}
 .lbbar button:hover{background:#28313b}
 .warnbox{margin:10px 0 0;padding:9px 10px;border:1px solid #f0b4ae;background:var(--bad-soft);
   color:var(--bad);border-radius:8px;font-size:12px;line-height:1.5}
 code{background:var(--bg);padding:1px 5px;border-radius:5px;font-size:13px}
 #otbl{display:block;overflow-x:auto}          /* 목차 표가 좁은 창에서 삐져나오던 문제 */
 header h1{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 @media (max-width:900px){
   .wrap{flex-direction:column}
   aside{width:auto;display:flex;gap:14px;flex-wrap:wrap}
   aside .card{flex:1 1 240px}
 }
</style>
<header>
  <h1>bookforge <span id=hbook>— 책을 고르거나 새로 만드세요</span></h1>
  <span id=hstate class="pill idle">대기</span>
  <span style="flex:1"></span>
  <a id=pdflink class=muted href="#" target=_blank style="display:none">PDF 열기 ↗</a>
  <span class=muted title="서버가 실행 중인 코드의 커밋. git log -1 과 다르면 서버가 옛 코드입니다 — 재시작하세요.">서버 버전 %VERSION%</span>
</header>
<div class=wrap>
 <aside>
  <div class=card>
    <h2>책</h2>
    <div class=booklist id=books></div>
    <button class=primary style="width:100%;margin-top:10px" onclick="newBook()">+ 새 책 만들기</button>
  </div>
  <div class=card>
    <h2>조사 설정</h2>
    <label style="display:flex;gap:8px;align-items:center;margin:0">
      <input type=checkbox id=useweb style="width:auto"> 웹으로 사실 확인</label>
    <p class=hint style="margin:6px 0 0">켜면 변하는 사실(가격·버전·정책·통계)만 골라
      검색합니다. 개념 설명은 검색하지 않습니다.</p>
    <label>검색 상한(질문 수)</label>
    <input id=maxq type=number value=6 min=1 max=12>
  </div>
  <div class=card>
    <h2>폰트</h2>
    <p class=hint id=curfonts>동봉 폰트</p>
    <select id=flang onchange=loadFonts()>
      <option value=ko>한국어</option><option value=ja>일본어</option><option value=en>영문·숫자</option>
    </select>
    <select id=ffam style="margin-top:6px"><option>—</option></select>
    <div class=row style="margin-top:6px">
      <button style="flex:1" onclick=setFont()>적용</button>
      <button style="flex:1" onclick=clearFont()>되돌리기</button>
    </div>
    <button style="width:100%;margin-top:6px" onclick=saveDefaults()>새 책 기본값으로</button>
    <p class=hint id=deffonts style="margin:6px 0 0">기본값 없음</p>
    <p class=warnbox>⚠ 배포 전 라이선스를 확인하세요.<br>
      PDF에는 쓴 서체가 <b>파일로 박혀</b> 나갑니다. 개인 열람은 괜찮아도 판매·인쇄물 배포에는
      별도 라이선스가 필요한 서체가 많고, 위반 시 금전적 책임이 따릅니다.<br>
      동봉 서체(Pretendard·Noto Serif KR·Paperlogy·Gmarket Sans·Barlow)는 OFL이라 상업 배포도
      가능합니다. 직접 고른 서체는 <b>본인이 확인</b>해야 합니다.</p>
  </div>
 </aside>
 <main>
  <div class=steps id=steps role=list aria-label="작업 단계"></div>
  <div id=panel></div>
  <div class=card><h2>실행 기록</h2><pre id=log role=status aria-live=polite>—</pre></div>
 </main>
</div>
<script>
const $=i=>document.getElementById(i);
const api=(u,d)=>fetch(u,d&&{method:'POST',body:JSON.stringify(d)})
  .then(r=>r.json().catch(()=>({error:`서버가 ${r.status} 응답을 보냈습니다`})))
  .catch(()=>({error:'서버에 연결할 수 없습니다. 터미널에서 서버가 살아 있는지 확인하세요.'}));
const esc=s=>String(s??'').replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const STYLES=%STYLES%, LENGTHS=%LENGTHS%;
let book=null, state=null, step=1, chap=null, newStyle='practical';

const STEPS=[
 ['책 만들기','주제와 스타일을 정한다'],
 ['자료','근거로 쓸 재료를 넣는다'],
 ['목차','장 구성을 정한다'],
 ['집필','장별 원고를 쓴다'],
 ['빌드·검사','PDF를 만들고 품질 검사를 돌린다'],
 ['검수','실제 지면을 눈으로 본다'],
];

async function boot(){
  const b=await api('/api/books');
  $('books').innerHTML=(b.books||[]).map(n=>
    `<button type=button class="${n===book?'on':''}" aria-current="${n===book}"
       onclick="open_('${esc(n)}')">${esc(n)}</button>`).join('')
    || '<p class=muted>아직 책이 없습니다</p>';
}
async function open_(n){
  book=n; state=await api('/api/state?name='+encodeURIComponent(n));
  if(state.error){ $('log').textContent=state.error; return; }
  $('hbook').textContent='— '+(state.book.title||n);
  $('pdflink').style.display=state.steps.built?'inline':'none';
  $('pdflink').href='/pdf?name='+n+'&t='+Date.now();
  const g=state.gate;
  $('hstate').className='pill '+(g? (g.pass?'ok':'bad') : 'idle');
  $('hstate').textContent = !g ? '미빌드'
    : g.stale ? '빌드 후 검사 필요' : (g.pass?`게이트 통과 · ${g.pages}쪽`:'게이트 실패');
  if(g&&g.stale) $('hstate').className='pill idle';
  $('curfonts').textContent=Object.keys(state.fonts||{}).length
    ? Object.entries(state.fonts).map(([k,v])=>`${k}: ${v}`).join(' · ') : '동봉 폰트';
  if(!chap || !state.chapters.includes(chap)) chap=state.chapters[0]||null;
  await boot(); loadFonts();
  if(step===1) step=nextStep();
  render();
}
function nextStep(){
  const s=state.steps;
  if(!s.research) return 2;
  if(!s.outline) return 3;
  if(!s.written) return 4;
  if(!s.passed) return 5;
  return 6;
}
function go(n){ step=n; render(); }
function newBook(){
  // 선택을 비우지 않으면 1단계에 이전 책의 '책 정보'가 남아 새 책을 만드는 화면처럼 안 보인다
  book=null; state=null; chap=null; step=1;
  $('hbook').textContent='— 책을 고르거나 새로 만드세요';
  $('hstate').className='pill idle'; $('hstate').textContent='대기';
  $('pdflink').style.display='none';
  $('curfonts').textContent='동봉 폰트';
  boot(); render();
}
function render(){
  $('steps').innerHTML=STEPS.map((s,i)=>{
    const n=i+1, done=state&&stepDone(n);
    return `<button class="step ${n===step?'on':''} ${done?'done':''}" onclick="go(${n})">
      <b>${n}. ${s[0]}</b><small>${s[1]}</small></button>`;
  }).join('');
  // 다시 그리기 전에 입력값을 담아 두고, 그린 뒤 되돌린다(폴더 이름·제목·책 정보 유실 방지)
  const keep = {};
  document.querySelectorAll('#panel input').forEach(el=>{ if(el.id) keep[el.id]=el.value; });
  $('panel').innerHTML = (!state && step!==1)
    ? cardMsg('왼쪽에서 책을 고르거나 새로 만드세요.')
    : ((state && step!==1 ? banner() : '') + PANEL[step]());
  document.querySelectorAll('#panel input').forEach(el=>{
    if(el.id && keep[el.id] !== undefined && el.value === '') el.value = keep[el.id];
  });
  if(step===4) loadChapter();
  if(step===2) loadFile('research.md','ta2');
}
function stepDone(n){
  const s=state.steps;
  return [null,true,s.research,s.outline,s.written,s.passed,s.reviewed][n];
}
function cardMsg(m){ return `<div class=card><p class=muted>${m}</p></div>`; }

// 지금 무엇을 해야 하는지 한 줄로 — 상태에서 계산한다(모든 단계 상단에 같은 문장이 뜬다)
function nextAction(){
  const s=state.steps;
  if(!s.outline)  return ['3단계에서 “AI에게 목차 맡기기”를 누르거나 직접 장을 넣고 저장하세요.',3];
  if(!s.written)  return ['4단계에서 “AI에게 전체 집필 맡기기”를 누르세요(장당 1분 안팎).',4];
  if(!s.built)    return ['5단계에서 ① 빌드를 누르세요.',5];
  if(!s.passed)   return ['5단계에서 ② 게이트를 누르세요. 통과해야 final PDF가 생깁니다.',5];
  if(!s.reviewed) return ['5단계에서 ③ 지면 이미지를 만들고, 6단계에서 눈으로 확인하세요.',5];
  return ['모든 단계를 마쳤습니다. 원고를 고치면 5단계부터 다시 돌리세요.',6];
}
function banner(){
  const [msg,n]=nextAction();
  return `<div class=card style="border-color:var(--brand);background:var(--brand-soft)">
    <div class=row><b>다음 할 일</b><span style="flex:1">${msg}</span>
    <button onclick="go(${n})">${n}단계로</button>
    <button class=primary onclick="agent('auto')">주제만 주고 전부 맡기기</button></div>
    <p class=hint style="margin:8px 0 0">‘전부 맡기기’는 조사 → 목차 → 집필 → 빌드·검사·수정을
      끝까지 돌립니다. 이미 채운 단계는 건너뜁니다.</p></div>`;
}

const PANEL={
 1:()=>(state?metaForm():'')+`<div class=card>
   <h2>새 책 만들기${state?' (다른 책을 새로 만듭니다)':''}</h2>
   <p class=hint>폴더 이름은 영문·숫자만. 제목·저자는 나중에 바꿔도 됩니다.</p>
   <div class=row>
     <div style="flex:1"><label>폴더 이름</label><input id=nname placeholder="mybook"></div>
     <div style="flex:2"><label>제목</label><input id=ntitle placeholder="책 제목"></div>
   </div>
   <div class=row>
     <div style="flex:2"><label>부제</label><input id=nsub placeholder="부제 (선택)"></div>
     <div style="flex:1"><label>저자</label><input id=nauthor placeholder="지은이"></div>
     <div style="flex:1"><label>분량</label><select id=nlen>${
       Object.entries(LENGTHS).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></div>
   </div>
   <label>스타일</label>
   <p class=hint style="margin:0 0 8px">아래는 각 스타일로 실제 만든 책의 표지와 본문 지면입니다.
     클릭해서 고르세요.</p>
   <div class=styles>${STYLES.map(s=>
     `<button type=button class="${s[0]===newStyle?'on':''}" aria-pressed="${s[0]===newStyle}"
        onclick="pickStyle('${s[0]}')">
        <div class=samples>
          <img src="/sample?style=${s[0]}&kind=cover" alt="${esc(s[1])} 표지 견본">
          <img src="/sample?style=${s[0]}&kind=page" alt="${esc(s[1])} 본문 견본">
        </div>
        <b>${esc(s[1])}</b><small>${esc(s[2])}</small></button>`).join('')}</div>
   <div class=row style="margin-top:14px"><button class=primary onclick=create()>만들기</button>
     <span class=muted>만들면 2단계(자료)로 넘어갑니다</span></div>
   <p class=hint style="margin-top:12px">책을 만든 뒤 2단계에 자료를 넣고, 어느 단계에서든
     <b>“주제만 주고 전부 맡기기”</b>를 누르면 조사·목차·집필·검사 통과까지 한 번에 갑니다.
     7장 기준 15~25분 걸립니다.</p>
 </div>`,
 2:()=>`<div class=card>
   <h2>자료 넣기</h2>
   <p class=hint>조사한 내용·인용할 사실·수치를 여기에 붙여넣습니다. 이 파일(<code>research.md</code>)은
     책에 실리지 않고 집필의 근거로만 씁니다. 확인 못 한 수치는 넣지 마세요 —
     본문에 없는 숫자를 콜아웃에 쓰면 게이트(G10)가 잡습니다.</p>
   <textarea id=ta2 rows=18 placeholder="예)&#10;- 핵심 개념 정의:&#10;- 사례:&#10;- 수치(출처·연도 필수):&#10;- 논쟁점:&#10;- 인용할 문장:"></textarea>
   <div class=row style="margin-top:10px"><button class=primary onclick="saveFile('research.md','ta2')">저장</button>
   <button onclick="agent('research')">AI에게 조사 맡기기</button>
   <button onclick="go(3)">다음: 목차</button></div>
   <p class=hint style="margin-top:10px">‘AI에게 조사 맡기기’는 이 컴퓨터의 Claude Code를 불러
     주제에 대한 조사 노트를 만들어 기존 내용 아래에 붙입니다. 확인 못 한 것은
     ‘확인 필요’로 표시하도록 시켰습니다 — 그 항목은 직접 채워 주세요.</p>
 </div>`,
 3:()=>`<div class=card>
   <h2>목차</h2>
   <p class=hint>장을 추가하고 제목·요약을 채웁니다. 저장하면 빈 원고 파일이 함께 만들어집니다.
     요약은 장 도비라에 그대로 실립니다.</p>
   <table id=otbl><thead><tr><th style="width:32%">장 제목</th><th>요약(도비라에 실림)</th>
     <th style="width:24%">목차 한 줄</th><th></th></tr></thead>
   <tbody>${(state.outline||[]).map((c,i)=>orow(c,i)).join('')}</tbody></table>
   <div class=row style="margin-top:12px">
     <button class=primary onclick="agent('outline')">AI에게 목차 맡기기</button>
     <button onclick=addRow()>+ 장 추가</button>
     <button onclick=saveOutline()>직접 쓴 목차 저장</button>
     <span class=muted>${(state.outline||[]).length}개 장 ${
       state.steps.outline?'':'· 아직 비어 있습니다(빌드하려면 최소 1장 필요)'}</span>
   </div>
   <p class=hint style="margin-top:10px">건너뛸 수 없는 단계입니다. 목차가 비면 빌드가
     <code>chapter file missing</code>으로 멈춥니다. 분량 기준은 짧게 = 5~7장입니다.</p>
 </div>`,
 4:()=>`<div class=card>
   <h2>집필</h2>
   <p class=hint>마크다운으로 씁니다. 첫 줄은 <code># 장 제목</code>이고 목차의 제목과 같아야 합니다.
     사진·스크린샷은 「이미지 넣기」 버튼으로 올리거나, 복사해 두고 본문에 <b>Cmd+V로 붙여넣으면</b>
     책 폴더 assets/에 저장되고 커서 자리에 링크가 끼워집니다. 캡션과 출처만 채우면 됩니다.</p>
   <div class=chaps>${state.chapters.map(c=>{
     const n=(state.sizes||{})[c]||0;
     const un = dirty(c) ? ' •저장 안 됨' : '';
     return `<button class="${c===chap?'on':''}" onclick="pickChap('${c}')">
       ${c.replace('chapters/','')} <span class=muted>${n<400?'미작성':n+'자'}${un}</span></button>`;}).join('')
     || '<span class=muted>3단계에서 목차를 먼저 저장하세요.</span>'}</div>
   <textarea id=ta4 rows=22></textarea>
   <div class=row style="margin-top:10px">
     <button class=primary onclick="agent('all')">AI에게 전체 집필 맡기기</button>
     <button onclick="agent('chapter',chap)">이 장만 다시 쓰게 하기</button>
     <button onclick="agent('diagrams')">AI에게 도해 넣기</button>
     <button onclick="$('imgfile').click()">이미지 넣기</button>
     <input type=file id=imgfile style="display:none"
       accept="image/png,image/jpeg,image/webp,image/svg+xml"
       onchange="if(this.files[0])uploadImage(this.files[0]);this.value=''">
     <button onclick="saveFile(chap,'ta4')">직접 고친 내용 저장</button>
     <button onclick="go(5)">다음: 빌드</button></div>
   <p class=hint style="margin-top:10px">‘도해 넣기’는 본문을 읽고 그림이 필요한 자리를 최대
     3곳 골라 SVG나 차트를 만들어 넣습니다(에세이 스타일은 무이미지 원칙이라 건너뜁니다).
     자동 집필은 장당 1분 안팎 걸립니다. 목차의 요약과
     2단계 자료를 근거로 씁니다 — 자료에 없는 수치는 쓰지 않도록 시켰습니다.</p>
   <details style="margin-top:12px"><summary class=muted>쓸 수 있는 문법</summary>
     <table><tr><th>요소</th><th>쓰는 법</th></tr>
     <tr><td>절 / 항</td><td><code>## 절 제목</code> · <code>### 항 제목</code></td></tr>
     <tr><td>강조</td><td><code>**굵게**</code></td></tr>
     <tr><td>인용</td><td><code>&gt; 인용문</code></td></tr>
     <tr><td>표</td><td><code>| 열 | 열 |</code> 형식</td></tr>
     <tr><td>콜아웃</td><td><code>::: tip 제목</code> … <code>:::</code> (info·tip·warn·quote·pull)</td></tr>
     <tr><td>도해</td><td><code>![캡션](../assets/fig-01.svg "출처: …")</code> — 단독 문단</td></tr>
     <tr><td>이미지</td><td><code>![캡션](../assets/사진.png "출처: …")</code> — 단독 문단. png·jpg·webp·svg</td></tr>
     </table></details>
 </div>`,
 5:()=>`<div class=card>
   <h2>빌드·검사</h2>
   <p class=hint>빌드가 PDF를 만들고, <b>게이트</b>(조판 품질 검사 16종)가 검사를 돌립니다.
     통과해야만 final 폴더에 PDF가 생깁니다.</p>
   <div class=row>
     <button class="${state.steps.built?'':'primary'}" onclick="run('build')">① 빌드</button>
     <button class="${state.steps.built&&!state.steps.passed?'primary':''}"
       ${state.steps.built?'':'disabled title="먼저 빌드하세요"'} onclick="run('qc')">② 게이트</button>
     <button ${state.steps.built?'':'disabled title="먼저 빌드하세요"'}
       onclick="run('sheet')">③ 지면 이미지 만들기(전 지면)</button>
     <button onclick="agent('fix')">AI에게 게이트 통과까지 맡기기</button>
   </div>
   <p class=hint style="margin-top:8px">마지막 버튼은 빌드 → 검사 → 실패한 장의 분량 조절을
     통과할 때까지 반복합니다(최대 6회차). 장 하나 고칠 때마다 1분 안팎 걸립니다.</p>
   <table style="margin-top:12px"><tr><th style="width:22%">버튼</th><th>무엇이 생기나</th></tr>
     <tr><td>① 빌드</td><td><code>draft/book.pdf</code> — 아직 검사 전 원고 PDF</td></tr>
     <tr><td>② 게이트</td><td>검사 통과 시에만 <code>final/책이름.pdf</code>. 실패하면 아래 표에 이유가 뜹니다</td></tr>
     <tr><td>③ 지면 이미지</td><td><code>qc/p001.png</code>… — 6단계에서 볼 지면 그림</td></tr></table>
   ${gateTable()}
 </div>`,
 6:()=>`<div class=card>
   <h2>검수 <button style="float:right" onclick="run('sheet')">지면 이미지 다시 만들기</button></h2>
   ${state.shots.length && state.pages && state.shots.length < state.pages
     ? `<p class="pill bad" style="display:block;padding:8px 12px">지면 이미지가 ${state.shots.length}장뿐입니다
        (책은 ${state.pages}쪽). 위 버튼을 눌러 전 지면을 다시 만드세요 — 예전 방식으로 앞 6쪽만
        만들어진 상태입니다.</p>` : ''}
   <p class=hint>지면을 눈으로 보고, 고칠 곳을 찾으면 그 쪽 아래 버튼으로 바로 갑니다.
     표지·차례는 <b>책 정보</b>와 스타일이 만들고, 본문 지면은 <b>그 장의 원고</b>가 만듭니다.
     쪽에 무엇이 몇 번째로 오는지는 직접 지정하지 않습니다 — 원고 순서와 분량이 정합니다.</p>
   ${state.shots.length? `<div class=grid>${state.shots.map(s=>{
     const pg=String(parseInt(s.replace(/[^0-9]/g,''),10));
     const src=(state.pagemap||{})[pg];
     const where = !src ? '' : src==='front'
       ? `<button onclick="go(1)">책 정보 고치기</button>`
       : `<button onclick="pickChap('chapters/${esc(src)}');go(4)">${esc(src)} 고치기</button>`;
     return `<figure style="margin:0">
       <button type=button class=thumb onclick="viewPage(${pg})" title="${pg}쪽 크게 보기">
         <img src="/qc?name=${book}&page=${s}&v=${state.sheet_ts||0}" loading=lazy
              alt="${pg}쪽 지면"></button>
       <figcaption class=muted style="margin-top:4px">
         <div><b>${pg}쪽</b> ${src&&src!=='front'?src:'앞부속'}</div>
         <div style="margin-top:4px">${where}</div></figcaption></figure>`;}).join('')}</div>`
     : '<p class=muted>5단계에서 “지면 이미지 만들기”를 먼저 누르세요.</p>'}
 </div>`,
};

function metaForm(){
  const b=state.book||{};
  return `<div class=card>
    <h2>책 정보 — 표지·판권면에 그대로 실립니다</h2>
    <p class=hint>여기 값이 표지 문구가 됩니다. 고친 뒤 5단계에서 다시 빌드해야 반영됩니다.
      표지의 <b>배치·급수</b>는 스타일 팩이 정합니다(스타일을 바꾸면 표지가 통째로 달라집니다).</p>
    <div class=row>
      <div style="flex:2"><label>제목</label><input id=mtitle value="${esc(b.title||'')}"></div>
      <div style="flex:2"><label>부제 (비우면 표지 리본이 사라집니다)</label>
        <input id=msub value="${esc(b.subtitle||'')}"></div>
    </div>
    <div class=row>
      <div style="flex:1"><label>지은이</label><input id=mauthor value="${esc(b.author||'')}"></div>
      <div style="flex:1"><label>펴낸곳 (비우면 표지·판권면에서 빠집니다)</label>
        <input id=mpub placeholder="bookforge" value="${esc(b.publisher===undefined?'':b.publisher)}"></div>
      <div style="flex:1"><label>발행 (예: 2026-08)</label><input id=mdate value="${esc(b.date||'')}"></div>
      <div style="flex:1"><label>브랜드색 (#rrggbb)</label><input id=mbrand value="${esc(b.brand||'')}"></div>
    </div>
    <div class=row>
      <div style="flex:1"><label>조판 표기 (판권면 · 비우면 그 줄이 빠집니다)</label>
        <input id=mtypeset placeholder="bookforge" value="${esc(b.typesetter===undefined?'bookforge':b.typesetter)}"></div>
    </div>
    ${b.style!=='business'?'':`<div class=row>
      <div style="flex:1"><label>시리즈 라벨 (표지 · 비우면 빠집니다)</label>
        <input id=mseries value="${esc(b.series===undefined?'BOOKFORGE INSIGHT REPORT':b.series)}"></div>
      <div style="flex:1"><label>호수</label>
        <input id=mseriesno value="${esc(b.series_no===undefined?'REPORT 01':b.series_no)}"></div>
    </div>`}
    <div class=row style="margin-top:12px"><button class=primary onclick=saveMeta()>책 정보 저장</button>
      <span class=muted>저장 후 5단계 ① 빌드</span></div>
  </div>`;
}
async function saveMeta(){
  const r=await api('/api/meta',{name:book,title:$('mtitle').value,subtitle:$('msub').value,
    author:$('mauthor').value,publisher:$('mpub').value,date:$('mdate').value,
    brand:$('mbrand').value,typesetter:$('mtypeset').value,
    ...($('mseries')?{series:$('mseries').value,series_no:$('mseriesno').value}:{})});
  $('log').textContent=r.out||r.error;
  if(!r.error) open_(book);
}
// 지면 크게 보기 — 모니터 세로에 맞춘다. ← → 로 넘기고 Esc로 닫는다.
let viewN = 0;
function viewPage(n){
  viewN = n;
  let lb = $('lb');
  if (!lb) {
    lb = document.createElement('div');
    lb.id = 'lb'; lb.className = 'lb';
    lb.onclick = e => { if (e.target === lb) closeView(); };
    lb.setAttribute('role', 'dialog');
    lb.setAttribute('aria-modal', 'true');
    lb.tabIndex = -1;
    document.body.appendChild(lb);
    document.addEventListener('keydown', viewKeys);
  }
  drawView();
  $('lb').focus();
}
function drawView(){
  const total = state.pages || (state.shots||[]).length;
  const src = (state.pagemap||{})[String(viewN)];
  const fix = !src ? '' : src === 'front'
    ? `<button onclick="closeView();go(1)">책 정보 고치기</button>`
    : `<button onclick="closeView();pickChap('chapters/${src}');go(4)">${src} 고치기</button>`;
  $('lb').innerHTML = `
    <div class=lbbar>
      <b>${viewN} / ${total}쪽</b>
      <span>${src && src !== 'front' ? src : '앞부속'}</span>
      ${fix}
      <span style="flex:1"></span>
      <button onclick="stepView(-1)">← 이전</button>
      <button onclick="stepView(1)">다음 →</button>
      <button onclick="closeView()">닫기 (Esc)</button>
    </div>
    <img src="/page?name=${book}&n=${viewN}&dpi=150" alt="${viewN}쪽">`;
}
function stepView(d){
  const total = state.pages || (state.shots||[]).length;
  viewN = Math.min(total, Math.max(1, viewN + d));
  drawView();
}
function closeView(){
  const lb = $('lb');
  if (lb) { lb.remove(); document.removeEventListener('keydown', viewKeys); }
}
function viewKeys(e){
  if (e.key === 'Escape') { closeView(); return; }
  if (e.key === 'ArrowRight') { stepView(1); return; }
  if (e.key === 'ArrowLeft') { stepView(-1); return; }
  if (e.key === 'Tab') {   // 포커스가 뒤 화면으로 새지 않게 상단 바 안에서만 돈다
    const btns = [...document.querySelectorAll('.lbbar button')];
    if (!btns.length) return;
    const i = btns.indexOf(document.activeElement);
    const next = e.shiftKey ? (i <= 0 ? btns.length - 1 : i - 1) : (i < 0 || i === btns.length - 1 ? 0 : i + 1);
    btns[next].focus(); e.preventDefault();
  }
}
function gateTable(){
  const g=state.gate;
  if(!g) return '<p class=muted style="margin-top:14px">아직 검사 결과가 없습니다.</p>';
  const OWN={'원고':'own-ms','스타일':'own-st','도구':'own-tool'};
  const rows=g.items.map(it=>`<tr>
    <td><span class="pill ${it.ok?'ok':'bad'}">${it.code}</span></td>
    <td>${it.ok?'':`<span class="pill ${OWN[it.owner]||''}">${esc(it.owner)}</span>`}</td>
    <td>${esc(it.what)}${it.ok?'':`<div class=muted>${esc(it.detail||'')}</div>`}</td>
    <td class=muted>${it.ok?'':esc(it.fix)}</td></tr>`).join('');
  return `<p style="margin:14px 0 6px">
    <span class="pill ${g.stale?'idle':(g.pass?'ok':'bad')}">${
      g.stale?'이전 결과(다시 검사 필요)':(g.pass?'통과':'실패')}</span>
    <span class=muted> · ${g.pages}쪽 · 권장 ${g.range[0]}~${g.range[1]}쪽</span></p>
    ${verdict(g)}
    <table><thead><tr><th>검사</th><th>누구 문제</th><th>무엇을 봤나</th><th>실패 시 할 일</th></tr></thead><tbody>${rows}</tbody></table>`;
}
// 실패했을 때 "그래서 내가 뭘 해야 하나"에 한 문단으로 답한다. 이게 없으면 화면이
// 막다른 길이 된다 — 코드만 빨갛게 뜨고, 맡기기를 눌러야 할지 아닌지 알 수 없다.
// 오류 신고 — 보내기 전에 나가는 내용을 통째로 보여준다. GitHub 이슈는 공개라
// 원고 일부가 그대로 공개되기 때문이다. 비공개가 필요하면 메일 쪽을 쓰게 한다.
async function saveReport(){
  const r=await api('/api/report',{name:book});
  if(r.error){ alert(r.error); return; }
  let lb=$('rep');
  if(!lb){
    lb=document.createElement('div'); lb.id='rep'; lb.className='lb';
    lb.onclick=e=>{ if(e.target===lb) closeReport(); };
    lb.setAttribute('role','dialog'); lb.setAttribute('aria-modal','true'); lb.tabIndex=-1;
    document.body.appendChild(lb);
    document.addEventListener('keydown', repKeys);
  }
  lb.innerHTML=`
    <div class=lbbar>
      <b>오류 신고</b>
      <span class=muted>아래 내용이 그대로 전송됩니다</span>
      <span style="flex:1"></span>
      <button onclick="closeReport()">닫기 (Esc)</button>
    </div>
    <div class=repbox>
      <p class=warn><b>GitHub 이슈는 공개입니다.</b> 아래에 원고 일부가 들어 있습니다.
        공개하기 곤란한 원고라면 <b>메일로 보내기</b>를 쓰세요.</p>
      <textarea readonly class=reptext>${esc(r.text)}</textarea>
      <p class=muted>파일로도 저장했습니다: <code>${esc(r.path)}</code></p>
      <div class=repbtns>
        <button class=primary onclick="window.open('${esc(r.issue)}','_blank','noopener')">GitHub 이슈로 신고</button>
        <button onclick="location.href='${esc(r.mail)}'">메일로 보내기 (비공개)</button>
        <button onclick="navigator.clipboard.writeText(document.querySelector('.reptext').value)">내용 복사</button>
      </div>
    </div>`;
  lb.focus();
}
function closeReport(){
  const lb=$('rep');
  if(lb){ lb.remove(); document.removeEventListener('keydown', repKeys); }
}
function repKeys(e){ if(e.key==='Escape') closeReport(); }
function verdict(g){
  if(g.stale || g.pass) return '';
  const a=g.autofix||[], m=g.manual||[], t=g.toolbug||[];
  if(!a.length && !m.length) return '';
  const L=[];
  if(a.length) L.push(`<b>${a.join(', ')}</b> — 「AI에게 게이트 통과까지 맡기기」가 고칠 수 있습니다.`);
  if(m.length) L.push(`<b>${m.join(', ')}</b> — 맡기기로는 안 됩니다. 아래 표의 「할 일」대로 직접 손봐야 합니다.`);
  if(t.length) L.push(`<b>${t.join(', ')}</b> — 이 도구의 결함입니다. 원고를 고쳐도 없어지지 않습니다.`);
  return `<div class="verdict">${L.map(x=>`<p>${x}</p>`).join('')}
    <button onclick="saveReport()">오류 신고</button>
    <span class=muted>보낼 내용을 먼저 보여줍니다. GitHub 이슈(공개) 또는 메일(비공개) 중에 고르세요.</span>
  </div>`;
}
function orow(c,i){
  return `<tr data-i="${i}">
    <td><input value="${esc(c.title||'')}" data-k=title></td>
    <td><input value="${esc(c.summary||'')}" data-k=summary></td>
    <td><input value="${esc(c.toc_line||'')}" data-k=toc_line></td>
    <td><button onclick="delRow(${i})">삭제</button></td></tr>`;
}
function collectOutline(){
  return [...document.querySelectorAll('#otbl tbody tr')].map(tr=>{
    const o={}; tr.querySelectorAll('input').forEach(i=>o[i.dataset.k]=i.value); return o;});
}
function addRow(){ state.outline=collectOutline(); state.outline.push({title:'',summary:'',toc_line:''}); render(); }
function delRow(i){ state.outline=collectOutline(); state.outline.splice(i,1); render(); }
function pickStyle(s){
  // 화면을 다시 그리면 입력 중이던 폴더 이름·제목이 지워진다(실측: 스타일을 고르면 폼이 빔).
  newStyle=s;
  document.querySelectorAll('.styles button').forEach((b,i)=>{
    const on = STYLES[i][0]===s;
    b.classList.toggle('on', on);
    b.setAttribute('aria-pressed', on);
  });
}
function pickChap(c){ chap=c; render(); }   // 편집 내용은 drafts에 남으니 경고가 필요 없다

// 편집 중인 내용은 DOM이 아니라 여기 남는다 — render()가 innerHTML을 통째로 갈아끼우므로
// textarea에만 두면 단계 이동·폴링 완료 때마다 디스크 내용으로 덮어써진다.
const drafts={}, saved={};
function key(path){ return book+'/'+path; }
function dirty(path){
  const k=key(path||chap||'research.md');
  return k in drafts && drafts[k]!==saved[k];
}
function anyDirty(){ return Object.keys(drafts).some(k=>drafts[k]!==saved[k]); }
async function loadFile(path,ta){
  if(!path) return;
  const el=$(ta); if(!el) return;
  const k=key(path);
  if(!(k in saved)){
    const d=await api(`/api/file?name=${book}&path=${encodeURIComponent(path)}`);
    saved[k]=d.text||''; if(!(k in drafts)) drafts[k]=saved[k];
  }
  el.value=drafts[k];
  el.oninput=()=>{ drafts[k]=el.value; };
}
window.addEventListener('beforeunload', e=>{ if(anyDirty()){ e.preventDefault(); e.returnValue=''; } });
async function loadChapter(){ await loadFile(chap,'ta4'); armImagePaste(); }
// 스크린샷을 복사해 원고에 바로 붙여넣기 — 파일 업로드와 같은 경로를 탄다
function armImagePaste(){
  const el=$('ta4'); if(!el) return;
  el.onpaste=e=>{
    const it=[...(e.clipboardData?.items||[])].find(i=>i.type.startsWith('image/'));
    if(!it) return;               // 글자 붙여넣기는 브라우저 기본 동작 그대로
    e.preventDefault();
    const ext=(it.type.split('/')[1]||'png').replace('jpeg','jpg').replace('svg+xml','svg');
    const t=new Date(), z=n=>String(n).padStart(2,'0');
    uploadImage(it.getAsFile(),
      `paste-${t.getFullYear()}${z(t.getMonth()+1)}${z(t.getDate())}-${z(t.getHours())}${z(t.getMinutes())}${z(t.getSeconds())}.${ext}`);
  };
}
async function uploadImage(file,forcedName){
  if(!chap){ $('log').textContent='먼저 왼쪽에서 장을 고르세요.'; return; }
  if(file.size>6*1024*1024){ $('log').textContent='이미지가 6MB를 넘습니다. 줄여서 올리세요.'; return; }
  const b64=await new Promise((ok,no)=>{ const r=new FileReader();
    r.onload=()=>ok(r.result.split(',')[1]); r.onerror=no; r.readAsDataURL(file); });
  const r=await api('/api/upload',{name:book,filename:forcedName||file.name,data:b64});
  if(r.error){ $('log').textContent='이미지 업로드 실패: '+r.error; return; }
  insertAtCursor('ta4', `\n\n![캡션을 쓰세요](${r.url} "출처: ")\n\n`);
  $('log').textContent=`이미지 저장됨: ${r.url} — 캡션·출처를 채우고 「직접 고친 내용 저장」을 누르세요.`;
}
function insertAtCursor(ta,text){
  const el=$(ta); if(!el) return;
  const a=el.selectionStart??el.value.length, b=el.selectionEnd??a;
  el.value=el.value.slice(0,a)+text+el.value.slice(b);
  el.selectionStart=el.selectionEnd=a+text.length;
  drafts[key(chap)]=el.value;    // 재렌더에도 살아남게 초안에 기록
  el.focus();
}
async function saveFile(path,ta){
  if(!path){ $('log').textContent='저장할 파일이 없습니다'; return; }
  const el=$(ta);
  const r=await api('/api/file',{name:book,path,text:el.value});
  $('log').textContent=r.ok?('저장됨: '+path):('실패: '+r.error);
  if(r.ok){ const k=key(path); saved[k]=el.value; drafts[k]=el.value; open_(book); }
}
async function saveOutline(){
  const r=await api('/api/outline',{name:book,chapters:collectOutline()});
  $('log').textContent=r.error||r.out;
  if(!r.error){ await open_(book); go(4); }
}
async function create(){
  const r=await api('/api/new',{name:$('nname').value,title:$('ntitle').value,subtitle:$('nsub').value,
    author:$('nauthor').value,length:$('nlen').value,style:newStyle});
  $('log').textContent=r.out||r.error;
  if(!r.error && r.code===0){ await boot(); await open_($('nname').value); go(2); }
}
function lockPanel(on){
  document.querySelectorAll('#panel button, .steps button').forEach(b=>b.disabled=on);
}
async function run(cmd){
  if(!book){ $('log').textContent='먼저 책을 고르세요'; return; }
  $('log').textContent='실행 중…'; lockPanel(true);
  const r=await api('/api/run',{name:book,cmd}).finally(()=>lockPanel(false));
  await open_(book);
  const [msg]=nextAction();
  $('log').textContent=(r.out||r.error)+'\n\n▶ 다음: '+msg;
  if(cmd==='sheet') go(6); else render();
}
async function agent(task,target){
  if(!book){ $('log').textContent='먼저 책을 고르세요'; return; }
  // AI 집필은 기존 원고를 통째로 갈아엎는다 — 되돌릴 방법이 UI에 없으므로 먼저 묻는다
  const sizes=state.sizes||{};
  const written=Object.entries(sizes).filter(([f,n])=>n>400);
  if((task==='all'||task==='auto') && written.length &&
     !confirm(`이미 쓴 장이 ${written.length}개 있습니다. AI가 전부 새로 씁니다(기존 원고는 사라집니다). 계속할까요?`)) return;
  if(task==='chapter' && (sizes[target]||0)>400 &&
     !confirm(`${target.replace('chapters/','')}에 이미 원고가 있습니다(${sizes[target]}자). 새로 씁니다. 계속할까요?`)) return;
  const r=await api('/api/agent',{name:book,task,target,
    web:$('useweb').checked, max_queries:+$('maxq').value||6});
  if(r.error){ $('log').textContent=r.error; return; }
  $('log').textContent='AI 작업 시작 — 창을 닫지 마세요…';
  poll();
}
let polling=false, pollFails=0;
function elapsed(sec){
  if(!sec) return '';
  const m=Math.floor(sec/60), s=Math.floor(sec%60);
  return m? `${m}분 ${s}초 경과` : `${s}초 경과`;
}
async function poll(){
  if(polling) return; polling=true; pollFails=0;
  const tick=async()=>{
    const j=await api('/api/job');
    if(j.error){                       // 서버가 잠깐 안 붙어도 폴링을 끊지 않는다
      pollFails++;
      $('log').textContent=`서버 응답 없음 (${pollFails}회). 작업은 서버에서 계속되고 있을 수 있습니다.\n${j.error}`;
      if(pollFails<20){ setTimeout(tick,3000); return; }
      polling=false; return;
    }
    pollFails=0;
    if(j.running){
      const sec=j.started? (Date.now()/1000 - j.started):0;
      $('log').textContent=`작업 중 — ${j.name} / ${j.task} · ${elapsed(sec)}\n`
        + '중간에 멈추려면 서버를 띄운 터미널에서 Ctrl+C 하세요.\n\n'+(j.log||'');
      setTimeout(tick,2000); return;
    }
    polling=false;
    if(j.name && j.name!==book) book=j.name;   // 작업 중 다른 책을 눌렀어도 결과는 그 책 것이다
    if(book) await open_(book);
    const head = j.ok===false ? '✖ 실패했습니다. 아래 마지막 줄이 원인입니다.\n\n'
                              : '';
    const tail = j.ok===false ? '' : (state? '\n\n▶ 다음: '+nextAction()[0] : '');
    $('log').textContent=head+(j.log||'')+tail;
  };
  tick();
}
async function loadFonts(){
  const lang=$('flang').value;
  const d=await api('/api/fonts?lang='+lang);
  $('ffam').innerHTML=(d.fonts||[]).map(f=>
    `<option value="${esc(f.family)}">${esc(f.family)} (${f.format})</option>`).join('')
    || '<option value="">쓸 수 있는 폰트 없음</option>';
  // 지금 책(없으면 기본값)에 지정된 폰트를 드롭다운에 되살린다 —
  // 이게 없으면 재시작 때마다 설정이 날아간 것처럼 보인다
  const cur=(state&&state.fonts&&state.fonts[lang]) || (defaults[lang]||'');
  if(cur) $('ffam').value=cur;
}
let defaults={};
async function loadDefaults(){
  const s=await api('/api/settings');
  defaults=(s&&s.default_fonts)||{};
  const txt=Object.entries(defaults).map(([k,v])=>`${k}: ${v}`).join(' · ');
  $('deffonts').textContent = txt ? ('새 책 기본값 — '+txt) : '기본값 없음 (새 책은 동봉 폰트)';
}
async function saveDefaults(){
  const d={...defaults, [$('flang').value]: $('ffam').value};
  const r=await api('/api/settings',{default_fonts:d});
  if(r.error){ $('log').textContent=r.error; return; }
  await loadDefaults();
  $('log').textContent='기본 폰트 저장 — 앞으로 만드는 책에 자동으로 적용됩니다';
}
async function setFont(){
  if(!book){ $('log').textContent='먼저 책을 고르세요'; return; }
  const r=await api('/api/font',{name:book,lang:$('flang').value,family:$('ffam').value});
  $('log').textContent=(r.out||r.error)
    + '\n\n⚠ 이 서체는 PDF에 파일로 박혀 배포됩니다. 판매·인쇄 배포 전에 라이선스를 확인하세요.';
  open_(book);
}
async function clearFont(){
  if(!book) return;
  const r=await api('/api/font',{name:book,clear:true});
  $('log').textContent=r.out||r.error; open_(book);
}
boot(); render(); loadDefaults().then(loadFonts);
api('/api/job').then(j=>{ if(j.running){ if(j.name) open_(j.name); poll(); } });
</script>
"""

_FONTS = {}
# 자동 집필은 몇 분씩 걸린다 — 한 번에 하나만, 진행 상황은 폴링으로 본다.
JOB = {"running": False, "name": "", "task": "", "log": "", "done": True,
       "ok": True, "started": 0.0}
import threading  # noqa: E402
JOB_LOCK = threading.Lock()   # 확인과 갱신 사이에 다른 요청이 끼어들지 못하게


def start_job(name: str, task: str, target: str | None,
              web: bool = False, max_queries: int = 6):
    """agent.py를 별도 스레드에서 돌린다. 서버는 응답을 막지 않는다."""
    with JOB_LOCK:
        if JOB["running"]:
            raise ValueError(f"이미 작업 중입니다: {JOB['name']} / {JOB['task']}")
        JOB["running"] = True
    d = book_dir(name)
    if task not in ("research", "outline", "chapter", "all", "diagrams", "fix", "auto"):
        raise ValueError("unknown task")
    argv = [sys.executable, str(SKILL / "scripts/agent.py"), task, str(d)]
    if web and task in ("research", "auto"):
        import datetime
        argv += ["--web", "--max-queries", str(max(1, min(12, int(max_queries)))),
                 "--today", datetime.date.today().isoformat()]
    if task == "chapter":
        if not CHAPTER_RE.fullmatch((target or "").replace("chapters/", "")):
            raise ValueError("bad chapter file")
        argv.append(target.replace("chapters/", ""))
    import time
    JOB.update({"name": name, "task": task, "log": "시작…", "done": False,
                "ok": True, "started": time.time()})

    def run():
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=7200)
            JOB["log"] = (p.stdout + p.stderr).strip()[-4000:] or "(출력 없음)"
            JOB["ok"] = p.returncode == 0
        except Exception as e:  # 타임아웃·실행 실패도 화면에 남긴다
            JOB["log"] = f"실패: {e}"
            JOB["ok"] = False
        finally:
            JOB.update({"running": False, "done": True})

    threading.Thread(target=run, daemon=True).start()
    return {"ok": True}


def _font_cache() -> dict:
    """폰트 스캔은 수백 개 파일을 읽는다 — 프로세스 수명 동안 한 번만."""
    if not _FONTS:
        _FONTS.update(fontpick.scan())
    return _FONTS


def settings_path() -> Path:
    return books_root() / ".bookforge.json"


def load_settings() -> dict:
    p = settings_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(data: dict) -> dict:
    """새 책에 물려줄 기본값 — 폰트를 매번 다시 고르지 않게 앱 수준에 한 번만 저장한다."""
    cur = load_settings()
    fonts = {k: v for k, v in (data.get("default_fonts") or {}).items()
             if k in fontpick.SAMPLES and isinstance(v, str) and v.strip()}
    cur["default_fonts"] = fonts
    settings_path().write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return cur


def books_root() -> Path:
    return ROOT


def under_root(p: Path) -> Path:
    """books 루트 밖을 가리키면 거부한다 — 이름 검사만으로는 심볼릭 링크를 못 막는다."""
    rp = p.resolve()
    if not rp.is_relative_to(books_root().resolve()):
        raise ValueError("경로가 books 폴더 밖을 가리킵니다")
    return rp


def book_dir(name: str) -> Path:
    if not NAME_RE.fullmatch(name or ""):
        raise ValueError("bad book name")
    d = books_root() / name
    if not (d / "book.json").exists():
        raise ValueError("no such book")
    under_root(d)
    return d



# 업로드 허용 형식과 매직 바이트 — 확장자만 믿으면 아무 파일이나 assets/에 들어온다.
IMAGE_TYPES = {
    "png": lambda b: b[:8] == b"\x89PNG\r\n\x1a\n",
    "jpg": lambda b: b[:2] == b"\xff\xd8",
    "jpeg": lambda b: b[:2] == b"\xff\xd8",
    "webp": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
    "svg": lambda b: b"<svg" in b[:4096],
}


def save_upload(name: str, filename: str, data_b64: str) -> dict:
    """이미지를 책의 assets/에 저장하고 원고에 쓸 상대 링크를 돌려준다."""
    import base64
    import binascii
    import re as _re
    d = book_dir(name)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in IMAGE_TYPES:
        return {"error": "png·jpg·webp·svg만 올릴 수 있습니다"}
    try:
        blob = base64.b64decode(data_b64, validate=True)
    except (binascii.Error, ValueError):
        return {"error": "이미지 데이터를 읽지 못했습니다"}
    if not blob or len(blob) > 6 * 1024 * 1024:
        return {"error": "이미지는 6MB까지입니다"}
    if not IMAGE_TYPES[ext](blob):
        return {"error": f"파일 내용이 .{ext} 형식이 아닙니다"}
    # 파일명은 조판 소스(Typst·HTML)에 그대로 박히므로 안전한 문자만 남긴다
    stem = _re.sub(r"[^\w가-힣-]", "-", filename.rsplit(".", 1)[0]).strip("-") or "img"
    assets = d / "assets"
    assets.mkdir(exist_ok=True)
    out, n = assets / f"{stem}.{ext}", 2
    while out.exists():           # 같은 이름이 있으면 덮어쓰지 않는다
        out, n = assets / f"{stem}-{n}.{ext}", n + 1
    under_root(out)
    out.write_bytes(blob)
    return {"url": f"../assets/{out.name}"}


def safe_file(name: str, rel: str) -> Path:
    """편집 허용 대상은 book.json · outline.json · research.md · chapters/ch-NN.md 뿐."""
    d = book_dir(name)
    rel = (rel or "").replace("\\", "/")
    if rel in EDITABLE:
        return under_root(d / rel)
    if rel.startswith("chapters/") and CHAPTER_RE.fullmatch(rel.split("/", 1)[1]):
        return under_root(d / rel)
    raise ValueError("path not allowed: " + rel)


def gate_summary(d: Path) -> dict | None:
    report = d / "gate-report.json"
    if not report.exists():
        return None
    g = json.loads(report.read_text())
    items = []
    for code, val in (g.get("gates") or {}).items():
        if not isinstance(val, dict):
            continue
        what, fix, owner, auto = gate_lookup(code)
        detail = ""
        for key in ("problems", "overflows", "mismatches", "violations", "stretched",
                    "not_embedded", "type3_pages", "blank_pages", "parity_filler", "tails"):
            v = val.get(key)
            if v:
                detail = str(v)[:160]
                break
        if not detail and val.get("ok") is False:
            detail = str({k: v for k, v in val.items() if k != "ok"})[:160]
        items.append({"code": code, "ok": bool(val.get("ok", True)),
                      "what": what, "fix": fix, "owner": owner, "auto": auto,
                      "detail": detail})
    items.sort(key=lambda x: (x["ok"], x["code"]))
    g1 = (g.get("gates") or {}).get("G1", {})
    fails = [i for i in items if not i["ok"]]
    return {"pass": bool(g.get("pass")), "pages": g1.get("pages"),
            "range": g1.get("range") or [0, 0], "items": items,
            # 화면이 "맡기기를 눌러도 되는가"에 답하려면 실패 코드의 성격이 필요하다
            "autofix": [i["code"] for i in fails if i["auto"]],
            "manual": [i["code"] for i in fails if not i["auto"]],
            "toolbug": [i["code"] for i in fails if i["owner"] == TOOL]}



def server_version() -> str:
    """이 서버가 실행 중인 코드의 버전. 커밋 해시·날짜가 1순위, git이 없으면 파일 수정시각.

    "재시작했는데 왜 안 바뀌지?"를 화면에서 바로 판별하기 위한 것 — 화면의 버전과
    `git log -1 --format=%h`가 다르면 옛 코드가 떠 있는 것이다.
    """
    import datetime
    import subprocess as sp
    try:
        r = sp.run(["git", "-C", str(SKILL), "log", "-1", "--format=%h %cs"],
                   capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    ts = datetime.datetime.fromtimestamp(pathlib_mtime := Path(__file__).stat().st_mtime)
    return "커밋 불명 · 파일 " + ts.strftime("%Y-%m-%d %H:%M")


VERSION = None  # main()에서 채운다 — import 시점의 git 호출을 피한다


def failed_codes(d: Path) -> list[str]:
    report = json.loads((d / "gate-report.json").read_text())
    return sorted(c for c, v in (report.get("gates") or {}).items()
                  if isinstance(v, dict) and v.get("ok") is False)


def failure_report(d: Path) -> Path:
    """재현에 필요한 것만 파일 하나로 묶는다 — 원고 전문은 넣지 않는다.

    화면이 "개발자에게 이걸 주세요"라고 말하려면 그 '이것'이 실재해야 한다.
    실패한 게이트의 판정 근거, 스타일, 도구 버전, 그리고 지목된 원고의 해당 부분만.
    """
    import platform
    import shutil as _sh
    import subprocess as _sp

    report = json.loads((d / "gate-report.json").read_text())
    book = json.loads((d / "book.json").read_text())
    fails = [(c, v) for c, v in (report.get("gates") or {}).items()
             if isinstance(v, dict) and v.get("ok") is False]

    def ver(exe, *args):
        path = _sh.which(exe)
        if not path:
            return "없음"
        try:
            r = _sp.run([path, *args], capture_output=True, text=True, timeout=20)
            return (r.stdout or r.stderr).strip().splitlines()[0][:60]
        except Exception:
            return "확인 실패"

    L = [f"# 실패 정보 — {book.get('title') or d.name}", ""]
    L.append(f"- 스타일: `{book.get('style')}`")
    pages = (report.get("gates") or {}).get("G1", {}).get("pages")
    # 렌더 전 게이트(G0·G10·G15-PARA)에서 떨어지면 G1이 아예 없다 — None을 그대로 찍지 않는다
    L.append(f"- 쪽수: {pages if pages else '렌더 전 단계에서 중단'}")
    L.append(f"- 폰트 지정: `{json.dumps(book.get('fonts') or {}, ensure_ascii=False)}`")
    L.append("")
    L.append("## 실패한 검사")
    L.append("")
    L.append("| 코드 | 누구 문제 | 자동수정 | 판정 근거 |")
    L.append("|---|---|---|---|")
    for code, val in fails:
        _, _, own, auto = gate_lookup(code)
        detail = json.dumps({k: v for k, v in val.items() if k != "ok"},
                            ensure_ascii=False)[:300].replace("|", "\\|")
        L.append(f"| {code} | {own} | {'가능' if auto else '불가'} | `{detail}` |")
    L.append("")

    # 게이트가 원고를 지목했다면 그 부분만 옮긴다 (전문 유출 방지)
    quoted = []
    for code, val in fails:
        for prob in (val.get("problems") or [])[:5]:
            m = re.search(r"(ch-\d+\.md)", str(prob))
            if not m:
                continue
            f = d / "chapters" / m.group(1)
            if not f.exists():
                continue
            # 게이트 메시지의 따옴표 안 토큰을 원고에서 찾아 그 언저리만 뜬다.
            # 못 찾으면 장 첫머리를 뜨는데, 그건 지목된 자리가 아니라 도움이 안 된다.
            body = f.read_text(encoding="utf-8")
            i = -1
            for token in re.findall(r"'([^']{2,40}?)…?'", str(prob)):
                i = body.find(token)
                if i >= 0:
                    break
            excerpt = body[max(0, i - 120):i + 400] if i >= 0 else body[:400]
            quoted.append((code, m.group(1), excerpt.strip()))
    if quoted:
        L.append("## 지목된 원고 부분")
        L.append("")
        for code, name, excerpt in quoted[:5]:
            L.append(f"**{code} — `{name}`**")
            L.append("")
            L.append("```")
            L.append(excerpt)
            L.append("```")
            L.append("")

    L.append("## 환경")
    L.append("")
    L.append(f"- OS: {platform.platform()}")
    L.append(f"- Python: {platform.python_version()}")
    L.append(f"- Typst: {ver('typst', '--version')}")
    L.append(f"- Node: {ver('node', '--version')}")
    L.append(f"- claude: {ver('claude', '--version')}")
    L.append("")
    L.append("이 파일에는 원고 전문이 들어 있지 않습니다. 게이트가 지목한 부분만 옮겼습니다.")

    out = d / "failure-report.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out


def page_map(d: Path, outline: list) -> dict:
    """쪽번호 → 그 쪽이 속한 원고 파일. 검수에서 '이 쪽은 어디서 고치나'에 답하려면 필요하다."""
    pdf = next(iter(sorted((d / "final").glob("*.pdf"))), d / "draft" / "book.pdf")
    if not pdf.exists():
        return {}
    try:
        import pymupdf
        doc = pymupdf.open(pdf)
        titles = {c["title"]: c["file"] for c in outline}
        starts = sorted((t[2], titles[t[1]]) for t in doc.get_toc()
                        if t[0] == 1 and t[1] in titles)
        total = doc.page_count
        doc.close()
    except Exception:
        return {}
    out, cur = {}, None
    for pg in range(1, total + 1):
        for s, f in starts:
            if s <= pg:
                cur = f
        out[str(pg)] = cur if (starts and pg >= starts[0][0]) else "front"
    return out


def state(name: str) -> dict:
    d = book_dir(name)
    book = json.loads((d / "book.json").read_text())
    outline = []
    op = d / "outline.json"
    if op.exists():
        outline = json.loads(op.read_text()).get("chapters", [])
    real = [c for c in outline if c.get("title") and "장 제목" not in c["title"]]
    chapters = sorted("chapters/" + p.name for p in (d / "chapters").glob("ch-*.md"))
    written = [c for c in chapters if len((d / c).read_text().strip()) > 400]
    research = d / "research.md"
    shot_files = sorted((d / "qc").glob("p*.png"))
    shots = [p.name for p in shot_files]
    sheet_ts = int(max((p.stat().st_mtime for p in shot_files), default=0))
    gate = gate_summary(d)
    pmap = page_map(d, outline)
    # 빌드를 다시 하면 build.py가 final/을 지운다 — 그때 남아 있는 이전 게이트 결과는
    # 지금 원고의 결과가 아니다. 검사 리포트가 draft보다 오래됐으면 '검사 필요'로 되돌린다.
    draft = d / "draft" / "book.pdf"
    report = d / "gate-report.json"
    stale = (draft.exists() and report.exists()
             and report.stat().st_mtime < draft.stat().st_mtime)
    final_pdf = next(iter((d / "final").glob("*.pdf")), None)
    if gate:
        gate["stale"] = bool(stale) or final_pdf is None
    return {
        "book": book,
        "outline": outline,
        "chapters": chapters,
        "sizes": {c: len((d / c).read_text().strip()) for c in chapters},
        "shots": shots,
        "sheet_ts": sheet_ts,
        "pagemap": pmap,
        "pages": len(pmap),
        "gate": gate,
        "fonts": {k: v["family"] for k, v in (book.get("fonts") or {}).items()},
        "steps": {
            "research": research.exists() and len(research.read_text().strip()) > 40,
            "outline": len(real) > 0,
            "written": bool(chapters) and len(written) == len(chapters),
            "built": (d / "draft" / "book.pdf").exists(),
            "passed": bool(gate and gate["pass"] and not gate["stale"]),
            "reviewed": bool(shots),
        },
    }


def save_outline(name: str, chapters: list) -> dict:
    d = book_dir(name)
    rows, made = [], []
    for i, c in enumerate([c for c in chapters if (c.get("title") or "").strip()], 1):
        title = c["title"].strip()
        f = f"ch-{i:02d}.md"
        rows.append({"file": f, "title": title,
                     "summary": (c.get("summary") or "").strip(),
                     "toc_line": (c.get("toc_line") or "").strip()})
        p = d / "chapters" / f
        if not p.exists():
            p.write_text(f"# {title}\n\n", encoding="utf-8")
            made.append(f)
    (d / "outline.json").write_text(json.dumps({"chapters": rows}, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    return {"out": f"목차 {len(rows)}장 저장" + (f" · 새 원고 {len(made)}개 생성" if made else "")}


def run_script(name: str, cmd: str) -> dict:
    d = book_dir(name)
    with JOB_LOCK:   # 같은 책에 빌드가 두 개 붙으면 같은 PDF를 동시에 쓴다
        if JOB["running"]:
            raise ValueError(f"이미 작업 중입니다: {JOB['name']} / {JOB['task']}")
        JOB.update({"running": True, "name": name, "task": cmd, "log": "실행 중…",
                    "done": False, "ok": True})
    if cmd == "build":
        argv = [sys.executable, str(SKILL / "scripts/build.py"), str(d)]
    elif cmd == "qc":
        argv = [sys.executable, str(SKILL / "scripts/qc_gate.py"), str(d)]
    elif cmd == "sheet":
        pdf = next(iter(sorted((d / "final").glob("*.pdf"))), d / "draft/book.pdf")
        for old in (d / "qc").glob("p*.png"):
            old.unlink()  # 쪽수가 줄면 옛 이미지가 남아 검수 화면이 어긋난다
        argv = [sys.executable, str(SKILL / "scripts/contact_sheet.py"), str(pdf),
                str(d / "qc"), "--dpi", "80"]  # --pages 없으면 전 지면
    else:
        raise ValueError("unknown cmd")
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=1800)
    finally:
        JOB.update({"running": False, "done": True})
    JOB["ok"] = p.returncode == 0
    return {"out": (p.stdout + p.stderr).strip() or "(출력 없음)", "code": p.returncode}


def scaffold(data: dict) -> dict:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("폴더 이름을 입력하세요 (제목이 아니라 파일용 영문 이름입니다)")
    if not NAME_RE.fullmatch(name):
        raise ValueError(f"폴더 이름 '{name}'은 쓸 수 없습니다 — 영문·숫자·-·_ 만 됩니다"
                         " (제목에는 한글·일본어를 자유롭게 쓰세요)")
    if data.get("style") not in STYLES:
        raise ValueError("bad style")
    length = data.get("length") or "short"
    if length not in LENGTHS:
        raise ValueError("bad length")
    argv = [sys.executable, str(SKILL / "scripts/scaffold.py"), str(books_root() / name),
            "--style", data["style"], "--title", (data.get("title") or name), "--length", length]
    if (data.get("subtitle") or "").strip():
        argv += ["--subtitle", data["subtitle"].strip()]
    if (data.get("author") or "").strip():
        argv += ["--author", data["author"].strip()]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    out = (p.stdout + p.stderr).strip()
    if p.returncode == 0:
        # 기본 폰트 물려주기 — 실패해도 책 생성 자체는 살린다(스타일에 따라 거부될 수 있다)
        for lang, family in (load_settings().get("default_fonts") or {}).items():
            r = subprocess.run([sys.executable, str(SKILL / "scripts/fontpick.py"), "set",
                                str(books_root() / name), f"--{lang}", family],
                               capture_output=True, text=True, timeout=300)
            out += "\n" + (r.stdout + r.stderr).strip().splitlines()[-1]
    return {"out": out, "code": p.returncode}


class Handler(http.server.BaseHTTPRequestHandler):
    timeout = 30          # 본문을 안 보내고 붙잡는 연결이 스레드를 영구 점유하지 않게
    MAX_BODY = 8 * 1024 * 1024

    def _local_only(self) -> bool:
        """브라우저가 연 다른 사이트가 이 서버를 조작하거나 읽지 못하게 막는다.

        - Origin: 다른 출처의 fetch(POST)는 응답을 못 읽어도 부작용은 일어난다(CSRF).
        - Host: 공격자 도메인이 127.0.0.1로 재바인딩되면 same-origin이 되어 원고를 읽을 수 있다.
        """
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        host = (self.headers.get("Host") or "").strip()
        if host and host not in allowed:
            return False
        origin = (self.headers.get("Origin") or "").strip()
        if origin:
            netloc = urllib.parse.urlparse(origin).netloc
            if netloc not in allowed:
                return False
        return True

    def _send(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_pdf(self, pdf: Path, d: Path, is_final: bool):
        """내려받을 때 이름이 정해지도록 Content-Disposition을 붙인다.

        형식: `제목_발행연월.pdf` (게이트 통과 전이면 `_draft`). 브라우저 PDF 뷰어가
        이 이름을 그대로 저장 이름으로 쓴다. 한글 제목은 RFC 5987(filename*)로 주고,
        그걸 못 읽는 옛 브라우저용 ASCII 대체 이름은 폴더명으로 준다.
        """
        book = json.loads((d / "book.json").read_text())
        title = re.sub(r'[\\/:*?"<>|]+', " ", str(book.get("title") or d.name))
        title = re.sub(r"\s+", " ", title).strip() or d.name
        stamp = str(book.get("date") or "").strip()
        name = f"{title}_{stamp}" if stamp else title
        if not is_final:
            name += "_draft"
        ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", d.name) + ".pdf"
        quoted = urllib.parse.quote(name + ".pdf")
        body = pdf.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition",
                         "inline; filename=\"%s\"; filename*=UTF-8''%s" % (ascii_name, quoted))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, "application/json; charset=utf-8",
                   json.dumps(obj, ensure_ascii=False).encode())

    def do_GET(self):
        if not self._local_only():
            return self._send(403, "text/plain; charset=utf-8",
                              "이 서버는 이 컴퓨터에서만 씁니다".encode())
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        one = lambda k: (q.get(k) or [""])[0]
        try:
            if u.path == "/":
                styles = [[k, ko, desc] for k, (ko, desc) in STYLE_KO.items()]
                page = (PAGE.replace("%STYLES%", json.dumps(styles, ensure_ascii=False))
                            .replace("%LENGTHS%", json.dumps(LENGTHS, ensure_ascii=False))
                            .replace("%VERSION%", VERSION or server_version()))
                return self._send(200, "text/html; charset=utf-8", page.encode())
            if u.path == "/api/settings":
                return self._json(load_settings())
            if u.path == "/api/books":
                names = sorted(p.parent.name for p in books_root().glob("*/book.json"))
                return self._json({"books": names})
            if u.path == "/api/job":
                return self._json(JOB)
            if u.path == "/api/state":
                return self._json(state(one("name")))
            if u.path == "/api/file":
                p = safe_file(one("name"), one("path"))
                return self._json({"text": p.read_text() if p.exists() else ""})
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
                final = next(iter(sorted((d / "final").glob("*.pdf"))), None)
                pdf = final or (d / "draft/book.pdf")
                if not pdf.exists():
                    return self._send(404, "text/plain; charset=utf-8", "아직 빌드 전".encode())
                return self._send_pdf(pdf, d, final is not None)
            if u.path == "/sample":
                style, kind = one("style"), one("kind") or "cover"
                if style not in SAMPLES:
                    raise ValueError("bad style")
                fn = SAMPLES[style][0 if kind == "cover" else 1]
                img = SKILL / "examples" / "showcase" / fn
                if not img.exists():
                    return self._send(404, "text/plain", b"no sample")
                body = img.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "max-age=86400")  # 견본은 안 바뀐다
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            if u.path == "/page":
                # 크게 보기용 — 썸네일(80dpi)을 확대하면 뭉개진다. 볼 때만 그 쪽을 다시 뜬다.
                d = book_dir(one("name"))
                pdf = next(iter(sorted((d / "final").glob("*.pdf"))), d / "draft/book.pdf")
                if not pdf.exists():
                    return self._send(404, "text/plain", b"no pdf")
                try:
                    n = int(one("n") or 1)
                    dpi = max(60, min(220, int(one("dpi") or 150)))
                except ValueError:
                    raise ValueError("bad page")
                import pymupdf
                doc = pymupdf.open(pdf)
                if not 1 <= n <= doc.page_count:
                    doc.close()
                    raise ValueError("page out of range")
                png = doc[n - 1].get_pixmap(dpi=dpi).tobytes("png")
                doc.close()
                return self._send(200, "image/png", png)
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
        if not self._local_only():
            return self._send(403, "text/plain; charset=utf-8",
                              "이 서버는 이 컴퓨터에서만 씁니다".encode())
        u = urllib.parse.urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > self.MAX_BODY:
                return self._send(413, "text/plain; charset=utf-8", "본문이 너무 큽니다".encode())
            data = json.loads(self.rfile.read(n) or b"{}")
            if u.path == "/api/file":
                safe_file(data["name"], data["path"]).write_text(data["text"])
                return self._json({"ok": True})
            if u.path == "/api/upload":
                return self._json(save_upload(data["name"], data.get("filename") or "",
                                              data.get("data") or ""))
            if u.path == "/api/settings":
                return self._json(save_settings(data))
            if u.path == "/api/report":
                d = book_dir(data["name"])
                if not (d / "gate-report.json").exists():
                    return self._json({"error": "검사 결과가 없습니다. 먼저 ② 게이트를 누르세요."})
                path = failure_report(d)
                text = path.read_text(encoding="utf-8")
                codes = ", ".join(failed_codes(d)) or "게이트 실패"
                title = f"[{codes}] {json.loads((d / 'book.json').read_text()).get('style')} 스타일에서 실패"
                body = text if len(text) <= URL_BODY_MAX else (
                    text[:URL_BODY_MAX] + "\n\n(이하 생략 — failure-report.md 파일을 첨부해 주세요)")
                q = urllib.parse.urlencode({"title": title, "body": body})
                return self._json({
                    "path": str(path), "text": text, "title": title,
                    "issue": f"https://github.com/{REPORT_REPO}/issues/new?{q}",
                    "mail": "mailto:" + REPORT_MAIL + "?" + urllib.parse.urlencode(
                        {"subject": title, "body": body}),
                })
            if u.path == "/api/meta":
                d = book_dir(data["name"])
                book = json.loads((d / "book.json").read_text())
                for k in ("title", "subtitle", "author", "publisher", "date", "brand",
                          "typesetter", "series", "series_no"):
                    if k in data:
                        v = (data[k] or "").strip()
                        if k == "brand" and v and not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
                            raise ValueError("브랜드색은 #rrggbb 형식이어야 합니다")
                        # typesetter·publisher는 빈 값 자체가 뜻을 갖는다 — "그 줄을 빼라".
                        # 지워버리면 Typst 기본값 "bookforge"가 되살아나 비우기가 동작하지 않는다.
                        if v or k in ("typesetter", "publisher", "series", "series_no"):
                            book[k] = v
                        else:
                            book.pop(k, None)
                (d / "book.json").write_text(json.dumps(book, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
                return self._json({"out": "책 정보 저장 — 표지·판권면에 반영하려면 다시 빌드하세요"})
            if u.path == "/api/outline":
                return self._json(save_outline(data["name"], data.get("chapters") or []))
            if u.path == "/api/run":
                return self._json(run_script(data["name"], data["cmd"]))
            if u.path == "/api/agent":
                return self._json(start_job(data["name"], data["task"], data.get("target"),
                                            bool(data.get("web")), data.get("max_queries") or 6))
            if u.path == "/api/new":
                return self._json(scaffold(data))
            if u.path == "/api/font":
                d = book_dir(data["name"])
                argv = [sys.executable, str(SKILL / "scripts/fontpick.py"), "set", str(d)]
                if not data.get("clear") and data.get("lang") not in fontpick.SAMPLES:
                    raise ValueError("bad lang")
                argv += ["--clear"] if data.get("clear") else [f"--{data['lang']}", data["family"]]
                p = subprocess.run(argv, capture_output=True, text=True, timeout=300)
                return self._json({"out": (p.stdout + p.stderr).strip(), "code": p.returncode})
            self._send(404, "text/plain", b"not found")
        except Exception as e:
            self._json({"error": str(e)}, 400)

    def log_message(self, *a):
        pass


def demo():
    """경로 가드·단계 계산 자체 점검."""
    global ROOT
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ROOT = Path(tmp)
        d = ROOT / "demo"
        (d / "chapters").mkdir(parents=True)
        (d / "qc").mkdir()
        (d / "book.json").write_text('{"title":"t","style":"practical"}')
        assert safe_file("demo", "chapters/ch-01.md").name == "ch-01.md"
        assert safe_file("demo", "research.md").name == "research.md"
        for bad in ("../../etc/passwd", "chapters/../book.json", "chapters/x.md",
                    "final/x.pdf", "gate-report.json", ""):
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
        s = state("demo")
        assert s["steps"] == {"research": False, "outline": False, "written": False,
                              "built": False, "passed": False, "reviewed": False}, s["steps"]
        save_outline("demo", [{"title": "1장", "summary": "요약"}, {"title": "  "}])
        assert (d / "chapters" / "ch-01.md").exists()
        assert not (d / "chapters" / "ch-02.md").exists(), "제목 없는 행은 장이 되면 안 된다"
        assert state("demo")["steps"]["outline"] is True
        assert state("demo")["steps"]["written"] is False, "빈 원고는 집필 완료가 아니다"
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
    global VERSION
    VERSION = server_version()
    print(f"bookforge web UI → http://127.0.0.1:{a.port}  (books: {ROOT})")
    print(f"서버 버전: {VERSION}")
    http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
