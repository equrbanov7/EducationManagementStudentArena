/* ════════════════════════════════════════════════════════════════════════════
   EMSArena — Kurs paneli · bölmə tab-bar enhancer
   Mənbə dizayn: "Kurs Paneli" (SectionNav + content pane).

   Progressive enhancement: server hər bölməni Bootstrap akkordeon kimi render
   edir (.ems-sec > .accordion-item). Bu skript onları horizontal .snav tab-bar +
   tək açıq panelə çevirir. JS yoxdursa akkordeon olduğu kimi işləyir (fallback).
   Bölmə partial-larına (5 app) TOXUNMUR — yalnız xarici davranış dəyişir.
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

  /* bölmə təsviri (dizaynın hint mətnləri) */
  var HINTS = {
    topics:      { az:'Kursun sillabusu və həftəlik strukturu', ru:'Программа и структура курса', en:'Syllabus and weekly structure', tr:'Müfredat ve haftalık yapı' },
    resources:   { az:'Mühazirələr, fayllar, video və linklər', ru:'Лекции, файлы, видео и ссылки', en:'Lectures, files, videos and links', tr:'Dersler, dosyalar, video ve bağlantılar' },
    assignments: { az:'Tələbələr üçün tapşırıqlar və təqdimatlar', ru:'Задания и сдачи для студентов', en:'Tasks and submissions for students', tr:'Öğrenciler için görevler ve teslimler' },
    labs:        { az:'Bloklar və suallarla praktiki laboratoriyalar', ru:'Практические лаборатории с блоками', en:'Practical labs with blocks and questions', tr:'Bloklar ve sorularla pratik laboratuvarlar' },
    exams:       { az:'Test və yazılı imtahanlar, nəzarət', ru:'Тесты и письменные экзамены', en:'Test and written exams, proctoring', tr:'Test ve yazılı sınavlar, gözetim' },
    projects:    { az:'Genişmiqyaslı kurs layihələri', ru:'Масштабные курсовые проекты', en:'Larger course projects', tr:'Büyük ölçekli kurs projeleri' },
    members:     { az:'Tələbələr və qruplar', ru:'Студенты и группы', en:'Students and groups', tr:'Öğrenciler ve gruplar' }
  };

  function svg(icon, size) {
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[icon] || ICONS.book) + '</svg>';
  }

  function labelOf(btn) {
    if (!btn) return '';
    var c = btn.cloneNode(true);
    Array.prototype.forEach.call(c.querySelectorAll('i, svg, .badge'), function (n) { n.remove(); });
    return (c.textContent || '').replace(/\s+/g, ' ').trim();
  }

  var PLUS = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>';

  /* bir düymənin "əlavə et" əməliyyatı olub-olmadığı (modal açan və ya exam-create) */
  function isAddBtn(b) {
    return (b.getAttribute && b.getAttribute('data-bs-toggle') === 'modal') ||
           (b.className && /js-open-course-exam-editor/.test(b.className));
  }

  /* bölmə gövdəsinin İLK uşağındakı add düymələrini tapır (siyahı düymələri yox) */
  function findAddButtons(body) {
    if (!body) return [];
    var first = body.children && body.children[0];
    if (!first) return [];
    var cand = [];
    if (first.matches && first.matches('.btn')) cand.push(first);
    if (first.querySelectorAll) Array.prototype.push.apply(cand, first.querySelectorAll('.btn'));
    var out = [], seen = {};
    cand.forEach(function (b) {
      if (!isAddBtn(b)) return;
      var k = b.getAttribute('data-bs-target') || (/js-open-course-exam-editor/.test(b.className) ? 'exam-create' : b.textContent.trim());
      if (seen[k]) return;
      seen[k] = 1;
      out.push(b);
    });
    return out;
  }

  function btnLabel(b) {
    var c = b.cloneNode(true);
    Array.prototype.forEach.call(c.querySelectorAll('i, svg'), function (n) { n.remove(); });
    return (c.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function directChildren(parent, selector) {
    return Array.prototype.filter.call(parent.children, function (el) {
      return el.matches && el.matches(selector);
    });
  }

  function forceOpenCollapse(collapse) {
    if (!collapse) return;
    collapse.classList.remove('collapse', 'collapsing');
    collapse.classList.add('show');
    collapse.removeAttribute('data-bs-parent');
    collapse.style.display = 'block';
    collapse.style.height = 'auto';
    collapse.style.overflow = 'visible';
    collapse.style.visibility = 'visible';
  }

  function init() {
    var cd = document.querySelector('.ems-cd');
    var dash = document.getElementById('courseDashboard');
    var snav = document.getElementById('emsSnav');
    if (!cd || !dash || !snav) return;

    var secs = directChildren(dash, '.ems-sec');
    if (!secs.length) return;

    var lang = (document.documentElement.getAttribute('lang') || 'az').slice(0, 2).toLowerCase();
    var data = [];

    secs.forEach(function (secEl) {
      try {
        var item = secEl.querySelector('.accordion-item');
        if (!item) return;
        var btn = item.querySelector('.accordion-button');
        var collapse = item.querySelector('.accordion-collapse');
        var badge = btn ? btn.querySelector('.badge') : null;

        // bölmə gövdəsini həmişə açıq saxla, Bootstrap collapse mexanizmindən ayır
        forceOpenCollapse(collapse);

        var body = item.querySelector('.accordion-body');
        var addButtons = [];
        try { addButtons = findAddButtons(body); } catch (e2) { addButtons = []; }

        data.push({
          el: secEl,
          key: secEl.dataset.key || '',
          color: secEl.dataset.color || '#2C5BFF',
          soft: secEl.dataset.soft || '#EEF2FF',
          deep: secEl.dataset.deep || '#1E40AF',
          icon: secEl.dataset.icon || 'book',
          label: labelOf(btn) || (secEl.dataset.key || ''),
          count: badge ? badge.textContent.trim() : '',
          addButtons: addButtons
        });
      } catch (e) { /* bir bölmə xəta versə, digərləri işləsin */ }
    });

    if (!data.length) return;

    // ── tab-bar qur ──
    var list = document.createElement('div');
    list.className = 'snav-list';
    data.forEach(function (d) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'snav-item';
      b.setAttribute('data-key', d.key);
      b.style.setProperty('--sec', d.color);
      b.style.setProperty('--sec-soft', d.soft);
      b.style.setProperty('--sec-deep', d.deep);
      b.innerHTML =
        '<span class="snav-ic">' + svg(d.icon, 17) + '</span>' +
        '<span class="snav-label"></span>' +
        (d.count !== '' ? '<span class="snav-count"></span>' : '');
      b.querySelector('.snav-label').textContent = d.label;
      if (d.count !== '') b.querySelector('.snav-count').textContent = d.count;
      b.addEventListener('click', function () { activate(d.key, true); });
      list.appendChild(b);
    });
    snav.appendChild(list);
    snav.hidden = false;

    var chead = document.getElementById('emsChead');
    if (chead) chead.hidden = false;
    var fallbackTitle = cd.querySelector('[data-ems-fallback-title]');
    if (fallbackTitle) fallbackTitle.style.display = 'none';

    cd.classList.add('ems-tabs-ready');

    var byKey = {};
    data.forEach(function (d) { byKey[d.key] = d; });
    var main = cd.querySelector('.ems-cd-main') || cd;
    var labelEl = cd.querySelector('[data-ems-active-label]');
    var hintEl = cd.querySelector('[data-ems-active-hint]');
    var cheadActions = cd.querySelector('.chead-actions');
    var aiBtn = cheadActions ? cheadActions.querySelector('[data-ems-ai]') : null;

    // add düymələrini başlığa köçürmək üçün orijinalları gizlət (yalnız müəllim/owner)
    if (cheadActions) {
      data.forEach(function (d) {
        (d.addButtons || []).forEach(function (orig) { orig.style.display = 'none'; });
      });
    }

    /* aktiv bölmənin add düymələrini başlıqda qur (bölmə rəngində) */
    function renderCheadAdds(d) {
      if (!cheadActions) return;
      try {
      Array.prototype.forEach.call(cheadActions.querySelectorAll('.ems-chead-add'), function (n) { n.remove(); });
      (d.addButtons || []).forEach(function (orig, idx) {
        var clone = document.createElement('button');
        clone.type = 'button';
        clone.className = 'btn ems-chead-add' + (idx > 0 ? ' secondary' : '');
        if (orig.getAttribute('data-bs-toggle') === 'modal' && orig.getAttribute('data-bs-target')) {
          clone.setAttribute('data-bs-toggle', 'modal');
          clone.setAttribute('data-bs-target', orig.getAttribute('data-bs-target'));
        } else {
          clone.addEventListener('click', function (e) { e.preventDefault(); orig.click(); });
        }
        clone.innerHTML = PLUS + '<span></span>';
        clone.querySelector('span').textContent = btnLabel(orig);
        cheadActions.insertBefore(clone, aiBtn || null);
      });
      } catch (e) { /* başlıq düyməsi xətası bölmənin görünməsinə mane olmasın */ }
    }

    function activate(key, fromClick) {
      var d = byKey[key];
      if (!d) return;

      data.forEach(function (x) { x.el.classList.toggle('is-active', x.key === key); });

      Array.prototype.forEach.call(list.querySelectorAll('.snav-item'), function (t) {
        t.classList.toggle('on', t.getAttribute('data-key') === key);
      });

      main.style.setProperty('--sec', d.color);
      main.style.setProperty('--sec-soft', d.soft);
      main.style.setProperty('--sec-deep', d.deep);

      renderCheadAdds(d);

      if (labelEl) labelEl.textContent = d.label;
      if (hintEl) hintEl.textContent = (HINTS[key] && (HINTS[key][lang] || HINTS[key].az)) || '';

      forceOpenCollapse(d.el.querySelector('.accordion-collapse'));

      if (fromClick) {
        try { history.replaceState(null, '', '#sec-' + key); } catch (e) { /* noop */ }
        var active = list.querySelector('.snav-item.on');
        if (active && active.scrollIntoView) active.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      }
    }

    var initKey = null;
    if (location.hash.indexOf('#sec-') === 0) initKey = location.hash.slice(5);
    if (!initKey || !byKey[initKey]) initKey = data[0].key;
    try {
      activate(initKey, false);
    } catch (e) {
      // hər ehtimala qarşı: heç olmasa ilk bölmə görünsün (hamısı gizli qalmasın)
      data[0].el.classList.add('is-active');
    }
    // təhlükəsizlik: aktiv bölmə yoxdursa ilkini göstər
    if (!cd.querySelector('.ems-sec.is-active') && data[0]) {
      data[0].el.classList.add('is-active');
    }
  }

  /* AI elementlərinin klikləri ayrıca course_ai_drawer.js tərəfindən idarə olunur. */

  function boot() { init(); }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
