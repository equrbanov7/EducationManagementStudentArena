/**
 * Toast auto-hide functionality.
 * Auto-dismisses alert messages after the specified timeout.
 */
function initAutoHideMessages(root) {
    var scope = root || document;
    var selector = '.toast-container .alert[data-auto-hide], [data-profile-flash-message]';

    scope.querySelectorAll(selector).forEach(function (messageEl) {
        if (messageEl.dataset.autoHideReady === '1') {
            return;
        }

        messageEl.dataset.autoHideReady = '1';

        var hideTime = parseInt(messageEl.dataset.autoHide, 10) || 5000;
        var dismiss = function () {
            if (!messageEl || !messageEl.parentNode || messageEl.dataset.dismissing === '1') {
                return;
            }

            messageEl.dataset.dismissing = '1';

            if (messageEl.matches('.toast-container .alert')) {
                messageEl.classList.add('fade-out');
                window.setTimeout(function () {
                    if (messageEl.parentNode) {
                        messageEl.remove();
                    }
                }, 300);
                return;
            }

            messageEl.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
            messageEl.style.opacity = '0';
            messageEl.style.transform = 'translateY(-6px)';
            window.setTimeout(function () {
                if (messageEl.parentNode) {
                    messageEl.remove();
                }
            }, 200);
        };

        window.setTimeout(dismiss, hideTime);
        messageEl.addEventListener('click', dismiss);
        messageEl.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                dismiss();
            }
        });
    });
}

function watchAutoHideMessages() {
    if (!document.body || typeof MutationObserver !== 'function') {
        return;
    }

    var observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            mutation.addedNodes.forEach(function (node) {
                if (!node || node.nodeType !== Node.ELEMENT_NODE) {
                    return;
                }

                if (node.matches && node.matches('.toast-container .alert[data-auto-hide], [data-profile-flash-message]')) {
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

function bootAutoHideMessages() {
    initAutoHideMessages(document);
    watchAutoHideMessages();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootAutoHideMessages);
} else {
    bootAutoHideMessages();
}
