/* Dərs modalı — yadda saxlanılmamış dəyişiklik BAYRAĞI (sahib 2026-09-20).
 *
 * Modal açılandan sonra istifadəçi hər hansı sahəni dəyişibsə `data-dirty="1"`
 * qoyulur; journal_grid.js `requestClose()` bu bayrağa baxıb ✕ / İmtina / fon /
 * Escape zamanı təsdiq soruşur. Bayraq `jd:lesson-modal-open` hadisəsində
 * sıfırlanır. Yalnız İSTİFADƏÇİ hadisələri sayılır (`isTrusted`) — korpus→otaq
 * kaskadı və paritet nişanı kimi proqram dəyişiklikləri saxta «dirty» yaratmır.
 * Ayrı modul: journal_grid.js ölçü büdcəsi (check_module_size) dolub.
 */
(function () {
    "use strict";
    var modal = document.querySelector("[data-jd-lesson-modal]");
    var form = modal ? modal.querySelector("[data-jd-lesson-form]") : null;
    if (!modal || !form) return;
    function mark(ev) {
        if (ev.isTrusted) modal.dataset.dirty = "1";
    }
    form.addEventListener("input", mark);
    form.addEventListener("change", mark);
    modal.addEventListener("jd:lesson-modal-open", function () {
        delete modal.dataset.dirty;
    });
})();
