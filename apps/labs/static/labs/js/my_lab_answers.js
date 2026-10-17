/*
 * my_lab_answers.js — «Mənim cavablarım» (2026-10-17, Paket E).
 * Cavab kartlarının aç/bağla düyməsi (`EMSDelegate`) + `?attempt=N` ilə əvvəlcədən açılan dialoq
 * (`#labAnswersConfig[data-preopen-modal]`, ortaq `EMSOverlay` ilə). Dialoqları açan «Bax» düymələri
 * `data-ems-overlay-open` ilə `ems_ui/overlay.js`-in özündə işləyir.
 */
(function () {
    "use strict";

    window.EMSDelegate.on("click", ".answer-toggle-btn", function (event, btn) {
        var card = document.getElementById("answer-item-" + btn.dataset.answerToggle);
        if (!card) { return; }
        var collapsed = card.classList.toggle("answer-collapsed");
        btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
        var icon = btn.querySelector("i");
        if (icon) {
            icon.classList.toggle("fa-chevron-down", collapsed);
            icon.classList.toggle("fa-chevron-up", !collapsed);
        }
    });

    window.EMSReady(function () {
        var cfg = document.getElementById("labAnswersConfig");
        var modalId = cfg && cfg.dataset.preopenModal;
        if (modalId && cfg.dataset.opened !== "1" && window.EMSOverlay) {
            cfg.dataset.opened = "1";
            window.EMSOverlay.open(modalId);
        }
    });
})();
