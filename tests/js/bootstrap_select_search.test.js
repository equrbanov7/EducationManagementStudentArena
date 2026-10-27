/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-27: «seçilmiş hər yerdə, filterdə search etmək olsun».
   static/js/bootstrap_select.js — menyu-daxili axtarış DEFAULT açıqdır. ƏSL
   göndərilən skript + search_fold.js (EMSSearch) jsdom-da. Yoxlanılır:
     · ≥ 6 variant → axtarış (atributsuz), ≤ 5 → yox; `data-live-search` true/false məcburi;
     · variantlar sonradan doldurulsa (dərs yükü dialoqu) axtarış növbəti açılışda görünür;
     · diakritik/registr tolerantlığı (ə/e, ş/s, ı/i, ç/c, ö/o, ü/u, ğ/g);
     · «nəticə yoxdur» + placeholder kataloqdan (window.gettext);
     · açılışda fokus axtarışda, bağlananda sorğu təmizlənir; variantda hərf → axtarışa;
     · sonradan DOM-a düşən select (dialoq/partial) MutationObserver ilə qoşulur,
       sarğısız `data-bootstrap-select` (Django widget) özü sarğılanır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const BSELECT = fs.readFileSync(path.join(ROOT, "static/js/bootstrap_select.js"), "utf8");
const FOLD = fs.readFileSync(path.join(ROOT, "static/js/search_fold.js"), "utf8");

const CITIES = ["Bakı", "Gəncə", "Sumqayıt", "Şəki", "Quba", "Ağdam", "Şamaxı", "Göyçay", "Ucar", "Lənkəran"];

function optionsHtml(labels) {
    return '<option value="">Seçilməyib</option>' +
        labels.map((label, i) => '<option value="' + (i + 1) + '">' + label + "</option>").join("");
}

function setup(bodyHtml, { gettext } = {}) {
    const dom = new JSDOM("<!doctype html><html><body>" + bodyHtml + "</body></html>", {
        runScripts: "outside-only",
        pretendToBeVisual: true,
    });
    const { window } = dom;
    if (gettext) {
        window.gettext = gettext;
    }
    window.eval(FOLD);
    window.eval(BSELECT);
    window.EMSBootstrapSelect.init(window.document);
    return window;
}

function handle(window, select) {
    const wrap = select.closest(".bootstrap-single-select");
    const toggle = wrap.querySelector(".bootstrap-single-select__toggle");
    const menu = wrap.querySelector(".bootstrap-single-select__menu");
    return {
        toggle,
        menu,
        input: () => menu.querySelector(".bootstrap-single-select__search-input"),
        empty: () => menu.querySelector(".bootstrap-single-select__search-empty"),
        visible: () => Array.from(menu.querySelectorAll(".bootstrap-single-select__option:not([hidden])"))
            .map((b) => b.textContent.trim()),
        open() {
            toggle.dispatchEvent(new window.Event("show.bs.dropdown", { bubbles: true }));
            menu.classList.add("show");
            toggle.dispatchEvent(new window.Event("shown.bs.dropdown", { bubbles: true }));
        },
        close() {
            menu.classList.remove("show");
            toggle.dispatchEvent(new window.Event("hidden.bs.dropdown", { bubbles: true }));
        },
        type(text) {
            const input = this.input();
            input.value = text;
            input.dispatchEvent(new window.Event("input", { bubbles: true }));
        },
    };
}

