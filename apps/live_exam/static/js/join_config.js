/* join_config.js — canlı imtahan «qoşul» səhifəsinin konfiqi.
 * Mənbə: liveExam/join.html (inline nonce script, 2026-09-21-də xarici fayla
 * çıxarıldı — CSP `script-src` yalnız SELF + NONCE).
 *
 * Şablon dəyərləri JSON data-adalarında gəlir:
 *   #joinConfig            — pin, joinUrl, csrf, resumeUrl, generatedNickname
 *   #joinI18n              — LIVE_EXAM_JOIN_I18N mətnləri
 *   #joinSessionSettings   — session_settings (json_script, dəyişməyib)
 *   #rememberedPlayerData  — remembered_player (json_script, dəyişməyib)
 *
 * KLASSİK, defer-siz skript: inline blokla eyni mövqedə (join.js-dən ƏVVƏL) işləyir
 * və eyni adları qurur — `const CONFIG` qlobal leksik bağlama (join.js bare
 * `CONFIG` oxuyur) və `window.LIVE_EXAM_JOIN_I18N`.
 */
const CONFIG = (function () {
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
    window.LIVE_EXAM_JOIN_I18N = readJson("joinI18n", {});
    return config;
})();
