/* style_mode.js — canlı oyunun TƏQDİMAT ÜSLUBU (2026-10-19, sahib: «ciddi mühitdə ikonlar uşaq
 * əyləncəli yox, rəsmi görünsün»). SAF modul: aparıcı (host_lobby/*) və oyunçu (player/*) qrafları
 * eyni faylı paylaşır (`../host_lobby/style_mode.js`, bax views/player/assets.py).
 *
 *   «formal»  (Rəsmi)      — A/B/C/D plitələri, xətti ikonlar, baş hərflər (avatar yox), konfetti /
 *                            səs / emoji / rəqs yoxdur, sıralama cədvəli sakit görünür;
 *   «playful» (Qeyri-rəsmi) — əvvəlki görünüş (fiqurlar, avatarlar, musiqi, final şousu).
 *
 * Mənbə: ictimai sessiya ayarlarındakı `presentation_style` (state JSON, lobby_state, session_settings
 * WS). Açar yoxdursa (köhnə keş / köhnə klient) — oyunbaz, yəni əvvəlki davranış dəyişmir.
 * Görünüş `body[data-lx-style]` atributu + CSS qatıdır (css/live_formal/*.css); JS yalnız
 * konfetti, səs, emoji və fiqur → hərf keçidlərini burada soruşur.
 */

export const STYLE_FORMAL = "formal";
export const STYLE_PLAYFUL = "playful";

const LETTERS = "ABCDEFGHIJ";
// Emoji (piktoqraflar + variasiya seçicisi + ZWJ) — rəsmi üslubda tərcümə mətnlərindən də çıxarılır.
const EMOJI_RE = /[\p{Extended_Pictographic}\u{FE0F}\u{200D}\u{20E3}]/gu;

let current = STYLE_PLAYFUL;

export const normalizeStyle = (value) => (String(value || "").toLowerCase() === STYLE_FORMAL ? STYLE_FORMAL : STYLE_PLAYFUL);

export const presentationStyle = () => current;

export const isFormal = () => current === STYLE_FORMAL;

/** Ayarlardan üslubu götürür; dəyişibsə `true` qaytarır. */
export function setPresentationStyle(settings) {
    const next = normalizeStyle(settings && typeof settings === "object" ? settings.presentation_style : settings);
    const changed = next !== current;
    current = next;
    return changed;
}

/** `body[data-lx-style]` + avatar rendereri (baş hərflər) — hər iki ekranda eyni. */
export function applyStyleToDocument(doc = globalThis.document) {
    if (doc?.body) doc.body.dataset.lxStyle = current;
    const renderer = globalThis.window?.LiveAvatarRenderer;
    if (renderer && typeof renderer.setFormal === "function") renderer.setFormal(current === STYLE_FORMAL);
}

/** 0 → «A», 1 → «B» … (variant sırası serverin göndərdiyi sıradır). */
export function optionLetter(index) {
    const n = Math.max(0, Math.floor(Number(index) || 0));
    return n < LETTERS.length ? LETTERS[n] : String(n + 1);
}

/** Rəsmi üslubda emoji mətndən çıxarılır (artıq boşluqlar yığılır); oyunbazda mətn olduğu kimi. */
export function plainText(text) {
    const value = String(text == null ? "" : text);
    if (current !== STYLE_FORMAL) return value;
    return value.replace(EMOJI_RE, "").replace(/[ \t]{2,}/g, " ").replace(/\s+([.!?…,])/g, "$1").trim();
}
