/* ════════════════════════════════════════════════════════════════════════════
   EMSArena — Kurs paneli · modal "design" enhancer
   Mövcud Bootstrap modallarını (5 app) dizayn .cmodal görünüşünə salır:
   ağ başlıq + bölmə-rəngli ikon plitəsi + alt başlıq, "AI ilə doldur" düyməsi,
   bölmə-rəngli "Əlavə et". Funksionallıq SİLİNMİR — yalnız xarici görünüş
   zənginləşdirilir (forma/submit/AJAX olduğu kimi qalır). Partial-lara toxunmur.
   ════════════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  var ICONS = {
    book:   '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2V5Z"/><path d="M4 19a2 2 0 0 0 2 2h13"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>',
    clip:   '<rect x="5" y="4" width="14" height="17" rx="2.5"/><path d="M9 4V3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1M9 11h6M9 15h4"/>',
    flask:  '<path d="M9 3h6M10 3v6.5L5 18a2 2 0 0 0 1.7 3h10.6A2 2 0 0 0 19 18l-5-8.5V3M7.5 14h9"/>',
    doc:    '<path d="M14 3v5h5M7 3h8l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M9 13h6M9 17h4"/>',
    flow:   '<circle cx="5" cy="6" r="2.5"/><circle cx="19" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M5 8.5v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3M12 13.5v2"/>',
    users:  '<circle cx="9" cy="8" r="3.3"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M17 5.4a3.3 3.3 0 0 1 0 6.5M21.5 20a6.5 6.5 0 0 0-4-6"/>'
  };
  var SEC = {
    topics:      { color:'#2C5BFF', soft:'#EEF2FF', deep:'#1E40AF', icon:'book' },
    resources:   { color:'#0F766E', soft:'#E6FBF7', deep:'#0B544E', icon:'folder' },
    assignments: { color:'#B45309', soft:'#FEF3C7', deep:'#92400E', icon:'clip' },
    labs:        { color:'#7C3AED', soft:'#F2ECFE', deep:'#5B21B6', icon:'flask' },
    exams:       { color:'#0284C7', soft:'#E0F2FE', deep:'#075985', icon:'doc' },
    projects:    { color:'#BE3455', soft:'#FCE7EE', deep:'#9F1239', icon:'flow' },
    members:     { color:'#16A34A', soft:'#DCFCE7', deep:'#15803D', icon:'users' }
  };

  /* AI text — səhifə dilinə görə */
  var AI_TXT = {
    az:{ btn:'AI ilə doldur', hint:'Sahələri AI ilə doldur' },
    ru:{ btn:'Заполнить с ИИ', hint:'Заполнить поля с ИИ' },
    tr:{ btn:'AI ile doldur', hint:'Alanları AI ile doldur' },
    en:{ btn:'Fill with AI', hint:'Let AI fill the fields' }
  };

  function keyForId(id) {
    id = (id || '').toLowerCase();
    if (id.indexOf('topic') > -1) return 'topics';
    if (id.indexOf('resource') > -1) return 'resources';
    if (id.indexOf('student') > -1 || id.indexOf('group') > -1 || id.indexOf('member') > -1) return 'members';
    if (id.indexOf('assignment') > -1) return 'assignments';
    if (id.indexOf('project') > -1) return 'projects';
    if (id.indexOf('lab') > -1) return 'labs';
    if (id.indexOf('exam') > -1) return 'exams';
    return null;
  }

  function svg(icon, size) {
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[icon] || ICONS.book) + '</svg>';
  }

  function sectionLabel(key) {
    var el = document.querySelector('.snav-item[data-key="' + key + '"] .snav-label');
    return el ? el.textContent.trim() : '';
  }

  function enhance(modal, lang) {
    if (!modal || modal.dataset.emsModalReady === '1') return;
    var key = keyForId(modal.id);
    if (!key) return;
    var meta = SEC[key];
    var content = modal.querySelector('.modal-content');
    if (!content) return;
    modal.dataset.emsModalReady = '1';

    content.style.setProperty('--sec', meta.color);
    content.style.setProperty('--sec-soft', meta.soft);
    content.style.setProperty('--sec-deep', meta.deep);

    /* ── başlıq ── */
    var header = content.querySelector('.modal-header');
    if (header) {
      // rəngli fon + ağ mətn siniflərini təmizlə
      Array.prototype.slice.call(header.classList).forEach(function (c) {
        if (/^bg-/.test(c) || c === 'text-white' || c === 'text-dark') header.classList.remove(c);
      });
      header.classList.add('ems-mh');
      var close = header.querySelector('.btn-close');
      if (close) close.classList.remove('btn-close-white');

      var title = header.querySelector('.modal-title');
      if (title && !header.querySelector('.ems-mh-ic')) {
        // başlıqdakı köhnə <i> ikonu sil
        var oldI = title.querySelector('i');
        if (oldI) oldI.remove();

        var ic = document.createElement('span');
        ic.className = 'ems-mh-ic';
        ic.style.background = meta.soft;
        ic.style.color = meta.deep;
        ic.innerHTML = svg(meta.icon, 20);

        var tx = document.createElement('div');
        tx.className = 'ems-mh-tx';
        header.insertBefore(ic, title);
        header.insertBefore(tx, title);
        tx.appendChild(title);

        var lbl = sectionLabel(key);
        if (lbl) {
          var sub = document.createElement('div');
          sub.className = 'ems-mh-sub';
          sub.textContent = lbl;
          tx.appendChild(sub);
        }
      }
    }

    // Qeyd: modal daxili "AI ilə doldur" düyməsi silindi — sahə doldurma backend-i
    // yoxdur. AI-nin əsas giriş nöqtələri: sidebar "AI ilə kurs qur" + başlıq
    // "AI ilə yarat" (course_ai_drawer.js çekməcəsini açır).
  }

  function init() {
    var root = document.querySelector('.ems-cd-modals');
    if (!root) return;
    var lang = (document.documentElement.getAttribute('lang') || 'az').slice(0, 2).toLowerCase();
    Array.prototype.forEach.call(root.querySelectorAll('.modal'), function (m) { enhance(m, lang); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
