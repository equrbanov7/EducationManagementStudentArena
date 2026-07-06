(function () {
    "use strict";

    function initFinalResultTimeout() {
        var el = document.querySelector("[data-final-result-timeout]");
        if (!el || el.getAttribute("data-final-result-timeout-bound") === "1") {
            return;
        }
        el.setAttribute("data-final-result-timeout-bound", "1");

        var seconds = parseInt(el.getAttribute("data-final-result-timeout-seconds") || "300", 10);
        var url = el.getAttribute("data-final-result-timeout-url") || "";
        if (!url) {
            return;
        }

        window.setTimeout(function () {
            window.location.replace(url);
        }, Math.max(seconds, 0) * 1000);
    }

    if (window.EMSReady) {
        window.EMSReady(initFinalResultTimeout);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initFinalResultTimeout);
    } else {
        initFinalResultTimeout();
    }
}());
