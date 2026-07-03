/* ════════════════════════════════════════════════════════════════════════════
   EMSArena — Kurs paneli · AI köməkçi çekməcəsi (dizayn: course-ai.jsx)
   "AI ilə qur / AI ilə yarat" düyməsi (data-ems-ai) bu çekməcəni açır — köhnə
   chatbot deyil. Vizual planlayıcı: prompt → generating → addım-addım/tam plan
   → done. Qeyd: real generasiya backend tələb edir; bu, dizayna uyğun UI-dir,
   təkliflər istifadəçi tərəfindən əl ilə əlavə oluna bilər.
   ════════════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  var I = {
    spark: 'M12 3l1.8 4.9L19 9.7l-5.2 1.8L12 16l-1.8-4.5L5 9.7l5.2-1.8L12 3Z',
    x: 'M18 6 6 18M6 6l12 12',
    check: 'M20 6 9 17l-5-5',
    flow: '',
    chev: 'm6 9 6 6 6-6',
    chevR: 'm9 6 6 6-6 6',
    retry: 'M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5',
    back: 'M19 12H5M11 6l-6 6 6 6',
    info: 'M12 11v5M12 8h.01'
  };
  function ic(path, size, sw) {
    return '<svg width="' + (size || 16) + '" height="' + (size || 16) + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="' + (sw || 2) + '" stroke-linecap="round" stroke-linejoin="round">' + path + '</svg>';
  }
  var SEC_ICON = {
    topics: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2V5Z"/><path d="M4 19a2 2 0 0 0 2 2h13"/>',
    resources: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>',
    assignments: '<rect x="5" y="4" width="14" height="17" rx="2.5"/><path d="M9 4V3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1M9 11h6M9 15h4"/>',
    labs: '<path d="M9 3h6M10 3v6.5L5 18a2 2 0 0 0 1.7 3h10.6A2 2 0 0 0 19 18l-5-8.5V3M7.5 14h9"/>',
    exams: '<path d="M14 3v5h5M7 3h8l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/>',
    members: '<circle cx="9" cy="8" r="3.3"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M17 5.4a3.3 3.3 0 0 1 0 6.5M21.5 20a6.5 6.5 0 0 0-4-6"/>'
  };
  var SEC = {
    topics:      { color:'#2C5BFF', soft:'#EEF2FF', deep:'#1E40AF' },
    resources:   { color:'#0F766E', soft:'#E6FBF7', deep:'#0B544E' },
    assignments: { color:'#B45309', soft:'#FEF3C7', deep:'#92400E' },
    labs:        { color:'#7C3AED', soft:'#F2ECFE', deep:'#5B21B6' },
    exams:       { color:'#0284C7', soft:'#E0F2FE', deep:'#075985' },
    members:     { color:'#16A34A', soft:'#DCFCE7', deep:'#15803D' }
  };
  var ORDER = ['topics', 'resources', 'assignments', 'labs', 'exams', 'members'];

  // dil
  var L = (document.documentElement.getAttribute('lang') || 'az').slice(0, 2).toLowerCase();
  function pick(o) { return o[L] || o.az || o.en; }

  var T = {
    title: { az:gettext('AI Kurs Köməkçisi'), ru:'AI помощник курса', tr:gettext('AI Kurs Asistanı'), en:'AI Course Assistant' },
    sub: { az:gettext('Hər addımı siz təsdiqləyirsiniz'), ru:'Вы подтверждаете каждый шаг', tr:gettext('Her adımı siz onaylarsınız'), en:'You approve every step' },
    mStep: { az:gettext('Addım-addım'), ru:'Пошагово', tr:gettext('Adım adım'), en:'Step by step' },
    mPlan: { az:'Tam plan', ru:'Весь план', tr:'Tam plan', en:'Full plan' },
    promptLbl: { az:gettext('Hansı kursu qurmaq istəyirsiniz?'), ru:'Какой курс построить?', tr:'Hangi kursu kurmak istersiniz?', en:'Which course do you want to build?' },
    promptPh: { az:gettext('Məs: “Veb texnologiyaları, 2-ci kurs, 14 həftə. Praktiki yönümlü.”'), ru:'Напр: «Веб-технологии, 2 курс, 14 недель»', tr:gettext('Örn: “Web teknolojileri, 2. sınıf, 14 hafta”'), en:'e.g. “Web technologies, 2nd year, 14 weeks”' },
    examples: { az:gettext('NÜMUNƏLƏR'), ru:'ПРИМЕРЫ', tr:gettext('ÖRNEKLER'), en:'EXAMPLES' },
    note: { az:gettext('AI mövzulardan tutmuş qruplara kimi hər şeyi təklif edir. Heç nə avtomatik tətbiq olunmur — hər addımı siz təsdiqləyirsiniz.'), ru:'ИИ предложит всё — от тем до групп. Ничего не применяется без вашего подтверждения.', tr:gettext('AI konulardan gruplara kadar her şeyi önerir. Hiçbir şey otomatik uygulanmaz.'), en:'AI proposes everything from topics to groups. Nothing is applied without your approval.' },
    generate: { az:'Yarat', ru:'Создать', tr:gettext('Oluştur'), en:'Generate' },
    genT: { az:gettext('AI kursu hazırlayır…'), ru:'ИИ готовит курс…', tr:gettext('AI kursu hazırlıyor…'), en:'AI is preparing the course…' },
    genS: { az:gettext('Sillabus, resurslar və tapşırıqlar planlanır'), ru:'Планируются программа, ресурсы и задания', tr:gettext('Müfredat, kaynaklar ve görevler planlanıyor'), en:'Planning syllabus, resources and tasks' },
    approve: { az:gettext('Təsdiqlə və davam et'), ru:'Подтвердить и далее', tr:'Onayla ve devam et', en:'Approve and continue' },
    skip: { az:gettext('Keç'), ru:'Пропустить', tr:'Atla', en:'Skip' },
    applied: { az:gettext('Təsdiqləndi'), ru:'Подтверждено', tr:gettext('Onaylandı'), en:'Approved' },
    planReady: { az:gettext('Plan hazırdır'), ru:'План готов', tr:gettext('Plan hazır'), en:'Plan ready' },
    planReadyS: { az:gettext('element təklif olunur'), ru:'предложенных элементов', tr:gettext('önerilen öğe'), en:'items suggested' },
    applyAll: { az:gettext('Hamısını qəbul et'), ru:'Принять всё', tr:'Hepsini uygula', en:'Accept all' },
    stepOf: { az:gettext('Addım'), ru:'Шаг', tr:gettext('Adım'), en:'Step' },
    confirmQ: { az:gettext('aşağıdakıları təsdiqləyim?'), ru:'подтвердить ниже?', tr:gettext('aşağıdakileri onaylayayım mı?'), en:'approve the items below?' },
    doneT: { az:gettext('Plan hazırdır 🎓'), ru:'План готов 🎓', tr:gettext('Plan hazır 🎓'), en:'Plan ready 🎓' },
    doneS: { az:gettext('AI təklifləri seçdiniz. İndi bölmələrdən “Əlavə et” ilə onları kursa daxil edə bilərsiniz.'), ru:'Вы выбрали предложения ИИ. Теперь добавьте их через «Добавить».', tr:gettext('AI önerilerini seçtiniz. Şimdi “Ekle” ile kursa ekleyin.'), en:'You selected the AI suggestions. Now add them to the course via the section “Add” buttons.' },
    sections: { az:gettext('bölmə'), ru:'разделов', tr:gettext('bölüm'), en:'sections' },
    items: { az:'element', ru:'элементов', tr:gettext('öğe'), en:'items' },
    viewCourse: { az:gettext('Kursa qayıt'), ru:'К курсу', tr:gettext('Kursa dön'), en:'Back to course' },
    secLabel: {
      topics:{az:gettext('Mövzular'),ru:'Темы',tr:'Konular',en:'Topics'},
      resources:{az:'Resurslar',ru:'Ресурсы',tr:'Kaynaklar',en:'Resources'},
      assignments:{az:gettext('Sərbəst işlər'),ru:'Задания',tr:gettext('Ödevler'),en:'Assignments'},
      labs:{az:gettext('Lab işləri'),ru:'Лабораторные',tr:'Laboratuvarlar',en:'Labs'},
      exams:{az:gettext('İmtahanlar'),ru:'Экзамены',tr:gettext('Sınavlar'),en:'Exams'},
      members:{az:gettext('Üzvlər'),ru:'Участники',tr:gettext('Üyeler'),en:'Members'}
    }
  };

  var EXAMPLES = {
    az: [gettext('Veb texnologiyaları · 2-ci kurs · 14 həftə'), gettext('Verilənlər bazası (SQL) · praktiki'), gettext('Python proqramlaşdırma · başlanğıc')],
    ru: ['Веб-технологии · 2 курс · 14 недель', 'Базы данных (SQL) · практика', 'Python · начинающие'],
    tr: [gettext('Web teknolojileri · 2. sınıf · 14 hafta'), gettext('Veritabanı (SQL) · pratik'), gettext('Python · başlangıç')],
    en: ['Web technologies · 2nd year · 14 weeks', 'Databases (SQL) · practical', 'Python · beginner']
  };

  var PLAN = {
    topics: { count:8, label:{az:gettext('8 mövzu (14 həftəlik sillabus)'),ru:'8 тем (14 недель)',tr:'8 konu (14 hafta)',en:'8 topics (14-week syllabus)'}, items:[
      {t:gettext('Giriş: veb texnologiyalarına baxış'), s:gettext('1-ci həftə')},
      {t:gettext('HTML5 — semantik struktur və formalar'), s:gettext('2–3-cü həftə')},
      {t:gettext('CSS əsasları: seçicilər və qutu modeli'), s:gettext('4-cü həftə')},
      {t:gettext('Flexbox və Grid ilə layout'), s:gettext('5–6-cı həftə')},
      {t:gettext('Responsiv dizayn və media-sorğular'), s:gettext('7-ci həftə')},
      {t:gettext('JavaScript əsasları'), s:gettext('8–10-cu həftə')},
      {t:gettext('DOM manipulyasiyası və hadisələr'), s:gettext('11–12-ci həftə')},
      {t:gettext('Fetch API və əsas backend əlaqəsi'), s:gettext('13–14-cü həftə')}
    ]},
    resources: { count:5, label:{az:gettext('5 resurs təklifi'),ru:'5 ресурсов',tr:'5 kaynak',en:'5 resources'}, items:[
      {t:gettext('MDN Web Docs — HTML referansı'), s:'Link'},
      {t:gettext('Flexbox Froggy — interaktiv məşq'), s:'Link'},
      {t:gettext('Mühazirə slaydları — CSS layout'), s:'PDF'},
      {t:gettext('Video: JavaScript 100 dəqiqədə'), s:'Video'},
      {t:gettext('Nümunə kod deposu (starter)'), s:'Link'}
    ]},
    assignments: { count:3, label:{az:gettext('3 sərbəst iş'),ru:'3 задания',tr:gettext('3 ödev'),en:'3 assignments'}, items:[
      {t:gettext('Şəxsi portfolio (HTML + CSS)'), s:gettext('Fərdi · 100 xal')},
      {t:'Responsiv menyu komponenti', s:gettext('Fərdi · 50 xal')},
      {t:'JavaScript kalkulyator', s:gettext('Cüt iş · 80 xal')}
    ]},
    labs: { count:1, label:{az:'1 lab (3 blok, 9 sual)',ru:'1 лаб. (3 блока)',tr:'1 lab (3 blok)',en:'1 lab (3 blocks, 9 q.)'}, items:[
      {t:'Lab 1 — Semantik HTML auditi', s:'3 blok · 9 sual · 100 xal'},
      {t:'Blok A — Struktur', s:'3 sual', muted:true},
      {t:gettext('Blok B — Əlçatanlıq (a11y)'), s:'3 sual', muted:true},
      {t:'Blok C — Formalar', s:'3 sual', muted:true}
    ]},
    exams: { count:1, label:{az:'1 imtahan (Midterm, 6 sual)',ru:'1 экзамен',tr:gettext('1 sınav'),en:'1 exam (Midterm)'}, items:[
      {t:'HTML/CSS Midterm', s:gettext('Test · 6 sual · 60 dəq')},
      {t:gettext('Semantik etiketlərin rolu?'), s:gettext('Çoxseçimli'), muted:true},
      {t:gettext('Box-model qatları?'), s:gettext('Çoxseçimli'), muted:true},
      {t:gettext('Flex vs Grid — fərq?'), s:gettext('Çoxseçimli'), muted:true}
    ]},
    members: { count:2, label:{az:gettext('2 qrup təyini'),ru:'2 группы',tr:'2 grup',en:'2 groups'}, items:[
      {t:'Veb-2026-A qrupu', s:gettext('24 tələbə')},
      {t:'Veb-2026-B qrupu', s:gettext('21 tələbə')}
    ]}
  };

  function previewHTML(key) {
    var s = SEC[key], n = 0, html = '<div class="aid-preview" style="--sc:' + s.color + ';--sc-soft:' + s.soft + '">';
    PLAN[key].items.forEach(function (it) {
      if (it.muted) {
        html += '<div class="aid-pli muted"><span class="dot">•</span><span><span class="ps">' + esc(it.t) + '</span> · <span class="ps">' + esc(it.s) + '</span></span></div>';
      } else {
        n++;
        html += '<div class="aid-pli"><span class="pn">' + n + '</span><span><b>' + esc(it.t) + '</b>' + (it.s ? ' · <span class="ps">' + esc(it.s) + '</span>' : '') + '</span></div>';
      }
    });
    return html + '</div>';
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]; }); }

  // ───────────────────────── drawer state + render ─────────────────────────
  var root = null, state = null;

  function close() {
    if (!root) return;
    root.classList.remove('open');
    setTimeout(function () { if (root) { root.remove(); root = null; } }, 220);
    document.body.style.overflow = '';
  }

  function open() {
    if (root) return;
    state = { mode: 'step', phase: 'prompt', prompt: '', status: {}, included: {}, openSec: 'topics' };
    ORDER.forEach(function (k) { state.included[k] = true; });
    root = document.createElement('div');
    root.className = 'ems-ai-root';
    root.innerHTML = '<div class="ai-scrim"></div><aside class="ai-drawer" role="dialog" aria-label="AI"></aside>';
    document.body.appendChild(root);
    root.querySelector('.ai-scrim').addEventListener('click', close);
    document.body.style.overflow = 'hidden';
    requestAnimationFrame(function () { root.classList.add('open'); });
    render();
  }

  function setMode(m) { state.mode = m; render(); }

  function curStepKey() {
    for (var i = 0; i < ORDER.length; i++) { if (!state.status[ORDER[i]]) return ORDER[i]; }
    return null;
  }

  function render() {
    if (!root) return;
    var d = root.querySelector('.ai-drawer');
    var head = '<div class="aid-head"><div class="aid-head-top">' +
      '<span class="aid-spark">' + ic(I.spark, 20, 1.9) + '</span>' +
      '<div><div class="aid-title">' + esc(pick(T.title)) + '</div><div class="aid-sub">EMSArena · ' + esc(pick(T.sub)) + '</div></div>' +
      '<button class="aid-x" data-act="close">' + ic(I.x, 19) + '</button></div>';
    if (state.phase !== 'done') {
      head += '<div class="aid-modes">' +
        '<button class="' + (state.mode === 'step' ? 'on' : '') + '" data-act="mode" data-v="step">' + esc(pick(T.mStep)) + '</button>' +
        '<button class="' + (state.mode === 'plan' ? 'on' : '') + '" data-act="mode" data-v="plan">' + esc(pick(T.mPlan)) + '</button></div>';
    }
    head += '</div>';

    var body = '<div class="aid-body">' + renderBody() + '</div>';
    var foot = renderFoot();
    d.innerHTML = head + body + foot;
    bind(d);
  }

  function renderBody() {
    if (state.phase === 'prompt') {
      var chips = (EXAMPLES[L] || EXAMPLES.az).map(function (ex) {
        return '<button class="aid-chip" data-act="ex" data-v="' + esc(ex) + '">' + esc(ex) + '</button>';
      }).join('');
      return '<div class="aid-prompt-lbl">' + esc(pick(T.promptLbl)) + '</div>' +
        '<textarea class="aid-ta" data-el="prompt" placeholder="' + esc(pick(T.promptPh)) + '">' + esc(state.prompt) + '</textarea>' +
        '<div class="aid-ex"><div class="aid-ex-h">' + esc(pick(T.examples)) + '</div><div class="aid-ex-chips">' + chips + '</div></div>' +
        '<div class="aid-note">' + ic(I.info, 15) + '<span>' + esc(pick(T.note)) + '</span></div>';
    }
    if (state.phase === 'generating') {
      var sh = [88, 72, 94, 64].map(function (w) { return '<div class="aid-shimmer" style="width:' + w + '%"></div>'; }).join('');
      return '<div class="aid-gen"><div class="aid-gen-orb">' + ic(I.spark, 26, 1.9) + '</div>' +
        '<div><div class="aid-gen-t">' + esc(pick(T.genT)) + '</div><div class="aid-gen-s">' + esc(pick(T.genS)) + '</div></div>' +
        '<div class="aid-gen-bars">' + sh + '</div></div>';
    }
    if (state.phase === 'review' && state.mode === 'step') return renderStep();
    if (state.phase === 'review' && state.mode === 'plan') return renderPlan();
    if (state.phase === 'done') return renderDone();
    return '';
  }

  function renderStep() {
    var cur = curStepKey();
    var html = '<div class="aid-steplist">';
    ORDER.forEach(function (key, i) {
      var s = SEC[key], st = state.status[key], isCur = key === cur;
      var cls = st === 'approved' ? 'aid-stepc done' : (st === 'skipped' ? 'aid-stepc dim' : (isCur ? 'aid-stepc active' : 'aid-stepc dim'));
      html += '<div class="' + cls + '" style="--sc:' + s.color + ';--sc-soft:' + s.soft + '">' +
        '<div class="aid-stepc-h"><span class="aid-stepc-n">' + (st === 'approved' ? ic(I.check, 14, 3) : (i + 1)) + '</span>' +
        '<div class="aid-stepc-tx"><div class="aid-stepc-t">' + esc(pick(T.secLabel[key])) + '</div><div class="aid-stepc-s">' + esc(pick(PLAN[key].label)) + '</div></div>' +
        (st === 'approved' ? '<span class="aid-stepc-badge ok">' + esc(pick(T.applied)) + '</span>' :
          st === 'skipped' ? '<span class="aid-stepc-badge">' + esc(pick(T.skip)) + '</span>' :
            (!isCur ? '<span class="aid-stepc-badge">' + PLAN[key].count + '</span>' : '')) + '</div>';
      if (isCur) {
        html += '<div class="aid-stepc-body"><div class="aid-step-q">' + esc(pick(T.stepOf)) + ' ' + (i + 1) + ' / ' + ORDER.length + ' — ' + esc(pick(T.confirmQ)) + '</div>' +
          previewHTML(key) +
          '<div class="aid-stepc-acts">' +
          '<button class="aid-btn go" style="--sec:' + s.color + '" data-act="approve" data-v="' + key + '">' + ic(I.check, 14, 3) + ' ' + esc(pick(T.approve)) + '</button>' +
          '<button class="aid-btn ghost" data-act="skip" data-v="' + key + '">' + esc(pick(T.skip)) + '</button></div></div>';
      }
      html += '</div>';
    });
    return html + '</div>';
  }

  function renderPlan() {
    var total = ORDER.reduce(function (n, k) { return n + (state.included[k] ? PLAN[k].count : 0); }, 0);
    var html = '<div class="aid-plan-summary"><span class="ic">' + ic(I.spark, 19, 1.9) + '</span>' +
      '<div><div class="t">' + esc(pick(T.planReady)) + '</div><div class="s">' + total + ' ' + esc(pick(T.planReadyS)) + '</div></div></div>';
    ORDER.forEach(function (key) {
      var s = SEC[key], open = state.openSec === key, inc = state.included[key];
      html += '<div class="aid-plan-sec ' + (open ? 'open' : 'closed') + '">' +
        '<div class="aid-plan-h" data-act="opensec" data-v="' + key + '">' +
        '<span class="aid-plan-ic" style="background:' + s.soft + ';color:' + s.deep + '">' + ic(SEC_ICON[key], 16) + '</span>' +
        '<div class="aid-plan-tx"><div class="t">' + esc(pick(T.secLabel[key])) + '</div><div class="s">' + esc(pick(PLAN[key].label)) + '</div></div>' +
        '<span class="aid-itoggle ' + (inc ? 'on' : '') + '" data-act="toggle" data-v="' + key + '"></span>' +
        '<span class="aid-plan-chev">' + ic(I.chev, 16) + '</span></div>' +
        '<div class="aid-plan-body">' + previewHTML(key) + '</div></div>';
    });
    return html;
  }

  function renderDone() {
    var keys = ORDER.filter(function (k) { return state.status[k] === 'approved' || (state.appliedAll && state.included[k]); });
    var items = keys.reduce(function (n, k) { return n + PLAN[k].count; }, 0);
    return '<div class="aid-done"><div class="ck">' + ic(I.check, 30, 3) + '</div>' +
      '<h3>' + esc(pick(T.doneT)) + '</h3><p>' + esc(pick(T.doneS)) + '</p>' +
      '<div class="aid-done-stats">' +
      '<div class="aid-done-stat"><div class="n">' + keys.length + '</div><div class="l">' + esc(pick(T.sections)) + '</div></div>' +
      '<div class="aid-done-stat"><div class="n">' + items + '</div><div class="l">' + esc(pick(T.items)) + '</div></div>' +
      '<div class="aid-done-stat"><div class="n">AI</div><div class="l">EMSArena</div></div></div></div>';
  }

  function renderFoot() {
    if (state.phase === 'prompt') {
      var dis = state.prompt.trim() ? '' : 'disabled';
      return '<div class="aid-foot"><button class="aid-btn ai" ' + dis + ' data-act="generate">' + ic(I.spark, 16, 1.9) + ' ' + esc(pick(T.generate)) + '</button></div>';
    }
    if (state.phase === 'review' && state.mode === 'plan') {
      var total = ORDER.reduce(function (n, k) { return n + (state.included[k] ? PLAN[k].count : 0); }, 0);
      return '<div class="aid-foot"><button class="aid-btn subtle" data-act="back">' + ic(I.back, 16) + '</button>' +
        '<button class="aid-btn ai" ' + (total ? '' : 'disabled') + ' data-act="applyall">' + ic(I.check, 15, 3) + ' ' + esc(pick(T.applyAll)) + ' (' + total + ')</button></div>';
    }
    if (state.phase === 'done') {
      return '<div class="aid-foot"><button class="aid-btn ai" data-act="close">' + esc(pick(T.viewCourse)) + ' ' + ic(I.chevR, 16) + '</button></div>';
    }
    return '';
  }

  function approve(key) {
    state.status[key] = 'approved';
    if (!curStepKey()) state.phase = 'done';
    render();
  }
  function skip(key) {
    state.status[key] = 'skipped';
    if (!curStepKey()) state.phase = 'done';
    render();
  }

  function bind(d) {
    var ta = d.querySelector('[data-el="prompt"]');
    if (ta) ta.addEventListener('input', function () {
      state.prompt = ta.value;
      var g = d.querySelector('[data-act="generate"]');
      if (g) g.disabled = !ta.value.trim();
    });
    Array.prototype.forEach.call(d.querySelectorAll('[data-act]'), function (el) {
      el.addEventListener('click', function (e) {
        var act = el.getAttribute('data-act'), v = el.getAttribute('data-v');
        if (act === 'close') return close();
        if (act === 'mode') return setMode(v);
        if (act === 'ex') { state.prompt = v; render(); var t2 = root.querySelector('[data-el="prompt"]'); if (t2) t2.focus(); return; }
        if (act === 'generate') { if (!state.prompt.trim()) return; state.phase = 'generating'; render(); setTimeout(function () { if (root) { state.phase = 'review'; render(); } }, 1600); return; }
        if (act === 'approve') return approve(v);
        if (act === 'skip') return skip(v);
        if (act === 'toggle') { state.included[v] = !state.included[v]; render(); return; }
        if (act === 'opensec') { state.openSec = state.openSec === v ? null : v; render(); return; }
        if (act === 'back') { state.phase = 'prompt'; render(); return; }
        if (act === 'applyall') { state.appliedAll = true; state.phase = 'done'; render(); return; }
      });
    });
  }

  // ───────────────────────── wiring ─────────────────────────
  document.addEventListener('click', function (e) {
    var trigger = e.target.closest ? e.target.closest('[data-ems-ai]') : null;
    if (!trigger) return;
    e.preventDefault();
    open();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });

  window.EMSCourseAI = { open: open, close: close };
})();
