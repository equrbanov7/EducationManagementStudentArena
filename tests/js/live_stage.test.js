/* ═══════════════════════════════════════════════════════════════════════════
   2026-09-29 LX-FE-STAGE: canlı oyunun final səhnəsi (stage_logic.js) və avatar
   rəssamının (live_avatar_renderer.js) ƏSL göndərilən fayllarla testləri.
   stage_logic.js ES moduludur — data: URL ilə OLDUĞU KİMİ import olunur.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const STATIC = path.join(ROOT, "apps/live_exam/static/js");

async function loadStageLogic() {
    const src = fs.readFileSync(path.join(STATIC, "host_lobby/stage_logic.js"), "utf8");
    return import("data:text/javascript;base64," + Buffer.from(src).toString("base64"));
}

const row = (id, score, extra) => Object.assign({ player_id: id, nickname: `P${id}`, score }, extra || {});

test("stage keeps the SERVER order even with tied scores (no client re-sort)", async () => {
    const { buildStageModel } = await loadStageLogic();
    // server: equal scores ordered by join time → id 9 before id 3
    const model = buildStageModel([row(9, 500), row(3, 500), row(5, 200), row(1, 100)]);
    assert.deepEqual(model.podium.map((e) => e.id), [9, 3, 5]);
    assert.deepEqual(model.podium.map((e) => e.place), [1, 2, 3]);
    assert.deepEqual(model.podium.map((e) => e.slot), ["center", "left", "right"]);
    assert.equal(model.podium[0].tie, true);
    assert.equal(model.podium[1].tie, true);
    assert.equal(model.podium[2].tie, false);
    assert.deepEqual(model.audience.map((e) => [e.id, e.place]), [[1, 4]]);
});

test("0 / 1 / 2 players and 90 players (audience cap + more)", async () => {
    const { buildStageModel, stageTimeline } = await loadStageLogic();
    const empty = buildStageModel([]);
    assert.equal(empty.empty, true);
    assert.ok(stageTimeline(empty).some((s) => s.action === "empty"));
    assert.ok(!stageTimeline(empty).some((s) => s.action === "reveal"));

    const one = buildStageModel([row(1, 10)]);
    const oneReveals = stageTimeline(one).filter((s) => s.action === "reveal").map((s) => s.place);
    assert.deepEqual(oneReveals, [1]);

    const two = buildStageModel([row(1, 10), row(2, 5)]);
    assert.deepEqual(stageTimeline(two).filter((s) => s.action === "reveal").map((s) => s.place), [2, 1]);

    const many = Array.from({ length: 50 }, (_, i) => row(i + 1, 1000 - i));
    const model = buildStageModel(many, { totalPlayers: 90 });
    assert.equal(model.podium.length, 3);
    assert.equal(model.audience.length, 7);
    assert.deepEqual(model.audience.map((e) => e.place), [4, 5, 6, 7, 8, 9, 10]);
    assert.equal(model.more, 80);
});

test("timeline reveals 3rd → 2nd → suspense → 1st, then cannons/crown/party; reduced motion is static", async () => {
    const { buildStageModel, stageTimeline } = await loadStageLogic();
    const steps = stageTimeline(buildStageModel([row(1, 30), row(2, 20), row(3, 10)]));
    const order = steps.filter((s) => ["reveal", "suspense", "cannons", "crown", "party"].includes(s.action)).map((s) => s.action + (s.place || ""));
    assert.deepEqual(order, ["reveal3", "reveal2", "suspense", "reveal1", "cannons", "crown", "party"]);
    const times = steps.map((s) => s.at);
    assert.deepEqual(times, times.slice().sort((a, b) => a - b), "addımlar zaman sırası ilə");
    assert.deepEqual(stageTimeline(buildStageModel([row(1, 1)]), { reduced: true }), [{ at: 0, action: "static" }]);
});

test("signature changes with scores; dances are valid API values", async () => {
    const { stageSignature, danceFor } = await loadStageLogic();
    assert.notEqual(stageSignature([row(1, 10)]), stageSignature([row(1, 11)]));
    assert.equal(stageSignature([]), "empty");
    const allowed = new Set(["bounce", "sway", "spin", "jump", "wave", "cheer", "idle"]);
    for (let place = 1; place <= 4; place += 1) {
        for (let phrase = 0; phrase < 8; phrase += 1) assert.ok(allowed.has(danceFor(place, phrase)));
    }
});

function avatarWindow() {
    const dom = new JSDOM("<!doctype html><html><body></body></html>", { runScripts: "outside-only", url: "http://localhost/live/" });
    dom.window.eval(fs.readFileSync(path.join(STATIC, "live_avatar_catalog.js"), "utf8"));
    dom.window.eval(fs.readFileSync(path.join(STATIC, "live_avatar_renderer.js"), "utf8"));
    return dom.window;
}

test("avatar renderer keeps its public API and renders every avatar × accessory with CSS hooks", () => {
    const window = avatarWindow();
    const R = window.LiveAvatarRenderer;
    const C = window.LiveAvatarCatalog;
    for (const name of ["getProfile", "renderAvatarMarkup", "renderAvatarDataUrl", "mountAvatar", "renderAvatarSvg", "renderAccessoryIcon", "setDance"]) {
        assert.equal(typeof R[name], "function", name);
    }
    assert.equal(C.avatarKeys.length, 16);
    assert.deepEqual(JSON.parse(JSON.stringify(C.avatarKeys)), Array.from({ length: 16 }, (_, i) => `avatar_${i + 1}`));
    assert.ok(C.accessoryKeys.includes("accessory_none") && C.accessoryKeys.includes("halo"));
    for (const avatar of C.avatarKeys) {
        for (const accessory of C.accessoryKeys) {
            const html = R.renderAvatarMarkup({ avatar_key: avatar, accessory_key: accessory }, { size: 140, crop: "full" });
            const host = window.document.createElement("div");
            host.innerHTML = html;
            const root = host.firstElementChild;
            assert.ok(root.classList.contains("live-avatar"), avatar);
            for (const hook of [".lva-rig", ".lva-head", ".lva-arm--l", ".lva-arm--r", ".lva-eye"]) {
                assert.ok(root.querySelector(hook), `${avatar}/${accessory} ${hook}`);
            }
            assert.equal(root.querySelector("svg [id]"), null, "inline SVG-də id olmamalıdır");
        }
        assert.match(R.renderAvatarDataUrl({ avatar_key: avatar }), /^data:image\/svg\+xml;charset=UTF-8,/);
    }
});

test("avatar renderer: fallback keys, dance attribute, escaped label, setDance", () => {
    const window = avatarWindow();
    const R = window.LiveAvatarRenderer;
    const profile = JSON.parse(JSON.stringify(R.getProfile({ avatar_key: "nope", accessory_key: "bad" })));
    assert.deepEqual(profile, { avatarKey: "avatar_1", accessoryKey: "accessory_none" });
    const host = window.document.createElement("div");
    host.innerHTML = R.renderAvatarMarkup({ avatar_key: "avatar_3" }, { size: 50, dance: "jump", label: 'A"<b>' });
    const root = host.firstElementChild;
    assert.equal(root.getAttribute("data-dance"), "jump");
    assert.equal(root.getAttribute("aria-label"), 'A"<b>');
    assert.ok(root.classList.contains("live-avatar--portrait"), "size < 96 → portret kəsimi");
    assert.equal(root.querySelector("b"), null);
    R.setDance(root, "wave");
    assert.equal(root.getAttribute("data-dance"), "wave");
    R.setDance(root, "not-a-dance");
    assert.equal(root.hasAttribute("data-dance"), false);
    assert.ok(R.renderAccessoryIcon("crown", 24).startsWith("<svg"));
});

/* ═══ 2026-11-10: viral + imza rəqsləri (stage_logic ↔ renderer DANCES ↔ live_avatar.css) ═══ */

