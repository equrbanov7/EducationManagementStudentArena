/* ═══════════════════════════════════════════════════════════════════════════
   UX2 2026-10-05: jurnal grid-in sağındakı «N q/b» sayğacı davamiyyət dəyişəndə canlı yenilənir.
   Server sayı (pəncərədən kənar dərslər daxil) baza götürülür; fərq = indi q/b olan select-lər −
   render olunanda q/b olan select-lər (option.defaultSelected). journal_grid_absence.js ƏSL DOM-da (jsdom).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/registrar/static/registrar/js/journal_grid_absence.js"), "utf8");

function select(selected) {
    const opt = (v, label) => '<option value="' + v + '"' + (selected === v ? " selected" : "") + ">" + label + "</option>";
    return (
        '<td><input type="hidden" data-jd-att value="">' +
        '<select data-jd-semselect>' + opt("", "—") + opt("qb", "q/b") + opt("ie", "i/e") + "</select></td>"
    );
}

function page() {
    // 1-ci sətir: server sayı 3 (pəncərədən kənar 2 + bu gün 1 q/b), 2-ci: server sayı 0.
    const html =
        "<table><tbody>" +
        '<tr class="jd2-row">' + select("qb") + select("") + '<td><span class="jd2-qchip">3 q/b</span></td></tr>' +
        '<tr class="jd2-row">' + select("") + select("ie") + '<td><span class="jd2-qchip">0 q/b</span></td></tr>' +
        "</tbody></table>";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/jurnal/o1/",
    });
    const { window } = dom;
    // Layihənin ems_ajax_init.js-inin delegasiya davranışı (document-də tək dinləyici).
    window.EMSDelegate = {
        on(type, selector, handler) {
            window.document.addEventListener(type, (event) => {
                const match = event.target.closest(selector);
                if (match) handler.call(match, event, match);
            });
        },
    };
    window.EMSReady = (fn) => fn();
    window.EMSReady.once = (key, fn) => fn();
    window.eval(SCRIPT);
    return window;
}

const tick = (window) => new Promise((resolve) => window.setTimeout(resolve, 5));

function change(window, sel, value) {
    sel.value = value;
    sel.dispatchEvent(new window.Event("change", { bubbles: true }));
}

function chips(window) {
    return Array.from(window.document.querySelectorAll(".jd2-qchip")).map((c) => c.textContent);
}

test("q/b selected → counter goes up by one, baseline includes out-of-window server absences", async () => {
    const window = page();
    await tick(window);
    assert.deepEqual(chips(window), ["3 q/b", "0 q/b"]);
    const second = window.document.querySelectorAll("tr.jd2-row")[1].querySelectorAll("select")[0];
    change(window, second, "qb");
    await tick(window);
    assert.deepEqual(chips(window), ["3 q/b", "1 q/b"]);
    assert.ok(window.document.querySelectorAll(".jd2-qchip")[1].classList.contains("is-live"));
});

test("clearing a rendered q/b lowers the counter; returning to the rendered state restores it", async () => {
    const window = page();
    await tick(window);
    const first = window.document.querySelectorAll("tr.jd2-row")[0].querySelectorAll("select")[0];
    change(window, first, "");
    await tick(window);
    assert.deepEqual(chips(window), ["2 q/b", "0 q/b"]);
    change(window, first, "qb");
    await tick(window);
    assert.deepEqual(chips(window), ["3 q/b", "0 q/b"]);
    assert.ok(!window.document.querySelectorAll(".jd2-qchip")[0].classList.contains("is-live"));
});

test("i/e and empty are not absences; several changes in one tick recount once", async () => {
    const window = page();
    await tick(window);
    const selects = window.document.querySelectorAll("tr.jd2-row")[1].querySelectorAll("select");
    change(window, selects[0], "qb");
    change(window, selects[1], "qb");
    change(window, selects[0], "ie");
    await tick(window);
    assert.deepEqual(chips(window), ["3 q/b", "1 q/b"]);
});
