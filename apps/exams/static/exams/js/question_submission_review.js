/* Mərkəz baxışı — 3 yollu qərar seçicisi (qəbul / düzəliş / rədd).
 *
 * Panel bir neçə qərara xidmət edə bilər: `data-decision` boşluqla ayrılmış
 * siyahıdır (məs. "reject revision" — hər ikisi eyni səbəb sahəsini işlədir).
 * Radio seçiminə görə uyğun panel açılır, gizli panelin
 * sahələri `disabled` olur (hər iki paneldə name="note" var — yalnız aktiv
 * olan POST-a düşsün), submit düyməsinin mətni/rəngi qərara uyğunlaşır.
 * Bank seçimində mövcud bank seçilərsə "yeni bankın adı" sahəsi gizlənir.
 *
 * Paket C 2026-10-17: düymə tonu ems_ui sinifləri ilə (ems-btn--success/warning/danger);
 * AJAX-safe — `EMSReady` + formada `data-qsubr-ready` bayrağı (təkrar bağlanma yoxdur).
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
            if (enabled && panel.dataset.decision.indexOf("accept") !== -1) {
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
            newBankField.hidden = !isNewBank;
            var input = newBankField.querySelector("input");
            if (input) {
                input.disabled = !isNewBank || bankSelect.disabled;
            }
        }

        function applyDecision(value) {
            panels.forEach(function (panel) {
                var owners = (panel.dataset.decision || "").split(/\s+/);
                setPanelEnabled(panel, Boolean(value) && owners.indexOf(value) !== -1);
            });
            if (!submit) {
                return;
            }
            submit.disabled = !value;
            submit.classList.remove("ems-btn--success", "ems-btn--warning", "ems-btn--danger");
            if (value === "accept") {
                submit.classList.add("ems-btn--success");
                if (submitLabel) { submitLabel.textContent = submit.dataset.acceptLabel || ""; }
                if (submitIcon) { submitIcon.className = "fas fa-check js-qsubr-submit-icon"; }
            } else if (value === "revision") {
                submit.classList.add("ems-btn--warning");
                if (submitLabel) { submitLabel.textContent = submit.dataset.revisionLabel || ""; }
                if (submitIcon) { submitIcon.className = "fas fa-pen js-qsubr-submit-icon"; }
            } else if (value === "reject") {
                submit.classList.add("ems-btn--danger");
                if (submitLabel) { submitLabel.textContent = submit.dataset.rejectLabel || ""; }
                if (submitIcon) { submitIcon.className = "fas fa-ban js-qsubr-submit-icon"; }
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

    function boot() {
        document.querySelectorAll(".js-qsubr-form").forEach(function (form) {
            if (form.dataset.qsubrReady === "1") {
                return;
            }
            form.dataset.qsubrReady = "1";
            initDecisionForm(form);
        });
    }

    if (window.EMSReady) {
        window.EMSReady(boot);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
