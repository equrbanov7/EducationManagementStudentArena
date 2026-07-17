/* Mərkəz baxışı — 2 yollu qərar seçicisi.
 *
 * Radio (qəbul / geri qaytar) seçiminə görə uyğun panel açılır, gizli panelin
 * sahələri `disabled` olur (hər iki paneldə name="note" var — yalnız aktiv
 * olan POST-a düşsün), submit düyməsinin mətni/rəngi qərara uyğunlaşır.
 * Bank seçimində mövcud bank seçilərsə "yeni bankın adı" sahəsi gizlənir.
 */
(function () {
    "use strict";

    function initDecisionForm(form) {
        var panels = Array.prototype.slice.call(form.querySelectorAll(".js-qsubr-panel"));
        var radios = Array.prototype.slice.call(form.querySelectorAll('input[name="decision"]'));
        var submit = form.querySelector(".js-qsubr-submit");
        var submitLabel = form.querySelector(".js-qsubr-submit-label");
        var submitIcon = form.querySelector(".js-qsubr-submit-icon");
        var bankSelect = form.querySelector(".js-qsubr-bank");
        var newBankField = form.querySelector(".js-qsubr-newbank");

        function setPanelEnabled(panel, enabled) {
            panel.classList.toggle("is-open", enabled);
            panel.querySelectorAll("input, select, textarea").forEach(function (field) {
                field.disabled = !enabled;
            });
            if (enabled && panel.dataset.decision === "accept") {
                syncNewBankVisibility();
            }
            // Custom select-in toggle vəziyyətini yenilə (disabled görünüşü).
            panel.querySelectorAll("[data-bootstrap-select]").forEach(function (select) {
                if (select._syncBootstrapSelect) {
                    select._syncBootstrapSelect();
                }
            });
        }

        function syncNewBankVisibility() {
            if (!bankSelect || !newBankField) {
                return;
            }
            var isNewBank = !bankSelect.value;
            newBankField.style.display = isNewBank ? "" : "none";
            var input = newBankField.querySelector("input");
            if (input) {
                input.disabled = !isNewBank || bankSelect.disabled;
            }
        }

        function applyDecision(value) {
            panels.forEach(function (panel) {
                setPanelEnabled(panel, panel.dataset.decision === value);
            });
            if (!submit) {
                return;
            }
            submit.disabled = !value;
            submit.classList.remove("qb-btn-green", "qb-btn-outline-danger");
            if (value === "accept") {
                submit.classList.add("qb-btn-green");
                if (submitLabel) { submitLabel.textContent = submit.dataset.acceptLabel || ""; }
                if (submitIcon) { submitIcon.className = "fas fa-check js-qsubr-submit-icon"; }
            } else if (value === "reject") {
                submit.classList.add("qb-btn-outline-danger");
                if (submitLabel) { submitLabel.textContent = submit.dataset.rejectLabel || ""; }
                if (submitIcon) { submitIcon.className = "fas fa-rotate-left js-qsubr-submit-icon"; }
            } else {
                if (submitLabel) { submitLabel.textContent = submit.dataset.idleLabel || ""; }
                if (submitIcon) { submitIcon.className = "fas fa-gavel js-qsubr-submit-icon"; }
            }
        }

        radios.forEach(function (radio) {
            radio.addEventListener("change", function () {
                if (radio.checked) {
                    applyDecision(radio.value);
                }
            });
        });

        if (bankSelect) {
            bankSelect.addEventListener("change", syncNewBankVisibility);
        }

        // İlkin vəziyyət (geri düyməsi ilə qayıdışda seçim qala bilər).
        var checked = radios.filter(function (radio) { return radio.checked; })[0];
        applyDecision(checked ? checked.value : "");
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll(".js-qsubr-form").forEach(initDecisionForm);
    });
})();
