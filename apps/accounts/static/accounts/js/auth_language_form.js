/*
 * auth_language_form.js
 * Source: apps/accounts/templates/accounts/login_portal.html
 *         apps/accounts/templates/accounts/login.html
 * Auth-page language switcher: on <select> change, stash the current relative
 * URL into the hidden `next` input and submit the set_language form.
 * NOTE: auth pages extend base_auth.html which does NOT load ems_ajax_init.js,
 * so EMSReady/EMSDelegate are unavailable here — this stays a plain IIFE
 * (these pages are never AJAX-swapped).
 */
(function () {
    "use strict";
    var form = document.querySelector("[data-auth-language-form]");
    if (!form) {
        return;
    }
    var select = form.querySelector("[data-auth-language-select]");
    var nextInput = form.querySelector('input[name="next"]');
    if (!select) {
        return;
    }
    function currentRelativeUrl() {
        try {
            var url = new URL(window.location.href);
            return url.pathname + url.search + url.hash;
        } catch (err) {
            return window.location.pathname + window.location.search + window.location.hash;
        }
    }
    select.addEventListener("change", function () {
        if (nextInput) {
            nextInput.value = currentRelativeUrl();
        }
        form.submit();
    });
})();
