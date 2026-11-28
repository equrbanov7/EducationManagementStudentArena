"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

function loadSubject(file) {
    const location = path.resolve(__dirname, "../../apps/labs/static/labs/science_room", file + ".js");
    return import("data:text/javascript;base64," + fs.readFileSync(location).toString("base64")).then(
        (module) => module.experiments
    );
}
function measure(scene, label) {
    const row = scene.results.find((result) => result.label === label);
    assert.ok(row, `Missing measurement: ${label}`);
    return row.value;
}
function number(text) {
    return Number.parseFloat(text.replace(",", "."));
}
function nearly(actual, expected, tolerance) {
    assert.ok(Math.abs(actual - expected) < tolerance, `${actual} vs. ${expected}`);
}

test("the photoelectric threshold depends on the cathode; no emission has no measured potential", async () => {
    const { photoelectric } = await loadSubject("physics");
    const visible = photoelectric.render({ tool: "sodium", wavelength: 430, runs: 1 });
    const silver = photoelectric.render({ tool: "silver", wavelength: 300, runs: 1 });
    nearly(number(measure(visible, "Fotonun enerjisi")), 1239.841984 / 430, 0.006);
    nearly(number(measure(visible, "Maksimal kinetik enerji")), 1239.841984 / 430 - 2.46, 0.006);
    assert.equal(measure(silver, "Saxlayıcı gərginliyin modulu"), "Ölçülmür");
    const uv = photoelectric.render({ tool: "silver", wavelength: 230, runs: 1 });
    nearly(number(measure(uv, "Saxlayıcı gərginliyin modulu")), 1239.841984 / 230 - 4.73, 0.006);
    assert.ok(uv.svg.includes("Ultrabənövşəyi"));
});
test("one-metre pendulum on Earth and Moon follows the small-angle period", async () => {
    const { pendulum } = await loadSubject("physics");
    function period(tool, length, angle) {
        return number(measure(pendulum.render({ tool, length, angle }), "Bir tam rəqsin dövrü"));
    }
    nearly(period("earth", 1, 5), (2 * Math.PI) / Math.sqrt(9.81), 0.0006);
    nearly(period("moon", 1, 10), (2 * Math.PI) / Math.sqrt(1.62), 0.0006);
    nearly(period("earth", 1, 5) / period("earth", 0.25, 9), 2, 0.002);
});
test("line reports slope, intercepts, horizontal lines and the chosen ordinate", async () => {
    const { linear } = await loadSubject("mathematics");
    const line = linear.render({ tool: "intercepts", slope: -2, intercept: 4, point: 3 });
    assert.equal(number(measure(line, "y = 0 tənliyinin həlli")), 2);
    assert.equal(number(measure(line, "Seçilən nöqtədə y")), -2);
    assert.equal(measure(line, "Oy oxunu kəsdiyi nöqtə"), "(0; 4)");
    const horizontal = (b) => linear.render({ tool: "intercepts", slope: 0, intercept: b, point: 1 });
    assert.equal(measure(horizontal(2), "y = 0 tənliyinin həlli"), "Kəsişmir");
    assert.equal(measure(horizontal(0), "y = 0 tənliyinin həlli"), "Bütün həqiqi ədədlər");
});
test("random trials are stable on redraw and count real generated outcomes", async () => {
    const { probability } = await loadSubject("mathematics");
    for (const [tool, sides] of [
        ["coin", 2],
        ["die", 6]
    ]) {
        const before = probability.render({ tool, trials: 120, runs: 0 });
        assert.equal(measure(before, "Müşahidə edilən say"), "Sınağı başladın");
        const run = (i) => probability.render({ tool, trials: 120, runs: i });
        assert.deepEqual(run(4), run(4));
        assert.notEqual(run(1).svg, run(2).svg);
        const current = run(4),
            hits = number(measure(current, "Müşahidə edilən say"));
        assert.equal(number(measure(current, "Gözlənilən say")), 120 / sides);
        assert.ok(Number.isInteger(hits) && hits >= 0 && hits <= 120);
        nearly(number(measure(current, "Nisbi tezlik")), (100 * hits) / 120, 0.051);
    }
});
test("each SVG accepts numeric and tool controls only; reduced motion keeps diagrams static", async () => {
    const physics = await loadSubject("physics"),
        maths = await loadSubject("mathematics");
    const old = globalThis.matchMedia;
    globalThis.matchMedia = () => ({ matches: true });
    try {
        for (const e of Object.values({ ...physics, ...maths })) {
            const input = Object.fromEntries(e.controls.map((c) => [c.id, "<script>NaN</script>"]));
            const example = e.render({ ...input, tool: "<script>", runs: 2 });
            assert.doesNotMatch(example.svg, /<script|<animate|NaN|Infinity|style=|onload=/i);
            assert.ok(example.results.every((r) => typeof r.value === "string"));
        }
    } finally {
        if (old) globalThis.matchMedia = old;
        else delete globalThis.matchMedia;
    }
});
