/* player_screen_config.js — iştirakçı (player) ekranının bootstrap/i18n konfiqi.
 * Mənbə: liveExam/player_screen.html (inline nonce script, 2026-09-21-də xarici
 * fayla çıxarıldı — CSP `script-src` yalnız SELF + NONCE).
 *
 * JSON data-adaları:
 *   #playerBootstrap       — pin, csrf, quizTitle, stateUrl, answerUrl,
 *                            waitingMessages[], player{id, nickname, avatar_key,
 *                            accessory_key, score}
 *   #playerI18n            — LIVE_EXAM_PLAYER_I18N mətnləri
 *   #playerSessionSettings — session_settings (json_script, dəyişməyib)
 *
 * KLASSİK, defer-siz skript: player.entry.js modulundan ƏVVƏL
 * `window.LIVE_EXAM_PLAYER_BOOTSTRAP` və `window.LIVE_EXAM_PLAYER_I18N`-i inline
 * blokla eyni formada qurur (player/config.js oxuyur).
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

    var bootstrap = readJson("playerBootstrap", {});
    bootstrap.sessionSettings = readJson("playerSessionSettings", {});
    window.LIVE_EXAM_PLAYER_BOOTSTRAP = bootstrap;
    window.LIVE_EXAM_PLAYER_I18N = readJson("playerI18n", {});
})();
