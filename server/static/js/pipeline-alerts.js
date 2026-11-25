'use strict';
// Pipeline alert status (relayed from the .81 observatory by Django, which caches it for 10s).
// Runs on every staff page: keeps the sidebar badge current and shows a toast for new alerts.
// On the pipeline alerts page it also renders the full view. Review state stays in this browser only.
(() => {
  const script = document.currentScript;
  const STATUS_URL = script.dataset.statusUrl;
  const STORE = 'nodeverse-pipeline-alerts-v1';
  const page = document.getElementById('pipeline-alerts-page');
  const POLL_MS = page ? 10000 : 30000;
  const STATE_LABELS = {waiting_context: '조건 대기', parked: '재시도 보관', blocked: '적재 중단', quarantined: '격리'};
  const GUIDES = {
    waiting_context: '회원 UUID 연결과 세션 → 문제 실행 → 풀이 시도의 선행 기록을 확인하세요. 선행 기록이 저장되면 작업자가 다시 처리합니다.',
    parked: '적재 작업자 로그에서 실패 원인을 확인하고 연결·권한 문제를 해결한 뒤 승인된 재처리 도구를 사용하세요.',
    blocked: 'ID 충돌·스키마 불일치를 조사하세요. 같은 ID의 다른 내용을 덮어쓰지 말고 원본과 매핑 규칙을 수정한 뒤 재처리를 검토하세요.',
    quarantined: '수신 로그에서 격리 사유를 확인하세요. 중복 ID의 내용 충돌·필수 필드·참조·시간 규약을 수정한 뒤 다시 시험하세요.',
  };
  const SERVICES = [['collector', '수집기'], ['progress', 'Spark 진행 신호'], ['mongo', '파이프라인 MongoDB'], ['remote', '공용 MongoDB(.167)']];
  const CONNECTION = {
    unconfigured: ['관측소 연결이 설정되지 않았습니다', '서버 .env에 OBSERVATORY_KEY(파이프라인 담당에게 받은 관측소 키)를 넣고 서버를 다시 시작하세요.'],
    unauthorized: ['관측소 키가 맞지 않습니다', '서버 .env의 OBSERVATORY_KEY가 .81 관측소 키와 같은지 파이프라인 담당과 확인하세요.'],
    starting: ['관측소가 첫 데이터를 모으는 중입니다', '잠시 후 자동으로 다시 확인합니다.'],
    unavailable: ['관측소에 연결할 수 없습니다', '.81 관측소(8011) 실행 상태와 네트워크를 확인하세요. 마지막으로 받은 값은 표시하지 않습니다.'],
  };

  const store = load();
  let snapshot = null, filter = 'unread', selectedState = null, busy = false, audio = null, toastTimer = null, lastFingerprint = '';

  function load() {
    try {
      const s = JSON.parse(localStorage.getItem(STORE) || '{}');
      const list = v => new Set(Array.isArray(v) ? v.filter(x => typeof x === 'string').slice(-200) : []);
      return {read: list(s.read), archived: list(s.archived), seen: list(s.seen), initialized: s.initialized === true,
              sound: s.sound === true, desktop: s.desktop === true, mutedUntil: Number(s.mutedUntil) || 0};
    } catch { return {read: new Set(), archived: new Set(), seen: new Set(), initialized: false, sound: false, desktop: false, mutedUntil: 0}; }
  }
  function save() {
    try {
      localStorage.setItem(STORE, JSON.stringify({read: [...store.read], archived: [...store.archived], seen: [...store.seen],
        initialized: store.initialized, sound: store.sound, desktop: store.desktop, mutedUntil: store.mutedUntil}));
    } catch { /* Private mode: review state lasts for this page only. */ }
  }
  const key = e => [e.id, e.phase, e.at].join('|');
  const $ = id => document.getElementById(id);
  const el = (tag, text, cls) => { const x = document.createElement(tag); if (text != null) x.textContent = text; if (cls) x.className = cls; return x; };
  const when = v => v ? new Date(v).toLocaleString('ko-KR', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false}) : '미확인';
  const ago = n => n == null ? '미확인' : n < 60 ? `${Math.floor(n)}초` : n < 3600 ? `${Math.floor(n / 60)}분` : `${(n / 3600).toFixed(1)}시간`;
  const phaseLabel = p => p === 'resolved' ? '복구' : p === 'changed' ? '등급 변경' : '발생';

  function ingest(s) {
    const events = s.incidents || [];
    const current = new Set(events.map(key));
    // Keep bookkeeping bounded to what the observatory still reports (its latest 100 events).
    for (const set of [store.read, store.archived, store.seen]) for (const k of [...set]) if (!current.has(k)) set.delete(k);
    const fresh = events.filter(e => !store.seen.has(key(e)));
    fresh.forEach(e => store.seen.add(key(e)));
    if (store.initialized) notify(fresh);
    store.initialized = true;
    save();
  }
  const unread = () => (snapshot?.incidents || []).filter(e => !store.read.has(key(e)));

  function badge() {
    const b = $('pipeline-alert-badge');
    if (!b) return;
    const ok = snapshot?.state === 'ok', count = ok ? unread().length : 0, errors = ok && (snapshot.alerts || []).some(a => a.level === 'error');
    b.hidden = !ok || (count === 0 && !(snapshot.alerts || []).length);
    b.textContent = count > 99 ? '99+' : String(count || (snapshot?.alerts || []).length);
    b.className = 'nav-alert-badge ' + (errors ? 'error' : 'warning');
    b.closest('a').title = ok ? `파이프라인 알림 · 현재 경고 ${(snapshot.alerts || []).length}개 · 미확인 ${count}개` : '파이프라인 알림 · 관측소 연결 확인 필요';
  }

  function toast(message) {
    const t = $('pipeline-toast');
    if (!t) return;
    t.replaceChildren(el('strong', '파이프라인 알림'), el('span', message));
    const link = el('a', '보기', 'pipeline-toast-link'); link.href = script.dataset.pageUrl; t.append(link);
    t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 9000);
  }
  function beep() {
    if (!store.sound) return;
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext; audio = audio || new Ctx();
      if (audio.state !== 'running') return; // Browsers allow sound only after a click on this page.
      const osc = audio.createOscillator(), gain = audio.createGain(), t = audio.currentTime;
      osc.frequency.value = 660; gain.gain.setValueAtTime(.08, t); gain.gain.exponentialRampToValueAtTime(.001, t + .3);
      osc.connect(gain); gain.connect(audio.destination); osc.start(t); osc.stop(t + .3);
    } catch { /* No audio support. */ }
  }
  function notify(events, test = false) {
    if (!events.length || (!test && store.mutedUntil > Date.now())) return;
    const last = events[events.length - 1];
    const message = `${test ? '[시험] ' : ''}${phaseLabel(last.phase)} · ${last.title}${events.length > 1 ? ` 외 ${events.length - 1}건` : ''}`;
    toast(message); beep();
    if (store.desktop && 'Notification' in window && Notification.permission === 'granted') {
      try { const n = new Notification('NODEVERSE 파이프라인', {body: message, tag: 'nodeverse-pipeline', silent: true}); setTimeout(() => n.close(), 10000); } catch { /* ignore */ }
    }
  }

  // ---------- full page ----------
  function renderPage() {
    const s = snapshot, ok = s?.state === 'ok';
    const alerts = ok ? s.alerts : [], errors = alerts.filter(a => a.level === 'error').length;
    const banner = $('pa-banner');
    if (!ok) {
      const [title, detail] = CONNECTION[s?.state] || CONNECTION.unavailable;
      banner.className = 'pa-banner error'; $('pa-banner-title').textContent = title; $('pa-banner-detail').textContent = detail;
    } else {
      const stale = (s.snapshot_age_s || 0) > 30 || !s.sampler_ok;
      banner.className = 'pa-banner ' + (errors || stale ? 'error' : alerts.length ? 'warning' : 'ok');
      $('pa-banner-title').textContent = stale ? '관측값이 늦어지고 있습니다' : errors ? '확인이 필요한 경고가 있습니다' : alerts.length ? '주의 항목이 있습니다' : '파이프라인이 정상적으로 응답하고 있습니다';
      $('pa-banner-detail').textContent = stale ? '관측소의 마지막 표본이 30초 넘게 지났습니다. .81 관측소 상태를 확인하세요.'
        : alerts.length ? (alerts.find(a => a.level === 'error') || alerts[0]).detail : '현재 활성 경고가 없습니다. 새 경고가 생기면 관리자 화면 어디에서든 알려드립니다.';
    }
    $('pa-updated').textContent = ok ? `관측 ${when(s.at)}` : s?.fetched_at ? `확인 ${when(s.fetched_at * 1000)}` : '';
    $('pa-errors').textContent = ok ? String(errors) : '—';
    $('pa-warnings').textContent = ok ? String(alerts.length - errors) : '—';
    $('pa-unread').textContent = ok ? String(unread().length) : '—';
    const counts = ok ? s.queue.counts : null;
    $('pa-attention').textContent = counts ? String(Object.keys(STATE_LABELS).reduce((n, k) => n + (counts[k] || 0), 0)) : '—';
    settings();
    // Rebuild the lists only when their content changed, so buttons do not vanish under the pointer every poll.
    const fingerprint = JSON.stringify([s?.state, ok && [s.alerts, s.incidents, s.services, s.queue, s.queries, s.alerts_persistent],
      [...store.read], [...store.archived], filter, selectedState]);
    if (fingerprint === lastFingerprint) return;
    lastFingerprint = fingerprint;
    services(ok); active(ok); queue(ok, counts); history(ok);
  }
  function services(ok) {
    const host = $('pa-services'); host.replaceChildren();
    for (const [name, label] of SERVICES) {
      const state = ok ? snapshot.services[name] : 'unknown';
      const kind = state === 'ok' ? 'ok' : state === 'unconfigured' || state === 'unknown' ? 'unknown' : state === 'stale' ? 'warning' : 'error';
      const text = {ok: '정상', unknown: '미확인', warning: '지연', error: '응답 실패'}[kind] + (state === 'unconfigured' ? ' (미설정)' : '');
      const item = el('div', null, 'pa-service ' + kind); item.append(el('span', label), el('strong', text)); host.append(item);
    }
    if (ok && snapshot.queries.length) {
      const running = snapshot.queries.filter(q => q.active).length;
      const item = el('div', null, 'pa-service ' + (running === snapshot.queries.length ? 'ok' : 'error'));
      item.append(el('span', 'Spark 쿼리'), el('strong', `${running} / ${snapshot.queries.length} 실행 중`)); host.append(item);
    }
  }
  function active(ok) {
    const host = $('pa-active'); host.replaceChildren();
    if (!ok) { host.append(el('p', '관측소에 연결되면 표시합니다.', 'empty')); return; }
    if (!snapshot.alerts.length) { host.append(el('p', '현재 활성 경고가 없습니다.', 'empty')); return; }
    const seenAt = a => { const t = Date.parse(a.first_seen || ''); return Number.isNaN(t) ? -Infinity : t; };
    const newestFirst = [...snapshot.alerts].sort((x, y) => seenAt(y) - seenAt(x));  // 처음 발생 시각 최신순, 시각 없는 경고는 맨 뒤
    for (const a of newestFirst) {
      const row = el('article', null, 'pa-alert ' + a.level);
      const head = el('div', null, 'pa-alert-head');
      head.append(el('span', a.level === 'error' ? '오류' : '주의', 'pa-level ' + a.level), el('strong', a.title));
      row.append(head, el('p', a.detail), el('small', `처음 발생 ${when(a.first_seen)}`, 'muted'));
      host.append(row);
    }
  }
  function queue(ok, counts) {
    const host = $('pa-queue'); host.replaceChildren();
    if (!counts) { host.append(el('p', ok ? '파이프라인 대기열 건수를 확인할 수 없습니다. 0건이라는 뜻이 아닙니다.' : '관측소에 연결되면 표시합니다.', 'empty')); return; }
    for (const [state, label] of Object.entries(STATE_LABELS)) {
      const b = el('button', null, 'pa-queue-item' + ((counts[state] || 0) ? ' has' : ''));
      b.type = 'button'; b.setAttribute('aria-pressed', String(selectedState === state));
      b.append(el('span', label), el('strong', `${counts[state] || 0}건`));
      b.onclick = () => { selectedState = selectedState === state ? null : state; renderPage(); records(); };
      host.append(b);
    }
    const ages = el('p', `처리 대기 중 가장 오래된 기록 ${ago(snapshot.queue.oldest_due_age_s)} · 조건 대기 중 가장 오래된 기록 ${ago(snapshot.queue.oldest_context_age_s)}`, 'muted pa-ages');
    host.append(ages);
  }
  async function records() {
    const host = $('pa-records'); host.replaceChildren();
    if (!selectedState) return;
    const box = el('div', null, 'pa-records');
    const loading = el('p', '불러오는 중…', 'muted');
    box.append(el('h3', `${STATE_LABELS[selectedState]} · 권장 조치`), el('p', GUIDES[selectedState]), loading);
    host.append(box);
    try {
      const r = await fetch(`${page.dataset.attentionUrl}?state=${encodeURIComponent(selectedState)}`, {cache: 'no-store', credentials: 'same-origin'});
      const data = await r.json();
      loading.remove();
      if (data.state !== 'ok') { box.append(el('p', data.state === 'index_required' ? '관측소의 점검용 인덱스가 아직 준비되지 않았습니다. 파이프라인 담당에게 확인하세요.' : '사유 표본을 불러오지 못했습니다.', 'muted')); return; }
      if (!data.records.length) { box.append(el('p', '해당 상태의 기록이 없습니다.', 'muted')); return; }
      const wrap = el('div', null, 'table-scroll'), table = el('table'), head = el('tr');
      for (const h of ['참조', '사유', '시도', '원격 원본', '대기열 진입', '마지막 갱신']) head.append(el('th', h));
      const thead = el('thead'); thead.append(head); const tbody = el('tbody');
      for (const row of data.records) {
        const tr = el('tr');
        for (const v of [row.reference, row.reason_label, row.attempts ?? '미확인', row.archive_stored === true ? '저장됨' : row.archive_stored === false ? '미저장' : '정보 없음', when(row.queued_at), when(row.updated_at)]) tr.append(el('td', String(v)));
        tbody.append(tr);
      }
      table.append(thead, tbody); wrap.append(table); box.append(wrap);
      if (data.more) box.append(el('p', '표본은 최대 20건입니다. 더 많은 기록이 있습니다.', 'muted'));
    } catch { loading.textContent = '사유 표본을 불러오지 못했습니다.'; if (!loading.isConnected) box.append(loading); }
  }
  function history(ok) {
    const host = $('pa-history'); host.replaceChildren();
    document.querySelectorAll('.pa-filters button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.filter === filter)));
    if (!ok) { host.append(el('p', '관측소에 연결되면 표시합니다.', 'empty')); return; }
    const activeIds = new Set(snapshot.alerts.map(a => a.id));
    const rows = snapshot.incidents.filter(e => filter === 'archived' ? store.archived.has(key(e))
      : !store.archived.has(key(e)) && (filter === 'all' || !store.read.has(key(e))));
    if (!rows.length) { host.append(el('p', filter === 'unread' ? '미확인 알림이 없습니다.' : '해당하는 알림이 없습니다.', 'empty')); return; }
    if (!snapshot.alerts_persistent) host.append(el('p', '관측소가 이력을 저장하지 못하고 있습니다. 관측소를 다시 시작하면 이력이 사라질 수 있습니다.', 'notice'));
    for (const e of rows) {
      const k = key(e), read = store.read.has(k);
      const row = el('div', null, `pa-event ${e.phase === 'resolved' ? 'resolved' : e.level}${read ? ' is-read' : ''}`);
      const text = el('div');
      text.append(el('strong', `${phaseLabel(e.phase)} · ${e.title}`), el('p', e.detail),
        el('small', `${when(e.at)} · ${activeIds.has(e.id) && e.phase !== 'resolved' ? '현재 문제 지속' : '현재 활성 아님'} · ${read ? '확인함' : '미확인'}`, 'muted'));
      const actions = el('div', null, 'pa-event-actions');
      const toggle = el('button', read ? '확인 취소' : '확인', 'btn secondary'); toggle.type = 'button';
      toggle.onclick = () => { if (read) { store.read.delete(k); store.archived.delete(k); } else store.read.add(k); save(); badge(); renderPage(); };
      actions.append(toggle);
      if (read) {
        const hide = el('button', store.archived.has(k) ? '다시 표시' : '숨기기', 'btn secondary'); hide.type = 'button';
        hide.onclick = () => { store.archived.has(k) ? store.archived.delete(k) : store.archived.add(k); save(); renderPage(); };
        actions.append(hide);
      }
      row.append(text, actions); host.append(row);
    }
  }
  function settings() {
    $('pa-sound').textContent = store.sound ? '소리 끄기' : '소리 켜기'; $('pa-sound').setAttribute('aria-pressed', String(store.sound));
    $('pa-desktop').textContent = store.desktop ? '브라우저 알림 끄기' : '브라우저 알림 켜기'; $('pa-desktop').setAttribute('aria-pressed', String(store.desktop));
    const muted = store.mutedUntil > Date.now();
    $('pa-mute').textContent = muted ? '알림 다시 켜기' : '15분 알림 끄기'; $('pa-mute').setAttribute('aria-pressed', String(muted));
  }
  function bindPage() {
    const status = msg => { $('pa-setting-status').textContent = msg; };
    $('pa-refresh').onclick = () => poll();
    document.querySelectorAll('.pa-filters button').forEach(b => { b.onclick = () => { filter = b.dataset.filter; renderPage(); }; });
    $('pa-read-all').onclick = () => { unread().forEach(e => store.read.add(key(e))); save(); badge(); renderPage(); };
    $('pa-archive-read').onclick = () => { store.read.forEach(k => store.archived.add(k)); save(); renderPage(); };
    $('pa-sound').onclick = async () => {
      store.sound = !store.sound;
      if (store.sound) { try { const Ctx = window.AudioContext || window.webkitAudioContext; audio = audio || new Ctx(); await audio.resume(); } catch { store.sound = false; status('이 브라우저에서는 소리를 쓸 수 없습니다.'); } }
      save(); settings(); if (store.sound) status('소리 알림을 켰습니다. 다른 화면으로 이동하면 그 화면을 한 번 클릭한 뒤부터 소리가 납니다.');
    };
    $('pa-desktop').onclick = async () => {
      if (store.desktop) { store.desktop = false; save(); settings(); status('브라우저 알림을 껐습니다.'); return; }
      if (!window.isSecureContext || !('Notification' in window)) { status('브라우저 알림은 HTTPS나 localhost 주소에서만 쓸 수 있습니다. 화면 알림은 계속 동작합니다.'); return; }
      const result = await Notification.requestPermission();
      store.desktop = result === 'granted'; save(); settings();
      status(store.desktop ? '브라우저 알림을 켰습니다.' : '브라우저 알림 권한이 허용되지 않았습니다. 화면 알림은 계속 동작합니다.');
    };
    $('pa-mute').onclick = () => {
      store.mutedUntil = store.mutedUntil > Date.now() ? 0 : Date.now() + 15 * 60000; save(); settings();
      status(store.mutedUntil ? '15분 동안 팝업·소리·브라우저 알림을 끕니다. 경고 수집과 이력은 계속됩니다.' : '알림을 다시 켰습니다.');
    };
    $('pa-test').onclick = () => { notify([{phase: 'opened', title: '시험 알림 · 실제 파이프라인에는 영향 없음'}], true); status('시험 알림을 보냈습니다. 이력에는 남지 않습니다.'); };
  }

  async function poll() {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const r = await fetch(STATUS_URL, {cache: 'no-store', credentials: 'same-origin'});
      snapshot = r.ok ? await r.json() : {state: 'unavailable'};
    } catch { snapshot = {state: 'unavailable'}; }
    busy = false;
    if (snapshot.state === 'ok') ingest(snapshot);
    badge();
    if (page) renderPage();
  }
  if (page) bindPage();
  poll();
  setInterval(poll, POLL_MS);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
})();
