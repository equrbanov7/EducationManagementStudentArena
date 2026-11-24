"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const script = fs.readFileSync(path.resolve(__dirname, "../../apps/exams/static/exams/js/export_waiting.js"), "utf8");
function waitingPage(response) {
    const dom = new JSDOM('<div id="exportWaitingCard" data-status-url="/status" data-i18n-failed="İxrac alınmadı">' +
        '<p hidden data-waiting-error></p></div>', { runScripts: "outside-only", url: "https://example.test/wait" });
    const { window } = dom;
    let requests = 0;
    const timers = [];
    window.setTimeout = callback => timers.push(callback);
    window.fetch = async () => { requests++; return response; };
    window.eval(script);
    return { dom, window, timers, requests: () => requests };
}

test("a terminal HTTP response ends export polling", async () => {
    const page = waitingPage({ status: 404, ok: false });
    try {
        await new Promise(resolve => setImmediate(resolve));
        assert.equal(page.timers.length, 0);
        const error = page.window.document.querySelector("[data-waiting-error]");
        assert.equal(error.hidden, false);
        assert.equal(error.textContent, "İxrac alınmadı");
    } finally { page.dom.window.close(); }
});

test("leaving the waiting page stops old requests", async () => {
    const page = waitingPage({ status: 200, ok: true, json: async () => ({ status: "pending" }) });
    try {
        await new Promise(resolve => setImmediate(resolve));
        assert.equal(page.timers.length, 1);
        page.window.document.getElementById("exportWaitingCard").remove();
        page.timers[0]();
        assert.equal(page.requests(), 1);
    } finally { page.dom.window.close(); }
});
