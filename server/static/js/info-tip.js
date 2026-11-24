// i 버튼(.kpi-info[data-tip]) 설명 말풍선: 버튼 위쪽에 뜸. 누르면 열고 다시 누르거나 바깥을 누르면 닫음, 마우스를 올려도 표시
(() => {
  const tip = document.createElement('div');
  tip.className = 'info-tooltip';
  tip.setAttribute('role', 'tooltip');
  tip.id = 'info-tooltip';
  tip.hidden = true;
  document.body.appendChild(tip);
  let pinned = null;

  const show = (el) => {
    tip.textContent = el.dataset.tip;
    tip.hidden = false;
    el.setAttribute('aria-describedby', tip.id);
    const r = el.getBoundingClientRect();
    const w = tip.offsetWidth;
    const left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
    // 기본은 버튼 위쪽(아래 숫자를 가리지 않게). 화면 위에 자리가 없을 때만 아래로
    let top = r.top - tip.offsetHeight - 8;
    if (top < 8) top = r.bottom + 8;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  };
  const hide = () => {
    tip.hidden = true;
    document.querySelectorAll('.kpi-info[aria-describedby]').forEach((el) => el.removeAttribute('aria-describedby'));
  };

  document.addEventListener('click', (e) => {
    const el = e.target.closest('.kpi-info[data-tip]');
    if (el) {
      e.preventDefault();
      if (pinned === el) { pinned = null; hide(); } else { pinned = el; show(el); }
      return;
    }
    if (pinned) { pinned = null; hide(); }
  });
  document.addEventListener('keydown', (e) => {
    const el = e.target.closest && e.target.closest('.kpi-info[data-tip]');
    if (el && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); el.click(); }
    if (e.key === 'Escape') { pinned = null; hide(); }
  });
  document.addEventListener('mouseover', (e) => {
    const el = e.target.closest('.kpi-info[data-tip]');
    if (el && !pinned) show(el);
  });
  document.addEventListener('mouseout', (e) => {
    const el = e.target.closest('.kpi-info[data-tip]');
    if (el && !pinned && !el.contains(e.relatedTarget)) hide();
  });
  window.addEventListener('scroll', () => { if (!tip.hidden) { pinned = null; hide(); } }, { passive: true });
})();
