/*
 * grade_submission.js — müəllimin qiymətləndirmə səhifəsi (2026-10-17, Paket E).
 * Suallar üzrə balların cəmi ümumi balı hesablayır (əl ilə yazılıbsa toxunmur), saxlamadan əvvəl təsdiq
 * (ortaq `EMSConfirm`), cavab kartlarının aç/bağla düyməsi. AJAX-safe: `EMSDelegate` + `EMSReady`;
 * sahələr hər hadisədə yenidən sorğulanır. Qarmaqlar: `#totalScoreInput`, `#gradeForm`,
 * `.answer-score-input`, `[data-grade-toggle]`.
 */
(function () {
    "use strict";

    var state = { manualTotalActive: false, submitConfirmed: false };

    function totalInput() {
        return document.getElementById("totalScoreInput");
    }

    function scoreInputs() {
        return Array.prototype.slice.call(document.querySelectorAll(".answer-score-input"));
    }

    function parseIntegerValue(rawValue) {
        var normalized = (rawValue || "").trim().replace(",", ".");
        if (!normalized) { return null; }
        var match = normalized.match(/^-?\d+/);
        if (!match) { return null; }
        var parsed = parseInt(match[0], 10);
        return isNaN(parsed) ? null : parsed;
    }

    function getQuestionMax(input) {
        var parsed = parseInt(input.dataset.questionMax || "0", 10);
        return isNaN(parsed) ? 0 : parsed;
    }

    function normalizePerQuestion(input) {
        var parsed = parseIntegerValue(input.value);
        if (parsed === null) {
            input.value = "";
            return 0;
        }
        var next = parsed < 0 ? 0 : parsed;
        var max = getQuestionMax(input);
        if (max > 0 && next > max) { next = max; }
        input.value = String(next);
        return next;
    }

    function recalcTotal() {
        var total = totalInput();
        var inputs = scoreInputs();
        if (!total || !inputs.length || state.manualTotalActive) { return; }
        total.value = String(inputs.reduce(function (acc, input) { return acc + normalizePerQuestion(input); }, 0));
    }

    function submitForm(form) {
        if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
        } else {
            form.submit();
        }
    }

    window.EMSReady(function () {
        var total = totalInput();
        state.manualTotalActive = !!(total && total.dataset.manualTotalInitial === "1");
        if (!state.manualTotalActive && scoreInputs().length) { recalcTotal(); }
    });

    window.EMSDelegate.on("input", ".answer-score-input", function () {
        recalcTotal();
    });

    window.EMSDelegate.on("focusout", ".answer-score-input", function (event, input) {
        normalizePerQuestion(input);
        recalcTotal();
    });

    window.EMSDelegate.on("input", "#totalScoreInput", function (event, input) {
        if (input.disabled) { return; }
        if (!(input.value || "").trim()) {
            state.manualTotalActive = false;
            recalcTotal();
            return;
        }
        state.manualTotalActive = true;
    });

    window.EMSDelegate.on("focusout", "#totalScoreInput", function (event, input) {
        if (input.disabled) { return; }
        var parsed = parseIntegerValue(input.value);
        if (parsed === null) {
            state.manualTotalActive = false;
            recalcTotal();
            return;
        }
        var next = parsed < 0 ? 0 : parsed;
        var max = parseInt(input.getAttribute("max") || "0", 10);
        if (!isNaN(max) && max > 0 && next > max) { next = max; }
        input.value = String(next);
    });

    window.EMSDelegate.on("submit", "#gradeForm", function (event, form) {
        var submitButton = form.querySelector('button[type="submit"]');
        if (state.submitConfirmed || !submitButton || submitButton.disabled) {
            state.submitConfirmed = false;
            return;
        }
        event.preventDefault();
        window.EMSConfirm.open({
            title: gettext("Qiymətləndirməni təsdiqləyin"),
            body: gettext("Bu bal və rəyi saxlamaq istədiyinizə əminsiniz?"),
            confirmLabel: submitButton.textContent.trim()
        }).then(function (ok) {
            if (!ok) { return; }
            state.submitConfirmed = true;
            submitForm(form);
        });
    });

    window.EMSDelegate.on("click", ".answer-toggle-btn[data-grade-toggle]", function (event, btn) {
        var card = document.getElementById("grade-answer-" + btn.dataset.gradeToggle);
        if (!card) { return; }
        var collapsed = card.classList.toggle("answer-collapsed");
        btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
        var icon = btn.querySelector("i");
        if (icon) {
            icon.classList.toggle("fa-chevron-down", collapsed);
            icon.classList.toggle("fa-chevron-up", !collapsed);
        }
    });
})();
