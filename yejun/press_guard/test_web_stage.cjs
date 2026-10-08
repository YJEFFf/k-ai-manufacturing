// 두 단계 경보 콘솔(web/stage.js)을 VM에서 실행한다. 제품 파일에는 시험용 전역을 넣지 않는다(test_web.cjs와 같은 방식).
// 확인: 행 표시(stage1·stage2·R1·R2·관측 부족)로 사건을 모으는 규칙, 모의 운용에서 2단계 행 전에는 1단계, 대기열·KPI·판정 띠·성능 표.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const elements = new Map();
function element() { return { innerHTML: '', textContent: '', value: 1, style: {}, disabled: false, hidden: false, clientWidth: 600, options: [],
  listeners: {}, addEventListener(k, f) { this.listeners[k] = f; }, classList: { toggle() {} }, appendChild() {},
  querySelector() { return this.svg ||= element(); }, querySelectorAll() { return []; },
  getBoundingClientRect() { return { left: 0, width: 600 }; } }; }
const document = { getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
  querySelectorAll() { return []; }, querySelector() { return null; }, createElement: element, body: { appendChild() {} } };
const context = { document, window: { addEventListener() {}, innerWidth: 1200 }, setTimeout, clearTimeout, setInterval, clearInterval, URLSearchParams };
let code = fs.readFileSync(__dirname + '/web/stage.js', 'utf8');
code = code.replace('  start();', '  globalThis.subject={buildView,viewNow,state,renderQueue,renderStats,filteredIncidents,levelNow,stageStrip,lineChart,renderDetail,selectIncident,renderStageEvidence,stageLine};');
vm.runInNewContext(code, context);
const S = context.subject;
const $ = id => document.getElementById(id);

// 기록 5개(10행씩, 기록 사이 5초). 사건 1: 기록 0의 8·9행 자기 경보(2단계) → 기록 1이 첫 7행을 이어받고 8번째 행에서 해제.
// 사건 2: 기록 3의 크기 단독 경보 1행을 R2가 보류(1단계만). 사건 3: 기록 4에서 1단계(R2 보류) 다음 2단계(파형).
const t0 = Date.UTC(2022, 6, 12, 1, 0, 0);
const points = Array.from({ length: 50 }, (_, i) => {
  const rec = Math.floor(i / 10), pos = i % 10;
  const p = { row_id: i, stage_record: rec, stage_position: pos, timestamp: new Date(t0 + rec * 6000 + pos * 100).toISOString(), status: 'ok',
    stage1: 0, stage2: 0, own1: 0, own2: 0, inherited1: 0, inherited2: 0, released1: 0, released2: 0, r2_hold: 0, insufficient: pos < 7 ? 1 : 0,
    v2_alarm: 0, stage_level: 0, stage_evidence: '', incident_id: 0, stage2_event: 0, score: 1, p_value: 0.5, magnitude_sensor: 'AI0_Vibration',
    operating_state: 'load', record_current_rms: 120, anomaly_probability: 0.01, likelihood_ratio: 1, AI2_Current: Math.sin(i), reference_label: rec < 2 ? 1 : 0 };
  const own = (lv, ev) => Object.assign(p, { stage1: 1, own1: 1, v2_alarm: 1, stage_evidence: ev, stage_level: lv, stage2: lv === 2 ? 1 : 0, own2: lv === 2 ? 1 : 0, score: 6 });
  if (rec === 0 && pos >= 8) { own(2, 'waveform'); p.incident_id = 1; p.stage2_event = 1; }
  if (rec === 1 && pos < 7) Object.assign(p, { stage1: 1, stage2: 1, inherited1: 1, inherited2: 1, stage_level: 2, incident_id: 1, stage2_event: 1 });
  if (rec === 1 && pos === 7) Object.assign(p, { released1: 1, released2: 1 });
  if (rec === 3 && pos === 8) { own(1, 'magnitude'); p.r2_hold = 1; p.incident_id = 2; }
  if (rec === 4 && pos === 7) { own(1, 'magnitude'); p.r2_hold = 1; p.incident_id = 3; }
  if (rec === 4 && pos === 9) { own(2, 'waveform'); p.incident_id = 3; p.stage2_event = 2; }
  return p;
});
const full = { points, incidents: [], cases: [], split: 'B', alpha: 0.01, dataset: 'mixed', prior: 0.01, lr_cap: 121, threshold: 3.5, min_p_attainable: 1 / 121,
  quality_actions: { 1: '다음 샘플 검사', 2: '보류·전수 확인' }, suspect_max_gap_s: 60, warnings: [],
  decision_actions: { vibration: '진동·부하 확인', current_shape: '전류 파형·계측 확인', vibration_and_current: '진동·전류 함께 점검' } };
