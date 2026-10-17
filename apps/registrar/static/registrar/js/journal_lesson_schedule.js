/* «Yeni dərs» modalı — seçilmiş TARİXİN cədvəl slotu (sahib 2026-10-17: «Elektron jurnalda yeni dərs əlavə
 * edərkən otaq nömrəsi cədvəldəki avtomatik gəlsin, müəllim istəsə dəyişə bilər»).
 *
 * Mənbə: `#jdSlotPattern` JSON adası (apps/registrar/journal_activation.slot_pattern) — açılışın cədvəldə
 * duran slotları: həftə günü, üst/alt (`week_type`), saat, tip, otaq (`room_id` reyestrdə tapılıbsa,
 * `room_label` cədvəldə yazıldığı kimi). Ada HƏR dəfə təzə oxunur.
 *
 *  * `match(modal)` — tarixin slotu: saatı uyğun gələn (eyni tip üstün) → eyni tipli → günün ilk slotu;
 *    həmin gün slot yoxdursa `null`. journal_lesson_room.js otağı buna görə doldurur. Qayda serverdəki
 *    `journal_lesson_prefill.schedule_slot_for` ilə EYNİDİR (otaq boş göndərilsə server də onu yazır).
 *  * Dərs saatı: YENİ dərsdə tarix / tip dəyişəndə, müəllim saatı ÖZÜ seçməyibsə, həmin günün slotunun
 *    saatına keçir (əvvəl eyni tipli slot). Yalnız standart siyahıdakı saat qoyulur — təşkilatın öz zəng
 *    saatını server yalnız slot bağı (`slot_id`, bu günün doldurması) ilə qəbul edir.
 *
 * Həftə pariteti journal_activation.js / backend `dashboard_data.lessons_on` ilə eyni: semestrin ilk
 * həftəsi = ÜST, dövrdən kənar tarixdə slot yoxdur. Server qaydaları həlledicidir — bu fayl yalnız UX-dir.
 * CSP/AJAX-safe: inline yoxdur; dinləyicilər document-də, bir dəfə (EMSReady.once).
 */
(function () {
    "use strict";

    var MODAL = "[data-jd-lesson-modal]";
    var DAY = 86400000;
    var applying = false;

    function pattern() {
        var node = document.getElementById("jdSlotPattern");
        if (!node) return [];
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
        return ((week % 2) + 2) % 2 === 1 ? "odd" : "even";
    }

    function field(modal, selector) {
        return modal ? modal.querySelector(selector) : null;
    }

    function kindOf(modal) {
        var kind = field(modal, "[name='lesson_kind']");
        return kind ? kind.value : "";
    }

    function isAdding(modal) {
        var action = field(modal, "[data-jd-lesson-action]");
        return !action || action.value === "add_lesson";
    }

    /** Seçilmiş tarixdə keçirilən slotlar (həftə günü + üst/alt + dövr sərhədi), saat sırası ilə. */
    function slotsOn(modal) {
        var date = field(modal, "[data-jd-lesson-date]");
        var day = parseISO(date ? date.value : "");
        if (!day) return [];
        var start = parseISO(modal.getAttribute("data-period-start"));
        var end = parseISO(modal.getAttribute("data-period-end"));
        if ((start && day < start) || (end && day > end)) return [];
        var weekday = ((day.getUTCDay() + 6) % 7) + 1;
        var weekParity = parity(day, modal.getAttribute("data-period-start"));
        return pattern()
            .filter(function (slot) {
                var everyWeek = slot.week_type !== "odd" && slot.week_type !== "even";
                return slot.weekday === weekday && (everyWeek || slot.week_type === weekParity);
            })
            .sort(function (a, b) {
                return a.start < b.start ? -1 : a.start > b.start ? 1 : 0;
            });
    }

    function firstOfKind(slots, kind) {
        for (var i = 0; i < slots.length; i++) {
            if (slots[i].kind === kind) return slots[i];
        }
        return null;
    }

    /** Tarixin slotu: saatı uyğun gələn (eyni tip üstün) → eyni tipli → günün ilk slotu; yoxdursa null. */
    function match(modal) {
        var slots = slotsOn(modal);
        if (!slots.length) return null;
        var time = field(modal, "[data-jd-lesson-time]");
        var start = time && time.value ? time.value.split("|")[0] : "";
        var timed = start
            ? slots.filter(function (slot) {
                  return slot.start === start;
              })
            : [];
        var pool = timed.length ? timed : slots;
        return firstOfKind(pool, kindOf(modal)) || pool[0];
    }

    function standardOption(select, value) {
        for (var i = 0; i < select.options.length; i++) {
            var opt = select.options[i];
            if (opt.value === value && !opt.hasAttribute("data-jd-slot-time")) return true;
        }
        return false;
    }

    /** YENİ dərs, saat toxunulmayıb: tarixin (eyni tipli) slotunun saatı. Cari saat bu tipin slotudursa qalır. */
    function syncTime(modal) {
        var select = field(modal, "[data-jd-lesson-time]");
        if (!select || select.tagName !== "SELECT" || !isAdding(modal) || modal.dataset.jdTimeTouched === "1") return;
        var slots = slotsOn(modal);
        if (!slots.length) return;
        var current = select.value;
        var timeOf = function (slot) {
            return slot.start + "|" + slot.end;
        };
        var same = slots.filter(function (slot) {
            return timeOf(slot) === current;
        });
        var kind = kindOf(modal);
        var target = firstOfKind(slots, kind);
        if (firstOfKind(same, kind) || (!target && same.length)) return;
        var value = timeOf(target || slots[0]);
        if (value === current || !standardOption(select, value)) return;
        applying = true;
        try {
            select.value = value;
            // Vidcet, «cədvəldən kənar» sahəsi, slot bağı və otaq bu hadisə ilə sinxronlanır.
            select.dispatchEvent(new Event("change", { bubbles: true }));
        } finally {
            applying = false;
        }
    }

    function onField(event) {
        var target = event.target;
        if (applying || !target || !target.matches) return;
        var modal = target.closest ? target.closest(MODAL) : null;
        if (!modal) return;
        if (target.matches("[data-jd-lesson-time]")) {
            if (event.type === "change") modal.dataset.jdTimeTouched = "1"; // müəllimin öz seçimi
            return;
        }
        if (target.matches("[data-jd-lesson-date], [name='lesson_kind']")) syncTime(modal);
    }

    function bind() {
        // Doldurma (journal_lesson_prefill.js `prepare`) açılışdan ƏVVƏL gedir — bayraq açılışda sıfırlanır.
        document.addEventListener("jd:lesson-modal-open", function (event) {
            var modal = event.target;
            if (modal && modal.matches && modal.matches(MODAL)) delete modal.dataset.jdTimeTouched;
        });
        document.addEventListener("change", onField);
        document.addEventListener("input", onField);
    }

    if (window.EMSReady && typeof window.EMSReady.once === "function") {
        window.EMSReady.once("jd-lesson-schedule", bind);
    } else {
        bind();
    }

    window.EMSJournalSchedule = { match: match, slotsOn: slotsOn, syncTime: syncTime };
})();
