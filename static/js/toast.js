/**
 * Toast auto-hide functionality.
 * Auto-dismisses alert messages after the specified timeout.
 */
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.toast-container .alert[data-auto-hide]').forEach(function (alert) {
        var hideTime = parseInt(alert.dataset.autoHide) || 5000;

        setTimeout(function () {
            alert.classList.add('fade-out');
            setTimeout(function () {
                alert.remove();
            }, 300);
        }, hideTime);
    });
});
