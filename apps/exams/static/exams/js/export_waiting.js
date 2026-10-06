/* Source template: apps/exams/templates/exams/teacher/export_waiting.html
 * Polls the export status endpoint and redirects to the download when ready.
 * Dynamic values (URLs, i18n) are bridged via data-* attributes on #exportWaitingCard.
 *
 * Tutum 2026-10-06: status endpointi DƏRHAL cavab verir (server sorğu axınında
 * yatmır), ona görə poll geri çəkilmə (backoff) ilə gedir: 1 s → ×1.5 → 5 s
 * tavan, ümumi büdcə ~10 dəq (əvvəlki 240 × 2.5 s ilə eyni). AJAX-safe:
 * EMSReady + kartda idempotent bayraq (iki dəfə init → bir poll dövrü).
 */
(function () {
    "use strict";

    var POLL_START_MS = 1000;
    var POLL_MAX_MS = 5000;
    var POLL_FACTOR = 1.5;
    var POLL_ERROR_EXTRA_MS = 1500;
    var POLL_BUDGET_MS = 10 * 60 * 1000;

    function init() {
        var card = document.getElementById("exportWaitingCard");
        if (!card || card.dataset.exportPollStarted === "1") return;
        card.dataset.exportPollStarted = "1";

        var statusUrl = card.getAttribute("data-status-url");
        var downloadUrl = card.getAttribute("data-download-url");
        var failedText = card.getAttribute("data-i18n-failed") || "";
        var timeoutText = card.getAttribute("data-i18n-timeout") || "";
        var errorEl = card.querySelector("[data-waiting-error]");
        var spinnerEl = card.querySelector("[data-waiting-spinner]");
        var startedAt = Date.now();
        var delay = POLL_START_MS;

        function fail(message) {
            if (spinnerEl) spinnerEl.hidden = true;
            if (errorEl) {
                errorEl.textContent = message;
                errorEl.hidden = false;
            }
        }

        function scheduleNext(extraMs) {
            if (Date.now() - startedAt >= POLL_BUDGET_MS) {
                fail(timeoutText);
                return;
            }
            setTimeout(poll, delay + (extraMs || 0));
            delay = Math.min(POLL_MAX_MS, Math.round(delay * POLL_FACTOR));
        }

        function poll() {
            fetch(statusUrl, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                credentials: "same-origin"
            })
                .then(function (r) { return r.json(); })
                .then(function (json) {
                    if (json.status === "success") {
                        window.location.href = downloadUrl;
                        return;
                    }
                    if (json.status === "failed") {
                        fail(json.error || failedText);
                        return;
                    }
                    scheduleNext(0);
                })
                .catch(function () {
                    scheduleNext(POLL_ERROR_EXTRA_MS);
                });
        }

        poll();
    }

    if (typeof window.EMSReady === "function") {
        window.EMSReady(init);
    } else {
        init();
    }
})();
