/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-03: jurnal başlığındakı toplu «i/e» / «q/b» YALNIZ BOŞ xanaları doldurur —
   müəllimin əvvəlcədən yazdığı q/b, i/e və bal toxunulmaz qalır. Mühazirə xanası da seminar/lab
   kimi açılan seçimdir (data-jd-semselect, bal yoxdur). journal_grid.js ƏSL DOM-da (jsdom).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/registrar/static/registrar/js/journal_grid.js"), "utf8");

function cell(lesson, att, score, value, withScore) {
    return (
        "<td>" +
        '<input type="hidden" data-jd-att data-jd-sem-att value="' + att + '">' +
        (withScore ? '<input type="hidden" data-jd-sem-score value="' + score + '">' : "") +
        '<div class="jd2-semselect"><select data-jd-semselect data-lesson="' + lesson + '">' +
        '<option value="">—</option><option value="qb">q/b</option><option value="ie">i/e</option>' +
        (withScore ? '<option value="7">7</option>' : "") +
        "</select></div></td>"
    );
}

function page() {
    const rows = [
        cell("L1", "absent", "", "qb", true), // q/b — qalmalıdır
        cell("L1", "present", "7", "7", true), // bal — qalmalıdır
        cell("L1", "", "", "", true), // boş — i/e olmalıdır
        cell("L2", "", "", "", false), // mühazirə, boş
        cell("L2", "absent", "", "qb", false), // mühazirə, q/b
    ];
    const html =
        '<div data-jd-page data-offering-id="o1"><form data-jd-draft><table><tr>' +
        rows.join("") +
        '</tr></table></form><button data-jd-bulk="present" data-lesson="L1">i/e</button>' +
        '<button data-jd-bulk="present" data-lesson="L2">i/e</button>' +
        '<button data-jd-bulk="absent" data-lesson="L2">q/b</button></div>';
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/jurnal/o1/",
    });
    const { window } = dom;
    window.gettext = (s) => s;
    window.interpolate = (s) => s;
    window.EMSDelegate = { on: () => {} };
    window.eval(SCRIPT);
    // Server render-i kimi: hər select-in ilkin seçimi gizli dəyərlərdən (bərpa yolu ilə eyni qayda).
    const selects = Array.from(window.document.querySelectorAll("[data-jd-semselect]"));
    selects.forEach((sel) => {
        const td = sel.closest("td");
        const att = td.querySelector("[data-jd-sem-att]").value;
        const scoreInput = td.querySelector("[data-jd-sem-score]");
        sel.value = att === "absent" ? "qb" : scoreInput && scoreInput.value ? scoreInput.value : att === "present" ? "ie" : "";
    });
    return { window, selects };
}

function state(selects) {
    return selects.map((sel) => {
        const td = sel.closest("td");
        const score = td.querySelector("[data-jd-sem-score]");
        return [sel.value, td.querySelector("[data-jd-sem-att]").value, score ? score.value : null];
    });
}

test("bulk i/e keeps q/b and scores, fills only empty cells", () => {
    const { window, selects } = page();
    try {
        window.document.querySelector('[data-jd-bulk="present"][data-lesson="L1"]').click();
        window.document.querySelector('[data-jd-bulk="present"][data-lesson="L2"]').click();
        assert.deepEqual(state(selects), [
            ["qb", "absent", ""],
            ["7", "present", "7"],
            ["ie", "present", ""],
            ["ie", "present", null],
            ["qb", "absent", null],
        ]);
    } finally {
        window.close();
    }
});

test("bulk q/b also fills only empty cells", () => {
    const { window, selects } = page();
    try {
        window.document.querySelector('[data-jd-bulk="absent"][data-lesson="L2"]').click();
        assert.deepEqual(state(selects).slice(3), [
            ["qb", "absent", null],
            ["qb", "absent", null],
        ]);
    } finally {
        window.close();
    }
});
