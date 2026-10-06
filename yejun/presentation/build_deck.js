// 발표자료 초안 생성 — 준용 결과보고서 최종본(claude/report/final_v5.md, PDF 42쪽, 74e6be3) 기준
// 수치는 모두 보고서 원고에서 옮겼다. 그림은 claude/report/figures/를 읽기만 한다.
// 실행: NODE_PATH=<pptxgenjs·react-icons·react·react-dom·sharp가 설치된 node_modules> node yejun/presentation/build_deck.js
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const RDS = require("react-dom/server");
const sharp = require("sharp");
const lu = require("react-icons/lu");
const JSZip = require(require.resolve("jszip", { paths: [require.resolve("pptxgenjs")] }));

const REPO = path.resolve(__dirname, "../..");
const FIGDIR = path.join(REPO, "claude/report/figures");
const OUT = path.join(__dirname, "발표자료_북적북적_초안.pptx");

// 보고서 그림과 같은 파랑·주황을 쓴다
const THEME = {
  name: "Bukjeok Press",
  headFontFace: "Malgun Gothic",
  bodyFontFace: "Malgun Gothic",
  colors: {
    dk1: "1E2125", lt1: "FFFFFF", dk2: "18293D", lt2: "F3F2EF",
    accent1: "2A78D6", accent2: "EB6834", accent3: "52514E", accent4: "2E8B57",
    accent5: "C98A12", accent6: "B8B6B0", hlink: "2A78D6", folHlink: "52514E",
  },
};
const SLOTS = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"];

// 보고서 그림 파일과 픽셀 크기(비율 유지용)
const FIG = {
  structure: ["fig1_structure.png", 1329, 650],
  observ: ["fig8_observability.png", 1511, 589],
  leak: ["fig0_leak.png", 1369, 568],
  collection: ["fig2_collection.png", 1186, 563],
  regime: ["fig9_regime_timeline.png", 1293, 730],
  loadvib: ["fig10_load_vibration.png", 1248, 677],
  model: ["fig11_model_structure.png", 1249, 640],
  miss: ["fig4_miss_position.png", 1076, 568],
  console: ["fig7_console.png", 1600, 1300],
  card: ["fig12_alarm_card.png", 1376, 581],
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.author = "북적북적";
pres.company = "북적북적";
pres.title = "프레스 유압펌프 이상 조기 경보와 오경보 발생조건 분석";
pres.subject = "제6회 K-인공지능 제조데이터 분석 경진대회 과제 ③ 발표자료 초안";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };

const C = pres.SchemeColor;
const H = THEME.colors; // 차트·표 테두리처럼 hex만 받는 옵션용
const SH = pres.shapes;
const M = 0.6;
const CW = 13.333 - 2 * M;
const TOP = 2.08;

// ---------- 레이아웃 ----------
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  margin: [0.5, 0.6, 0.6, 0.6],
  objects: [
    { text: { text: "북적북적 · 프레스 유압펌프 이상 조기 경보", options: { x: M, y: 7.02, w: 8, h: 0.28, fontSize: 10, color: C.accent3, margin: 0 } } },
    { placeholder: { options: { name: "kicker", type: "body", x: M, y: 0.32, w: 10, h: 0.3, fontSize: 12, bold: true, color: C.accent1, margin: 0, valign: "middle" }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.64, w: CW, h: 0.68, fontSize: 30, bold: true, color: C.text1, margin: 0, valign: "middle", align: "left" }, text: "" } },
    { placeholder: { options: { name: "lead", type: "body", x: M, y: 1.36, w: CW, h: 0.62, fontSize: 15, color: C.accent3, margin: 0, valign: "top" }, text: "" } },
  ],
  slideNumber: { x: 12.13, y: 7.02, w: 0.6, h: 0.28, fontSize: 10, color: C.accent3, align: "right", margin: 0 },
});
pres.defineSlideMaster({
  title: "COVER",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 1.75, w: 11.7, h: 2.3, fontSize: 36, bold: true, color: C.background1, margin: 0, valign: "top", align: "left" }, text: "" } },
    { placeholder: { options: { name: "sub", type: "body", x: 0.8, y: 4.3, w: 11.7, h: 0.5, fontSize: 18, color: C.background2, margin: 0, valign: "top" }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CLOSING",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 0.55, w: 11.7, h: 0.8, fontSize: 32, bold: true, color: C.background1, margin: 0, valign: "middle", align: "left" }, text: "" } },
  ],
  slideNumber: { x: 12.13, y: 7.02, w: 0.6, h: 0.28, fontSize: 10, color: C.background2, align: "right", margin: 0 },
});

// ---------- 도우미 ----------
function content(section, kicker, title, lead) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  s.addText(kicker, { placeholder: "kicker" });
  s.addText(title, { placeholder: "title" });
  if (lead) s.addText(lead, { placeholder: "lead" });
  return s;
}
function tx(s, text, o) {
  s.addText(text, Object.assign({ isTextBox: true, margin: 0, fontSize: 14, color: C.text1, valign: "top" }, o));
}
function card(s, x, y, w, h, color = C.background2, transparency = 0, extra = {}) {
  s.addShape(SH.ROUNDED_RECTANGLE, Object.assign({ x, y, w, h, fill: { color, transparency }, line: { type: "none" }, rectRadius: 0.08 }, extra));
}
// items: 문자열 또는 { b: 굵은 앞말, t: 나머지 }
function bullets(s, items, o = {}) {
  const gap = o.gap ?? 7;
  const runs = [];
  items.forEach((it, i) => {
    const last = i === items.length - 1;
    const p = { bullet: { indent: 13 }, paraSpaceAfter: gap };
    if (typeof it === "string") runs.push({ text: it, options: Object.assign({}, p, { breakLine: !last }) });
    else {
      runs.push({ text: it.b, options: Object.assign({}, p, { bold: true, color: it.c || C.text1 }) });
      runs.push({ text: " " + it.t, options: { breakLine: !last } });
    }
  });
  const opts = Object.assign({ isTextBox: true, margin: 0, fontSize: 14, color: C.text1, valign: "top" }, o);
  delete opts.gap;
  s.addText(runs, opts);
}
function fig(s, key, x, y, w, alt) {
  const [file, pw, ph] = FIG[key];
  const h = (w * ph) / pw;
  s.addImage({ path: path.join(FIGDIR, file), x, y, w, h, altText: alt });
  return y + h;
}
function figH(s, key, x, y, h, alt) {
  const [file, pw, ph] = FIG[key];
  const w = (h * pw) / ph;
  s.addImage({ path: path.join(FIGDIR, file), x, y, w, h, altText: alt });
  return x + w;
}
function num(s, n, x, y, d, color = C.accent1, size = 14) {
  s.addText(String(n), { shape: SH.OVAL, x, y, w: d, h: d, fill: { color }, color: C.background1, bold: true, fontSize: size, align: "center", valign: "middle", margin: 0 });
}
function arrow(s, x, y, w = 0.2, h = 0.28, color = C.accent6) {
  s.addShape(SH.ISOSCELES_TRIANGLE, { x, y, w: h, h: w, rotate: 90, fill: { color }, line: { type: "none" } });
}
const ICON = {};
async function loadIcons(names) {
  for (const n of names) {
    let svg = RDS.renderToStaticMarkup(React.createElement(lu[n], { size: 256 }));
    svg = svg.replace(/currentColor/g, "#FFFFFF");
    const buf = await sharp(Buffer.from(svg)).png().toBuffer();
    ICON[n] = "image/png;base64," + buf.toString("base64");
  }
}
function icon(s, name, x, y, d, color = C.accent1) {
  s.addShape(SH.OVAL, { x, y, w: d, h: d, fill: { color }, line: { type: "none" } });
  const p = d * 0.24;
  s.addImage({ data: ICON[name], x: x + p, y: y + p, w: d - 2 * p, h: d - 2 * p });
}
// 표: header 문자열 배열, rows 셀 배열(문자열 또는 {text, options})
function table(s, header, rows, o) {
  const fs_ = o.fontSize ?? 12;
  const hdr = header.map((h) => ({ text: h, options: { bold: true, color: C.background1, fill: { color: C.text2 }, fontSize: fs_, valign: "middle" } }));
  const body = rows.map((r, i) =>
    r.map((c) => {
      const cell = typeof c === "object" && c !== null && !Array.isArray(c) && "text" in c ? c : { text: c };
      return { text: cell.text, options: Object.assign({ fill: { color: i % 2 ? C.background2 : C.background1 }, fontSize: fs_, color: C.text1, valign: "middle" }, cell.options || {}) };
    })
  );
  s.addTable([hdr, ...body], {
    x: o.x, y: o.y, w: o.w, colW: o.colW, rowH: o.rowH,
    border: { type: "solid", pt: 0.75, color: "DAD8D3" },
    margin: [0.05, 0.09, 0.05, 0.09], autoPage: false,
  });
}
const V = {
  ok: (t) => ({ text: t, options: { bold: true, color: C.accent4 } }),
  info: (t) => ({ text: t, options: { bold: true, color: C.accent1 } }),
  warn: (t) => ({ text: t, options: { bold: true, color: C.accent2 } }),
  amber: (t) => ({ text: t, options: { bold: true, color: C.accent5 } }),
  gray: (t) => ({ text: t, options: { bold: true, color: C.accent3 } }),
};

