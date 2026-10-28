"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const root = path.resolve(__dirname, "../..");
const source = fs.readFileSync(path.join(root, "apps/accounts/static/accounts/js/profile/applications_thread.js"), "utf8");
const mobileCss = fs.readFileSync(path.join(root, "apps/accounts/static/accounts/css/profile/applications_mobile.css"), "utf8");

test("actual detail rendering has a visible font-independent close control with accessible name", () => {
    const dom = new JSDOM("<main></main>", { runScripts: "outside-only" });
    const w = dom.window;
    w.EMSApplications = { esc: value => String(value || ""), t: key => key === "closeDetail" ? "Bağla" : key,
        dateTime: value => value, rules: {} };
    w.eval(source);
    const app = { number: "LOCAL-TEST", subject: "Local preview", body: "Local fixture only", submitted_at: "2026-10-28",
        requester: { name: "Test" }, kind: {}, status: {}, current_unit: {}, events: [], allowed_actions: [], viewer: {} };
    w.document.querySelector("main").innerHTML = w.EMSApplications.thread.html(app, {});
    const button = w.document.querySelector("[data-apx-detail-close]");
    assert.equal(button.tagName, "BUTTON");
    assert.equal(button.getAttribute("aria-label"), "Bağla");
    const glyph = button.querySelector(".apx-modal__closeglyph");
    assert.equal(glyph.textContent, "×");
    assert.equal(glyph.getAttribute("aria-hidden"), "true");
    assert.equal(button.querySelector("i"), null, "closing must not depend on an icon font");
    dom.window.close();
});

test("mobile close control retains a centered 44px target and readable glyph", () => {
    const rules = mobileCss.slice(mobileCss.indexOf("@media (max-width: 640px)"));
    const close = rules.match(/\.apx-modal__close\s*\{([^}]+)\}/)[1];
    assert.match(close, /min-width:\s*44px/);
    assert.match(close, /min-height:\s*44px/);
    assert.match(close, /justify-content:\s*center/);
    const glyph = rules.match(/\.apx-modal__closeglyph\s*\{([^}]+)\}/)[1];
    assert.match(glyph, /font-size:\s*24px/);
    assert.match(glyph, /line-height:\s*1\s*;/);
});
