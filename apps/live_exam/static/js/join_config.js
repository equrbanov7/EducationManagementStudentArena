/* join_config.js — canlı imtahan «qoşul» səhifəsinin konfiqi (LX-FE-PLAYER 2026-09-29).
 * JSON data-adaları: #joinConfig, #joinI18n, #joinSessionSettings, #rememberedPlayerData.
 * KLASSİK skript: join.js-dən ƏVVƏL `window.LiveJoinConfig` və `window.LIVE_EXAM_JOIN_I18N` qurur.
 */
(function () {
    "use strict";

    function readJson(id, fallback) {
        var el = document.getElementById(id);
        if (!el) {
            return fallback;
        }
        try {
            return JSON.parse(el.textContent);
        } catch (err) {
            return fallback;
        }
    }

    var config = readJson("joinConfig", {});
    config.sessionSettings = readJson("joinSessionSettings", {});
    config.rememberedPlayer = readJson("rememberedPlayerData", null);
    window.LiveJoinConfig = config;
    window.LIVE_EXAM_JOIN_I18N = readJson("joinI18n", {});
})();
