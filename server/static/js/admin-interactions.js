/* Progressive interaction layer. Server links, forms and existing page scripts remain authoritative. */
(() => {
  'use strict';
  const main = document.querySelector('main.workspace');
  if (!main) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const animate = (el, frames, options = {}) => {
    if (!reduced.matches && el && el.animate) el.animate(frames, { duration: 180, easing: 'ease-out', ...options });
  };
  const announce = document.createElement('div');
  announce.className = 'motion-announcement';
  announce.setAttribute('role', 'status');
  announce.setAttribute('aria-live', 'polite');
  document.body.append(announce);
  let noticeTimer;
  function say(message) {
    announce.textContent = message;
    announce.classList.add('is-visible');
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => announce.classList.remove('is-visible'), 2600);
  }
  const progress = document.createElement('div');
  progress.className = 'navigation-progress';
  progress.setAttribute('aria-hidden', 'true');
  document.body.append(progress);
  function busy() { document.body.classList.add('is-navigating'); }
  function resetBusy() {
    document.body.classList.remove('is-navigating');
    document.querySelectorAll('form[data-motion-submitting]').forEach(form => {
      delete form.dataset.motionSubmitting;
      form.removeAttribute('aria-busy');
      form.querySelectorAll('.motion-submitting').forEach(button => {
        button.classList.remove('motion-submitting');
        button.removeAttribute('aria-disabled');
      });
    });
  }
  addEventListener('pageshow', resetBusy);
  // Indicate real navigation without fetching/replacing script-bearing Django pages.
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.download || link.target && link.target !== '_self') return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith('/staff/') || url.searchParams.has('format') || url.pathname.includes('/export')) return;
    if (url.pathname === location.pathname && url.search === location.search) return;
    busy();
    setTimeout(resetBusy, 12000);
  });
  document.addEventListener('submit', event => {
    const form = event.target;
    if (event.defaultPrevented || !(form instanceof HTMLFormElement)) return;
    if (form.dataset.motionSubmitting) { event.preventDefault(); return; }
    if (!form.checkValidity()) return;
    form.dataset.motionSubmitting = 'true';
    form.setAttribute('aria-busy', 'true');
    // Keep successful controls enabled so submitter values and CSRF are preserved.
    if (event.submitter) {
      event.submitter.classList.add('motion-submitting');
      event.submitter.setAttribute('aria-disabled', 'true');
    }
    busy();
    setTimeout(resetBusy, 15000);
  });
  // Existing row handler owns hidden/expanded; animate after that handler completes.
  document.addEventListener('click', event => {
    const button = event.target.closest('.row-toggle');
    if (!button) return;
    const row = document.getElementById(button.getAttribute('aria-controls'));
    if (row && !row.hidden) animate(row.querySelector('.event-detail-box') || row, [{ opacity: 0, transform: 'translateY(-5px)' }, { opacity: 1, transform: 'translateY(0)' }]);
  });
  document.addEventListener('toggle', event => {
    const details = event.target;
    if (details instanceof HTMLDetailsElement && details.open && main.contains(details)) {
      [...details.children].filter(el => el.tagName !== 'SUMMARY').forEach(el => animate(el, [{ opacity: 0 }, { opacity: 1 }]));
    }
  }, true);

  // Expand the actual chart/card node so listeners, tooltips and polling targets survive.
  const dialog = document.createElement('dialog');
  dialog.className = 'motion-chart-dialog';
  const bar = document.createElement('div');
  bar.className = 'motion-dialog-bar';
  const dialogTitle = document.createElement('strong');
  dialogTitle.id = 'motion-chart-title';
  const close = document.createElement('button');
  close.type = 'button'; close.className = 'btn-ghost'; close.textContent = '닫기 ×';
  bar.append(dialogTitle, close);
  dialog.append(bar);
  dialog.setAttribute('aria-labelledby', dialogTitle.id);
  document.body.append(dialog);
  let expanded = null;
  const resizeCharts = () => requestAnimationFrame(() => dispatchEvent(new Event('resize')));
  function restoreChart() {
    if (!expanded) return;
    const { card, placeholder, trigger } = expanded;
    placeholder.replaceWith(card);
    card.classList.remove('motion-expanded');
    expanded = null;
    resizeCharts();
    if (trigger.isConnected) trigger.focus({ preventScroll: true });
  }
  close.addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', restoreChart);
  dialog.addEventListener('click', event => { if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close(); } });

  const memoryKey = 'nodeverse-panel-layout-v1:' + location.pathname;
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(memoryKey) || '{}') || {}; } catch (_) { /* optional */ }
  const panelStates = new Map();
  function persist() {
    const panels = {};
    panelStates.forEach((state, card) => { panels[state.key] = { collapsed: state.collapsed, wide: card.classList.contains('motion-wide') }; });
    const orders = {};
    [...new Set([...panelStates.keys()].map(card => card.parentElement))].forEach((parent, i) => {
      orders[i] = [...parent.children].filter(el => panelStates.has(el)).map(el => panelStates.get(el).key);
    });
    try { localStorage.setItem(memoryKey, JSON.stringify({ panels, orders })); } catch (_) { /* storage may be blocked */ }
  }
  const cards = [...main.querySelectorAll('.ov-card, .viz-card, .guide-card')].filter(card => !card.closest('[data-ov-root]') && !card.parentElement.closest('.card') && card.querySelector('.ov-card-head, .chart-head, header'));
  const parents = [...new Set(cards.map(card => card.parentElement))];
  cards.forEach((card, index) => {
    const head = card.querySelector('.ov-card-head, .chart-head, header');
    const title = head.querySelector('h2, h3');
    if (!title || !head.parentElement.isSameNode(card)) return;
    const key = card.id || title.id || 'panel-' + index;
    const state = { key, collapsed: false, hidden: new Map() };
    panelStates.set(card, state);
    const tools = document.createElement('span'); tools.className = 'motion-panel-tools';
    const fold = document.createElement('button');
    fold.type = 'button'; fold.className = 'motion-tool'; fold.textContent = '−';
    fold.title = title.textContent.trim() + ' 접기'; fold.setAttribute('aria-label', fold.title); fold.setAttribute('aria-expanded', 'true');
    function collapse(value) {
      state.collapsed = value;
      [...card.children].filter(el => el !== head && el.tagName !== 'SCRIPT').forEach(el => {
        if (value) { state.hidden.set(el, el.hidden); el.hidden = true; }
        else if (state.hidden.has(el)) el.hidden = state.hidden.get(el);
      });
      if (!value) state.hidden.clear();
      card.classList.toggle('motion-collapsed', value);
      fold.textContent = value ? '+' : '−'; fold.setAttribute('aria-expanded', String(!value));
      fold.title = title.textContent.trim() + (value ? ' 펼치기' : ' 접기'); fold.setAttribute('aria-label', fold.title);
      if (!value) { resizeCharts(); animate(card, [{ opacity: .6 }, { opacity: 1 }]); }
    }
    fold.addEventListener('click', () => { collapse(!state.collapsed); persist(); });
    tools.append(fold);
    if (card.querySelector('[data-chart], .line-chart, .bar-list, .live-table, [id$="-bars"]')) {
      const zoom = document.createElement('button'); zoom.type = 'button'; zoom.className = 'motion-tool'; zoom.textContent = '⤢';
      zoom.title = title.textContent.trim() + ' 크게 보기'; zoom.setAttribute('aria-label', zoom.title);
      zoom.addEventListener('click', () => {
        if (expanded || typeof dialog.showModal !== 'function') return;
        if (state.collapsed) collapse(false);
        const placeholder = document.createElement('div'); placeholder.style.height = card.offsetHeight + 'px';
        placeholder.style.gridColumn = getComputedStyle(card).gridColumn;
        card.before(placeholder); expanded = { card, placeholder, trigger: zoom };
        dialogTitle.textContent = title.textContent.trim();
        card.classList.add('motion-expanded'); dialog.append(card); dialog.showModal();
        animate(dialog, [{ opacity: 0, transform: 'translateY(8px) scale(.985)' }, { opacity: 1, transform: 'none' }]);
        resizeCharts();
      });
      tools.prepend(zoom);
    }
    // Reorder within the same grid only; keep filters and headings in place.
    if (parents.includes(card.parentElement)) {
      for (const [direction, glyph, label] of [[-1, '↑', '앞으로 이동'], [1, '↓', '뒤로 이동']]) {
        const move = document.createElement('button'); move.type = 'button'; move.className = 'motion-tool motion-edit-control'; move.textContent = glyph; move.setAttribute('aria-label', title.textContent.trim() + ' ' + label);
        move.addEventListener('click', () => {
          const siblings = [...card.parentElement.children].filter(el => panelStates.has(el));
          const other = siblings[siblings.indexOf(card) + direction]; if (!other) return;
          if (direction < 0) other.before(card); else other.after(card);
          persist(); move.focus(); say('카드 순서를 저장했습니다');
        });
        tools.append(move);
      }
      if (card.parentElement.matches('.split-grid, .viz-grid')) {
        const width = document.createElement('button'); width.type = 'button'; width.className = 'motion-tool motion-edit-control'; width.textContent = '↔'; width.setAttribute('aria-label', title.textContent.trim() + ' 너비 전환');
        width.addEventListener('click', () => { width.setAttribute('aria-pressed', String(card.classList.toggle('motion-wide'))); persist(); resizeCharts(); });
        tools.append(width);
        width.setAttribute('aria-pressed', String(!!saved.panels?.[key]?.wide));
        card.classList.toggle('motion-wide', !!saved.panels?.[key]?.wide);
      }
    }
    head.append(tools);
    if (saved.panels?.[key]?.collapsed) collapse(true);
  });
  parents.forEach((parent, i) => {
    const order = saved.orders?.[i]; if (!Array.isArray(order)) return;
    // Insert into original card slots, preserving non-card nodes.
    const slots = [...parent.children].filter(el => panelStates.has(el));
    const byKey = new Map(slots.map(el => [panelStates.get(el).key, el]));
    const ordered = [...order.map(key => byKey.get(key)).filter(Boolean), ...slots.filter(el => !order.includes(panelStates.get(el).key))];
    const markers = slots.map(el => { const mark = document.createComment('card-slot'); el.before(mark); return mark; });
    markers.forEach((mark, index) => mark.replaceWith(ordered[index]));
  });
  const heading = main.querySelector('.ov-head');
  if (heading && cards.length && !main.querySelector('[data-ov-root]')) {
    const actions = document.createElement('div'); actions.className = 'motion-layout-actions';
    const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'btn-ghost'; edit.textContent = '배치 편집'; edit.setAttribute('aria-pressed', 'false');
    edit.addEventListener('click', () => { const on = main.classList.toggle('motion-editing'); edit.setAttribute('aria-pressed', String(on)); edit.textContent = on ? '편집 완료' : '배치 편집'; if (!on) say('화면 배치를 이 브라우저에 저장했습니다'); });
    const reset = document.createElement('button'); reset.type = 'button'; reset.className = 'btn-ghost motion-edit-control'; reset.textContent = '기본 배치';
    reset.addEventListener('click', () => { try { localStorage.removeItem(memoryKey); } catch (_) {} location.reload(); });
    actions.append(edit, reset); heading.append(actions);
  }
  // Highlight changed KPI values only. Do not animate counters or move live table rows.
  main.querySelectorAll('.kpi-value').forEach(el => {
    let previous = el.textContent;
    new MutationObserver(() => { const next = el.textContent; if (next !== previous) { previous = next; animate(el, [{ backgroundColor: 'rgba(80,130,180,.18)' }, { backgroundColor: 'transparent' }], { duration: 650 }); } }).observe(el, { childList: true, characterData: true, subtree: true });
  });
})();
