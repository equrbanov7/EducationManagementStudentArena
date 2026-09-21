/* coding_exam_config_bootstrap.js
   Mənbə: exams/student/take_coding_exam.html (inline nonce script,
   2026-09-21-də xarici fayla çıxarıldı — CSP unsafe-inline yolu bağlanır).

   Şablon konfiqi `<script id="coding-exam-config" type="application/json">`
   data-adasında render edir (URL-lər, id-lər, bayraqlar, qalan saniyə, i18n);
   bu KLASSİK (modul olmayan) skript onu parse edib inline blokun qoyduğu EYNİ
   qlobalı — `window.CODING_EXAM_CONFIG` — qurur. Parse anında işlədiyi üçün
   deferred `coding_exam.entry.js` modulu (context.js) oxuyanda artıq hazırdır. */
(function () {
    "use strict";

    var el = document.getElementById("coding-exam-config");
    if (!el) {
        return;
    }
    try {
        window.CODING_EXAM_CONFIG = JSON.parse(el.textContent);
    } catch (e) {
        window.CODING_EXAM_CONFIG = {};
    }
})();
