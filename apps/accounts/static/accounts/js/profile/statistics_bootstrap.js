/*
 * statistics_bootstrap.js
 * Source: apps/accounts/templates/accounts/profile/sections/_statistics.html
 * Reads the two JSON data blocks (#stats-data-json, #stats-i18n-json) rendered
 * in the statistics panel and exposes them as window.STATS_DATA / STATS_I18N for
 * the statistics chart bundle (accounts/js/statistics/*). The role scalar — the
 * only dynamic value the old inline block interpolated — is bridged via the
 * panel's data-stats-role attribute. Self-executes on load; the section loader
 * re-runs it verbatim on each AJAX swap.
 */
(function () {
    "use strict";

    var raw = document.getElementById("stats-data-json");
    if (raw) {
        try {
            var parsed = JSON.parse(raw.textContent);
            var panel = document.querySelector('[data-profile-section-panel="statistics"]');
            parsed.role = (panel && panel.dataset.statsRole) || "student";
            window.STATS_DATA = parsed;
        } catch (e) {
            window.STATS_DATA = null;
        }
    }

    var i18nEl = document.getElementById("stats-i18n-json");
    if (i18nEl) {
        try {
            window.STATS_I18N = JSON.parse(i18nEl.textContent);
        } catch (e) {
            window.STATS_I18N = {};
        }
    }
})();