function single(attrs, labels) {
    return '<div class="bootstrap-single-select"><select data-bootstrap-select ' + attrs + ">" +
        optionsHtml(labels) + "</select></div>";
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test("search is on by default for lists with six or more options", () => {
    const window = setup(single("", CITIES.slice(0, 6)));
    const h = handle(window, window.document.querySelector("select"));
    h.open();
    assert.ok(h.input(), "atributsuz select-də də axtarış sahəsi var");
    assert.ok(h.menu.classList.contains("bootstrap-single-select__menu--searchable"));
    window.close();
});

test("tiny fixed lists (five or fewer options) stay without search", () => {
    const window = setup(single("", CITIES.slice(0, 5)));
    const h = handle(window, window.document.querySelector("select"));
    h.open();
    assert.equal(h.input(), null);
    assert.equal(h.menu.classList.contains("bootstrap-single-select__menu--searchable"), false);
    window.close();
});

test("data-live-search forces the search on or off", () => {
    const window = setup(single('data-live-search="true"', CITIES.slice(0, 2)) +
        single('data-live-search="false"', CITIES));
    const [forced, off] = Array.from(window.document.querySelectorAll("select")).map((s) => handle(window, s));
    forced.open();
    off.open();
    assert.ok(forced.input());
    assert.equal(off.input(), null);
    window.close();
});

test("options filled after init (workload dialog) get the search on the next open", () => {
    const window = setup(single('name="subject_id"', []));
    const select = window.document.querySelector("select");
    const h = handle(window, select);
    h.open();
    assert.equal(h.input(), null, "yalnız «Seçilməyib» — axtarış yoxdur");
    h.close();
    CITIES.forEach((label, i) => {
        const option = window.document.createElement("option");
        option.value = String(i + 1);
        option.textContent = label;
        select.appendChild(option);
    });
    window.EMSBootstrapSelect.refresh(select);
    h.open();
    assert.ok(h.input(), "variantlar gəldikdən sonra axtarış görünür");
    assert.equal(h.visible().length, CITIES.length + 1);
    window.close();
});

test("filtering is diacritic- and case-tolerant", () => {
    const window = setup(single("", CITIES));
    const h = handle(window, window.document.querySelector("select"));
    h.open();
    h.type("gence");
    assert.deepEqual(h.visible(), ["Gəncə"]);
    h.type("SEKI");
    assert.deepEqual(h.visible(), ["Şəki"]);
    h.type("samaxi");
    assert.deepEqual(h.visible(), ["Şamaxı"]);
    h.type("goycay");
    assert.deepEqual(h.visible(), ["Göyçay"]);
    h.type("agdam");
    assert.deepEqual(h.visible(), ["Ağdam"]);
    h.type("lənk");
    assert.deepEqual(h.visible(), ["Lənkəran"]);
    window.close();
});

test("no-results text and placeholder come from the JS catalog", () => {
    const window = setup(single("", CITIES), { gettext: (s) => "T:" + s });
    const h = handle(window, window.document.querySelector("select"));
    h.open();
    assert.equal(h.input().placeholder, "T:Axtar…");
    assert.equal(h.input().getAttribute("aria-label"), "T:Axtar…");
    assert.equal(h.empty().hidden, true);
    h.type("zzzz");
    assert.deepEqual(h.visible(), []);
    assert.equal(h.empty().hidden, false);
    assert.equal(h.empty().textContent, "T:Uyğun nəticə yoxdur");
    window.close();
});

test("opening focuses the search; closing clears the query", async () => {
    const window = setup(single("", CITIES));
    const h = handle(window, window.document.querySelector("select"));
    h.open();
    await tick();
    assert.equal(window.document.activeElement, h.input());
    h.type("quba");
    assert.deepEqual(h.visible(), ["Quba"]);
    h.close();
    assert.equal(h.input().value, "");
    assert.equal(h.visible().length, CITIES.length + 1);
    window.close();
});

test("Enter picks the first match; typing on an option jumps back to the search", () => {
    const window = setup(single("", CITIES));
    const select = window.document.querySelector("select");
    const h = handle(window, select);
    h.open();
    h.type("ucar");
    h.input().dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    const focused = window.document.activeElement;
    assert.ok(focused.classList.contains("bootstrap-single-select__option"));
    focused.dispatchEvent(new window.KeyboardEvent("keydown", { key: "b", bubbles: true }));
    assert.equal(window.document.activeElement, h.input());
    h.input().dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    assert.equal(select.value, String(CITIES.indexOf("Ucar") + 1));
    window.close();
});

test("an open menu rebuilt by refresh keeps the typed query", () => {
    const window = setup(single("", CITIES));
    const select = window.document.querySelector("select");
    const h = handle(window, select);
    h.open();
    h.type("bak");
    window.EMSBootstrapSelect.refresh(select);
    assert.equal(h.input().value, "bak");
    assert.deepEqual(h.visible(), ["Bakı"]);
    window.close();
});

test("selects inserted later (dialogs, partials) are enhanced automatically", async () => {
    const window = setup("<main></main>");
    const main = window.document.querySelector("main");
    main.innerHTML = single('id="late"', CITIES) +
        '<label>Rating <select id="bare" data-bootstrap-select>' + optionsHtml(CITIES) + "</select></label>";
    await tick();
    const late = window.document.getElementById("late");
    const bare = window.document.getElementById("bare");
    assert.ok(late.classList.contains("is-enhanced"));
    assert.ok(bare.classList.contains("is-enhanced"), "sarğısız widget də qoşulur");
    assert.ok(bare.parentElement.classList.contains("bootstrap-single-select"));
    assert.ok(bare.classList.contains("bootstrap-single-select__native"));
    const h = handle(window, bare);
    h.open();
    assert.ok(h.input());
    window.close();
});
