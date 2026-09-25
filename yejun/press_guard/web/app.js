// Press Guard v2 웹 콘솔 — serve.py의 /api/overview, /api/analyze에 연결한다.
// 로컬 기록 재생·CSV 분석용이다. 설비 제어 명령을 보내지 않으며 고장 확률·원인·잔여수명을 추정하지 않는다.
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
  const state = { overview: null, result: null, selected: null, filter: 'all', upload: null, replay: null, cursor: null, busy: false };

  const fmt = {
    int: v => (v == null || Number.isNaN(v)) ? '—' : Number(v).toLocaleString('ko-KR'),
    num: (v, d = 2) => (v == null || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(d),
    pct: (v, d = 1) => (v == null || Number.isNaN(Number(v))) ? '—' : (100 * v).toFixed(d) + '%',
    time: s => { const m = /(\d{2}:\d{2}:\d{2}(?:\.\d+)?)/.exec(String(s || '')); return m ? m[1].slice(0, 12) : String(s || '—'); },
  };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
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
    ['analyze', 'dataset', 'split', 'alpha', 'file'].forEach(id => { $(id).disabled = busy; });
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
    const request = { split: $('split').value, alpha: Number($('alpha').value), dataset };
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
      stopReplay();
      renderResult();
      const src = dataset === 'upload' ? state.upload.name : result.source_name;
      setMessage(`${src} · ${fmt.int(result.stats.rows)}행 · 정상 기준 ${result.split} (보정 구간 ${result.calibration_segments}개) · α ${fmt.pct(result.alpha, 0)} · 처리 ${fmt.num(result.stats.elapsed_s, 2)}초`);
    } catch (err) {
      setMessage(`분석 실패: ${err.message}`, true);
    } finally {
      setBusy(false);
    }
  }
  $('analyze').addEventListener('click', analyze);
  ['dataset', 'split', 'alpha'].forEach(id => $(id).addEventListener('change', analyze));

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
    $('k-case').textContent = fmt.int(r.cases.length);
    $('k-case-sub').textContent = r.cases.length ? `${fmt.int(s.segments)}개 기록 구간 중 · 구간별 첫 경보 한 번만 알림` : '경보가 발생한 구간이 없습니다';
    $('k-alarm').textContent = fmt.int(s.alarm_rows);
    $('k-coverage').textContent = s.rows ? fmt.pct(s.scored / s.rows, 1) : '—';
    $('k-quality').textContent = s.invalid ? `수집 오류 ${fmt.int(s.invalid)}행은 판정 보류` : '수집 오류 행 없음';
    $('k-segment').textContent = fmt.int(s.segments);
    $('k-rows').textContent = `${fmt.int(s.rows)}행 · 0.1초 간격 관측`;
    renderQueue();
    const first = filteredCases()[0];
    if (first) selectCase(first.record_id); else renderDetail(null);
  }

  function filteredCases() {
    const cases = state.result ? state.result.cases : [];
    return state.filter === 'all' ? cases : cases.filter(c => String(c.evidence).split('+').includes(state.filter));
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
      const chips = String(c.evidence).split('+').filter(Boolean).map(e => `<span class="chip ${esc(e)}">${esc(REASON_LABEL[e] || e)}</span>`).join('');
      const ref = c.reference_label == null ? '' : (Number(c.reference_label) === 1 ? ' · 참조 라벨: 이상' : ' · 참조 라벨: 정상');
      return `<button type="button" class="queue-item${c.record_id === state.selected ? ' selected' : ''}" data-record="${c.record_id}">
        <div class="queue-top"><span class="queue-id">구간 ${fmt.int(c.record_id)}</span><span class="queue-time">${esc(fmt.time(c.first_timestamp))}</span></div>
        <div class="chips">${chips}</div>
        <div class="queue-action">첫 경보 ${fmt.num(c.detection_delay_s, 1)}초 · 경보 ${fmt.int(c.alarm_rows)}/${fmt.int(c.observed_rows)}행${ref}</div>
      </button>`;
    }).join('');
    queue.querySelectorAll('.queue-item').forEach(el => el.addEventListener('click', () => selectCase(Number(el.dataset.record))));
  }
  $('filter').addEventListener('change', () => { state.filter = $('filter').value; renderQueue(); const first = filteredCases()[0]; if (first && !filteredCases().some(c => c.record_id === state.selected)) selectCase(first.record_id); });

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
      $('detail-title').textContent = state.result ? '경보 구간이 없습니다' : '점검 구간을 선택하세요';
      $('reference').textContent = '';
      summary.innerHTML = '경보가 발생한 시점과 관측 근거를 함께 확인합니다.';
      $('current-chart').innerHTML = ''; $('score-chart').innerHTML = '';
      $('action').textContent = '—'; $('position').textContent = '—';
      $('scrubber').max = 1; $('scrubber').value = 1;
      return;
    }
    const rows = recordRows(c.record_id);
    $('detail-title').textContent = `구간 ${fmt.int(c.record_id)} · ${fmt.int(rows.length)}관측`;
    $('reference').textContent = c.reference_label == null ? '참조 라벨 없음' : (Number(c.reference_label) === 1 ? '참조 라벨: 이상 기록' : '참조 라벨: 정상 기록');
    const reasons = String(c.evidence).split('+').filter(Boolean).map(e => REASON_LABEL[e] || e).join(' + ');
    summary.innerHTML = [
      ['첫 경보', `${fmt.num(c.detection_delay_s, 1)}초 (${fmt.int(c.first_alarm_position + 1)}번째 관측)`],
      ['경보 관측', `${fmt.int(c.alarm_rows)} / ${fmt.int(c.observed_rows)}행`],
      ['최소 p값', fmt.num(c.min_p, 4)],
      ['최대 점수', fmt.num(c.peak_score, 2)],
      ['근거', reasons || '—'],
    ].map(([k, v]) => `<div><span>${k}</span><b>${esc(v)}</b></div>`).join('');
    $('action').textContent = c.action || '—';
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
    domain.forEach(r => series.forEach(s => { const v = Number(r[s.key]); if (Number.isFinite(v)) vals.push(v); }));
    if (opts.threshold != null && Number.isFinite(opts.threshold)) vals.push(opts.threshold);
    if (!vals.length) { container.innerHTML = '<div class="empty">표시할 값이 없습니다</div>'; return; }
    let lo = Math.min(...vals), hi = Math.max(...vals);
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
      rows.forEach((r, i) => { const v = Number(r[s.key]); if (!Number.isFinite(v)) { pen = false; return; } d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true; });
      svg += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"${s.dash ? ` stroke-dasharray="${s.dash}"` : ''}/>`;
      const last = [...rows].reverse().find(r => Number.isFinite(Number(r[s.key])));
      if (last && series.length > 1) svg += `<text x="${W - m.r}" y="${y(Number(last[s.key])) - 5}" text-anchor="end" style="fill:${s.color}">${esc(s.name)}</text>`;
    });
    if (opts.alarms) {
      rows.forEach((r, i) => { if (Number(r.alarm) === 1 && Number.isFinite(Number(r[series[0].key]))) svg += `<circle cx="${x(i)}" cy="${y(Number(r[series[0].key]))}" r="4" fill="${ALARM}" stroke="#fff" stroke-width="2"/>`; });
    }
    if (state.cursor != null && state.cursor < rows.length) {
      const i = state.cursor;
      svg += `<line x1="${x(i)}" x2="${x(i)}" y1="${m.t}" y2="${H - m.b}" stroke="#8a969e" stroke-width="1"/>`;
      series.forEach(s => { const v = Number(rows[i][s.key]); if (Number.isFinite(v)) svg += `<circle cx="${x(i)}" cy="${y(v)}" r="4.5" fill="${s.color}" stroke="#fff" stroke-width="2"/>`; });
    }
    svg += '</svg>';
    container.innerHTML = svg;
    const el = container.querySelector('svg');
    const move = ev => {
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

  // ---------- 내보내기 ----------
  $('export').addEventListener('click', () => {
    const list = filteredCases();
    if (!list.length) { setMessage('내보낼 점검 구간이 없습니다.', true); return; }
    const cols = ['record_id', 'first_timestamp', 'first_alarm_position', 'detection_delay_s', 'alarm_rows', 'observed_rows', 'peak_score', 'min_p', 'evidence', 'action', 'reference_label'];
    const cell = v => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const csv = [cols.join(','), ...list.map(c => cols.map(k => cell(c[k])).join(','))].join('\n');
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
  async function start() {
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
