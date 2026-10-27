/* «Data bərpası» rejimi (journal.teacher_full_edit, sahib 2026-10-27) — yalnız UX; server həlledicidir.

   1) XANANI TƏMİZLƏMƏK: rejimdə (`form[data-jd-full-edit]`) dolu xananın seçimi «—» edilirsə gizli `att__…`
      sahəsi `clear` olur (journal_grid.js onu əvvəlcə «» edir — ona görə növbəti tikdə). Server yalnız rejim açıq
      olanda və səbəblə silir.
   2) SƏBƏB DİALOQU: avtomatik yadda saxlama 409 `reason_required` alanda (journal_grid_autosave.js
      `jd:autosave-refused` hadisəsi) dialoq açılır; yazılan səbəb formanın gizli `full_edit_reason` sahəsinə
      (`data-jd-autosave-extra`) düşür və «Yenidən cəhd et» ilə təkrar göndərilir. Səbəb səhifədə yadda qalır.
   3) DƏRS MODALI: səbəb sahəsi yalnız adi qayda ilə bağlı olan əməldə (bağlı jurnal, redaktə vaxtı keçmiş dərs,
      yazma pəncərəsindən köhnə tarix) MƏCBURİ olur; silmə təsdiqi silinəcək qeyd sayını göstərir.
   CSP/AJAX-safe: inline yoxdur, mətnlər data-atributlardadır; hadisələr EMSDelegate / EMSReady.once ilə bir dəfə. */
(function () {
    "use strict";

    if (!window.EMSDelegate || !window.EMSReady) return;

    var FORM = "form[data-jd-full-edit]";

    function serverValue(select) {
        for (var i = 0; i < select.options.length; i += 1) {
            if (select.options[i].defaultSelected) return select.options[i].value;
        }
        return "";
    }

    // ── 1) «—» → clear ───────────────────────────────────────────────────
    window.EMSDelegate.on("change", FORM + " select[data-jd-semselect]", function (event, select) {
        window.setTimeout(function () {
            var cell = select.closest("td");
            var att = cell && cell.querySelector("[data-jd-sem-att]");
            if (!att) return;
            if (select.value === "" && serverValue(select) !== "") att.value = "clear";
        }, 0);
    });

    // ── 2) Səbəb dialoqu (avtomatik yadda saxlama) ───────────────────────
    var pendingForm = null;

    function dialog() {
        return document.querySelector("[data-jd-fe-dialog]");
    }

    function closeDialog() {
        var box = dialog();
        if (box) box.hidden = true;
        pendingForm = null;
    }

    function openDialog(form) {
        var box = dialog();
        if (!box) return;
        pendingForm = form;
        var input = box.querySelector("[data-jd-fe-dialog-input]");
        var error = box.querySelector("[data-jd-fe-dialog-error]");
        var stored = form.querySelector("[data-jd-fe-reason]");
        if (input) input.value = stored ? stored.value : "";
        if (error) error.hidden = true;
        box.hidden = false;
        if (input) input.focus();
    }

    function confirmDialog() {
        var box = dialog();
        if (!box || !pendingForm) return;
        var input = box.querySelector("[data-jd-fe-dialog-input]");
        var error = box.querySelector("[data-jd-fe-dialog-error]");
        var min = parseInt((input && input.getAttribute("data-min")) || "3", 10);
        var text = input ? input.value.replace(/\s+/g, " ").trim() : "";
        if (text.length < min) {
            if (error) error.hidden = false;
            if (input) input.focus();
            return;
        }
        var form = pendingForm;
        var stored = form.querySelector("[data-jd-fe-reason]");
        if (stored) stored.value = text;
        closeDialog();
        var retry = form.querySelector("[data-jd-autosave-retry]");
        if (retry) retry.click();
    }

    window.EMSDelegate.on("click", "[data-jd-fe-cancel]", function () {
        closeDialog();
    });
    window.EMSDelegate.on("click", "[data-jd-fe-confirm]", function () {
        confirmDialog();
    });

    // ── 3) Dərs modalı: səbəbin məcburiliyi + silmə təsdiqi ──────────────
    var editing = null; // açıq redaktənin düyməsi (yeni dərsdə null)

    function lessonModal() {
        return document.querySelector("[data-jd-lesson-modal]");
    }

    function syncLessonReason() {
        var modal = lessonModal();
        var reason = modal && modal.querySelector("[data-jd-fe-lesson-reason]");
        if (!reason) return;
        var dateInput = modal.querySelector("[data-jd-lesson-date]");
        var normalMin = modal.getAttribute("data-fe-normal-min") || "";
        var needed = modal.getAttribute("data-fe-journal-locked") === "1";
        if (editing && editing.getAttribute("data-lesson-fe") === "1") needed = true;
        var date = dateInput ? dateInput.value : "";
        var unchanged = editing && date === editing.getAttribute("data-lesson-date");
        if (date && normalMin && date < normalMin && !unchanged) needed = true;
        reason.required = needed;
    }

    function syncDeleteConfirm() {
        var modal = lessonModal();
        var del = modal && modal.querySelector("[data-jd-lesson-delete]");
        var template = modal && modal.getAttribute("data-fe-delete-body");
        if (!del || !template || !editing) return;
        var count = editing.getAttribute("data-lesson-marks") || "0";
        del.setAttribute("data-confirm-body", template.replace("{n}", count));
    }

    function init() {
        // Modal açılır (journal_grid_lesson_modal.js `jd:lesson-modal-open`): redaktədə düyməni tap.
        window.EMSReady.once("journal-full-edit", function () {
            document.addEventListener("jd:lesson-modal-open", function (event) {
                var data = event.detail;
                editing = null;
                if (data && data.actionUrl) {
                    var buttons = document.querySelectorAll("[data-jd-edit-lesson]");
                    for (var i = 0; i < buttons.length; i += 1) {
                        if (buttons[i].getAttribute("data-action-url") === data.actionUrl) editing = buttons[i];
                    }
                }
                syncLessonReason();
                syncDeleteConfirm();
            });
            // Avtomatik yadda saxlama səbəb istəyir → dialoq.
            document.addEventListener("jd:autosave-refused", function (event) {
                var detail = event.detail || {};
                var form = event.target && event.target.closest ? event.target.closest(FORM) : null;
                if (form && detail.code === "reason_required") openDialog(form);
            });
            document.addEventListener("keydown", function (event) {
                var box = dialog();
                if (event.key === "Escape" && box && !box.hidden) closeDialog();
            });
        });
    }

    window.EMSDelegate.on("change", "[data-jd-lesson-modal] [data-jd-lesson-date]", function () {
        syncLessonReason();
    });

    window.EMSReady(init);
})();
