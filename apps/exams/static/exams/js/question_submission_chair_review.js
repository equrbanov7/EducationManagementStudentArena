/* Kafedra təsdiqi — qərar düymələri + səbəb dialoqu (focus trap, aria).
 *
 * AJAX-safe: `window.EMSReady` sarğısı (idempotent, null-safe) — panel swap
 * olunsa da təkrar bağlanma yaratmır. Inline JS YOXDUR (CSP: script-src SELF).
 * Dinamik dəyərlər (URL, minimum uzunluq, mətnlər) data-atributlardan oxunur.
 */
(function () {
    "use strict";

    function boot() {
        var root = document.querySelector("[data-qchair]");
        if (!root) {
            return;
        }
        var form = root.querySelector("[data-qchair-form]");
        var decisionInput = root.querySelector("[data-qchair-decision]");
        var reasonInput = root.querySelector("[data-qchair-reason]");
        var dialog = document.querySelector("[data-qchair-dialog]");
        if (!form || !decisionInput || !reasonInput || !dialog) {
            return;
        }

        var minReason = parseInt(root.dataset.minReason, 10) || 20;
        var titleEl = dialog.querySelector("[data-qchair-dialog-title]");
        var hintEl = dialog.querySelector("[data-qchair-dialog-hint]");
        var textEl = dialog.querySelector("[data-qchair-dialog-text]");
        var counterEl = dialog.querySelector("[data-qchair-counter]");
        var confirmBtn = dialog.querySelector("[data-qchair-confirm]");
        var cancelBtn = dialog.querySelector("[data-qchair-cancel]");
        var lastFocused = null;
        var pendingDecision = "";

        var COPY = {
            revision: {
                title: root.dataset.revisionTitle || "Düzəliş istə",
                hint: root.dataset.revisionHint || "Müəllim nəyi düzəltməlidir? Səbəb ona bildiriş kimi gedəcək."
            },
            reject: {
                title: root.dataset.rejectTitle || "Rədd et",
                hint: root.dataset.rejectHint || "Rəddin səbəbini yazın — göndəriş İmtahan Mərkəzinə çatmayacaq."
            }
        };

        function renderCounter() {
            var value = (textEl.value || "").trim();
            var tooShort = value.length < minReason;
            if (counterEl) {
                var template = counterEl.dataset.template || "Ən azı {min} simvol — hazırda {n}.";
                counterEl.textContent = template.replace("{min}", minReason).replace("{n}", value.length);
                counterEl.classList.toggle("is-short", tooShort);
            }
            confirmBtn.disabled = tooShort;
        }

        function focusables() {
            return Array.prototype.slice
                .call(dialog.querySelectorAll("button, textarea, [href], input, select, [tabindex]"))
                .filter(function (el) {
                    return !el.disabled && el.offsetParent !== null;
                });
        }

        function trap(event) {
            if (event.key === "Escape") {
                closeDialog();
                return;
            }
            if (event.key !== "Tab") {
                return;
            }
            var items = focusables();
            if (!items.length) {
                return;
            }
            var first = items[0];
            var last = items[items.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }

        function openDialog(decision) {
            pendingDecision = decision;
            var copy = COPY[decision] || COPY.revision;
            if (titleEl) {
                titleEl.textContent = copy.title;
            }
            if (hintEl) {
                hintEl.textContent = copy.hint;
            }
            textEl.value = "";
            renderCounter();
            lastFocused = document.activeElement;
            dialog.hidden = false;
            document.addEventListener("keydown", trap, true);
            window.setTimeout(function () {
                textEl.focus();
            }, 0);
        }

        function closeDialog() {
            dialog.hidden = true;
            pendingDecision = "";
            document.removeEventListener("keydown", trap, true);
            if (lastFocused && typeof lastFocused.focus === "function") {
                lastFocused.focus();
            }
        }

        function submit(decision, reason) {
            decisionInput.value = decision;
            reasonInput.value = reason || "";
            form.submit();
        }

        root.addEventListener("click", function (event) {
            var button = event.target.closest("[data-qchair-action]");
            if (!button || !root.contains(button)) {
                return;
            }
            event.preventDefault();
            var decision = button.dataset.qchairAction;
            if (decision === "approve") {
                submit("approve", "");
                return;
            }
            openDialog(decision);
        });

        textEl.addEventListener("input", renderCounter);
        if (cancelBtn) {
            cancelBtn.addEventListener("click", closeDialog);
        }
        dialog.addEventListener("click", function (event) {
            if (event.target === dialog) {
                closeDialog();
            }
        });
        confirmBtn.addEventListener("click", function () {
            var value = (textEl.value || "").trim();
            if (value.length < minReason || !pendingDecision) {
                return;
            }
            submit(pendingDecision, value);
        });
    }

    if (window.EMSReady) {
        window.EMSReady(boot);
    } else {
        document.addEventListener("DOMContentLoaded", boot);
    }
})();
