/* ═══════════════════════════════════════════════════════════════════════════
   schedule_editor_confirm.js — «Cədvəl idarəetməsi» ümumi təsdiq dialoqu

   Sahibin tələbi (2026-09-09): «slot dəyişəndə hər zamanda təsdiq istəsin
   kiçik bir modalda ki əminsiz deyə, problem olmasa belə». Yəni xanaya dərs
   YAZANDA, onu DÜZƏLDƏNDƏ və SİLƏNDƏ — toqquşma olmasa da — kiçik təsdiq
   dialoqu çıxır. Sürüklə-buraxın öz təsdiqi «seditMove» dialoqundadır.

   AYRI fayldır, çünki `schedule_editor.js` modul-ölçü büdcəsinə (600 sətir)
   dayanmışdı. `profile.html`-də BU fayl redaktorda ƏVVƏL yüklənir.

   Müqavilə:  window.EMSScheduleConfirm.ask(summary, note, onOk)
              window.EMSScheduleConfirm.texts()          → `data-t-*` mətnləri
              window.EMSScheduleConfirm.cellSummary(el)  → xananın xülasə sətri
   ═══════════════════════════════════════════════════════════════════════════ */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    var CONFIRM_ID = "seditConfirm";
    var pending = null;

    function box() {
        return document.getElementById(CONFIRM_ID);
    }

    /* Sabit mətnlər şablonda tərcümə olunub `data-t-*` atributlarında gəlir
     * (xarici JS Django template engine-dən keçmir). */
    function texts() {
        var host = document.querySelector("[data-sedit-confirm-texts]");
        return host ? host.dataset : {};
    }

    function ask(summary, note, onOk) {
        var el = box();
        if (!el || !window.EMSOverlay) {
            onOk();                    // dialoq yoxdursa axını bloklama
            return;
        }
        pending = onOk;
        var sumNode = el.querySelector("[data-sedit-confirm-summary]");
        if (sumNode) {
            sumNode.textContent = summary || "";
        }
        var noteNode = el.querySelector("[data-sedit-confirm-note]");
        if (noteNode) {
            noteNode.textContent = note || "";
            noteNode.hidden = !note;
        }
        window.EMSOverlay.open(CONFIRM_ID);
    }

    /* Təsdiq mətnindəki xülasə: xana dialoqunun SEÇİLMİŞ dəyərləri (fənn ·
     * müəllim · gün · saat · tip · həftə). Etiketlər seçicinin öz option
     * mətnindən götürülür — serverdən ikinci sorğu OLMADAN. */
    function selectedLabel(host, name) {
        var el = host ? host.querySelector('[data-sedit-field="' + name + '"]') : null;
        if (!el) {
            return "";
        }
        if (el.tagName === "SELECT") {
            var opt = el.options[el.selectedIndex];
            return opt && opt.value ? opt.textContent.trim() : "";
        }
        return (el.value || "").trim();
    }

    function cellSummary(host) {
        return ["subject_id", "instructor_id", "weekday", "time_slot", "slot_kind", "week_type"]
            .map(function (name) {
                return selectedLabel(host, name);
            })
            .filter(Boolean)
            .join(" · ");
    }

    DELEGATE.on("click", "[data-sedit-confirm-ok]", function (event) {
        event.preventDefault();
        var run = pending;
        pending = null;
        if (window.EMSOverlay) {
            window.EMSOverlay.close(CONFIRM_ID);
        }
        if (run) {
            run();
        }
    });

    /* Dialoq «Ləğv et»/Escape ilə bağlananda gözləyən əməl ATILIR — növbəti
     * təsdiqdə köhnə callback işə düşməsin. */
    document.addEventListener("ems:overlay:close", function (event) {
        if (event.target && event.target.id === CONFIRM_ID) {
            pending = null;
        }
    });

    window.EMSScheduleConfirm = { ask: ask, texts: texts, cellSummary: cellSummary };
})(window, document);
