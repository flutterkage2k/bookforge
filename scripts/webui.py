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
ROOT = Path("books")

# 게이트 코드 → (무엇을 봤는가, 떨어졌을 때 할 일). qc_gate.py의 판정 기준을 사람 말로 옮긴 것.
GATE_HELP = {
    "G0": ("도해 SVG 원본 검사", "도해 파일에 외부 링크·빈 텍스트가 없는지 확인하세요."),
    "G1": ("렌더 성공·판형·분량", "쪽수가 범위를 벗어나면 경고만 납니다. 원고를 늘리거나 줄이세요."),
    "G2": ("폰트 임베드·Type3 0건", "otf 폰트가 원인입니다. ttf로 바꾸세요(scripts/convert_fonts.py)."),
    "G3": ("글자가 판면 밖으로 나갔는지", "표가 너무 넓거나 긴 단어가 원인입니다. 줄이세요."),
    "G4": ("목차·북마크가 실제 쪽과 맞는지", "빌드를 다시 하세요. 계속 어긋나면 목차 제목과 장 제목을 맞추세요."),
    "G7-TAIL": ("장 마지막 면이 너무 비었는지", "그 장 본문을 3~5줄 단위로 늘리거나 줄이세요."),
    "G7-MID": ("장 중간 면이 비었는지", "표·콜아웃이 다음 면으로 밀려 생긴 구멍입니다. 앞 문단을 조절하세요."),
    "G7-DOC": ("책 전체 꼬리 면 평균", "여러 장의 끝 면이 얕습니다. 장별 분량을 다시 설계하세요."),
    "G7-FRAME": ("판면 좌표 드리프트", "본문 첫 요소가 이미지면 문단을 먼저 두세요."),
    "G7-BLANK": ("의도치 않은 빈 면", "빈 면을 만든 블록을 앞뒤로 옮기세요."),
    "G8": ("여백으로 억지로 채웠는지", "짧은 불릿·잦은 소제목이 원인입니다. 문장으로 합치거나 절을 병합하세요."),
    "G9": ("면 끝 제목 고립·widow", "제목이 면 끝에 홀로 남았습니다. 앞 문단을 늘려 밀어내세요."),
    "G10": ("콜아웃 수치가 본문에 실재하는지", "박스에만 있는 숫자는 금지입니다. 본문에도 그 수치를 쓰세요."),
    "G11": ("여백 사유 코드 무결성", "pageroles.json 선언과 실제 지면이 다릅니다."),
    "G12": ("장 앞 빈 면", "인쇄용 백면은 전자책에서 금지입니다."),
    "G13": ("도해 글자가 PDF에 실재하는지", "도해 변환에서 글자가 빠졌습니다. 도해를 다시 렌더하세요."),
    "G14-A": ("목차 쪽번호 ↔ 실제 폴리오", "빌드를 다시 하세요."),
    "G14-B": ("목차 색 ↔ 장 도비라 색", "스타일 색 설정을 확인하세요."),
    "G14-C": ("글자 대비(WCAG)", "배경 위 글자색이 너무 옅습니다."),
    "G15-PARA": ("문단 길이 상한", "한 문단이 깁니다. 8행 이내로 끊으세요."),
    "G15-RHYTHM": ("시각 요소 없는 연속 면", "표·도해·콜아웃을 3면마다 하나씩 넣으세요."),
}

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
 .booklist a{display:block;padding:7px 9px;border-radius:8px;color:var(--ink);
   text-decoration:none;cursor:pointer;font-size:14px}
 .booklist a:hover{background:var(--bg)}
 .booklist a.on{background:var(--brand-soft);color:var(--brand);font-weight:600}
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
 table{width:100%;border-collapse:collapse;font-size:13px}
 th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
 th{color:var(--mute);font-weight:600}
 td button{white-space:nowrap;padding:6px 10px}
 #otbl td:last-child{width:1%}
 pre{margin:0;padding:10px;background:#0f1419;color:#d7dde5;border-radius:8px;
   font:12px/1.5 ui-monospace,monospace;max-height:220px;overflow:auto;white-space:pre-wrap}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}
 .grid img{width:100%;border:1px solid var(--line);border-radius:8px;background:#fff}
 .styles{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px}
 .styles div{border:1px solid var(--line);border-radius:10px;padding:10px;cursor:pointer}
 .styles div.on{border-color:var(--brand);background:var(--brand-soft)}
 .styles b{font-size:14px}.styles small{display:block;color:var(--mute);font-size:12px;margin-top:2px}
 .chaps{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
 .chaps button.on{border-color:var(--brand);color:var(--brand);font-weight:600}
 .muted{color:var(--mute);font-size:13px}
 code{background:var(--bg);padding:1px 5px;border-radius:5px;font-size:13px}
</style>
<header>
  <h1>bookforge <span id=hbook>— 책을 고르거나 새로 만드세요</span></h1>
  <span id=hstate class="pill idle">대기</span>
  <span style="flex:1"></span>
  <a id=pdflink class=muted href="#" target=_blank style="display:none">PDF 열기 ↗</a>
</header>
<div class=wrap>
 <aside>
  <div class=card>
    <h2>책</h2>
    <div class=booklist id=books></div>
    <button class=primary style="width:100%;margin-top:10px" onclick="go(1)">+ 새 책 만들기</button>
  </div>
  <div class=card>
    <h2>폰트</h2>
    <p class=hint id=curfonts>동봉 폰트</p>
    <select id=flang onchange=loadFonts()>
      <option value=ko>한국어</option><option value=ja>일본어</option><option value=en>영문·숫자</option>
    </select>
    <select id=ffam style="margin-top:6px"><option>—</option></select>
    <div class=row style="margin-top:6px">
      <button style="flex:1" onclick=setFont()>지정</button>
      <button style="flex:1" onclick=clearFont()>해제</button>
    </div>
  </div>
 </aside>
 <main>
  <div class=steps id=steps></div>
  <div id=panel></div>
  <div class=card><h2>실행 기록</h2><pre id=log>—</pre></div>
 </main>
</div>
<script>
const $=i=>document.getElementById(i);
const api=(u,d)=>fetch(u,d&&{method:'POST',body:JSON.stringify(d)}).then(r=>r.json());
const esc=s=>(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const STYLES=%STYLES%, LENGTHS=%LENGTHS%;
let book=null, state=null, step=1, chap=null, newStyle='practical';

const STEPS=[
 ['책 만들기','주제와 스타일을 정한다'],
 ['자료','근거로 쓸 재료를 넣는다'],
 ['목차','장 구성을 정한다'],
 ['집필','장별 원고를 쓴다'],
 ['빌드·검사','PDF를 만들고 게이트를 돌린다'],
 ['검수','실제 지면을 눈으로 본다'],
];

async function boot(){
  const b=await api('/api/books');
  $('books').innerHTML=(b.books||[]).map(n=>
    `<a class="${n===book?'on':''}" onclick="open_('${n}')">${esc(n)}</a>`).join('')
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
  await boot();
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
function render(){
  $('steps').innerHTML=STEPS.map((s,i)=>{
    const n=i+1, done=state&&stepDone(n);
    return `<button class="step ${n===step?'on':''} ${done?'done':''}" onclick="go(${n})">
      <b>${n}. ${s[0]}</b><small>${s[1]}</small></button>`;
  }).join('');
  $('panel').innerHTML = (!state && step!==1)
    ? cardMsg('왼쪽에서 책을 고르거나 새로 만드세요.')
    : ((state && step!==1 ? banner() : '') + PANEL[step]());
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
    <button onclick="go(${n})">${n}단계로</button></div></div>`;
}

const PANEL={
 1:()=>`<div class=card>
   <h2>새 책 만들기</h2>
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
   <div class=styles>${STYLES.map(s=>
     `<div class="${s[0]===newStyle?'on':''}" onclick="pickStyle('${s[0]}')">
        <b>${esc(s[1])}</b><small>${esc(s[2])}</small></div>`).join('')}</div>
   <div class=row style="margin-top:14px"><button class=primary onclick=create()>만들기</button>
     <span class=muted>만들면 2단계(자료)로 넘어갑니다</span></div>
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
   <p class=hint>마크다운으로 씁니다. 첫 줄은 <code># 장 제목</code>이고 목차의 제목과 같아야 합니다.</p>
   <div class=chaps>${state.chapters.map(c=>{
     const n=(state.sizes||{})[c]||0;
     return `<button class="${c===chap?'on':''}" onclick="pickChap('${c}')">
       ${c.replace('chapters/','')} <span class=muted>${n<400?'미작성':n+'자'}</span></button>`;}).join('')
     || '<span class=muted>3단계에서 목차를 먼저 저장하세요.</span>'}</div>
   <textarea id=ta4 rows=22></textarea>
   <div class=row style="margin-top:10px">
     <button class=primary onclick="agent('all')">AI에게 전체 집필 맡기기</button>
     <button onclick="agent('chapter',chap)">이 장만 다시 쓰게 하기</button>
     <button onclick="saveFile(chap,'ta4')">직접 고친 내용 저장</button>
     <button onclick="go(5)">다음: 빌드</button></div>
   <p class=hint style="margin-top:10px">자동 집필은 장당 1분 안팎 걸립니다. 목차의 요약과
     2단계 자료를 근거로 씁니다 — 자료에 없는 수치는 쓰지 않도록 시켰습니다.</p>
   <details style="margin-top:12px"><summary class=muted>쓸 수 있는 문법</summary>
     <table><tr><th>요소</th><th>쓰는 법</th></tr>
     <tr><td>절 / 항</td><td><code>## 절 제목</code> · <code>### 항 제목</code></td></tr>
     <tr><td>강조</td><td><code>**굵게**</code></td></tr>
     <tr><td>인용</td><td><code>&gt; 인용문</code></td></tr>
     <tr><td>표</td><td><code>| 열 | 열 |</code> 형식</td></tr>
     <tr><td>콜아웃</td><td><code>::: tip 제목</code> … <code>:::</code> (info·tip·warn·quote·pull)</td></tr>
     <tr><td>도해</td><td><code>![캡션](../assets/fig-01.svg "출처: …")</code> — 단독 문단</td></tr>
     </table></details>
 </div>`,
 5:()=>`<div class=card>
   <h2>빌드·검사</h2>
   <p class=hint>빌드가 PDF를 만들고, 게이트가 검사를 돌립니다. 통과해야만 final 폴더에 PDF가 생깁니다.</p>
   <div class=row>
     <button class="${state.steps.built?'':'primary'}" onclick="run('build')">① 빌드</button>
     <button class="${state.steps.built&&!state.steps.passed?'primary':''}"
       ${state.steps.built?'':'disabled title="먼저 빌드하세요"'} onclick="run('qc')">② 게이트</button>
     <button ${state.steps.built?'':'disabled title="먼저 빌드하세요"'}
       onclick="run('sheet')">③ 지면 이미지 만들기</button>
   </div>
   <table style="margin-top:12px"><tr><th style="width:22%">버튼</th><th>무엇이 생기나</th></tr>
     <tr><td>① 빌드</td><td><code>draft/book.pdf</code> — 아직 검사 전 원고 PDF</td></tr>
     <tr><td>② 게이트</td><td>검사 통과 시에만 <code>final/책이름.pdf</code>. 실패하면 아래 표에 이유가 뜹니다</td></tr>
     <tr><td>③ 지면 이미지</td><td><code>qc/p001.png</code>… — 6단계에서 볼 지면 그림</td></tr></table>
   ${gateTable()}
 </div>`,
 6:()=>`<div class=card>
   <h2>검수</h2>
   <p class=hint>파일이 생긴 것은 완료가 아닙니다. 표지·차례·도비라·본문을 눈으로 확인하세요.</p>
   ${state.shots.length? `<div class=grid>${state.shots.map(s=>
     `<img src="/qc?name=${book}&page=${s}&t=${Date.now()}" loading=lazy>`).join('')}</div>`
     : '<p class=muted>5단계에서 “지면 이미지 만들기”를 먼저 누르세요.</p>'}
 </div>`,
};

function gateTable(){
  const g=state.gate;
  if(!g) return '<p class=muted style="margin-top:14px">아직 검사 결과가 없습니다.</p>';
  const rows=g.items.map(it=>`<tr>
    <td><span class="pill ${it.ok?'ok':'bad'}">${it.code}</span></td>
    <td>${esc(it.what)}${it.ok?'':`<div class=muted>${esc(it.detail||'')}</div>`}</td>
    <td class=muted>${it.ok?'':esc(it.fix)}</td></tr>`).join('');
  return `<p style="margin:14px 0 6px">
    <span class="pill ${g.stale?'idle':(g.pass?'ok':'bad')}">${
      g.stale?'이전 결과(다시 검사 필요)':(g.pass?'통과':'실패')}</span>
    <span class=muted> · ${g.pages}쪽 · 권장 ${g.range[0]}~${g.range[1]}쪽</span></p>
    <table><thead><tr><th>검사</th><th>무엇을 봤나</th><th>실패 시 할 일</th></tr></thead><tbody>${rows}</tbody></table>`;
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
function pickStyle(s){ newStyle=s; render(); }
function pickChap(c){ chap=c; render(); }

async function loadFile(path,ta){
  if(!path) return;
  const d=await api(`/api/file?name=${book}&path=${encodeURIComponent(path)}`);
  const el=$(ta); if(el) el.value=d.text||'';
}
async function loadChapter(){ loadFile(chap,'ta4'); }
async function saveFile(path,ta){
  if(!path){ $('log').textContent='저장할 파일이 없습니다'; return; }
  const r=await api('/api/file',{name:book,path,text:$(ta).value});
  $('log').textContent=r.ok?('저장됨: '+path):('실패: '+r.error);
  if(r.ok) open_(book);
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
async function run(cmd){
  $('log').textContent='실행 중…';
  const r=await api('/api/run',{name:book,cmd});
  await open_(book);
  const [msg]=nextAction();
  $('log').textContent=(r.out||r.error)+'\n\n▶ 다음: '+msg;
  if(cmd==='sheet') go(6); else render();
}
async function agent(task,target){
  if(!book){ $('log').textContent='먼저 책을 고르세요'; return; }
  const r=await api('/api/agent',{name:book,task,target});
  if(r.error){ $('log').textContent=r.error; return; }
  $('log').textContent='AI 작업 시작 — 창을 닫지 마세요…';
  poll();
}
let polling=false;
async function poll(){
  if(polling) return; polling=true;
  const tick=async()=>{
    const j=await api('/api/job');
    $('log').textContent=(j.running?'작업 중… ':'')+ (j.log||'');
    if(j.running){ setTimeout(tick,2000); }
    else{ polling=false; await open_(book);
      const [msg]=nextAction(); $('log').textContent=(j.log||'')+'\n\n▶ 다음: '+msg; }
  };
  tick();
}
async function loadFonts(){
  const d=await api('/api/fonts?lang='+$('flang').value);
  $('ffam').innerHTML=(d.fonts||[]).map(f=>
    `<option value="${esc(f.family)}">${esc(f.family)} (${f.format})</option>`).join('')
    || '<option value="">쓸 수 있는 폰트 없음</option>';
}
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
boot(); render(); loadFonts();
api('/api/job').then(j=>{ if(j.running) poll(); });
</script>
"""

_FONTS = {}
# 자동 집필은 몇 분씩 걸린다 — 한 번에 하나만, 진행 상황은 폴링으로 본다.
JOB = {"running": False, "name": "", "task": "", "log": "", "done": True}


def start_job(name: str, task: str, target: str | None):
    """agent.py를 별도 스레드에서 돌린다. 서버는 응답을 막지 않는다."""
    import threading
    if JOB["running"]:
        raise ValueError(f"이미 작업 중입니다: {JOB['name']} / {JOB['task']}")
    d = book_dir(name)
    if task not in ("research", "outline", "chapter", "all"):
        raise ValueError("unknown task")
    argv = [sys.executable, str(SKILL / "scripts/agent.py"), task, str(d)]
    if task == "chapter":
        if not CHAPTER_RE.match((target or "").replace("chapters/", "")):
            raise ValueError("bad chapter file")
        argv.append(target.replace("chapters/", ""))
    JOB.update({"running": True, "name": name, "task": task, "log": "시작…", "done": False})

    def run():
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=7200)
            JOB["log"] = (p.stdout + p.stderr).strip()[-4000:] or "(출력 없음)"
        except Exception as e:  # 타임아웃·실행 실패도 화면에 남긴다
            JOB["log"] = f"실패: {e}"
        finally:
            JOB.update({"running": False, "done": True})

    threading.Thread(target=run, daemon=True).start()
    return {"ok": True}


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
    """편집 허용 대상은 book.json · outline.json · research.md · chapters/ch-NN.md 뿐."""
    d = book_dir(name)
    rel = (rel or "").replace("\\", "/")
    if rel in EDITABLE:
        return d / rel
    if rel.startswith("chapters/") and CHAPTER_RE.match(rel.split("/", 1)[1]):
        return d / rel
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
        what, fix = (GATE_HELP.get(code) or GATE_HELP.get(code.split("-")[0])
                     or (code, "qc_gate.py 출력을 확인하세요."))
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
                      "what": what, "fix": fix, "detail": detail})
    items.sort(key=lambda x: (x["ok"], x["code"]))
    g1 = (g.get("gates") or {}).get("G1", {})
    return {"pass": bool(g.get("pass")), "pages": g1.get("pages"),
            "range": g1.get("range") or [0, 0], "items": items}


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
    shots = sorted(p.name for p in (d / "qc").glob("p*.png"))
    gate = gate_summary(d)
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
    if cmd == "build":
        argv = [sys.executable, str(SKILL / "scripts/build.py"), str(d)]
    elif cmd == "qc":
        argv = [sys.executable, str(SKILL / "scripts/qc_gate.py"), str(d)]
    elif cmd == "sheet":
        pdf = next(iter(sorted((d / "final").glob("*.pdf"))), d / "draft/book.pdf")
        argv = [sys.executable, str(SKILL / "scripts/contact_sheet.py"), str(pdf),
                str(d / "qc"), "--dpi", "90", "--pages", "1,2,3,4,5,6"]
    else:
        raise ValueError("unknown cmd")
    p = subprocess.run(argv, capture_output=True, text=True, timeout=1800)
    return {"out": (p.stdout + p.stderr).strip() or "(출력 없음)", "code": p.returncode}


def scaffold(data: dict) -> dict:
    name = data.get("name")
    if not NAME_RE.match(name or ""):
        raise ValueError("폴더 이름은 영문·숫자·-·_ 만 됩니다")
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
                styles = [[k, ko, desc] for k, (ko, desc) in STYLE_KO.items()]
                page = (PAGE.replace("%STYLES%", json.dumps(styles, ensure_ascii=False))
                            .replace("%LENGTHS%", json.dumps(LENGTHS, ensure_ascii=False)))
                return self._send(200, "text/html; charset=utf-8", page.encode())
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
            if u.path == "/api/outline":
                return self._json(save_outline(data["name"], data.get("chapters") or []))
            if u.path == "/api/run":
                return self._json(run_script(data["name"], data["cmd"]))
            if u.path == "/api/agent":
                return self._json(start_job(data["name"], data["task"], data.get("target")))
            if u.path == "/api/new":
                return self._json(scaffold(data))
            if u.path == "/api/font":
                d = book_dir(data["name"])
                argv = [sys.executable, str(SKILL / "scripts/fontpick.py"), "set", str(d)]
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
    print(f"bookforge web UI → http://127.0.0.1:{a.port}  (books: {ROOT})")
    http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
