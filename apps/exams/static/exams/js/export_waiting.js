/* Source template: apps/exams/templates/exams/teacher/export_waiting.html
 * Polls the export status endpoint and redirects to the download when ready.
 * Dynamic values (URLs, i18n) are bridged via data-* attributes on #exportWaitingCard.
 */
(function () {
    "use strict";
    var card = document.getElementById("exportWaitingCard");
    if (!card) return;
    var statusUrl = card.getAttribute("data-status-url");
    var downloadUrl = card.getAttribute("data-download-url");
    var failedText = card.getAttribute("data-i18n-failed") || "";
    var timeoutText = card.getAttribute("data-i18n-timeout") || "";
    var errorEl = card.querySelector("[data-waiting-error]");
    var spinnerEl = card.querySelector("[data-waiting-spinner]");
    var attempts = 0;

    function fail(message) {
        if (spinnerEl) spinnerEl.hidden = true;
        if (errorEl) {
            errorEl.textContent = message;
            errorEl.hidden = false;
        }
    }

    function poll() {
        attempts += 1;
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
                if (attempts >= 240) {
                    fail(timeoutText);
                    return;
                }
                setTimeout(poll, 2500);
            })
            .catch(function () {
                if (attempts >= 240) {
                    fail(timeoutText);
                    return;
                }
                setTimeout(poll, 4000);
            });
    }

    poll();
})();
