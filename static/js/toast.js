/**
 * Global flash toast behavior.
 * Handles auto-hide and close buttons without relying on Bootstrap's data API.
 */
(function () {
    "use strict";

    var TOAST_SELECTOR =
        ".toast-container [data-auto-hide], .toast-container .alert[data-auto-hide], [data-toast-item][data-auto-hide]";

    function dismissToast(messageEl) {
        if (!messageEl || !messageEl.parentNode || messageEl.dataset.dismissing === "1") {
            return;
        }

        messageEl.dataset.dismissing = "1";
        messageEl.classList.add("fade-out");

        window.setTimeout(function () {
            if (messageEl.parentNode) {
                messageEl.remove();
            }
        }, 240);
    }

    function initAutoHideMessages(root) {
        var scope = root || document;

        scope.querySelectorAll(TOAST_SELECTOR).forEach(function (messageEl) {
            if (messageEl.dataset.autoHideReady === "1") {
                return;
            }

            messageEl.dataset.autoHideReady = "1";

            var hideTime = parseInt(messageEl.dataset.autoHide, 10);
            if (!Number.isFinite(hideTime) || hideTime <= 0) {
                hideTime = 3000;
            }

            window.setTimeout(function () {
                dismissToast(messageEl);
            }, hideTime);
        });
    }

    function watchAutoHideMessages() {
        if (!document.body || typeof MutationObserver !== "function") {
            return;
        }

        var observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (!node || node.nodeType !== Node.ELEMENT_NODE) {
                        return;
                    }

                    if (node.matches && node.matches(TOAST_SELECTOR)) {
                        initAutoHideMessages(node.parentNode || document);
                        return;
                    }

                    if (node.querySelectorAll) {
                        initAutoHideMessages(node);
                    }
                });
            });
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }

    function bindDismissButtons() {
        document.addEventListener(
            "click",
            function (event) {
                var closeButton = event.target.closest("[data-toast-dismiss]");
                if (!closeButton) {
                    return;
                }

                var toast = closeButton.closest(".toast-container .alert, [data-toast-item]");
                if (!toast) {
                    return;
                }

                event.preventDefault();
                event.stopPropagation();
                dismissToast(toast);
            },
            true
        );

        document.addEventListener("keydown", function (event) {
            if (event.key !== "Escape") {
                return;
            }

            var latestToast = document.querySelector(".toast-container [data-toast-item]:last-child");
            if (latestToast) {
                dismissToast(latestToast);
            }
        });
    }

    function bootAutoHideMessages() {
        initAutoHideMessages(document);
        watchAutoHideMessages();
        bindDismissButtons();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bootAutoHideMessages);
    } else {
        bootAutoHideMessages();
    }
})();
