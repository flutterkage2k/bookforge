// bookforge P1.5 도해 프리렌더 — diagrams/fig-NN.json (AntV Infographic DSL 사이드카)
// → assets/fig-NN.svg (+ fig-NN.labels.json, G13 대조 정본).
//
// Usage: node render_diagrams.mjs <book_dir> --style <style>
// 계약(references/diagrams.md):
//   사이드카 {bf:{width:"full"|"twothirds", icons:false}, dsl:"..."|[줄배열]}
//   테마는 스타일 토큰(diagram 블록)이 강제 — 콘텐츠 theme 블록은 덮어쓴다.
//   렌더는 오프라인 재현 가능해야 한다: 산출 SVG 첫 줄의 dsl 해시가 일치하면 skip.
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { convertForeignObjectText, fontFaceCss, normalizeAuthoredSvg, pixelSelfCheck } from "./fo2text.mjs";

const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const FONT_DIR = path.join(SKILL, "assets", "fonts");
const CONVERTER_VERSION = 6; // fo2text/트림 알고리즘 변경 시 올려서 캐시 전체 무효화
const PIXEL_TOLERANCE = 0.02;
const MM2PT = 72 / 25.4;

function fail(msg) { console.error(`DIAGRAM FAIL: ${msg}`); process.exit(1); }

const args = process.argv.slice(2);
const bookDir = args[0] && !args[0].startsWith("--") ? path.resolve(args[0]) : null;
const style = args.includes("--style") ? args[args.indexOf("--style") + 1] : null;
if (!bookDir || !style) fail("usage: node render_diagrams.mjs <book_dir> --style <style>");

const tokensPath = path.join(SKILL, "styles", style, "tokens.json");
if (!existsSync(tokensPath)) fail(`unknown style: ${style}`);
const tokens = JSON.parse(readFileSync(tokensPath, "utf8"));
const dg = tokens.diagram;
if (!dg) fail(`styles/${style}/tokens.json에 diagram 블록 없음 — 이 스타일은 도해 미지원`);
// build_html.py와 동일 우선순위: book.json brand가 있으면 강조색(팔레트 1번)만 교체
const bookMeta = JSON.parse(readFileSync(path.join(bookDir, "book.json"), "utf8"));
const palette = [...dg.palette];
if (bookMeta.brand) palette[0] = bookMeta.brand;

// 템플릿 적합성 실측 원장 — blocked 템플릿은 SSR 전에 차단 (minFontPt 사후 검사와 이중 방어)
const ledger = JSON.parse(readFileSync(path.join(SKILL, "references", "diagram-ledger.json"), "utf8"));

