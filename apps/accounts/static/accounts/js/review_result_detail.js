/*
 * review_result_detail.js
 * Source: apps/accounts/templates/accounts/review_result_detail.html
 * Collapses/expands a lab-answer card when its toggle is clicked.
 * Delegated on document (EMSDelegate) → idempotent and AJAX-safe.
 */
(function () {
    "use strict";

    EMSDelegate.on("click", ".review-answer-toggle", function (e, btn) {
        var id = btn.getAttribute("data-review-toggle");
        var card = document.getElementById("review-answer-" + id);
        if (!card) return;
        var collapsed = card.classList.toggle("is-collapsed");
        var icon = btn.querySelector("i");
        if (icon) {
            icon.classList.toggle("fa-chevron-down", collapsed);
            icon.classList.toggle("fa-chevron-up", !collapsed);
        }
    });
})();
