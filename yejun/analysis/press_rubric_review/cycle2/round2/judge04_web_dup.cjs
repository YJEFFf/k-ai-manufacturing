// 평가관 04 cycle2 round2: 콘솔(app.js)이 한 기록구간 안의 여러 건을 구별하는지 확인한다. 저장소 파일은 읽기만 한다.
// 실행(yejun/에서): node analysis/press_rubric_review/cycle2/round2/judge04_web_dup.cjs
// 끊김 없는 연속 입력은 기록구간이 하나라 건들이 같은 record_id를 가진다(judge04_r2_check.json stream.S3·console_api.upload_continuous).
// 실제 app.js를 VM에서 실행하고(test_web.cjs와 같은 방식), 같은 record_id의 두 건에서 상세·결과 기록이 어느 건에 붙는지 본다.
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const APP = path.resolve(__dirname, '../../../../press_guard/web/app.js');
const elements = new Map();
function element() {
  return { innerHTML: '', textContent: '', value: '', style: {}, disabled: false, hidden: false, clientWidth: 600, max: 1,
    listeners: {}, addEventListener(k, f) { this.listeners[k] = f; }, classList: { toggle() {} },
    querySelector() { return this.svg ||= element(); }, querySelectorAll() { return []; },
    getBoundingClientRect() { return { left: 0, width: 600 }; }, scrollIntoView() {} };
}
const store = new Map();
const localStorage = { getItem: k => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) };
const document = { getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
  querySelectorAll() { return []; }, querySelector() { return null; }, createElement: element, body: { appendChild() {} } };
const context = { document, window: { addEventListener() {}, innerWidth: 1200, localStorage }, setTimeout, clearTimeout, setInterval, clearInterval,
  URL, Blob: function () {}, console };
let code = fs.readFileSync(APP, 'utf8');
code = code.replace('  start();', '  globalThis.subject={state,renderQueue,selectCase,renderDetail,filteredCases,outcomeOf};');
vm.runInNewContext(code, context);
const { state, renderQueue, selectCase } = context.subject;
const $ = id => document.getElementById(id);

// 한 연속 기록(record_id 0) 안의 두 건: 앞 건은 정상 구간의 1행 경보(주의), 뒤 건은 이상 600행(점검 요청).
const c1 = { record_id: 0, first_row: 41, first_timestamp: '2026-09-27 08:00:04.100', first_alarm_position: 41, detection_delay_s: 4.1, alarm_rows: 1,
  observed_rows: 50, level: 1, escalation_row: null, priority_rank: 2, evidence: 'magnitude', magnitude_sensors: 'AI0_Vibration', action: '진동·부하 확인',
  quality_action: '다음 샘플 검사를 앞당긴다(가설)', suspect_open: 0, suspect_from: '2026-09-27T08:00:00+00:00', suspect_to: '2026-09-27T08:00:05+00:00', suspect_seconds: 5, peak_score: 4, min_p: 0.0083 };
const c2 = { record_id: 0, first_row: 9050, first_timestamp: '2026-09-27 08:15:05.000', first_alarm_position: 9050, detection_delay_s: 905.0, alarm_rows: 600,
  observed_rows: 650, level: 2, escalation_row: 9051, priority_rank: 1, evidence: 'dynamics+magnitude+waveform', magnitude_sensors: 'AI0_Vibration', action: '진동·전류 함께 점검',
  quality_action: '의심 시간창에 만든 가공품을 보류하고 전단면·버·치수·평탄도를 전수 확인한다(가설)', suspect_open: 1, suspect_from: '', suspect_to: '', suspect_seconds: null, peak_score: 57, min_p: 0.0083 };
state.result = { cases: [c1, c2], points: [], split: 'B', alpha: 0.01, dataset: 'upload', prior: 0.01, threshold: 3.5, min_p_attainable: 1 / 121 };
state.overview = { decision_table: [] };
renderQueue();
const html = $('queue').innerHTML;
const buttons = (html.match(/data-record="(\d+)"/g) || []);
// 대기열 첫 줄(우선 1)은 뒤 건 c2다. 사용자가 그 줄을 누르면 app.js는 selectCase(Number(dataset.record)) = selectCase(0)을 부른다.
selectCase(0);
const summary = $('detail-summary').innerHTML;
const shownDelay = /첫 경보<\/span><b>([^<]+)</.exec(summary);
const shownRows = /경보 관측<\/span><b>([^<]+)</.exec(summary);
// 그 상태에서 결과를 "이상 확인"으로 저장하면 어느 건의 키에 붙는가
$('o-owner').value = '보전'; $('o-outcome').value = '이상 확인'; $('o-measure').value = '펌프 점검';
$('outcome').listeners.submit({ preventDefault() {} });
const keys = [...store.keys()];
const out = {
  queue_buttons: buttons,
  queue_buttons_share_record: new Set(buttons).size < buttons.length,
  clicked_row_is_priority1_case: 'c2 (이상 600행, 점검 요청)',
  detail_shows_first_alarm: shownDelay && shownDelay[1], detail_shows_alarm_rows: shownRows && shownRows[1],
  detail_is_c2: !!(shownRows && /600/.test(shownRows[1])),
  quality_action_shown: $('quality-action').textContent,
  saved_keys: keys,
  outcome_saved_to_c2: keys.some(k => k.endsWith(c2.first_timestamp)),
  outcome_saved_to_c1: keys.some(k => k.endsWith(c1.first_timestamp)),
};
fs.writeFileSync(path.join(__dirname, 'judge04_web_dup.json'), JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
