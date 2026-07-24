/*
 * profile_embed_base.js
 * Source: apps/accounts/templates/accounts/profile_embed_base.html
 * Lightweight mobile sidebar toggle for profile-embed pages (no SPA load).
 * Wrapped in EMSReady + idempotent per-element guards (page extends base.html).
 */
(function () {
    "use strict";

    window.EMSReady(function () {
        var btn = document.querySelector('[data-profile-sidebar-toggle], .profile-hamburger, #profileSidebarToggle');
        var sidebar = document.querySelector('.profile-sidebar');
        var backdrop = document.getElementById('profileSidebarBackdrop');

        function open() {
            if (sidebar) sidebar.classList.add('is-open');
            if (backdrop) backdrop.classList.add('is-visible');
        }
        function close() {
            if (sidebar) sidebar.classList.remove('is-open');
            if (backdrop) backdrop.classList.remove('is-visible');
        }

        if (btn && btn.dataset.pebBound !== "1") {
            btn.dataset.pebBound = "1";
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                (sidebar && sidebar.classList.contains('is-open')) ? close() : open();
            });
        }
        if (backdrop && backdrop.dataset.pebBound !== "1") {
            backdrop.dataset.pebBound = "1";
            backdrop.addEventListener('click', close);
        }
    });
})();
