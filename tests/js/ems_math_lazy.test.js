/* ═══════════════════════════════════════════════════════════════════════════
   Perf 2026-10-07: `static/js/ems_math.js` KaTeX-i TƏNBƏL yükləyir — ƏSL DOM-da
   (jsdom) icra testləri. Göndərilən fayl OLDUĞU KİMİ icra olunur (skript teqinin
   `data-katex-*` atributları `document.currentScript`-dən oxunur).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SOURCE = fs.readFileSync(path.join(ROOT, "static/js/ems_math.js"), "utf8");

async function boot(body) {
    const dom = new JSDOM("<!doctype html><html><head></head><body>" + body + "</body></html>", {
        runScripts: "dangerously",
        url: "http://localhost/exams/x/attempt/1/",
    });
    const { window } = dom;
    // Real səhifədəki kimi: `defer` skript DOM hazır olandan sonra işləyir.
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    const script = window.document.createElement("script");
    script.setAttribute("data-katex-css", "/static/vendor/katex/katex.min.css");
    script.setAttribute("data-katex-js", "/static/vendor/katex/katex.min.js");
    script.setAttribute("data-katex-autorender", "/static/vendor/katex/auto-render.min.js");
    script.textContent = SOURCE;
    window.document.body.appendChild(script); // jsdom icra edir, currentScript = bu teq
    return window;
}

function katexNodes(window) {
    return {
        links: [...window.document.querySelectorAll('link[href*="katex"]')].map((n) => n.getAttribute("href")),
        scripts: [...window.document.querySelectorAll('script[src*="katex"]')],
    };
}

test("a page without formulas never downloads KaTeX", async () => {
    const window = await boot('<div data-ems-math>Sadə sual mətni</div><div data-ems-math>Qiymət 5 AZN</div>');
    const { links, scripts } = katexNodes(window);
    assert.deepEqual(links, []);
    assert.equal(scripts.length, 0);
    window.document.querySelectorAll("[data-ems-math]").forEach((node) => {
        assert.equal(node.getAttribute("data-ems-math-done"), "1");
    });
});

test("a formula triggers one ordered KaTeX load, then renders", async () => {
    const window = await boot('<div data-ems-math id="q">Hesabla \\(\\frac{a}{b}\\)</div>');
    const { links, scripts } = katexNodes(window);
    assert.deepEqual(links, ["/static/vendor/katex/katex.min.css"]);
    assert.deepEqual(scripts.map((s) => s.getAttribute("src")), [
        "/static/vendor/katex/katex.min.js",
        "/static/vendor/katex/auto-render.min.js",
    ]);
    assert.ok(scripts.every((s) => s.async === false), "sıra saxlanılmalıdır (async=false)");

    const rendered = [];
    window.renderMathInElement = (node, options) => rendered.push([node.id, options.trust, options.throwOnError]);
    // Təkrar skan (MutationObserver / EMSReady) ikinci yükləmə yaratmamalıdır.
    window.EMSMath.render(window.document);
    scripts.forEach((s) => s.dispatchEvent(new window.Event("load")));
    assert.equal(katexNodes(window).scripts.length, 2);
    assert.deepEqual(rendered, [["q", false, false]]);
    assert.equal(window.document.getElementById("q").getAttribute("data-ems-math-done"), "1");
});

test("a failed KaTeX download leaves the text readable and does not retry in a loop", async () => {
    const window = await boot('<div data-ems-math>\\(x^2\\)</div>');
    const { scripts } = katexNodes(window);
    scripts.forEach((s) => s.dispatchEvent(new window.Event("error")));
    window.EMSMath.render(window.document);
    assert.equal(katexNodes(window).scripts.length, 2);
    assert.match(window.document.querySelector("[data-ems-math]").textContent, /x\^2/);
});
