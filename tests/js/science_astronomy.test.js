"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const file = path.resolve(__dirname, "../../apps/labs/static/labs/science_room/astronomy.js");
const subject = import("data:text/javascript;base64," + fs.readFileSync(file).toString("base64")).then(
    (m) => m.experiments
);

function get(scene, label) {
    return scene.results.find((row) => row.label === label).value;
}
function number(scene, label) {
    return Number.parseFloat(get(scene, label).replace(",", "."));
}
function area(pathData) {
    const vertices = Array.from(pathData.matchAll(/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/g), (m) => [
        Number(m[1]),
        Number(m[2])
    ]);
    return (
        Math.abs(
            vertices.reduce((sum, [x, y], i) => {
                const next = vertices[(i + 1) % vertices.length];
                return sum + x * next[1] - y * next[0];
            }, 0)
        ) / 2
    );
}
test("lunar quadratures, modelled age and drawn illuminated area agree", async () => {
    const { moonphase } = await subject;
    for (const [angle, percent, name] of [
        [0, 0, "Yeni ay"],
        [60, 25, "Böyüyən hilal"],
        [90, 50, "İlk rüb"],
        [180, 100, "Bədirlənmiş ay"],
        [270, 50, "Son rüb"],
        [360, 0, "Yeni ay"]
    ]) {
        const scene = moonphase.render({ phase: angle, tool: "telescope", runs: 0 });
        assert.equal(number(scene, "Görünən diskin işıqlı hissəsi"), percent);
        assert.equal(get(scene, "Ayın fazası"), name);
        const polygon = scene.svg.match(/<clipPath id="astro-lit-face"><path d="([^"]+)"/)[1];
        assert.ok(Math.abs((area(polygon) / (Math.PI * 69 ** 2)) * 100 - percent) < 0.1);
    }
    const first = moonphase.render({ phase: 90, runs: 0 });
    assert.equal(number(first, "Yeni aydan keçən vaxt"), 7.38);
});
test("lunar day controls accumulate elapsed time; the sampling grid changes only the instrument", async () => {
    const { moonphase } = await subject;
    const initial = moonphase.render({ phase: 0, days: 1.5, runs: 4, tool: "telescope" });
    const grid = moonphase.render({ phase: 0, days: 1.5, runs: 4, tool: "grid" });
    assert.equal(number(initial, "Yeni aydan keçən vaxt"), 6);
    assert.deepEqual(grid.results, initial.results);
    assert.notEqual(grid.svg, initial.svg);
    assert.equal(number(moonphase.render({ phase: 0, days: 1, runs: 30 }), "Yeni aydan keçən vaxt"), 0.47);
});
test("solar altitude and shadow length reverse seasons between hemispheres", async () => {
    const { seasons } = await subject;
    const s = (latitude, day, tool = "short") => seasons.render({ latitude, longitude: 0, day, tool });
    const north = s(40, 172),
        south = s(-40, 172);
    assert.ok(Math.abs(number(north, "Günəşin üfüqdən hündürlüyü") - 73.45) < 0.12);
    assert.ok(Math.abs(number(south, "Günəşin üfüqdən hündürlüyü") - 26.55) < 0.12);
    assert.equal(get(north, "Kölgənin istiqaməti"), "Şimal");
    assert.equal(get(south, "Kölgənin istiqaməti"), "Cənub");
    const geometric = 1 / Math.tan((number(north, "Günəşin üfüqdən hündürlüyü") * Math.PI) / 180);
    assert.ok(Math.abs(number(north, "Kölgənin uzunluğu") - geometric) < 0.006);
    assert.ok(Math.abs(number(s(40, 172, "tall"), "Kölgənin uzunluğu") - 2 * geometric) < 0.006);
    assert.ok(number(s(40, 355), "Günəşin üfüqdən hündürlüyü") < 27);
});
test("polar night, local solar noon, longitude and year wrap are handled explicitly", async () => {
    const { seasons } = await subject;
    const at = (longitude, day, latitude = 40, runs = 0) => seasons.render({ longitude, day, latitude, runs });
    const night = at(0, 355, 80);
    assert.ok(number(night, "Günəşin üfüqdən hündürlüyü") < 0);
    assert.equal(get(night, "Kölgənin uzunluğu"), "Kölgə yoxdur");
    assert.equal(get(night, "Kölgənin istiqaməti"), "—");
    const minutes = (label) => {
        const [h, m] = label.split(":").map(Number);
        return h * 60 + m;
    };
    const utc = (scene) => get(scene, "Günəş günortası (UTC)");
    assert.equal(minutes(utc(at(0, 172))) - minutes(utc(at(30, 172))), 120);
    assert.match(utc(at(180, 304)), /əvvəlki gün/);
    assert.match(utc(at(-180, 42)), /sonrakı gün/);
    assert.deepEqual(at(0, 365, 40, 1).results, at(0, 7, 40).results);
});
test("unknown tools and invalid numbers cannot enter scene markup", async () => {
    for (const experiment of Object.values(await subject)) {
        const input = Object.fromEntries(
            experiment.controls.map((c) => [c.id, "<foreignObject>invalid</foreignObject>"])
        );
        const scene = experiment.render({ ...input, tool: "__proto__", runs: Infinity });
        assert.doesNotMatch(scene.svg, /<foreignObject|NaN|Infinity|style=|<script/i);
        assert.ok(scene.results.every((r) => typeof r.value === "string"));
    }
});
