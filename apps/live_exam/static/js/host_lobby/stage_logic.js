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

/** Hər 8 vuruşda (≈4.3 s) yerə görə növbəti rəqs hərəkəti. */
export function danceFor(place, phrase) {
    const list = MOVES[place] || ["cheer", "bounce"];
    return list[Math.abs(Number(phrase) || 0) % list.length];
}

/** Tamaşaçı sırası üçün faza sürüşməsi (hamı eyni anda tullanmasın). */
export function audienceDelay(index) {
    return -((index * 0.137) % 0.55);
}
