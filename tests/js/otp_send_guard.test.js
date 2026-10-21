/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-21: OTP «Təsdiq kodu göndər» ikiqat göndərişi
   (apps/accounts/static/accounts/js/otp_send_guard.js + otp_timer.js) ƏSL DOM-da (jsdom).
   Fayllar olduğu kimi icra olunur.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const GUARD = fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/otp_send_guard.js"), "utf8");
const TIMER = fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/otp_timer.js"), "utf8");

const tick = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function page(html, scripts) {
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/accounts/set-password/",
    });
    const { window } = dom;
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    // jsdom forma göndərişini (naviqasiya) icra etmir — sayğacla əvəz edirik.
    window.__submits = 0;
    window.HTMLFormElement.prototype.requestSubmit = function () {
        const event = new window.Event("submit", { bubbles: true, cancelable: true });
        if (this.dispatchEvent(event)) {
            window.__submits += 1;
        }
    };
    for (const script of scripts) {
        window.eval(script);
    }
    return window;
}

const SEND_FORM =
    '<form id="f" method="post" data-otp-submit-once data-busy-label="Göndərilir…">' +
    '<input name="email" value="a@b.az"><button type="submit" class="auth-submit-btn">Təsdiq kodu göndər</button></form>';

test("first submit locks the button and shows the sending label; the second submit is cancelled", async () => {
    const window = await page(SEND_FORM, [GUARD]);
    try {
        const doc = window.document;
        const form = doc.getElementById("f");
        const button = form.querySelector("button");

        form.requestSubmit();
        form.requestSubmit(); // ikiqat klik / Enter — eyni tikdə
        await tick(5);
        form.requestSubmit(); // düymə artıq bağlıdır, yenə də ləğv olunur

        assert.equal(window.__submits, 1);
        assert.equal(button.disabled, true);
        assert.equal(button.textContent, "Göndərilir…");
        assert.equal(form.getAttribute("aria-busy"), "true");
    } finally {
        window.close();
    }
});

test("a submit cancelled by another script does not lock the form", async () => {
    const window = await page(SEND_FORM, [GUARD]);
    try {
        const doc = window.document;
        const form = doc.getElementById("f");
        form.addEventListener("submit", (event) => event.preventDefault());
        form.requestSubmit();
        await tick(5);
        assert.equal(window.__submits, 0);
        assert.equal(form.querySelector("button").disabled, false);
        assert.equal(form.dataset.otpSubmitting, undefined);
    } finally {
        window.close();
    }
});

test("forms without the attribute are untouched", async () => {
    const window = await page('<form id="g"><button type="submit">Go</button></form>', [GUARD]);
    try {
        const form = window.document.getElementById("g");
        form.requestSubmit();
        form.requestSubmit();
        await tick(5);
        assert.equal(window.__submits, 2);
        assert.equal(form.querySelector("button").disabled, false);
    } finally {
        window.close();
    }
});

test("resend button waits for the server cooldown and then unlocks", async () => {
    const html =
        '<form data-otp-submit-once><button type="submit" class="auth-link-btn" data-otp-resend-wait="1" ' +
        'data-label-wait="Kodu yenidən göndər ({s} san.)">Kodu yenidən göndər</button></form>';
    const window = await page(html, [GUARD]);
    try {
        const button = window.document.querySelector("button");
        assert.equal(button.disabled, true);
        assert.equal(button.textContent, "Kodu yenidən göndər (1 san.)");
        for (let waited = 0; button.disabled && waited < 3500; waited += 100) {
            await tick(100);
        }
        assert.equal(button.disabled, false);
        assert.equal(button.textContent, "Kodu yenidən göndər");
    } finally {
        window.close();
    }
});

test("guard script is idempotent (AJAX re-run binds the listener once)", async () => {
    const window = await page(SEND_FORM, [GUARD, GUARD]);
    try {
        const form = window.document.getElementById("f");
        form.requestSubmit();
        await tick(5);
        assert.equal(window.__submits, 1);
        assert.equal(form.querySelector("button").disabled, true);
    } finally {
        window.close();
    }
});

test("validity countdown uses server seconds, not the client clock", async () => {
    const html =
        '<div data-otp-timer data-otp-remaining-seconds="125" data-otp-expires-at="2000-01-01T00:00:00+04:00" ' +
        'data-expired-label="Kodun vaxtı keçib"><strong data-otp-countdown>--:--</strong>' +
        "<span data-otp-expired-note hidden>new</span></div>";
    const window = await page(html, [TIMER]);
    try {
        const banner = window.document.querySelector("[data-otp-timer]");
        // ISO tarix keçmişdədir (səhv saat), amma server 125 s deyir — sayğac «vaxtı keçib» GÖSTƏRMİR.
        assert.equal(banner.querySelector("[data-otp-countdown]").textContent, "02:05");
        assert.equal(banner.classList.contains("is-expired"), false);
    } finally {
        window.close();
    }
});

test("expired code shows the expired label and the resend note", async () => {
    const html =
        '<div data-otp-timer data-otp-remaining-seconds="0" data-expired-label="Kodun vaxtı keçib">' +
        "<strong data-otp-countdown>--:--</strong><span data-otp-expired-note hidden>new</span></div>";
    const window = await page(html, [TIMER]);
    try {
        const banner = window.document.querySelector("[data-otp-timer]");
        assert.equal(banner.querySelector("[data-otp-countdown]").textContent, "Kodun vaxtı keçib");
        assert.equal(banner.classList.contains("is-expired"), true);
        assert.equal(banner.querySelector("[data-otp-expired-note]").hidden, false);
    } finally {
        window.close();
    }
});
