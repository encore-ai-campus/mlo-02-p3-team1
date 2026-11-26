// 전체 현황 화면 상호작용: 추이 그래프 확대, 지표·분야 연동, 상세 패널, 카드 배치, 자동 갱신.
// 서버 화면(overview.html)이 그대로 동작하는 상태에서 기능만 더한다. 수치는 서버가 내려준 것만 쓴다.
(() => {
  'use strict';
  const root = document.querySelector('[data-ov-root]');
  if (!root) return;

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const store = {
    get(key, fallback) { try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch (e) { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* 저장 불가 환경 */ } },
    remove(key) { try { localStorage.removeItem(key); } catch (e) { /* noop */ } },
  };
  const h = (tag, attrs = {}, ...children) => {
    const el = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (v === null || v === undefined || v === false) return;
      if (k === 'class') el.className = v; else if (k === 'text') el.textContent = v; else el.setAttribute(k, v === true ? '' : v);
    });
    children.flat().forEach((c) => { if (c !== null && c !== undefined && c !== false) el.append(c.nodeType ? c : document.createTextNode(String(c))); });
    return el;
  };
  const announcer = h('p', { class: 'sr-only', 'aria-live': 'polite' });
  root.append(announcer);
  const announce = (text) => { announcer.textContent = ''; setTimeout(() => { announcer.textContent = text; }, 30); };
  const pad = (n) => String(n).padStart(2, '0');
  const clock = (d = new Date()) => `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;

  // JS가 있어야 쓰는 조작부만 보인다(스크립트 없이도 화면은 그대로 읽힘).
  $$('[data-live], [data-edit-toggle], [data-log-chips], [data-trend-tools]', root).forEach((el) => { el.hidden = false; });

  // ---------------------------------------------------------------- 추이 그래프
  const SERIES = [
    { key: 'started', label: '문제 시작', color: 'var(--trend-start)' },
    { key: 'completed', label: '문제 해결', color: 'var(--trend-done)' },
  ];
  const chartEl = $('[data-ov-trend]', root);
  const readData = (doc) => {
    const el = doc.getElementById('visualization-data');
    try { return el ? JSON.parse(el.textContent) : null; } catch (e) { return null; }
  };
  let data = readData(document);
  const trend = {
    from: 0, to: 0, hidden: new Set(store.get('nodeverse.overview.hidden', [])), emphasis: null,
    hover: null, brush: null, drawn: false,
  };
  const rows = () => (data && Array.isArray(data.trend) ? data.trend : []);
  const resetRange = () => { trend.from = 0; trend.to = Math.max(0, rows().length - 1); };
  resetRange();

  const NS = 'http://www.w3.org/2000/svg';
  const s = (tag, attrs = {}) => { const el = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v)); return el; };
  const niceStep = (raw) => { const p = 10 ** Math.floor(Math.log10(raw || 1)); const f = raw / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; };
  const filterEnd = () => { const el = $('#analysis-filters [name=end]'); return el && el.value ? el.value : null; };
  const addDays = (iso, days) => { const d = new Date(iso + 'T00:00:00'); d.setDate(d.getDate() + days); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
  const pointEnd = (row) => {
    const stride = (data && data.stride) || 1;
    if (!row.date) return null;
    let end = addDays(row.date, stride - 1);
    const limit = filterEnd();
    if (limit && end > limit) end = limit;
    return end;
  };
  let geom = null;

  function renderTrend() {
    if (!chartEl) return;
    const all = rows();
    const tools = $('[data-trend-tools]', root);
    if (!data || !data.runs || !all.length) {
      chartEl.replaceChildren(h('p', { class: 'ov-empty trend-empty', text: '선택한 기간에 시작한 문제가 없습니다.' }));
      if (tools) tools.classList.add('is-disabled');
      updateRangeLabel();
      return;
    }
    if (tools) tools.classList.remove('is-disabled');
    trend.from = Math.max(0, Math.min(trend.from, all.length - 1));
    trend.to = Math.max(trend.from, Math.min(trend.to, all.length - 1));
    const view = all.slice(trend.from, trend.to + 1);
    const width = Math.max(240, chartEl.clientWidth);
    const height = Math.max(160, chartEl.clientHeight);
    const m = { l: 38, r: 14, t: 14, b: 28 };
    const pw = width - m.l - m.r, ph = height - m.t - m.b;
    const visible = SERIES.filter((sr) => !trend.hidden.has(sr.key));
    const peak = Math.max(1, ...view.flatMap((r) => visible.map((sr) => r[sr.key] || 0)));
    const step = niceStep(peak / 4);
    const top = Math.max(step, Math.ceil(peak / step) * step);
    const x = (i) => m.l + (view.length <= 1 ? pw / 2 : (i * pw) / (view.length - 1));
    const y = (v) => m.t + ph - (v / top) * ph;
    geom = { m, pw, ph, width, height, x, y, n: view.length };

    const svg = s('svg', { viewBox: `0 0 ${width} ${height}`, width, height, class: 'trend-svg', 'aria-hidden': 'true' });
    for (let v = 0; v <= top + 1e-9; v += step) {
      svg.append(s('line', { x1: m.l, x2: width - m.r, y1: y(v), y2: y(v), class: v === 0 ? 'axis-line' : 'grid-line' }));
      const t = s('text', { x: m.l - 8, y: y(v) + 4, class: 'axis-text', 'text-anchor': 'end' }); t.textContent = Math.round(v); svg.append(t);
    }
    const every = Math.max(1, Math.ceil(view.length / Math.max(2, Math.floor(pw / 58))));
    view.forEach((r, i) => {
      const lastIndex = view.length - 1;
      if (i !== lastIndex && (i % every || (i && lastIndex - i < every * 0.6))) return;
      const t = s('text', { x: x(i), y: height - 8, class: 'axis-text', 'text-anchor': i === 0 && view.length > 1 ? 'start' : i === view.length - 1 && view.length > 1 ? 'end' : 'middle' });
      t.textContent = r.label; svg.append(t);
    });
    if (!visible.length) {
      const t = s('text', { x: m.l + pw / 2, y: m.t + ph / 2, class: 'axis-text', 'text-anchor': 'middle' });
      t.textContent = '범례에서 표시할 항목을 선택하세요'; svg.append(t);
    }
    visible.forEach((sr) => {
      const pts = view.map((r, i) => [x(i), y(r[sr.key] || 0)]);
      const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('');
      const dim = trend.emphasis && trend.emphasis !== sr.key ? ' is-dim' : '';
      const strong = trend.emphasis === sr.key ? ' is-strong' : '';
      const g = s('g', { class: `series series-${sr.key}${dim}${strong}`, style: `--c:${sr.color}` });
      g.append(s('path', { d: `${line}L${pts[pts.length - 1][0].toFixed(1)},${y(0)}L${pts[0][0].toFixed(1)},${y(0)}Z`, class: 'series-area' }));
      const path = s('path', { d: line, class: 'series-line' + (!trend.drawn && !reduceMotion ? ' is-drawing' : '') });
      g.append(path);
      if (view.length <= 40) pts.forEach((p) => g.append(s('circle', { cx: p[0], cy: p[1], r: 2.6, class: 'series-dot' })));
      svg.append(g);
    });
    svg.append(s('line', { class: 'hover-line', x1: 0, x2: 0, y1: m.t, y2: m.t + ph, visibility: 'hidden' }));
    svg.append(s('g', { class: 'hover-dots' }));
    svg.append(s('rect', { class: 'brush', x: 0, y: m.t, width: 0, height: ph, visibility: 'hidden' }));
    svg.append(s('rect', { class: 'trend-hit', x: m.l, y: m.t, width: pw, height: ph }));
    const tip = h('div', { class: 'trend-tip', role: 'status', hidden: true });
    chartEl.replaceChildren(svg, tip);
    trend.drawn = true;
    $$('[data-series]', root).forEach((b) => {
      b.setAttribute('aria-pressed', String(!trend.hidden.has(b.dataset.series)));
      b.classList.toggle('is-strong', trend.emphasis === b.dataset.series);
    });
    updateRangeLabel();
    if (trend.hover !== null) showHover(trend.hover);
  }

  // 표시 중인 구간 요약(확대하면 그 구간 기준으로 다시 계산). 서버가 준 날짜별 값만 더한다.
  function updateSummary() {
    const box = $('[data-trend-summary]', root);
    if (!box) return;
    const all = rows();
    if (!data || !data.runs || !all.length) { box.hidden = true; return; }
    const view = all.slice(trend.from, trend.to + 1);
    const started = view.reduce((n, r) => n + (r.started || 0), 0);
    const completed = view.reduce((n, r) => n + (r.completed || 0), 0);
    const active = view.filter((r) => r.started).length;
    const peak = view.reduce((best, r) => ((r.started || 0) > (best.started || 0) ? r : best), view[0]);
    const stride = data.stride || 1;
    const unit = stride > 1 ? `${stride}일 묶음` : '날';
    const item = (label, value, note, empty) => h('div', {}, h('dt', { text: label }), h('dd', {}, h('b', { class: empty ? 'is-empty' : '', text: value }), note ? h('small', { text: note }) : null));
    box.replaceChildren(
      item('표시 구간 문제 시작', `${started}건`, `${view.length}개 ${unit} 중 ${active}개에 기록`, !started),
      item('그중 해결', started ? `${completed}건` : '기록 없음', started ? `해결 비율 ${Math.round((100 * completed) / started)}%` : '시작한 문제 없음', !started),
      item(`문제 시작이 가장 많은 ${stride > 1 ? '구간' : '날'}`, peak && peak.started ? peak.label : '기록 없음', peak && peak.started ? `${peak.started}건 시작 · ${peak.completed || 0}건 해결` : null, !(peak && peak.started)),
      item(`${stride > 1 ? '구간' : '하루'} 평균 시작`, `${(started / view.length).toFixed(1)}건`, '기록 없는 날 포함', !started),
    );
    box.hidden = false;
  }

  function updateRangeLabel() {
    updateSummary();
    const label = $('[data-trend-range]', root);
    const apply = $('[data-zoom-apply]', root);
    const all = rows();
    const zoomed = all.length && (trend.from > 0 || trend.to < all.length - 1);
    if (label) {
      label.textContent = !all.length ? '' : zoomed
        ? `${all[trend.from].label} ~ ${all[trend.to].label} 확대 중 (${trend.to - trend.from + 1}/${all.length}구간)`
        : `전체 기간 ${all[0].label} ~ ${all[all.length - 1].label}`;
    }
    $$('[data-zoom="reset"], [data-zoom="out"]', root).forEach((b) => { b.disabled = !zoomed; });
    const zin = $('[data-zoom="in"]', root);
    if (zin) zin.disabled = !all.length || trend.to - trend.from < 2;
    if (apply) {
      apply.hidden = !(zoomed && all[trend.from].date);
      if (!apply.hidden) {
        const params = new URLSearchParams(location.search);
        params.set('start', all[trend.from].date);
        params.set('end', pointEnd(all[trend.to]));
        params.delete('page');
        apply.href = `${location.pathname}?${params}`;
      }
    }
  }

  const indexAt = (clientX) => {
    if (!geom) return null;
    const rect = chartEl.querySelector('svg').getBoundingClientRect();
    const px = ((clientX - rect.left) / rect.width) * geom.width;
    if (geom.n <= 1) return 0;
    const i = Math.round(((px - geom.m.l) / geom.pw) * (geom.n - 1));
    return Math.max(0, Math.min(geom.n - 1, i));
  };

  function showHover(local) {
    const svg = chartEl && chartEl.querySelector('svg');
    if (!svg || !geom || local === null) return;
    local = Math.max(0, Math.min(geom.n - 1, local));
    trend.hover = local;
    const row = rows()[trend.from + local];
    const line = svg.querySelector('.hover-line');
    const dots = svg.querySelector('.hover-dots');
    const cx = geom.x(local);
    line.setAttribute('x1', cx); line.setAttribute('x2', cx); line.setAttribute('visibility', 'visible');
    dots.replaceChildren(...SERIES.filter((sr) => !trend.hidden.has(sr.key)).map((sr) => s('circle', { cx, cy: geom.y(row[sr.key] || 0), r: 4.5, class: 'hover-dot', style: `--c:${sr.color}` })));
    const tip = chartEl.querySelector('.trend-tip');
    const stride = (data && data.stride) || 1;
    const rate = row.started ? Math.round((100 * row.completed) / row.started) : null;
    tip.replaceChildren(
      h('strong', {}, row.label, stride > 1 ? h('small', { text: ` 부터 ${stride}일` }) : null),
      ...SERIES.map((sr) => h('span', { class: trend.hidden.has(sr.key) ? 'is-off' : '' }, h('i', { style: `background:${sr.color}` }), sr.label, h('b', { text: `${row[sr.key] || 0}건` }))),
      h('small', { class: 'tip-note', text: rate === null ? '이날 시작한 문제 없음' : `이날 시작 중 지금까지 해결 ${rate}%` }),
    );
    tip.hidden = false;
    const box = chartEl.getBoundingClientRect();
    const svgBox = svg.getBoundingClientRect();
    const px = svgBox.left - box.left + (cx / geom.width) * svgBox.width;
    const tw = tip.offsetWidth;
    tip.style.left = `${Math.max(4, Math.min(box.width - tw - 4, px + (px + tw + 16 > box.width ? -tw - 12 : 12)))}px`;
    tip.style.top = '8px';
  }
  function hideHover() {
    trend.hover = null;
    const svg = chartEl && chartEl.querySelector('svg');
    if (!svg) return;
    svg.querySelector('.hover-line').setAttribute('visibility', 'hidden');
    svg.querySelector('.hover-dots').replaceChildren();
    const tip = chartEl.querySelector('.trend-tip'); if (tip) tip.hidden = true;
  }

  function zoomTo(from, to, message) {
    const all = rows();
    if (!all.length) return;
    trend.from = Math.max(0, Math.min(from, to));
    trend.to = Math.min(all.length - 1, Math.max(from, to));
    trend.hover = null;
    saveZoom();
    renderTrend();
    if (message) announce(message);
  }
  function zoomBy(factor) {
    const all = rows();
    const span = trend.to - trend.from + 1;
    const center = trend.hover !== null ? trend.from + trend.hover : Math.round((trend.from + trend.to) / 2);
    const next = Math.max(2, Math.min(all.length, Math.round(span * factor)));
    let from = Math.round(center - (next - 1) / 2);
    from = Math.max(0, Math.min(all.length - next, from));
    zoomTo(from, from + next - 1, factor < 1 ? '그래프를 확대했습니다' : '그래프를 축소했습니다');
  }
  const saveZoom = () => {
    const all = rows();
    const zoomed = all.length && (trend.from > 0 || trend.to < all.length - 1);
    trend.saved = zoomed ? { from: all[trend.from].date || all[trend.from].label, to: all[trend.to].date || all[trend.to].label } : null;
  };
  const restoreZoom = () => {
    const all = rows();
    if (!trend.saved) { resetRange(); return; }
    const key = (r) => r.date || r.label;
    const from = all.findIndex((r) => key(r) === trend.saved.from);
    const to = all.findIndex((r) => key(r) === trend.saved.to);
    if (from < 0 || to < 0) { trend.saved = null; resetRange(); return; }
    trend.from = from; trend.to = to;
  };

  if (chartEl) {
    chartEl.addEventListener('dblclick', (e) => {
      const row = rows()[trend.from + indexAt(e.clientX)];
      if (!row || !row.date) return;
      const u = new URL('/staff/events/', location.origin);
      const p = new URLSearchParams(location.search);
      ['source', 'category', 'game_id', 'player_id'].forEach(k => { if (p.has(k)) u.searchParams.set(k,p.get(k)); });
      u.searchParams.set('start', row.date); u.searchParams.set('end', pointEnd(row));
      location.assign(u);
    });
    chartEl.addEventListener('pointerdown', (e) => {
      if (!e.target.classList || !e.target.classList.contains('trend-hit') || e.button !== 0) return;
      const i = indexAt(e.clientX);
      trend.brush = { start: i, end: i, x0: e.clientX };
      chartEl.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    chartEl.addEventListener('pointermove', (e) => {
      const i = indexAt(e.clientX);
      if (i === null) return;
      if (trend.brush) {
        trend.brush.end = i;
        const svg = chartEl.querySelector('svg');
        const rect = svg.querySelector('.brush');
        const a = Math.min(trend.brush.start, i), b = Math.max(trend.brush.start, i);
        const half = geom.n > 1 ? geom.pw / (geom.n - 1) / 2 : geom.pw / 2;
        const x0 = Math.max(geom.m.l, geom.x(a) - half), x1 = Math.min(geom.m.l + geom.pw, geom.x(b) + half);
        rect.setAttribute('x', x0); rect.setAttribute('width', Math.max(0, x1 - x0)); rect.setAttribute('visibility', 'visible');
      }
      if (e.target.classList && (e.target.classList.contains('trend-hit') || trend.brush)) showHover(i);
    });
    const endBrush = (e) => {
      if (!trend.brush) return;
      const { start, end, x0 } = trend.brush;
      trend.brush = null;
      const svg = chartEl.querySelector('svg');
      if (svg) svg.querySelector('.brush').setAttribute('visibility', 'hidden');
      if (e.type === 'pointerup' && Math.abs(end - start) >= 1 && Math.abs(e.clientX - x0) > 6) {
        zoomTo(trend.from + Math.min(start, end), trend.from + Math.max(start, end), '선택한 구간으로 확대했습니다');
      }
    };
    chartEl.addEventListener('pointerup', endBrush);
    chartEl.addEventListener('pointercancel', endBrush);
    chartEl.addEventListener('pointerleave', () => { if (!trend.brush && document.activeElement !== chartEl) hideHover(); });
    chartEl.addEventListener('dblclick', () => zoomTo(0, rows().length - 1, '전체 기간으로 돌아왔습니다'));
    chartEl.addEventListener('keydown', (e) => {
      if (!geom) return;
      const cur = trend.hover === null ? geom.n - 1 : trend.hover;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        e.preventDefault();
        const next = cur + (e.key === 'ArrowLeft' ? -1 : 1);
        if (next < 0 && trend.from > 0) { zoomTo(trend.from - 1, trend.to - 1); showHover(0); return; }
        if (next >= geom.n && trend.to < rows().length - 1) { zoomTo(trend.from + 1, trend.to + 1); showHover(geom.n - 1); return; }
        showHover(next);
      } else if (e.key === 'Home') { e.preventDefault(); showHover(0); }
      else if (e.key === 'End') { e.preventDefault(); showHover(geom.n - 1); }
      else if (e.key === '+' || e.key === '=') { e.preventDefault(); zoomBy(0.5); }
      else if (e.key === '-' || e.key === '_') { e.preventDefault(); zoomBy(2); }
      else if (e.key === '0') { e.preventDefault(); zoomTo(0, rows().length - 1, '전체 기간으로 돌아왔습니다'); }
      else if (e.key === 'Escape') hideHover();
    });
    chartEl.addEventListener('focus', () => { if (geom && trend.hover === null) showHover(geom.n - 1); });
    chartEl.addEventListener('blur', hideHover);
    if ('ResizeObserver' in window) {
      let last = chartEl.clientWidth + 'x' + chartEl.clientHeight;
      new ResizeObserver(() => { const w = chartEl.clientWidth + 'x' + chartEl.clientHeight; if (w !== last) { last = w; renderTrend(); } }).observe(chartEl);
    } else window.addEventListener('resize', renderTrend);
  }
  root.addEventListener('click', (e) => {
    const zoom = e.target.closest('[data-zoom]');
    if (zoom) {
      if (zoom.dataset.zoom === 'in') zoomBy(0.5);
      else if (zoom.dataset.zoom === 'out') zoomBy(2);
      else zoomTo(0, rows().length - 1, '전체 기간으로 돌아왔습니다');
      return;
    }
    const series = e.target.closest('[data-series]');
    if (series) {
      const key = series.dataset.series;
      if (trend.hidden.has(key)) trend.hidden.delete(key); else trend.hidden.add(key);
      store.set('nodeverse.overview.hidden', [...trend.hidden]);
      renderTrend();
      announce(`${series.textContent.trim()} ${trend.hidden.has(key) ? '숨김' : '표시'}`);
    }
  });
  renderTrend();

  // ---------------------------------------------------------------- 로그 필터 · 지표 연동
  const LINKS = {
    players: { label: '활성 플레이어', series: 'started', log: 'all', column: 'player', text: '그래프는 문제 시작을, 로그는 플레이어 열을 강조합니다' },
    completion: { label: '문제 해결률', series: 'completed', log: 'solved', text: '그래프는 문제 해결을 강조하고, 로그는 문제 해결 기록만 보여 줍니다' },
    time: { label: '평균 풀이 시간', series: 'completed', log: 'solved', text: '풀이 시간이 계산되는 해결 기록만 로그에 남깁니다' },
    retry: { label: '재시작한 문제', series: null, log: 'failure', card: 'attention', text: '확인이 필요한 문제를 강조하고, 로그는 실패 기록만 보여 줍니다' },
  };
  const LOG_LABELS = { all: '전체', success: '성공', failure: '실패', solved: '문제 해결', hint: '힌트' };
  let logFilter = 'all';
  let linkKey = null;

  function applyLogFilter() {
    const body = $('[data-live-part="recent"]', root);
    if (!body) return;
    const all = $$('tr[data-key]', body);
    let shown = 0;
    all.forEach((tr) => {
      const ok = logFilter === 'all'
        || (logFilter === 'success' && tr.dataset.result === 'success')
        || (logFilter === 'failure' && tr.dataset.result === 'failure')
        || (logFilter === 'solved' && tr.hasAttribute('data-solved'))
        || (logFilter === 'hint' && tr.hasAttribute('data-hint'));
      tr.hidden = !ok;
      if (ok) shown += 1;
    });
    const empty = $('.log-filter-empty', body);
    if (empty) empty.hidden = !(all.length && !shown);
    $$('[data-log-filter]', root).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.logFilter === logFilter)));
    const count = $('[data-log-count]', root);
    if (count) count.textContent = logFilter === 'all' ? `최근 ${all.length}건` : `최근 ${all.length}건 중 ${LOG_LABELS[logFilter]} ${shown}건`;
  }
  function applyLink() {
    const link = linkKey ? LINKS[linkKey] : null;
    $$('[data-kpi-link]', root).forEach((b) => {
      const on = b.dataset.kpiLink === linkKey;
      b.setAttribute('aria-pressed', String(on));
      b.closest('.kpi').classList.toggle('is-linked', on);
    });
    root.classList.toggle('has-link', Boolean(link));
    root.dataset.highlight = link && link.column ? link.column : '';
    $$('[data-card]', root).forEach((c) => c.classList.toggle('is-spotlight', Boolean(link && link.card === c.dataset.card)));
    const bar = $('[data-link-bar]', root);
    if (bar) {
      bar.hidden = !link;
      if (link) $('[data-link-text]', bar).replaceChildren(h('b', { text: link.label }), ` 기준으로 보는 중 · ${link.text}`);
    }
    if (trend.emphasis !== (link ? link.series : null)) { trend.emphasis = link ? link.series : null; renderTrend(); }
  }
  function setLink(key) {
    linkKey = key && key !== linkKey ? key : null;
    logFilter = linkKey ? LINKS[linkKey].log : 'all';
    applyLink();
    applyLogFilter();
    announce(linkKey ? `${LINKS[linkKey].label} 연결: ${LINKS[linkKey].text}` : '지표 연결을 해제했습니다');
  }
  root.addEventListener('click', (e) => {
    const kpi = e.target.closest('[data-kpi-link]');
    if (kpi) { setLink(kpi.dataset.kpiLink); return; }
    if (e.target.closest('[data-link-clear]')) { setLink(null); return; }
    const chip = e.target.closest('[data-log-filter]');
    if (chip) {
      if (linkKey) { linkKey = null; applyLink(); }
      logFilter = chip.dataset.logFilter;
      applyLogFilter();
    }
  });
  applyLogFilter();

  // ---------------------------------------------------------------- 상세 패널(오른쪽)
  const drawer = $('[data-drawer]', root);
  const drawerBody = drawer && $('[data-drawer-body]', drawer);
  let drawerTrigger = null;
  let drawerTimer = null;
  function openDrawer(heading, content, trigger) {
    if (!drawer) return;
    const zoomDialog = $('[data-zoom-dialog]', root);
    if (zoomDialog && zoomDialog.open) zoomDialog.close();
    $$('.is-selected', root).forEach((el) => el.classList.remove('is-selected'));
    drawerTrigger = trigger || null;
    const row = trigger && (trigger.closest('tr[data-key]') || trigger.closest('.attention-list li'));
    if (row) row.classList.add('is-selected');
    $('[data-drawer-heading]', drawer).textContent = heading;
    drawerBody.replaceChildren(content);
    clearTimeout(drawerTimer);
    drawer.hidden = false;
    root.classList.add('has-drawer');
    requestAnimationFrame(() => { drawer.classList.add('is-open'); drawerBody.scrollTop = 0; drawerBody.focus({ preventScroll: true }); });
  }
  function closeDrawer() {
    if (!drawer || drawer.hidden) return;
    drawer.classList.remove('is-open');
    root.classList.remove('has-drawer');
    $$('.is-selected', root).forEach((el) => el.classList.remove('is-selected'));
    drawerTimer = setTimeout(() => { drawer.hidden = true; }, reduceMotion ? 0 : 220);
    if (drawerTrigger && document.contains(drawerTrigger)) drawerTrigger.focus({ preventScroll: true });
    drawerTrigger = null;
  }
  const fromTemplate = (id) => { const t = document.getElementById(id); return t ? t.content.cloneNode(true) : h('p', { class: 'ov-empty', text: '상세 정보를 찾지 못했습니다.' }); };

  const analysisQuery = () => {
    const params = new URLSearchParams(location.search);
    ['page', 'scope', 'format'].forEach((k) => params.delete(k));
    return params;
  };
  async function openPlayer(link) {
    const id = link.dataset.player;
    const name = link.dataset.playerName || link.textContent.trim();
    const box = h('div', { class: 'drawer-player' }, h('p', { class: 'drawer-kicker', text: '플레이어' }), h('h3', { class: 'drawer-title', text: name }), h('p', { class: 'ov-empty', text: '불러오는 중…' }));
    openDrawer('플레이어 요약', box, link);
    try {
      const res = await fetch(`/api/admin/players/${encodeURIComponent(id)}?${analysisQuery()}`, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!res.ok) throw new Error(String(res.status));
      const json = await res.json();
      if (drawerTrigger !== link) return;
      const sm = json.summary || {}, ln = json.learning || {};
      const stat = (label, value, note, empty) => h('div', {}, h('dt', { text: label }), h('dd', {}, h('b', { class: empty ? 'is-empty' : '', text: value }), note ? h('small', { text: note }) : null));
      const tasks = (ln.tasks || []).filter((t) => t.runs).sort((a, b) => (b.retry_runs / b.runs) - (a.retry_runs / a.runs) || b.runs - a.runs).slice(0, 4);
      const player = json.player || {};
      const playerHref = link.getAttribute('href');
      const logs = new URLSearchParams(analysisQuery()); logs.set('player_id', id);
      box.replaceChildren(
        h('p', { class: 'drawer-kicker' }, '플레이어 · ', player.source === 'demo' ? '데모' : '실제', ' · ', h('code', { text: (player.external_id || '').slice(0, 18) })),
        h('h3', { class: 'drawer-title', text: player.display_name || name }),
        h('dl', { class: 'drawer-stats' },
          stat('문제 해결률', ln.runs ? `${ln.completion_rate}%` : '기록 없음', ln.runs ? `해결 ${ln.completed} / 시작 ${ln.runs}건` : '시작한 문제 없음', !ln.runs),
          stat('재시작한 문제', ln.runs ? `${ln.retry_runs}건` : '기록 없음', '같은 레벨 2회 이상', !ln.runs),
          stat('평균 풀이 시간', ln.avg_active_seconds != null ? `${Math.round(ln.avg_active_seconds)}초` : (ln.completed ? '미수집' : '기록 없음'), ln.avg_active_seconds != null ? '해결한 문제 기준' : null, ln.avg_active_seconds == null),
          stat('행동 기록', `${sm.total || 0}건`, `연산·시도 성공 ${sm.successes || 0} · 실패 ${sm.failures || 0}`, !sm.total),
          stat('힌트', `${sm.hints || 0}회`, null, false),
          stat('시도', `${sm.attempts || 0}회`, null, false),
        ),
        h('p', { class: 'ov-note', text: '문제 해결률은 문제 완료 기준이고, 행동 기록의 성공·실패는 연산 하나하나의 결과입니다.' }),
        h('h4', { class: 'drawer-sub', text: '재시작이 많은 문제' }),
        tasks.length ? h('ol', { class: 'drawer-causes' }, tasks.map((t) => {
          const rate = Math.round((100 * t.retry_runs) / t.runs);
          return h('li', {}, h('span', {}, h('b', { text: t.title || t.task_id }), h('small', { text: `${t.task_id} · 버전 ${t.version}` })),
            h('span', { class: 'bar', role: 'img', 'aria-label': `재시작률 ${rate}%` }, h('i', { style: `width:${rate}%` })),
            h('span', { class: 'numeric', text: `${t.retry_runs}/${t.runs}회 · ${rate}%` }));
        })) : h('p', { class: 'ov-empty', text: '선택한 기간에 시작한 문제가 없습니다.' }),
        h('div', { class: 'drawer-actions' }, h('a', { class: 'btn-solid', href: playerHref, text: '플레이어 상세' }), h('a', { class: 'btn-ghost', href: `/staff/events/?${logs}`, text: '이 플레이어 로그' })),
      );
    } catch (err) {
      if (drawerTrigger !== link) return;
      box.replaceChildren(h('p', { class: 'ov-empty', text: '플레이어 정보를 불러오지 못했습니다.' }), h('div', { class: 'drawer-actions' }, h('a', { class: 'btn-solid', href: link.getAttribute('href'), text: '플레이어 상세로 이동' })));
    }
  }

  root.addEventListener('click', (e) => {
    if (e.target.closest('[data-drawer-close]')) { closeDrawer(); return; }
    const modified = e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button > 0;
    const player = e.target.closest('a[data-player]');
    if (player && !modified) { e.preventDefault(); openPlayer(player); return; }
    const task = e.target.closest('button[data-detail]');
    if (task) { openDrawer('문제 상세', fromTemplate(`detail-${task.dataset.detail}`), task); return; }
    const row = e.target.closest('tr[data-detail]');
    if (row && !e.target.closest('a, button')) openDrawer('행동 로그 상세', fromTemplate(`detail-${row.dataset.detail}`), row);
  });
  root.addEventListener('keydown', (e) => {
    const row = e.target.matches && e.target.matches('tr[data-detail]') ? e.target : null;
    if (row && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openDrawer('행동 로그 상세', fromTemplate(`detail-${row.dataset.detail}`), row); }
    if (row && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault();
      const list = $$('tr[data-detail]:not([hidden])', root);
      const next = list[list.indexOf(row) + (e.key === 'ArrowDown' ? 1 : -1)];
      if (next) next.focus();
    }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && drawer && !drawer.hidden && !$('[data-zoom-dialog]', root).open) closeDrawer();
  });

  // ---------------------------------------------------------------- 카드: 크게 보기 · 배치 편집
  const board = $('[data-board]', root);
  const LAYOUT_KEY = 'nodeverse.overview.layout.v1';
  const SPANS = [4, 6, 8, 12];
  const cards = () => $$(':scope > [data-card]', board);
  const defaults = { order: cards().map((c) => c.dataset.card), spans: Object.fromEntries(cards().map((c) => [c.dataset.card, c.dataset.span])) };
  function applyLayout(layout) {
    const byId = Object.fromEntries(cards().map((c) => [c.dataset.card, c]));
    const order = [...(layout.order || []).filter((id) => byId[id]), ...defaults.order.filter((id) => byId[id] && !(layout.order || []).includes(id))];
    order.forEach((id) => board.append(byId[id]));
    Object.entries(byId).forEach(([id, c]) => {
      const span = Number((layout.spans || {})[id] || defaults.spans[id]);
      c.dataset.span = SPANS.includes(span) ? span : defaults.spans[id];
    });
  }
  const saveLayout = () => store.set(LAYOUT_KEY, { order: cards().map((c) => c.dataset.card), spans: Object.fromEntries(cards().map((c) => [c.dataset.card, c.dataset.span])) });
  const cardName = (c) => { const t = c.querySelector('h2'); return t ? t.childNodes[0].textContent.trim() : c.dataset.card; };
  if (board) applyLayout(store.get(LAYOUT_KEY, defaults));

  const editToggle = $('[data-edit-toggle]', root);
  const editBar = $('[data-edit-bar]', root);
  function setEditing(on) {
    root.classList.toggle('is-editing', on);
    if (editToggle) { editToggle.setAttribute('aria-pressed', String(on)); editToggle.querySelector('span').textContent = on ? '편집 중' : '배치 편집'; }
    if (editBar) editBar.hidden = !on;
    cards().forEach((c) => { c.draggable = on; });
    announce(on ? '배치 편집을 시작했습니다. 카드의 위치와 너비를 바꿀 수 있습니다.' : '배치를 저장했습니다');
  }
  root.addEventListener('click', (e) => {
    if (e.target.closest('[data-edit-toggle]')) { setEditing(!root.classList.contains('is-editing')); return; }
    if (e.target.closest('[data-edit-done]')) { saveLayout(); setEditing(false); return; }
    if (e.target.closest('[data-layout-reset]')) { store.remove(LAYOUT_KEY); applyLayout(defaults); announce('기본 배치로 되돌렸습니다'); return; }
    const move = e.target.closest('[data-move]');
    if (move) {
      const card = move.closest('[data-card]');
      const list = cards();
      const i = list.indexOf(card), j = i + Number(move.dataset.move);
      if (j < 0 || j >= list.length) return;
      if (j > i) list[j].after(card); else list[j].before(card);
      move.focus();
      saveLayout();
      announce(`${cardName(card)} 카드를 ${j + 1}번째로 옮겼습니다`);
      return;
    }
    const resize = e.target.closest('[data-resize]');
    if (resize) {
      const card = resize.closest('[data-card]');
      const next = SPANS[(SPANS.indexOf(Number(card.dataset.span)) + 1) % SPANS.length];
      card.dataset.span = next;
      saveLayout();
      announce(`${cardName(card)} 카드 너비 ${Math.round((next / 12) * 100)}%`);
    }
  });
  let dragged = null;
  if (board) {
    board.addEventListener('dragstart', (e) => {
      if (!root.classList.contains('is-editing')) return;
      dragged = e.target.closest('[data-card]');
      if (!dragged) return;
      dragged.classList.add('is-dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', dragged.dataset.card);
    });
    board.addEventListener('dragover', (e) => {
      if (!dragged) return;
      e.preventDefault();
      const over = e.target.closest('[data-card]');
      if (!over || over === dragged) return;
      const r = over.getBoundingClientRect();
      const sideBySide = Number(over.dataset.span) < 12;
      const before = sideBySide ? e.clientX < r.left + r.width / 2 : e.clientY < r.top + r.height / 2;
      if (before) over.before(dragged); else over.after(dragged);
    });
    board.addEventListener('drop', (e) => { if (dragged) e.preventDefault(); });
    board.addEventListener('dragend', () => { if (!dragged) return; dragged.classList.remove('is-dragging'); dragged = null; saveLayout(); });
  }

  const zoomDialog = $('[data-zoom-dialog]', root);
  const zoomSlot = zoomDialog && $('[data-zoom-slot]', zoomDialog);
  let zoomed = null;
  root.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-card-expand]');
    if (btn && zoomDialog && typeof zoomDialog.showModal === 'function') {
      const card = btn.closest('[data-card]');
      if (zoomed) { zoomDialog.close(); return; }
      const holder = h('div', { class: 'card-placeholder', style: `height:${card.offsetHeight}px` });
      holder.dataset.span = card.dataset.span;
      card.before(holder);
      zoomed = { card, holder, button: btn };
      card.classList.add('is-zoomed');
      zoomSlot.append(card);
      zoomDialog.setAttribute('aria-label', `${cardName(card)} 크게 보기`);
      zoomDialog.showModal();
      btn.setAttribute('aria-label', '크게 보기 닫기');
      return;
    }
    if (e.target.closest('[data-zoom-close]') && zoomDialog) zoomDialog.close();
  });
  if (zoomDialog) {
    zoomDialog.addEventListener('click', (e) => { if (e.target === zoomDialog) zoomDialog.close(); });
    zoomDialog.addEventListener('close', () => {
      if (!zoomed) return;
      const { card, holder, button } = zoomed;
      holder.replaceWith(card);
      card.classList.remove('is-zoomed');
      button.setAttribute('aria-label', '크게 보기');
      zoomed = null;
      button.focus({ preventScroll: true });
    });
  }

  // ---------------------------------------------------------------- 자동 갱신 · 분야 연동(제자리 교체)
  const LIVE_KEY = 'nodeverse.overview.live';
  const live = { on: store.get(LIVE_KEY, { on: true }).on !== false, interval: Number(store.get(LIVE_KEY, {}).interval) || 60, timer: null, busy: false, due: 0 };
  const toggle = $('[data-live-toggle]', root);
  const intervalSelect = $('[data-live-interval]', root);
  const status = $('[data-live-status]', root);
  const notice = $('[data-live-notice]', root);
  let lastRefreshed = new Date();
  if (intervalSelect) intervalSelect.value = String(live.interval);
  const icon = (name) => {
    const svg = s('svg', { class: 'nav-icon', width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.5, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' });
    if (name === 'pause') { svg.append(s('rect', { x: 6, y: 5, width: 4, height: 14, rx: 1 }), s('rect', { x: 14, y: 5, width: 4, height: 14, rx: 1 })); }
    else svg.append(s('path', { d: 'M7 4.5v15l12-7.5z' }));
    return svg;
  };
  function paintLive() {
    root.classList.toggle('is-live', live.on);
    if (toggle) {
      toggle.setAttribute('aria-pressed', String(live.on));
      toggle.setAttribute('aria-label', live.on ? '자동 갱신 일시정지' : '자동 갱신 다시 시작');
      toggle.replaceChildren(icon(live.on ? 'pause' : 'play'), h('span', { text: live.on ? '일시정지' : '자동 갱신' }));
    }
    if (status) {
      const left = Math.max(0, Math.round((live.due - Date.now()) / 1000));
      status.textContent = live.busy ? '갱신 중…' : live.on ? (document.hidden ? '화면이 가려져 대기 중' : `${left}초 뒤 갱신`) : `일시정지 · ${clock(lastRefreshed)} 기준`;
    }
  }
  function schedule() {
    clearTimeout(live.timer);
    if (!live.on) { paintLive(); return; }
    live.due = Date.now() + live.interval * 1000;
    paintLive();
  }
  setInterval(() => {
    if (!live.on || live.busy) return;
    if (document.hidden) { paintLive(); return; }
    if (Date.now() >= live.due) refresh({ announceNew: true }); else paintLive();
  }, 1000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && live.on && Date.now() >= live.due) refresh({ announceNew: true }); else paintLive(); });
  if (toggle) toggle.addEventListener('click', () => {
    live.on = !live.on;
    store.set(LIVE_KEY, { on: live.on, interval: live.interval });
    if (live.on) refresh({ announceNew: true }); else schedule();
    announce(live.on ? '자동 갱신을 다시 시작했습니다' : '자동 갱신을 일시정지했습니다');
  });
  if (intervalSelect) intervalSelect.addEventListener('change', () => {
    live.interval = Number(intervalSelect.value) || 60;
    store.set(LIVE_KEY, { on: live.on, interval: live.interval });
    schedule();
  });

  let noticeTimer = null;
  function showNotice(parts) {
    if (!notice || !parts.length) return;
    notice.replaceChildren(h('span', { class: 'live-dot', 'aria-hidden': 'true' }), ...parts, h('button', { type: 'button', class: 'btn-ghost', 'data-notice-close': '', 'aria-label': '알림 닫기', text: '닫기' }));
    notice.hidden = false;
    notice.classList.remove('is-in'); void notice.offsetWidth; notice.classList.add('is-in');
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => { notice.hidden = true; }, 12000);
  }
  root.addEventListener('click', (e) => {
    if (e.target.closest('[data-notice-close]')) { notice.hidden = true; return; }
    const jump = e.target.closest('[data-jump-log]');
    if (jump) { const card = $('[data-card="recent"]', root); if (card) card.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' }); notice.hidden = true; }
  });

  const watchValues = () => Object.fromEntries($$('[data-watch]', root).map((el) => [el.dataset.watch, el.textContent.trim()]));
  const rowKeys = () => new Set($$('[data-live-part="recent"] tr[data-key]', root).map((tr) => tr.dataset.key));

  async function refresh({ url = location.href, announceNew = false, transition = false } = {}) {
    if (live.busy) return false;
    if (dragged || trend.brush) { live.due = Date.now() + 3000; return false; }
    live.busy = true; paintLive();
    root.classList.toggle('is-swapping', transition);
    try {
      const res = await fetch(url, { credentials: 'same-origin', cache: 'no-store', headers: { 'X-Requested-With': 'fetch' } });
      if (!res.ok || !(res.headers.get('content-type') || '').includes('text/html')) throw new Error(String(res.status));
      if (res.redirected && new URL(res.url).pathname !== new URL(url, location.href).pathname) { location.href = url; return false; }
      const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
      if (!doc.querySelector('[data-ov-root]')) throw new Error('layout');
      const beforeValues = watchValues();
      const beforeRows = rowKeys();
      const swap = () => {
        $$('[data-live-part]', root).forEach((part) => {
          const next = doc.querySelector(`[data-live-part="${part.dataset.livePart}"]`);
          if (next) part.innerHTML = next.innerHTML;
        });
        $$('[data-qs-link]', root).forEach((a) => {
          const next = doc.querySelector(`[data-qs-link="${a.dataset.qsLink}"]`);
          if (next) a.setAttribute('href', next.getAttribute('href'));
        });
        const nextData = readData(doc);
        const holder = document.getElementById('visualization-data');
        if (nextData && holder) holder.textContent = JSON.stringify(nextData);
        data = nextData || data;
        restoreZoom();
        renderTrend();
        applyLink();
        applyLogFilter();
      };
      if (transition && document.startViewTransition && !reduceMotion) await document.startViewTransition(swap).updateCallbackDone; else swap();

      const afterValues = watchValues();
      const changed = Object.keys(afterValues).filter((k) => k in beforeValues && beforeValues[k] !== afterValues[k]);
      changed.forEach((k) => { const el = $(`[data-watch="${CSS.escape(k)}"]`, root); if (el) { el.classList.remove('is-changed'); void el.offsetWidth; el.classList.add('is-changed'); } });
      const fresh = $$('[data-live-part="recent"] tr[data-key]', root).filter((tr) => !beforeRows.has(tr.dataset.key));
      if (announceNew) {
        fresh.forEach((tr) => tr.classList.add('is-new'));
        const parts = [];
        if (fresh.length) parts.push(h('span', {}, '새 행동 기록 ', h('b', { text: `${fresh.length}건` })), h('button', { type: 'button', class: 'text-link', 'data-jump-log': '', text: '로그 보기' }));
        if (changed.length) parts.push(h('span', { text: `바뀐 값 ${changed.length}개를 강조했습니다` }));
        if (parts.length) { parts.push(h('small', { text: clock() })); showNotice(parts); }
      }
      lastRefreshed = new Date();
      return true;
    } catch (err) {
      if (status) status.textContent = '갱신 실패 · 다음 주기에 다시 시도';
      if (!announceNew) location.href = url;
      return false;
    } finally {
      live.busy = false;
      root.classList.remove('is-swapping');
      schedule();
    }
  }

  // 분야 카드: 이 화면 전체에 분야 필터를 걸거나 푼다(주소도 함께 바뀌어 새로고침·공유 가능).
  const syncFilterForm = () => {
    const params = new URLSearchParams(location.search);
    const category = $('#analysis-filters [name=category]');
    if (category) category.value = params.get('category') || '';
    const game = $('#analysis-filters [name=game_id]');
    if (game) game.value = params.get('game_id') || '';
    const reset = $('#analysis-filters .ov-reset');
    if (reset) reset.classList.toggle('is-active', [...params.keys()].length > 0);
  };
  // 사이드바의 분석 화면 링크에 지금 조건(기간·분야·데이터 구분)을 이어 붙인다.
  const syncNav = () => {
    const params = new URLSearchParams(location.search);
    const keep = new URLSearchParams();
    ['start', 'end', 'source', 'category'].forEach((k) => { if (params.get(k)) keep.set(k, params.get(k)); });
    $$('.sidebar a[href]').forEach((a) => {
      const u = new URL(a.href, location.href);
      if (!['/staff/', '/staff/games/', '/staff/events/'].includes(u.pathname)) return;
      u.search = keep.toString();
      a.href = u.pathname + u.search;
    });
  };
  root.addEventListener('click', async (e) => {
    const a = e.target.closest('a[data-area-filter]');
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button > 0) return;
    e.preventDefault();
    const url = a.getAttribute('href');
    history.pushState({ overview: true }, '', url);
    syncFilterForm(); syncNav();
    const label = a.querySelector('strong') ? a.querySelector('strong').textContent : '';
    const ok = await refresh({ url, transition: true });
    if (ok) announce(new URLSearchParams(location.search).get('category') ? `${label} 분야로 지표·그래프·로그를 다시 계산했습니다` : '분야 필터를 해제했습니다');
  });
  window.addEventListener('popstate', () => { syncFilterForm(); syncNav(); refresh({ url: location.href, transition: true }); });
  syncNav();
  schedule();
})();
