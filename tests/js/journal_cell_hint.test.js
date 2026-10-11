/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-10: jurnal xanasının üstünə gələndə (və ya fokusda) onun KİMƏ aid olduğu
   görünür — «Soyad Ad Ata adı» + sütun etiketi. journal_cell_hint.js ƏSL DOM-da (jsdom).
   Ad sətirdə (`[data-jd-hint-name]`), etiket başlıqdadır (`th[data-jd-hint-col]`).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/registrar/static/registrar/js/journal_cell_hint.js"), "utf8");

function page() {
    const html =
        '<table data-jd-hint><thead><tr>' +
        "<th>№ · SOYAD AD ATA ADI</th>" +
        '<th data-jd-hint-col="09.10.2026 · Seminar">09.10</th>' +
        "<th>QAYIB</th>" +
        "</tr></thead><tbody>" +
        '<tr class="jd2-row"><td class="jd2-td-student"><span data-jd-hint-name>Vəliyev Əli Həsən</span></td>' +
        '<td class="jd2-cell"><button type="button">q/b</button></td><td>1 q/b</td></tr>' +
        '<tr class="jd2-row"><td class="jd2-td-student"><span data-jd-hint-name>Vəliyev Əli Rəşid</span></td>' +
        '<td class="jd2-cell"><button type="button">i/e</button></td><td>0 q/b</td></tr>' +
        "</tbody></table><p id=\"outside\">x</p>";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/jurnal/o1/",
    });
    const { window } = dom;
    window.EMSReady = (fn) => fn();
    window.EMSReady.once = (key, fn) => fn();
    window.eval(SCRIPT);
    return window;
}

function over(window, el) {
    el.dispatchEvent(new window.MouseEvent("mouseover", { bubbles: true }));
}

function cell(window, row, col) {
    return window.document.querySelectorAll("tbody tr")[row].children[col];
}

function tip(window) {
    return window.document.getElementById("jd-cell-hint");
}

test("hovering a mark cell shows that row's full name and the lesson label", () => {
    const window = page();
    over(window, cell(window, 1, 1).querySelector("button"));
    const box = tip(window);
    assert.ok(box && !box.hidden);
    assert.equal(box.querySelector(".jd-hint__name").textContent, "Vəliyev Əli Rəşid");
    assert.equal(box.querySelector(".jd-hint__meta").textContent, "09.10.2026 · Seminar");
    assert.ok(window.document.querySelectorAll("tbody tr")[1].classList.contains("is-hint-row"));
    assert.ok(cell(window, 1, 1).classList.contains("is-hint-cell"));
    assert.ok(window.document.querySelectorAll("thead th")[1].classList.contains("is-hint-col"));
});

test("moving to another row switches the name and clears the previous row's highlight", () => {
    const window = page();
    over(window, cell(window, 0, 1));
    over(window, cell(window, 1, 1));
    assert.equal(tip(window).querySelector(".jd-hint__name").textContent, "Vəliyev Əli Rəşid");
    assert.ok(!window.document.querySelectorAll("tbody tr")[0].classList.contains("is-hint-row"));
    assert.ok(!cell(window, 0, 1).classList.contains("is-hint-cell"));
});

test("a column without a label shows only the name; the name cell itself shows nothing", () => {
    const window = page();
    over(window, cell(window, 0, 2));
    assert.equal(tip(window).querySelector(".jd-hint__name").textContent, "Vəliyev Əli Həsən");
    assert.ok(tip(window).querySelector(".jd-hint__meta").hidden);
    over(window, cell(window, 0, 0));
    assert.ok(tip(window).hidden);
});

test("leaving the table hides the hint; keyboard focus shows it and links aria-describedby", () => {
    const window = page();
    over(window, cell(window, 0, 1));
    over(window, window.document.getElementById("outside"));
    assert.ok(tip(window).hidden);
    assert.ok(!window.document.querySelector(".is-hint-row"));

    const button = cell(window, 1, 1).querySelector("button");
    button.focus();
    assert.ok(!tip(window).hidden);
    assert.equal(button.getAttribute("aria-describedby"), "jd-cell-hint");
    window.document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    assert.ok(tip(window).hidden);
    assert.equal(button.getAttribute("aria-describedby"), null);
});

test("the name is written as text, never as markup", () => {
    const window = page();
    window.document.querySelector("[data-jd-hint-name]").textContent = "<img src=x onerror=alert(1)>";
    over(window, cell(window, 0, 1));
    assert.equal(tip(window).querySelector("img"), null);
    assert.equal(tip(window).querySelector(".jd-hint__name").textContent, "<img src=x onerror=alert(1)>");
});

function rect(top, bottom) {
    return { top, bottom, left: 100, right: 180, width: 80, height: bottom - top, x: 100, y: top };
}

function withMenu(window, menuTop, menuBottom) {
    const td = cell(window, 1, 1);
    const menu = window.document.createElement("div");
    menu.className = "dropdown-menu show";
    td.appendChild(menu);
    td.getBoundingClientRect = () => rect(300, 340);
    menu.getBoundingClientRect = () => rect(menuTop, menuBottom);
    over(window, td);
    Object.defineProperty(tip(window), "offsetHeight", { value: 40, configurable: true });
    Object.defineProperty(tip(window), "offsetWidth", { value: 160, configurable: true });
    td.dispatchEvent(new window.Event("shown.bs.dropdown", { bubbles: true }));
    return tip(window);
}

test("menu opened upward (overlapping the cell edge) → hint goes below the cell", () => {
    const box = withMenu(page(), 90, 304);
    assert.ok(!box.hidden);
    assert.equal(box.style.top, "348px");
});

test("menu opened downward → hint stays above the cell", () => {
    const box = withMenu(page(), 336, 600);
    assert.ok(!box.hidden);
    assert.equal(box.style.top, "252px");
});
