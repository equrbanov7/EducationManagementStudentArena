/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-01: «AI ilə təhlil et» hesabatının render qaydası
   (apps/accounts/static/accounts/js/monitoring/system_monitoring_ai.js) ƏSL DOM-da.
   Model cavabı etibarsız mətndir: əvvəl tam escape, sonra məhdud markdown; keçid yalnız
   yerli «/…» (amma «//» və «/\» YOX) və ya https://.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(
    path.join(ROOT, "apps/accounts/static/accounts/js/monitoring/system_monitoring_ai.js"),
    "utf8"
);

function load() {
    const dom = new JSDOM("<!doctype html><html><body><div id='out'></div></body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/accounts/profile/?section=system-monitoring",
    });
    dom.window.eval(SCRIPT);
    return dom.window;
}

function render(window, text) {
    const out = window.document.getElementById("out");
    out.innerHTML = window.EMSSystemMonitoring.ai.renderMarkdown(text);
    return out;
}

test("markup in the model answer is escaped, never executed", () => {
    const window = load();
    const out = render(window, '<img src=x onerror="alert(1)"> <script>alert(2)</script> **ok**');
    assert.equal(out.querySelectorAll("img, script").length, 0);
    assert.match(out.textContent, /<img src=x onerror="alert\(1\)">/);
    assert.equal(out.querySelector("strong").textContent, "ok");
    window.close();
});

test("headings and both list kinds render as fixed tags", () => {
    const window = load();
    const out = render(window, "## Qısa nəticə\nHər şey normaldır.\n- bir\n- iki\n1. birinci\n2. ikinci");
    assert.equal(out.querySelector("h5.smx-md__h").textContent, "Qısa nəticə");
    assert.equal(out.querySelectorAll("ul > li").length, 2);
    assert.equal(out.querySelectorAll("ol > li").length, 2);
    window.close();
});

test("only local or https links survive; javascript:, // and /\\ do not", () => {
    const window = load();
    const out = render(
        window,
        "[yerli](/accounts/profile/) [https](https://example.org/x) [js](javascript:alert(1)) " +
            "[proto](//evil.example) [slash](/\\evil.example)"
    );
    const hrefs = Array.from(out.querySelectorAll("a")).map((a) => a.getAttribute("href"));
    assert.deepEqual(hrefs, ["/accounts/profile/", "https://example.org/x"]);
    const external = out.querySelector('a[href^="https://"]');
    assert.equal(external.getAttribute("rel"), "noopener noreferrer");
    window.close();
});

test("quotes cannot break out of an href attribute", () => {
    const window = load();
    const out = render(window, '[x](/a"onmouseover="alert(1))');
    const link = out.querySelector("a");
    assert.ok(link, "local link is kept");
    assert.equal(link.getAttributeNames().sort().join(","), "href");
    window.close();
});
