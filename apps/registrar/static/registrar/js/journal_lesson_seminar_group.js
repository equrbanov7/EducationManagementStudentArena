/* Dərs modalı — seminar alt qrupu seçimi (sahib 2026-11-07).

   Ana qrupun jurnalında seminar alt qrupları varsa (`[data-jd-seminar-group-field]` render olunur) sahə yalnız dərs
   tipi «seminar» olanda görünür; seçim İSTƏYƏ BAĞLIDIR («Bütün qrup» = birgə seminar), başqa tipdə boşaldılır (server
   də yoxlayır — seminar_groups.py). Redaktədə dərsin öz alt qrupu `jd:lesson-modal-open` hadisəsinin
   `detail.seminarGroup` dəyərindən gəlir (journal_grid_lesson_modal.js). AJAX-safe: yalnız EMSDelegate. */
(function () {
    "use strict";

    var SEMINAR = "seminar";

    function setValue(select, value) {
        if (!select || select.value === value) return;
        select.value = value;
        select.dispatchEvent(new Event("change", { bubbles: true })); // bootstrap-select görünüşü
    }

    function sync(modal) {
        var wrap = modal && modal.querySelector("[data-jd-seminar-group-field]");
        if (!wrap) return;
        var field = modal.querySelector("[name='lesson_kind']");
        var isSeminar = !!field && field.value === SEMINAR;
        wrap.hidden = !isSeminar;
        var select = wrap.querySelector("[data-jd-lesson-seminar-group]");
        if (!isSeminar) setValue(select, "");
        // ?seminar=N görünüşü (sahib 2026-11-08): yeni seminar dərsində həmin alt qrup öncədən seçilir.
        var preset = wrap.getAttribute("data-jd-default-seminar-group") || "";
        if (isSeminar && select && !select.value && preset && modal.getAttribute("data-jd-seminar-editing") !== "1") setValue(select, preset);
    }

    // ⚠️ EMSDelegate «hadisə|selektor» cütü üzrə TƏK işləyici saxlayır — lab skripti eyni hadisələri başqa
    // selektorla dinləyir; burada fərqli selektor ikisinin də işləməsi üçündür.
    window.EMSDelegate.on("change", ".jd-modal[data-jd-lesson-modal] select[name='lesson_kind']", function (event, field) {
        sync(field.closest("[data-jd-lesson-modal]"));
    });

    window.EMSDelegate.on("jd:lesson-modal-open", "[data-jd-lesson-modal][data-jd-seminar-modal]", function (event, modal) {
        modal.setAttribute("data-jd-seminar-editing", event.detail ? "1" : "");
        setValue(modal.querySelector("[data-jd-lesson-seminar-group]"), (event.detail && event.detail.seminarGroup) || "");
        sync(modal);
    });
})();
