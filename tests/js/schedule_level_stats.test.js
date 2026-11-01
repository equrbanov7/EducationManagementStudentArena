"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const script = fs.readFileSync(path.resolve(__dirname, "../../apps/registrar/static/registrar/js/schedule_grid.js"), "utf8");

function page() {
    const dom = new JSDOM(`<!doctype html><div data-schedule-root>
      <button class="smtx-card" data-sgx-slot data-abs="10" data-abs-limit="10" data-abs-unit="Q/b"
        data-abs-label="Q/b" data-entry="30" data-entry-max="30" data-barred="0">Level10</button>
      <button class="smtx-card" data-sgx-slot data-abs="11" data-abs-limit="10" data-abs-unit="Q/b"
        data-abs-label="Q/b" data-entry="20" data-entry-max="30" data-barred="1">Level11</button>
      <button class="smtx-card" data-sgx-slot data-abs="6" data-abs-limit="15" data-abs-unit="saat"
        data-abs-label="qayıb saatı" data-entry="50" data-entry-max="50" data-barred="0">Regular</button>
      <div data-sgx-modal class="sgx-modal" hidden>
        <button data-sgx-close class="sgx-modal-close">Close</button>
        <div data-sgx-row="stats" data-ok-label="Normal" data-barred-label="Blocked" data-abs-label="qayıb saatı">
          <b data-sgx-f="abs"></b><small data-sgx-f="abs_label"></small>
          <b data-sgx-f="entry"></b><div class="sgx-stat-card--status"><b data-sgx-f="status"></b></div>
        </div>
      </div></div>`, { runScripts: "outside-only" });
    dom.window.eval(script);
    return dom.window;
}

test("level modal shows displayed QB counts and bars only above ten", () => {
    const window = page();
    const doc = window.document;
    const cards = doc.querySelectorAll("[data-sgx-slot]");
    cards[0].click();
    assert.equal(doc.querySelector('[data-sgx-f="abs"]').textContent, "10 / 10 Q/b");
    assert.equal(doc.querySelector('[data-sgx-f="entry"]').textContent, "30 / 30");
    assert.equal(doc.querySelector('[data-sgx-f="status"]').textContent, "Normal");
    cards[1].click();
    assert.equal(doc.querySelector('[data-sgx-f="abs"]').textContent, "11 / 10 Q/b");
    assert.equal(doc.querySelector('[data-sgx-f="status"]').textContent, "Blocked");
    window.close();
});

test("opening a regular card after a level restores hour label and ordinary cap", () => {
    const window = page();
    const doc = window.document;
    const cards = doc.querySelectorAll("[data-sgx-slot]");
    cards[0].click();
    cards[2].click();
    assert.equal(doc.querySelector('[data-sgx-f="abs"]').textContent, "6 / 15 saat");
    assert.equal(doc.querySelector('[data-sgx-f="abs_label"]').textContent, "qayıb saatı");
    assert.equal(doc.querySelector('[data-sgx-f="entry"]').textContent, "50 / 50");
    window.close();
});
