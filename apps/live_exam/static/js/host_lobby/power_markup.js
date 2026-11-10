/* power_markup.js — güc rejimlərinin (💣 bomba, ×2 xal) SAF markup köməkçiləri (2026-11-10).
 * DOM-a toxunmur; question.js / reveal.js / powerups.js istifadə edir (dövri import yoxdur).
 * Qayda serverdədir: `question.is_bomb` / `question.is_double` nəşrdə dondurulmuş bayraqlardır. */
import { icon } from './icons.js?v=lx20261110p';
import { esc, tr } from './utils.js?v=lx20261110p';
import { BOMB_SVG } from './power_art.js?v=lx20261110p';

export const isBombQuestion = (question) => Boolean(question?.is_bomb);
export const isDoubleQuestion = (question) => Boolean(question?.is_double);

export { BOMB_SVG };

/** Sual başlığındakı nişanlar (proyektor): 💣 Bomba sualı · ×2 Xal. */
export function powerBadgesMarkup(question) {
    const badges = [];
    if (isBombQuestion(question)) {
        badges.push(
            `<span class="hx-badge hx-badge--bomb" title="${esc(tr("bombBadgeHelp", "Səhv cavab bu oyundakı xalı sıfırlayır"))}">${icon("bomb")}${esc(tr("bombBadge", "Bomba sualı"))}</span>`
        );
    }
    if (isDoubleQuestion(question)) {
        badges.push(
            `<span class="hx-badge hx-badge--double" title="${esc(tr("doubleBadgeHelp", "Düzgün cavab ikiqat xal gətirir"))}">${icon("double")}${esc(tr("doubleBadge", "×2 xal"))}</span>`
        );
    }
    return badges.join("");
}

/** Səhnədə üzən bomba (fitil qığılcımı ilə) + qırmızı nəbz vinyeti. */
export function bombSceneMarkup(question) {
    if (!isBombQuestion(question)) return "";
    return (
        `<div class="hx-bomb" data-bomb aria-hidden="true">${BOMB_SVG}` +
        `<span class="hx-bomb__trail"></span><span class="hx-bomb__trail hx-bomb__trail--2"></span></div>` +
        `<div class="hx-bomb-vignette" aria-hidden="true"></div>`
    );
}

/** Səhnədə ×2 «qızıl sikkə» aurası. */
export function doubleSceneMarkup(question) {
    if (!isDoubleQuestion(question)) return "";
    return `<div class="hx-double" aria-hidden="true"><span class="hx-double__coin">${icon("double")}</span><span class="hx-double__ring"></span></div>`;
}

/** Sual səhnəsinin sinif əlavələri (`.hx-question`-a). */
export function powerSceneClass(question) {
    return `${isBombQuestion(question) ? " is-bomb" : ""}${isDoubleQuestion(question) ? " is-double" : ""}`;
}

/** Partlayış qırıntıları (reveal-də bomba partlayanda). Bucaq/məsafə JS-də `style.setProperty`
 *  ilə verilir (powerups.js) — markup-da inline `style=` yoxdur (CSP style-src-attr hədəfi). */
export const EXPLOSION_SHARDS = 18;

export function explosionMarkup(count = EXPLOSION_SHARDS) {
    const shards = Array.from({ length: count }, (_, i) => `<i class="hx-explosion__shard" data-shard="${i}"></i>`).join("");
    return (
        `<div class="hx-explosion" data-explosion aria-hidden="true">` +
        `<span class="hx-explosion__flash"></span><span class="hx-explosion__wave"></span><span class="hx-explosion__wave hx-explosion__wave--2"></span>` +
        `<span class="hx-explosion__core">${icon("bomb")}</span>${shards}</div>`
    );
}

/** Qırıntıların yolu: bucaq, məsafə, ölçü (deterministik — i-yə görə). */
export function shardVars(index, count = EXPLOSION_SHARDS) {
    return {
        "--a": `${Math.round((index / count) * 360 + (index % 2) * 11)}deg`,
        "--d": `${38 + (index % 5) * 9}vmin`,
        "--s": String(0.6 + (index % 4) * 0.25),
        "--t": `${0.55 + (index % 3) * 0.12}s`,
    };
}
