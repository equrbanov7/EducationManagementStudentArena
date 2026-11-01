"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/registrar/static/registrar/js/journal_grid.js"), "utf8");

test("joint-history disclosure stays on the list; ordinary row still opens journal", () => {
    const dom = new JSDOM('<table><tr data-jl-href="#joint"><td><span id="row-label">Group 1 + Group 2</span>' +
        '<details><summary><span id="summary-label">Separate records</span></summary>' +
        '<p id="history">Anonymous legacy history</p></details></td></tr></table>',
        { runScripts: "outside-only", url: "http://localhost/jurnal/" });
    const { window } = dom;
    window.gettext = (value) => value;
    window.interpolate = (value) => value;
    window.EMSDelegate = { on: () => {} };
    window.eval(SCRIPT);
    window.document.getElementById("summary-label").click();
    assert.equal(window.location.hash, "");
    assert.equal(window.document.querySelector("details").open, true);
    window.document.getElementById("history").click();
    assert.equal(window.location.hash, "");
    window.document.getElementById("row-label").click();
    assert.equal(window.location.hash, "#joint");
    window.close();
});

test("unsupported legacy score explains its own lock instead of a time-window lock", () => {
    const dom = new JSDOM('<form data-jd-lock-url="/requests/" data-jd-lock-msg-time="Time elapsed" ' +
        'data-jd-lock-msg-unsupported_score="Stored legacy score is protected"><span data-jd-lock="unsupported_score">0</span></form>',
        { runScripts: "outside-only", url: "http://localhost/jurnal/" });
    const { window } = dom;
    let body;
    window.EMSConfirm = { open: (options) => { body = options.body; return Promise.resolve(false); } };
    window.eval(fs.readFileSync(path.join(ROOT, "apps/registrar/static/registrar/js/journal_mark_lock.js"), "utf8"));
    window.EMSJournalMarkLock.explain(window.document.querySelector("[data-jd-lock]"));
    assert.equal(body, "Stored legacy score is protected");
    assert.equal(window.document.querySelector("[data-jd-lock]").textContent, "0");
    window.close();
});
