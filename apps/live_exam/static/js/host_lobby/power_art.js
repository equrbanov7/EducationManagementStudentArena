/* power_art.js — güc rejimlərinin SAF rəsmləri (2026-11-10): import YOXDUR, ona görə oyunçu
 * qrafından (../host_lobby/) da yüklənə bilər (stage_logic.js / code_text.js kimi — host CONFIG-i yox). */

/** Fitilli bomba (120×120): gövdə, qapaq, fitil və qığılcım (`.hx-bomb__spark` CSS-də yanıb-sönür). */
export const BOMB_SVG =
    '<svg class="hx-bomb__art" viewBox="0 0 120 120" aria-hidden="true" focusable="false">' +
    '<defs><radialGradient id="hxBombBody" cx="38%" cy="32%" r="70%"><stop offset="0" stop-color="#5b6478"/><stop offset=".55" stop-color="#1c2131"/><stop offset="1" stop-color="#05070f"/></radialGradient></defs>' +
    '<path class="hx-bomb__fuse" d="M78 30 C86 18 96 14 108 16" fill="none" stroke="#c9a46a" stroke-width="5" stroke-linecap="round"/>' +
    '<circle class="hx-bomb__cap" cx="76" cy="36" r="9" fill="#9aa3b8"/>' +
    '<circle class="hx-bomb__body" cx="56" cy="68" r="42" fill="url(#hxBombBody)"/>' +
    '<ellipse cx="40" cy="52" rx="11" ry="7" fill="#fff" opacity=".22" transform="rotate(-30 40 52)"/>' +
    '<g class="hx-bomb__spark"><circle cx="108" cy="16" r="6" fill="#ffd166"/><circle cx="108" cy="16" r="2.6" fill="#fff"/>' +
    '<path d="M108 3v6M108 23v6M95 16h6M115 16h6M99 7l4 4M113 25l4 4M117 7l-4 4M103 25l-4 4" stroke="#ffb703" stroke-width="2.4" stroke-linecap="round"/></g>' +
    '</svg>';
