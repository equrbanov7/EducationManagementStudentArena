/* host_lobby_config.js — aparıcı (host) lobbi VƏ təqdimat ekranının konfiqi.
 * Mənbə: liveExam/host_lobby.html + liveExam/host_presentation.html (eyni inline
 * nonce script, 2026-09-21-də bir xarici fayla çıxarıldı — CSP `script-src`
 * yalnız SELF + NONCE). İki şablon yalnız JSON dəyərlərində fərqlənir
 * (presentationOnly, controlsEnabled, autoFullscreen).
 *
 * JSON data-adaları:
 *   #hostConfig — pin, csrf, maxQuestions, examTitle, entryUrl, qrUrl, sessionLocked,
 *                 maxParticipantsCap, languageCode, presentationOnly, controlsEnabled,
 *                 autoFullscreen, urls{…}, sessionSettingsId (json_script elementinin id-si)
 *   #hostI18n   — LIVE_EXAM_HOST_I18N mətnləri
 *
 * KLASSİK, defer-siz skript: host_lobby.entry.js modulundan ƏVVƏL işləyir və
 * inline blokla eyni adları qurur:
 *   • `const CONFIG` — qlobal leksik bağlama (host_lobby/*.js bare `CONFIG` oxuyur);
 *   • `window.LIVE_EXAM_HOST_I18N`;
 *   • qlobal funksiyalar `currentLobbyQrUrl`, `toggleQR` (events.js
 *     `typeof toggleQR === "function"` ilə çağırır), `closePodium`;
 *   • DOMContentLoaded: QR modal fon kliki bağlayır; #closePodiumBtn varsa
 *     (yalnız lobbi) podiumu bağlayır — hər ikisi null-safe.
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
    var config = readJson("hostConfig", {});
    config.sessionSettings = readJson(config.sessionSettingsId || "hostSessionSettings", {});
    window.LIVE_EXAM_HOST_I18N = readJson("hostI18n", {});
    return config;
})();

function currentLobbyQrUrl() {
    const settings = window.LiveHostLobbyController?.getState?.().settings || CONFIG.sessionSettings || {};
    const mode = settings.two_step_join === false ? "direct" : "pin";
    return `${CONFIG.qrUrl}${CONFIG.qrUrl.includes("?") ? "&" : "?"}mode=${mode}`;
}

function toggleQR(show) {
    const modal = document.getElementById("qrModal");
    const image = document.getElementById("qrModalImage");
    if (image) {
        image.src = currentLobbyQrUrl();
    }
    modal.style.display = show ? "flex" : "none";
}

function closePodium() {
    document.getElementById("finalPodium").style.display = "none";
}

document.addEventListener("DOMContentLoaded", function () {
    const qrModal = document.getElementById("qrModal");
    if (qrModal) {
        qrModal.addEventListener("click", function () { toggleQR(false); });
    }
    const closePodiumBtn = document.getElementById("closePodiumBtn");
    if (closePodiumBtn) {
        closePodiumBtn.addEventListener("click", closePodium);
    }
});
