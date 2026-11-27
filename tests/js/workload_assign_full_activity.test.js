const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const forms = fs.readFileSync(path.join(__dirname, "../../apps/accounts/static/accounts/js/profile/workload_distribution_forms.js"), "utf8");

// Sahib 2026-11-28: tam bölünmüş mühazirədə «Bölüşdür» boş «Vakant» forması açırdı (müəllim təyin olunmayıb kimi).
test("full activity with one teacher opens that assignment; otherwise a new one", () => {
    const dom = new JSDOM("<div></div>", { runScripts: "outside-only" });
    dom.window.eval(forms);
    const api = dom.window.EMSWorkloadForms;
    const lecture = { id: "a1", activity: "lecture", teacher_id: "7", hours: 45 };
    const row = {
        activities: { lecture: { total: 45, remaining: 0 }, seminar: { total: 30, remaining: 10 } },
        assignments: [lecture, { id: "a2", activity: "seminar", teacher_id: "7", hours: 20 }],
    };
    assert.equal(api.fullAssignment(row, "lecture").id, "a1");
    assert.equal(api.fullAssignment(row, "seminar"), null); // qalıq var → yeni təyinat
    row.assignments.push({ id: "a3", activity: "lecture", teacher_id: "8", hours: 0 });
    assert.equal(api.fullAssignment(row, "lecture"), null); // bir neçə müəllim → çiplər üzərindən redaktə
    assert.equal(api.fullAssignment(null, "lecture"), null);
});
