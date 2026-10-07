/* ═══════════════════════════════════════════════════════════════════════════
   Review 2026-10-07: «Elanlar» → «Müraciət et» (keçid rejimi)
   (apps/announcements/static/announcements/js/detail.js) ƏSL kodla, jsdom-da.

   Bug: keçid `window.open(href, "_blank", "noopener,noreferrer")` ilə açılırdı.
   HTML spesifikasiyasına görə `noopener`/`noreferrer` verilən `window.open`
   HƏMİŞƏ `null` qaytarır — kod bunu «popup bloklandı» sayıb qəbz POST-undan
   sonra CARİ səhifəni də həmin keçidə aparırdı: keçid iki dəfə açılır, tələbə
   kabinetdən çıxır. `window.open` burada spesifikasiyaya uyğun saxta ilə
   əvəzlənir (noopener → null, bloklanmış popup → null).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const INIT = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/announcements/static/announcements/js/detail.js"), "utf8");
const HREF = "https://forms.example.org/apply";

async function page({ popupBlocked }) {
    const navigations = [];
    const virtualConsole = new VirtualConsole();
    virtualConsole.on("jsdomError", (error) => {
        if (String(error && error.message).includes("navigation")) navigations.push(error.message);
    });
    const html =
        '<section data-ann-apply data-apply-url="/elanlar/api/x/apply/" data-msg-error="err">' +
        '<button type="button" data-ann-apply-link data-href="' + HREF + '">Go</button>' +
        "<p data-ann-apply-result hidden></p></section>";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/accounts/profile/?section=announcements&elan=x",
        virtualConsole,
    });
    const { window } = dom;
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    const opened = [];
    const posts = [];
    window.open = function (url, target, features) {
        const popup = { url, target, features: features || "", opener: window };
        opened.push(popup);
        // Spesifikasiya: noopener/noreferrer → həmişə null; bloklanmış popup → null.
        if (popupBlocked || /noopener|noreferrer/.test(features || "")) return null;
        return popup;
    };
    window.EMSCore = {
        fetchJSON(url, options) {
            posts.push({ url, options });
            return Promise.resolve({ ok: true, created: true });
        },
    };
    window.eval(INIT);
    window.eval(SCRIPT);
    return { window, opened, posts, navigations };
}

async function flush() {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setImmediate(resolve));
}

test("link opens ONCE in a new tab and the cabinet page stays put", async () => {
    const { window, opened, posts, navigations } = await page({ popupBlocked: false });
    try {
        window.document.querySelector("[data-ann-apply-link]").click();
        await flush();
        assert.equal(posts.length, 1, "qəbz POST-u getməlidir");
        assert.deepEqual(navigations, [], "cari səhifə keçidə getməməlidir (keçid iki dəfə açılırdı)");
        assert.equal(opened.length, 1, "keçid bir dəfə açılmalıdır");
        assert.equal(opened[0].url, HREF);
        assert.equal(opened[0].target, "_blank");
        assert.equal(opened[0].opener, null, "yeni pəncərənin opener-i kəsilməlidir (tabnabbing)");
    } finally {
        window.close();
    }
});

test("blocked popup falls back to same-tab navigation after the receipt", async () => {
    const { window, posts, navigations } = await page({ popupBlocked: true });
    try {
        window.document.querySelector("[data-ann-apply-link]").click();
        await flush();
        assert.equal(posts.length, 1);
        assert.equal(navigations.length, 1, "popup bloklananda cari tab keçidə getməlidir");
    } finally {
        window.close();
    }
});
