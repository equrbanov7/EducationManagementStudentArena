/*
 * notification_list.js
 * Source: apps/notifications/templates/notifications/notification_list.html
 * Bulk-select / select-all behaviour for the notifications list.
 * AJAX-safe: EMSReady for initial reveal, EMSDelegate for change events.
 */
(function () {
    "use strict";

    function updateBulkBar() {
        var btn = document.getElementById("bulk-delete-btn");
        if (!btn) return;
        var checkedCount = document.querySelectorAll(".notification-checkbox:checked").length;
        btn.disabled = checkedCount === 0;
    }

    window.EMSReady(function () {
        var selectAll = document.getElementById("select-all-notifications");
        var bulkBar = document.getElementById("bulk-actions-bar");
        if (selectAll && bulkBar) {
            // Reveal the bulk bar (was hidden via the --hidden class).
            bulkBar.classList.remove("notifications-bulk-actions--hidden");
            updateBulkBar();
        }
    });

    EMSDelegate.on("change", "#select-all-notifications", function (e, selectAll) {
        var checkboxes = document.querySelectorAll(".notification-checkbox");
        checkboxes.forEach(function (cb) {
            cb.checked = selectAll.checked;
        });
        updateBulkBar();
    });

    EMSDelegate.on("change", ".notification-checkbox", function () {
        var selectAll = document.getElementById("select-all-notifications");
        var checkboxes = document.querySelectorAll(".notification-checkbox");
        if (selectAll) {
            selectAll.checked =
                document.querySelectorAll(".notification-checkbox:checked").length ===
                checkboxes.length;
        }
        updateBulkBar();
    });
})();
