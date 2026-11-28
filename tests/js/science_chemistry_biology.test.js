"use strict";

const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {JSDOM} = require("jsdom");

const directory = path.resolve(__dirname, "../../apps/labs/static/labs/science_room");
function load(name) {
    const source = fs.readFileSync(path.join(directory, name + ".js")).toString("base64");
    return import("data:text/javascript;base64," + source).then(module => module.experiments);
}
function read(scene, label) {
    const row = scene.results.find(item => item.label === label);
    assert.ok(row, label);
    return row.value;
}

test("cabbage pigment identifies acidic juice, a neutral control and a mild base with either tool", async () => {
    const {indicator} = await load("chemistry");
    const {choices} = indicator.controls.find(control => control.id === "sample");
    assert.deepEqual(choices.map(choice => choice.label), ["Təmiz su", "Alma şirəsi", "Limon şirəsi", "Soda məhlulu"]);
    for (const choice of choices) {
        assert.equal(read(indicator.render({sample: choice.value, runs: 1}), "Nümunə"), choice.label);
    }
    for (const {id: tool} of indicator.tools) {
        assert.equal(read(indicator.render({sample: 1, tool, runs: 0}), "Mühit"), "—");
        const kinds = [1, 2, 3, 4].map(sample => read(indicator.render({sample, tool, runs: 1}), "Mühit"));
        assert.deepEqual(kinds, ["Neytral", "Turş", "Turş", "Zəif qələvi"]);
    }
    const solution = indicator.render({sample: 3, tool: "pipette", runs: 1});
    const strip = indicator.render({sample: 3, tool: "strip", runs: 1});
    assert.notEqual(solution.svg, strip.svg);
    assert.equal(read(solution, "İndikatorun rəngi"), read(strip, "İndikatorun rəngi"));
});

test("carbon dioxide yield is limited by the smaller mole count and zero without either reactant", async () => {
    const {bubbles} = await load("chemistry");
    const scene = (vinegar, soda) => bubbles.render({runs: 1, vinegar, soda});
    const gas = (vinegar, soda) => Number.parseFloat(read(scene(vinegar, soda), "Nəzəri CO₂ kütləsi").replace(",", "."));
    assert.equal(gas(0, 3), 0);
    assert.equal(gas(30, 0), 0);
    assert.equal(gas(20, 1), 0.52);
    assert.equal(gas(40, 1), gas(20, 1));
    assert.equal(gas(20, 2), 0.73);
    assert.equal(gas(20, 3), gas(20, 2));
    assert.equal(read(scene(20, 1), "Miqdarı məhdudlaşdıran"), "Qida sodası");
    assert.equal(read(scene(20, 2), "Miqdarı məhdudlaşdıran"), "Sirkə turşusu");
    assert.equal(read(scene(20, 84.007 / 60.052), "Miqdarı məhdudlaşdıran"), "Hər ikisi tam sərf olunur");
    assert.doesNotMatch(bubbles.render({runs: 0, vinegar: 20, soda: 1}).svg, /class="sci-cb-bubble"/);
});

test("a dark tank or absent carbon source stops photosynthesis in the two-factor model", async () => {
    const {photosynthesis} = await load("biology");
    const at = (light, carbon, runs = 1) => photosynthesis.render({light, carbon, runs});
    const rate = (light, carbon) => read(at(light, carbon), "Fotosintez meyli");
    assert.equal(rate(0, 100), "Yoxdur");
    assert.equal(rate(100, 0), "Yoxdur");
    assert.equal(rate(20, 50), rate(20, 100));
    assert.equal(rate(50, 20), rate(100, 20));
    assert.equal(rate(100, 100), "Yüksək");
    assert.equal(read(at(100, 20), "Modeldə məhdudlaşdıran"), "Həll olmuş CO₂");
    assert.equal(read(at(20, 100), "Modeldə məhdudlaşdıran"), "İşıq");
    assert.doesNotMatch(at(80, 80, 0).svg, /class="sci-cb-bubble"/);
});

test("vapor pressure deficit at 25 °C depends on humidity and water loss can occur in still air", async () => {
    const {transpiration} = await load("biology");
    const at = (humidity, air) => transpiration.render({humidity, air, runs: 1});
    assert.equal(read(at(0, 0), "Buxar təzyiqi fərqi (25 °C)"), "3,17 kPa");
    assert.equal(read(at(50, 100), "Buxar təzyiqi fərqi (25 °C)"), "1,58 kPa");
    assert.equal(read(at(50, 0), "Buxar təzyiqi fərqi (25 °C)"), "1,58 kPa");
    assert.equal(read(at(100, 100), "Su itkisinin meyli"), "Yoxdur");
    assert.notEqual(read(at(0, 0), "Su itkisinin meyli"), "Yoxdur");
    assert.equal(read(at(0, 100), "Su itkisinin meyli"), "Yüksək");
});

test("each tool returns standalone, valid SVG at parameter extremes with text results independent of motion", async () => {
    for (const subject of ["chemistry", "biology"]) {
        for (const experiment of Object.values(await load(subject))) {
            for (const {id: tool} of experiment.tools) {
                for (const edge of ["min", "max", "value"]) {
                    const settings = Object.fromEntries(experiment.controls.map(c => [c.id, c[edge]]));
                    const output = experiment.render({...settings, tool, runs: 2});
                    assert.doesNotMatch(output.svg, /\b(?:NaN|undefined|Infinity)\b/);
                    const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 340">' + output.svg + '</svg>';
                    const dom = new JSDOM(svg, {contentType: "image/svg+xml"});
                    assert.ok(dom.window.document.querySelectorAll("path").length > 5);
                    assert.ok(output.results.every(row => row.label && row.value));
                    dom.window.close();
                }
            }
        }
    }
    const css = fs.readFileSync(path.join(directory, "chemistry-biology.css"), "utf8");
    assert.match(css, /@media\s*\(prefers-reduced-motion:\s*no-preference\)/);
});
