(function (window, document) {
    "use strict";

    // Telefonda yapışqan yığcam taymer həbi (UX2 2026-10-05).
    // Başlıq (taymerlərlə birlikdə) uzun sualda yuxarı sürüşüb gedir; tələbə qalan vaxtı görmür.
    // Həb `position: fixed` olduğu üçün scroll konteynerindən asılı deyil (başlığın `sticky`-si
    // `html`+`body` overflow səbəbindən işləmir). Yalnız əsl taymer zolağı ekrandan çıxanda göstərilir
    // (CSS: yalnız ≤768px). Dəyərlər əsl taymerlərdən (`#timer-value`, `#question-timer-value`) oxunur —
    // taymer məntiqinə (timers.js) toxunulmur, ona görə imtahan vaxtı hesabı dəyişmir.

    function bind() {
        var pill = document.getElementById("exam-timer-pill");
        if (!pill || pill.getAttribute("data-pill-bound") === "1") return;
        pill.setAttribute("data-pill-bound", "1");

        var strip = document.querySelector(".timer-strip");
        var examValue = document.getElementById("timer-value");
        var qValue = document.getElementById("question-timer-value");
        var qBox = document.getElementById("question-timer-container");
        var pillExam = pill.querySelector("[data-pill-exam]");
        var pillExamValue = pill.querySelector("[data-pill-exam-value]");
        var pillQ = pill.querySelector("[data-pill-q]");
        var pillQValue = pill.querySelector("[data-pill-q-value]");
        if (!strip || !("IntersectionObserver" in window)) return;

        var stripVisible = true;

        function seconds(text) {
            var m = /^(\d+):(\d{2})(?::(\d{2}))?$/.exec((text || "").trim());
            if (!m) return null;
            return m[3] !== undefined
                ? parseInt(m[1], 10) * 3600 + parseInt(m[2], 10) * 60 + parseInt(m[3], 10)
                : parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
        }

        function sync() {
            var examText = examValue ? examValue.textContent : "";
            var qShown = !!qBox && window.getComputedStyle(qBox).display !== "none";
            var hasExam = !!examValue && examText !== "" && examText !== "--:--";
            if (pillExam) pillExam.classList.toggle("is-on", hasExam);
            if (pillExamValue && hasExam) pillExamValue.textContent = examText;
            if (pillQ) pillQ.classList.toggle("is-on", qShown);
            if (pillQValue && qShown && qValue) pillQValue.textContent = qValue.textContent;
            var left = seconds(examText);
            pill.classList.toggle("is-danger", (left !== null && left < 60) || (qShown && !!qBox && qBox.classList.contains("danger")));
            pill.classList.toggle("is-visible", !stripVisible && (hasExam || qShown));
        }

        new window.IntersectionObserver(function (entries) {
            stripVisible = entries[entries.length - 1].isIntersecting;
            sync();
        }).observe(strip);

        if ("MutationObserver" in window) {
            var observer = new window.MutationObserver(sync);
            [examValue, qValue].forEach(function (el) {
                if (el) observer.observe(el, { childList: true, characterData: true, subtree: true });
            });
            if (qBox) observer.observe(qBox, { attributes: true, attributeFilter: ["style", "class"] });
        }
        sync();
    }

    if (window.EMSReady) {
        window.EMSReady(bind);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bind);
    } else {
        bind();
    }
})(window, document);
