// LX-FE-PLAYER — GÜC REJİMLƏRİ (sahib 2026-11-10): 💣 bomba və ×2 xal — telefon tərəfi.
//  * Nişanlar (kicker), üzən bomba, ×2 sikkəsi — serverin DONDURULMUŞ bayraqlarından (`question.is_bomb`,
//    `question.is_double`); bal qaydası yalnız serverdədir.
//  * Ambiyans: bomba sualının cavab pəncərəsində ürək döyüntüsü (audio.js) + qırmızı nəbz vinyeti
//    (body.lxp-bomb-armed, data-bomb-urgency); vaxt azaldıqca sürətlənir.
//  * `question_modifiers` WS hadisəsi: aparıcı rejimi cavabsız cari suala tətbiq etdi → bayraqlar
//    dəyişir, görünüş açarı (modsKey) dəyişdiyi üçün faza yenidən çəkilir.
import { PHASES } from './config.js?v=lx20261111f';
import { startHeartbeat, stopHeartbeat } from './audio.js?v=lx20261111f';
import { state } from './state.js?v=lx20261111f';
import { esc, nowMs, toInt, tr, ts } from './utils.js?v=lx20261111f';
import { BOMB_SVG } from '../host_lobby/power_art.js?v=lx20261111f';

const BOMB_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="11" cy="14" r="7" fill="currentColor"/><path d="M14.5 7.5l2.2-2.2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M16.7 5.3c1.4-1.3 2.9-.9 3.6.4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="21" cy="4.5" r="1.3" fill="currentColor"/></svg>';
export const DOUBLE_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5.5 8.5c0-1.8 1.4-3 3.2-3s3.1 1.1 3.1 2.8c0 1.5-1 2.5-2.4 3.7L5.5 15.3h6.6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><path d="M14.5 9.5l5 5M19.5 9.5l-5 5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/></svg>';

export const isBombQuestion = (question) => Boolean(question && question.is_bomb);
export const isDoubleQuestion = (question) => Boolean(question && question.is_double);

/** Görünüş açarına əlavə — bayraq dəyişəndə view yenidən qurulur (səslər sual açarı ilə qalır). */
export const modsKey = (question) => `${isBombQuestion(question) ? "b" : "-"}${isDoubleQuestion(question) ? "d" : "-"}`;

export function powerClass(question) {
    return `${isBombQuestion(question) ? " is-bomb" : ""}${isDoubleQuestion(question) ? " is-double" : ""}`;
}

export function powerBadgesMarkup(question) {
    const parts = [];
    if (isBombQuestion(question)) {
        parts.push(`<span class="lxp-badge lxp-badge--bomb">${BOMB_ICON}<span>${esc(tr("bombBadge", "Bomba sualı"))}</span></span>`);
    }
    if (isDoubleQuestion(question)) {
        parts.push(`<span class="lxp-badge lxp-badge--double">${DOUBLE_ICON}<span>${esc(tr("doubleBadge", "×2 xal"))}</span></span>`);
    }
    return parts.join("");
}

/** Sual görünüşündə (kicker olmayan faza) yalnız güc nişanları sırası. */
export function powerKickerMarkup(question) {
    const badges = powerBadgesMarkup(question);
    return badges ? `<p class="lxp-kicker lxp-kicker--power" data-no-bomb-rule>${badges}</p>` : "";
}

export function powerArtMarkup(question) {
    return (
        (isBombQuestion(question) ? `<div class="lxp-bomb" aria-hidden="true">${BOMB_SVG}</div>` : "") +
        (isDoubleQuestion(question) ? `<div class="lxp-double" aria-hidden="true">${DOUBLE_ICON}</div>` : "")
    );
}

/** Nəticədə ×2 çipi (serverin `points_multiplier`-i; xal 0-dırsa göstərilmir). */
export function doubleChipMarkup(result, payload) {
    const multiplier = toInt((result && result.points_multiplier) || (payload && payload.points_multiplier) || 1, 1);
    if (multiplier < 2 || !result || toInt(result.awarded_points, 0) <= 0) return "";
    return `<span class="lxp-pill lxp-pill--double">${DOUBLE_ICON}<span>${esc(tr("doubleChip", "×2 xal!"))}</span></span>`;
}

export const resultIsDouble = (result, payload) =>
    toInt((result && result.points_multiplier) || (payload && payload.points_multiplier) || 1, 1) >= 2 &&
    Boolean(result) &&
    toInt(result.awarded_points, 0) > 0;

/* ── Ambiyans ── */
export function syncBombAmbience() {
    const question = state.currentQuestion;
    const active =
        isBombQuestion(question) && !state.revealPayload && (state.phase === PHASES.QUESTION || state.phase === PHASES.INTRO);
    document.body.classList.toggle("lxp-bomb-armed", active);
    if (!active) {
        delete document.body.dataset.bombUrgency;
        stopHeartbeat();
        return;
    }
    if (state.phase !== PHASES.QUESTION) {
        document.body.dataset.bombUrgency = "1";
        stopHeartbeat();
        return;
    }
    const left = Math.max(0, ts(question.ends_at) - nowMs());
    const urgency = left <= 5000 ? "3" : left <= 10000 ? "2" : "1";
    if (document.body.dataset.bombUrgency !== urgency) document.body.dataset.bombUrgency = urgency;
    startHeartbeat(urgency === "3" ? 128 : urgency === "2" ? 96 : 64);
}

/** `question_modifiers` (server cari suala tətbiq etdi) → bayraqları dəyişir; `true` = dəyişdi. */
export function applyQuestionModifiers(data) {
    const question = state.currentQuestion;
    if (!question || !data || !data.applied || Number(data.question_id || 0) !== Number(question.id || 0)) return false;
    const next = { is_bomb: Boolean(data.is_bomb), is_double: Boolean(data.is_double) };
    if (isBombQuestion(question) === next.is_bomb && isDoubleQuestion(question) === next.is_double) return false;
    state.currentQuestion = Object.assign({}, question, next);
    return true;
}
