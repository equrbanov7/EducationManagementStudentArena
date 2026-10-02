/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-01: giriş bloku geri sayımı (apps/accounts/static/accounts/js/login_lockout.js)
   ƏSL DOM-da (jsdom). Fayl olduğu kimi icra olunur.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/login_lockout.js"), "utf8");

async function page(seconds) {
    const html =
        '<div class="auth-lockout" data-login-lockout data-seconds="' + seconds + '">' +
        '<p data-lockout-waiting>wait <strong data-lockout-countdown>--</strong></p>' +
        "<p data-lockout-ready hidden>ready</p></div>" +
        '<form class="auth-form"><button type="submit" class="auth-submit-btn">Daxil ol</button></form>';
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/accounts/login/muellim/",
    });
    const { window } = dom;
    // Real səhifədəki kimi: skript DOM hazır olandan sonra işləyir.
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    window.eval(SCRIPT);
    return window;
}

test("countdown shows MM:SS and locks the submit button", async () => {
    const window = await page(125);
    try {
        const doc = window.document;
        assert.equal(doc.querySelector("[data-lockout-countdown]").textContent, "02:05");
        assert.equal(doc.querySelector(".auth-submit-btn").disabled, true);
        assert.equal(doc.querySelector("[data-lockout-ready]").hidden, true);
    } finally {
        window.close(); // interval dayansın — test prosesi asılı qalmasın
    }
});

test("when time is up the button unlocks and the ready line appears", async () => {
    const window = await page(1);
    try {
        const doc = window.document;
        // CI 2026-10-02 (Node 20, yüklü runner): sayğac saniyədə bir yoxlayır — kilid 1-ci və ya 2-ci
        // tikdə açılır. Sabit 1.3 s gözləmə əvəzinə şərti 3.5 s-yə qədər yoxla.
        const button = doc.querySelector(".auth-submit-btn");
        for (let waited = 0; button.disabled && waited < 3500; waited += 100) {
            await new Promise((resolve) => setTimeout(resolve, 100));
        }
        assert.equal(button.disabled, false);
        assert.equal(doc.querySelector("[data-lockout-ready]").hidden, false);
        assert.equal(doc.querySelector("[data-lockout-waiting]").hidden, true);
        assert.ok(doc.querySelector("[data-login-lockout]").classList.contains("is-ready"));
    } finally {
        window.close();
    }
});

test("missing or zero seconds leaves the form untouched", async () => {
    const window = await page(0);
    try {
        assert.equal(window.document.querySelector(".auth-submit-btn").disabled, false);
    } finally {
        window.close();
    }
});
