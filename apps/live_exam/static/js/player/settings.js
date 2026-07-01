import { SESSION_SETTINGS } from './config.js';

export function applySessionSettings(nextSettings) {
    Object.assign(SESSION_SETTINGS, nextSettings || {});
    document.body.dataset.liveTheme = SESSION_SETTINGS.theme_key || "aurora";
}
