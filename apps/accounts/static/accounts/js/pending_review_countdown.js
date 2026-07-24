/*
 * pending_review_countdown.js
 * Source: extracted verbatim from the inline <script> in
 * _pending_review_content.html (setupReviewQueueCountdowns; CSP inline-removal).
 * Renders the recheck / anonymity countdown timers and reloads the page when a
 * window elapses. i18n strings are bridged via data-* on #pendingReviewCountdownI18n.
 * Per-node dataset guard + EMSReady.once keep it idempotent across AJAX swaps.
 */
(function () {
    "use strict";

    var shouldReload = false;

    function i18nFor(node, key, fallback) {
        return node ? (node.getAttribute(key) || fallback) : fallback;
    }

    window.EMSReady(function () {
        var countdownNodes = document.querySelectorAll("[data-review-queue-countdown]");
        if (!countdownNodes.length) {
            return;
        }

        var cfg = document.getElementById("pendingReviewCountdownI18n");
        var TXT_TIME_UP = i18nFor(cfg, "data-time-up", "");
        var TXT_ANON_PREFIX = i18nFor(cfg, "data-anon-prefix", "");
        var TXT_RECHECK_PREFIX = i18nFor(cfg, "data-recheck-prefix", "");
        var TXT_MIN = i18nFor(cfg, "data-min", "");
        var TXT_SEC = i18nFor(cfg, "data-sec", "");

        countdownNodes.forEach(function (node) {
            if (node.dataset.countdownBound === "1") {
                return;
            }
            node.dataset.countdownBound = "1";

            var secondsLeft = parseInt(node.getAttribute("data-seconds"), 10);
            if (Number.isNaN(secondsLeft)) {
                node.textContent = "";
                return;
            }

            function render() {
                if (secondsLeft <= 0) {
                    node.textContent = TXT_TIME_UP;
                    shouldReload = true;
                    return;
                }
                var minutes = Math.floor(secondsLeft / 60);
                var seconds = secondsLeft % 60;
                if (node.textContent.indexOf("Anonim") !== -1) {
                    node.textContent = TXT_ANON_PREFIX + " " + minutes + " " + TXT_MIN + " " + seconds + " " + TXT_SEC;
                    return;
                }
                node.textContent = TXT_RECHECK_PREFIX + " " + minutes + " " + TXT_MIN + " " + seconds + " " + TXT_SEC;
            }

            render();
            window.setInterval(function () {
                secondsLeft = Math.max(0, secondsLeft - 1);
                render();
            }, 1000);
        });

        window.EMSReady.once("pending-review-countdown-reload", function () {
            window.setInterval(function () {
                if (shouldReload) {
                    window.location.reload();
                }
            }, 1500);
        });
    });
})();