// 2026-11-10: baza + rəqslər iki fayldadır (modul ölçü büdcəsi) — birlikdə oxunur.
const CSS_PATHS = ["live_avatar.css", "live_avatar_dances.css"].map((name) => path.join(ROOT, "apps/live_exam/static/css", name));
const readCss = () => CSS_PATHS.map((file) => fs.readFileSync(file, "utf8")).join("\n");

function rendererDances() {
    const src = fs.readFileSync(path.join(STATIC, "live_avatar_renderer.js"), "utf8");
    const m = src.match(/const DANCES = \[([\s\S]*?)\];/);
    assert.ok(m, "renderer DANCES massivi tapılmadı");
    return new Set(Array.from(m[1].matchAll(/"([a-z]+)"/g), (x) => x[1]));
}

function cssDances(css) {
    return new Set(Array.from(css.matchAll(/\.live-avatar\[data-dance="([a-z]+)"\]/g), (x) => x[1]));
}

test("viral/signature names exist in the renderer DANCES array AND have a CSS data-dance rule", async () => {
    const { VIRAL_DANCES, SIGNATURE_DANCES, signatureDance, danceFor, audienceDance } = await loadStageLogic();
    const css = readCss();
    const inRenderer = rendererDances();
    const inCss = cssDances(css);
    const produced = new Set([...VIRAL_DANCES, ...Object.values(SIGNATURE_DANCES), signatureDance("nope")]);
    for (let place = 1; place <= 4; place += 1) {
        for (let phrase = 0; phrase < 24; phrase += 1) {
            produced.add(danceFor(place, phrase));
            for (let a = 1; a <= 16; a += 1) produced.add(danceFor(place, phrase, `avatar_${a}`));
        }
    }
    for (let i = 0; i < 14; i += 1) for (let phrase = 0; phrase < 8; phrase += 1) produced.add(audienceDance(i, phrase));
    for (const name of produced) {
        assert.ok(inRenderer.has(name), `renderer DANCES-də yoxdur: ${name}`);
        assert.ok(inCss.has(name), `live_avatar.css-də [data-dance="${name}"] yoxdur`);
    }
    // və əksinə: CSS ↔ renderer tam üst-üstə düşür
    assert.deepEqual([...inCss].sort(), [...inRenderer].sort());
    assert.equal(VIRAL_DANCES.length, 12);
    assert.equal(new Set(VIRAL_DANCES).size, 12);
});

