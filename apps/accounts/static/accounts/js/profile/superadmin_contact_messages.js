/*
 * superadmin_contact_messages.js
 * Source: apps/accounts/templates/accounts/profile/sections/superadmin/_superadmin_contact_messages.html
 * "Send from" mailbox picker for the contact/trial reply forms: clicking an option
 * updates the hidden input, the visible label, and the active/aria-selected state.
 * Static behavior (no template vars). AJAX-safe via delegated listener on document,
 * registered once (window guard) so swaps do not stack handlers.
 */
(function () {
    "use strict";

    if (window._EMS_CONTACT_REPLY_FROM_BOUND) { return; }
    window._EMS_CONTACT_REPLY_FROM_BOUND = true;

    window.EMSDelegate.on("click", "[data-contact-reply-from-option]", function (e, option) {
        var picker = option.closest("[data-contact-reply-from]");
        if (!picker) { return; }
        var row = picker.closest(".contact-form-row");
        var input = row ? row.querySelector("[data-contact-reply-from-input]") : null;
        var label = picker.querySelector("[data-contact-reply-from-label]");
        if (!input || !label) { return; }

        input.value = option.getAttribute("data-value") || "";
        label.textContent = option.getAttribute("data-label") || option.textContent.trim();
        picker.querySelectorAll("[data-contact-reply-from-option]").forEach(function (item) {
            var isActive = item === option;
            item.classList.toggle("is-active", isActive);
            item.setAttribute("aria-selected", isActive ? "true" : "false");
        });
    });
})();
