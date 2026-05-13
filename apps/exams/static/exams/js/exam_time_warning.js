(function () {
    function storageGet(key) {
        if (!key) {
            return "";
        }
        try {
            return window.localStorage.getItem(key) || "";
        } catch (error) {
            return "";
        }
    }

    function storageSet(key, value) {
        if (!key) {
            return;
        }
        try {
            window.localStorage.setItem(key, value);
        } catch (error) {
            // localStorage can be unavailable in private windows; the in-memory flag still protects this page view.
        }
    }

    function init(options) {
        var config = options || {};
        var modal = document.getElementById(config.modalId || "examTimeWarningModal");
        if (!modal) {
            return null;
        }

        var closeBtn = modal.querySelector("[data-exam-time-warning-close]");
        var thresholdSeconds = parseInt(config.thresholdSeconds, 10);
        var autoCloseMs = parseInt(config.autoCloseMs, 10);
        var storageKey = config.storageKey || "";
        var hasShown = storageGet(storageKey) === "1";
        var closeTimer = null;

        if (!Number.isFinite(thresholdSeconds) || thresholdSeconds <= 0) {
            thresholdSeconds = 300;
        }
        if (!Number.isFinite(autoCloseMs) || autoCloseMs <= 0) {
            autoCloseMs = 5000;
        }

        function hide() {
            window.clearTimeout(closeTimer);
            closeTimer = null;
            modal.classList.remove("is-visible");
            modal.setAttribute("aria-hidden", "true");
        }

        function show() {
            if (hasShown) {
                return;
            }
            hasShown = true;
            storageSet(storageKey, "1");
            modal.classList.add("is-visible");
            modal.setAttribute("aria-hidden", "false");
            if (closeBtn && typeof closeBtn.focus === "function") {
                try {
                    closeBtn.focus({ preventScroll: true });
                } catch (error) {
                    closeBtn.focus();
                }
            }
            closeTimer = window.setTimeout(hide, autoCloseMs);
        }

        if (closeBtn) {
            closeBtn.addEventListener("click", hide);
        }
        modal.addEventListener("click", function (event) {
            if (event.target === modal) {
                hide();
            }
        });

        return {
            maybeShow: function (remainingSeconds) {
                var remaining = parseInt(remainingSeconds, 10);
                if (Number.isFinite(remaining) && remaining > 0 && remaining <= thresholdSeconds) {
                    show();
                }
            },
            hide: hide
        };
    }

    window.ExamTimeWarning = {
        init: init
    };
})();
