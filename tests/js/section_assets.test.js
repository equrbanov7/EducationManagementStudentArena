/* ═══════════════════════════════════════════════════════════════════════════
   Perf 2026-10-07: kabinet bölmə asset yükləyicisi (`section_assets.js`) — ƏSL DOM-da
   (jsdom) icra testləri. Göndərilən fayl OLDUĞU KİMİ icra olunur.

   Müqavilə:
     • səhifədə artıq olan link/skript TƏKRAR qoşulmur;
     • yeni CSS `<head>`-də `data-ems-css-order` kaskad mövqeyinə düşür;
     • yeni JS `async=false` ilə şablon sırasında, bir dəfə qoşulur;
     • eyni URL üçün paralel çağırışlar bir yükləməni bölüşür;
     • `ensure()` YALNIZ hamısı yükləndikdən (load/error) sonra həll olunur.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const LOADER = fs.readFileSync(
    path.join(ROOT, "apps/accounts/static/accounts/js/profile/section_assets.js"),
    "utf8",
);

function makeWindow() {
    const dom = new JSDOM(
        "<!doctype html><html><head>" +
            '<link rel="stylesheet" href="/static/a.css" data-ems-css-order="0">' +
            '<link rel="stylesheet" href="/static/c.css" data-ems-css-order="20">' +
            '<link rel="stylesheet" href="/static/ems_ui.css">' +
            "</head><body>" +
            '<script src="/static/shell.js"></script>' +
            "</body></html>",
        { runScripts: "outside-only", url: "http://localhost/accounts/profile/" },
    );
    dom.window.eval(LOADER);
    return dom.window;
}

function fire(node, type) {
    node.dispatchEvent(new node.ownerDocument.defaultView.Event(type || "load"));
}

test("stylesheets: existing ones are skipped, new ones land at their cascade position", async () => {
    const window = makeWindow();
    const done = window.EMSSectionAssets.ensure({
        css: [
            { href: "/static/a.css", order: 0 },
            { href: "/static/b.css", order: 10 },
            { href: "/static/z.css", order: 99 },
        ],
        js: [],
    });
    const hrefs = [...window.document.head.querySelectorAll('link[rel="stylesheet"]')].map((l) =>
        new URL(l.href).pathname,
    );
    assert.deepEqual(hrefs, ["/static/a.css", "/static/b.css", "/static/c.css", "/static/z.css", "/static/ems_ui.css"]);

    let settled = false;
    done.then(() => { settled = true; });
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(settled, false, "CSS yüklənməmiş swap başlamamalıdır (FOUC)");
    window.document.querySelectorAll('link[href$="b.css"], link[href$="z.css"]').forEach((l) => fire(l));
    await done;
});

test("scripts: present ones are skipped, new ones keep template order and are not async", async () => {
    const window = makeWindow();
    const done = window.EMSSectionAssets.ensure({ css: [], js: ["/static/shell.js", "/static/one.js", "/static/two.js"] });
    const added = [...window.document.querySelectorAll("script[data-ems-section-js]")];
    assert.deepEqual(added.map((s) => new URL(s.src).pathname), ["/static/one.js", "/static/two.js"]);
    assert.ok(added.every((s) => s.async === false), "dinamik skript async=false olmalıdır (sıra)");
    added.forEach((s) => fire(s));
    await done;
});

test("parallel calls share one load per URL and a failed load does not block", async () => {
    const window = makeWindow();
    const first = window.EMSSectionAssets.ensure({ js: ["/static/one.js"], css: [{ href: "/static/b.css", order: 5 }] });
    const second = window.EMSSectionAssets.ensure({ js: ["/static/one.js"], css: [{ href: "/static/b.css", order: 5 }] });
    assert.equal(window.document.querySelectorAll('script[src$="one.js"]').length, 1);
    assert.equal(window.document.querySelectorAll('link[href$="b.css"]').length, 1);
    fire(window.document.querySelector('script[src$="one.js"]'), "error");
    fire(window.document.querySelector('link[href$="b.css"]'));
    await Promise.all([first, second]);
});

test("ensure tolerates missing payloads", async () => {
    const window = makeWindow();
    await window.EMSSectionAssets.ensure(undefined);
    await window.EMSSectionAssets.ensure({});
    assert.equal(window.document.querySelectorAll("script[data-ems-section-js]").length, 0);
});
