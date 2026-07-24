/*
 * pending_post_approvals.js
 * Source: apps/accounts/templates/accounts/profile/sections/_pending_post_approvals.html
 * Pending-post-approvals section: debounced auto-filter form, content show-more/less
 * toggle, shared confirmation modal + action buttons (approve/reject/needs-changes).
 * i18n strings read from #pending-post-approvals-config data-*; CSRF not needed (form
 * submit). AJAX-safe: EMSReady-wrapped, null-safe, per-element/window idempotency guards.
 */
(function () {
    "use strict";

    window.EMSReady(function () {
        var panel = document.querySelector(".profile-section--pending-post-approvals");
        if (!panel) { return; }

        var cfgEl = document.getElementById("pending-post-approvals-config");
        var I18N = {
            confirmTitle: (cfgEl && cfgEl.dataset.i18nConfirmTitle) || "",
            reasonRequired: (cfgEl && cfgEl.dataset.i18nReasonRequired) || ""
        };

        /* ---- Auto-filter form ---- */
        panel.querySelectorAll("[data-auto-filter-form]").forEach(function (form) {
            if (!form || form.dataset.autoFilterBound === "1") { return; }
            form.dataset.autoFilterBound = "1";

            var debounceHandle = null;
            var textFields = form.querySelectorAll('input[type="text"], input[type="search"]');
            var selects = form.querySelectorAll("select");

            function submitForm() {
                if (typeof form.requestSubmit === "function") { form.requestSubmit(); return; }
                form.submit();
            }

            textFields.forEach(function (field) {
                field.addEventListener("input", function () {
                    window.clearTimeout(debounceHandle);
                    debounceHandle = window.setTimeout(submitForm, 350);
                });
                field.addEventListener("keydown", function (event) {
                    if (event.key === "Enter") { event.preventDefault(); window.clearTimeout(debounceHandle); submitForm(); }
                });
            });
            selects.forEach(function (select) { select.addEventListener("change", submitForm); });
        });

        /* ---- Content toggle ---- */
        panel.querySelectorAll("[data-pending-post-toggle]").forEach(function (button) {
            if (!button || button.dataset.toggleBound === "1") { return; }
            button.dataset.toggleBound = "1";
            button.addEventListener("click", function () {
                var container = button.closest("[data-pending-post-content]");
                if (!container) { return; }
                var preview = container.querySelector("[data-pending-post-preview]");
                var full = container.querySelector("[data-pending-post-full]");
                if (!preview || !full) { return; }
                var isExpanded = button.getAttribute("aria-expanded") === "true";
                preview.hidden = !isExpanded;
                full.hidden = isExpanded;
                button.setAttribute("aria-expanded", isExpanded ? "false" : "true");
                button.textContent = isExpanded
                    ? (button.dataset.collapsedLabel || "Show more")
                    : (button.dataset.expandedLabel || "Show less");
                container.classList.toggle("is-expanded", !isExpanded);
            });
        });

        /* ---- Shared confirmation modal ---- */
        var modal = document.getElementById("postActionConfirmModal");
        var modalTitle = document.getElementById("postActionConfirmTitle");
        var modalMsg = document.getElementById("postActionConfirmMsg");
        var modalOk = document.getElementById("postActionConfirmOk");
        var modalCancel = document.getElementById("postActionConfirmCancel");
        var pendingCallback = null;

        function openModal(title, msg, onConfirm) {
            modalTitle.textContent = title;
            modalMsg.textContent = msg;
            pendingCallback = onConfirm;
            modal.style.display = "flex";
            modalOk.focus();
        }

        function closeModal() {
            modal.style.display = "none";
            pendingCallback = null;
        }

        if (modal && modal.dataset.ppaModalBound !== "1") {
            modal.dataset.ppaModalBound = "1";
            if (modalCancel) { modalCancel.addEventListener("click", closeModal); }
            if (modalOk) {
                modalOk.addEventListener("click", function () {
                    var cb = pendingCallback;
                    closeModal();
                    if (cb) { cb(); }
                });
            }
            modal.addEventListener("click", function (e) { if (e.target === modal) { closeModal(); } });
        }

        // ESC — document-level listener registered ONCE (script re-runs on AJAX swap,
        // so it must not stack). The modal is looked up by id at event time so we do
        // not hold onto a detached reference.
        if (!window.__emsPendingEscBound) {
            window.__emsPendingEscBound = true;
            document.addEventListener("keydown", function (e) {
                if (e.key !== "Escape") { return; }
                var m = document.getElementById("postActionConfirmModal");
                if (m && m.style.display === "flex") { m.style.display = "none"; }
            });
        }

        /* ---- Action button handler (all action buttons use js-post-action-btn) ---- */
        panel.querySelectorAll(".js-post-action-btn").forEach(function (btn) {
            if (btn.dataset.ppaActionBound === "1") { return; }
            btn.dataset.ppaActionBound = "1";
            btn.addEventListener("click", function () {
                var form = btn.closest("form");
                if (!form) { return; }

                var action = btn.dataset.action || "";
                var confirmTitle = btn.dataset.confirmTitle || I18N.confirmTitle;
                var confirmMsg = btn.dataset.confirmMsg || "";
                var postTitle = (form.dataset.postTitle || "").trim();
                var fullMsg = postTitle ? '"' + postTitle + '"\n' + confirmMsg : confirmMsg;

                openModal(confirmTitle, fullMsg, function () {
                    /* Validate feedback textarea if present and required */
                    var reasonField = form.querySelector(".pending-post-moderate-reason");
                    if (reasonField && reasonField.required && !reasonField.value.trim()) {
                        reasonField.focus();
                        reasonField.classList.add("is-invalid");
                        var existing = form.querySelector(".moderate-reason-error");
                        if (!existing) {
                            var errDiv = document.createElement("div");
                            errDiv.className = "invalid-feedback moderate-reason-error";
                            errDiv.style.display = "block";
                            errDiv.textContent = I18N.reasonRequired;
                            reasonField.parentNode.insertBefore(errDiv, reasonField.nextSibling);
                        }
                        return;
                    }
                    if (reasonField) {
                        reasonField.classList.remove("is-invalid");
                        var err = form.querySelector(".moderate-reason-error");
                        if (err) { err.remove(); }
                    }

                    /* Set dynamic action input if the form uses one */
                    var actionInput = form.querySelector("input.js-form-action[name='action']");
                    if (actionInput) { actionInput.value = action; }

                    form.submit();
                });
            });
        });
    });
})();
