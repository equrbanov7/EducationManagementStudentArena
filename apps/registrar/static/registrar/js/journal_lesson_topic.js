/* Dərs modalının MÖVZU sahələri — plan seçimi ↔ sərbəst mətn (sahib 2026-10-25).
 *
 * Modalda iki sahə var: təsdiqlənmiş sillabusun həftəlik planından seçim (`[data-jd-lesson-topic]`,
 * select) və planda olmayan mövzu üçün sərbəst mətn (`[data-jd-lesson-topic-custom]`). Server sərbəst
 * mətni üstün tutur (journal_topics.posted_topic), ona görə sahələr bir-birini təmizləyir:
 *
 *  * plandan mövzu seçiləndə sərbəst mətn boşalır;
 *  * sərbəst mətn yazılanda plan seçimi «Mövzunu seçin…»-ə qayıdır;
 *  * YENİ dərs (`jd:lesson-modal-prepare`) — sərbəst mətn sıfırlanır (doldurma planın növbəti mövzusunu
 *    seçir, journal_lesson_prefill.js);
 *  * REDAKTƏ (`jd:lesson-modal-open`, detail = dərsin dəyərləri) — mövzu planda yoxdursa sərbəst mətnə
 *    yazılır (əvvəl plandan kənar mövzu redaktədə səssizcə silinirdi).
 *
 * Plan seçimi sillabus sətrinə bağlanmanı (`Lesson.syllabus_week`) server həll edir. CSP/AJAX-safe:
 * inline yoxdur; document dinləyiciləri `EMSReady.once` ilə bir dəfə qoşulur, modal yoxdursa heç nə etmir.
 */
(function () {
    "use strict";

    if (!window.EMSReady) return;

    function parts(node) {
        var modal = node && node.closest ? node.closest("[data-jd-lesson-modal]") : null;
        if (!modal) return null;
        var select = modal.querySelector("select[data-jd-lesson-topic]");
        var custom = modal.querySelector("[data-jd-lesson-topic-custom]");
        return select && custom ? { select: select, custom: custom } : null;
    }

    function hasOption(select, value) {
        for (var i = 0; i < select.options.length; i++) {
            if (select.options[i].value === value) return true;
        }
        return false;
    }

    function clearSelect(select) {
        if (!select.value) return;
        select.value = "";
        // data-bootstrap-select vidcetinin görünüşü sinxronlansın.
        select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    window.EMSReady.once("jd-lesson-topic", function () {
        document.addEventListener("change", function (event) {
            var target = event.target;
            if (!target || !target.matches || !target.matches("select[data-jd-lesson-topic]")) return;
            var p = parts(target);
            if (p && target.value) p.custom.value = "";
        });

        document.addEventListener("input", function (event) {
            var target = event.target;
            if (!target || !target.matches || !target.matches("[data-jd-lesson-topic-custom]")) return;
            var p = parts(target);
            if (p && target.value.trim()) clearSelect(p.select);
        });

        document.addEventListener("jd:lesson-modal-prepare", function (event) {
            var p = parts(event.target);
            if (p) p.custom.value = "";
        });

        document.addEventListener("jd:lesson-modal-open", function (event) {
            var p = parts(event.target);
            var data = event.detail;
            if (!p || !data) return; // YENİ dərs — prepare artıq sıfırlayıb
            var topic = String(data.topic || "");
            if (topic && !hasOption(p.select, topic)) {
                clearSelect(p.select);
                p.custom.value = topic;
            } else {
                p.custom.value = "";
            }
        });
    });
})();
