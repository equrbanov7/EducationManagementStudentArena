(function () {
    "use strict";

    function pad(n) {
        return (n < 10 ? "0" : "") + n;
    }

    function formatClock(totalSeconds) {
        var s = Math.max(0, totalSeconds | 0);
        var m = Math.floor(s / 60);
        return pad(m) + ":" + pad(s % 60);
    }

    function initFinalResultTimeout() {
        var el = document.querySelector("[data-final-result-timeout]");
        if (!el || el.getAttribute("data-final-result-timeout-bound") === "1") {
            return;
        }
        el.setAttribute("data-final-result-timeout-bound", "1");

        var remaining = parseInt(el.getAttribute("data-final-result-timeout-seconds") || "300", 10);
        var url = el.getAttribute("data-final-result-timeout-url") || "";
        if (!url) {
            return;
        }
        if (isNaN(remaining) || remaining < 0) {
            remaining = 0;
        }

        var timerWrap = document.querySelector("[data-final-result-timer]");
        var countEl = document.querySelector("[data-final-result-countdown]");
        if (timerWrap) {
            timerWrap.hidden = false;
        }

        function render() {
            if (countEl) {
                countEl.textContent = formatClock(remaining);
            }
            // Son 60 saniyə — təcili görünüş.
            if (timerWrap) {
                timerWrap.classList.toggle("is-urgent", remaining <= 60);
            }
        }

        function redirect() {
            window.location.replace(url);
        }

        render();
        if (remaining <= 0) {
            redirect();
            return;
        }

        var intervalId = window.setInterval(function () {
            remaining -= 1;
            if (remaining <= 0) {
                render();
                window.clearInterval(intervalId);
                redirect();
                return;
            }
            render();
        }, 1000);
    }

    if (window.EMSReady) {
        window.EMSReady(initFinalResultTimeout);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initFinalResultTimeout);
    } else {
        initFinalResultTimeout();
    }
}());
