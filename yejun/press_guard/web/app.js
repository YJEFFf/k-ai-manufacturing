// Press Guard v2 웹 콘솔 — serve.py의 /api/overview, /api/analyze에 연결한다.
// 로컬 기록 재생·CSV 분석·모의 운용용이다. 설비 제어 명령을 보내지 않으며 고장 원인·잔여수명을 추정하지 않는다.
// 이상 확률은 경보와 별도인 보정 층의 값이며 사전 비율 π 가정에 조건부다.
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const SERIES = [
    { key: 'g_dynamics', name: '전류 예측 오차', color: '#6d55c9', dash: '' },
    { key: 'g_waveform', name: '전류 파형', color: '#178cc2', dash: '5 3' },
    { key: 'g_magnitude', name: '센서 크기', color: '#b07510', dash: '1.5 2.5' },
  ];
  const REASON_LABEL = { dynamics: '전류 예측 오차', waveform: '전류 파형', magnitude: '센서 크기' };
  const ALARM = '#b3412e';
  const state = { overview: null, result: null, selected: null, filter: 'all', levelFilter: 'all', sort: 'priority', upload: null, replay: null, cursor: null, busy: false, sim: null };
  const LEVEL = { 1: '주의', 2: '점검 요청' };
  // 점검 결과는 이 브라우저에만 저장한다(저장이 막혀 있어도 화면은 동작한다).
  const store = {
    get(k) { try { const v = window.localStorage && window.localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch (e) { return null; } },
    set(k, v) { try { if (window.localStorage) window.localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } },
  };
  const outcomeKey = c => `pg-outcome:${state.result.split}:${state.result.alpha}:${state.result.dataset}:${c.record_id}:${c.first_timestamp}`;
  const outcomeOf = c => (state.result && store.get(outcomeKey(c))) || { confirmed_at: '', owner: '', outcome: '', measure: '', status: '열림' };
  // 모의 운용 중에는 커서까지 들어온 행만 보인다.
  const simVisible = c => !state.sim || c.first_row <= state.sim.row;
  const levelNow = c => (state.sim && Number(c.level) === 2 && !(c.escalation_row <= state.sim.row)) ? 1 : Number(c.level);
  const SENSOR_LABEL = { AI0_Vibration: '진동', AI1_Vibration: '진동', AI2_Current: '전류' };
  // 크기 성분은 최대 편차가 난 센서까지 붙여 보인다(진동·전류).
  const reasonLabel = (e, c) => {
    if (e !== 'magnitude' || !c || !c.magnitude_sensors) return REASON_LABEL[e] || e;
    const kinds = [...new Set(String(c.magnitude_sensors).split('+').filter(Boolean).map(s => SENSOR_LABEL[s] || s))];
    return `${REASON_LABEL.magnitude}(${kinds.join('·')})`;
  };

  const fmt = {
    int: v => (v == null || Number.isNaN(v)) ? '—' : Number(v).toLocaleString('ko-KR'),
    num: (v, d = 2) => (v == null || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(d),
    pct: (v, d = 1) => (v == null || Number.isNaN(Number(v))) ? '—' : (100 * v).toFixed(d) + '%',
    time: s => { const m = /(\d{2}:\d{2}:\d{2}(?:\.\d+)?)/.exec(String(s || '')); return m ? m[1].slice(0, 12) : String(s || '—'); },
  };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const numberOrNaN = v => v == null || v === '' ? NaN : Number(v);
  const setMessage = (text, error = false) => { const m = $('message'); m.textContent = text; m.classList.toggle('error', !!error); };

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
      setMessage(`${src} · ${fmt.int(result.stats.rows)}행 · 정상 기준 ${result.split} (보정 구간 ${result.calibration_segments}개) · α ${fmt.pct(result.alpha, 0)} · 이상 확률 π ${fmt.pct(result.prior, 1)}${result.probability_available ? '' : '(보정기 없음)'} · 처리 ${fmt.num(result.stats.elapsed_s, 2)}초`);
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
  function renderResult() {
    const r = state.result;
    const s = r.stats;
    renderLevelKpis();
    $('k-alarm').textContent = fmt.int(s.alarm_rows);
    $('k-coverage').textContent = s.rows ? fmt.pct(s.scored / s.rows, 1) : '—';
    $('k-quality').textContent = s.invalid ? `수집 오류 ${fmt.int(s.invalid)}행은 판정 보류` : '수집 오류 행 없음';
    $('k-segment').textContent = fmt.int(s.segments);
    $('k-rows').textContent = `${fmt.int(s.rows)}행 · 0.1초 간격 관측`;
    renderQueue();
    const first = filteredCases()[0];
    if (first) selectCase(first.record_id); else renderDetail(null);
  }

  function renderLevelKpis() {
    const cases = (state.result ? state.result.cases : []).filter(simVisible);
    const l2 = cases.filter(c => levelNow(c) === 2).length;
    $('k-case').textContent = fmt.int(l2);
    $('k-level1').textContent = fmt.int(cases.length - l2);
    $('k-case-sub').textContent = cases.length ? `전체 ${fmt.int(cases.length)}건 중 · 건 안에서 경보 2행 이상 · 현장 점검` : '경보가 발생한 구간이 없습니다';
  }

  function filteredCases() {
    const cases = (state.result ? state.result.cases : []).filter(simVisible);
    let list = state.filter === 'all' ? cases : cases.filter(c => String(c.evidence).split('+').includes(state.filter));
    if (state.levelFilter !== 'all') list = list.filter(c => levelNow(c) === Number(state.levelFilter));
    // 우선순위는 이상 라벨 없이 정한 정렬 키(단계 → 근거 성분 수 → 경보 행 비율 → 최대 점수). 시간순은 첫 경보 행 순서.
    return [...list].sort((a, b) => state.sort === 'priority' ? (a.priority_rank - b.priority_rank) : (a.first_row - b.first_row));
  }

  function renderQueue() {
    const list = filteredCases();
    $('queue-count').textContent = fmt.int(list.length);
    const queue = $('queue');
    if (!list.length) {
      queue.innerHTML = `<div class="empty">${state.result && state.result.cases.length ? '선택한 근거로 경보한 구간이 없습니다.' : '경보가 발생한 기록 구간이 없습니다.'}</div>`;
      return;
    }
    queue.innerHTML = list.map(c => {
      const chips = String(c.evidence).split('+').filter(Boolean).map(e => `<span class="chip ${esc(e)}">${esc(reasonLabel(e, c))}</span>`).join('');
      const ref = c.reference_label == null ? '' : (Number(c.reference_label) === 1 ? ' · 참조 라벨: 이상' : ' · 참조 라벨: 정상');
      const lv = levelNow(c), o = outcomeOf(c);
      const done = o.outcome ? ` · <span class="done">${esc(o.outcome)}</span>` : '';
      const prob = Number.isFinite(numberOrNaN(c.max_probability)) ? ` · 이상 확률 ${fmt.pct(c.max_probability, 1)}` : '';
      return `<button type="button" class="queue-item${c.record_id === state.selected ? ' selected' : ''}" data-record="${c.record_id}">
        <div class="queue-top"><span class="queue-id"><em class="badge l${lv}">${LEVEL[lv]}</em> 우선 ${fmt.int(c.priority_rank)} · 구간 ${fmt.int(c.record_id)}</span><span class="queue-time">${esc(fmt.time(c.first_timestamp))}</span></div>
        <div class="chips">${chips}</div>
        <div class="queue-action">첫 경보 ${fmt.num(c.detection_delay_s, 1)}초 · 경보 ${fmt.int(c.alarm_rows)}/${fmt.int(c.observed_rows)}행${prob}${ref}${done}</div>
      </button>`;
    }).join('');
    queue.querySelectorAll('.queue-item').forEach(el => el.addEventListener('click', () => selectCase(Number(el.dataset.record))));
  }
  $('sort').addEventListener('change', () => { state.sort = $('sort').value; renderQueue(); });
  $('level-filter').addEventListener('change', () => { state.levelFilter = $('level-filter').value; renderQueue(); const first = filteredCases()[0]; if (!first) renderDetail(null); else if (!filteredCases().some(c => c.record_id === state.selected)) selectCase(first.record_id); });
  $('filter').addEventListener('change', () => { state.filter = $('filter').value; renderQueue(); const first = filteredCases()[0]; if (!first) renderDetail(null); else if (!filteredCases().some(c => c.record_id === state.selected)) selectCase(first.record_id); });

  function selectCase(recordId) {
    state.selected = recordId;
    stopReplay();
    document.querySelectorAll('.queue-item').forEach(el => el.classList.toggle('selected', Number(el.dataset.record) === recordId));
    const item = document.querySelector(`.queue-item[data-record="${recordId}"]`);
    if (item && item.scrollIntoView) item.scrollIntoView({ block: 'nearest' });
    renderDetail(state.result.cases.find(c => c.record_id === recordId) || null);
  }

  function recordRows(recordId) { return state.result.points.filter(p => p.record_id === recordId); }

  function renderDetail(c) {
    const summary = $('detail-summary');
    if (!c) {
      state.selected = null; stopReplay(); hideTooltip();
      $('scrubber').disabled = true; $('replay').disabled = true;
      $('detail-title').textContent = state.result ? '경보 구간이 없습니다' : '점검 구간을 선택하세요';
      $('reference').textContent = '';
      summary.innerHTML = '경보가 발생한 시점과 관측 근거를 함께 확인합니다.';
      $('current-chart').innerHTML = ''; $('score-chart').innerHTML = '';
      $('action').textContent = '—'; $('position').textContent = '—';
      $('checklist').textContent = '관측 이상에 대한 확인 순서입니다. 고장 원인 확정이나 자동 정지 명령이 아닙니다.';
      $('quality-action').textContent = '—'; $('suspect').textContent = '—'; $('outcome').hidden = true;
      $('scrubber').max = 1; $('scrubber').value = 1;
      return;
    }
    const rows = recordRows(c.record_id);
    $('scrubber').disabled = false; $('replay').disabled = false;
    $('detail-title').textContent = `구간 ${fmt.int(c.record_id)} · ${fmt.int(rows.length)}관측`;
    $('reference').textContent = c.reference_label == null ? '참조 라벨 없음' : (Number(c.reference_label) === 1 ? '참조 라벨: 이상 기록' : '참조 라벨: 정상 기록');
    const reasons = String(c.evidence).split('+').filter(Boolean).map(e => reasonLabel(e, c)).join(' + ');
    const thr = state.result.threshold;
    // α 1%에서는 모든 경보의 p값이 보정으로 낼 수 있는 최솟값 하나라 건 사이 순위 정보가 없다. 문턱 대비 최대 점수를 먼저 보인다.
    const lv = levelNow(c);
    const esc2 = Number(c.level) === 2 && Number.isFinite(numberOrNaN(c.escalation_after_first_s)) ? ` · 첫 경보 ${fmt.num(c.escalation_after_first_s, 1)}초 뒤 격상` : '';
    summary.innerHTML = [
      ['단계', `${LEVEL[lv]}${lv === 2 ? esc2 : ' · 화면 확인·기록'}`],
      ['첫 경보', `${fmt.num(c.detection_delay_s, 1)}초 (${fmt.int(c.first_alarm_position + 1)}번째 관측)`],
      ['경보 관측', `${fmt.int(c.alarm_rows)} / ${fmt.int(c.observed_rows)}행`],
      ['문턱 대비 최대 점수', Number.isFinite(thr) && thr > 0 ? `${fmt.num(c.peak_score, 2)} / ${fmt.num(thr, 2)} (×${fmt.num(c.peak_score / thr, 1)})` : fmt.num(c.peak_score, 2)],
      ['최소 p값', `${fmt.num(c.min_p, 4)} (가능한 최솟값 ${fmt.num(state.result.min_p_attainable, 4)})`],
      ['근거', reasons || '—'],
      ['이상 확률', Number.isFinite(numberOrNaN(c.max_probability)) ? `${fmt.pct(c.max_probability, 1)} (π ${fmt.pct(state.result.prior, 1)} 가정 · 우도비 ${fmt.num(c.max_likelihood_ratio, 1)})` : '보정기 없음'],
    ].map(([k, v]) => `<div><span>${k}</span><b>${esc(v)}</b></div>`).join('');
    $('action').textContent = c.action || '—';
    const rule = ((state.overview && state.overview.decision_table) || []).find(r => r.action === c.action);
    $('checklist').textContent = rule ? `점검 항목(가설): ${rule.checklist} · 고장 모드 후보 ${rule.failure_modes}` : '관측 이상에 대한 확인 순서입니다. 고장 원인 확정이나 자동 정지 명령이 아닙니다.';
    $('quality-action').textContent = c.quality_action || '—';
    $('suspect').textContent = Number(c.suspect_open) === 1
      ? `의심 생산 시간창: ${c.suspect_from ? fmt.time(c.suspect_from) : '자료 처음'} ~ ${c.suspect_to ? fmt.time(c.suspect_to) : '진행 중'} (열림 · 다음 정상 기록을 확인할 때까지)`
      : `의심 생산 시간창: ${fmt.time(c.suspect_from)} ~ ${fmt.time(c.suspect_to)} (${fmt.num(c.suspect_seconds, 1)}초 · 분당 20~60행정이면 ${fmt.num(c.suspect_seconds / 3, 0)}~${fmt.num(c.suspect_seconds, 0)}개, 가정)`;
    fillOutcome(c);
    $('scrubber').max = rows.length; $('scrubber').value = rows.length;
    state.cursor = null;
    drawCharts(rows, rows.length);
  }

  function drawCharts(rows, upto) {
    const shown = rows.slice(0, upto);
    $('position').textContent = `${fmt.int(upto)} / ${fmt.int(rows.length)} 관측`;
    lineChart($('current-chart'), shown, [{ key: 'AI2_Current', name: '전류', color: '#176d55', dash: '' }], { alarms: true, unit: '' , domainRows: rows });
    lineChart($('score-chart'), shown, SERIES, { threshold: state.result.threshold, domainRows: rows, unit: '' });
  }

  // 단일 SVG 선 그래프: 격자·축 라벨·경보 점·문턱선·호버 툴팁. 라이브러리 없음.
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
    if (opts.alarms) {
      rows.forEach((r, i) => { if (Number(r.alarm) === 1 && Number.isFinite(numberOrNaN(r[series[0].key]))) svg += `<circle cx="${x(i)}" cy="${y(Number(r[series[0].key]))}" r="4" fill="${ALARM}" stroke="#fff" stroke-width="2"/>`; });
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
    if (!state.result || state.selected == null) return;
    const rows = recordRows(state.selected);
    drawCharts(rows, Number($('scrubber').value) || rows.length);
  }

  let tip = null;
  function tooltip() { if (!tip) { tip = document.createElement('div'); tip.className = 'tooltip'; tip.hidden = true; document.body.appendChild(tip); } return tip; }
  function showTooltip(row, i, ev) {
    const t = tooltip();
    const lines = [`<b>${fmt.num(i * 0.1, 1)}초 · ${esc(fmt.time(row.timestamp))}</b>`,
      `전류 ${fmt.num(row.AI2_Current, 2)} · 진동 ${fmt.num(row.AI0_Vibration, 3)} / ${fmt.num(row.AI1_Vibration, 3)}`,
      ...SERIES.map(s => `<i style="background:${s.color}"></i>${s.name} ${fmt.num(row[s.key], 2)}`),
      row.status !== 'ok' ? '<span class="warn">수집 오류 · 판정 보류</span>' :
        (Number(row.alarm) === 1 ? `<span class="warn">경보 · p=${fmt.num(row.p_value, 4)} · ${String(row.reason).split('+').map(e => REASON_LABEL[e] || e).join('+')}</span>` : `p=${fmt.num(row.p_value, 4)} · 정상 범위`)];
    t.innerHTML = lines.join('<br>');
    t.hidden = false;
    positionTooltip(ev);
  }
  function positionTooltip(ev) { const t = tooltip(); const x = Math.min(ev.clientX + 14, window.innerWidth - t.offsetWidth - 8); t.style.left = `${x}px`; t.style.top = `${ev.clientY + 14}px`; }
  function hideTooltip() { if (tip) tip.hidden = true; }

  // ---------- 재생 ----------
  $('scrubber').addEventListener('input', () => { if (state.selected == null) return; state.cursor = null; drawCharts(recordRows(state.selected), Number($('scrubber').value)); });
  function stopReplay() { if (state.replay) { clearInterval(state.replay); state.replay = null; $('replay').textContent = '▷ 선택 구간 재생'; } }
  $('replay').addEventListener('click', () => {
    if (state.selected == null) return;
    if (state.replay) { stopReplay(); return; }
    const rows = recordRows(state.selected);
    let i = 0;
    $('replay').textContent = '■ 재생 중지';
    state.replay = setInterval(() => {
      i += 1; $('scrubber').value = i; state.cursor = null; drawCharts(rows, i);
      if (i >= rows.length) stopReplay();
    }, 100);
  });

  // ---------- 점검 결과 기록 ----------
  function fillOutcome(c) {
    const o = outcomeOf(c);
    $('outcome').hidden = false;
    $('o-owner').value = o.owner || ''; $('o-outcome').value = o.outcome || ''; $('o-measure').value = o.measure || '';
    $('outcome-state').textContent = o.confirmed_at ? `${o.status} · ${fmt.time(o.confirmed_at)} 기록` : '열림 · 미확인';
  }
  $('outcome').addEventListener('submit', ev => {
    ev.preventDefault();
    const c = state.result && state.result.cases.find(x => x.record_id === state.selected);
    if (!c) return;
    const outcome = $('o-outcome').value;
    const record = { confirmed_at: new Date().toISOString(), owner: $('o-owner').value.trim(), outcome, measure: $('o-measure').value.trim(),
      status: (outcome === '정상 확인' || outcome === '이상 확인') ? '닫힘' : '열림' };
    const saved = store.set(outcomeKey(c), record);
    fillOutcome(c); renderQueue();
    setMessage(saved ? `구간 ${c.record_id} 점검 결과를 기록했습니다(${record.status}).` : '이 브라우저에서는 결과를 저장할 수 없습니다. CSV로 내보내 따로 보관하세요.', !saved);
  });

  // ---------- 모의 운용: 분석한 기록을 10배속(초당 100행)으로 흘려 알림이 쌓이는 순서를 본다 ----------
  // 알림 시점·단계는 서버의 StreamDetector(인과 순차 추론) 결과이며 simulate.py와 같다. 화면은 커서까지 들어온 건만 보인다.
  function stopSim(render = true) {
    if (!state.sim) return;
    clearInterval(state.sim.timer); state.sim = null;
    $('sim-bar').hidden = true; $('simulate').textContent = '▶ 모의 운용';
    if (render && state.result) { renderLevelKpis(); renderQueue(); }
  }
  function startSim() {
    if (!state.result || state.busy) return;
    if (state.sim) { stopSim(); return; }
    const points = state.result.points, rowsPerTick = 10;
    const events = [];
    state.result.cases.forEach(c => { events.push({ row: c.first_row, text: `주의 · 구간 ${c.record_id}` }); if (Number(c.level) === 2 && c.escalation_row != null) events.push({ row: c.escalation_row, text: `점검 요청 · 구간 ${c.record_id}` }); });
    events.sort((a, b) => a.row - b.row);
    state.sim = { row: -1, next: 0, timer: null };
    $('sim-bar').hidden = false; $('simulate').textContent = '■ 모의 중지';
    state.sim.timer = setInterval(() => {
      const sim = state.sim; if (!sim) return;
      sim.row = Math.min(points.length - 1, sim.row + rowsPerTick);
      $('sim-clock').textContent = `${fmt.time(points[sim.row].timestamp)} · ${fmt.int(sim.row + 1)} / ${fmt.int(points.length)}행`;
      let changed = false;
      while (sim.next < events.length && events[sim.next].row <= sim.row) { $('sim-last').textContent = `최근 알림: ${events[sim.next].text}`; sim.next += 1; changed = true; }
      if (changed) { renderLevelKpis(); renderQueue(); }
      if (sim.row >= points.length - 1) { $('sim-last').textContent += ' · 끝'; clearInterval(sim.timer); setTimeout(() => stopSim(), 1500); }
    }, 100);
    renderLevelKpis(); renderQueue();
  }
  $('simulate').addEventListener('click', startSim);
  $('sim-stop').addEventListener('click', () => stopSim());

  // ---------- 내보내기 ----------
  $('export').addEventListener('click', () => {
    const list = filteredCases();
    if (!list.length) { setMessage('내보낼 점검 구간이 없습니다.', true); return; }
    const cols = ['priority_rank', 'level', 'level_name', 'record_id', 'first_timestamp', 'first_alarm_position', 'detection_delay_s', 'escalation_delay_s', 'alarm_rows', 'observed_rows', 'alarm_share', 'peak_score', 'min_p', 'evidence', 'magnitude_sensors', 'action', 'suspect_from', 'suspect_to', 'suspect_seconds', 'suspect_open', 'quality_action', 'max_probability', 'alert_units', 'beyond_calibration_length', 'reference_label'];
    const outcomeCols = (state.overview && state.overview.outcome_columns) || ['confirmed_at', 'owner', 'outcome', 'measure', 'status'];
    const cell = v => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const csv = [cols.concat(outcomeCols, ['probability_prior']).join(','), ...list.map(c => { const o = outcomeOf(c); return cols.map(k => cell(c[k])).concat(outcomeCols.map(k => cell(o[k])), [cell(state.result.prior)]).join(','); })].join('\n');
    const url = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a'); a.href = url; a.download = `press_guard_cases_${state.result.split}_a${Math.round(state.result.alpha * 100)}.csv`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  // ---------- 성능 검증 탭 ----------
  function renderEvidence(o) {
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
    const order = ['A', 'B'];
    $('comparison').innerHTML = `<table><thead><tr><th>정상 기준</th><th>모델</th><th>행 단위 F1</th><th>미탐 행</th><th>오경보 행</th><th>정상 알림 구간</th><th>이상 알림 구간</th><th>최대 첫 경보 지연</th></tr></thead><tbody>${
      order.flatMap(split => ['baseline_v1', 'guard_v2'].map(model => rows.find(r => r.split === split && r.model === model)).filter(Boolean).map(r =>
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
    if (!rows.length) { el.innerHTML = '<div class="empty">조건표(outputs/error_conditions_v2.csv)가 없습니다. analyze.py를 실행하세요.</div>'; return; }
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
    if (!rows.length) { el.innerHTML = '<div class="empty">업무량 표(outputs/workload_v2.csv)가 없습니다. analyze.py를 실행하세요.</div>'; return; }
    el.innerHTML = `<table><thead><tr><th>정상 기준</th><th>α</th><th>경과 1시간당 구간</th><th>명목 비율</th><th>교대 8시간 · 명목</th><th>관측 알림 / 구간</th><th>교대 8시간 · 관측</th><th>교대 8시간 · 관측 95% 상한</th></tr></thead><tbody>${
      rows.map(r => `<tr><td>${esc(r.split_id)}</td><td>${fmt.pct(r.alpha, 0)}</td><td>${fmt.int(Math.round(r.units_per_elapsed_hour))}</td><td>${fmt.pct(r.alpha_grid_rate, 2)}</td><td>${fmt.num(r.nominal_alerts_per_8h_elapsed, 0)}건</td><td>${fmt.int(r.first_alert_segments)} / ${fmt.int(r.normal_segments)}</td><td>${fmt.num(r.observed_alerts_per_8h_elapsed, 0)}건</td><td>${fmt.num(r.upper95_alerts_per_8h_elapsed, 0)}건</td></tr>`).join('')
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
    if (!rows.length) { el.innerHTML = '<div class="empty">단계별 표(outputs/alert_levels_v2.csv)가 없습니다. analyze.py를 실행하세요.</div>'; return; }
    const shown = rows.filter(r => Number(r.alpha) === 0.01);
    el.innerHTML = `<table><thead><tr><th>모델 · 정상 평가 구간</th><th>단계</th><th>정상 알림 / 구간</th><th>교대 8시간 · 관측</th><th>95% 상한</th><th>이상 21구간 탐지</th><th>지연 중앙·최대</th></tr></thead><tbody>${
      shown.map(r => `<tr${Number(r.level) === 2 ? ' class="highlight"' : ''}><td>${esc(r.model)} · ${esc(r.normal_window)}${r.same_calibration_as ? ` <small>(= ${esc(r.same_calibration_as)})</small>` : ''}</td><td>${LEVEL[r.level]}</td><td>${fmt.int(r.normal_alerted_segments)} / ${fmt.int(r.normal_segments)}</td><td>${fmt.num(r.alerts_per_8h_elapsed, 0)}건</td><td>${fmt.num(r.upper95_alerts_per_8h_elapsed, 0)}건</td><td>${fmt.int(r.abnormal_detected_segments)} / ${fmt.int(r.abnormal_segments)}</td><td>${fmt.num(r.delay_median_s, 1)} · ${fmt.num(r.delay_max_s, 1)}초</td></tr>`).join('')
    }</tbody></table>`;
  }

  function renderQualityRules(o) {
    const el = $('quality-rules');
    const qa = o.quality_actions || {};
    const fa = (o.quality_windows || []).filter(r => r.split === 'B');
    el.innerHTML = `<table><thead><tr><th>단계</th><th>품질 조치(가설)</th></tr></thead><tbody>${
      Object.keys(qa).map(k => `<tr><td>${LEVEL[k] || k}</td><td>${esc(qa[k])}</td></tr>`).join('')
    }</tbody></table>${fa.length ? `<p class="fine">예: 대회 B 정상 평가 구간의 1단계 오경보 ${fa.length}건의 의심 시간창은 ${fa.map(r => `${fmt.num(r.suspect_seconds, 1)}초`).join('·')}이며, 분당 20~60행정이면 건당 ${fmt.num(Math.min(...fa.map(r => r.pieces_spm20)), 1)}~${fmt.num(Math.max(...fa.map(r => r.pieces_spm60)), 1)}개입니다(가정). 확인 순서는 대기열 순서를 따릅니다.</p>` : ''}`;
  }

  function renderProbability(o) {
    const el = $('probability');
    const ev = (o.probability || []).filter(r => r.cv === '21fold' && r.unit === 'rows');
    const lf = (o.label_free || []).filter(r => r.far_basis === 'nominal' || r.far_basis === 'calibrated95');
    if (!ev.length) { el.innerHTML = '<div class="empty">확률 평가표(outputs/probability_eval_v2.csv)가 없습니다.</div>'; return; }
    const name = { calibrated_isotonic: '라벨 보정 확률(교차 적합·LR 상한 121)', isotonic_uncapped: '상한 없는 등방 회귀(비교용)', platt_logistic: 'Platt(비교용)', naive_1_minus_p: '1−p (확률 아님, 비교용)', prevalence_only: '유병률만' };
    const t1 = `<table><thead><tr><th>정상 기준</th><th>방법</th><th>Brier</th><th>log-loss</th><th>ECE</th></tr></thead><tbody>${
      ev.map(r => `<tr${r.method === 'calibrated_isotonic' ? ' class="highlight"' : ''}><td>${esc(r.split)}</td><td>${name[r.method] || esc(r.method)}</td><td>${fmt.num(r.brier, 4)}</td><td>${fmt.num(r.log_loss, 4)}</td><td>${fmt.num(r.ece, 4)}</td></tr>`).join('')
    }</tbody></table>`;
    const pick = lf.filter(r => r.split === 'A' && (r.tpr_basis === 'E1 cur_noise 0.1' || r.tpr_basis === '대회 21/21 95% 하한'));
    const t2 = pick.length ? `<table><thead><tr><th>오경보율 기준</th><th>탐지율 기준</th><th>우도비</th><th>π 0.01%</th><th>π 0.1%</th><th>π 1%</th></tr></thead><tbody>${
      [...new Set(pick.map(r => `${r.far_basis}|${r.tpr_basis}`))].map(key => {
        const [fb, tb] = key.split('|'); const g = pick.filter(r => r.far_basis === fb && r.tpr_basis === tb);
        const at = pi => { const r = g.find(x => Math.abs(Number(x.prior) - pi) < 1e-12); return r ? fmt.pct(r.p_anomaly_given_alert, 1) : '—'; };
        return `<tr><td>${fb === 'nominal' ? '명목 1/121' : '보정 조건부 95%'} (${fmt.pct(g[0].far, 2)})</td><td>${esc(tb)} (${fmt.pct(g[0].tpr, 1)})</td><td>${fmt.num(g[0].likelihood_ratio, 0)}</td><td>${at(1e-4)}</td><td>${at(1e-3)}</td><td>${at(1e-2)}</td></tr>`;
      }).join('')
    }</tbody></table>` : '';
    el.innerHTML = `<div class="two-tables"><div><b>교차 보정 평가(21겹, 행 단위)</b>${t1}</div><div><b>라벨 없는 환산 · 1단계 알림 한 건의 이상 확률(A, α 1%)</b>${t2}</div></div>`;
  }

  function renderMonitorGain(rows) {
    const el = $('monitor-gain');
    if (!rows.length) { el.innerHTML = '<div class="empty">감시 모의표(outputs/monitor_gain_v2.csv)가 없습니다.</div>'; return; }
    el.innerHTML = `<table><thead><tr><th>정상 기준</th><th>전류 배율</th><th>창별 알림 단위(60단위씩)</th><th>한도 95·99%</th><th>전류 수준 최대 비(기준 범위)</th><th>재보정 검토</th></tr></thead><tbody>${
      rows.map(r => `<tr${r.recalibration_review ? ' class="highlight"' : ''}><td>${esc(r.split)}</td><td>×${fmt.num(r.gain, 2)}</td><td>${esc(r.alerted_by_window)}</td><td>${fmt.int(r.limit95)} · ${fmt.int(r.limit99)}</td><td>${fmt.num(r.max_current_ratio, 2)} (${fmt.num(r.band_low, 2)}~${fmt.num(r.band_high, 2)})</td><td>${r.recalibration_review ? `발동(창 ${fmt.int(r.first_review_window + 1)})` : '—'}</td></tr>`).join('')
    }</tbody></table>`;
  }

  function renderEffect(rows) {
    const el = $('effect');
    if (!rows.length) { el.innerHTML = '<div class="empty">기대효과표(outputs/expected_effect_v2.csv)가 없습니다.</div>'; return; }
    const shown = rows.filter(r => r.case === '중간' || r.alert_scenario === '관측');
    el.innerHTML = `<table><thead><tr><th>알림 수(B, α 1%)</th><th>운영 방식</th><th>가정</th><th>교대 8시간 알림 1·2단계</th><th>교대당 점검 시간</th><th>연간 줄이는 가동 중단</th><th>손익분기 배수</th></tr></thead><tbody>${
      shown.map(r => `<tr${r.policy === '2단계만 출동' ? ' class="highlight"' : ''}><td>${esc(r.alert_scenario)}</td><td>${esc(r.policy)}</td><td>${esc(r.case)}</td><td>${fmt.num(r.level1_per_8h, 0)} · ${r.level2_per_8h == null ? '—' : fmt.num(r.level2_per_8h, 0)}건</td><td>${fmt.num(r.inspection_hours_per_shift, 1)}시간${Number(r.shift_share) > 1 ? ' (교대 초과)' : ''}</td><td>${fmt.num(r.downtime_hours_avoided_per_year, 1)}시간/년</td><td>${Number.isFinite(Number(r.breakeven_loss_ratio)) ? '×' + fmt.num(r.breakeven_loss_ratio, 1) : '—'}</td></tr>`).join('')
    }</tbody></table>`;
  }

  function renderRobustness(rows) {
    const el = $('robustness');
    if (!rows.length) { el.innerHTML = '<div class="empty">강건성 표(outputs/robustness_v2.csv)가 없습니다. analyze.py를 실행하세요.</div>'; return; }
    const variants = ['raw', 'matched', 'coarse'];
    const alphas = [0.01, 0.03, 0.05];
    el.innerHTML = `<table><thead><tr><th>정상 기준</th><th>α</th><th>모델</th>${variants.map(v => `<th>${v} · 정상 알림 / 미탐 행 / F1</th>`).join('')}</tr></thead><tbody>${
      ['A', 'B'].flatMap(split => alphas.flatMap(alpha => ['v1', 'v2'].map(version => {
        const cells = variants.map(v => { const r = rows.find(x => x.split_id === split && Number(x.alpha) === alpha && x.version === version && x.input_variant === v); return r ? `${fmt.int(r.normal_notified_segments)}/${fmt.int(r.normal_segments)} · ${fmt.int(r.fn)} · ${fmt.num(r.f1_all_rows, 4)}` : '—'; });
        return `<tr${version === 'v2' ? ' class="highlight"' : ''}><td>${split}</td><td>${fmt.pct(alpha, 0)}</td><td>${version}</td>${cells.map(c => `<td>${c}</td>`).join('')}</tr>`;
      }))).join('')
    }</tbody></table>`;
  }

  // ---------- 외부 데이터 탭 ----------
  function renderExternal(o) {
    const rows = o.external.filter(r => r.model === 'normal_signature');
    if (!rows.length) { $('external-table').innerHTML = '<div class="empty">외부 검증 결과(analysis/press_external/metrics.csv)가 없습니다.</div>'; return; }
    const mode = m => m === 'local_normal_reference' ? '해당 환경 정상 기준' : '다른 환경 기준(환경 이동)';
    $('external-table').innerHTML = `<table><thead><tr><th>정상 기준</th><th>냉각 조건</th><th>F1</th><th>정상 오경보</th><th>누설 재현율</th><th>AUROC</th></tr></thead><tbody>${
      rows.map(r => `<tr><td>${mode(r.mode)}</td><td>${r.cooler}</td><td>${fmt.num(r.f1, 4)}</td><td>${fmt.int(r.fp)} / ${fmt.int(Number(r.fp) + Number(r.tn))} (${fmt.pct(r.normal_alarm_rate, 1)})</td><td>${fmt.pct(r.recall, 1)}</td><td>${fmt.num(r.auroc, 3)}</td></tr>`).join('')
    }</tbody></table>`;
  }

  // ---------- 시작 ----------
  // 주소로 초기 선택을 줄 수 있다(예: /?split=B&alpha=0.01&tab=evidence). 화면 캡처·공유용.
  function applyQuery() {
    let q = null;
    try { q = new URLSearchParams((window.location && window.location.search) || ''); } catch (e) { return; }
    [['split', 'split'], ['alpha', 'alpha'], ['dataset', 'dataset'], ['prior', 'prior']].forEach(([key, id]) => {
      const v = q.get(key); if (v != null && [...$(id).options || []].some(o => o.value === v)) $(id).value = v;
    });
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
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (state.selected != null) redrawCursor(); }, 150); });
  start();
})();
