/*
 * student_org_request.js
 * Source: extracted verbatim from the inline <script> in
 * _student_org_request_content.html (CSP inline-removal, 2026-07).
 * Live character counter for the join-request message textarea.
 * Idempotent (dataset guard) and AJAX-safe (re-runs on section swaps).
 */
(function () {
    "use strict";

    window.EMSReady(function () {
        var messageInput = document.getElementById("studentOrgRequestMessage");
        if (!messageInput) { return; }
        var counterId = messageInput.getAttribute("data-char-count-target");
        if (!counterId) { return; }
        var counter = document.getElementById(counterId);
        if (!counter) { return; }

        function syncCounter() {
            counter.textContent = String((messageInput.value || "").length);
        }

        if (messageInput.dataset.charCountBound !== "1") {
            messageInput.dataset.charCountBound = "1";
            messageInput.addEventListener("input", syncCounter);
        }
        syncCounter();
    });
})();
