"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");
const source = fs.readFileSync(path.resolve(__dirname, "../../apps/accounts/static/accounts/js/profile/syllabus_editor_fields.js"), "utf8");

test("approved autosave keeps submit disabled while a complete draft may submit", () => {
    const dom = new JSDOM('<div data-status="approved"><button data-syl-submit disabled></button></div>', { runScripts: "outside-only" });
    dom.window.eval(source);
    const root = dom.window.document.querySelector("div");
    const button = root.querySelector("button");
    const report = { percent: 100, sections: {}, issues: [] };
    dom.window.EMSSyllabusFields.paintCompletion(root, report, false);
    assert.equal(button.disabled, true);
    root.setAttribute("data-status", "draft");
    dom.window.EMSSyllabusFields.paintCompletion(root, report, false);
    assert.equal(button.disabled, false);
    dom.window.close();
});
