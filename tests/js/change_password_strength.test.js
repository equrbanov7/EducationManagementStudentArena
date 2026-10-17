/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-15 «sadə parol»: «Şifrəni dəyiş» köməkçisi
   (apps/accounts/static/accounts/js/profile/change_password_strength.js) ƏSL DOM-da (jsdom).
   Göstərici yalnız MƏLUMATDIR — 8+ simvollu sadə parol göndərməni bağlamır, qırmızı «bad» vermir.

   Göndərilən fayllar OLDUĞU KİMİ icra olunur:
     static/js/ems_ajax_init.js — EMSReady / EMSDelegate
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const INIT = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const SCRIPT = fs.readFileSync(
    path.join(ROOT, "apps/accounts/static/accounts/js/profile/change_password_strength.js"),
    "utf8"
);

const PANEL =
    '<section data-profile-section-panel="change-password">' +
    '<div data-password-mode-panel="current"><form class="pwform">' +
    '<div class="pwfield"><div class="pwfield__control" data-pw-meter><input type="password" name="new_password1"></div>' +
    '<div class="pwmeter" data-pw-meter-out data-level="0"></div>' +
    '<p data-pw-meter-label data-label-none="none" data-label-weak="short" data-label-fair="ok"' +
    ' data-label-good="good" data-label-strong="strong"></p></div>' +
    '<button type="submit">Save</button></form></div>' +
    '<aside><div data-pw-rules data-pw-min="8" data-pw-username="elvin.qurbanov"' +
    ' data-pw-trivial="12345678 password qwerty12">' +
    '<ul><li data-pw-rule="length"><i class="pwrule__icon"></i></li>' +
    '<li data-pw-rule="trivial"><i class="pwrule__icon"></i></li></ul></div></aside></section>';

async function makeWindow() {
    const dom = new JSDOM("<!doctype html><html><body>" + PANEL + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/accounts/profile/?section=change-password",
    });
    const { window } = dom;
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    window.eval(INIT);
    window.eval(SCRIPT);
    return window;
}

function type(window, value) {
    const input = window.document.querySelector("[data-pw-meter] input");
    input.value = value;
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
}

function state(window, rule) {
    return window.document.querySelector('[data-pw-rule="' + rule + '"]').getAttribute("data-state");
}

test("simple 8-char passwords are acceptable and never block submit", async () => {
    const window = await makeWindow();
    try {
        const doc = window.document;
        for (const value of ["elvin123", "19850412", "salam123"]) {
            type(window, value);
            assert.ok(Number(doc.querySelector("[data-pw-meter-out]").getAttribute("data-level")) >= 2, value);
            assert.equal(doc.querySelector("[data-pw-meter-label]").textContent === "short", false, value);
            assert.equal(state(window, "length"), "ok", value);
            assert.equal(state(window, "trivial"), "ok", value);
            assert.equal(doc.querySelector("button[type=submit]").disabled, false, value);
        }
    } finally {
        window.close();
    }
});

test("a single repeated character is flagged as trivial like the server rule", async () => {
    const window = await makeWindow();
    try {
        for (const value of ["aaaaaaaa", "ZZZZZZZZZ", "11111111", "........"]) {
            type(window, value);
            assert.equal(state(window, "trivial"), "bad", value);
            assert.equal(window.document.querySelector("button[type=submit]").disabled, false, value);
        }
        type(window, "aaaaaaab");
        assert.equal(state(window, "trivial"), "ok");
    } finally {
        window.close();
    }
});

test("short password is neutral (no 'bad'), blocklisted and username are flagged", async () => {
    const window = await makeWindow();
    try {
        type(window, "elvin12");
        assert.equal(window.document.querySelector("[data-pw-meter-label]").textContent, "short");
        assert.equal(state(window, "length"), "idle");
        assert.notEqual(state(window, "trivial"), "bad");

        type(window, "Password");
        assert.equal(state(window, "trivial"), "bad");
        type(window, "elvin.qurbanov");
        assert.equal(state(window, "trivial"), "bad");
        assert.equal(window.document.querySelector("button[type=submit]").disabled, false);
    } finally {
        window.close();
    }
});

test("strength levels grow with length but start at 'ok' once the minimum is met", async () => {
    const window = await makeWindow();
    try {
        const api = window.EMSPasswordStrength;
        const rules = api.policy();
        assert.equal(rules.min, 8);
        assert.equal(api.strengthOf("", rules), 0);
        assert.equal(api.strengthOf("abc", rules), 1);
        assert.equal(api.strengthOf("abcdefgh", rules), 2);
        assert.equal(api.strengthOf("Salam123!xyz", rules), 4);
    } finally {
        window.close();
    }
});
