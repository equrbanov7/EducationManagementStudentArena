// LX-FE-PLAYER (2026-09-29): host sessiya parametrləri (tema, yüksək kontrast) telefonda da tətbiq olunur.
import { SESSION_SETTINGS } from './config.js?v=lx20260929';

export function applySessionSettings(nextSettings) {
    Object.assign(SESSION_SETTINGS, nextSettings || {});
    document.body.dataset.liveTheme = SESSION_SETTINGS.theme_key || "aurora";
    document.body.classList.toggle("lxp-high-contrast", Boolean(SESSION_SETTINGS.increase_contrast));
}
