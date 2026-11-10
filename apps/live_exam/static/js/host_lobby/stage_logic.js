/* stage_logic.js — final səhnəsinin SAF məntiqi (DOM yoxdur; Node testləri: tests/js/live_stage.test.js).
 *
 * DÜZGÜNLÜK QAYDASI: yerlər SERVERİN `top` sırasıdır (xal ↓, qoşulma vaxtı ↑, id ↑).
 * Müştəri heç vaxt yenidən sıralamır və natamam məlumatdan rütbə hesablamır;
 * bərabər xal yalnız «Bərabər xal» nişanı kimi göstərilir (yer dəyişmir).
 */

export const SLOT_BY_PLACE = { 1: "center", 2: "left", 3: "right" };
export const AUDIENCE_LIMIT = 7; // 4–10-cu yerlər

const idOf = (row) => Number(row?.player_id ?? row?.id ?? 0);
const scoreOf = (row) => Number(row?.score ?? 0);

export function stageSignature(top) {
    return (Array.isArray(top) ? top : []).map((row) => `${idOf(row)}:${scoreOf(row)}`).join("|") || "empty";
}

/**
 * @param {Array} top      server `top` (sıralı)
 * @param {Object} meta    { totalPlayers }
 */
export function buildStageModel(top, meta = {}) {
    const rows = (Array.isArray(top) ? top : []).filter((row) => row && typeof row === "object");
    const tieAt = (index) =>
        (index > 0 && scoreOf(rows[index - 1]) === scoreOf(rows[index])) ||
        (index < rows.length - 1 && scoreOf(rows[index + 1]) === scoreOf(rows[index]));
    const podium = rows.slice(0, 3).map((player, index) => ({
        place: index + 1,
        slot: SLOT_BY_PLACE[index + 1],
        player,
        id: idOf(player),
        score: scoreOf(player),
        tie: tieAt(index),
    }));
    const audience = rows.slice(3, 3 + AUDIENCE_LIMIT).map((player, offset) => ({
        place: offset + 4,
        player,
        id: idOf(player),
        score: scoreOf(player),
        tie: tieAt(offset + 3),
    }));
    const total = Math.max(Number(meta.totalPlayers || 0), rows.length);
    return {
        podium,
        audience,
        more: Math.max(0, total - podium.length - audience.length),
        total,
        empty: rows.length === 0,
        signature: stageSignature(rows),
    };
}

/**
 * Zaman xətti (ms). Olmayan yerlər atlanır; 3-cü → 2-ci → (fasilə + barabam) → 1-ci.
 * reduced=true → hər şey dərhal (statik final kadrı).
 */
export function stageTimeline(model, { reduced = false } = {}) {
    if (reduced) {
        return [{ at: 0, action: "static" }];
    }
    const steps = [
        { at: 0, action: "intro" },
        { at: 250, action: "drumroll", seconds: 2.9 },
        { at: 900, action: "curtains" },
        { at: 2300, action: "podium" },
    ];
    if (model.empty) {
        steps.push({ at: 3300, action: "empty" });
        return steps;
    }
    let cursor = 3300;
    [3, 2].forEach((place) => {
        if (model.podium.some((entry) => entry.place === place)) {
            steps.push({ at: cursor, action: "focus", place });
            steps.push({ at: cursor + 200, action: "reveal", place });
            cursor += 2200;
        }
    });
    if (model.podium.length > 1) {
        steps.push({ at: cursor, action: "suspense", seconds: 2.2 });
        cursor += 2400;
    }
    steps.push({ at: cursor, action: "focus", place: 1 });
    steps.push({ at: cursor + 200, action: "reveal", place: 1 });
    steps.push({ at: cursor + 350, action: "cannons" });
    steps.push({ at: cursor + 700, action: "crown" });
    steps.push({ at: cursor + 1100, action: "fireworks" });
    steps.push({ at: cursor + 1900, action: "fireworks" });
    steps.push({ at: cursor + 2800, action: "party" });
    return steps;
}

const MOVES = {
    1: ["jump", "spin", "bounce", "wave"],
    2: ["sway", "bounce", "wave", "spin"],
    3: ["bounce", "sway", "jump", "wave"],
};

/* ── Viral + imza rəqsləri (2026-11-10). Adlar live_avatar.css `data-dance`
 * qaydaları və live_avatar_renderer.js DANCES siyahısı ilə eynidir (test yoxlayır). */
export const VIRAL_DANCES = Object.freeze([
    "floss", "griddy", "dab", "moonwalk", "robot", "shuffle",
    "woah", "hype", "macarena", "gangnam", "orange", "worm",
]);

/** avatar_1…avatar_16 → növün imza hərəkəti (live_avatar_catalog.js sırası). */
export const SIGNATURE_DANCES = Object.freeze({
    avatar_1: "tailspin", // tülkü
    avatar_2: "roll", // panda
    avatar_3: "roar", // şir
    avatar_4: "pounce", // pələng
    avatar_5: "snooze", // koala
    avatar_6: "wiggle", // donuz
    avatar_7: "leap", // qurbağa
    avatar_8: "tentacle", // osminoq
    avatar_9: "swing", // meymun
    avatar_10: "prance", // təkbuynuz
    avatar_11: "hophop", // dovşan
    avatar_12: "wheel", // hamster
    avatar_13: "howl", // canavar
    avatar_14: "slide", // ağ ayı
    avatar_15: "handstand", // qırmızı panda
    avatar_16: "hophop", // nanə/lop dovşan
});

export function signatureDance(avatarKey) {
    return SIGNATURE_DANCES[String(avatarKey ?? "")] || "bounce";
}

const phraseIndex = (phrase) => Math.abs(Math.trunc(Number(phrase) || 0));

/**
 * Hər 8 vuruşda (≈4.3 s) növbəti rəqs hərəkəti.
 *   danceFor(place, phrase)            → köhnə davranış (yerə görə əsas hərəkətlər).
 *   danceFor(place, phrase, avatarKey) → cüt frazada imza hərəkəti, tək frazada viral;
 *     viral indeksi yer + frazadan çıxır (1-2-3-cü yerlər eyni anda eyni viralı etmir;
 *     ofset 4 → fraza yerə görə ±1 sürüşsə də toqquşmur).
 */
export function danceFor(place, phrase, avatarKey) {
    const n = phraseIndex(phrase);
    if (avatarKey == null || avatarKey === "") {
        const list = MOVES[place] || ["cheer", "bounce"];
        return list[n % list.length];
    }
    if (n % 2 === 0) return signatureDance(avatarKey);
    const slot = Math.max(0, (Number(place) || 1) - 1);
    return VIRAL_DANCES[(Math.floor(n / 2) + slot * 4) % VIRAL_DANCES.length];
}

const AUDIENCE_POOL = Object.freeze([...VIRAL_DANCES, "cheer", "bounce"]);

/** Tamaşaçı (4–10-cu yer) üçün hərəkət: qonşular fərqli, fraza ilə dəyişir, deterministik. */
export function audienceDance(index, phrase) {
    const i = Math.abs(Math.trunc(Number(index) || 0));
    // 5 və 14 qarşılıqlı sadədir → ardıcıl 14 tamaşaçı hamısı fərqli; 7 fraza addımı dövrü sürüşdürür.
    return AUDIENCE_POOL[(i * 5 + phraseIndex(phrase) * 7) % AUDIENCE_POOL.length];
}

/** Tamaşaçı sırası üçün faza sürüşməsi (hamı eyni anda tullanmasın). */
export function audienceDelay(index) {
    return -((index * 0.137) % 0.55);
}
