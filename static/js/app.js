// ═══════════════════════════════════════════════
// Levando Email Agent – App JavaScript
// ═══════════════════════════════════════════════

// Mobile Sidebar Toggle
(function(){
  const sidebar  = document.getElementById('sidebar');
  const toggle   = document.getElementById('sidebarToggle');
  const backdrop = document.getElementById('sidebarBackdrop');
  if (!sidebar || !toggle || !backdrop) return;
  function open()  { sidebar.classList.add('open');  backdrop.classList.add('active'); document.body.style.overflow = 'hidden'; }
  function close() { sidebar.classList.remove('open'); backdrop.classList.remove('active'); document.body.style.overflow = ''; }
  toggle.addEventListener('click', open);
  backdrop.addEventListener('click', close);
  sidebar.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
    if (window.innerWidth < 992) setTimeout(close, 100);
  }));
})();

// Auto-wrap tables in scroll containers (mobile)
(function(){
  document.querySelectorAll('main.main-content table.table').forEach(tbl => {
    if (tbl.parentElement.classList.contains('table-responsive-wrap') ||
        tbl.parentElement.classList.contains('card-body')) {
      const parent = tbl.closest('.card-body');
      if (parent && !parent.classList.contains('table-responsive-wrap')) {
        parent.classList.add('table-responsive-wrap');
      }
      return;
    }
    const wrap = document.createElement('div');
    wrap.className = 'table-responsive-wrap';
    tbl.parentElement.insertBefore(wrap, tbl);
    wrap.appendChild(tbl);
  });
})();

// Global Reject Modal Handler
(function(){
  const modal   = document.getElementById('rejectModal');
  if (!modal) return;
  const form    = document.getElementById('rejectForm');
  const subjEl  = document.getElementById('rejectSubject');
  const reasonEl = document.getElementById('rejectReason');
  const bsModal = new bootstrap.Modal(modal);
  document.body.addEventListener('click', function(ev){
    const btn = ev.target.closest('[data-reject-id]');
    if (!btn) return;
    ev.preventDefault(); ev.stopPropagation();
    form.action = '/reject/' + btn.getAttribute('data-reject-id');
    subjEl.textContent = btn.getAttribute('data-reject-subject') || '';
    reasonEl.value = '';
    bsModal.show();
    setTimeout(() => reasonEl.focus(), 300);
  });
})();

// Global Snooze Modal Handler
(function(){
  const modal  = document.getElementById('snoozeModal');
  if (!modal) return;
  const form   = document.getElementById('snoozeForm');
  const subjEl = document.getElementById('snoozeSubject');
  const bsModal = new bootstrap.Modal(modal);
  document.body.addEventListener('click', function(ev){
    const btn = ev.target.closest('[data-snooze-id]');
    if (!btn) return;
    ev.preventDefault(); ev.stopPropagation();
    form.action = '/snooze/' + btn.getAttribute('data-snooze-id');
    subjEl.textContent = btn.getAttribute('data-snooze-subject') || '';
    bsModal.show();
  });
})();

// Auto-dismiss flash alerts after 5s
(function(){
  document.querySelectorAll('.alert.alert-dismissible').forEach(el => {
    setTimeout(() => {
      el.style.transition = 'opacity 0.5s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 500);
    }, 5000);
  });
})();
