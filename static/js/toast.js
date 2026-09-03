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

    /* ── Proqram yolu ilə toast (AJAX əməlləri üçün) ───────────────────────────
     * Server-render olunmuş Django `messages` toast-ları ilə EYNİ markup/CSS
     * işlədilir — ona görə auto-hide, bağlama düyməsi və ESC davranışı yuxarıdakı
     * MutationObserver sayəsində PULSUZ gəlir (əlavə bağlama lazım deyil).
     *
     *   EMSToast.show("Tələbə əlavə olundu", "success");
     */
    var ICONS = {
        success: "fa-check",
        error: "fa-exclamation",
        danger: "fa-exclamation",
        warning: "fa-triangle-exclamation",
        info: "fa-info",
    };

    function container() {
        var box = document.querySelector(".toast-container");
        if (!box) {
            box = document.createElement("div");
            box.className = "toast-container";
            box.setAttribute("aria-live", "polite");
            box.setAttribute("aria-atomic", "true");
            document.body.appendChild(box);
        }
        return box;
    }

    function showToast(message, level, timeout) {
        if (!message) {
            return null;
        }
        var tag = ICONS[level] ? level : "info";
        var toast = document.createElement("div");
        toast.className = "alert alert-" + tag + " app-toast app-toast--" + tag + " fade show";
        toast.setAttribute("role", tag === "error" || tag === "danger" ? "alert" : "status");
        toast.setAttribute("data-auto-hide", String(timeout || 4000));
        toast.setAttribute("data-toast-item", "");

        var icon = document.createElement("span");
        icon.className = "app-toast__icon";
        icon.setAttribute("aria-hidden", "true");
        var i = document.createElement("i");
        i.className = "fas " + ICONS[tag];
        icon.appendChild(i);

        var body = document.createElement("span");
        body.className = "app-toast__body";
        body.textContent = message; // mətn — HTML inyeksiyası yoxdur

        var close = document.createElement("button");
        close.type = "button";
        close.className = "app-toast__close";
        close.setAttribute("data-toast-dismiss", "");
        // Etiket base.html-dən gəlir (xarici JS tərcümə tag-larından keçmir).
        var closeLabel = document.body ? document.body.getAttribute("data-toast-close-label") : "";
        if (closeLabel) {
            close.setAttribute("aria-label", closeLabel);
        }
        var x = document.createElement("i");
        x.className = "fas fa-xmark";
        x.setAttribute("aria-hidden", "true");
        close.appendChild(x);

        toast.appendChild(icon);
        toast.appendChild(body);
        toast.appendChild(close);
        container().appendChild(toast);
        return toast;
    }

    window.EMSToast = window.EMSToast || { show: showToast };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bootAutoHideMessages);
    } else {
        bootAutoHideMessages();
    }
})();
