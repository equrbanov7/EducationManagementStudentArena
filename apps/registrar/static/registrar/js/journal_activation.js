/* «Dərsi aktivləşdir» (UNEC müqayisəsi P1-1, 2026-09-25) — jurnal səhifəsində iki kiçik davranış:
 *
 * 1) «Bu günün cədvəl dərsləri» zolağındakı «Aktivləşdir» formalarında İKİQAT GÖNDƏRİŞ qapısı.
 * 2) «+ Yeni dərs» modalında «cədvəldən kənar dərs — səbəb» sahəsi: seçilmiş tarix + standart
 *    saat açılışın heç bir cədvəl slotuna uyğun gəlmirsə sahə açılır və MƏCBURİ olur.
 *    Uyğunluq backend (`journal_activation.slot_matches` → `dashboard_data.lessons_on`) ilə
 *    EYNİ qaydadır: həftə günü + üst/alt paritet (semestrin ilk həftəsi = ÜST) + dövr sərhədi.
 *    Server qaydası həlledicidir — bu yalnız UX-dir (səbəbsiz göndəriş serverdə rədd olunur).
 *
 * CSP/AJAX-safe: inline yoxdur; hadisələr `EMSDelegate.on` ilə document-ə delegasiya olunur.
 * Slot naxışı `#jdSlotPattern` JSON adasından HƏR dəfə təzə oxunur.
 */
(function () {
    "use strict";

    if (!window.EMSDelegate) {
        return;
    }

    // ── 1. «Aktivləşdir»: ikiqat göndəriş qapısı ────────────────────────────
    window.EMSDelegate.on("submit", "[data-jd-activate-form]", function (event, form) {
        if (form.getAttribute("data-busy") === "1") {
            event.preventDefault();
            return;
        }
        form.setAttribute("data-busy", "1");
        var button = form.querySelector('button[type="submit"]');
        if (button) {
            // Göndəriş getdikdən SONRA söndürülür (əks halda düymə dəyəri formdan düşə bilər).
            window.setTimeout(function () {
                button.disabled = true;
                button.classList.add("is-busy");
                button.setAttribute("aria-busy", "true");
            }, 0);
        }
    });

    // ── 2. Modal: cədvəldən kənar dərsin səbəbi ─────────────────────────────
    var DAY = 86400000;

    function slotPattern() {
        var node = document.getElementById("jdSlotPattern");
        if (!node) {
            return [];
        }
        try {
            var data = JSON.parse(node.textContent || "[]");
            return Array.isArray(data) ? data : [];
        } catch (e) {
            return [];
        }
    }

    function parseISO(value) {
        var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
        return m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])) : null;
    }

    function mondayOf(day) {
        return new Date(day.getTime() - ((day.getUTCDay() + 6) % 7) * DAY);
    }

    function isoWeek(day) {
        var t = new Date(day.getTime());
        t.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7) + 3);
        var firstThursday = new Date(Date.UTC(t.getUTCFullYear(), 0, 4));
        return 1 + Math.round(((t - firstThursday) / DAY - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7);
    }

    function parity(day, periodStart) {
        var start = parseISO(periodStart);
        var week = start ? Math.floor((mondayOf(day) - mondayOf(start)) / (7 * DAY)) + 1 : isoWeek(mondayOf(day));
        // Python `%` kimi (mənfi həftədə də müsbət qalıq) — backend `week_parity` ilə eyni nəticə.
        return ((week % 2) + 2) % 2 === 1 ? "odd" : "even";
    }

    function onSchedule(modal, slots) {
        var dateInput = modal.querySelector("[data-jd-lesson-date]");
        var timeSelect = modal.querySelector("[data-jd-lesson-time]");
        var day = parseISO(dateInput ? dateInput.value : "");
        var time = timeSelect && timeSelect.value ? timeSelect.value.split("|")[0] : "";
        if (!day || !time) {
            return true; // hələ seçilməyib — sahə açılmır (saat onsuz da məcburidir)
        }
        var start = parseISO(modal.getAttribute("data-period-start"));
        var end = parseISO(modal.getAttribute("data-period-end"));
        if ((start && day < start) || (end && day > end)) {
            return false; // dövrdən kənar tarixdə cədvəl dərsi yoxdur
        }
        var weekday = ((day.getUTCDay() + 6) % 7) + 1;
        var weekParity = parity(day, modal.getAttribute("data-period-start"));
        return slots.some(function (slot) {
            var everyWeek = slot.week_type !== "odd" && slot.week_type !== "even";
            return slot.weekday === weekday && (everyWeek || slot.week_type === weekParity) && slot.start === time;
        });
    }

    function refresh(modal) {
        var box = modal ? modal.querySelector("[data-jd-offsched]") : null;
        if (!box) {
            return;
        }
        var slots = slotPattern();
        var action = modal.querySelector("[data-jd-lesson-action]");
        var adding = !action || action.value === "add_lesson";
        var needed = slots.length > 0 && adding && !onSchedule(modal, slots);
        box.hidden = !needed;
        var reason = box.querySelector("[data-jd-offsched-reason]");
        if (reason) {
            reason.required = needed;
            reason.minLength = needed ? 3 : 0;
        }
    }

    window.EMSDelegate.on("jd:lesson-modal-open", "[data-jd-lesson-modal]", function (event, modal) {
        refresh(modal);
    });

    function onFieldChange(event, field) {
        refresh(field.closest("[data-jd-lesson-modal]"));
    }

    window.EMSDelegate.on("change", "[data-jd-lesson-date]", onFieldChange);
    window.EMSDelegate.on("input", "[data-jd-lesson-date]", onFieldChange);
    window.EMSDelegate.on("change", "[data-jd-lesson-time]", onFieldChange);
})();
