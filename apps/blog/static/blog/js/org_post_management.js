/*
 * org_post_management.js
 * Source: apps/blog/templates/blog/org_post_management.html
 * Org post moderation: delete + request-changes modals. Post title / moderate URL
 * read from data-* on the trigger buttons. Behavior identical to the former inline
 * script (delegated clicks so it is AJAX-safe; one-time listeners bound once).
 */
(function () {
    "use strict";
    if (window.__ORG_POST_MGMT_BOUND) { return; }
    window.__ORG_POST_MGMT_BOUND = true;

    function $(id) { return document.getElementById(id); }

    /* Delete modal */
    var delModal = $("orgDeleteModal");
    var delForm = $("orgDeleteForm");
    var delTitle = $("orgDeletePostTitle");
    var delReason = $("orgDeleteReason");

    function closeDelModal() {
        if (!delModal) { return; }
        delModal.classList.remove("active");
        document.body.classList.remove("modal-open");
    }

    /* Feedback modal */
    var fbModal = $("orgFeedbackModal");
    var fbForm = $("orgFeedbackForm");
    var fbTitle = $("orgFeedbackPostTitle");
    var fbText = $("orgFeedbackText");

    function closeFbModal() {
        if (!fbModal) { return; }
        fbModal.classList.remove("active");
        document.body.classList.remove("modal-open");
    }

    document.addEventListener("click", function (e) {
        var delBtn = e.target.closest(".js-org-delete-post");
        if (delBtn && delModal) {
            delTitle.textContent = delBtn.dataset.postTitle;
            delForm.action = delBtn.dataset.moderateUrl;
            delReason.value = "";
            delModal.classList.add("active");
            document.body.classList.add("modal-open");
            return;
        }

        var fbBtn = e.target.closest(".js-org-feedback-post");
        if (fbBtn && fbModal) {
            fbTitle.textContent = fbBtn.dataset.postTitle;
            fbForm.action = fbBtn.dataset.moderateUrl;
            fbText.value = "";
            fbModal.classList.add("active");
            document.body.classList.add("modal-open");
            return;
        }

        if (e.target.id === "orgDeleteCancel") { closeDelModal(); return; }
        if (e.target === delModal) { closeDelModal(); return; }
        if (e.target.id === "orgFeedbackCancel") { closeFbModal(); return; }
        if (e.target === fbModal) { closeFbModal(); return; }
    });

    /* Escape closes either modal */
    document.addEventListener("keydown", function (e) {
        if (e.key !== "Escape") { return; }
        if (delModal && delModal.classList.contains("active")) { closeDelModal(); }
        if (fbModal && fbModal.classList.contains("active")) { closeFbModal(); }
    });
})();