test("signature mapping: 16 avatars, species-specific, unknown → bounce", async () => {
    const { SIGNATURE_DANCES, signatureDance } = await loadStageLogic();
    assert.deepEqual(Object.keys(SIGNATURE_DANCES), Array.from({ length: 16 }, (_, i) => `avatar_${i + 1}`));
    assert.equal(signatureDance("avatar_1"), "tailspin"); // tülkü
    assert.equal(signatureDance("avatar_2"), "roll"); // panda
    assert.equal(signatureDance("avatar_3"), "roar"); // şir
    assert.equal(signatureDance("avatar_7"), "leap"); // qurbağa
    assert.equal(signatureDance("avatar_8"), "tentacle"); // osminoq
    assert.equal(signatureDance("avatar_11"), "hophop"); // dovşan
    assert.equal(signatureDance("avatar_16"), "hophop"); // lop/nanə dovşan
    assert.equal(signatureDance("avatar_15"), "handstand");
    assert.equal(signatureDance("nope"), "bounce");
    assert.equal(signatureDance(undefined), "bounce");
    assert.equal(signatureDance(null), "bounce");
    // dovşanlardan başqa hamısı fərqli
    const values = Object.values(SIGNATURE_DANCES);
    assert.equal(new Set(values).size, 15);
});

test("danceFor with avatarKey alternates signature (even) / viral (odd); podium never shares a viral move", async () => {
    const { VIRAL_DANCES, danceFor, signatureDance } = await loadStageLogic();
    const viral = new Set(VIRAL_DANCES);
    for (let phrase = 0; phrase < 48; phrase += 1) {
        for (let place = 1; place <= 3; place += 1) {
            const d = danceFor(place, phrase, `avatar_${place}`);
            if (phrase % 2 === 0) assert.equal(d, signatureDance(`avatar_${place}`), `cüt fraza ${phrase} → imza`);
            else assert.ok(viral.has(d), `tək fraza ${phrase} → viral (${d})`);
        }
        if (phrase % 2 === 1) {
            const trio = [1, 2, 3].map((p) => danceFor(p, phrase, "avatar_5"));
            assert.equal(new Set(trio).size, 3, `fraza ${phrase}: ${trio.join(",")}`);
            // stage.js kimi yerə görə sürüşmüş fraza ilə də toqquşmur
            const shifted = [1, 2, 3].map((p) => danceFor(p, phrase + p, "avatar_5")).filter((d) => viral.has(d));
            assert.equal(new Set(shifted).size, shifted.length, `sürüşmüş fraza ${phrase}: ${shifted.join(",")}`);
        }
    }
    // zamanla bütün virallar görünür
    const seen = new Set();
    for (let phrase = 1; phrase < 48; phrase += 2) seen.add(danceFor(1, phrase, "avatar_1"));
    assert.equal(seen.size, VIRAL_DANCES.length);
    // avatarKey olmadan köhnə davranış dəyişmir
    assert.deepEqual(
        [0, 1, 2, 3, 4].map((p) => danceFor(1, p)),
        ["jump", "spin", "bounce", "wave", "jump"],
    );
    assert.equal(danceFor(9, 0), "cheer");
    assert.equal(danceFor(1, 0, ""), "jump", "boş avatarKey = verilməyib");
    // mənfi/qeyri-ədədi fraza çökmür
    assert.ok(typeof danceFor(2, -3, "avatar_2") === "string");
    assert.ok(typeof danceFor(2, "x", "avatar_2") === "string");
});

