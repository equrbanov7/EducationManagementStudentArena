/* Dərs modalı — laboratoriya qrupu seçimi (sahib 2026-11-06).

   Jurnal Lab-1 / Lab-2 siyahılarına bölünübsə (`[data-jd-lab-group-field]` render olunur) sahə yalnız dərs tipi
   «laboratoriya» olanda görünür və yeni dərsdə məcburidir; başqa tipdə boşaldılır (server də yoxlayır — lab_groups.py).
   Redaktədə dərsin öz qrupu `jd:lesson-modal-open` hadisəsinin `detail.labGroup` dəyərindən gəlir
   (journal_grid_lesson_modal.js), yeni dərsdə boş başlayır. AJAX-safe: yalnız EMSDelegate. */
(function () {
    "use strict";

    var LAB = "lab";

    function kindOf(modal) {
        var field = modal.querySelector("[name='lesson_kind']");
        return field ? field.value : "";
    }

    function setValue(select, value) {
        if (!select || select.value === value) return;
        select.value = value;
        select.dispatchEvent(new Event("change", { bubbles: true })); // bootstrap-select görünüşü
    }

    function sync(modal) {
        var wrap = modal.querySelector("[data-jd-lab-group-field]");
        if (!wrap) return;
        var select = wrap.querySelector("[data-jd-lesson-lab-group]");
        var isLab = kindOf(modal) === LAB;
        wrap.hidden = !isLab;
        if (select) {
            // Yeni dərsdə məcburi; redaktədə köhnə (bütün qruplu) lab dərsi qrupsuz qala bilər.
            select.required = isLab && modal.getAttribute("data-jd-lab-editing") !== "1";
            if (!isLab) setValue(select, "");
        }
    }

    window.EMSDelegate.on("change", "[data-jd-lesson-modal] [name='lesson_kind']", function (event, field) {
        sync(field.closest("[data-jd-lesson-modal]"));
    });

    // ⚠️ EMSDelegate «hadisə|selektor» cütü üzrə TƏK işləyici saxlayır — journal_activation.js eyni hadisəni
    // `[data-jd-lesson-modal]` ilə dinləyir; fərqli selektor ikisinin də işləməsi üçündür.
    window.EMSDelegate.on("jd:lesson-modal-open", ".jd-modal[data-jd-lesson-modal]", function (event, modal) {
        var select = modal.querySelector("[data-jd-lesson-lab-group]");
        if (!select) return;
        modal.setAttribute("data-jd-lab-editing", event.detail ? "1" : "");
        setValue(select, (event.detail && event.detail.labGroup) || "");
        sync(modal);
    });
})();
