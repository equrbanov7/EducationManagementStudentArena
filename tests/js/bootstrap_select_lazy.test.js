/* ═══════════════════════════════════════════════════════════════════════════
   PERF-2 H3 (2026-10-17): static/js/bootstrap_select.js menyunu TƏNBƏL qurur.
   ƏSL göndərilən skript (jsdom). Yoxlanılır:
     · init yalnız toggle-u qurur (variant düymələri yoxdur), etiket seçilmiş variantdandır;
     · `show.bs.dropdown` (Bootstrap açılışı) və toggle fokusu menyunu qurur;
     · delegə klik native `<select>`-ə yazır və `change` (bubbles) göndərir;
     · bağlı menyuda `refresh()` → növbəti açılışda gizli option-lar nəzərə alınır;
     · açıq menyuda `refresh()` dərhal yenidən qurur; canlı axtarış + Enter ilk uyğunu seçir;
     · təkrar init ikinci toggle yaratmır, disabled select toggle-u da söndürür.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const BSELECT = fs.readFileSync(path.join(ROOT, "static/js/bootstrap_select.js"), "utf8");

function page(selectHtml) {
    const dom = new JSDOM(
        '<!doctype html><html><body><div class="bootstrap-single-select">' + selectHtml + "</div></body></html>",
        { runScripts: "outside-only", pretendToBeVisual: true }
    );
    const { window } = dom;
    window.eval(BSELECT);
    window.EMSBootstrapSelect.init(window.document);
    const select = window.document.querySelector("select");
    const wrap = select.closest(".bootstrap-single-select");
    return {
        window,
        select,
        toggle: wrap.querySelector(".bootstrap-single-select__toggle"),
        menu: wrap.querySelector(".bootstrap-single-select__menu"),
        options: () => Array.from(wrap.querySelectorAll(".bootstrap-single-select__option")),
        open() {
            this.toggle.dispatchEvent(new window.Event("show.bs.dropdown", { bubbles: true }));
            this.menu.classList.add("show");
            this.toggle.dispatchEvent(new window.Event("shown.bs.dropdown", { bubbles: true }));
        },
        close() {
            this.menu.classList.remove("show");
            this.toggle.dispatchEvent(new window.Event("hidden.bs.dropdown", { bubbles: true }));
        },
    };
}

const SCORES = '<select data-bootstrap-select name="s"><option value="">—</option>' +
    [0, 1, 2, 3, 4, 5].map((n) => '<option value="' + n + '"' + (n === 3 ? " selected" : "") + ">" + n + "</option>").join("") +
    "</select>";

test("init builds only the toggle; the label comes from the selected option", () => {
    const p = page(SCORES);
    assert.equal(p.options().length, 0, "variant düymələri hələ qurulmayıb");
    assert.equal(p.menu.children.length, 0);
    assert.equal(p.toggle.querySelector(".bootstrap-single-select__label-text").textContent, "3");
    assert.equal(p.toggle.classList.contains("is-placeholder"), false);
    assert.ok(p.select.classList.contains("is-enhanced"));
    p.window.close();
});

test("first open builds the menu once, with the selected option marked", () => {
    const p = page(SCORES);
    p.open();
    const buttons = p.options();
    assert.equal(buttons.length, 7);
    assert.deepEqual(buttons.filter((b) => b.classList.contains("is-selected")).map((b) => b.dataset.value), ["3"]);
    assert.ok(buttons[0].classList.contains("is-placeholder"));
    const first = buttons[1];
    p.close();
    p.open();
    assert.equal(p.options()[1], first, "təkrar açılışda yenidən qurulmur");
    p.window.close();
});

test("focusing the toggle pre-builds the menu", () => {
    const p = page(SCORES);
    p.toggle.focus();
    assert.equal(p.options().length, 7);
    p.window.close();
});

test("a delegated click writes the native select and fires a bubbling change", () => {
    const p = page(SCORES);
    const seen = [];
    p.window.document.body.addEventListener("change", (event) => seen.push(event.target.value));
    p.open();
    p.options().find((b) => b.dataset.value === "5").click();
    assert.equal(p.select.value, "5");
    assert.deepEqual(seen, ["5"]);
    assert.equal(p.toggle.querySelector(".bootstrap-single-select__label-text").textContent, "5");
    assert.deepEqual(p.options().filter((b) => b.classList.contains("is-selected")).map((b) => b.dataset.value), ["5"]);
    p.window.close();
});

test("disabled options are not selectable", () => {
    const p = page('<select data-bootstrap-select><option value="a">A</option><option value="b" disabled>B</option></select>');
    p.open();
    const b = p.options().find((btn) => btn.dataset.value === "b");
    assert.equal(b.disabled, true);
    b.click();
    assert.equal(p.select.value, "a");
    p.window.close();
});

test("refresh on a closed menu rebuilds on the next open (hidden options skipped)", () => {
    const p = page(SCORES);
    p.open();
    p.close();
    p.select.querySelector('option[value="4"]').hidden = true;
    p.select.value = "1";
    p.window.EMSBootstrapSelect.refresh(p.select);
    assert.equal(p.toggle.querySelector(".bootstrap-single-select__label-text").textContent, "1");
    p.open();
    assert.deepEqual(p.options().map((b) => b.dataset.value), ["", "0", "1", "2", "3", "5"]);
    p.window.close();
});

test("refresh on an open menu rebuilds immediately", () => {
    const p = page(SCORES);
    p.open();
    const opt = p.window.document.createElement("option");
    opt.value = "9";
    opt.textContent = "9";
    p.select.appendChild(opt);
    p.select._refreshBootstrapSelect();
    assert.ok(p.options().some((b) => b.dataset.value === "9"));
    p.window.close();
});

test("live search filters the built menu and Enter picks the first match", () => {
    const p = page('<select data-bootstrap-select data-live-search="true" data-live-search-placeholder="Axtar">' +
        '<option value="">Seç</option><option value="1">Bakı</option><option value="2">Gəncə</option>' +
        '<option value="3">Sumqayıt</option></select>');
    p.open();
    const input = p.menu.querySelector(".bootstrap-single-select__search-input");
    assert.ok(input, "axtarış sahəsi menyunun başındadır");
    input.value = "gən";
    input.dispatchEvent(new p.window.Event("input", { bubbles: true }));
    assert.deepEqual(p.options().filter((b) => !b.hidden).map((b) => b.dataset.value), ["2"]);
    input.dispatchEvent(new p.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    assert.equal(p.select.value, "2");
    p.window.close();
});

test("re-init does not add a second toggle; disabled select disables the toggle", () => {
    const p = page('<select data-bootstrap-select disabled><option value="">—</option></select>');
    p.window.EMSBootstrapSelect.init(p.window.document);
    p.window.document.dispatchEvent(new p.window.CustomEvent("profile:section:loaded", { detail: {} }));
    assert.equal(p.window.document.querySelectorAll(".bootstrap-single-select__toggle").length, 1);
    assert.equal(p.toggle.disabled, true);
    assert.ok(p.toggle.classList.contains("is-placeholder"));
    p.window.close();
});
