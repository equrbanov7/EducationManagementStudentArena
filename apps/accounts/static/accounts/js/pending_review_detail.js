/*
 * pending_review_detail.js
 * Source: apps/accounts/templates/accounts/pending_review_detail.html
 * Per-question score inputs feed an auto-computed total; a confirm modal
 * guards the save. i18n confirm strings are read from data-* on #pendingReviewForm.
 * Wrapped in EMSReady + idempotent form guard (page extends base.html).
 */
(function () {
    "use strict";

    window.EMSReady(function () {
        var form = document.getElementById("pendingReviewForm");
        if (!form || form.dataset.prBound === "1") {
            return;
        }
        form.dataset.prBound = "1";

        var d = form.dataset;
        var confirmTitle = d.i18nConfirmTitle;
        var confirmMessage = d.i18nConfirmMessage;

        var totalInput = document.getElementById("id_score");
        var scoreInputs = Array.prototype.slice.call(document.querySelectorAll(".question-score-input"));
        var manualTotalActive = totalInput && totalInput.getAttribute("data-manual-total-initial") === "1";
        var submitConfirmed = false;

        function parseIntegerValue(rawValue) {
            var normalized = (rawValue || "").trim().replace(",", ".");
            var match = normalized.match(/^-?\d+/);
            if (!match) return null;
            var parsed = parseInt(match[0], 10);
            return Number.isNaN(parsed) ? null : parsed;
        }

        function normalizeInput(input) {
            var parsed = parseIntegerValue(input.value);
            if (parsed === null) {
                input.value = "";
                return 0;
            }
            var nextValue = Math.max(0, parsed);
            var max = parseInt(input.getAttribute("max") || input.getAttribute("data-question-max") || "0", 10);
            if (!Number.isNaN(max) && max > 0 && nextValue > max) nextValue = max;
            input.value = String(nextValue);
            return nextValue;
        }

        function recalcTotal() {
            if (!totalInput || manualTotalActive || !scoreInputs.length) return;
            var total = scoreInputs.reduce(function (sum, input) {
                return sum + normalizeInput(input);
            }, 0);
            totalInput.value = String(total);
        }

        scoreInputs.forEach(function (input) {
            input.addEventListener("input", recalcTotal);
            input.addEventListener("blur", function () {
                normalizeInput(input);
                recalcTotal();
            });
        });

        if (totalInput && !totalInput.disabled) {
            totalInput.addEventListener("input", function () {
                manualTotalActive = Boolean((totalInput.value || "").trim());
                if (!manualTotalActive) recalcTotal();
            });
            totalInput.addEventListener("blur", function () {
                if ((totalInput.value || "").trim()) normalizeInput(totalInput);
            });
        }

        if (!manualTotalActive) recalcTotal();

        if (form) {
            form.addEventListener("submit", function (event) {
                var submitButton = form.querySelector("button[type='submit']");
                if (submitConfirmed || !submitButton || submitButton.disabled) {
                    submitConfirmed = false;
                    return;
                }
                event.preventDefault();
                if (typeof window.openActionConfirmModal !== "function") {
                    submitConfirmed = true;
                    form.requestSubmit ? form.requestSubmit() : form.submit();
                    return;
                }
                window.openActionConfirmModal({
                    title: confirmTitle,
                    message: confirmMessage,
                    confirmLabel: submitButton.textContent.trim(),
                    confirmButtonClass: "btn btn-success",
                    onConfirm: function () {
                        submitConfirmed = true;
                        form.requestSubmit ? form.requestSubmit() : form.submit();
                    },
                });
            });
        }

        document.querySelectorAll(".answer-accordion-btn").forEach(function (button) {
            button.addEventListener("click", function () {
                var card = document.getElementById("grade-answer-" + button.getAttribute("data-grade-toggle"));
                if (!card) return;
                var collapsed = card.classList.toggle("is-collapsed");
                var icon = button.querySelector("i");
                if (icon) {
                    icon.classList.toggle("fa-chevron-down", collapsed);
                    icon.classList.toggle("fa-chevron-up", !collapsed);
                }
            });
        });
    });
})();
