/* wait_room_config.js — canlı imtahan gözləmə otağının konfiqi.
 * Mənbə: liveExam/wait_room.html (inline nonce script, 2026-09-21-də xarici
 * fayla çıxarıldı — CSP `script-src` yalnız SELF + NONCE).
 *
 * JSON data-adaları:
 *   #waitRoomConfig          — csrf, wsPath, stateUrl, profileUrl, reactionUrl,
 *                              playerScreenUrl, joinPageUrl, myPlayerId
 *   #waitRoomI18n            — LIVE_EXAM_WAIT_ROOM_I18N mətnləri
 *   #waitRoomMyPlayer        — my_player (json_script, dəyişməyib)
 *   #waitRoomSessionSettings — session_settings (json_script, dəyişməyib)
 *
 * KLASSİK, defer-siz skript: wait_room_page.js-dən ƏVVƏL, inline blokla eyni
 * mövqedə işləyir; `window.LiveWaitRoomConfig` və `window.LIVE_EXAM_WAIT_ROOM_I18N`
 * qurur (eyni açarlar, eyni tiplər — myPlayerId rəqəm).
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

    var config = readJson("waitRoomConfig", {});
    config.myPlayer = readJson("waitRoomMyPlayer", null);
    config.sessionSettings = readJson("waitRoomSessionSettings", {});
    window.LiveWaitRoomConfig = config;
    window.LIVE_EXAM_WAIT_ROOM_I18N = readJson("waitRoomI18n", {});
})();
