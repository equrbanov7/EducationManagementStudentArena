/*
 * superadmin_post_management.js
 * Source: apps/blog/templates/blog/superadmin_post_management.html
 * Superadmin post delete modal. Post title / delete URL read from data-* on the
 * trigger buttons. Behavior identical to the former inline script (delegated
 * clicks so it is AJAX-safe; one-time listeners bound once).
 */
(function () {
    "use strict";
    if (window.__SA_POST_MGMT_BOUND) { return; }
    window.__SA_POST_MGMT_BOUND = true;

    function $(id) { return document.getElementById(id); }

    var modal = $("saDeleteModal");
    var form = $("saDeleteForm");
    var titleSpan = $("saDeletePostTitle");
    var reasonInput = $("saDeleteReason");

    function closeModal() {
        if (!modal) { return; }
        modal.classList.remove("active");
        document.body.classList.remove("modal-open");
    }

    document.addEventListener("click", function (e) {
        var btn = e.target.closest(".js-sa-delete-post");
        if (btn && modal) {
            titleSpan.textContent = btn.dataset.postTitle;
            form.action = btn.dataset.deleteUrl;
            reasonInput.value = "";
            modal.classList.add("active");
            document.body.classList.add("modal-open");
            return;
        }

        if (e.target.id === "saDeleteCancel") { closeModal(); return; }
        if (e.target === modal) { closeModal(); return; }
    });

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && modal && modal.classList.contains("active")) {
            closeModal();
        }
    });
})();