test("audienceDance: neighbours differ, deterministic, no Math.random anywhere in stage_logic", async () => {
    const { audienceDance, VIRAL_DANCES } = await loadStageLogic();
    const allowed = new Set([...VIRAL_DANCES, "cheer", "bounce"]);
    for (let phrase = 0; phrase < 10; phrase += 1) {
        const row = Array.from({ length: 7 }, (_, i) => audienceDance(i, phrase));
        row.forEach((d) => assert.ok(allowed.has(d), d));
        for (let i = 1; i < row.length; i += 1) assert.notEqual(row[i], row[i - 1], `fraza ${phrase}, ${i - 1}/${i}`);
        assert.equal(new Set(row).size, 7, `7 tamaşaçı hamısı fərqli (fraza ${phrase})`);
        assert.deepEqual(row, Array.from({ length: 7 }, (_, i) => audienceDance(i, phrase)), "deterministik");
    }
    assert.notDeepEqual(
        Array.from({ length: 7 }, (_, i) => audienceDance(i, 0)),
        Array.from({ length: 7 }, (_, i) => audienceDance(i, 1)),
        "fraza dəyişəndə hərəkətlər dəyişir",
    );
    const src = fs.readFileSync(path.join(STATIC, "host_lobby/stage_logic.js"), "utf8");
    assert.doesNotMatch(src, /Math\.random/);
});

test("live_avatar.css: every animation-name has keyframes, parts are neutralised for reduced motion, no url()/@import", () => {
    const css = readCss();
    assert.doesNotMatch(css, /url\(|@import/);
    const keyframes = new Set(Array.from(css.matchAll(/@keyframes\s+([A-Za-z0-9_-]+)/g), (m) => m[1]));
    const used = new Set();
    for (const m of css.matchAll(/animation-name:\s*([A-Za-z0-9_-]+)/g)) used.add(m[1]);
    for (const m of css.matchAll(/animation:\s*([A-Za-z][A-Za-z0-9_-]*)\s/g)) if (m[1] !== "none") used.add(m[1]);
    for (const name of used) assert.ok(keyframes.has(name), `@keyframes ${name} yoxdur`);
    for (const name of keyframes) assert.ok(used.has(name), `istifadəsiz @keyframes ${name}`);
    // reduced-motion bloku: rəqs altında animasiya olunan hər hissə sinfi orada söndürülür
    const reducedStart = css.indexOf("@media (prefers-reduced-motion: reduce)");
    assert.ok(reducedStart > 0);
    const reduced = css.slice(reducedStart);
    const parts = new Set(Array.from(css.slice(0, reducedStart).matchAll(/\[data-dance(?:="[a-z]+")?\]\s+\.(lva-[a-z]+)/g), (m) => m[1]));
    assert.ok(parts.has("lva-feet") && parts.has("lva-body") && parts.has("lva-paw"), "yeni hissələr animasiya olunur");
    for (const part of parts) {
        assert.match(reduced, new RegExp(`\\.live-avatar(?:\\[data-dance\\])? \\.${part}(?:,|\\s*\\{)`), `reduced-motion-da .${part} söndürülməyib`);
    }
    // yalnız transform animasiya olunur (keyframes gövdəsində başqa xüsusiyyət yoxdur — opacity yalnız sparkle-da)
    const keyframeBodies = [];
    for (const m of css.matchAll(/@keyframes\s+(lva[A-Za-z]+)\s*\{/g)) {
        let depth = 1;
        let i = m.index + m[0].length;
        const from = i;
        while (i < css.length && depth > 0) {
            if (css[i] === "{") depth += 1;
            else if (css[i] === "}") depth -= 1;
            i += 1;
        }
        keyframeBodies.push([m[1], css.slice(from, i - 1)]);
    }
    assert.ok(keyframeBodies.length > 40);
    for (const [name, body] of keyframeBodies) {
        const props = new Set(Array.from(body.matchAll(/([a-z-]+)\s*:/g), (m) => m[1]));
        props.delete("transform");
        if (name === "lvaTwinkle") props.delete("opacity");
        assert.equal(props.size, 0, `${name}: yalnız transform (${[...props].join(",")})`);
    }
});