// authored SVG 팔레트 강제 — 허용색 = 스타일 팔레트 + 뉴트럴(백·먹·회색 램프)
// CSS Color Level 4 named colors → hex (transparent/currentColor는 alienColors에서 별도 처리)
const CSS_NAMED_COLORS = {
  aliceblue: "#f0f8ff", antiquewhite: "#faebd7", aqua: "#00ffff", aquamarine: "#7fffd4", azure: "#f0ffff",
  beige: "#f5f5dc", bisque: "#ffe4c4", black: "#000000", blanchedalmond: "#ffebcd", blue: "#0000ff",
  blueviolet: "#8a2be2", brown: "#a52a2a", burlywood: "#deb887", cadetblue: "#5f9ea0", chartreuse: "#7fff00",
  chocolate: "#d2691e", coral: "#ff7f50", cornflowerblue: "#6495ed", cornsilk: "#fff8dc", crimson: "#dc143c",
  cyan: "#00ffff", darkblue: "#00008b", darkcyan: "#008b8b", darkgoldenrod: "#b8860b", darkgray: "#a9a9a9",
  darkgreen: "#006400", darkgrey: "#a9a9a9", darkkhaki: "#bdb76b", darkmagenta: "#8b008b", darkolivegreen: "#556b2f",
  darkorange: "#ff8c00", darkorchid: "#9932cc", darkred: "#8b0000", darksalmon: "#e9967a", darkseagreen: "#8fbc8f",
  darkslateblue: "#483d8b", darkslategray: "#2f4f4f", darkslategrey: "#2f4f4f", darkturquoise: "#00ced1",
  darkviolet: "#9400d3", deeppink: "#ff1493", deepskyblue: "#00bfff", dimgray: "#696969", dimgrey: "#696969",
  dodgerblue: "#1e90ff", firebrick: "#b22222", floralwhite: "#fffaf0", forestgreen: "#228b22", fuchsia: "#ff00ff",
  gainsboro: "#dcdcdc", ghostwhite: "#f8f8ff", gold: "#ffd700", goldenrod: "#daa520", gray: "#808080",
  green: "#008000", greenyellow: "#adff2f", grey: "#808080", honeydew: "#f0fff0", hotpink: "#ff69b4",
  indianred: "#cd5c5c", indigo: "#4b0082", ivory: "#fffff0", khaki: "#f0e68c", lavender: "#e6e6fa",
  lavenderblush: "#fff0f5", lawngreen: "#7cfc00", lemonchiffon: "#fffacd", lightblue: "#add8e6",
  lightcoral: "#f08080", lightcyan: "#e0ffff", lightgoldenrodyellow: "#fafad2", lightgray: "#d3d3d3",
  lightgreen: "#90ee90", lightgrey: "#d3d3d3", lightpink: "#ffb6c1", lightsalmon: "#ffa07a",
  lightseagreen: "#20b2aa", lightskyblue: "#87cefa", lightslategray: "#778899", lightslategrey: "#778899",
  lightsteelblue: "#b0c4de", lightyellow: "#ffffe0", lime: "#00ff00", limegreen: "#32cd32", linen: "#faf0e6",
  magenta: "#ff00ff", maroon: "#800000", mediumaquamarine: "#66cdaa", mediumblue: "#0000cd",
  mediumorchid: "#ba55d3", mediumpurple: "#9370db", mediumseagreen: "#3cb371", mediumslateblue: "#7b68ee",
  mediumspringgreen: "#00fa9a", mediumturquoise: "#48d1cc", mediumvioletred: "#c71585", midnightblue: "#191970",
  mintcream: "#f5fffa", mistyrose: "#ffe4e1", moccasin: "#ffe4b5", navajowhite: "#ffdead", navy: "#000080",
  oldlace: "#fdf5e6", olive: "#808000", olivedrab: "#6b8e23", orange: "#ffa500", orangered: "#ff4500",
  orchid: "#da70d6", palegoldenrod: "#eee8aa", palegreen: "#98fb98", paleturquoise: "#afeeee",
  palevioletred: "#db7093", papayawhip: "#ffefd5", peachpuff: "#ffdab9", peru: "#cd853f", pink: "#ffc0cb",
  plum: "#dda0dd", powderblue: "#b0e0e6", purple: "#800080", rebeccapurple: "#663399", red: "#ff0000",
  rosybrown: "#bc8f8f", royalblue: "#4169e1", saddlebrown: "#8b4513", salmon: "#fa8072", sandybrown: "#f4a460",
  seagreen: "#2e8b57", seashell: "#fff5ee", sienna: "#a0522d", silver: "#c0c0c0", skyblue: "#87ceeb",
  slateblue: "#6a5acd", slategray: "#708090", slategrey: "#708090", snow: "#fffafa", springgreen: "#00ff7f",
  steelblue: "#4682b4", tan: "#d2b48c", teal: "#008080", thistle: "#d8bfd8", tomato: "#ff6347",
  turquoise: "#40e0d0", violet: "#ee82ee", wheat: "#f5deb3", white: "#ffffff", whitesmoke: "#f5f5f5",
  yellow: "#ffff00", yellowgreen: "#9acd32",
};
function hslToHex(h, s, l) {
  s /= 100; l /= 100;
  const k = (n) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1));
  return "#" + [f(0), f(8), f(4)].map((v) => Math.round(v * 255).toString(16).padStart(2, "0")).join("");
}
// 정규화 성공 시 "#rrggbb", 실패 시 null — null은 alienColors에서 위반으로 승격(침묵 통과 금지)
function normHex(c) {
  if (!c) return null;
  c = c.trim().toLowerCase();
  let m = c.match(/^rgba?\(\s*([\d.]+)(%?)\s*[, ]\s*([\d.]+)(%?)\s*[, ]\s*([\d.]+)(%?)/);
  if (m) {
    return "#" + [[m[1], m[2]], [m[3], m[4]], [m[5], m[6]]]
      .map(([v, pct]) => Math.max(0, Math.min(255, Math.round(pct ? (+v * 255) / 100 : +v))))
      .map((v) => v.toString(16).padStart(2, "0")).join("");
  }
  m = c.match(/^hsla?\(\s*(-?[\d.]+)(?:deg)?\s*[, ]\s*([\d.]+)%\s*[, ]\s*([\d.]+)%/);
  if (m) return hslToHex(((+m[1] % 360) + 360) % 360, +m[2], +m[3]);
  if (c in CSS_NAMED_COLORS) return CSS_NAMED_COLORS[c];
  if (/^#[0-9a-f]{3,4}$/.test(c)) c = "#" + [...c.slice(1)].map((ch) => ch + ch).join("");
  if (/^#[0-9a-f]{8}$/.test(c)) c = c.slice(0, 7); // 알파 채널 절단 — 색상 성분만 대조
  if (/^#[0-9a-f]{6}$/.test(c)) return c;
  return null;
}
function alienColors(svg, palette, strict = false) {
  // strict(authored 트랙): 허용색 = 스타일 팔레트 + paper(#ffffff)뿐 — 토큰 밖 색은
  // 무채색이라도 빌드 실패 (STYLE 「금지 사항」 2번, 토큰 밖 색 금지).
  // 비-strict(antv 트랙): 템플릿 산출 무채색 램프는 종전대로 허용.
  const allowed = new Set([...palette.map((c) => normHex(c)), "#ffffff"]);
  const out = new Set();
  const check = (raw) => {
    const v = raw.trim().toLowerCase();
    if (!v || v === "none" || v === "transparent" || v === "currentcolor" || v.startsWith("url(")) return;
    const hex = normHex(v);
    if (!hex) { out.add(`${v}(해석불가)`); return; } // 정규화 불가 색 문자열도 위반 — 무검증 통과 금지
    if (allowed.has(hex)) return;
    // 뉴트럴 허용: 무채색(채도 미미) 램프 — antv 트랙 한정
    const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
    if (!strict && Math.max(r, g, b) - Math.min(r, g, b) <= 16) return;
    out.add(hex);
  };
  for (const m of svg.matchAll(/(?:fill|stroke)="([^"]+)"/gi)) check(m[1]);
  // style="fill:...;stroke:..." 인라인 CSS도 동일 검사 (fill-opacity 등 접미 속성은 비매칭)
  for (const s of svg.matchAll(/style="([^"]*)"/gi)) {
    for (const d of s[1].matchAll(/(?:^|;)\s*(?:fill|stroke)\s*:\s*([^;]+)/gi)) check(d[1]);
  }
  return [...out];
}

// antv 트랙: 템플릿에 하드코딩된 강조색(vs 배지·화살표 그라데이션 등)은 theme palette로
// 덮이지 않고 그대로 새어 나온다. 팔레트 밖 유채색만 밝기에 따라 팔레트 색으로 치환한다
// (무채색 램프는 종전대로 보존 — alienColors 비-strict 규칙과 동일 기준).
function remapAlienColors(svg, palette) {
  const allowed = new Set([...palette.map((c) => normHex(c)), "#ffffff"]);
  const aliens = new Set();
  const scan = (raw) => {
    const hex = normHex((raw || "").trim().toLowerCase());
    if (!hex || allowed.has(hex)) return;
    const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
    if (Math.max(r, g, b) - Math.min(r, g, b) <= 16) return; // 무채색 램프는 보존
    aliens.add(hex);
  };
  // alienColors와 달리 gradient stop-color까지 본다 — 템플릿 강조색은 대부분 여기로 샌다
  for (const m of svg.matchAll(/(?:fill|stroke|stop-color)="([^"]+)"/gi)) scan(m[1]);
  for (const s of svg.matchAll(/style="([^"]*)"/gi)) {
    for (const d of s[1].matchAll(/(?:^|;)\s*(?:fill|stroke|stop-color)\s*:\s*([^;]+)/gi)) scan(d[1]);
  }
  if (!aliens.size) return svg;
  const brand = normHex(palette[0]), pale = normHex(palette[palette.length - 1]);
  const pick = (hex) => {
    const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.72 ? pale : brand;
  };
  let out = svg;
  for (const hex of aliens) {
    // ponytail: 정규화 hex 문자열만 치환 — rgb()·색이름 표기로 새는 색은 미대응(현 템플릿 산출은 전량 hex)
    out = out.replace(new RegExp(hex, "gi"), pick(hex));
  }
  return out;
}

const diagramsDir = path.join(bookDir, "diagrams");
const sidecars = existsSync(diagramsDir)
  ? readdirSync(diagramsDir).filter((f) => /^fig-\d+\.json$/.test(f)).sort()
  : [];
if (!sidecars.length) { console.log("no diagrams — skip"); process.exit(0); }

// SSR 모듈: 1순위 = 커밋된 벤더 번들(vendor/antv-ssr.bundle.mjs — 레지스트리·
// node_modules 불필요, byte-identical 검증 완료). 폴백 = 로컬 node_modules.
const skillRequire = createRequire(path.join(SKILL, "package.json"));
let renderToString, getTemplate;
const bundlePath = path.join(SKILL, "vendor", "antv-ssr.bundle.mjs");
if (existsSync(bundlePath)) {
  ({ renderToString, getTemplate } = await import(bundlePath));
} else {
  try {
    ({ renderToString } = await import(skillRequire.resolve("@antv/infographic/ssr")));
    ({ getTemplate } = await import(skillRequire.resolve("@antv/infographic")));
  } catch {
    fail("도해 렌더러 부재 — vendor/antv-ssr.bundle.mjs 유실 시 스킬 루트에서 `npm ci` 후 `node vendor/build-bundle.mjs`");
  }
}

// Playwright: print_pdf.mjs와 동일하게 NODE_PATH(글로벌 npm root) 우선, 폴백으로 직접 해석
let chromium;
try {
  ({ chromium } = createRequire(import.meta.url)("playwright"));
} catch {
  try {
    const g = execSync("npm root -g", { encoding: "utf8" }).trim();
    ({ chromium } = createRequire(path.join(g, "noop.js"))("playwright"));
  } catch {
    fail("playwright 미가용 — `npm i -g playwright && npx playwright install chromium`");
  }
}

function applyTheme(dsl, palette) {
  // 콘텐츠의 theme 블록(들여쓰기 연속 줄 포함)을 제거하고 스타일 팔레트를 강제한다.
  const stripped = dsl.replace(/^theme\r?\n(?:[ \t]+.*\r?\n?)*/gm, "").replace(/\s+$/, "");
  return `${stripped}\ntheme\n  palette ${palette.join(" ")}\n`;
}

function stripIconLines(dsl) {
  return dsl.split("\n").filter((l) => !/^\s+icon\s+\S/.test(l)).join("\n");
}

function sortDefsSymbols(svg) {
  // <symbol> id가 콘텐츠 해시라 정렬 = 결정론화 (네트워크 완료 순서 비결정 흡수)
  return svg.replace(/<defs\b[^>]*>([\s\S]*?)<\/defs>/, (whole, inner) => {
    const symbols = inner.match(/<symbol\b[\s\S]*?<\/symbol>/g);
    if (!symbols || symbols.length < 2) return whole;
    const rest = symbols.reduce((acc, s) => acc.replace(s, ""), inner);
    const sorted = [...symbols].sort((a, b) => {
      const ida = (a.match(/id="([^"]*)"/) || [])[1] || "";
      const idb = (b.match(/id="([^"]*)"/) || [])[1] || "";
      return ida < idb ? -1 : ida > idb ? 1 : 0;
    });
    return whole.replace(inner, rest.trim() ? rest + sorted.join("") : sorted.join(""));
  });
}

// viewBox 트림 — SVG 내부의 빈 좌우/상하 패딩을 제거해, 지면에서 도해가 판면
// 좌측 라인(27mm)에 정확히 물리고 폭이 명목 폭(130/86mm)과 일치하게 한다.
// (내부 여백이 있으면 콘텐츠가 8~36mm 안쪽에서 시작해 본문 정렬축이 어긋난다.)
// 반드시 pixelSelfCheck 이후에 적용할 것 — 트림은 원본과 프레이밍이 달라진다.
async function trimViewBox(page, svg) {
  const harness = `<!doctype html><html><head><meta charset="utf-8"><style>
${fontFaceCss(FONT_DIR)}
html,body{margin:0;padding:0;background:#fff;}
#stage svg text, #stage svg tspan { font-family:'Pretendard' !important; }
</style></head><body><div id="stage">${svg}</div></body></html>`;
  await page.setContent(harness, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  return page.evaluate(() => {
    const el = document.querySelector("#stage svg");
    if (!el) return null;
    const bb = el.getBBox();
    if (!bb || bb.width < 1 || bb.height < 1) return null;
    // 패딩: 스트로크 폭·마커(getBBox 비포함)를 덮는 소여백
    const pad = Math.max(2, 0.008 * Math.max(bb.width, bb.height));
    el.setAttribute("viewBox",
      `${(bb.x - pad).toFixed(2)} ${(bb.y - pad).toFixed(2)} ` +
      `${(bb.width + 2 * pad).toFixed(2)} ${(bb.height + 2 * pad).toFixed(2)}`);
    el.removeAttribute("width");
    el.removeAttribute("height");
    return new XMLSerializer().serializeToString(el);
  });
}

function fontFloorViolations(svg, widthKey) {
  const minPt = dg.minFontPt;
  const widthMm = (dg.widths || {})[widthKey];
  if (!minPt || !widthMm) return [];
  const vb = svg.match(/viewBox="[-\d. ]*?([\d.]+) ([\d.]+)"\s*/);
  const vbW = vb ? parseFloat(vb[1]) : null;
  if (!vbW) return [`viewBox 폭을 읽지 못함 — minFontPt 검사 불가`];
  const scalePt = (widthMm * MM2PT) / vbW; // user unit -> 실제 pt
  const out = [];
  const checkSize = (tag, num, unit) => {
    let user = parseFloat(num);
    if (unit === "pt") user *= 96 / 72; // CSS pt → user unit(px)
    else if (unit && unit !== "px") { // 미지 단위는 검증 불가 — 침묵 통과 금지
      out.push(`${tag} font-size 단위 '${unit}' 미지원 — px/pt/무단위로 지정할 것`);
      return;
    }
    const pt = user * scalePt;
    if (pt < minPt - 0.05) out.push(`${tag} ${num}${unit || "u"} ≈ ${pt.toFixed(1)}pt < ${minPt}pt 하한`);
  };
  // <text>뿐 아니라 <tspan>의 font-size 속성·style 내 font-size도 검사 (하한 우회 차단)
  for (const m of svg.matchAll(/<(text|tspan)\b[^>]*?font-size="([\d.]+)([a-z%]*)"/gi)) checkSize(m[1], m[2], m[3]);
  for (const m of svg.matchAll(/<(text|tspan)\b[^>]*?style="[^"]*?font-size\s*:\s*([\d.]+)([a-z%]*)/gi)) checkSize(m[1], m[2], m[3]);
  return out;
}

async function ssrWithRetry(dsl, name) {
  // SSR 내장 타임아웃(10s)은 미지 템플릿 등 일부 경로에서 발화하지 않는다(실측) —
  // 외부 30s 레이스로 무한 대기를 차단한다.
  const withTimeout = (p, ms) => Promise.race([
    p, new Promise((_, rej) => setTimeout(() => rej(new Error(`timeout ${ms}ms`)), ms).unref?.()),
  ]);
  for (let attempt = 1; attempt <= 3; attempt++) {
    try { return await withTimeout(renderToString(dsl), 30_000); }
    catch (e) {
      if (attempt === 3) fail(`${name}: SSR 3회 실패 — ${e.message}`);
      console.error(`${name}: SSR attempt ${attempt} failed (${e.message}) — retry`);
    }
  }
}

const assetsDir = path.join(bookDir, "assets");
mkdirSync(assetsDir, { recursive: true });
const checkDir = path.join(bookDir, "typeset", "diagcheck");
mkdirSync(checkDir, { recursive: true });

let browser = null;
let page = null;
let rendered = 0, skipped = 0;

for (const file of sidecars) {
  const name = file.replace(/\.json$/, "");
  const sidecar = JSON.parse(readFileSync(path.join(bookDir, "diagrams", file), "utf8"));
  const bf = sidecar.bf || {};
  const widthKey = bf.width || "full";
  if (!["full", "twothirds"].includes(widthKey)) fail(`${name}: bf.width는 full|twothirds`);
  const kind = sidecar.kind || "antv";
  if (!["antv", "authored"].includes(kind)) fail(`${name}: kind는 antv|authored`);

  if (kind === "authored") {
    // ---- authored SVG 트랙: 에이전트가 그린 diagrams/fig-NN.svg를 동일 정규화 파이프라인에 통과 ----
    const srcPath = path.join(bookDir, "diagrams", `${name}.svg`);
    if (!existsSync(srcPath)) fail(`${name}: kind=authored인데 diagrams/${name}.svg 부재`);
    const rawAuthored = readFileSync(srcPath, "utf8");
    if (/xml-stylesheet/.test(rawAuthored) || /(?:href|src)="https?:\/\//.test(rawAuthored)) {
      fail(`${name}: 외부 참조(CDN 폰트·원격 자원) 금지 — 자립 SVG로 그릴 것`);
    }
    // palette 포함 필수: 스타일(팔레트) 교체 재빌드 시 캐시 미스로 alienColors 재검증 강제
    const hashA = createHash("sha256")
      .update(JSON.stringify({ svg: rawAuthored, width: widthKey, palette, v: CONVERTER_VERSION }))
      .digest("hex");
    const outSvgA = path.join(assetsDir, `${name}.svg`);
    const outLabelsA = path.join(assetsDir, `${name}.labels.json`);
    if (existsSync(outSvgA) && existsSync(outLabelsA)) {
      const head = readFileSync(outSvgA, "utf8").slice(0, 130);
      if (head.includes(`bf:authored=sha256:${hashA}`)) { skipped++; console.log(`${name}: cache hit — skip`); continue; }
    }
    const tA = Date.now();
    if (!browser) {
      browser = await chromium.launch();
      page = await browser.newPage({ viewport: { width: 1600, height: 1200 }, deviceScaleFactor: 2 });
    }
    let normalized, labelsA;
    try {
      ({ svg: normalized, labels: labelsA } = await normalizeAuthoredSvg(page, rawAuthored, FONT_DIR));
    } catch (e) {
      fail(`${name}: ${e.message.replace(/^.*Error: /s, "").split("\n")[0]}`);
    }
    if (!labelsA.length) fail(`${name}: 라벨 0개`);
    const aliens = alienColors(normalized, palette, true);
    if (aliens.length) {
      fail(`${name}: 팔레트 밖 색 ${aliens.join(", ")} — authored SVG는 styles/${style} tokens.diagram.palette + #ffffff만 허용(토큰 밖 색 금지)`);
    }
    const checkA = await pixelSelfCheck(browser, rawAuthored, normalized, FONT_DIR, path.join(checkDir, name));
    if (checkA.ratio > PIXEL_TOLERANCE) {
      fail(`${name}: 정규화 자기검증 실패 — 픽셀 상이율 ${(checkA.ratio * 100).toFixed(2)}% (${checkDir}/${name}.diff.png)`);
    }
    normalized = (await trimViewBox(page, normalized)) || normalized;
    // 글자 하한은 트림 후 최종 좌표계 기준으로 검사 (트림은 실크기를 키우는 방향)
    const floorsA = fontFloorViolations(normalized, widthKey);
    if (floorsA.length) fail(`${name}: 글자 크기 하한 위반 — ${floorsA.join("; ")} (bf.width=${widthKey})`);
    writeFileSync(outSvgA, `<!--bf:authored=sha256:${hashA}-->\n${normalized}`);
    writeFileSync(outLabelsA, JSON.stringify(labelsA, null, 2));
    rendered++;
    console.log(`${name}: OK (authored) ${labelsA.length} labels, diff ${(checkA.ratio * 100).toFixed(2)}%, ${Date.now() - tA}ms`);
    continue;
  }

  let dsl = Array.isArray(sidecar.dsl) ? sidecar.dsl.join("\n") : sidecar.dsl;
  if (typeof dsl !== "string" || !dsl.trim().startsWith("infographic ")) {
    fail(`${name}: dsl은 'infographic <template>'로 시작하는 문자열(또는 줄 배열)`);
  }
  // AntV는 미지 템플릿명을 조용히 기본 템플릿으로 폴백한다(실측) — 오타 침묵 통과 차단
  const tplName = dsl.trim().split(/\s+/)[1];
  if (!getTemplate(tplName)) {
    fail(`${name}: 미지 템플릿 '${tplName}' — infographic-creator 스킬의 템플릿 목록 참조`);
  }
  // 실측 원장 사전 차단 — 8pt 하한에 도달 불가 판정 템플릿 (references/diagram-ledger.json)
  if (ledger.blocked_prefixes.some((p) => tplName.startsWith(p))) {
    fail(`${name}: 템플릿 '${tplName}'은 실측 원장에서 차단(라벨이 ${ledger.floor_pt}pt 하한 도달 불가) — 대안: sequence-timeline-simple 등 원장 ok 템플릿`);
  }
  const wantIcons = bf.icons === true;
  if (wantIcons && !dg.iconsAllowed) fail(`${name}: 이 스타일(${style})은 icons 미허용`);
  if (!wantIcons) dsl = stripIconLines(dsl);
  dsl = applyTheme(dsl, palette);

  const hash = createHash("sha256")
    .update(JSON.stringify({ dsl, width: widthKey, icons: wantIcons, v: CONVERTER_VERSION }))
    .digest("hex");
  const outSvg = path.join(assetsDir, `${name}.svg`);
  const outLabels = path.join(assetsDir, `${name}.labels.json`);
  if (existsSync(outSvg) && existsSync(outLabels)) {
    const head = readFileSync(outSvg, "utf8").slice(0, 120);
    if (head.includes(`bf:dsl=sha256:${hash}`)) { skipped++; console.log(`${name}: cache hit — skip`); continue; }
  }

  const t0 = Date.now();
  let raw = await ssrWithRetry(dsl, name);
  if (wantIcons) {
    const symbols = (raw.match(/<symbol\b/g) || []).length;
    if (!symbols) fail(`${name}: icons:true인데 <symbol> 0개 — 아이콘 API 미도달(오프라인?). 조용한 탈락 금지`);
  }

  if (!browser) {
    browser = await chromium.launch();
    page = await browser.newPage({ viewport: { width: 1600, height: 1200 }, deviceScaleFactor: 2 });
  }
  let convertedRaw, labels;
  try {
    ({ svg: convertedRaw, labels } = await convertForeignObjectText(page, raw, FONT_DIR));
  } catch (e) {
    fail(`${name}: ${e.message.replace(/^.*Error: /s, "").split("\n")[0]}`);
  }
  if (!labels.length) fail(`${name}: 변환 후 텍스트 줄 0개 — DSL에 라벨이 없거나 변환 실패`);
  let converted = sortDefsSymbols(convertedRaw);

  if ((converted.match(/<foreignObject/g) || []).length) fail(`${name}: foreignObject 잔존`);

  const check = await pixelSelfCheck(browser, raw, converted, FONT_DIR, path.join(checkDir, name));
  if (check.ratio > PIXEL_TOLERANCE) {
    fail(`${name}: 변환 자기검증 실패 — 픽셀 상이율 ${(check.ratio * 100).toFixed(2)}% > ${PIXEL_TOLERANCE * 100}% (${checkDir}/${name}.diff.png 확인)`);
  }
  converted = (await trimViewBox(page, converted)) || converted;
  converted = remapAlienColors(converted, palette); // 템플릿 하드코딩 강조색 → 스타일 팔레트
  // 글자 하한은 트림 후 최종 좌표계 기준으로 검사 (트림은 실크기를 키우는 방향)
  const floors = fontFloorViolations(converted, widthKey);
  if (floors.length) fail(`${name}: 도해 내 글자 크기 하한 위반 — ${floors.join("; ")} (bf.width=${widthKey} 기준)`);

  writeFileSync(outSvg, `<!--bf:dsl=sha256:${hash}-->\n${converted}`);
  writeFileSync(outLabels, JSON.stringify(labels, null, 2));
  rendered++;
  console.log(`${name}: OK ${labels.length} labels, diff ${(check.ratio * 100).toFixed(2)}%, ${Date.now() - t0}ms`);
}

if (browser) await browser.close();
console.log(`diagrams done: ${rendered} rendered, ${skipped} cached`);