async function build() {
  await loadIcons(["LuTimer", "LuClock", "LuCalendarX", "LuTriangleAlert", "LuMoon", "LuCheck", "LuWaves", "LuSplit", "LuRepeat", "LuGauge"]);

  // ===== 1. 표지 =====
  pres.addSection({ title: "표지" });
  {
    const s = pres.addSlide({ masterName: "COVER", sectionTitle: "표지" });
    tx(s, "제6회 K-인공지능 제조데이터 분석 경진대회 · 과제 ③ 프레스 유압펌프", { x: 0.8, y: 1.05, w: 11.7, h: 0.4, fontSize: 16, bold: true, color: C.accent2 });
    s.addText("설비 물리·데이터 결함 진단에 기반한\n프레스 유압펌프 이상 조기 경보와\n오경보 발생조건 분석", { placeholder: "title" });
    s.addText("팀 북적북적  |  허예준(팀장) · 장준용  |  일반국민·대학(원)생 부문", { placeholder: "sub" });
    // 시스템 한 줄 요약: 센서 3채널 → 모델 → 2단계 경보
    const y = 5.55, h = 0.52;
    let x = 0.8;
    ["상부 진동", "하부 진동", "모터 전류"].forEach((t) => {
      s.addText(t, { shape: SH.ROUNDED_RECTANGLE, x, y, w: 1.45, h, rectRadius: 0.08, fill: { color: C.background1, transparency: 86 }, line: { color: C.background2, width: 0.75 }, color: C.background1, fontSize: 13, align: "center", valign: "middle", margin: 0 });
      x += 1.6;
    });
    arrow(s, x + 0.02, y + 0.12, 0.28, 0.28, C.background2);
    x += 0.45;
    s.addText("v2 + R1 · R2", { shape: SH.ROUNDED_RECTANGLE, x, y, w: 1.75, h, rectRadius: 0.08, fill: { color: C.accent1 }, line: { type: "none" }, color: C.background1, bold: true, fontSize: 13, align: "center", valign: "middle", margin: 0 });
    x += 1.9;
    arrow(s, x + 0.02, y + 0.12, 0.28, 0.28, C.background2);
    x += 0.45;
    s.addText("1단계 주의 · 2단계 점검 요청", { shape: SH.ROUNDED_RECTANGLE, x, y, w: 3.0, h, rectRadius: 0.08, fill: { color: C.accent2 }, line: { type: "none" }, color: C.background1, bold: true, fontSize: 13, align: "center", valign: "middle", margin: 0 });
    s.addNotes("인사 후 한 문장으로 시작한다: 진동 2개와 전류 1개만으로 프레스 유압펌프의 이상 상태 진입을 실시간으로 알리고, 정상 운전 중 오경보가 언제 나는지까지 밝힌 작업이다. 아래 띠가 시스템 전체 흐름이다 — 세 센서, 기반 모델 v2와 두 규칙, 2단계 경보.");
  }

  // ===== 2. 핵심 결과 =====
  pres.addSection({ title: "도입" });
  {
    const s = content("도입", "요약", "핵심 결과 한눈에", "정상 자료만 학습한 기반 모델 v2에, 오류 분석에서 나온 규칙 R1(사건 지속)·R2(교차 확인)를 더했다");
    const stats = [
      ["1.000", "최종 모델 test 행 F1", "실시간 판정, 분할 A·B 모두 · 미탐·오경보 0행 (α 1%)", C.accent2],
      ["0.498", "베이스라인 최고 test F1", "MLP 오토인코더 · 규칙 없는 v2는 0.965 / 0.970", C.accent1],
      ["9 → 1", "고부하 정상 오경보 기록(53개 중)", "R2 교차 확인 · 분할 B, α 5%, 사후 집계", C.accent1],
      ["26 / 26", "보고서 수치 재현 일치", "새 가상환경 · run_all.py", C.accent1],
    ];
    const w = (CW - 3 * 0.3) / 4;
    stats.forEach(([big, label, sub, col], i) => {
      const x = M + i * (w + 0.3);
      card(s, x, TOP, w, 2.35);
      tx(s, big, { x: x + 0.25, y: TOP + 0.22, w: w - 0.5, h: 0.8, fontSize: 40, bold: true, color: col, valign: "middle" });
      tx(s, label, { x: x + 0.25, y: TOP + 1.08, w: w - 0.5, h: 0.6, fontSize: 14, bold: true });
      tx(s, sub, { x: x + 0.25, y: TOP + 1.68, w: w - 0.5, h: 0.55, fontSize: 12, color: C.accent3 });
    });
    tx(s, "무엇을 했나", { x: M, y: 4.68, w: 6.0, h: 0.35, fontSize: 15, bold: true });
    bullets(s, [
      { b: "데이터 진단:", t: "저장 형식 누수(행 F1 0.992)를 지우고, 최대 5초씩 끊긴 기록·날짜 교락·단일 사건을 설계에 반영" },
      { b: "오류 조건:", t: "미탐은 기록 시작 직후, 오경보는 고부하 정상의 크기 성분 단독 경보에 몰린다" },
      { b: "현장:", t: "진동 2·전류 1채널로 2단계 경보(주의·점검 요청)와 경보 근거별 점검 순서" },
    ], { x: M, y: 5.08, w: 6.0, h: 1.7, fontSize: 14 });
    card(s, 6.9, 4.68, 5.833, 2.07, C.accent2, 90);
    tx(s, "1.000을 읽는 법", { x: 7.15, y: 4.83, w: 5.4, h: 0.35, fontSize: 15, bold: true, color: C.accent2 });
    tx(s, "약 3분짜리 단일 고장 사건의 결과다. R1만 붙여도 베이스라인이 test 0.982~1.000이라 모델 우열은 R1 없는 값(v2 0.965 / 0.970)으로 읽는다. R1·R2는 전체 데이터를 본 뒤 착안했고, 최종 모델은 test 확인 후 정했다.", { x: 7.15, y: 5.22, w: 5.4, h: 1.45, fontSize: 14 });
    s.addNotes("결과부터 말한다. 최종 모델은 test에서 분할 A·B 모두 행 F1 1.000, 미탐·오경보 0행이다. 같은 조건의 베이스라인 최고는 MLP 오토인코더 0.498이고, 규칙 없는 기반 모델 v2만으로도 0.965·0.970이다. 다만 1.000은 약 3분짜리 고장 사건 하나의 결과라서, 우리는 이 숫자를 어떻게 읽어야 하는지를 발표 내내 함께 보여 드린다(오른쪽 상자). 근거: 보고서 내용요약, 1장 첫 표.");
  }

  // ===== 3. 과제와 접근 =====
  {
    const s = content("도입", "과제 ③ 진동·전류 시계열 기반 프레스 유압펌프 이상 조기탐지 및 오경보 분석", "과제가 요구한 두 가지와 우리의 답", "① 이상 조기 탐지 ② 정상 운전변화 오경보 억제와 미탐·오경보 발생조건 분석 — ②는 가이드북 실습에 없던 요구다");
    card(s, M, TOP, 3.9, 4.67);
    icon(s, "LuTimer", M + 0.25, TOP + 0.25, 0.6, C.accent2);
    tx(s, "왜 중요한가", { x: M + 1.0, y: TOP + 0.33, w: 2.7, h: 0.45, fontSize: 16, bold: true, valign: "middle" });
    bullets(s, [
      "펌프가 고장 나면 수리비와 부품 수급 때문에 최대 2~3일 공정이 멈춘다",
      "지금은 숙련 작업자가 작동 소음을 듣고 판단한다",
      "주어진 센서: 상부·하부 진동 2개와 모터 전류 1개, 초당 10회",
    ], { x: M + 0.25, y: TOP + 1.1, w: 3.4, h: 3.1, fontSize: 14, gap: 10 });
    tx(s, "출처: 대회 가이드북", { x: M + 0.25, y: TOP + 4.22, w: 3.4, h: 0.3, fontSize: 11, color: C.accent3 });
    const items = [
      ["데이터 이해·진단", "15점", "형식 누수 제거, 수집 구조·날짜 교락·운전 상태 진단"],
      ["AI 예측모델·성능", "40점", "v2 + R1 + R2, 베이스라인 5종 등 같은 조건 비교와 의심 검증"],
      ["영향요인·오류분석", "15점", "미탐은 기록 시작 직후, 오경보는 고부하 정상"],
      ["현장 활용방안", "10점", "2단계 경보, 경보 근거별 점검 순서, 수집 개선 ①~④"],
      ["창의성·차별성", "10점", "신호 물리, 세션 교락 측정, 오경보 상한의 운영 환산"],
      ["코드·재현성", "10점", "run_all.py 한 명령, 보고서 수치 26/26 일치"],
    ];
    const gx = 4.8, gw = 13.333 - M - gx, cw = (gw - 2 * 0.25) / 3, ch = (4.67 - 0.25) / 2;
    items.forEach(([name, pt, ans], i) => {
      const x = gx + (i % 3) * (cw + 0.25), y = TOP + Math.floor(i / 3) * (ch + 0.25);
      card(s, x, y, cw, ch);
      num(s, i + 1, x + 0.22, y + 0.22, 0.5, C.accent1, 16);
      tx(s, pt, { x: x + 0.85, y: y + 0.27, w: cw - 1.05, h: 0.4, fontSize: 13, color: C.accent3, valign: "middle" });
      tx(s, name, { x: x + 0.22, y: y + 0.88, w: cw - 0.4, h: 0.4, fontSize: 15, bold: true });
      tx(s, ans, { x: x + 0.22, y: y + 1.32, w: cw - 0.4, h: 0.8, fontSize: 13, color: C.accent3 });
    });
    s.addNotes("과제문은 두 과업을 요구한다. 조기 탐지와, 정상적인 운전 변화가 이상으로 잡히는 오경보를 줄이고 그 발생 조건을 분석하는 일이다. 두 번째 과업은 가이드북 실습에 없던 요구라 우리가 특히 공을 들였다. 오른쪽 여섯 칸은 평가 항목 순서이고, 발표도 이 순서로 간다. 근거: 보고서 1.1절.");
  }

  // ===== 4. 설비와 센서 =====
  pres.addSection({ title: "1 데이터 이해·진단" });
  const K1 = "1  데이터 이해 및 진단 · 15점";
  {
    const s = content("1 데이터 이해·진단", K1, "설비와 센서: 초당 10회로 무엇을 볼 수 있나", "파인블랭킹 프레스(약 1000톤)의 모터-펌프 유닛에 진동 2개와 전류 1개 — 나이퀴스트 5Hz 위의 고장 서명은 직접 볼 수 없다");
    fig(s, "structure", M, TOP, 7.2, "설비 계통(일반 구조, 추정)과 센서 위치");
    card(s, M, 5.78, 7.2, 0.97, C.accent1, 90);
    tx(s, [
      { text: "전류 0.600Hz의 정체(가설) ", options: { bold: true, color: C.accent1 } },
      { text: "60Hz 계열 파형이 10Hz 표본에 접힌 결과로 보인다(홀수 고조파가 정확히 3·5·7배 위치). 계통이 정확히 60Hz라면 표본 간격은 약 99 또는 101ms이고, 시각은 실측이 아닌 계산값으로 보인다(추정)." },
    ], { x: M + 0.2, y: 5.88, w: 6.8, h: 0.8, fontSize: 13 });
    tx(s, "10Hz로 남는 정보 → 세 성분(설계 뒤 점검)", { x: 8.1, y: TOP, w: 4.63, h: 0.4, fontSize: 14.5, bold: true });
    const rows = [
      ["관측 진폭의 크기", "세 센서의 표준화 값 → 크기 성분"],
      ["저주파 시간 구조", "겉보기 0.6Hz 전류의 시간 구조 → 동역학 성분(AR(2) 예측 오차)"],
      ["전류 파형", "사인 적합 1−R² → 파형 성분. 부하 토크 변동은 전류를 위상 변조한다"],
    ];
    rows.forEach(([h, b], i) => {
      const y = 2.6 + i * 1.07;
      card(s, 8.1, y, 4.63, 0.95);
      num(s, i + 1, 8.27, y + 0.24, 0.46, C.accent1, 14);
      tx(s, h, { x: 8.9, y: y + 0.1, w: 3.7, h: 0.34, fontSize: 14, bold: true });
      tx(s, b, { x: 8.9, y: y + 0.44, w: 3.7, h: 0.48, fontSize: 12, color: C.accent3 });
    });
    card(s, 8.1, 5.85, 4.63, 0.9, C.accent3, 92);
    tx(s, [
      { text: "직접 볼 수 없는 것 ", options: { bold: true } },
      { text: "회전 1X(약 29Hz), 기어 맞물림(약 260~350Hz), 캐비테이션 고주파. 극수·잇수는 가정값이다." },
    ], { x: 8.28, y: 5.95, w: 4.3, h: 0.75, fontSize: 12.5 });
    s.addNotes("이 설비는 판재를 V링으로 누르고 역압으로 받친 채 블랭킹하는 3중 동작 유압 프레스다. 센서는 모터-펌프 유닛 상부·하부 진동과 모터 전력선 전류 세 개이고 PLC가 초당 10회 모은다. 그래서 기어 맞물림이나 베어링 결함 주파수 같은 표준 진단은 할 수 없다. 남는 정보는 오른쪽 세 가지이고, 우리 모델의 세 성분이 여기에 하나씩 대응한다. 또 전류의 0.600Hz는 60Hz가 접힌 것으로 보여, 표본 시각이 실측이 아닌 계산값일 수 있다는 추정까지 이어졌다(인버터 구동 가능성이 남아 표본 간격은 확정하지 않았다). 근거: 보고서 1.2~1.5절, 그림 1·2.");
  }

  // ===== 5. 형식 누수 =====
  {
    const s = content("1 데이터 이해·진단", K1, "저장 형식만으로 F1 0.992 — 누수부터 지웠다", "정상·이상 파일의 소수 자릿수가 달라, 학습 없는 '자릿수 > 6' 규칙만으로 행 F1 0.992가 나온다");
    fig(s, "leak", M, TOP, 8.0, "형식 누수: 원본과 정밀도를 맞춘 뒤의 소수 자릿수 분포");
    tx(s, "0.992", { x: 8.95, y: TOP, w: 3.78, h: 0.85, fontSize: 48, bold: true, color: C.accent2, valign: "middle" });
    tx(s, "학습 없는 '자릿수 > 6' 규칙의 행 F1", { x: 8.95, y: 2.98, w: 3.78, h: 0.6, fontSize: 14, bold: true });
    bullets(s, [
      "상부 진동 소수 자릿수: 정상은 89.8%가 6자리, 이상은 8자리 44.0%·9자리 41.0%",
      "이상 전류만 1.192 간격 격자",
      "형식 특징을 쓰는 모델은 이 누수만으로 F1 0.972~1.000이 가능하다",
    ], { x: 8.95, y: 3.68, w: 3.78, h: 1.75, fontSize: 13 });
    card(s, M, 5.6, 5.95, 0.98, C.accent1, 90);
    tx(s, [
      { text: "조치 ", options: { bold: true, color: C.accent1 } },
      { text: "두 파일을 같은 정밀도로 맞췄다(진동 1e-4, 전류 1.1920929 간격). 맞춘 뒤 4자리 비율은 89.5% 대 90.2%로 같아진다." },
    ], { x: M + 0.2, y: 5.72, w: 5.55, h: 0.95, fontSize: 13 });
    card(s, 6.783, 5.6, 5.95, 0.98);
    tx(s, [
      { text: "확인 ", options: { bold: true } },
      { text: "값만 보는 모델은 원본·맞춤본 F1이 같았다(분할 B 초기 감사: max|z| 0.536·0.536, 5NN 0.582·0.582). 이후 모든 점수는 맞춤 입력에서 쟀다." },
    ], { x: 6.983, y: 5.72, w: 5.55, h: 0.95, fontSize: 13 });
    s.addNotes("데이터를 처음 열었을 때 가장 먼저 의심한 것은 저장 형식이다. 정상 파일과 이상 파일의 소수 자릿수가 달라서, 아무것도 학습하지 않은 '자릿수가 6보다 크면 이상' 규칙만으로 행 F1이 0.992가 나온다. 이건 고장을 맞히는 게 아니라 파일을 맞히는 누수다. 그래서 두 파일의 정밀도를 같게 맞춘 뒤 분석을 시작했고, 값만 보는 모델은 맞춘 뒤에도 점수가 같다는 것까지 확인했다. 근거: 보고서 1.6절, 그림 3.");
  }

  // ===== 6. 데이터 제약 =====
  {
    const s = content("1 데이터 이해·진단", K1, "데이터 제약 네 가지를 설계에 반영했다", "결측은 0이지만, 가이드북 품질지수(정상 96.66%)로는 잡히지 않는 결함이 있다");
    const rows = [
      ["LuClock", "측정이 띄엄띄엄 끊긴다", "정상 77분 중 실제 측정 33분(43.3%). 행은 최대 50행(5초) '기록'으로 끊겨 들어온다(정상 600·이상 21기록)", "기록을 분석 단위로 삼고 모든 창 계산을 기록 안에서만 한다. 기록 시작 직후는 과거 정보 없이 판단해야 한다"],
      ["LuCalendarX", "정상과 이상이 다른 날에서 왔다", "정상 2022-07-12(화) 00:00~01:17, 이상 07-17(일) 10:51~10:53", "고장과 운전·수집 조건이 섞인다(교락) → 수집 조건 흔들림 시험(V5)으로 민감도를 잰다"],
      ["LuTriangleAlert", "고장은 한 사건뿐이다", "이상 600행 = 2분 46초짜리 한 사건이 21기록으로 나뉨. 라벨은 파일 단위라 고장 시작 시점이 없다", "21기록을 독립된 21건으로 세지 않는다 → 이항·포아송 상한을 함께 보고한다"],
      ["LuMoon", "정상 안에 운전 상태가 섞여 있다", "00:59~01:11 정숙 구간 90기록(전류 진폭 약 121로 고정). 가이드북 그래프의 진폭 축소 구간과 겹친다", "정숙 구간은 학습에 없다 → 운전 상태별 오경보를 따로 센다(3장)"],
    ];
    rows.forEach(([ic, head, ev, design], i) => {
      const y = TOP + i * 1.18, h = 1.07;
      card(s, M, y, 7.0, h);
      icon(s, ic, M + 0.2, y + 0.235, 0.6, i === 2 ? C.accent2 : C.accent1);
      tx(s, head, { x: 1.6, y: y + 0.1, w: 5.85, h: 0.36, fontSize: 15, bold: true });
      tx(s, ev, { x: 1.6, y: y + 0.48, w: 5.85, h: 0.55, fontSize: 12.5, color: C.accent3 });
      arrow(s, 7.68, y + 0.4, 0.22, 0.28);
      card(s, 8.0, y, 4.733, h, C.accent1, 90);
      tx(s, "설계 반영", { x: 8.2, y: y + 0.1, w: 4.3, h: 0.28, fontSize: 11, bold: true, color: C.accent1 });
      tx(s, design, { x: 8.2, y: y + 0.38, w: 4.35, h: 0.65, fontSize: 12.5 });
    });
    s.addNotes("형식 말고도 데이터에는 네 가지 제약이 있다. 측정이 최대 5초짜리 기록으로 띄엄띄엄 끊기고, 정상과 이상이 5일 떨어진 다른 날·다른 요일에서 왔고, 고장은 2분 46초짜리 한 사건뿐이며, 정상 77분 안에 정숙 구간이라는 다른 운전 상태가 섞여 있다. 오른쪽은 각 제약을 분석 설계에 어떻게 반영했는지다. 특히 기록 단위로 끊기는 구조는 뒤에서 미탐 원인과 규칙 R1의 근거로 다시 나온다. 근거: 보고서 1.6절 결함 표.");
  }

  // ===== 7. 운전 상태와 분할 =====
  {
    const s = content("1 데이터 이해·진단", K1, "운전 상태와 시간순 분할", "정상 77분은 변동 구간과 정숙 구간으로 나뉜다 — 정숙 구간은 두 분할 모두 학습에 없다");
    fig(s, "regime", M, TOP, 7.0, "정상 77분의 운전 상태와 분할 경계, v2 오경보 기록");
    tx(s, "주황 원 = v2 오경보 기록(α 1%, valid·test) · 회색 띠 = 정숙 구간(00:59~01:11, 90기록)", { x: M, y: 6.15, w: 7.0, h: 0.3, fontSize: 11, color: C.accent3 });
    table(s, ["구분", "분할 A", "분할 B", "이상 21기록"], [
      [{ text: "train", options: { bold: true } }, "기록 0~359", "0~299", "사용 안 함"],
      [{ text: "valid", options: { bold: true } }, "360~479", "300~419", "앞 10기록"],
      [{ text: "test", options: { bold: true } }, "480~599", "420~599", "뒤 11기록"],
    ], { x: 7.9, y: TOP, w: 4.833, colW: [0.85, 1.25, 1.15, 1.583], fontSize: 13, rowH: 0.42 });
    bullets(s, [
      "표준화·성분 분포는 train, 경보 문턱은 valid 정상 기록으로 정한다. valid 오경보는 그 기록을 뺀 나머지로 정한 문턱으로 잰다(leave-one-record-out)",
      "valid 선택 결과를 해시로 잠근 뒤에만 test를 채점한다. 행 단위 채점, point-adjust는 쓰지 않는다(R1이 주는 비슷한 이득은 따로 밝힘)",
      "A·B는 이상 기록이 같아 독립된 두 확인이 아니다. A test 정상 120기록 중 83기록이 정숙 구간이라 고부하 오경보는 B와 valid로 읽는다",
    ], { x: 7.9, y: 3.95, w: 4.833, h: 2.8, fontSize: 13.5, gap: 9 });
    s.addNotes("변화점 검출로 정상 77분을 나누면 전류 진폭이 오르내리는 변동 구간과, 약 12분 동안 진폭이 121 근처로 고정된 정숙 구간이 나온다. 가이드북 그래프에서 설명 없이 진폭이 줄어든 구간(16,000~19,000행)과 90기록 중 82기록이 겹친다. 분할은 시간순 train/valid/test 두 가지(A·B)를 썼고, 정숙 구간은 두 분할 모두 학습에 없다. 그래서 '학습에 없던 운전 상태에서 오경보가 나는가'를 자연스럽게 시험할 수 있었다. 근거: 보고서 1.6~1.7절, 그림 5.");
  }

  // ===== 8. 진단 매트릭스 =====
  pres.addSection({ title: "2 AI 모델·성능" });
  const K2 = "2  AI 예측모델 개발 및 성능평가 · 40점";
  {
    const s = content("2 AI 모델·성능", K2, "세 센서로는 고장 종류를 가를 수 없다", "ISO 13379-1 방식의 고장 모드–증상 매트릭스로 따져, 목표를 '고장 상태 진입의 실시간 경보'로 좁혔다");
    table(s, ["고장 모드", "10Hz 데이터로 볼 수 있나 · 관찰과의 관계", "판정"], [
      ["측판·끝면 마모", "압력 측정 없음. 이상 전류 RMS가 낮지만(88.7 대 100.0) 직류 편차가 커서 믿기 어렵다", V.gray("구분 불가")],
      ["치면 마모·피팅", "맞물림 측대역은 불가. 전류 변조는 파형 붕괴(O1)로 간접 관찰", V.info("부합 가능")],
      ["캐비테이션·에어레이션", "고주파 광대역은 직접 볼 수 없다. O1·O2와 맞지만 유일한 설명이 아니다", V.info("부합 가능")],
      ["커플링 정렬 불량", "회전 1X가 5Hz 위라 판별 불가", V.gray("구분 불가")],
      ["기초·체결 풀림", "1X 위상은 아니다. 상·하부 음의 상관(O3)이 정황", V.amber("정황만")],
      ["계측·수집 이상", "영점 이동·형식 변화는 볼 수 있다. 전류 치우침(O5)과 맞는다", V.warn("배제 불가")],
    ], { x: M, y: TOP, w: 7.75, colW: [2.0, 4.45, 1.3], fontSize: 12, rowH: 0.6 });
    tx(s, "이상 사건에서 본 관찰 O1~O5", { x: 8.65, y: TOP, w: 4.083, h: 0.36, fontSize: 14, bold: true });
    const obs = [
      ["O1", "전류 파형 붕괴", "사인 적합 R² ≤ 0.617 (정상 중앙 0.995)"],
      ["O2", "진동 증가·저주파화", "SD 상부 5.34배·하부 2.55배(기록 중앙값)"],
      ["O3", "상·하부 음의 상관", "상관 중앙값 −0.36, 위상차 약 120°"],
      ["O4", "부하로 설명 안 되는 진동", "부하 효과를 지워도 정상 잔차 밖"],
      ["O5", "전류 치우침", "|평균|/RMS 중앙값 0.60"],
    ];
    obs.forEach(([k, h, b], i) => {
      const y = 2.52 + i * 0.53;
      tx(s, k, { x: 8.65, y, w: 0.5, h: 0.46, fontSize: 13, bold: true, color: C.accent2, valign: "middle" });
      tx(s, [{ text: h, options: { bold: true, breakLine: true } }, { text: b, options: { color: C.accent3, fontSize: 11.5 } }], { x: 9.15, y, w: 3.583, h: 0.5, fontSize: 12.5, valign: "middle" });
    });
    card(s, 8.65, 5.27, 4.083, 1.48, C.accent2, 90);
    tx(s, [
      { text: "목표 재설정", options: { bold: true, color: C.accent2, breakLine: true } },
      { text: "고장 전 예고는 검증할 수 없다(정상·이상 사이 5일 공백, 이상 파일은 첫 기록부터 이상). 정상 자료만 학습해 '고장 상태에 들어선 순간을 실시간으로 알리는 경보'를 만든다." },
    ], { x: 8.83, y: 5.37, w: 3.75, h: 1.32, fontSize: 12.5 });
    s.addNotes("문헌에서 기어펌프 고장 모드별 서명을 정리하고, 이상 사건에서 본 다섯 가지 관찰과 맞춰 봤다. 결론은 솔직하게 '세 센서로는 고장 종류를 가를 수 없다'이다. 이상 상태는 뚜렷하지만 원인이 펌프 기계 고장인지, 운전 조건인지, 계측·수집 변화인지는 데이터로 분리되지 않는다. 고장 직전 패턴도 없다. 그래서 목표를 '고장 상태 진입을 실시간으로 알리는 경보'로 좁혔다. 이 매트릭스는 뒤에서 경보 근거별 점검 순서로 다시 쓰인다. 근거: 보고서 2.1절.");
  }

  // ===== 9. 모델 구조 =====
  {
    const s = content("2 AI 모델·성능", K2, "기반 모델 v2와 경보 규칙 R1·R2", "정상 train만으로 0.1초마다 세 성분을 계산하고, 가장 드문 성분의 꼬리 점수를 conformal 문턱(α 1%)과 비교한다");
    fig(s, "model", M, TOP, 7.9, "최종 모델 구조: 기반 모델 v2의 세 성분, conformal 문턱, R2와 R1, 확률 층");
    card(s, M, 6.22, 7.9, 0.53, C.accent3, 92);
    tx(s, [
      { text: "경위 ", options: { bold: true } },
      { text: "R1·R2와 상수는 초기 탐색에서, v2의 초반 창·AR(2)·2행 기준은 v2를 만들 때 전체 이상 데이터를 본 뒤 정했다 → 이후 시간순 분할로 다시 평가하고 valid 선택을 해시로 잠갔다" },
    ], { x: M + 0.15, y: 6.27, w: 7.6, h: 0.45, fontSize: 11.5, valign: "middle" });
    const why = [
      ["세 성분 = 10Hz로 남는 세 정보", "켜진 성분이 곧 경보 근거가 된다. 대응 관계는 설계 뒤에 점검했다", C.accent1],
      ["R1 사건 지속 — 근거", "고장은 수집 공백(수 초) 사이에 사라지지 않는다. v2의 미탐은 기록 시작 직후에 몰린다. 해제는 전류 파형의 정상 확인(8행 이상)으로", C.accent2],
      ["R2 교차 확인 — 근거", "고부하 정상은 진동 크기만 커지고 전류 파형은 정상이다. 두 물리 채널이 함께 가리킬 때만 크기 경보를 낸다(과업 ②)", C.accent2],
    ];
    why.forEach(([h, b, col], i) => {
      const y = TOP + i * 1.42;
      card(s, 8.8, y, 3.933, 1.3, col, 90);
      tx(s, h, { x: 8.98, y: y + 0.1, w: 3.6, h: 0.34, fontSize: 13.5, bold: true, color: col });
      tx(s, b, { x: 8.98, y: y + 0.46, w: 3.6, h: 0.8, fontSize: 12 });
    });
    tx(s, "확률 층은 경보와 별도: 단조 회귀를 valid로 맞춘 이상 확률을 예측 파일 열로 낸다", { x: 8.8, y: 6.3, w: 3.933, h: 0.45, fontSize: 11.5, color: C.accent3 });
    s.addNotes("기반 모델 v2는 정상 데이터만으로 학습한다. 0.1초마다 크기(세 센서 표준화 최댓값), 파형(최근 6~8행 전류의 사인 적합 1−R²), 동역학(전류 AR(2) 예측 오차) 세 성분을 계산하고, 가장 드문 성분의 꼬리 점수를 valid 정상 기록으로 정한 conformal 문턱과 비교한다. 여기에 오류 분석에서 나온 두 규칙을 붙였다. R2는 크기만 넘고 전류 파형이 정상이면 경보를 보류하고, R1은 직전 기록이 확인된 이상이면 다음 기록 첫 행부터 경보를 이어받는다. 규칙과 상수는 전체 데이터를 본 뒤 정했다는 경위도 그대로 밝힌다. 근거: 보고서 2.3절, 그림 8.");
  }

  // ===== 10. 같은 조건 비교 =====
  {
    const s = content("2 AI 모델·성능", K2, "같은 분할·같은 보정에서 모델 비교", "모든 모델을 같은 시간순 분할, 같은 valid 보정(α 1%), 형식 누수를 지운 입력에서 test 실시간 행 F1로 채점했다");
    const L = ["IsolationForest", "LSTM 오토인코더(20행)", "max|z|(한 행)", "5NN 거리", "MLP 오토인코더(5행)", "v1(크기+파형)", "기반 모델 v2", "v2 + v3 조건부", "v2 + R1 (잠금 선택)", "v2+R1+R2 (최종·test 후 선정)"];
    const A = [0.133, 0.289, 0.404, 0.474, 0.498, 0.904, 0.965, 0.968, 1.0, 1.0];
    const B = [0.094, 0.238, 0.428, 0.487, 0.498, 0.912, 0.97, 0.955, 0.995, 1.0];
    s.addChart(pres.charts.BAR, [{ name: "분할 B", labels: L, values: B }, { name: "분할 A", labels: L, values: A }], {
      x: M, y: 1.98, w: 7.5, h: 4.85, barDir: "bar", barGrouping: "clustered", barGapWidthPct: 45,
      chartColors: [H.accent2, H.accent1],
      showValue: true, dataLabelFormatCode: "0.000", dataLabelFontSize: 9, dataLabelColor: H.accent3, dataLabelPosition: "outEnd", dataLabelFontFace: "+mn-lt",
      catAxisLabelFontSize: 11, catAxisLabelColor: H.dk1, catAxisLabelFontFace: "+mn-lt", catAxisLineShow: false,
      valAxisHidden: true, valAxisMinVal: 0, valAxisMaxVal: 1.13, valGridLine: { style: "none" }, catGridLine: { style: "none" },
      showLegend: true, legendPos: "t", legendFontSize: 11, legendFontFace: "+mn-lt", legendColor: H.accent3,
      showTitle: true, title: "test 실시간 행 F1 (α 1%)", titleFontSize: 12, titleColor: H.accent3, titleFontFace: "+mn-lt",
    });
    const pts = [
      "한 행만 보는 모델과 오토인코더는 실시간으로 이상 행 대부분을 놓친다(0.094~0.498)",
      "차이는 주로 기록 시작 직후 행을 얼마나 빨리 잡느냐에서 난다",
      "가이드북 방식 LSTM 오토인코더(20행 창)는 기록 앞 19행을 판정하지 못해 test 이상 324행 중 177행(54.6%)이 처음부터 미탐이다 — 창 길이와 점수 방식 영향이 크다",
      "v3 조건부 진동 성분은 A에서 조금 오르고 B에서 내려, 미리 잠근 판정 기준을 넘지 못했다",
    ];
    let y = TOP;
    const hs = [0.85, 0.6, 1.15, 0.85];
    y += 0.05;
    pts.forEach((p, i) => {
      num(s, i + 1, 8.4, y + 0.02, 0.38, C.accent1, 12);
      tx(s, p, { x: 8.95, y, w: 3.783, h: hs[i], fontSize: 13.5 });
      y += hs[i] + 0.3;
    });
    s.addNotes("베이스라인 5종(IsolationForest, 가이드북 방식 LSTM 오토인코더, max|z|, 5NN, MLP 오토인코더)과 우리 모델 계열을 모두 같은 분할·같은 보정으로 채점했다. 한 행만 보는 모델과 오토인코더는 실시간으로 이상 행 대부분을 놓쳐 0.5를 넘지 못했다. v2는 0.965·0.970이고 규칙을 붙이면 1.000까지 간다. LSTM 오토인코더가 낮은 데에는 20행 창 때문에 기록 앞부분을 판정하지 못하는 구조적 이유가 크다는 점도 함께 말한다. 근거: 보고서 2.4절 주 비교표, 그림 9.");
  }

  // ===== 11. 1.000을 읽는 법 =====
  {
    const s = content("2 AI 모델·성능", K2, "1.000을 어떻게 읽어야 하나", "R1은 어떤 점수 모델에도 붙는다. 베이스라인에 붙여 보니 test에서는 차이가 거의 사라졌다(사후 비교)");
    const b = (t) => ({ text: t, options: { bold: true } });
    table(s, ["앞단 모델 + R1", "valid F1", "test F1\nA / B", "test 오경보 행\nA / B", "test부터 따로\nA / B"], [
      ["IsolationForest", "0.426", "1.000 / 1.000", "0 / 0", "0.612 / 0.609"],
      ["LSTM 오토인코더", "0.918", "0.998 / 0.998", "1 / 1", "0.924 / 0.924"],
      ["MLP 오토인코더", "0.931", "0.986 / 0.986", "9 / 9", "0.914 / 0.914"],
      ["max|z|", "0.996", "1.000 / 0.995", "0 / 3", "1.000 / 0.995"],
      ["5NN 거리", "0.998", "0.998 / 0.982", "1 / 12", "0.998 / 0.982"],
      [b("v2 (= 잠금 선택)"), b("0.997"), b("1.000 / 0.995"), b("0 / 3"), b("1.000 / 0.995")],
    ], { x: M, y: TOP, w: 7.6, colW: [2.05, 1.05, 1.5, 1.55, 1.45], fontSize: 12, rowH: 0.44 });
    card(s, M, 5.32, 7.6, 1.2);
    tx(s, [
      { text: "R1을 붙인 뒤 남는 차이 ", options: { bold: true } },
      { text: "max|z|+R1도 v2+R1과 거의 같다. 그래서 v2의 파형·동역학 성분이 더하는 몫은 R1 없는 탐지(test 미탐 max|z| 242·235행 → v2 22·16행)와 R2의 파형 판정에 있다. 사건 앞부분을 포함한 valid에서는 IsolationForest+R1 0.426, v2+R1 0.997로 갈린다." },
    ], { x: M + 0.2, y: 5.42, w: 7.2, h: 1.02, fontSize: 12.5 });
    const pts = [
      ["test 1.000의 뜻", "이 사건에서 정상 오경보가 없고 경보가 끝까지 유지됐다는 뜻이다. test 이상 11기록은 60초 안 간격으로 이어진 한 사건이라, 경보가 한 번 켜지면 나머지 행은 앞단 모델과 상관없이 맞는다"],
      ["우열은 어디서 읽나", "R1 없는 값, 사건 앞부분을 포함한 valid, 정상 오경보로 읽는다. R1은 앞단의 오경보도 번지게 한다(B test 5NN 5→12행, MLP 2→9행)"],
      ["최종 모델은 설계 판단", "잠금 규칙(valid 차이 0.002 이내면 단순한 쪽)은 v2+R1을 골랐다. R2가 줄인 test 오경보 3행은 착안 때 본 행이라 표본 밖 근거가 아니다"],
    ];
    pts.forEach(([h, t], i) => {
      const y = TOP + i * 1.6;
      card(s, 8.5, y, 4.233, 1.48, i === 2 ? C.accent2 : C.accent1, 90);
      num(s, i + 1, 8.65, y + 0.12, 0.36, i === 2 ? C.accent2 : C.accent1, 12);
      tx(s, h, { x: 9.1, y: y + 0.1, w: 3.5, h: 0.4, fontSize: 13.5, bold: true, valign: "middle" });
      tx(s, t, { x: 8.68, y: y + 0.52, w: 3.92, h: 0.92, fontSize: 11.5 });
    });
    s.addNotes("심사위원이 가장 먼저 물을 질문에 먼저 답한다. R1을 베이스라인에 붙이면 IsolationForest도 test에서 1.000이 된다. test 이상 구간이 하나로 이어진 사건이라, 경보가 한 번 켜지면 R1이 끝까지 이어 주기 때문이다. 그래서 test 1.000은 '이 사건에서 오경보 없이 경보가 끝까지 유지됐다'로 읽고, 모델 우열은 사건 앞부분을 포함한 valid와 R1 없는 값, 정상 오경보로 읽는다. 또 최종 모델은 미리 정한 잠금 규칙이 아니라 test를 본 뒤의 설계 판단이었음을 숨기지 않는다. 근거: 보고서 2.4절 † 표, 2.5절.");
  }

  // ===== 12. 의심 검증 =====
  {
    const s = content("2 AI 모델·성능", K2, "다 맞았지만 의심했다: 검증 시험", "판정 기준은 실험 전에 정했고 모든 실험은 test 채점 이후에 했다 — 인공 고장 주입, 진폭 감소, 분할 변경, 수집 조건 흔들림");
    table(s, ["의심", "실험", "결과", "판정"], [
      ["정상 구간을 바꾸면 무너지나", "V3 분 단위 + 시간순 5창 (6개 분할)", "6개 분할 모두 정상 오경보 0, 이상 21/21, 행 F1 0.999~1.000", V.info("기술 (같은 이상 재사용, 2개 분할은 A·B와 구간 같음)")],
      ["R1이 경보를 퍼뜨리나", "V1a′ 한 기록에만 주입 후 다음 정상 기록 관찰", "이어받은 오경보 8행 이하로 해제 92.0%, 중앙 7행, 사슬 최대 2기록·14행", V.ok("기준 충족 (7행 기준은 미달)")],
      ["이어지는 이상에 R1이 도움 되나", "V1a 이어지는 3기록에 같은 주입", "전류 잔차 둘째·셋째 기록 v2 0.380·0.325 → v2+R1 0.422·0.418. 진동 대역 잡음 사슬은 최종이 v2보다 낮다(0.046 → 0.017)", V.info("기술")],
      ["규칙이 전류형 탐지를 해치나", "V1 전류 잔차 주입", "모든 강도·분할에서 v2 대비 −5%p 이내. 강도 0.5에서는 최종 모델도 2.5%·13.5%", V.ok("해치지 않음 (절대 탐지율은 낮음)")],
      ["R2가 진동형 고장을 숨기나", "V1b 진동 단독 주입", "v2+R1보다 최대 23.7%p 낮다(B 상부 감쇠 충격 0.350 → 0.113)", V.warn("기준 초과 → 적용 조건")],
      ["줄어드는 고장·센서 끊김은", "V2 진폭 감소(0.75~0배)", "최종 모델·v2 모두 탐지 0~2%", V.warn("못 잡음 → 적용 조건")],
      ["수집 조건 차이를 잡는 것 아닌가", "V5 전류 이동·표본 시각 흔들림·평균 제거", "이상 기록 평균을 지워도 21/21. 시각 0.1ms 흔들림에 정상 기록 경보율 A 8.8%·B 35.2%", V.warn("적용 조건 (파형·시각 교락은 배제 못 함)")],
      ["다른 설비에서도 되나", "UCI 유압 시험대에 v2 구조 이식", "AUROC 0.43~0.55", V.gray("검증 못 함")],
    ], { x: M, y: 2.0, w: CW, colW: [2.45, 2.6, 5.0, 2.083], fontSize: 11, rowH: 0.5 });
    s.addNotes("모든 것이 맞았을 때 오히려 의심했다. 의심마다 실험을 붙였고, 판정 기준은 실험 전에 정했다. 정상 구간을 바꿔도 오경보는 없었고, R1이 경보를 퍼뜨리는 정도는 기준 안이었으며, 규칙이 전류형 이상 탐지를 해치지도 않았다. 반대로 R2는 진동 단독 인공 주입의 탐지율을 최대 23.7%p 낮추고, 진폭이 줄어드는 고장과 수집 조건 변화에는 약하다. 이 약점들은 숨기지 않고 '적용 조건'으로 바꿔 현장 권고에 반영했다. 근거: 보고서 2.6절.");
  }

  // ===== 13. 영향 변수 =====
  pres.addSection({ title: "3 영향요인·오류분석" });
  const K3 = "3  영향요인 및 오류분석 · 15점";
  {
    const s = content("3 영향요인·오류분석", K3, "가장 강한 변수는 전류 파형이다", "진동은 크기와 시간 구조가 함께 바뀌고, 정상에서는 부하(전류)를 따른다 — 크기만 보면 고부하 정상과 이상을 헷갈린다");
    const tiles = [
      ["0.995 → 0.095", "전류 사인 적합 R² 중앙값 (정상 → 이상)", C.accent2],
      ["6.3배", "상부 진동 표준편차\n(전 행 합산 기준)", C.accent1],
      ["−0.031 → 0.686", "상부 진동 자기상관(lag-1) 중앙값 — 느린 흔들림으로", C.accent1],
      ["0.28 → −0.36", "상·하부 진동 상관 중앙값", C.accent1],
    ];
    tiles.forEach(([big, label, col], i) => {
      const x = M + (i % 2) * 2.75, y = TOP + Math.floor(i / 2) * 1.75;
      card(s, x, y, 2.55, 1.6);
      tx(s, big, { x: x + 0.18, y: y + 0.18, w: 2.25, h: 0.55, fontSize: 21, bold: true, color: col, valign: "middle" });
      tx(s, label, { x: x + 0.18, y: y + 0.82, w: 2.25, h: 0.7, fontSize: 12, color: C.accent3 });
    });
    tx(s, [
      { text: "기록 단위 AUROC ", options: { bold: true } },
      { text: "전류 사인 적합 R² 1.000 · 잔차 비율 1.000 · 상부 lag-1 0.945 · 하부 lag-1 0.923 · 상·하부 상관 0.859 · 상부 SD 0.825" },
    ], { x: M, y: 5.68, w: 5.3, h: 1.05, fontSize: 12.5 });
    fig(s, "loadvib", 6.2, TOP, 6.533, "부하(전류 RMS)와 진동 SD의 정상 관계, 그리고 벗어난 이상 기록");
    tx(s, [
      { text: "상호작용 ", options: { bold: true } },
      { text: "정상에서 하부 진동 SD는 전류의 약 1.73제곱에 비례한다(학습 R² 0.93) → 크기만 보면 고부하 정상과 이상을 헷갈린다. 부하 효과를 지워도 이상 기록은 정상 잔차 대비 z 중앙값 하부 8.09·상부 9.20(일부는 학습 범위 밖으로 늘린 값이고, 실제 부하 변화를 원인에서 뺄 수는 없다)." },
    ], { x: 6.2, y: 5.7, w: 6.533, h: 1.08, fontSize: 12 });
    s.addNotes("영향 변수를 정리하면, 가장 강한 것은 전류 파형이다. 정상 전류는 사인에 거의 완벽히 맞지만(R² 0.995) 이상에서는 0.095로 무너진다. 진동은 크기가 커질 뿐 아니라 느린 흔들림으로 바뀌고, 상·하부 관계가 음의 상관으로 뒤집힌다. 중요한 상호작용은 오른쪽 그림이다. 정상에서는 하부 진동이 부하를 따라 커지므로, 진동 크기만 보면 고부하 정상과 이상을 헷갈린다. 이것이 다음 장의 오경보 조건으로 이어진다. 근거: 보고서 2.2절, 3.1절, 그림 7.");
  }

  // ===== 14. 오경보 발생조건 =====
  {
    const s = content("3 영향요인·오류분석", K3, "오경보는 고부하 정상에 몰린다", "학습에 없던 정숙 구간(90기록)의 오경보는 10개 모델 × α 1·3·5%를 모두 합쳐 1행이었다");
    const ST = ["정숙 구간(90)", "저부하(58)", "중부하(77)", "고부하(53)", "짧은 기록(22)"];
    s.addChart(pres.charts.BAR, [
      { name: "max|z|", labels: ST, values: [0, 0, 2, 10, 0] },
      { name: "v2", labels: ST, values: [0, 0, 4, 9, 0] },
      { name: "v2 + R2", labels: ST, values: [0, 0, 2, 1, 0] },
      { name: "최종 v2+R1+R2", labels: ST, values: [0, 1, 2, 1, 0] },
    ], {
      x: M, y: 1.98, w: 7.0, h: 4.45, barDir: "col", barGrouping: "clustered", barGapWidthPct: 60,
      chartColors: [H.accent6, H.accent1, "8DB4E6", H.accent2],
      showValue: true, dataLabelFormatCode: "0", dataLabelFontSize: 10, dataLabelColor: H.accent3, dataLabelPosition: "outEnd", dataLabelFontFace: "+mn-lt",
      catAxisLabelFontSize: 11, catAxisLabelColor: H.dk1, catAxisLabelFontFace: "+mn-lt",
      valAxisMinVal: 0, valAxisMaxVal: 11, valAxisMajorUnit: 2, valAxisLabelFontSize: 10, valAxisLabelColor: H.accent3, valAxisLabelFontFace: "+mn-lt",
      valGridLine: { color: "E4E3E0", size: 0.5 }, catGridLine: { style: "none" },
      showLegend: true, legendPos: "t", legendFontSize: 11, legendFontFace: "+mn-lt", legendColor: H.accent3,
      showTitle: true, title: "오경보가 난 정상 기록 수 (운전 상태별)", titleFontSize: 12, titleColor: H.accent3, titleFontFace: "+mn-lt",
    });
    tx(s, "분할 B valid+test 300기록, 경보가 1행이라도 난 기록 수. 차이가 보이게 α 5%로 셌다(사후). 부하 등급 경계 127.2·225.1", { x: M, y: 6.45, w: 7.0, h: 0.32, fontSize: 10.5, color: C.accent3 });
    bullets(s, [
      { b: "집중:", t: "단일 모델 7개(분할 B, α 5%)의 오경보 기록 중 66%가 고부하, 33%가 중부하" },
      { b: "비율:", t: "고부하 기록 오경보 14.0%(95% 10.6~18.0%) — 전체 3.8%의 3.7배(같은 기록을 모델마다 겹쳐 센 참고 구간)" },
      { b: "원인:", t: "α 1% v2 오경보 기록 4개는 모두 상부 진동 SD가 학습의 98.6~99.6% 분위. 위험한 '학습 분포 밖'은 아래(정숙)가 아니라 위(더 센 부하)다" },
      { b: "R2 효과:", t: "고부하 오경보 기록 9/53 → 1/53(착안 때 본 자료 안의 확인). test 미탐은 α 1·3·5% 모두 v2와 같다", c: C.accent2 },
      { b: "R1 비용:", t: "α 5%에서 중부하 경보가 다음 저부하 기록 앞 7행으로 번졌다 → 운영 α를 1%로 두는 근거 중 하나", c: C.accent2 },
    ], { x: 7.9, y: TOP, w: 4.833, h: 4.67, fontSize: 13.5, gap: 9 });
    s.addNotes("과업 ②의 핵심인 오경보 발생 조건이다. 정상 기록을 운전 상태별로 나눠 모델마다 오경보를 셌다. 예상과 달리 학습에 없던 정숙 구간은 오경보를 거의 내지 않았다. 진동이 작고 전류 파형이 정상이라 이상 점수가 오히려 낮다. 오경보는 고부하 정상에 몰렸고, 원인은 상부 진동이 학습 상위 꼬리에 닿을 때 크기 성분만 단독으로 울리는 경보였다. R2는 바로 이 경보를 전류 파형으로 한 번 더 걸러 고부하 오경보 기록을 9개에서 1개로 줄였다. R1이 경보를 다음 기록으로 번지게 하는 비용도 함께 쟀다. 근거: 보고서 3.2절.");
  }

  // ===== 15. 미탐 조건과 규칙 효과 =====
  {
    const s = content("3 영향요인·오류분석", K3, "미탐은 기록 시작 직후에 몰린다", "과거 행이 없는 기록 첫 1~2행은 크기 성분만 계산되는데, 이상 기록 상당수는 진동이 오히려 작다");
    fig(s, "miss", M, TOP, 6.0, "v2 미탐의 기록 안 위치");
    card(s, M, 5.42, 6.0, 1.33);
    tx(s, [
      { text: "맞물린 오류 ", options: { bold: true } },
      { text: "진동 크기만 보면 진동이 커진 정상(고부하)은 오경보, 진동이 작아진 이상(기록 3·19·20)은 미탐이 된다. '너무 작음'까지 경보하면 정숙 구간이 오경보가 된다(A 28·B 27기록). 진동은 같은 순간의 부하·전류 파형에 비춰 봐야 하고, R2가 그 최소 구현이다." },
    ], { x: M + 0.2, y: 5.52, w: 5.6, h: 1.17, fontSize: 12 });
    tx(s, "규칙별 효과 분해 (test, α 1%)", { x: 6.9, y: TOP, w: 5.833, h: 0.36, fontSize: 14, bold: true });
    const b = (t) => ({ text: t, options: { bold: true } });
    table(s, ["모델", "미탐 행\nA / B", "오경보 행\nA / B", "F1\nA / B"], [
      ["v2", "22 / 16", "0 / 3", "0.965 / 0.970"],
      ["v2 + R2", "22 / 16", "0 / 0", "0.965 / 0.975"],
      ["v2 + R1", "0 / 0", "0 / 3", "1.000 / 0.995"],
      [b("v2 + R1 + R2"), b("0 / 0"), b("0 / 0"), b("1.000 / 1.000")],
    ], { x: 6.9, y: 2.52, w: 5.833, colW: [1.6, 1.4, 1.4, 1.433], fontSize: 12.5, rowH: 0.42 });
    card(s, 6.9, 4.8, 2.8, 0.88, C.accent1, 88);
    tx(s, [{ text: "R1 → 미탐 0", options: { bold: true, color: C.accent1, fontSize: 16, breakLine: true } }, { text: "test 미탐 A 22·B 16행 → 0" }], { x: 7.05, y: 4.88, w: 2.55, h: 0.75, fontSize: 12, valign: "middle" });
    card(s, 9.933, 4.8, 2.8, 0.88, C.accent2, 88);
    tx(s, [{ text: "R2 → 오경보 0", options: { bold: true, color: C.accent2, fontSize: 16, breakLine: true } }, { text: "test 오경보 B 3행 → 0" }], { x: 10.083, y: 4.88, w: 2.55, h: 0.75, fontSize: 12, valign: "middle" });
    tx(s, "v2 미탐은 기록 위치 0~1에 A 14행·B 12행. 최종 모델의 valid 미탐 1행은 사건의 첫 표본이다(이어받을 직전 기록이 없음).", { x: 6.9, y: 5.85, w: 5.833, h: 0.9, fontSize: 12.5, color: C.accent3 });
    s.addNotes("미탐은 기록 시작 직후에 몰린다. 기록 첫 한두 행은 과거 행이 없어 크기 성분만 계산되는데, 이 사건의 일부 기록은 진동이 오히려 정숙 구간보다 작다. 그래서 크기만 보는 판정은 고부하 정상을 오경보로, 진동이 작은 이상을 미탐으로 만든다. 두 오류가 같은 뿌리에서 나온다는 점이 핵심이다. 오른쪽 분해표처럼 R1은 미탐을, R2는 오경보를 각각 없앤다. 근거: 보고서 3.3~3.4절, 그림 10·11.");
  }

  // ===== 16. 적용 조건과 한계 =====
  {
    const s = content("3 영향요인·오류분석", K3, "적용 조건과 한계", "1.000은 단일 고장 사건, 행 단위, α 1%에서의 결과다 — 약한 조건마다 보완책을 붙였다");
    card(s, M, TOP, 3.75, 4.67, C.accent4, 88);
    icon(s, "LuCheck", M + 0.22, TOP + 0.22, 0.55, C.accent4);
    tx(s, "잘 작동하는 조건", { x: M + 0.9, y: TOP + 0.27, w: 2.7, h: 0.45, fontSize: 15, bold: true, color: C.accent4, valign: "middle" });
    bullets(s, [
      "고장이 여러 기록에 걸쳐 이어진다",
      "전류 파형도 함께 흐트러진다",
      "수집 조건이 학습 때와 같다",
      "분할 경계를 바꿔도 정상 오경보 0, 이상 21/21 (V3, 같은 이상 재사용)",
      "학습에 없던 정숙 구간에서는 오경보가 거의 없다 (3.2절, 사후)",
    ], { x: M + 0.25, y: TOP + 1.0, w: 3.3, h: 3.5, fontSize: 13.5, gap: 10 });
    const rows = [
      ["진동만 나타나는 고장", "R2가 진동 단독 주입 탐지율을 최대 23.7%p 낮춘다. R2를 빼도 B 최대 35.0%", "별도 진동 모델, 수 kHz 진동 파형(수집 개선 ④)"],
      ["진폭 감소·센서 끊김", "세 성분은 커지거나 흐트러지는 변화만 본다. 탐지 0~2%(V2)", "센서 건전성 규칙(수집 개선 ②)"],
      ["파형을 유지한 마모", "측판·끝면 마모의 문헌 서명은 전류 감소 — R2가 크기 경보를 보류할 수 있다", "전류 진폭 기준선의 주·월 추세(검증 안 한 제안)"],
      ["수집 조건 변화", "표본 시각 0.1ms 흔들림에 정상 기록 경보율 B 35.2%(V5)", "현장 정상 데이터로 재보정, 표본화 시각 동기화"],
    ];
    rows.forEach(([h, e, fix], i) => {
      const y = TOP + i * 1.2, hh = 1.08;
      card(s, 4.6, y, 4.6, hh, C.accent2, 90);
      tx(s, h, { x: 4.78, y: y + 0.1, w: 4.25, h: 0.34, fontSize: 14, bold: true, color: C.accent2 });
      tx(s, e, { x: 4.78, y: y + 0.46, w: 4.25, h: 0.58, fontSize: 12 });
      arrow(s, 9.27, y + 0.4, 0.2, 0.26);
      card(s, 9.6, y, 3.133, hh, C.accent1, 90);
      tx(s, "보완", { x: 9.78, y: y + 0.1, w: 2.8, h: 0.28, fontSize: 11, bold: true, color: C.accent1 });
      tx(s, fix, { x: 9.78, y: y + 0.4, w: 2.8, h: 0.62, fontSize: 12.5 });
    });
    s.addNotes("모델이 잘 되는 조건과 약한 조건을 나눠 정리했다. 잘 되는 조건은 고장이 여러 기록에 걸쳐 이어지고 전류 파형도 흐트러지며 수집 조건이 학습 때와 같을 때다. 약한 조건은 네 가지다. 진동만 나타나는 고장, 진폭이 줄거나 센서가 끊기는 경우, 파형을 유지한 채 진행하는 마모, 수집 조건 변화. 각각 오른쪽의 보완책을 현장 권고로 연결했다. 데이터에 없는 정보(모터·펌프 사양, 압력·유온·유량, 센서 단위·축, 실제 표본 간격, 운전 상태 코드, 고장 이력)는 보고서 3.5절 표에 정리했다. 근거: 보고서 3.5~3.6절.");
  }

  // ===== 17. 경보에서 조치까지 =====
  pres.addSection({ title: "4 현장 활용" });
  const K4 = "4  현장 활용방안 · 10점";
  {
    const s = content("4 현장 활용", K4, "경보에서 조치까지", "ISO 13374-1 처리 블록에 맞춘 운영 흐름 — 이번 범위는 데이터 획득~상태 감지, 건강 평가는 진단 매트릭스 수준까지");
    const blocks = [
      ["데이터 획득", "PLC 초당 10회, 진동 2·전류 1"],
      ["데이터 처리", "정밀도 맞춤, 기록 분할, 세 성분 계산"],
      ["상태 감지", "v2 conformal 문턱 + R1·R2, 운영 α 1%"],
      ["건강 평가", "경보 근거 → 진단 매트릭스로 점검 우선순위"],
      ["예지", "하지 않음 — 고장 1건으로는 잔여 수명을 추정할 수 없다"],
      ["조언 생성", "경보 단계별 점검·품질 조치"],
    ];
    const bw = 1.84, gap = (CW - 6 * bw) / 5;
    blocks.forEach(([h, b], i) => {
      const x = M + i * (bw + gap), gray = i === 4;
      card(s, x, TOP, bw, 1.45, gray ? C.background1 : C.accent1, gray ? 0 : 90, gray ? { line: { color: H.accent6, width: 1, dashType: "dash" } } : {});
      tx(s, h, { x: x + 0.12, y: TOP + 0.1, w: bw - 0.24, h: 0.35, fontSize: 13.5, bold: true, color: gray ? C.accent3 : C.accent1 });
      tx(s, b, { x: x + 0.12, y: TOP + 0.48, w: bw - 0.24, h: 0.92, fontSize: 12, color: gray ? C.accent3 : C.text1 });
      if (i < 5) arrow(s, x + bw + gap / 2 - 0.07, TOP + 0.6, 0.14, 0.2);
    });
    tx(s, "60초 안에 이어지는 경보는 한 사건으로 묶는다. 담당·절차는 v2 운영 문서의 절차를 가져온 제안이다.", { x: M, y: 3.64, w: CW, h: 0.3, fontSize: 11.5, color: C.accent3 });
    const stages = [
      ["1단계 · 주의", "사건의 첫 경보", ["콘솔 기록, 품질 샘플 검사 앞당김", "사람은 부르지 않는다", "약한 진동형 고장이 여기 머물 수 있어 기록은 남긴다"], C.accent5],
      ["2단계 · 점검 요청", "사건 안 경보가 2행에 이르면", ["운전원: 운전 중 점검 항목", "보전원: 그 교대 안에 [정지] 항목", "품질: 의심 시간대 가공품 보류 → 전단면·버·치수 확인"], C.accent2],
      ["종료 · 점검자 확인", "R1 자동 해제는 화면 표시만 끈다", ["확인 시각·담당·결과(정상 확인·이상 확인·보류)·조치 기록", "정상 확인 구간 → 다음 재보정 자료", "이상 확인 사건 → 고장 라벨로 축적"], C.accent3],
    ];
    const sw = 3.82, sg = (CW - 3 * sw) / 2;
    stages.forEach(([h, trig, items, col], i) => {
      const x = M + i * (sw + sg), y = 4.05;
      card(s, x, y, sw, 2.7, col, 90);
      tx(s, h, { x: x + 0.2, y: y + 0.12, w: sw - 0.4, h: 0.4, fontSize: 16, bold: true, color: col });
      tx(s, trig, { x: x + 0.2, y: y + 0.54, w: sw - 0.4, h: 0.32, fontSize: 13, bold: true });
      bullets(s, items, { x: x + 0.2, y: y + 0.95, w: sw - 0.4, h: 1.7, fontSize: 12.5, gap: 5 });
      if (i < 2) arrow(s, x + sw + sg / 2 - 0.08, y + 1.2, 0.16, 0.24);
    });
    s.addNotes("현장 운영은 상태감시 표준 ISO 13374-1의 처리 블록에 맞췄다. 예지, 즉 잔여 수명 추정은 고장이 한 건뿐이라 하지 않는다고 분명히 적었다. 경보는 두 단계다. 사건의 첫 경보는 '주의'로 기록과 품질 샘플 검사만 앞당기고, 사건 안 경보가 2행에 이르면 '점검 요청'으로 운전원과 보전원이 움직인다. R1의 자동 해제는 화면 표시만 끄고, 사건은 점검자가 결과를 적어야 닫힌다. 이렇게 쌓인 확인 결과가 다음 재보정 자료와 고장 라벨이 된다. 근거: 보고서 4.1~4.2절.");
  }

  // ===== 18. 점검 순서 =====
  {
    const s = content("4 현장 활용", K4, "경보 근거와 이상 양상별로 먼저 볼 곳", "계측·수집 이상을 배제할 수 없어 운전 중에 볼 수 있는 계측 항목부터 시작하고, [정지] 항목은 보전원이 교대 안에 본다");
    const head = (a, b) => ({ text: [{ text: a, options: { bold: true, breakLine: true } }, { text: b, options: { color: C.accent3, fontSize: 11 } }] });
    table(s, ["경보 근거 · 확인 대상(가설)", "점검 순서 (운전 중 → [정지])"], [
      [head("크기(진동 센서)", "기어 마모·체결·베어링·부하 변화, 센서 부착 이상"), "센서 부착·케이블 → 베어링 소음·온도 → 작동유 레벨·온도 → [정지] 체결 볼트·커플링 정렬"],
      [head("전류 파형·예측 오차", "모터·전원·계측·수집 시각, 출력 유압 불안정"), "수집 장비 표본화 시각 → 출력 압력 안정성 → 릴리프 밸브 → [정지] 전류센서 영점·접지"],
      [head("전류 치우침·순시값 범위 초과", "전류센서 영점 이동·포화, 고압 유지 부하"), "전류센서 체결·케이블 → 램 정지 상태의 릴리프 작동 여부 → [정지] 무전류 상태의 전류센서 영점·포화"],
      [head("진동 + 전류 함께", "캐비테이션·에어레이션, 기어 마모로 유압 약화, 계측·수집 변화"), "센서 부착·수집 설정 → 흡입측 소리(고음은 캐비테이션, 불규칙한 소음은 에어레이션)·유면·거품 → 출력 유압 → [정지] 흡입 필터·작동유 오염 → 전류센서 영점"],
    ], { x: M, y: TOP, w: 7.5, colW: [2.6, 4.9], fontSize: 12, rowH: [0.4, 0.88, 0.88, 0.88, 1.02] });
    tx(s, "이번 사건의 이상 양상", { x: 8.4, y: TOP, w: 4.333, h: 0.34, fontSize: 14, bold: true });
    tx(s, "10행 이상 17기록 · 정상 분포 0.5~99.5% 기준 (사후)", { x: 8.4, y: 2.42, w: 4.333, h: 0.3, fontSize: 11, color: C.accent3 });
    const pats = [
      ["상·하부 진동 모두 큼 · 9기록", "흡입측(흡입 필터·유면·흡입 배관 공기 유입) → 펌프 소음 → [정지] 커플링"],
      ["상부 진동만 큼 · 5기록", "상부 센서 쪽 체결·지지와 센서 부착 → [정지] 커플링 정렬 → 흡입측"],
      ["진동 정상·작음, 전류만 이상 · 3기록", "전류센서 영점·배선, 모터 전원 → 램 정지 상태의 고압 유지 여부"],
    ];
    pats.forEach(([h, b], i) => {
      const y = 2.85 + i * 1.22;
      card(s, 8.4, y, 4.333, 1.1);
      tx(s, h, { x: 8.58, y: y + 0.1, w: 4.0, h: 0.32, fontSize: 13, bold: true, color: C.accent2 });
      tx(s, b, { x: 8.58, y: y + 0.44, w: 4.0, h: 0.62, fontSize: 12 });
    });
    tx(s, "양상은 한 사건 안에서 기록마다 바뀐 모습이며 고장 종류가 아니다. 신호가 가리키는 부위부터 보는 현장 관례에 따른 추정이다.", { x: M, y: 6.5, w: CW, h: 0.3, fontSize: 11, color: C.accent3 });
    s.addNotes("경보가 울렸을 때 무엇부터 볼지다. 왼쪽은 켜진 성분, 즉 경보 근거별 점검 순서다. 앞서 본 진단 매트릭스에서 계측·수집 이상을 배제할 수 없었기 때문에, 어느 근거든 운전 중에 확인할 수 있는 계측 항목부터 보게 했다. 오른쪽은 이번 사건 기록을 진동 양상으로 묶어 본 것으로, 같은 경보라도 양상에 따라 먼저 볼 곳을 좁힌다. 다만 한 사건 안의 양상이라 고장 종류를 뜻하지는 않는다. 근거: 보고서 4.2절 두 표.");
  }

  // ===== 19. 점검 콘솔 =====
  {
    const s = content("4 현장 활용", K4, "점검 콘솔과 경보 카드", "v2의 로컬 웹 콘솔(Press Guard): 우선순위순 사건 대기열, 경보 근거·정상 기준 대비 편차·권장 점검, 결과 양식, 기록 재생");
    figH(s, "console", M, TOP, 4.67, "점검 콘솔 화면: 사건 대기열, 경보 근거, 권장 점검");
    fig(s, "card", 6.65, TOP, 6.083, "최종 모델 경보 카드: 이상 기록 11과 정상 기록 423");
    bullets(s, [
      { b: "콘솔:", t: "분할 B 정상 test와 이상 21기록을 v2 기준으로 분석한 화면. 이상 사건 1건이 2단계 '점검 요청', 고부하·중부하 정상 3건이 1단계 '주의' — 이 3건이 R2가 거르는 경보다" },
      { b: "경보 카드:", t: "(a) 이상 기록 11은 v2가 끊긴 행까지 R1이 채워 기록 전체가 2단계 (b) 정상 기록 423은 크기만 넘은 v2 경보를 R2가 보류" },
      { b: "주의:", t: "이상 확률 55.0%는 표시 상한이며 고장 확률이 아니다. 콘솔의 R1·R2 반영은 도입 전 작업이고, 설비 제어 명령은 보내지 않는다", c: C.accent2 },
    ], { x: 6.65, y: 4.78, w: 6.083, h: 1.97, fontSize: 12, gap: 6 });
    s.addNotes("모의 운용까지 해 볼 수 있는 형태도 만들었다. 왼쪽은 로컬에서 도는 점검 콘솔로, 사건을 우선순위순 대기열로 보여 주고 사건마다 어떤 성분이 켜졌는지, 정상 기준에서 얼마나 벗어났는지, 무엇을 점검할지를 보여 준다. 오른쪽 경보 카드는 최종 모델이 행 단위로 어떻게 판단했는지를 보여 준다. 이상 기록은 R1 덕에 기록 전체가 경보이고, 정상 기록 423의 크기 단독 경보는 R2가 보류했다. 콘솔은 아직 v2 기준이라 R1·R2 반영은 도입 전에 할 일로 남겨 두었다. 근거: 보고서 4.2절, 그림 12·13.");
  }

  // ===== 20. 운영 기준과 수집 개선 =====
  {
    const s = content("4 현장 활용", K4, "경보 운영 기준과 수집 개선 순서", "추가 센서 없이 진동 2·전류 1채널로 동작한다 — 다른 설비에는 그 설비 정상 데이터로 다시 맞춰 옮긴다(외부 검증은 못 함)");
    card(s, M, TOP, 4.95, 1.5);
    tx(s, "시간당 약 3.7기록", { x: M + 0.22, y: TOP + 0.14, w: 4.5, h: 0.55, fontSize: 24, bold: true, color: C.accent1, valign: "middle" });
    tx(s, "α 1% 설계 오경보를 연속 운전에 옮긴 참고치(묶음 전 기록 수) — 운전원 경보 예산(시간당 약 6건)의 약 60%", { x: M + 0.22, y: TOP + 0.75, w: 4.5, h: 0.65, fontSize: 12, color: C.accent3 });
    bullets(s, [
      { b: "도입 첫 달:", t: "단계별 경보 사건을 기록하고 넘치면 α를 낮춘다(1% 미만은 보정용 정상 기록이 120개보다 많아야 한다)" },
      { b: "경보 시각:", t: "첫 경보 0.0초는 데이터 시각 기준이다. 기록이 최대 5초씩 묶여 올라오는 구조라면(추정) 화면에는 그만큼 늦을 수 있다" },
      { b: "운전 상태 연동:", t: "PLC 행정·대기 신호를 받으면 운전 상태별 기준을 둘 수 있다" },
      { b: "다른 설비로:", t: "그 설비의 정상 데이터로 표준화·문턱을 다시 맞춘다. 단, 느린 누설을 다룬 UCI 유압 시험대에는 옮겨지지 않았다" },
    ], { x: M, y: 3.78, w: 4.95, h: 2.97, fontSize: 12.5, gap: 7 });
    tx(s, "데이터 수집 개선 — 비용이 적은 순서 (①·②는 장비 추가 없음)", { x: 5.9, y: TOP, w: 6.833, h: 0.36, fontSize: 14, bold: true });
    const steps = [
      ["①", "설정 변경", "연속 수집, 실측 타임스탬프, 행정·대기 신호, 저장 형식 통일, 진동 필터 사양 확인", "기록 시작 직후 미탐, 경보 지연, 수집 조건 민감도, 운전 상태별 오경보, 형식 누수", C.accent1],
      ["②", "규칙 추가", "센서 건전성 규칙, 전류 진폭 기준선 추세", "진폭 감소·센서 끊김, 파형을 유지한 마모", C.accent1],
      ["③", "센서 추가", "토출 압력·유온, 이어서 흡입 압력·유량", "기록 19·20의 원인, 기동·예열 판별, 캐비테이션·체적효율", C.accent2],
      ["④", "장비 교체", "수 kHz 진동 파형이나 대역 스펙트럼, 전류 실효값", "진동 단독 고장, 맞물림 측대역·1X 위상", C.accent2],
    ];
    steps.forEach(([n, name, act, fill, col], i) => {
      const y = 2.52 + i * 1.07;
      s.addText([{ text: n, options: { fontSize: 18, breakLine: true } }, { text: name, options: { fontSize: 12 } }], { shape: SH.ROUNDED_RECTANGLE, x: 5.9, y, w: 1.35, h: 0.97, rectRadius: 0.08, fill: { color: col }, line: { type: "none" }, color: C.background1, bold: true, align: "center", valign: "middle", margin: 0 });
      card(s, 7.35, y, 5.383, 0.97);
      tx(s, act, { x: 7.52, y: y + 0.08, w: 5.05, h: 0.45, fontSize: 12.5, bold: true });
      tx(s, "메우는 실패 조건: " + fill, { x: 7.52, y: y + 0.52, w: 5.05, h: 0.42, fontSize: 11, color: C.accent3 });
    });
    s.addNotes("운영 기준을 숫자로 정했다. α 1% 보정을 연속 운전에 옮기면 설계상 오경보는 시간당 약 3.7기록으로, 산업 경보 관리에서 운전원 한 명이 감당할 수 있다고 보는 시간당 약 6건의 60% 정도다(묶음 전 기록 수 기준의 참고치). 실제 값은 이 데이터로 확인할 수 없어 도입 첫 달에 직접 세고 조정하도록 했다. 오른쪽은 데이터 수집 개선 권고를 비용이 적은 순서로 정리하고, 각 단계가 앞서 찾은 어떤 실패 조건을 메우는지 연결한 것이다. 근거: 보고서 4.3~4.4절.");
  }

  // ===== 21. 가이드북 대비 =====
  pres.addSection({ title: "5 창의성·차별성" });
  const K5 = "5  창의성 및 차별성 · 10점";
  {
    const s = content("5 창의성·차별성", K5, "가이드북 기본 틀과 무엇이 다른가", "점수는 조건이 달라 직접 비교하지 않고 방법만 대조한다(가이드북 LSTM 오토인코더 자체 결과 F1 74.76%)");
    const ours = (t) => ({ text: t, options: { fill: { color: "EAF1FB" } } });
    const k = (t) => ({ text: t, options: { bold: true } });
    table(s, ["항목", "가이드북 기본 틀", "이 작업"], [
      [k("분할"), "정상 앞부분으로 학습, 나머지 정상과 이상을 임곗값용 창과 평가용 창으로 나눔", ours("정상 기록을 시간순 train/valid/test로 나누고 valid 선택을 해시로 잠근 뒤 test 채점")],
      [k("평가 단위"), "20행 창이 수집 공백을 가로지르고 창 단위로 판정", ours("형식 누수를 지운 입력에서 기록 안 행마다 실시간 판정. point-adjust는 쓰지 않음(R1이 주는 비슷한 이득은 따로 밝힘)")],
      [k("모델 점수"), "LSTM 오토인코더 복원 오차", ours("크기·파형·동역학 세 성분의 꼬리 점수 최댓값 — 켜진 성분이 경보 근거")],
      [k("문턱"), "이상 라벨이 든 검증 창으로 임곗값을 고름", ours("정상 valid 기록만으로 conformal 문턱(α 1%), α 1·3·5% 민감도 보고")],
      [k("오경보 분석"), "혼동행렬의 오경보 수까지. 발생 조건은 다루지 않음", ours("운전 상태별·모델별 오경보와 원인(크기 성분 단독 경보)을 R2와 운영 α로 연결")],
      [k("검증"), "평가 구간 한 번의 채점 결과", ours("베이스라인·표준 기법 대조, 인공 고장 주입·진폭 감소·분할 변경·수집 조건 흔들림, 오경보 이항·포아송 상한")],
      [k("재현"), "초기 가중치가 실행마다 달라 결과가 소폭 다를 수 있음", ours("명령 하나로 예측 파일·수치 대조까지. 새 가상환경에서 수치 26개 일치, 예측 파일 바이트 동일")],
    ], { x: M, y: TOP, w: CW, colW: [1.55, 4.3, 6.283], fontSize: 12.5, rowH: 0.6 });
    s.addNotes("가이드북 실습과 방법을 나란히 놓았다. 점수는 조건이 달라 비교하지 않는다. 가장 큰 차이는 평가 방식이다. 우리는 형식 누수를 지운 입력에서, 창이 수집 공백을 가로지르지 않는 기록 안 실시간 행 판정으로, 정상 자료만으로 정한 문턱으로 채점했다. 그리고 가이드북에 없는 오경보 발생 조건 분석과 의심 검증, 한 명령 재현을 더했다. 근거: 보고서 5장 대조표.");
  }

  // ===== 22. 차별점 네 가지 =====
  {
    const s = content("5 창의성·차별성", K5, "숫자 뒤의 원인까지 잰 네 가지 시도", "데이터의 약점을 숨기지 않고 재서, 운영 조건과 개선 권고로 이었다");
    const cards = [
      ["LuWaves", "신호 물리로 표본 간격 역산", "약 99 · 101ms", "전류 겉보기 0.600Hz를 60Hz 계열의 접힘으로 보면(홀수 고조파 3·5·7배) 표본 간격은 약 99·101ms다 → 시각은 계산값으로 보여(추정) 실측 타임스탬프를 수집 개선 첫 단계에 넣었다"],
      ["LuSplit", "세션 교락의 크기 측정", "ROC-AUC 0.75~0.87", "라벨 지도학습은 F1 0.793~0.970을 냈지만, 고장 없는 같은 날 정상끼리도 약 1시간 떨어지면 이만큼 갈랐다 → 지도학습 점수는 성능 비교에서 뺐다"],
      ["LuRepeat", "표준 기법 대조와 R1의 해제", "0.7초 vs 11.4~12.2분", "CUSUM·EWMA도 기록 간 상태를 이어 가면 R1 수준 → 이득의 핵심은 수집 공백을 넘는 기억이다. 고장 뒤 정상 기록을 이어 붙인 가상 흐름(사후)에서 R1은 0.7초, 상한·리셋 없는 표준형 CUSUM은 11.4~12.2분"],
      ["LuGauge", "오경보 상한을 운영 단위로", "2.47% · 1.65%", "정상 오경보 0/120·0/180의 이항 95% 상한과 시간당 포아송 95% 상한(11.2·7.5건)을 경보 관리 기준(운전원당 시간당 약 6건)과 견줬다(기록 독립·사건률 일정 가정의 참고값) → 더 긴 정상 기록이 필요함을 보였다"],
    ];
    const w = (CW - 0.3) / 2, h = (4.67 - 0.25) / 2;
    cards.forEach(([ic, head, big, body], i) => {
      const x = M + (i % 2) * (w + 0.3), y = TOP + Math.floor(i / 2) * (h + 0.25);
      card(s, x, y, w, h);
      icon(s, ic, x + 0.25, y + 0.22, 0.55, C.accent1);
      tx(s, head, { x: x + 0.95, y: y + 0.27, w: w - 1.2, h: 0.45, fontSize: 15, bold: true, valign: "middle" });
      tx(s, big, { x: x + 0.25, y: y + 0.82, w: w - 0.5, h: 0.45, fontSize: 22, bold: true, color: C.accent2, valign: "middle" });
      tx(s, body, { x: x + 0.25, y: y + 1.3, w: w - 0.5, h: 0.85, fontSize: 11.5 });
    });
    s.addNotes("차별점을 네 가지로 압축했다. 첫째, 전류 고조파 구조로 표본 간격을 역산해 시각이 계산값임을 밝혔다. 둘째, 지도학습이 높은 점수를 내지만 고장 없는 정상끼리도 1시간 떨어지면 갈라진다는 것을 재서, 세션 차이가 얼마나 큰지를 수치로 보였다. 셋째, CUSUM·EWMA와 비교해 이득의 핵심이 '수집 공백을 넘는 기억'임을 보였다. 사후 가상 흐름에서 해제는 R1 0.7초, EWMA 0.2~0.3초, 상한·리셋 없는 표준형 CUSUM 11.4~12.2분이었고, R1의 해제는 고장 규모가 아니라 전류 파형의 정상 확인에 묶인다. F1로는 셋을 가를 수 없었다. 넷째, 오경보 0이라는 결과를 그대로 믿지 않고 통계 상한을 운영 단위로 바꿔 경보 관리 기준과 견줬다. 근거: 보고서 5장.");
  }

  // ===== 23. 재현성 =====
  pres.addSection({ title: "6 재현성" });
  {
    const s = content("6 재현성", "6  코드 구성 및 재현성 · 10점", "명령 하나로 전처리부터 수치 대조까지", "압축을 풀고 패키지를 설치한 뒤 run_all.py 하나로 전처리 → 학습 → 추론 → test 예측 파일 → 보고서 수치 대조까지 끝난다");
    s.addText([
      { text: "$ pip install -r requirements.txt", options: { breakLine: true } },
      { text: "$ python run_all.py          # 전체, 약 56분", options: { breakLine: true } },
      { text: "$ python run_all.py --quick  # 약 13분" },
    ], { shape: SH.ROUNDED_RECTANGLE, x: M, y: TOP, w: 5.75, h: 1.3, rectRadius: 0.08, fill: { color: C.text2 }, line: { type: "none" }, color: C.background1, fontFace: "Courier New", fontSize: 13, valign: "middle", margin: [0, 0.25, 0, 0.25], paraSpaceAfter: 4 });
    const tiles = [
      ["26 / 26", "보고서 수치 대조 일치 (새 가상환경, Windows 11)"],
      ["바이트 동일", "제출 test 예측 파일 (줄바꿈 맞춘 뒤 비교)"],
      ["Python 3.13", "패키지 판 고정 · seed 고정 · 원본 CSV 해시 확인"],
      ["0.961938 / 0.970990", "v2 원래 평가 F1 A / B가 같은 코드로 재현"],
    ];
    tiles.forEach(([big, label], i) => {
      const x = M + (i % 2) * 2.95, y = 3.6 + Math.floor(i / 2) * 1.6;
      card(s, x, y, 2.8, 1.45);
      tx(s, big, { x: x + 0.18, y: y + 0.15, w: 2.45, h: 0.5, fontSize: i === 3 ? 15 : 20, bold: true, color: C.accent1, valign: "middle" });
      tx(s, label, { x: x + 0.18, y: y + 0.72, w: 2.45, h: 0.66, fontSize: 12, color: C.accent3 });
    });
    tx(s, "run_all.py가 도는 4단계", { x: 6.75, y: TOP, w: 5.983, h: 0.36, fontSize: 14, bold: true });
    const steps = [
      ["진단", "cases/01·03, 06_alias_frequency_audit", "기록 구조, 형식 누수, 겉보기 주파수"],
      ["모델", "tvt/01 → 02 → 03 → 05 → 08", "정상 학습, valid 보정·선택·해시 잠금, 잠금 확인 후 test 채점, 예측 파일, 이상 확률"],
      ["검증", "tvt/04", "인공 고장 주입, 분할 변경, 수집 조건 흔들림"],
      ["사후 분석", "domain/01~07, tvt/06·07", "신호 물리, PCA·CUSUM·EWMA, 지도학습 대조, 운전 상태별 오경보, R1을 붙인 베이스라인"],
    ];
    steps.forEach(([name, scr, desc], i) => {
      const y = 2.52 + i * 0.95;
      card(s, 6.75, y, 5.983, 0.86);
      num(s, i + 1, 6.9, y + 0.21, 0.46, C.accent1, 14);
      tx(s, [{ text: name + "  ", options: { bold: true, fontSize: 13.5 } }, { text: scr, options: { fontFace: "Courier New", fontSize: 11, color: C.accent3 } }], { x: 7.5, y: y + 0.08, w: 5.1, h: 0.34, valign: "middle" });
      tx(s, desc, { x: 7.5, y: y + 0.44, w: 5.1, h: 0.42, fontSize: 11.5, color: C.text1 });
    });
    tx(s, "다시 만들지 않는 수치: UCI 외부 실험, 단순 규칙 F1, 콘솔 화면(모듈 개발 때 결과 인용). 3·4단계와 이상 확률은 test 채점 뒤에 돌렸고 선택에 쓰지 않았다.", { x: 6.75, y: 6.33, w: 5.983, h: 0.45, fontSize: 10.5, color: C.accent3 });
    s.addNotes("재현성이다. 압축을 풀고 패키지를 설치한 뒤 명령 하나면 전처리부터 test 예측 파일, 보고서 수치 대조까지 끝난다. 새 가상환경에서 전체를 돌려 보고서 수치 26개가 모두 일치했고, 예측 파일은 바이트 단위로 같았다. 무작위가 있는 곳은 seed를 고정했고, 비교용 LSTM 오토인코더만 학습 난수 때문에 허용 오차를 두었다. 근거: 보고서 6장.");
  }

  // ===== 24. 정리 =====
  pres.addSection({ title: "정리" });
  {
    const s = pres.addSlide({ masterName: "CLOSING", sectionTitle: "정리" });
    s.addText("정리", { placeholder: "title" });
    const pts = [
      ["데이터를 먼저 의심했다", "저장 형식 누수(F1 0.992)를 지우고, 최대 5초씩 끊긴 기록·날짜 교락·단일 사건을 분석 설계에 반영했다"],
      ["물리로 해석되는 경보", "정상만 학습한 세 성분에 R1·R2를 더해 test 1.000 / 1.000(최종 모델은 test 확인 후 선정). 오경보가 고부하 정상의 크기 단독 경보에 몰린다는 것을 밝혔다"],
      ["현장으로 이어지는 운영", "진동 2·전류 1채널의 2단계 경보, 경보 근거별 점검 순서, 비용 순 수집 개선 ①~④"],
    ];
    pts.forEach(([h, b], i) => {
      const y = 1.65 + i * 1.18;
      tx(s, String(i + 1), { x: 0.8, y, w: 0.6, h: 0.55, fontSize: 30, bold: true, color: C.accent2, valign: "middle" });
      tx(s, h, { x: 1.5, y, w: 11.0, h: 0.45, fontSize: 19, bold: true, color: C.background1, valign: "middle" });
      tx(s, b, { x: 1.5, y: y + 0.48, w: 11.0, h: 0.55, fontSize: 14, color: C.background2 });
    });
    card(s, 0.8, 5.3, 11.733, 0.85, C.background1, 90);
    tx(s, [
      { text: "한계  ", options: { bold: true, color: C.accent2 } },
      { text: "고장 사건이 1건(약 3분)이라 1.000의 일반화 근거는 약하다. 더 긴 정상 운전, 다른 고장 사건, 압력·유온 데이터가 다음 단계다." },
    ], { x: 1.05, y: 5.38, w: 11.3, h: 0.7, fontSize: 14, color: C.background1, valign: "middle" });
    tx(s, "감사합니다", { x: 0.8, y: 6.35, w: 6, h: 0.55, fontSize: 24, bold: true, color: C.background1, valign: "middle" });
    tx(s, "팀 북적북적 · 허예준 · 장준용", { x: 6.5, y: 6.42, w: 5.4, h: 0.42, fontSize: 14, color: C.background2, align: "right", valign: "middle" });
    s.addNotes("세 가지로 정리한다. 데이터를 먼저 의심해 누수와 수집 구조를 진단했고, 정상만 학습하고 물리적으로 해석되는 세 성분과 두 규칙으로 경보를 만들었으며, 오경보가 어디서 나는지 밝혀 현장 운영 규칙으로 이었다. 한계도 분명히 말한다. 고장 사건이 하나라 1.000의 일반화 근거는 약하고, 더 긴 정상 운전과 다른 고장 사건, 압력·유온 데이터가 다음 단계다. 감사합니다.");
  }

  // ===== 부록 =====
  pres.addSection({ title: "부록" });
  {
    const s = content("부록", "부록 A1  ·  보고서 1.4~1.5절", "10Hz 관측 대역과 전류 접힘", "초당 10회 점 표본이 직접 담는 대역은 5Hz 이하 — 전류의 0.600Hz는 60Hz 계열이 접힌 것으로 보인다(가설)");
    fig(s, "observ", M, TOP, 7.6, "초당 10회 점 표본의 관측 가능 대역과 접힘");
    card(s, M, 5.28, 7.6, 1.47);
    tx(s, [
      { text: "필터 단서 ", options: { bold: true } },
      { text: "접힘 가설이 맞다면 적어도 전류 채널에는 충분한 안티앨리어싱 필터가 없다. 진동 채널은 확인하지 못했다 → 진동 SD는 관측 표본의 상대 변동 지표로만 쓰고 절대 RMS로 읽지 않는다. 진동 단위가 공개되지 않아 ISO 20816 구역 판정도 하지 않는다." },
    ], { x: M + 0.2, y: 5.38, w: 7.2, h: 1.3, fontSize: 12.5 });
    bullets(s, [
      "정상 전류는 기록마다 겉보기 0.600Hz 사인에 맞는다(30행 이상 360기록, R² 0.9941~0.9996)",
      "기본파를 뺀 잔차에 홀수 고조파가 정확히 3·5·7배(1.8·3.0·4.2Hz), 배경의 2131·485·391배. 짝수 고조파는 거의 없다 — 교류 모터 전류의 반파 대칭과 맞는다",
      "한국 계통 60±0.2Hz를 넣으면 표본 간격은 약 100.7~101.4 또는 98.7~99.3ms. 기록 안 간격은 모두 정확히 100ms라 시각은 계산값으로 보인다",
      "77분 동안 겉보기 주파수가 0.00066Hz 안에서만 움직여 인버터 구동 가능성도 남는다 → 표본 간격은 확정하지 않는다",
    ], { x: 8.5, y: TOP, w: 4.233, h: 4.67, fontSize: 12.5, gap: 9 });
    s.addNotes("질문 대비 슬라이드. '왜 시각이 계산값이라고 보나'라는 질문이 오면 이 장으로 답한다. 근거: 보고서 1.4~1.5절, 그림 2.");
  }
  {
    const s = content("부록", "부록 A2  ·  보고서 2.5절", "확률·불확실성과 첫 경보", "경보와 별도로 이상 확률을 내고, 오경보 0과 탐지 11/11을 통계 상한·하한으로 다시 읽었다");
    const cols = [
      ["이상 확률 (단조 회귀는 valid로 보정)", "0.0046 · 0.0038", "행 단위 Brier A · B — 사전 비율을 test 파일 이상 비율(7.3%·5.0%)로 둔 값 (비율만 쓴 예측 0.068 · 0.048)", [
        "현장 가정 1%: Brier 0.018 · 0.012, 확률 최대 55%(보정 기록 수가 정한 표시 상한)",
        "같은 사건의 앞부분(valid)으로 맞추고 뒷부분(test)으로 잰 값 — 다른 사건에서는 알 수 없다",
        "경보 행 대부분이 상한에 몰려 확률로는 점검 순서를 가르지 못한다 → 운영 판단은 conformal 경보로",
      ]],
      ["오경보·탐지의 통계 범위", "2.47% · 1.65%", "정상 오경보 0/120 · 0/180의 단측 95% 상한(Clopper–Pearson, 설계값 0.83%)", [
        "정상 test는 달력 16.1·24.1분 → 포아송 95% 상한 시간당 11.2·7.5건",
        "이상 11/11 탐지의 95% 하한 76.2% — 사건 단위 표본은 1",
        "기록 독립·사건률 일정 가정의 참고값",
      ]],
      ["α 민감도와 첫 경보", "0 → 1 → 9행", "test B 오경보, α 1 → 3 → 5% (F1 1.000 → 0.998 → 0.986, A는 모두 1.000)", [
        "test 이상 11기록 모두 기록 첫 행(0.0초)에서 경보 — R1이 직전 기록 판정을 이어받은 결과",
        "기록마다 새로 판단하는 v2는 최대 3행(0.3초) 늦다",
        "파일 첫 기록의 첫 경보: valid A 0.1초, B 0.0초",
      ]],
    ];
    const w = (CW - 0.6) / 3;
    cols.forEach(([h, big, label, items], i) => {
      const x = M + i * (w + 0.3);
      card(s, x, TOP, w, 4.67);
      tx(s, h, { x: x + 0.22, y: TOP + 0.18, w: w - 0.44, h: 0.4, fontSize: 14.5, bold: true });
      tx(s, big, { x: x + 0.22, y: TOP + 0.65, w: w - 0.44, h: 0.6, fontSize: 24, bold: true, color: C.accent2, valign: "middle" });
      tx(s, label, { x: x + 0.22, y: TOP + 1.3, w: w - 0.44, h: 0.7, fontSize: 11.5, color: C.accent3 });
      bullets(s, items, { x: x + 0.22, y: TOP + 2.1, w: w - 0.44, h: 2.45, fontSize: 12, gap: 7 });
    });
    s.addNotes("질문 대비 슬라이드. '오경보 0이면 오경보율 0인가', '확률은 믿을 만한가', '조기 탐지는 몇 초인가'에 답한다. 근거: 보고서 2.5절.");
  }
  {
    const s = content("부록", "부록 A3  ·  보고서 2.4절", "딥러닝·지도학습을 최종으로 고르지 않은 이유", "F1 차이보다 데이터 조건과 해석 가능성을 근거로, 물리적으로 해석되는 성분과 규칙을 택했다");
    const w = (CW - 0.3) / 2;
    card(s, M, TOP, w, 4.67);
    tx(s, "딥러닝 오토인코더", { x: M + 0.25, y: TOP + 0.2, w: w - 0.5, h: 0.4, fontSize: 15, bold: true });
    bullets(s, [
      "같은 조건 test 실시간 F1이 낮았다: LSTM 오토인코더 0.289 / 0.238, MLP 오토인코더 0.498 / 0.498",
      "단, 20행 창은 기록 앞 19행을 판정 못 해 test 이상 324행 중 177행(54.6%)을 처음부터 미탐으로 셌다. 점수 방식 개선은 시험하지 않았다",
      "R1을 붙이면 LSTM 오토인코더도 test 0.998이지만 사건 앞부분을 포함한 valid는 0.918(v2+R1 0.997)",
      "데이터 조건: 고장 1사건, 기록이 최대 50행(5초)으로 끊겨 긴 연속 구간이 없고, 초당 10회라 빠른 진동 정보가 없다",
      "다변량 시계열 이상탐지 연구에서도 단순한 방법이 비슷하거나 낫다는 보고가 있다[9][10]",
    ], { x: M + 0.25, y: TOP + 0.75, w: w - 0.5, h: 3.8, fontSize: 12.5, gap: 8 });
    const x2 = M + w + 0.3;
    card(s, x2, TOP, w, 4.67);
    tx(s, "지도학습 대조(사후): 세션 교락의 크기", { x: x2 + 0.25, y: TOP + 0.2, w: w - 0.5, h: 0.4, fontSize: 15, bold: true });
    const rows = [
      ["0.793~0.970", "F1 — 라벨 지도학습(HGB·RF·LR, 기록 그룹 5겹), 형식 누수를 지운 자료", C.accent1],
      ["0.75~0.87", "ROC-AUC 중앙값 — 고장 없는 같은 날 정상끼리, 약 1시간 떨어진 블록(인접 블록 0.48~0.58)", C.accent2],
      ["0.93~1.00", "이상–정상 분리 — 고장 때문인지 5일 떨어진 세션 차이 때문인지 가를 수 없다", C.accent3],
    ];
    rows.forEach(([big, label, col], i) => {
      const y = TOP + 0.8 + i * 1.05;
      tx(s, big, { x: x2 + 0.25, y, w: 2.1, h: 0.9, fontSize: 20, bold: true, color: col, valign: "middle" });
      tx(s, label, { x: x2 + 2.4, y, w: w - 2.65, h: 0.9, fontSize: 12, valign: "middle" });
    });
    tx(s, "→ 지도학습 점수는 성능 비교에서 빼고 사후 대조로만 적었다. 정상만 학습한 모델도 세션 차이를 완전히 배제하지는 못한다(V5).", { x: x2 + 0.25, y: TOP + 4.0, w: w - 0.5, h: 0.6, fontSize: 12, color: C.accent3 });
    s.addNotes("질문 대비 슬라이드. '왜 딥러닝을 안 썼나', '라벨이 있는데 왜 지도학습을 안 했나'에 답한다. 근거: 보고서 2.4절.");
  }
  {
    const s = content("부록", "부록 A4  ·  보고서 2.4~2.5절", "표준 기법 대조: PCA 관리도, CUSUM·EWMA", "공정 산업의 표준 기법을 같은 분할·같은 보정으로 돌렸다(사후, 선택·잠금에는 쓰지 않음)");
    table(s, ["기법", "결과", "해석"], [
      ["PCA 관리도 T²·SPE (교과서 99% 한계)", "valid 정상 기록의 49%(A)·45%(B)가 한계를 넘음. test 기록 판정 F1 0.163·0.127", "창 겹침 자기상관, 부하의 이봉 분포, 기록마다 수십 번 반복되는 검정 → 기록 단위 운영에 맞지 않음"],
      ["PCA 관리도 + conformal 보정", "test 실시간 F1 0.557 / 0.908, 고부하 정상 오경보 0", "기록 위치 0~1은 점수가 없고 2~6행은 둔하다"],
      ["CUSUM (기록마다 리셋)", "test 실시간 F1 0.978 / 0.975", "v2보다 조금 오르는 데 그친다"],
      ["v2 + CUSUM · EWMA (기록 간 상태 유지)", "1.000 / 1.000 · 1.000 / 0.998", "R1 수준 → 이득의 핵심은 수집 공백을 넘는 기억. CUSUM k=5는 격자 끝값이고 정상 점수 최댓값(A 4.42·B 3.52)보다 커서 α 보정이 퇴화했다 — B test 1.000은 이 높은 문턱 덕"],
      ["해제 동작 (고장 뒤 정상 기록을 이어 붙인 가상 흐름)", "R1 0.7초 · EWMA 0.2~0.3초 · CUSUM 11.4~12.2분", "R1의 해제는 고장 규모가 아니라 전류 파형의 정상 확인에 묶인다. EWMA는 약한 이상에서 다음 기록까지 남지 않을 수 있다"],
      ["PCA 기여 분석", "이상 행 T² 기여: 전류 사인 잔차 비율 26%·28%, 상부 진동 RMS 26%·25%, 하부 lag-1 15%·16%", "SPE는 하부 진동 RMS(44%)와 전류 잔차가 크다 — 하부 진동이 부하를 따르던 정상 관계의 붕괴"],
    ], { x: M, y: TOP, w: CW, colW: [2.9, 4.2, 5.033], fontSize: 11.5, rowH: [0.42, 0.62, 0.5, 0.45, 0.78, 0.72, 0.62] });
    s.addNotes("질문 대비 슬라이드. '공정 표준 기법(SPC)과 비교했나', 'R1 대신 CUSUM을 쓰면 안 되나'에 답한다. 근거: 보고서 2.4~2.5절, 3.1절.");
  }
  {
    const s = content("부록", "부록 A5  ·  보고서 1.4·1.6절", "수집 구조: 기록과 공백", "행은 최대 50행(5초)짜리 기록으로 끊겨 들어온다 — 기록 시작 직후 판단이 어려운 이유이자 R1의 근거다");
    fig(s, "collection", M, TOP, 7.4, "수집 구조: 기록(최대 50행)과 공백");
    card(s, M, 5.75, 7.4, 1.0, C.accent1, 90);
    tx(s, "기록 시작 직후에는 과거 정보가 없다 → v2 미탐이 기록 위치 0~1에 몰린 원인이고, R1이 수집 공백을 넘어 경보를 잇는 근거다.", { x: M + 0.2, y: 5.85, w: 7.0, h: 0.8, fontSize: 13, valign: "middle" });
    bullets(s, [
      "정상 77분 중 실제 측정은 33분(43.3%)",
      "50행을 넘는 기록 0개, 정확히 50행인 기록 202개",
      "기록 시작은 약 8.02초, 끝은 약 6.78초 주기에 묶여 있다 → PLC가 표본을 최대 50개 모아 올리는 구조로 보인다(추정)",
      "기록 길이와 진동 SD는 뚜렷한 관계가 없다(Spearman 0.08·0.015) → 길이가 다른 기록도 같은 지표로 비교",
      "정상의 중복 행 1개는 v2·규칙·베이스라인에서 그대로 둬 600기록으로 센다",
    ], { x: 8.3, y: TOP, w: 4.433, h: 4.67, fontSize: 13, gap: 9 });
    s.addNotes("질문 대비 슬라이드. '기록이 무엇인가', '왜 기록 단위로 나눴나'에 답한다. 근거: 보고서 1.4절, 1.6절, 그림 4.");
  }

  await pres.writeFile({ fileName: OUT });
  await postProcess(OUT);
  console.log("written", OUT);
}

