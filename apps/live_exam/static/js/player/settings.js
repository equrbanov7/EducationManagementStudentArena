// LX-FE-PLAYER (2026-09-29): host sessiya parametrləri (tema, yüksək kontrast) telefonda da tətbiq olunur.
// 2026-10-19: təqdimat üslubu (Rəsmi / Qeyri-rəsmi) — `body[data-lx-style]` + baş hərf avatarları.
import { SESSION_SETTINGS } from './config.js?v=lx20261019s';
import { applyStyleToDocument, setPresentationStyle } from '../host_lobby/style_mode.js?v=lx20261019s';

export function applySessionSettings(nextSettings) {
    Object.assign(SESSION_SETTINGS, nextSettings || {});
    document.body.dataset.liveTheme = SESSION_SETTINGS.theme_key || "aurora";
    document.body.classList.toggle("lxp-high-contrast", Boolean(SESSION_SETTINGS.increase_contrast));
    const changed = setPresentationStyle(SESSION_SETTINGS);
    applyStyleToDocument();
    return changed;
}
