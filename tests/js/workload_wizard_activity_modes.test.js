const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

function setup(rowOverrides) {
    const window = new JSDOM('<main data-wl-wiz-panel="seminar"></main><main data-wl-wiz-panel="lab"></main>', { runScripts: "outside-only" }).window;
    const document = window.document;
    window.EMSWorkloadDist = { q: selector => document.querySelector(selector), state: { task: { id: "task" } } };
    for (const suffix of ["", "_groups", "_sections", "_units"]) {
        const file = path.join(__dirname, "../../apps/accounts/static/accounts/js/profile/workload_split_wizard" + suffix + ".js");
        window.eval(fs.readFileSync(file, "utf8"));
    }
    const W = window.EMSWorkloadWizard;
    const row = {
        id: "r", groups: ["a", "b"], label: "A · B", subgroup_count: 3, lab_group_count: 1,
        plans: { seminar: 30, lab: 15 }, totals: { seminar: 90, lab: 15 }, assignments: [],
        joint_by_activity: { seminar: false, lab: true }, ...rowOverrides,
    };
    function section(number) { return { number, name: "№" + number, label: "№" + number }; }
    const journal = {
        can_manage: true, block_reason: "", seminar: [1, 2].map(section), lab: [1, 2, 3, 4].map(section),
        students: [1, 2, 3, 4].map((n) => ({ id: String(n), name: "T" + n, seminar: n <= 2 ? 1 : 2, lab: n })),
    };
    const groups = [{ id: "a", name: "A", row_id: row.id, journal }, { id: "b", name: "B", row_id: row.id, journal: null }];
    const data = { rows: [row], groups, task: { can_fix_totals: true } };
    W.S = { data, selected: {} };
    W.init(data);
    W.bindSections({ on(event, selector, handle) {
        document.addEventListener(event, e => {
            const target = e.target.closest(selector);
            if (target) handle(e, target);
        });
    } });
    function show(kind) {
        W.S.step = W.STEPS.indexOf(kind);
        const panel = document.querySelector('[data-wl-wiz-panel="' + kind + '"]');
        W.render[kind](panel);
        return panel;
    }
    function toggle(kind, together) {
        show(kind).querySelector('[data-wl-wiz-joint][data-activity="' + kind + '"][data-value="' + Number(together) + '"]').click();
    }
    return { W, row, show, toggle };
}

test("a hidden lab roster survives seminar edits, and independent lab groups preserve the real numbers", () => {
    const { W, row, show, toggle } = setup();
    const lab = W.S.groups.a.lab;
    const before = JSON.stringify(lab);
    const semPanel = show("seminar");
    assert.equal(semPanel.querySelector('[data-activity="seminar"][aria-pressed="true"]').dataset.value, "0");
    assert.equal(show("lab").querySelector('[data-activity="lab"][aria-pressed="true"]').dataset.value, "1");
    show("seminar").querySelector('[data-wl-wiz-seminar-count="3"][data-group-id="a"]').click();
    assert.equal(JSON.stringify(lab), before);
    toggle("lab", false);
    assert.equal(lab.mode, "flat");
    assert.deepEqual(Array.from(lab.numbers), [1, 2, 3, 4]);
    assert.deepEqual(Object.values(lab.place), [1, 2, 3, 4]);
    assert.equal(W.isJoint(row, "seminar"), false);
    toggle("seminar", true);
    assert.equal(show("lab").querySelector('[data-wl-wiz-lab-mode="nested"]').disabled, true);
    const body = W.payload();
    assert.deepEqual({ ...body.rows[0].joint_by_activity }, { seminar: true, lab: false });
    assert.equal(body.rows[0].joint, true);
    assert.equal(body.groups[0].seminar.count, 0);
    assert.equal(body.groups[0].lab.nested, false);
    assert.equal(body.units.filter(u => u.activity === "seminar").length, 1);
    assert.equal(body.units.filter(u => u.activity === "lab").length, 5);
    assert.deepEqual({ ...W.fixData(row) }, { seminar_total: 30, lab_total: 75, subgroup_count: 1, lab_group_count: 5 });
});

test("a lab-only row can be combined from its lab step without resetting the dormant seminar count", () => {
    const { W, row, show, toggle } = setup({
        subgroup_count: 7, lab_group_count: 5, totals: { seminar: 0, lab: 75 },
        joint_by_activity: { seminar: false, lab: false },
    });
    assert.equal(show("seminar").querySelector("[data-wl-wiz-joint]"), null);
    assert.deepEqual({ ...W.fixData(row) }, {});
    toggle("lab", true);
    assert.equal(W.isJoint(row, "seminar"), false);
    assert.deepEqual({ ...W.fixData(row) }, { lab_total: 15, lab_group_count: 1 });
    assert.equal(W.groupPayload(row, "a").apply_journal, false);
});
