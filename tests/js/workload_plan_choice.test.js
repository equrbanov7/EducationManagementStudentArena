const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const forms = fs.readFileSync(path.join(__dirname, "../../apps/accounts/static/accounts/js/profile/workload_distribution_forms.js"), "utf8");

test("plan suggestions require a choice and leave period, groups and contact hours with the operator", () => {
    const dom = new JSDOM(`<form>
        <select name="subject_id"><option value="old" selected>Old</option></select><input name="subject_text" value="old">
        <select name="specialty_id"></select><select name="season"><option value="fall">Fall</option><option value="spring">Spring</option></select>
        <select name="degree_level"><option value="bachelor">Bachelor</option></select>
        <input name="credits" value="5"><input name="credits_value" value="5"><input name="lab_total" value="30">
        <select name="period_id"><option value="p" selected>Period</option></select>
        <input name="lecture_plan" value="15"><input name="lecture_total" value="60">
        <input name="seminar_total" value="45"><input name="subgroup_count" value="2">
        <select name="group_ids" multiple><option value="g" selected>G</option><option value="h" selected>H</option></select>
        <select id="suggestions" data-placeholder="Choose"></select>
    </form>`, { runScripts: "outside-only" });
    const win = dom.window;
    win.eval(forms);
    const form = win.document.querySelector("form");
    const select = form.querySelector("#suggestions");
    const rows = [["a", "Algebra", "fall", "3"], ["b", "Analysis", "spring", "7"], ["b", "Analysis", "spring", "4"]].map(([id, name, season, credits]) => ({
        subject_id: id, subject_name: name, specialty_id: "sp", specialty_name: "Math",
        degree_level: "bachelor", season, credits, credits_value: Number(credits),
        semester_number: 2, lecture_hours: 10, seminar_hours: 5, lab_hours: 0,
    }));
    const api = win.EMSWorkloadForms;
    api.planChoices(select, rows, row => row.subject_name + " · " + row.credits);
    api.applyPlanChoice(form, select);
    assert.equal(select.value, "");
    assert.equal(form.elements.subject_id.value, "old");
    assert.equal(form.elements.credits.value, "5");
    assert.equal(select.options[2].textContent, "Analysis · 7");
    select.selectedIndex = 2;
    api.applyPlanChoice(form, select);
    const values = api.values(form);
    assert.deepEqual([values.subject_id, values.specialty_id, values.season, values.credits, values.credits_value],
        ["b", "sp", "spring", "7", "7"]);
    assert.equal(values.subject_text, "");
    select.selectedIndex = 3;
    api.applyPlanChoice(form, select);
    const variant = api.values(form);
    assert.deepEqual([variant.subject_id, variant.specialty_id, variant.credits, variant.credits_value], ["b", "sp", "4", "4"]);
    assert.deepEqual([variant.period_id, Array.from(variant.group_ids), variant.subgroup_count], ["p", ["g", "h"], "2"]);
    assert.deepEqual([variant.lecture_plan, variant.lecture_total, variant.seminar_total, variant.lab_total], ["15", "60", "45", "30"]);
    assert.equal("suggestions" in values, false);
});
