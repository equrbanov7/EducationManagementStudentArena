/*
 * register_globals.js
 * Source: apps/accounts/templates/accounts/register.html
 * Hydrates the two window globals the register wizard reads lazily
 * (state.js: window.REGISTER_I18N / window.SIGNUP_LOOKUP_DATA) from the
 * JSON <script> blocks emitted in the template. Runs at parse time (plain
 * IIFE, no EMSReady — base_auth.html does not load ems_ajax_init.js), before
 * the wizard's init fires, exactly as the former inline script did.
 */
(function () {
    "use strict";
    var lookupEl = document.getElementById("signup-lookup-data");
    var i18nEl = document.getElementById("register-i18n-data");
    if (lookupEl) {
        window.SIGNUP_LOOKUP_DATA = JSON.parse(lookupEl.textContent);
    }
    if (i18nEl) {
        window.REGISTER_I18N = JSON.parse(i18nEl.textContent);
    }
})();
