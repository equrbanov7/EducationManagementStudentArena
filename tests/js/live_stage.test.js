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
