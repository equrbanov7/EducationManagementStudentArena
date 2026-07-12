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

        // Mütləq deadline: səyyah setInterval-ı fon tabında throttle edir
        // (təxminən dəqiqədə bir) — sadə "remaining -= 1" sayğacı sürüşüb
        // donur. Deadline + Date.now() ilə hər render dəqiq qalanı hesablayır,
        // fokus qayıdanda dərhal düzəlir.
        var deadlineMs = Date.now() + remaining * 1000;
        var intervalId = null;

        function secondsLeft() {
            return Math.max(0, Math.round((deadlineMs - Date.now()) / 1000));
        }

        function redirect() {
            if (intervalId !== null) {
                window.clearInterval(intervalId);
                intervalId = null;
            }
            window.location.replace(url);
        }

        function render() {
            var left = secondsLeft();
            if (countEl) {
                countEl.textContent = formatClock(left);
            }
            // Son 60 saniyə — təcili görünüş.
            if (timerWrap) {
                timerWrap.classList.toggle("is-urgent", left <= 60);
            }
            if (left <= 0) {
                redirect();
            }
        }

        render();
        if (secondsLeft() <= 0) {
            return;
        }

        intervalId = window.setInterval(render, 1000);
        // Fon tabından qayıdanda dərhal düzgün dəyəri göstər (throttle drift-i sıfırla).
        document.addEventListener("visibilitychange", function () {
            if (!document.hidden) {
                render();
            }
        });
        window.addEventListener("focus", render);
    }

    if (window.EMSReady) {
        window.EMSReady(initFinalResultTimeout);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initFinalResultTimeout);
    } else {
        initFinalResultTimeout();
    }
}());