const v = S.buildView(full, Infinity);
const byId = id => v.incidents.find(c => c.incident_id === id);
assert.equal(v.incidents.length, 3);
assert.deepEqual([byId(1).level, byId(2).level, byId(3).level], [2, 1, 2]);
assert.equal(byId(1).escalation_row, 8); assert.equal(byId(3).escalation_row, 49); assert.equal(byId(2).escalation_row, null);
assert.equal(byId(1).cases, 2); assert.equal(byId(1).r1_rows, 7); assert.equal(byId(1).r1_only_rows, 7);
assert.equal(byId(1).release_rows, 1); assert.equal(byId(1).release_row, 17); assert.equal(byId(1).insufficient_rows, 7);
assert.equal(byId(2).r2_hold_rows, 1); assert.equal(byId(2).stage2_rows, 0); assert.equal(byId(2).action, '진동·부하 확인');
assert.equal(byId(1).action, '전류 파형·계측 확인');
// 우선순위: 단계 → 근거 성분 수 → 경보 행 비율 → 최대 점수. 사건 3(2단계, 성분 2개) > 사건 1(2단계, 성분 1개) > 사건 2(1단계)
assert.deepEqual([byId(3).priority_rank, byId(1).priority_rank, byId(2).priority_rank], [1, 2, 3]);
assert.equal(v.cases.find(c => c.record_id === 1).release_position, 7);
assert.equal(v.stats.stage2_events, 2); assert.equal(v.stats.r2_hold_rows, 2); assert.equal(v.stats.level2_incidents, 2);
assert.match(S.stageLine(byId(2)), /R2 보류/);
// 의심 시간창: 사건 2 앞뒤의 1단계 경보 없는 기록(2·4는 경보가 있어 뒤는 열림)
assert.ok(byId(2).suspect_from); assert.equal(byId(2).suspect_open, 1);

// 서버 결과처럼 넣고 화면 함수
Object.assign(full, { incidents: v.incidents, cases: v.cases, stats: v.stats });
S.state.result = full;
S.renderStats();
assert.equal($('k-case').textContent, '2'); assert.equal($('k-level1').textContent, '1');
assert.equal($('k-r1').textContent, '7행'); assert.equal($('k-r2').textContent, '2행');
S.renderQueue();
const q = $('queue').innerHTML;
assert.match(q, /badge l2">점검 요청/); assert.match(q, /chip r1">R1 이어받음 7행/); assert.match(q, /chip r2">R2 보류 1행/); assert.match(q, /R1 해제/);
S.state.filter = 'r2'; assert.equal(S.filteredIncidents().map(c => c.incident_id).sort().join(','), '2,3'); S.state.filter = 'all';
S.selectIncident(1, 10);
assert.match($('detail-summary').innerHTML, /8번째 관측에서 해제/);
assert.match($('stage-chart').innerHTML, /#7a68c9/); assert.match($('stage-chart').innerHTML, /#176d55/);

// 모의 운용: 커서까지 들어온 행만으로 사건을 다시 모은다. 사건 3은 2단계 행(49) 전에는 1단계다.
S.state.sim = { row: 7 }; assert.equal(S.filteredIncidents().length, 0);
S.state.sim = { row: 8 }; assert.equal(S.filteredIncidents().length, 1); assert.equal(S.levelNow(S.filteredIncidents()[0]), 2);
S.state.sim = { row: 48 }; let inc3 = S.viewNow().incidents.find(c => c.incident_id === 3);
assert.equal(inc3.level, 1); assert.equal(S.levelNow(inc3), 1);
S.state.sim = { row: 49 }; inc3 = S.viewNow().incidents.find(c => c.incident_id === 3);
assert.equal(inc3.level, 2); assert.equal(S.levelNow(inc3), 2);
S.state.sim = null;

// 성능 검증 표: 상한이 기준 이하인지 표시
S.renderStageEvidence({ volume: { sets: [
    { set: 'E3 5창 합침', stage: 'stage2', exposure_min: 38.6, records: 300, alarm_rows: 0, events: 0, rate_h: 0, ci95_lo_h: 0, ci95_hi_h: 5.7, per_shift: 0, ci95_lo_shift: 0, ci95_hi_shift: 45.8, upper95_h: 4.7, benchmark_per_hour: 6, point_within_benchmark: true, upper95_within_benchmark: true },
    { set: 'E3 5창 합침', stage: 'stage1', exposure_min: 38.6, records: 300, alarm_rows: 2, events: 2, rate_h: 3.1, ci95_lo_h: 0.4, ci95_hi_h: 11.2, per_shift: 24.8, ci95_lo_shift: 3, ci95_hi_shift: 89.7, upper95_h: 9.8, benchmark_per_hour: 6, point_within_benchmark: true, upper95_within_benchmark: false }],
  states: [{ state: 'busy_high', state_label: '변동·고부하', records: 53, exposure_h: 0.118, stage: 'stage1', events: 2, rate_h: 17, ci95_lo_h: 2.1, ci95_hi_h: 61.4 }],
  repeat: { primary: { threshold: 34, rate_h: 3.1, mean: 24.8, p_at_threshold: 0.046 }, all: [{ basis: '주', rate_h: 3.1, hours: 8, tail: 0.05, mean: 24.8, threshold: 34, p_at_threshold: 0.046 }] } },
  replay: { latency_ms: { median: 9.8, p99: 17.7 }, cpu: 'cpu', splits: { B: { flows: { normal: { rows: 9867, test_rows: 6097, alarms: { stage1: { equal: 6097, rows: 6097 }, stage2: { equal: 6097, rows: 6097 }, v2: { equal: 6097, rows: 6097 } }, score_max_abs_diff: 0, chunks_equal: true } } } } } });
assert.match($('stage-volume').innerHTML, /상한도 이하/); assert.match($('stage-volume').innerHTML, /점추정만 이하/);
assert.match($('stage-repeat').innerHTML, /교대 34건 이상/); assert.match($('stage-replay').innerHTML, /6,097\/6,097/);
console.log('test_web_stage.cjs: 통과');
