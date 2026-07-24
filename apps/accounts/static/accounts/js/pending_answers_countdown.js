/*
 * pending_answers_countdown.js
 * Source: extracted verbatim from the inline <script> in
 * _pending_answers_content.html (setupPendingAnswerCountdowns; CSP inline-removal).
 * Counts down the "result opens in ..." timers. i18n strings are bridged via
 * data-* on #pendingAnswersCountdownI18n. Per-node dataset guard keeps it
 * idempotent across AJAX section swaps.
 */
(function () {
    "use strict";

    function i18nFor(node, key, fallback) {
        return node ? (node.getAttribute(key) || fallback) : fallback;
    }

    window.EMSReady(function () {
        var nodes = document.querySelectorAll("[data-pending-answer-countdown]");
        if (!nodes.length) {
            return;
        }

        var cfg = document.getElementById("pendingAnswersCountdownI18n");
        var TXT_NOT_READY = i18nFor(cfg, "data-not-ready", "");
        var TXT_RESULT_PREFIX = i18nFor(cfg, "data-result-prefix", "");
        var TXT_MIN = i18nFor(cfg, "data-min", "");
        var TXT_SEC_SUFFIX = i18nFor(cfg, "data-sec-suffix", "");

        nodes.forEach(function (node) {
            if (node.dataset.countdownBound === "1") {
                return;
            }
            node.dataset.countdownBound = "1";

            var secondsLeft = parseInt(node.getAttribute("data-seconds"), 10);
            if (Number.isNaN(secondsLeft) || secondsLeft <= 0) {
                node.textContent = TXT_NOT_READY;
                return;
            }

            function render() {
                var minutes = Math.floor(secondsLeft / 60);
                var seconds = secondsLeft % 60;
                node.textContent = TXT_RESULT_PREFIX + " " + minutes + " " + TXT_MIN + " " + seconds + " " + TXT_SEC_SUFFIX;
            }

            render();
            window.setInterval(function () {
                secondsLeft = Math.max(0, secondsLeft - 1);
                render();
            }, 1000);
        });
    });
})();
