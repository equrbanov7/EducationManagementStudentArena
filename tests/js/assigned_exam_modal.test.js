"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const script = fs.readFileSync(path.resolve(__dirname, "../../apps/accounts/static/accounts/js/profile/assigned_exam.js"), "utf8");

function setup() {
    const dom = new JSDOM(`<body style="overflow:auto">
      <button id="trigger" class="js-open-assigned-exam-modal" data-is-final="1" data-requires-code="1" data-final-has-ticket="1" data-final-pin="123456"></button>
      <div id="assignedExamInfoBackdrop" aria-hidden="true">
        <div class="assigned-exam-info-modal">
          <button id="assignedExamInfoClose"><i id="close-icon"></i></button>
          <form id="assignedExamCodeForm"><input id="assignedExamAccessCodeInput"></form>
          <div id="assignedExamFinalBlock" hidden><span id="assignedExamFinalPin"></span><span id="assignedExamFinalPinHint"></span></div>
          <button id="assignedExamInfoStartBtn"></button><button id="assignedExamInfoCancelBtn"></button>
        </div>
      </div></body>`, { runScripts: "outside-only", url: "https://example.test/accounts/profile/" });
    const w = dom.window;
    const ctx = { profilePage: true, sectionLinks: [1], sectionPanels: [1] };
    w.gettext = text => text;
    w.EMSProfile = { register: fn => fn(ctx) };
    w.eval(script);
    return { w, ctx, doc: w.document };
}

test("final PIN opens on visible close control, traps focus and restores scroll/focus after closing", () => {
    const { w, ctx, doc } = setup();
    try {
        const trigger = doc.getElementById("trigger");
        trigger.click();
        assert.equal(ctx.isAssignedExamInfoOpen(), true);
        assert.equal(doc.activeElement.id, "assignedExamInfoClose");
        assert.equal(doc.getElementById("assignedExamFinalPin").textContent, "123456");
        assert.equal(doc.body.style.overflow, "hidden");
        doc.activeElement.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true }));
        assert.equal(doc.activeElement.id, "assignedExamInfoCancelBtn");
        doc.activeElement.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
        assert.equal(doc.activeElement.id, "assignedExamInfoClose");
        doc.getElementById("close-icon").click();
        assert.equal(ctx.isAssignedExamInfoOpen(), false);
        assert.equal(doc.body.style.overflow, "auto");
        assert.equal(doc.activeElement, trigger);
    } finally { w.close(); }
});

test("delegated modal still closes after an AJAX replacement, via escape and backdrop", () => {
    const { w, ctx, doc } = setup();
    try {
        const old = doc.getElementById("assignedExamInfoBackdrop");
        old.outerHTML = old.outerHTML;
        doc.getElementById("trigger").click();
        assert.equal(ctx.isAssignedExamInfoOpen(), true);
        doc.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
        assert.equal(ctx.isAssignedExamInfoOpen(), false);
        doc.getElementById("trigger").click();
        doc.getElementById("assignedExamInfoBackdrop").click();
        assert.equal(ctx.isAssignedExamInfoOpen(), false);
    } finally { w.close(); }
});
