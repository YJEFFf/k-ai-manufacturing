// Press Guard 두 단계 경보 콘솔 — stage_console.py의 /api/overview, /api/analyze에 연결한다.
// 1단계 "주의" = v2 + R1(사건 지속), 2단계 "점검 요청" = v2 → R2(교차 확인) → R1. 행마다의 단계·R1·R2·관측 부족 표시는 서버의
// stages.TwoStageStream(제출 예측 파일과 같은 규칙, 인과 순차)이 낸 값이고, 이 화면은 그것을 사건(60초 묶음)으로 모아 보인다.
// 기존 v2 콘솔(app.js)을 바탕으로 했다. 설비 제어 명령을 보내지 않으며 고장 원인·잔여수명을 추정하지 않는다.
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const SERIES = [
    { key: 'g_dynamics', name: '전류 예측 오차', color: '#6d55c9', dash: '' },
    { key: 'g_waveform', name: '전류 파형', color: '#178cc2', dash: '5 3' },
    { key: 'g_magnitude', name: '센서 크기', color: '#b07510', dash: '1.5 2.5' },
  ];
  const REASON_LABEL = { dynamics: '전류 예측 오차', waveform: '전류 파형', magnitude: '센서 크기' };
  const ALARM = '#b3412e', CAUTION = '#c98a12', R1 = '#7a68c9', R2 = '#178cc2', RELEASE = '#176d55', SHORT = '#c4ced1';
  const state = { overview: null, result: null, selected: null, selectedCase: null, filter: 'all', levelFilter: 'all', sort: 'priority', upload: null, replay: null, cursor: null, busy: false, sim: null, initialIncident: null, initialCase: null };
  const LEVEL = { 1: '주의', 2: '점검 요청' };
  const STAGE_NAME = { 'stage1': '1단계 주의(v2+R1)', 'stage2': '2단계 점검 요청(v2→R2→R1)' };
  const OPERATING_STATE = { load: '부하', low: '저수준', short: '판정 대기(17행 미만)' };
  const stateLabel = value => String(value || 'short').split('+').map(s => OPERATING_STATE[s] || s).join(' · ');
  function operatingStateText(c) {
    let value = c.operating_state, rms = c.record_current_rms;
    if (state.sim) {
      const visible = caseRows(c).filter(p => p.row_id <= state.sim.row);
      const last = visible[visible.length - 1];
      value = last ? last.operating_state : 'short'; rms = last ? last.record_current_rms : null;
    }
    return `${stateLabel(value)} · 전류 RMS ${fmt.num(rms, 1)}`;
  }
  const store = {
    get(k) { try { const v = window.localStorage && window.localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch (e) { return null; } },
    set(k, v) { try { if (window.localStorage) window.localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } },
  };
  // 대기열의 단위는 사건이다: 60초 안에 이어지는 1단계 경보 행의 묶음. 건은 사건이 걸친 기록 하나이고 case_uid(그 기록의 첫 경보 행)로 구분한다.
  const incidentsOf = () => (viewNow() || {}).incidents || [];
  const casesOf = inc => ((viewNow() || {}).cases || []).filter(c => Number(c.incident_id) === Number(inc.incident_id)).sort((a, b) => a.first_row - b.first_row);
  const outcomeKey = inc => `pg-stage-outcome:${state.result.split}:${state.result.alpha}:${state.result.dataset}:inc${inc.incident_id}:${inc.first_timestamp}`;
  const outcomeOf = c => (!state.sim && state.result && store.get(outcomeKey(c))) || { confirmed_at: '', owner: '', outcome: '', measure: '', status: '열림' };
  const simVisible = c => !state.sim || c.first_row <= state.sim.row;
  const levelNow = c => (state.sim && Number(c.level) === 2 && !(c.escalation_row <= state.sim.row)) ? 1 : Number(c.level);
  const probText = x => {
    if (!Number.isFinite(numberOrNaN(x.max_probability))) return '보정기 없음';
    const capped = state.result && state.result.lr_cap != null && Number(x.max_likelihood_ratio) >= Number(state.result.lr_cap) - 1e-6;
    return capped ? `${fmt.pct(x.max_probability, 1)}(모형 상한)` : fmt.pct(x.max_probability, 1);
  };
  const SENSOR_LABEL = { AI0_Vibration: '진동', AI1_Vibration: '진동', AI2_Current: '전류' };
  const reasonLabel = (e, c) => {
    if (e !== 'magnitude' || !c || !c.magnitude_sensors) return REASON_LABEL[e] || e;
    const kinds = [...new Set(String(c.magnitude_sensors).split('+').filter(Boolean).map(s => SENSOR_LABEL[s] || s))];
    return `${REASON_LABEL.magnitude}(${kinds.join('·')})`;
  };
  const fmt = {
    int: v => (v == null || Number.isNaN(Number(v))) ? '—' : Number(v).toLocaleString('ko-KR'),
    num: (v, d = 2) => (v == null || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(d),
    pct: (v, d = 1) => (v == null || Number.isNaN(Number(v))) ? '—' : (100 * v).toFixed(d) + '%',
    time: s => { const m = /(\d{2}:\d{2}:\d{2}(?:\.\d+)?)/.exec(String(s || '')); return m ? m[1].slice(0, 12) : String(s || '—'); },
  };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const numberOrNaN = v => v == null || v === '' ? NaN : Number(v);
  const flag = (p, k) => Number(p[k]) === 1 || p[k] === true;
  const setMessage = (text, error = false) => { const m = $('message'); m.textContent = text; m.classList.toggle('error', !!error); };
  const repeatCriterion = () => { const v = state.overview && state.overview.stage && state.overview.stage.volume; return v && v.repeat ? v.repeat.primary : null; };

  // ---------- 사건·건 집계(모의 운용의 접두부용, 서버 stage_console.stage_tables와 같은 규칙) ----------
  const union = values => [...new Set(values.flatMap(v => String(v || '').split('+')).filter(Boolean))].sort();
  const timestampMs = value => { let s = String(value || '').replace(' ', 'T'); if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(s)) s += 'Z'; return Date.parse(s); };
  const extrema = (rows, key, minimum = false) => {
    let value = null;
    for (const row of rows) { const v = numberOrNaN(row[key]); if (Number.isFinite(v)) value = value == null ? v : (minimum ? Math.min(value, v) : Math.max(value, v)); }
    return value;
  };
  const rank = rows => {
    const ordered = [...rows].sort((a, b) => b.level - a.level || b.evidence_count - a.evidence_count
      || b.alarm_share - a.alarm_share || (b.peak_score ?? -Infinity) - (a.peak_score ?? -Infinity) || a.first_row - b.first_row);
    ordered.forEach((r, i) => { r.priority_rank = i + 1; });
  };
  function actionFor(full, sensors, reasons) {
    if (!reasons.length) return 'R1 이어받음: 직전 기록의 근거·점검 항목을 따른다';
    const actions = full.decision_actions || {};
    const vibration = sensors.some(s => s !== 'AI2_Current'), current = sensors.includes('AI2_Current');
    const shape = reasons.includes('waveform') || reasons.includes('dynamics');
    return (vibration ? (shape || current ? actions.vibration_and_current : actions.vibration)
      : current ? (shape ? actions.current_magnitude_and_shape : actions.current_magnitude) : actions.current_shape) || '';
  }
  function buildView(full, cursor) {
    const points = full.points.filter(p => Number(p.row_id) <= cursor);
    const recs = new Map();
    for (const p of points) {
      const r = Number(p.stage_record);
      if (!recs.has(r)) recs.set(r, { rows: [], s1: false, valid: true });
      const g = recs.get(r); g.rows.push(p); g.s1 = g.s1 || flag(p, 'stage1'); g.valid = g.valid && p.status === 'ok';
    }
    const recIds = [...recs.keys()];
    const groups = new Map();
    for (const p of points) { const id = Number(p.incident_id); if (id > 0) { if (!groups.has(id)) groups.set(id, []); groups.get(id).push(p); } }
    const quality = full.quality_actions || {}, maxGap = full.suspect_max_gap_s ?? 60;
    const incidents = [], cases = [];
    groups.forEach((rows, id) => {
      const members = [...new Set(rows.map(p => Number(p.stage_record)))];
      const span = members.flatMap(r => recs.get(r).rows);
      const level = rows.some(p => flag(p, 'stage2')) ? 2 : 1;
      const esc2 = rows.find(p => flag(p, 'stage2'));
      const own = rows.filter(p => flag(p, 'own1'));
      const evidence = union(own.map(p => p.stage_evidence));
      const sensors = union(own.filter(p => String(p.stage_evidence).split('+').includes('magnitude')).map(p => p.magnitude_sensor));
      const before = recIds.filter(r => r < members[0]).map(r => recs.get(r)).filter(g => !g.s1 && g.valid).pop();
      const after = recIds.filter(r => r > members[members.length - 1]).map(r => recs.get(r)).find(g => !g.s1 && g.valid);
      let from = before ? before.rows[before.rows.length - 1].timestamp : '', to = after ? after.rows[0].timestamp : '';
      const firstRec = recs.get(members[0]).rows, lastRec = recs.get(members[members.length - 1]).rows;
      const fromGap = timestampMs(firstRec[0].timestamp) - timestampMs(from), toGap = timestampMs(to) - timestampMs(lastRec[lastRec.length - 1].timestamp);
      if (!(fromGap >= 0 && fromGap <= maxGap * 1000)) from = '';
      if (!(toGap >= 0 && toGap <= maxGap * 1000)) to = '';
      const releases = span.filter(p => flag(p, 'released1'));
      const caseUids = [];
      members.forEach(r => {
        const all = recs.get(r).rows, mine = all.filter(p => Number(p.incident_id) === id), first = mine[0] || all[0];
        const ownC = mine.filter(p => flag(p, 'own1')), evC = union(ownC.map(p => p.stage_evidence));
        const sensC = union(ownC.filter(p => String(p.stage_evidence).split('+').includes('magnitude')).map(p => p.magnitude_sensor));
        const rel = all.find(p => flag(p, 'released1'));
        caseUids.push(first.row_id);
        cases.push({ case_uid: first.row_id, incident_id: id, record_id: r, row_from: all[0].row_id, row_to: all[all.length - 1].row_id,
          first_row: first.row_id, first_timestamp: first.timestamp, first_alarm_position: Number(first.stage_position),
          detection_delay_s: Number(first.stage_position) * 0.1, alarm_rows: mine.length, stage2_rows: mine.filter(p => flag(p, 'stage2')).length,
          own_rows: ownC.length, observed_rows: all.length, alarm_share: mine.length / all.length,
          r1_rows: mine.filter(p => flag(p, 'inherited1')).length, r1_only_rows: mine.filter(p => flag(p, 'inherited1') && !flag(p, 'own1')).length,
          release_row: rel ? rel.row_id : null, release_position: rel ? Number(rel.stage_position) : null,
          r2_hold_rows: mine.filter(p => flag(p, 'r2_hold')).length, insufficient_rows: mine.filter(p => flag(p, 'insufficient')).length,
          level: mine.some(p => flag(p, 'stage2')) ? 2 : 1, evidence: evC.join('+'), evidence_count: evC.length, magnitude_sensors: sensC.join('+'),
          action: actionFor(full, sensC, evC), peak_score: extrema(mine, 'score'), min_p: extrema(mine, 'p_value', true),
          operating_state: all[all.length - 1].operating_state, record_current_rms: all[all.length - 1].record_current_rms,
          first_alarm_operating_state: first.operating_state, max_probability: extrema(mine, 'anomaly_probability'),
          max_likelihood_ratio: extrema(mine, 'likelihood_ratio'), reference_label: extrema(all, 'reference_label') });
      });
      incidents.push({ incident_id: id, first_row: rows[0].row_id, last_row: rows[rows.length - 1].row_id, first_timestamp: rows[0].timestamp,
        last_timestamp: rows[rows.length - 1].timestamp, last_case_timestamp: (span.find(p => p.row_id === caseUids[caseUids.length - 1]) || rows[0]).timestamp,
        level, level_name: LEVEL[level], escalation_row: esc2 ? esc2.row_id : null,
        escalation_after_first_s: esc2 ? (timestampMs(esc2.timestamp) - timestampMs(rows[0].timestamp)) / 1000 : null,
        cases: members.length, case_uids: caseUids.join('+'), records: members.join('+'), alarm_rows: rows.length,
        stage2_rows: rows.filter(p => flag(p, 'stage2')).length, own_rows: own.length, observed_rows: span.length, alarm_share: rows.length / span.length,
        r1_rows: rows.filter(p => flag(p, 'inherited1')).length, r1_only_rows: rows.filter(p => flag(p, 'inherited1') && !flag(p, 'own1')).length,
        release_rows: releases.length, release_row: releases.length ? releases[0].row_id : null,
        r2_hold_rows: rows.filter(p => flag(p, 'r2_hold')).length, insufficient_rows: rows.filter(p => flag(p, 'insufficient')).length,
        evidence: evidence.join('+'), evidence_count: evidence.length, magnitude_sensors: sensors.join('+'), action: actionFor(full, sensors, evidence),
        peak_score: extrema(rows, 'score'), min_p: extrema(rows, 'p_value', true), max_probability: extrema(rows, 'anomaly_probability'),
        max_likelihood_ratio: extrema(rows, 'likelihood_ratio'), operating_state: [...new Set(members.map(r => { const g = recs.get(r).rows; return g[g.length - 1].operating_state; }))].join('+'),
        first_alarm_operating_state: rows[0].operating_state, suspect_from: from, suspect_to: to, suspect_open: Number(!from || !to),
        quality_action: quality[level] || '', reference_label: extrema(span, 'reference_label') });
    });
    rank(incidents); rank(cases);
    const count = k => points.filter(p => flag(p, k)).length;
    const n2 = incidents.filter(c => c.level === 2).length;
    const stats = { rows: points.length, segments: recs.size, scored: points.filter(p => Number.isFinite(numberOrNaN(p.score))).length,
      invalid: points.filter(p => p.status !== 'ok').length, alarm_rows: count('stage1'), stage1_rows: count('stage1'), stage2_rows: count('stage2'),
      v2_alarm_rows: count('v2_alarm'), r1_rows: count('inherited1'), r1_only_rows: points.filter(p => flag(p, 'inherited1') && !flag(p, 'own1')).length,
      r1_release_rows: count('released1'), r2_hold_rows: count('r2_hold'), insufficient_rows: count('insufficient'),
      stage1_events: incidents.length, stage2_events: points.filter(p => Number(p.stage2_event) > 0).reduce((s, p, i, a) => s + (i === 0 || Number(a[i - 1].stage2_event) !== Number(p.stage2_event) ? 1 : 0), 0),
      level2_incidents: n2, level1_incidents: incidents.length - n2 };
    return { ...full, points, incidents, cases, stats };
  }
  let simCache = null;
  function viewNow() {
    const full = state.result;
    if (!full || !state.sim) return full;
    const cursor = state.sim.row;
    if (simCache && simCache.source === full && simCache.row === cursor) return simCache.view;
    const view = buildView(full, cursor);
    simCache = { source: full, row: cursor, view };
    return view;
  }

  async function api(path, body) {
    const res = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) throw new Error((data && data.error) || `HTTP ${res.status}`);
    return data;
  }
  function setBusy(busy) {
    state.busy = busy;
    ['analyze', 'dataset', 'split', 'alpha', 'prior', 'file', 'simulate'].forEach(id => { $(id).disabled = busy; });
  }

  // ---------- 탭 ----------
  document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === tab));
    document.querySelectorAll('.tab-page').forEach(p => { p.hidden = p.id !== tab.dataset.tab; });
  }));

  // ---------- 분석 ----------
  async function analyze() {
    if (state.busy) return;
    const dataset = $('dataset').value;
    const request = { split: $('split').value, alpha: Number($('alpha').value), prior: Number($('prior').value), dataset };
    if (dataset === 'upload') {
      if (!state.upload) { setMessage('먼저 CSV를 불러오세요.', true); return; }
      request.csv = state.upload.csv;
    }
    setBusy(true);
    setMessage(dataset === 'upload' ? `${state.upload.name} 분석 중…` : '실제 기록을 불러오고 있습니다.');
    try {
      const result = await api('/api/analyze', request);
      state.result = result;
      state.selected = null;
      stopReplay(); stopSim(false);
      renderResult();
      const src = dataset === 'upload' ? state.upload.name : result.source_name;
      const st = result.stage || {};
      const official = Math.abs(Number(result.alpha) - Number(st.official_alpha || 0.01)) < 1e-12;
      setMessage(`${src} · ${fmt.int(result.stats.rows)}행 · 정상 기준 ${result.split} (보정 구간 ${result.calibration_segments}개) · α ${fmt.pct(result.alpha, 0)}${official ? '(제출 체계)' : '(비교용, 제출 체계는 1%)'} · 전류 R² 기준 ${fmt.num(st.r2_ref, 4)} · ${result.probability_available ? `이상 행 비율 π ${fmt.pct(result.prior, 1)}` : '라벨 확률 보정기 없음'}${result.stats.v2_mismatch_rows ? ` · 주의: v2 두 계산 불일치 ${result.stats.v2_mismatch_rows}행` : ''} · 처리 ${fmt.num(result.stats.elapsed_s, 2)}초`);
      if (state.initialIncident != null) {
        const id = state.initialIncident, k = state.initialCase;
        state.initialIncident = null; state.initialCase = null;
        const inc = incidentsOf().find(c => Number(c.incident_id) === id);
        if (inc) { const members = casesOf(inc); selectIncident(id, k != null && members[k - 1] ? members[k - 1].case_uid : undefined); }
      }
    } catch (err) {
      setMessage(`분석 실패: ${err.message}`, true);
    } finally {
      setBusy(false);
    }
  }
  $('analyze').addEventListener('click', analyze);
  ['dataset', 'split', 'alpha', 'prior'].forEach(id => $(id).addEventListener('change', analyze));
  $('file').addEventListener('change', () => {
    const file = $('file').files[0];
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) { setMessage('CSV는 8 MB 이하만 불러올 수 있습니다.', true); $('file').value = ''; return; }
    const reader = new FileReader();
    reader.onload = () => {
      state.upload = { name: file.name, csv: String(reader.result) };
      const select = $('dataset');
      let option = select.querySelector('option[value="upload"]');
      if (!option) { option = document.createElement('option'); option.value = 'upload'; select.appendChild(option); }
      option.textContent = `불러온 CSV · ${file.name}`;
      select.value = 'upload';
      $('file').value = '';
      analyze();
    };
    reader.onerror = () => setMessage('파일을 읽지 못했습니다.', true);
    reader.readAsText(file);
  });

  // ---------- 결과 ----------
  function renderStats() {
    const r = viewNow();
    const s = r.stats;
    const list = incidentsOf().filter(simVisible);
    const l2 = list.filter(c => levelNow(c) === 2).length;
    $('k-case').textContent = fmt.int(l2);
    $('k-level1').textContent = fmt.int(list.length - l2);
    $('k-case-sub').textContent = list.length ? `사건 ${fmt.int(list.length)}개 중 · R2를 통과한 경보 + R1 · 현장 점검` : '경보 사건이 없습니다';
    const rep = repeatCriterion();
    const official = Math.abs(Number(r.alpha) - Number((r.stage || {}).official_alpha || 0.01)) < 1e-12;   // 되풀이 기준은 α 1%의 정상 경보량으로 정했다
    $('k-level1-sub').textContent = `v2 + R1 경보 · 화면 표시(출동 없음)${rep && official ? ` · 되풀이 기준 교대 ${fmt.int(rep.threshold)}건 이상` : (rep ? ' · 되풀이 기준은 α 1%에서만 정함' : '')}`;
    $('k-r1').textContent = `${fmt.int(s.r1_rows)}행`;
    $('k-r1-sub').textContent = `R1로만 켜진 행 ${fmt.int(s.r1_only_rows)} · 해제 ${fmt.int(s.r1_release_rows)}회. 직전 기록이 확인된 이상이고 60초 안이면 이어받음`;
    $('k-r2').textContent = `${fmt.int(s.r2_hold_rows)}행`;
    $('k-short').textContent = s.rows ? fmt.pct(s.insufficient_rows / s.rows, 1) : '—';
    $('k-short-sub').textContent = `${fmt.int(s.insufficient_rows)}행 · 기록 첫 7행·수집 오류(R2 보류·R1 해제 불가)${s.invalid ? ` · 수집 오류 ${fmt.int(s.invalid)}행` : ''}`;
    $('k-segment').textContent = fmt.int(s.segments);
    $('k-rows').textContent = `${fmt.int(s.rows)}행 · 1단계 경보 ${fmt.int(s.stage1_rows)}행 · 2단계 ${fmt.int(s.stage2_rows)}행${(!state.sim && r.warnings && r.warnings.length) ? ` · ${r.warnings[0]}` : ''}`;
  }
  function renderResult() {
    renderStats();
    renderQueue();
    const first = filteredIncidents()[0];
    if (first) selectIncident(first.incident_id); else renderDetail(null);
  }
  function filteredIncidents() {
    const all = incidentsOf().filter(simVisible);
    const keep = c => state.filter === 'all' ? true : state.filter === 'r1' ? Number(c.r1_rows) > 0
      : state.filter === 'r2' ? Number(c.r2_hold_rows) > 0 : String(c.evidence).split('+').includes(state.filter);
    let list = all.filter(keep);
    if (state.levelFilter !== 'all') list = list.filter(c => levelNow(c) === Number(state.levelFilter));
    return [...list].sort((a, b) => state.sort === 'priority' ? (a.priority_rank - b.priority_rank) : (a.first_row - b.first_row));
  }
  function stageLine(c) {
    const lv = levelNow(c);
    if (lv === 2) {
      const dt = Number(c.escalation_after_first_s);
      return `점검 요청 승격: ${Number.isFinite(dt) && dt > 0 ? `첫 주의 ${fmt.num(dt, 1)}초 뒤` : '첫 경보와 같은 행'}`;
    }
    if (Number(c.level) === 2) return '아직 1단계(모의 운용: 2단계 행 전)';
    if (Number(c.r2_hold_rows) > 0) return 'R2 보류: 크기 단독 + 전류 파형 정상 → 2단계로 올리지 않음';
    if (Number(c.r1_only_rows) === Number(c.alarm_rows)) return '1단계 R1 이어받음만(2단계 입력 경보 없음)';
    return '2단계 조건 미충족(R2 통과 경보가 R1 확인 기준에 못 미침)';
  }
  function renderQueue() {
    const list = filteredIncidents();
    $('queue-count').textContent = fmt.int(list.length);
    const queue = $('queue');
    if (!list.length) {
      queue.innerHTML = `<div class="empty">${incidentsOf().length ? '선택한 조건의 사건이 없습니다.' : '경보가 발생한 사건이 없습니다.'}</div>`;
      return;
    }
    queue.innerHTML = list.map(c => {
      const chips = String(c.evidence).split('+').filter(Boolean).map(e => `<span class="chip ${esc(e)}">${esc(REASON_LABEL[e] || e)}</span>`).join('')
        + (Number(c.r1_rows) > 0 ? `<span class="chip r1">R1 이어받음 ${fmt.int(c.r1_rows)}행</span>` : '')
        + (Number(c.release_rows) > 0 ? '<span class="chip rel">R1 해제</span>' : '')
        + (Number(c.r2_hold_rows) > 0 ? `<span class="chip r2">R2 보류 ${fmt.int(c.r2_hold_rows)}행</span>` : '')
        + (Number(c.insufficient_rows) > 0 ? `<span class="chip short">관측 부족 ${fmt.int(c.insufficient_rows)}행</span>` : '');
      const ref = c.reference_label == null ? '' : (Number(c.reference_label) === 1 ? ' · 참조 라벨: 이상' : ' · 참조 라벨: 정상');
      const lv = levelNow(c), o = outcomeOf(c);
      const done = o.outcome ? ` · <span class="done">${esc(o.outcome)}</span>` : '';
      const span = Number(c.cases) > 1 ? ` ~ ${esc(fmt.time(c.last_timestamp))}` : '';
      return `<button type="button" class="queue-item${Number(c.incident_id) === state.selected ? ' selected' : ''}" data-incident="${c.incident_id}">
        <div class="queue-top"><span class="queue-id"><em class="badge l${lv}">${LEVEL[lv]}</em> 우선 ${fmt.int(c.priority_rank)} · 사건 ${fmt.int(c.incident_id)} · 기록 ${fmt.int(c.cases)}</span><span class="queue-time">${esc(fmt.time(c.first_timestamp))}${span}</span></div>
        <div class="chips">${chips}</div>
        <div class="queue-action">1단계 ${fmt.int(c.alarm_rows)}행 · 2단계 ${fmt.int(c.stage2_rows)}행 / 관측 ${fmt.int(c.observed_rows)}행 · 권장 확인: ${esc(c.action || '—')}${ref}${done}</div>
        <div class="stage-line">${esc(stageLine(c))}</div>
      </button>`;
    }).join('');
    queue.querySelectorAll('.queue-item').forEach(el => el.addEventListener('click', () => selectIncident(Number(el.dataset.incident))));
  }
  const refocus = () => { renderQueue(); const list = filteredIncidents(); if (!list.length) renderDetail(null); else if (!list.some(c => Number(c.incident_id) === state.selected)) selectIncident(list[0].incident_id); };
  $('sort').addEventListener('change', () => { state.sort = $('sort').value; renderQueue(); });
  $('level-filter').addEventListener('change', () => { state.levelFilter = $('level-filter').value; refocus(); });
  $('filter').addEventListener('change', () => { state.filter = $('filter').value; refocus(); });

  function selectIncident(incidentId, caseUid) {
    state.selected = Number(incidentId);
    stopReplay();
    document.querySelectorAll('.queue-item').forEach(el => el.classList.toggle('selected', Number(el.dataset.incident) === state.selected));
    const item = document.querySelector(`.queue-item[data-incident="${state.selected}"]`);
    if (item && item.scrollIntoView) item.scrollIntoView({ block: 'nearest' });
    const inc = incidentsOf().find(c => Number(c.incident_id) === state.selected) || null;
    const members = inc ? casesOf(inc) : [];
    const c = members.find(x => Number(x.case_uid) === Number(caseUid)) || members[0] || null;
    state.selectedCase = c ? Number(c.case_uid) : null;
    renderDetail(inc, c);
  }
  function caseRows(c) { return c ? viewNow().points.filter(p => p.row_id >= c.row_from && p.row_id <= c.row_to) : []; }
  function currentRows() { return caseRows(((viewNow() || {}).cases || []).find(c => Number(c.case_uid) === state.selectedCase)); }

  function renderDetail(inc, c) {
    const summary = $('detail-summary');
    if (state.sim && inc) {
      inc = incidentsOf().find(x => Number(x.incident_id) === Number(inc.incident_id));
      const members = inc ? casesOf(inc) : [];
      c = members.find(x => c && Number(x.case_uid) === Number(c.case_uid)) || members[0];
    }
    if (!inc || !c) {
      state.selected = null; state.selectedCase = null; stopReplay(); hideTooltip();
      $('scrubber').disabled = true; $('replay').disabled = true;
      $('detail-title').textContent = state.result ? '경보 사건이 없습니다' : '점검 사건을 선택하세요';
      $('reference').textContent = '';
      summary.innerHTML = '경보가 발생한 시점과 두 단계 판정 근거를 함께 확인합니다.';
      $('current-chart').innerHTML = ''; $('score-chart').innerHTML = ''; $('stage-chart').innerHTML = '';
      $('action').textContent = '—'; $('position').textContent = '—';
      $('checklist').textContent = '관측 이상에 대한 확인 순서입니다. 고장 원인 확정이나 자동 정지 명령이 아닙니다.';
      $('quality-action').textContent = '—'; $('suspect').textContent = '—'; $('outcome').hidden = true;
      $('scrubber').max = 1; $('scrubber').value = 1;
      return;
    }
    const rows = caseRows(c);
    const members = casesOf(inc);
    $('scrubber').disabled = !!state.sim; $('replay').disabled = !!state.sim;
    $('detail-title').textContent = `사건 ${fmt.int(inc.incident_id)} · 기록 ${members.findIndex(x => x.case_uid === c.case_uid) + 1}/${members.length} · 구간 ${fmt.int(c.record_id)} · ${fmt.int(rows.length)}관측`;
    $('reference').textContent = c.reference_label == null ? '참조 라벨 없음' : (Number(c.reference_label) === 1 ? '참조 라벨: 이상 기록' : '참조 라벨: 정상 기록');
    const reasons = String(c.evidence).split('+').filter(Boolean).map(e => reasonLabel(e, c)).join(' + ');
    const thr = state.result.threshold;
    const lv = levelNow(inc);
    const dt = Number(inc.escalation_after_first_s);
    const esc2 = lv === 2 ? (Number.isFinite(dt) && dt > 0 ? `첫 주의 ${fmt.num(dt, 1)}초 뒤(행 ${fmt.int(inc.escalation_row)})` : `첫 경보와 같은 행(행 ${fmt.int(inc.escalation_row)})`) : stageLine(inc);
    const rel = c.release_position != null ? `이 기록 ${fmt.int(Number(c.release_position) + 1)}번째 관측에서 해제(전류 R² 정상)` : (Number(c.r1_rows) > 0 ? '이 기록 안에서 해제 안 됨' : '없음');
    summary.innerHTML = [
      ['사건 단계', `${LEVEL[lv]}${lv === 2 ? ' · 현장 점검' : ' · 화면 표시·기록'} · 기록 ${members.length}개`],
      ['2단계 승격', esc2],
      ['R1 이어받음(이 기록)', `${fmt.int(c.r1_rows)}행(R1만 ${fmt.int(c.r1_only_rows)}행) · ${rel}`],
      ['R2 보류(이 기록)', `${fmt.int(c.r2_hold_rows)}행`],
      ['관측 부족(경보 행)', `${fmt.int(c.insufficient_rows)}행 · 기록 첫 7행은 파형 판단 전`],
      [state.sim ? '현재까지 운전 상태' : '운전 상태(기록 끝)', operatingStateText(c)],
      ['첫 경보', `${fmt.num(c.detection_delay_s, 1)}초 (${fmt.int(Number(c.first_alarm_position) + 1)}번째 관측)`],
      ['경보 관측(이 기록)', `1단계 ${fmt.int(c.alarm_rows)} · 2단계 ${fmt.int(c.stage2_rows)} / ${fmt.int(c.observed_rows)}행`],
      ['문턱 대비 최대 점수', Number.isFinite(thr) && thr > 0 && c.peak_score != null ? `${fmt.num(c.peak_score, 2)} / ${fmt.num(thr, 2)} (×${fmt.num(c.peak_score / thr, 1)})` : fmt.num(c.peak_score, 2)],
      ['최소 p값', `${fmt.num(c.min_p, 4)} (가능한 최솟값 ${fmt.num(state.result.min_p_attainable, 4)})`],
      ['근거(v2 성분)', reasons || 'R1 이어받음(직전 기록)'],
      ['이상 확률(참고)', `${probText(c)} (π ${fmt.pct(state.result.prior, 1)} 가정)`],
    ].map(([k, v]) => `<div><span>${k}</span><b>${esc(v)}</b></div>`).join('') + (members.length > 1
      ? `<div class="case-tabs">${members.map((x, k) => `<button type="button" class="quiet${x.case_uid === c.case_uid ? ' on' : ''}" data-case="${x.case_uid}">기록 ${k + 1} · 구간 ${fmt.int(x.record_id)}${Number(x.level) === 2 ? ' · 2단계' : ''}</button>`).join('')}</div>` : '');
    summary.querySelectorAll('.case-tabs button').forEach(el => el.addEventListener('click', () => selectIncident(inc.incident_id, Number(el.dataset.case))));
    $('action').textContent = c.action || '—';
    const rule = ((state.overview && state.overview.decision_table) || []).find(r => r.action === c.action);
    $('checklist').textContent = `먼저 운전 상태 확인: ${operatingStateText(c)}. ` + (rule ? `점검 항목(가설): ${rule.checklist} · 고장 모드 후보 ${rule.failure_modes}` : '관측 이상에 대한 확인 순서입니다. 고장 원인 확정이나 자동 정지 명령이 아닙니다.')
      + (lv === 1 ? ' 1단계는 출동하지 않고 기록만 합니다. 같은 교대에 되풀이 기준 이상 쌓이면 품질 샘플 검사를 앞당기고 다음 정지 때 진동 항목을 봅니다.' : '');
    $('quality-action').textContent = inc.quality_action || '—';
    $('suspect').textContent = Number(inc.suspect_open) === 1
      ? `의심 생산 시간창(사건): ${inc.suspect_from ? fmt.time(inc.suspect_from) : '자료 처음'} ~ ${inc.suspect_to ? fmt.time(inc.suspect_to) : '진행 중'} (열림 · 다음 정상 기록을 확인할 때까지)`
      : `의심 생산 시간창(사건): ${fmt.time(inc.suspect_from)} ~ ${fmt.time(inc.suspect_to)} (분당 20~60행정 가정으로 수량을 환산해 확인)`;
    fillOutcome(inc);
    $('scrubber').max = rows.length; $('scrubber').value = rows.length;
    state.cursor = null;
    drawCharts(rows, rows.length);
  }

  function drawCharts(rows, upto) {
    const shown = rows.slice(0, upto);
    $('position').textContent = `${fmt.int(upto)} / ${fmt.int(rows.length)} 관측`;
    const marker = r => flag(r, 'stage1') ? { color: flag(r, 'stage2') ? ALARM : CAUTION, hollow: !flag(r, 'own1') } : null;
    lineChart($('current-chart'), shown, [{ key: 'AI2_Current', name: '전류', color: '#176d55', dash: '' }], { marker, unit: '', domainRows: rows });
    stageStrip($('stage-chart'), shown, rows.length);
    lineChart($('score-chart'), shown, SERIES, { threshold: state.result.threshold, domainRows: rows, unit: '' });
  }

  // 행마다 세 줄: 단계(점검 요청·주의), R1(이어받음·해제), R2·관측(보류·부족). 라이브러리 없음.
  function stageStrip(container, rows, total) {
    const W = Math.max(280, container.clientWidth || 600), H = 84;
    const m = { l: 42, r: 12, t: 4, b: 18 };
    const n = Math.max(total, 1), laneH = (H - m.t - m.b) / 3, cw = (W - m.l - m.r) / n;
    let svg = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="두 단계 판정 띠">`;
    [['단계', 0], ['R1', 1], ['R2·부족', 2]].forEach(([name, k]) => {
      svg += `<rect x="${m.l}" y="${m.t + laneH * k}" width="${W - m.l - m.r}" height="${laneH - 3}" fill="#f4f6f7"/><text x="${m.l - 6}" y="${m.t + laneH * k + laneH / 2 + 2}" text-anchor="end">${name}</text>`;
    });
    rows.forEach((r, i) => {
      const x = (m.l + i * cw).toFixed(1), w = Math.max(cw - 1, 1).toFixed(1), h = (laneH - 3).toFixed(1);
      const lv = Number(r.stage_level);
      if (lv > 0) svg += `<rect x="${x}" y="${m.t}" width="${w}" height="${h}" fill="${lv === 2 ? ALARM : CAUTION}"/>`;
      if (flag(r, 'released1')) svg += `<rect x="${x}" y="${(m.t + laneH).toFixed(1)}" width="${w}" height="${h}" fill="${RELEASE}"/>`;
      else if (flag(r, 'inherited1')) svg += `<rect x="${x}" y="${(m.t + laneH).toFixed(1)}" width="${w}" height="${h}" fill="${R1}"/>`;
      if (flag(r, 'r2_hold')) svg += `<rect x="${x}" y="${(m.t + 2 * laneH).toFixed(1)}" width="${w}" height="${h}" fill="${R2}"/>`;
      else if (flag(r, 'insufficient')) svg += `<rect x="${x}" y="${(m.t + 2 * laneH).toFixed(1)}" width="${w}" height="${h}" fill="${SHORT}"/>`;
    });
    const xticks = Math.min(6, n - 1);
    for (let k = 0; k <= xticks && n > 1; k++) {
      const i = Math.round((n - 1) * k / xticks);
      svg += `<text x="${(m.l + (i + 0.5) * cw).toFixed(1)}" y="${H - 4}" text-anchor="middle">${fmt.num(i * 0.1, 1)}s</text>`;
    }
    if (state.cursor != null && state.cursor < rows.length) {
      const x = m.l + (state.cursor + 0.5) * cw;
      svg += `<line x1="${x}" x2="${x}" y1="${m.t}" y2="${H - m.b}" stroke="#4a5a61" stroke-width="1"/>`;
    }
    svg += '</svg>';
    container.innerHTML = svg;
  }

  // 단일 SVG 선 그래프: 격자·축 라벨·경보 점(채움 = v2 자기 경보, 빈 원 = R1로만 켜진 행)·문턱선·호버 툴팁.
  function lineChart(container, rows, series, opts) {
    const W = Math.max(280, container.clientWidth || 600), H = 143;
    const m = { l: 42, r: 12, t: 10, b: 22 };
    const domain = opts.domainRows || rows;
    const n = domain.length;
    const vals = [];
    domain.forEach(r => series.forEach(s => { const v = numberOrNaN(r[s.key]); if (Number.isFinite(v)) vals.push(v); }));
    if (opts.threshold != null && Number.isFinite(opts.threshold)) vals.push(opts.threshold);
    if (!vals.length) { container.innerHTML = '<div class="empty">표시할 값이 없습니다</div>'; return; }
    let lo = Infinity, hi = -Infinity;
    vals.forEach(v => { lo = Math.min(lo, v); hi = Math.max(hi, v); });
    if (opts.threshold != null) lo = Math.min(lo, 0);
    if (hi === lo) { hi = lo + 1; }
    const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
    const x = i => m.l + (n <= 1 ? 0 : (i / (n - 1)) * (W - m.l - m.r));
    const y = v => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
    let svg = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(series.map(s => s.name).join(', '))} 시계열">`;
    const ticks = 3;
    for (let k = 0; k <= ticks; k++) {
      const v = lo + pad + (hi - lo - 2 * pad) * k / ticks;
      svg += `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${m.l - 6}" y="${y(v) + 3}" text-anchor="end">${fmt.num(v, Math.abs(hi) >= 50 ? 0 : 1)}</text>`;
    }
    const xticks = Math.min(6, n - 1);
    for (let k = 0; k <= xticks && n > 1; k++) {
      const i = Math.round((n - 1) * k / xticks);
      svg += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${fmt.num(i * 0.1, 1)}s</text>`;
    }
    if (opts.threshold != null && Number.isFinite(opts.threshold)) {
      svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(opts.threshold)}" y2="${y(opts.threshold)}" stroke="${ALARM}" stroke-width="1" stroke-dasharray="3 3"/><text x="${m.l + 4}" y="${y(opts.threshold) - 4}" text-anchor="start" style="fill:${ALARM}">경보 문턱 ${fmt.num(opts.threshold, 2)}</text>`;
    }
    series.forEach(s => {
      let d = '', pen = false;
      rows.forEach((r, i) => { const v = numberOrNaN(r[s.key]); if (!Number.isFinite(v)) { pen = false; return; } d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true; });
      svg += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"${s.dash ? ` stroke-dasharray="${s.dash}"` : ''}/>`;
      const last = [...rows].reverse().find(r => Number.isFinite(numberOrNaN(r[s.key])));
      if (last && series.length > 1) svg += `<text x="${W - m.r}" y="${y(Number(last[s.key])) - 5}" text-anchor="end" style="fill:${s.color}">${esc(s.name)}</text>`;
    });
    if (opts.marker) {
      rows.forEach((r, i) => {
        const mk = opts.marker(r), v = numberOrNaN(r[series[0].key]);
        if (mk && Number.isFinite(v)) svg += mk.hollow
          ? `<circle cx="${x(i)}" cy="${y(v)}" r="3.6" fill="#fff" stroke="${mk.color}" stroke-width="1.8"/>`
          : `<circle cx="${x(i)}" cy="${y(v)}" r="4" fill="${mk.color}" stroke="#fff" stroke-width="2"/>`;
      });
    }
    if (state.cursor != null && state.cursor < rows.length) {
      const i = state.cursor;
      svg += `<line x1="${x(i)}" x2="${x(i)}" y1="${m.t}" y2="${H - m.b}" stroke="#8a969e" stroke-width="1"/>`;
      series.forEach(s => { const v = numberOrNaN(rows[i][s.key]); if (Number.isFinite(v)) svg += `<circle cx="${x(i)}" cy="${y(v)}" r="4.5" fill="${s.color}" stroke="#fff" stroke-width="2"/>`; });
    }
    svg += '</svg>';
    container.innerHTML = svg;
    const el = container.querySelector('svg');
    const move = ev => {
      if (!rows.length) return;
      const rect = el.getBoundingClientRect();
      const px = (ev.clientX - rect.left) * (W / rect.width);
      const i = Math.max(0, Math.min(rows.length - 1, Math.round((px - m.l) / (W - m.l - m.r) * (n - 1))));
      if (i !== state.cursor) { state.cursor = i; showTooltip(rows[i], i, ev); redrawCursor(); }
      else positionTooltip(ev);
    };
    el.addEventListener('mousemove', move);
    el.addEventListener('mouseleave', () => { state.cursor = null; hideTooltip(); redrawCursor(); });
  }
  function redrawCursor() {
    if (!state.result || state.selectedCase == null) return;
    const rows = currentRows();
    drawCharts(rows, Number($('scrubber').value) || rows.length);
  }
  let tip = null;
  function tooltip() { if (!tip) { tip = document.createElement('div'); tip.className = 'tooltip'; tip.hidden = true; document.body.appendChild(tip); } return tip; }
  function stageText(row) {
    const lv = Number(row.stage_level);
    const tags = [lv === 2 ? '2단계 점검 요청' : lv === 1 ? '1단계 주의' : '경보 없음'];
    if (flag(row, 'inherited1')) tags.push(flag(row, 'own1') ? 'R1 이어받음(자기 경보도 있음)' : 'R1 이어받음');
    if (flag(row, 'released1')) tags.push('R1 해제');
    if (flag(row, 'r2_hold')) tags.push('R2 보류');
    if (flag(row, 'insufficient')) tags.push('관측 부족');
    return tags.join(' · ');
  }
  function showTooltip(row, i, ev) {
    const t = tooltip();
    const r2 = numberOrNaN(row.prefix_r2);
    const lines = [`<b>${fmt.num(i * 0.1, 1)}초 · ${esc(fmt.time(row.timestamp))}</b>`,
      `전류 ${fmt.num(row.AI2_Current, 2)} · 진동 ${fmt.num(row.AI0_Vibration, 3)} / ${fmt.num(row.AI1_Vibration, 3)}`,
      ...SERIES.map(s => `<i style="background:${s.color}"></i>${s.name} ${fmt.num(row[s.key], 2)}`),
      `<b>${esc(stageText(row))}</b>`,
      `전류 R²(기록 시작부터) ${Number.isFinite(r2) ? fmt.num(r2, 4) : '— (8행 미만)'}`,
      row.status !== 'ok' ? '<span class="warn">수집 오류 · 판정 보류</span>' :
        (flag(row, 'v2_alarm') ? `<span class="warn">v2 경보 · p=${fmt.num(row.p_value, 4)} · ${String(row.stage_evidence).split('+').map(e => REASON_LABEL[e] || e).join('+')}</span>` : `p=${fmt.num(row.p_value, 4)} · v2 정상 범위`)];
    t.innerHTML = lines.join('<br>');
    t.hidden = false;
    positionTooltip(ev);
  }
  function positionTooltip(ev) { const t = tooltip(); const x = Math.min(ev.clientX + 14, window.innerWidth - t.offsetWidth - 8); t.style.left = `${x}px`; t.style.top = `${ev.clientY + 14}px`; }
  function hideTooltip() { if (tip) tip.hidden = true; }

  // ---------- 재생 ----------
  $('scrubber').addEventListener('input', () => { if (state.selectedCase == null) return; state.cursor = null; drawCharts(currentRows(), Number($('scrubber').value)); });
  function stopReplay() { if (state.replay) { clearInterval(state.replay); state.replay = null; $('replay').textContent = '▷ 선택 구간 재생'; } }
  $('replay').addEventListener('click', () => {
    if (state.selectedCase == null) return;
    if (state.replay) { stopReplay(); return; }
    const rows = currentRows();
    let i = 0;
    $('replay').textContent = '■ 재생 중지';
    state.replay = setInterval(() => {
      i += 1; $('scrubber').value = i; state.cursor = null; drawCharts(rows, i);
      if (i >= rows.length) stopReplay();
    }, 100);
  });

  // ---------- 점검 결과 기록(사건 단위) ----------
  function fillOutcome(inc) {
    if (state.sim) { $('outcome').hidden = true; return; }
    const o = outcomeOf(inc);
    $('outcome').hidden = false;
    $('o-owner').value = o.owner || ''; $('o-outcome').value = o.outcome || ''; $('o-measure').value = o.measure || '';
    $('outcome-state').textContent = o.confirmed_at ? `${o.status} · ${fmt.time(o.confirmed_at)} 기록` : '열림 · 미확인';
  }
  function saveOutcome(inc, fields) {
    const record = { confirmed_at: new Date().toISOString(), owner: fields.owner, outcome: fields.outcome, measure: fields.measure,
      status: (fields.outcome === '정상 확인' || fields.outcome === '이상 확인') ? '닫힘' : '열림' };
    return { saved: store.set(outcomeKey(inc), record), record };
  }
  $('outcome').addEventListener('submit', ev => {
    ev.preventDefault();
    const inc = incidentsOf().find(x => Number(x.incident_id) === state.selected);
    if (!inc) return;
    const { saved, record } = saveOutcome(inc, { owner: $('o-owner').value.trim(), outcome: $('o-outcome').value, measure: $('o-measure').value.trim() });
    fillOutcome(inc); renderQueue();
    setMessage(saved ? `사건 ${inc.incident_id} 점검 결과를 기록했습니다(${record.status}).` : '이 브라우저에서는 결과를 저장할 수 없습니다. CSV로 내보내 따로 보관하세요.', !saved);
  });

  // ---------- 모의 운용: 1단계 사건 시작(주의)과 첫 2단계 행(점검 요청)을 그 행이 들어온 때 알린다 ----------
  function renderSimView() {
    renderStats();
    const list = filteredIncidents();
    const inc = list.find(c => Number(c.incident_id) === state.selected) || list[0];
    const members = inc ? casesOf(inc) : [];
    const c = members.find(x => Number(x.case_uid) === state.selectedCase) || members[0];
    state.selected = inc ? Number(inc.incident_id) : null;
    state.selectedCase = c ? Number(c.case_uid) : null;
    renderQueue(); renderDetail(inc, c);
  }
  function stopSim(render = true) {
    if (!state.sim) return;
    clearInterval(state.sim.timer); state.sim = null;
    $('sim-bar').hidden = true; $('simulate').textContent = '▶ 모의 운용';
    if (render && state.result) renderSimView();
  }
  function startSim() {
    if (!state.result || state.busy) return;
    if (state.sim) { stopSim(); return; }
    stopReplay();
    const points = state.result.points, rowsPerTick = 10;
    const events = [];
    (state.result.incidents || []).forEach(c => { events.push({ row: c.first_row, text: `주의 · 사건 ${c.incident_id}` }); if (Number(c.level) === 2 && c.escalation_row != null) events.push({ row: c.escalation_row, text: `점검 요청 · 사건 ${c.incident_id}` }); });
    events.sort((a, b) => a.row - b.row);
    state.sim = { row: -1, next: 0, timer: null };
    $('sim-bar').hidden = false; $('simulate').textContent = '■ 모의 중지';
    state.sim.timer = setInterval(() => {
      const sim = state.sim; if (!sim) return;
      sim.row = Math.min(points.length - 1, sim.row + rowsPerTick);
      $('sim-clock').textContent = `${fmt.time(points[sim.row].timestamp)} · ${fmt.int(sim.row + 1)} / ${fmt.int(points.length)}행`;
      while (sim.next < events.length && events[sim.next].row <= sim.row) { $('sim-last').textContent = `최근 알림: ${events[sim.next].text}`; sim.next += 1; }
      renderSimView();
      if (sim.row >= points.length - 1) { $('sim-last').textContent += ' · 끝'; clearInterval(sim.timer); setTimeout(() => { if (state.sim === sim) stopSim(); }, 1500); }
    }, 100);
    $('sim-last').textContent = '관측 시작 대기 · 점검 결과 기록은 모의 종료 후 가능';
    renderSimView();
  }
  $('simulate').addEventListener('click', startSim);
  $('sim-stop').addEventListener('click', () => stopSim());

  // ---------- 내보내기(사건 단위, 두 단계 열·점검 결과 포함) ----------
  $('export').addEventListener('click', () => {
    const list = filteredIncidents();
    if (!list.length) { setMessage('내보낼 점검 사건이 없습니다.', true); return; }
    const cols = ['priority_rank', 'incident_id', 'level', 'level_name', 'first_timestamp', 'last_timestamp', 'escalation_row', 'escalation_after_first_s', 'cases', 'records', 'evidence',
      'alarm_rows', 'stage2_rows', 'own_rows', 'r1_rows', 'r1_only_rows', 'release_rows', 'r2_hold_rows', 'insufficient_rows', 'observed_rows', 'alarm_share', 'peak_score', 'action',
      'suspect_from', 'suspect_to', 'suspect_open', 'quality_action', 'max_probability', 'max_likelihood_ratio', 'reference_label'];
    const outcomeCols = (state.overview && state.overview.outcome_columns) || ['confirmed_at', 'owner', 'outcome', 'measure', 'status'];
    const cell = v => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const csv = [cols.concat(outcomeCols, ['alpha', 'probability_prior']).join(','), ...list.map(c => { const o = outcomeOf(c); return cols.map(k => cell(c[k])).concat(outcomeCols.map(k => cell(o[k])), [cell(state.result.alpha), cell(state.result.prior)]).join(','); })].join('\n');
    const url = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a'); a.href = url; a.download = `press_guard_stage_incidents_${state.result.split}_a${Math.round(state.result.alpha * 100)}.csv`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  // ---------- 성능 검증 탭: 두 단계 경보 ----------
  const ci = (lo, hi, d = 1) => `${fmt.num(lo, d)}~${fmt.num(hi, d)}`;
  function renderStageEvidence(st) {
    const vol = st && st.volume, rep = st && st.replay;
    if (!vol) {
      ['stage-volume', 'stage-states', 'stage-repeat'].forEach(id => { $(id).innerHTML = '<div class="empty">정상 경보량 결과(analysis/press_stage_replay_2026-10-08/outputs/alarm_volume.json)가 없습니다. alarm_volume.py를 실행하세요.</div>'; });
    } else {
      const bench = Number(vol.sets[0] && vol.sets[0].benchmark_per_hour) || 6;
      $('stage-volume').innerHTML = `<table><thead><tr><th>정상 자료</th><th>단계</th><th>노출</th><th>경보 행</th><th>사건</th><th>시간당(95% 구간)</th><th>교대 8시간(95% 구간)</th><th>단측 95% 상한(시간당)</th><th>기준 ${fmt.num(bench, 0)}건/시</th></tr></thead><tbody>${
        vol.sets.map(r => `<tr${r.stage === 'stage2' ? ' class="highlight"' : ''}><td>${esc(r.set)}${r.window_events ? ` <small>(창별 ${esc(r.window_events)})</small>` : ''}</td><td>${STAGE_NAME[r.stage] || esc(r.stage)}</td><td>${fmt.num(r.exposure_min, 1)}분 · ${fmt.int(r.records)}기록</td><td>${fmt.int(r.alarm_rows)}</td><td>${fmt.int(r.events)}</td><td>${fmt.num(r.rate_h, 1)} (${ci(r.ci95_lo_h, r.ci95_hi_h)})</td><td>${fmt.num(r.per_shift, 1)} (${ci(r.ci95_lo_shift, r.ci95_hi_shift)})</td><td>${fmt.num(r.upper95_h, 1)}</td><td class="${r.upper95_within_benchmark ? 'ok-cell' : (r.point_within_benchmark ? '' : 'warn-cell')}">${r.upper95_within_benchmark ? '상한도 이하' : (r.point_within_benchmark ? '점추정만 이하' : '초과')}</td></tr>`).join('')
      }</tbody></table>`;
      const states = {};
      vol.states.forEach(r => { (states[r.state] = states[r.state] || { label: r.state_label, records: r.records, exposure_h: r.exposure_h })[r.stage] = r; });
      $('stage-states').innerHTML = `<table><thead><tr><th>운전 상태(domain/06)</th><th>기록</th><th>노출</th><th>1단계 사건 · 시간당(95%)</th><th>2단계 사건 · 시간당(95%)</th></tr></thead><tbody>${
        Object.values(states).map(s => `<tr><td>${esc(s.label)}</td><td>${fmt.int(s.records)}</td><td>${fmt.num(s.exposure_h * 60, 1)}분</td>${['stage1', 'stage2'].map(k => { const r = s[k] || {}; return `<td>${fmt.int(r.events)} · ${fmt.num(r.rate_h, 1)} (${ci(r.ci95_lo_h, r.ci95_hi_h)})</td>`; }).join('')}</tr>`).join('')
      }</tbody></table><p class="fine">사건은 첫 경보 행이 든 기록의 상태로, 노출은 기록 시작부터 다음 기록 시작까지를 그 기록의 상태로 셉니다. 상태별 노출이 2~12분이라 구간이 넓습니다.</p>`;
      const p = vol.repeat.primary;
      $('stage-repeat').innerHTML = `<div class="repeat-box"><strong>교대 ${fmt.int(p.threshold)}건 이상</strong><span>정상 1단계 사건률 시간당 ${fmt.num(p.rate_h, 2)}건(E3 5창 합침)이면 교대 8시간 평균 ${fmt.num(p.mean, 1)}건이고, ${fmt.int(p.threshold)}건 이상일 확률은 ${fmt.pct(p.p_at_threshold, 1)}(≤5%)입니다.</span></div><table><thead><tr><th>민감도 기준</th><th>시간당 사건</th><th>창</th><th>꼬리</th><th>평균</th><th>되풀이 기준</th><th>그 이상일 확률</th></tr></thead><tbody>${
        vol.repeat.all.map((r, k) => `<tr${k === 0 ? ' class="highlight"' : ''}><td>${esc(r.basis)}</td><td>${fmt.num(r.rate_h, 2)}</td><td>${fmt.num(r.hours, 0)}시간</td><td>${fmt.pct(r.tail, 0)}</td><td>${fmt.num(r.mean, 1)}</td><td>${fmt.int(r.threshold)}건</td><td>${fmt.pct(r.p_at_threshold, 1)}</td></tr>`).join('')
      }</tbody></table><p class="fine">정상 자료만으로 정한 값이며 이상 자료로 고르지 않았습니다. 사건이 2건뿐이고(같은 고부하 시간대) 창 사이 과산포를 배제하지 못하므로 도입 첫 달의 1단계 경보량으로 다시 정합니다.</p>`;
    }
    if (!rep) { $('stage-replay').innerHTML = '<div class="empty">재생 대조 결과(replay_summary.json)가 없습니다. replay.py를 실행하세요.</div>'; return; }
    const rows = [];
    Object.entries(rep.splits).forEach(([sid, s]) => Object.entries(s.flows).forEach(([flow, f]) => rows.push(`<tr><td>${esc(sid)}</td><td>${flow === 'normal' ? '정상(검증→시험 한 흐름)' : '이상 21기록'}</td><td>${fmt.int(f.rows)}행 · 시험 ${fmt.int(f.test_rows)}행</td>${['stage1', 'stage2', 'v2'].map(k => `<td>${fmt.int(f.alarms[k].equal)}/${fmt.int(f.alarms[k].rows)}</td>`).join('')}<td>${fmt.num(f.score_max_abs_diff, 1)}</td><td>${f.chunks_equal ? '같음' : '다름'}</td></tr>`)));
    $('stage-replay').innerHTML = `<table><thead><tr><th>분할</th><th>흐름</th><th>행</th><th>1단계 = locked_v2_R1</th><th>2단계 = final_v2_R1_R2</th><th>v2</th><th>점수 최대 차이</th><th>한 행씩 = 무작위 묶음</th></tr></thead><tbody>${rows.join('')}</tbody></table><p class="fine">시험 행은 제출 예측 파일 열과 행마다 대조했습니다(검증 행은 공식 계산과 대조). 한 행 처리 시간 중앙 ${fmt.num(rep.latency_ms.median, 1)}ms · p99 ${fmt.num(rep.latency_ms.p99, 1)}ms(${esc(rep.cpu || '')}, 한 스레드). 같은 자료의 오프라인 재생이며 PLC 배포 검증이 아닙니다.</p>`;
  }
  function renderMethodNote(st) {
    const vol = st && st.volume;
    if (!vol) return;
    const e3 = k => vol.sets.find(r => r.set === 'E3 5창 합침' && r.stage === k);
    const s1 = e3('stage1'), s2 = e3('stage2'), p = vol.repeat.primary;
    if (!s1 || !s2) return;
    $('method-text').textContent = `1단계 주의는 사전 잠금 모델 v2 + R1의 경보이고(공식 성능), 2단계 점검 요청은 v2 경보에 R2 교차 확인을 먼저 적용한 뒤 R1을 붙인 경보로 늘 1단계 안에 있습니다. R1은 직전 기록(끝난 지 60초 안)이 확인된 이상이면 새 기록 첫 행부터 경보를 잇고 전류 R²가 정상 학습 기준 이상인 행(8행째부터)에서 풉니다. R2는 크기 성분만 문턱을 넘고 전류 파형이 정상인 경보를 2단계 입력에서 뺍니다. 정상 자료(E3 시간순 5창, ${fmt.num(s1.exposure_min, 1)}분)의 60초 묶음 사건은 1단계 시간당 ${fmt.num(s1.rate_h, 1)}건(95% ${ci(s1.ci95_lo_h, s1.ci95_hi_h)}), 2단계 ${fmt.int(s2.events)}건(95% 상한 시간당 ${fmt.num(s2.ci95_hi_h, 1)}건)입니다. 1단계 되풀이 기준은 교대 ${fmt.int(p.threshold)}건 이상(정상에서 ${fmt.pct(p.p_at_threshold, 1)})입니다. 같은 날 77분 자료의 추정이며, p값은 고장 확률이 아닙니다.`;
  }

  // ---------- 성능 검증 탭: 기존 v2 표(app.js와 같음) ----------
  function renderEvidence(o) {
    renderStageEvidence(o.stage);
    renderMethodNote(o.stage);
    const rows = o.metrics.filter(r => Number(r.alpha) === 0.01);
    const bars = (container, key, label, better) => {
      container.innerHTML = ['A', 'B'].map(split => {
        const v1 = rows.find(r => r.split === split && r.model === 'baseline_v1'), v2 = rows.find(r => r.split === split && r.model === 'guard_v2');
        if (!v1 || !v2) return '';
        const max = Math.max(Number(v1[key]), Number(v2[key]), 1e-9);
        const bar = (r, cls, name) => `<div class="bar${cls}"><div style="width:${(100 * Number(r[key]) / max).toFixed(1)}%"></div><span>${name} ${label(r[key])}</span></div>`;
        return `<div class="bar-group"><div class="bar-title"><span>정상 기준 ${split}</span><span>${better}</span></div>${bar(v1, '', 'v1')}${bar(v2, ' new', 'v2')}</div>`;
      }).join('');
    };
    bars($('f1-bars'), 'f1', v => fmt.num(v, 4), '높을수록 좋음');
    bars($('miss-bars'), 'fn', v => `${fmt.int(v)}행`, '낮을수록 좋음 · 이상 600행 중');
    $('comparison').innerHTML = `<table><thead><tr><th>정상 기준</th><th>모델</th><th>행 단위 F1</th><th>미탐 행</th><th>오경보 행</th><th>정상 알림 구간</th><th>이상 알림 구간</th><th>최대 첫 경보 지연</th></tr></thead><tbody>${
      ['A', 'B'].flatMap(split => ['baseline_v1', 'guard_v2'].map(model => rows.find(r => r.split === split && r.model === model)).filter(Boolean).map(r =>
        `<tr${r.model === 'guard_v2' ? ' class="highlight"' : ''}><td>${r.split}</td><td>${r.model === 'guard_v2' ? 'v2 · 정상 동역학 결합' : 'v1 · 기존 결합'}</td><td>${fmt.num(r.f1, 6)}</td><td>${fmt.int(r.fn)}</td><td>${fmt.int(r.fp)}</td><td>${fmt.int(r.normal_notified_segments)} / ${fmt.int(r.normal_segments)}</td><td>${fmt.int(r.abnormal_notified_segments)} / ${fmt.int(r.abnormal_segments)}</td><td>${fmt.num(r.delay_max_s, 1)}초</td></tr>`)).join('')
    }</tbody></table>`;
    renderConditions(o.conditions || []);
    renderWorkload(o.workload || []);
    renderDecisionTable(o.decision_table || []);
    renderLevels(o.levels || []);
    renderQualityRules(o);
    renderProbability(o);
    renderMonitorGain(o.monitor_gain || []);
    renderEffect(o.expected_effect || []);
    renderRobustness(o.robustness || []);
    const audit = o.audit && o.audit.checks ? o.audit.checks : [];
    const bench = o.benchmark && o.benchmark.runs ? o.benchmark.runs : [];
    const auditRows = audit.map(c => `<div class="audit-row"><span>${esc(c.name)}</span><b>${c.ok ? '통과' : '실패'} · ${esc(c.detail || '')}</b></div>`);
    const benchRows = bench.map(b => `<div class="audit-row"><span>처리 속도 · 묶음 ${esc(b.label)}</span><b>${fmt.int(Math.round(b.rows_per_second))}행/초 · 호출당 ${fmt.num(b.p95_ms, 1)}ms(p95)</b></div>`);
    $('audit-list').innerHTML = (auditRows.length || benchRows.length) ? auditRows.concat(benchRows).join('') : '<div class="empty">실행 검증 기록(outputs/audit.json)이 없습니다. audit.py를 실행하세요.</div>';
  }
  function renderConditions(rows) {
    const el = $('conditions');
    if (!rows.length) { el.innerHTML = '<div class="empty">조건표(outputs/error_conditions_v2.csv)가 없습니다.</div>'; return; }
    const pos = rows.filter(r => r.condition === 'pos_bin');
    const order = ['0', '1', '2–4', '5–6', '7–9', '≥10'];
    const cell = (split, model, subset, value) => { const r = pos.find(x => x.split_id === split && x.model === model && x.subset === subset && String(x.value) === value); return r ? `${fmt.int(r.error_rows)} / ${fmt.int(r.rows)}` : '—'; };
    el.innerHTML = `<table><thead><tr><th>정상 기준</th><th>모델</th><th>구분</th>${order.map(v => `<th>위치 ${v}</th>`).join('')}</tr></thead><tbody>${
      ['A', 'B'].flatMap(split => [['abnormal', '이상 미탐 행 / 행'], ['normal', '정상 오경보 행 / 행']].flatMap(([subset, label]) => ['v1', 'v2'].map(model =>
        `<tr${model === 'v2' ? ' class="highlight"' : ''}><td>${split}</td><td>${model}</td><td>${label}</td>${order.map(v => `<td>${cell(split, model, subset, v)}</td>`).join('')}</tr>`))).join('')
    }</tbody></table>`;
  }
  function renderWorkload(rows) {
    const el = $('workload');
    if (!rows.length) { el.innerHTML = '<div class="empty">업무량 표(outputs/workload_v2.csv)가 없습니다.</div>'; return; }
    el.innerHTML = `<table><thead><tr><th>정상 기준</th><th>α</th><th>경과 1시간당 구간</th><th>명목 비율</th><th>교대 8시간 · 명목</th><th>관측 알림 / 구간</th><th>교대 8시간 · 관측</th><th>관측 95% 상한</th><th>보정 반영 사후 95%</th></tr></thead><tbody>${
      rows.map(r => `<tr><td>${esc(r.split_id)}</td><td>${fmt.pct(r.alpha, 0)}</td><td>${fmt.int(Math.round(r.units_per_elapsed_hour))}</td><td>${fmt.pct(r.alpha_grid_rate, 2)}</td><td>${fmt.num(r.nominal_alerts_per_8h_elapsed, 0)}건</td><td>${fmt.int(r.first_alert_segments)} / ${fmt.int(r.normal_segments)}</td><td>${fmt.num(r.observed_alerts_per_8h_elapsed, 0)}건</td><td>${fmt.num(r.upper95_alerts_per_8h_elapsed, 0)}건</td><td>${fmt.num(r.posterior95_alerts_per_8h_elapsed, 0)}건</td></tr>`).join('')
    }</tbody></table>`;
  }
  function renderDecisionTable(rows) {
    const el = $('decision-table');
    if (!rows.length) { el.innerHTML = '<div class="empty">판단표가 없습니다.</div>'; return; }
    el.innerHTML = `<table><thead><tr><th>경보 근거</th><th>확인 대상(가설)</th><th>권장 확인</th><th>점검 항목(가설)</th><th>고장 모드 후보</th></tr></thead><tbody>${
      rows.map(r => `<tr><td>${esc(r.evidence)}</td><td>${esc(r.check_target)}</td><td>${esc(r.action)}</td><td>${esc(r.checklist || '')}</td><td>${esc(r.failure_modes || '')}</td></tr>`).join('')
    }</tbody></table>`;
  }
  function renderLevels(rows) {
    const el = $('levels');
    if (!rows.length) { el.innerHTML = '<div class="empty">단계별 표(outputs/alert_levels_v2.csv)가 없습니다.</div>'; return; }
    const shown = rows.filter(r => Number(r.alpha) === 0.01);
    el.innerHTML = `<table><thead><tr><th>모델 · 정상 평가 구간</th><th>단계(v2 프로토타입)</th><th>정상 알림 / 구간</th><th>교대 8시간 · 관측</th><th>95% 상한</th><th>이상 21구간 탐지</th><th>지연 중앙·최대</th></tr></thead><tbody>${
      shown.map(r => `<tr><td>${esc(r.model)} · ${esc(r.normal_window)}${r.same_calibration_as ? ` <small>(= ${esc(r.same_calibration_as)})</small>` : ''}</td><td>${LEVEL[r.level]}</td><td>${fmt.int(r.normal_alerted_segments)} / ${fmt.int(r.normal_segments)}</td><td>${fmt.num(r.alerts_per_8h_elapsed, 0)}건</td><td>${fmt.num(r.upper95_alerts_per_8h_elapsed, 0)}건</td><td>${fmt.int(r.abnormal_detected_segments)} / ${fmt.int(r.abnormal_segments)}</td><td>${fmt.num(r.delay_median_s, 1)} · ${fmt.num(r.delay_max_s, 1)}초</td></tr>`).join('')
    }</tbody></table>`;
  }
  function renderQualityRules(o) {
    const el = $('quality-rules');
    const qa = o.quality_actions || {};
    el.innerHTML = `<table><thead><tr><th>단계</th><th>품질 조치(가설)</th></tr></thead><tbody>${
      Object.keys(qa).map(k => `<tr><td>${LEVEL[k] || k}</td><td>${esc(qa[k])}</td></tr>`).join('')
    }</tbody></table>`;
  }
  function renderProbability(o) {
    const el = $('probability');
    const ev = (o.probability || []).filter(r => r.cv === '21fold' && r.unit === 'rows');
    if (!ev.length) { el.innerHTML = '<div class="empty">확률 평가표(outputs/probability_eval_v2.csv)가 없습니다.</div>'; return; }
    const name = { calibrated_isotonic: '라벨 보정 확률(교차 적합·LR 상한 121)', isotonic_uncapped: '상한 없는 등방 회귀(비교용)', platt_logistic: 'Platt(비교용)', naive_1_minus_p: '1−p (확률 아님, 비교용)', prevalence_only: '유병률만' };
    el.innerHTML = `<table><thead><tr><th>정상 기준</th><th>방법</th><th>Brier</th><th>log-loss</th><th>ECE</th></tr></thead><tbody>${
      ev.map(r => `<tr${r.method === 'calibrated_isotonic' ? ' class="highlight"' : ''}><td>${esc(r.split)}</td><td>${name[r.method] || esc(r.method)}</td><td>${fmt.num(r.brier, 4)}</td><td>${fmt.num(r.log_loss, 4)}</td><td>${fmt.num(r.ece, 4)}</td></tr>`).join('')
    }</tbody></table>`;
  }
  function renderMonitorGain(rows) {
    const el = $('monitor-gain');
    if (!rows.length) { el.innerHTML = '<div class="empty">감시 모의표(outputs/monitor_gain_v2.csv)가 없습니다.</div>'; return; }
    el.innerHTML = `<table><thead><tr><th>정상 기준</th><th>전류 배율</th><th>창별 알림 단위(60단위씩)</th><th>한도 95·99%</th><th>전류 수준 최대 비(기준 범위)</th><th>창별 권장 조치 · 변경 기록 없음</th></tr></thead><tbody>${
      rows.map(r => `<tr${r.recalibration_review ? ' class="highlight"' : ''}><td>${esc(r.split)}</td><td>×${fmt.num(r.gain, 2)}</td><td>${esc(r.alerted_by_window)}</td><td>${fmt.int(r.limit95)} · ${fmt.int(r.limit99)}</td><td>${fmt.num(r.max_current_ratio, 2)} (${fmt.num(r.band_low, 2)}~${fmt.num(r.band_high, 2)})</td><td>${esc(r.recommended_actions_no_change || '산출물 재생성 필요')}</td></tr>`).join('')
    }</tbody></table>`;
  }
  function renderEffect(rows) {
    const el = $('effect');
    if (!rows.length) { el.innerHTML = '<div class="empty">기대효과표(outputs/expected_effect_v2.csv)가 없습니다.</div>'; return; }
    const shown = rows.filter(r => r.case === '중간');
    el.innerHTML = `<table><thead><tr><th>알림 수(B, α 1%, v2 프로토타입 규칙)</th><th>운영 방식</th><th>교대 8시간 알림 1·2단계</th><th>교대당 점검 시간</th><th>연간 줄이는 가동 중단</th><th>손익분기 배수</th></tr></thead><tbody>${
      shown.map(r => `<tr><td>${esc(r.alert_scenario)}</td><td>${esc(r.policy)}</td><td>${fmt.num(r.level1_per_8h, 0)} · ${r.level2_per_8h == null ? '—' : fmt.num(r.level2_per_8h, 1)}건</td><td>${fmt.num(r.inspection_hours_per_shift, 1)}시간${Number(r.shift_share) > 1 ? ' (교대 초과)' : ''}</td><td>${fmt.num(r.downtime_hours_avoided_per_year, 1)}시간/년</td><td>${Number.isFinite(Number(r.breakeven_loss_ratio)) ? '×' + fmt.num(r.breakeven_loss_ratio, 1) : '—'}</td></tr>`).join('')
    }</tbody></table>`;
  }
  function renderRobustness(rows) {
    const el = $('robustness');
    if (!rows.length) { el.innerHTML = '<div class="empty">강건성 표(outputs/robustness_v2.csv)가 없습니다.</div>'; return; }
    const variants = ['raw', 'matched', 'coarse'];
    el.innerHTML = `<table><thead><tr><th>정상 기준</th><th>α</th><th>모델</th>${variants.map(v => `<th>${v} · 정상 알림 / 미탐 행 / F1</th>`).join('')}</tr></thead><tbody>${
      ['A', 'B'].flatMap(split => [0.01, 0.03, 0.05].flatMap(alpha => ['v1', 'v2'].map(version => {
        const cells = variants.map(v => { const r = rows.find(x => x.split_id === split && Number(x.alpha) === alpha && x.version === version && x.input_variant === v); return r ? `${fmt.int(r.normal_notified_segments)}/${fmt.int(r.normal_segments)} · ${fmt.int(r.fn)} · ${fmt.num(r.f1_all_rows, 4)}` : '—'; });
        return `<tr${version === 'v2' ? ' class="highlight"' : ''}><td>${split}</td><td>${fmt.pct(alpha, 0)}</td><td>${version}</td>${cells.map(c => `<td>${c}</td>`).join('')}</tr>`;
      }))).join('')
    }</tbody></table>`;
  }
  function renderExternal(o) {
    const rows = (o.external || []).filter(r => r.model === 'normal_signature');
    if (!rows.length) { $('external-table').innerHTML = '<div class="empty">외부 검증 결과(analysis/press_external/metrics.csv)가 없습니다.</div>'; return; }
    const mode = m => m === 'local_normal_reference' ? '해당 환경 정상 기준' : '다른 환경 기준(환경 이동)';
    $('external-table').innerHTML = `<table><thead><tr><th>정상 기준</th><th>냉각 조건</th><th>F1</th><th>정상 오경보</th><th>누설 재현율</th><th>AUROC</th></tr></thead><tbody>${
      rows.map(r => `<tr><td>${mode(r.mode)}</td><td>${r.cooler}</td><td>${fmt.num(r.f1, 4)}</td><td>${fmt.int(r.fp)} / ${fmt.int(Number(r.fp) + Number(r.tn))} (${fmt.pct(r.normal_alarm_rate, 1)})</td><td>${fmt.pct(r.recall, 1)}</td><td>${fmt.num(r.auroc, 3)}</td></tr>`).join('')
    }</tbody></table>`;
  }

  // ---------- 시작 ----------
  // 주소로 초기 선택을 줄 수 있다(예: /?split=B&alpha=0.01&incident=4&case=12&tab=evidence). 화면 캡처·공유용.
  function applyQuery() {
    let q = null;
    try { q = new URLSearchParams((window.location && window.location.search) || ''); } catch (e) { return; }
    [['split', 'split'], ['alpha', 'alpha'], ['dataset', 'dataset'], ['prior', 'prior']].forEach(([key, id]) => {
      const v = q.get(key); if (v != null && [...$(id).options || []].some(o => o.value === v)) $(id).value = v;
    });
    const inc = q.get('incident'); if (inc != null && /^\d+$/.test(inc)) state.initialIncident = Number(inc);
    const kase = q.get('case'); if (kase != null && /^\d+$/.test(kase)) state.initialCase = Number(kase);   // 사건 안 몇 번째 기록(1부터)
    const tab = q.get('tab');
    if (tab) document.querySelectorAll('.tab').forEach(t => { if (t.dataset.tab === tab) t.click(); });
  }
  async function start() {
    applyQuery();
    try {
      state.overview = await api('/api/overview');
      renderEvidence(state.overview);
      renderExternal(state.overview);
    } catch (err) {
      $('audit-list').innerHTML = `<div class="empty">개요를 불러오지 못했습니다: ${esc(err.message)}</div>`;
    }
    await analyze();
  }
  let resizeTimer = null;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (state.selectedCase != null) redrawCursor(); }, 150); });
  start();
})();
