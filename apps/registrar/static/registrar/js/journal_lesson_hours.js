/* Dərs modalının «SAAT» seçimi — yalnız 1, 2 və «Passiv · 1/2» (sahib 2026-11-15).
 *
 * 3 / 4 (və «Passiv · 3/4») variantları şablonda GİZLİ qalır (`data-jd-hours-legacy`): yeni dərsdə görünmür, server də
 * yeni / saatı dəyişən dərsdə 1..2 qəbul edir (journal_activation.MAX_LESSON_HOURS). Mövcud 3–4 saatlıq dərs
 * redaktə olunanda (journal_grid_lesson_modal.js dəyəri artıq seçib) yalnız HƏMİN variant görünür — müəllim saatı
 * dəyişməsə server onu yoxlamır, mövzu / tip düzəlişi xətasız keçir.
 *
 * Qoşulma: `jd:lesson-modal-open` (detail = redaktə datası, yeni dərsdə null) — document-də, bir dəfə; CSP/AJAX-safe.
 */
(function () {
    "use strict";

    var MODAL = "[data-jd-lesson-modal]";
    var DEFAULT_HOURS = "2";

    function sync(event) {
        var modal = event.target;
        if (!modal || !modal.matches || !modal.matches(MODAL)) return;
        var select = modal.querySelector("[data-jd-lesson-hours]");
        if (!select) return;
        var editing = Boolean(event.detail);
        var current = select.value;
        var legacySelected = false;
        Array.prototype.forEach.call(select.querySelectorAll("option[data-jd-hours-legacy]"), function (option) {
            var show = editing && option.value === current;
            if (show) legacySelected = true;
            if (option.hidden === show) option.hidden = !show;
        });
        var selected = select.options[select.selectedIndex];
        if (!editing && selected && selected.hasAttribute("data-jd-hours-legacy") && !legacySelected) {
            // Yeni dərsə köhnə (3/4) dəyər düşməsin — standart 2 saat.
            select.value = DEFAULT_HOURS;
            select.dispatchEvent(new Event("change", { bubbles: true }));
        }
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
        }
    }

    function bind() {
        document.addEventListener("jd:lesson-modal-open", sync);
    }

    if (window.EMSReady && typeof window.EMSReady.once === "function") {
        window.EMSReady.once("jd-lesson-hours", bind);
    } else {
        bind();
    }
})();
