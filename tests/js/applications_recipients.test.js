"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const script = fs.readFileSync(path.resolve(__dirname, "../../apps/accounts/static/accounts/js/profile/applications_recipients.js"), "utf8");

test("konkret prorektor seçimi tələb olunur və şöbə dəyişdikdə köhnə seçim qalmır", () => {
    const dom = new JSDOM('<div id="box"><div data-apx-unit-list></div></div>', { runScripts: "outside-only" });
    dom.window.EMSApplications = { t: key => key };
    dom.window.eval(script);
    const box = dom.window.document.getElementById("box");
    const pick = dom.window.EMSApplications.recipientPicker;
    const unit = { requires_recipient: true, recipients: [{ id: "7", name: "Prorektor <Ad>" }] };
    pick(box, unit);
    const select = box.querySelector("select");
    assert.equal(select.required, true);
    assert.equal(select.value, "");
    assert.equal(select.options[1].textContent, "Prorektor <Ad>");
    assert.equal(box.querySelector("ad"), null);
    select.value = "7";
    pick(box, unit);
    assert.equal(box.querySelectorAll("select").length, 1);
    assert.equal(box.querySelector("select").value, "");
    pick(box, { requires_recipient: false });
    assert.equal(box.querySelector("select"), null);
    dom.window.close();
});