// pptxgenjs가 쓰지 못하는 테마 색·한글 글꼴·한국어 줄바꿈을 마지막에 채운다
async function postProcess(file) {
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  const tpart = "ppt/theme/theme1.xml";
  let t = await zip.file(tpart).async("string");
  const scheme = `<a:clrScheme name="${THEME.name}">` + SLOTS.map((k) => `<a:${k}><a:srgbClr val="${THEME.colors[k]}"/></a:${k}>`).join("") + "</a:clrScheme>";
  t = t.replace(/<a:clrScheme\b[\s\S]*?<\/a:clrScheme>/, () => scheme)
    .replace(/(<a:(?:theme|fontScheme)\b[^>]*?\bname=")[^"]*"/g, (_, head) => `${head}${THEME.name}"`)
    .replace(/<a:ea typeface=""\/>/g, '<a:ea typeface="Malgun Gothic"/>');
  if (!t.includes(scheme)) throw new Error("theme1.xml에 clrScheme이 없다");
  zip.file(tpart, t);
  // lang이 en-US면 PowerPoint가 한글 어절 중간에서 줄을 바꾼다
  for (const name of Object.keys(zip.files)) {
    if (!/^ppt\/(slides|slideLayouts|slideMasters|notesSlides|notesMasters)\/[^/]+\.xml$/.test(name)) continue;
    let x = await zip.file(name).async("string");
    x = x.replace(/lang="en-US"/g, 'lang="ko-KR" altLang="en-US"');
    const bad = x.match(/<a:srgbClr val="((?![0-9A-Fa-f]{6}")[^"]*)"/);
    if (bad) throw new Error(`${name}: srgbClr ${bad[1]} — hex만 받는 옵션에 테마 색을 넣었다`);
    zip.file(name, x);
  }
  fs.writeFileSync(file, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}

build().catch((e) => { console.error(e); process.exit(1); });
