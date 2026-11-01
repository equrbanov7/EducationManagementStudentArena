/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-11-02: tələbə hərəkəti «Yeni qrup» — siyahı ilk 50 qrupdur, axtarışda
   «2535 ML» tapılmırdı. static/js/bootstrap_select.js `data-live-search-url`:
     · yazılan sorğu serverə `?q=…&limit=50` ilə gedir, variantlar cavabla əvəzlənir;
     · server tapdığı variantı yerli süzgəc gizlətmir;
     · seçili variant və placeholder saxlanılır; köhnə (gecikmiş) cavab yenisini əzmir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const BSELECT = fs.readFileSync(path.join(ROOT, "static/js/bootstrap_select.js"), "utf8");
const REMOTE = fs.readFileSync(path.join(ROOT, "static/js/bootstrap_select_remote.js"), "utf8");
const FOLD = fs.readFileSync(path.join(ROOT, "static/js/search_fold.js"), "utf8");

const FIRST = ["131 Si ing", "131 Sİ rus", "131 T", "132 P", "132 P RUS", "132 P ing"];
const SERVER = { "2535 ml": ["2535 ML"], "535 i": ["535 İ"] };

function setup() {
    const options = '<option value="">Seçin</option>' +
        FIRST.map((name, i) => '<option value="g' + i + '">' + name + "</option>").join("");
    const dom = new JSDOM(
        '<!doctype html><html><body><div class="bootstrap-single-select"><select data-bootstrap-select ' +
            'data-live-search="true" data-live-search-url="/people/academic/groups/">' + options +
            "</select></div></body></html>",
        { runScripts: "outside-only", pretendToBeVisual: true, url: "https://ems.test/accounts/profile/" }
    );
    const { window } = dom;
    window.requests = [];
    window.fetch = (url) => {
        const parsed = new window.URL(url);
        window.requests.push(parsed.pathname + parsed.search);
        const q = (parsed.searchParams.get("q") || "").toLowerCase();
        const names = q ? SERVER[q] || [] : FIRST;
        return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ results: names.map((text) => ({ id: "id-" + text, text })) }),
        });
    };
    window.eval(FOLD);
    window.eval(REMOTE);
    window.eval(BSELECT);
    window.EMSBootstrapSelect.init(window.document);
    const select = window.document.querySelector("select");
    const wrap = select.closest(".bootstrap-single-select");
    const toggle = wrap.querySelector(".bootstrap-single-select__toggle");
    const menu = wrap.querySelector(".bootstrap-single-select__menu");
    return {
        window,
        select,
        menu,
        open() {
            toggle.dispatchEvent(new window.Event("show.bs.dropdown", { bubbles: true }));
            menu.classList.add("show");
            toggle.dispatchEvent(new window.Event("shown.bs.dropdown", { bubbles: true }));
        },
        type(text) {
            const input = menu.querySelector(".bootstrap-single-select__search-input");
            input.value = text;
            input.dispatchEvent(new window.Event("input", { bubbles: true }));
        },
        visible: () => Array.from(menu.querySelectorAll(".bootstrap-single-select__option:not([hidden])"))
            .map((b) => b.textContent.trim()),
    };
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test("server axtarışı ilk 50-dən kənar qrupu tapır və yerli süzgəc onu gizlətmir", async () => {
    const ui = setup();
    ui.open();
    ui.type("2535 ml");
    await wait(320);
    assert.ok(ui.window.requests.some((r) => r === "/people/academic/groups/?q=2535+ml&limit=50"));
    assert.deepEqual(ui.visible(), ["2535 ML"]);
    assert.equal(ui.menu.querySelector(".bootstrap-single-select__search-input").value, "2535 ml");
    ui.menu.querySelector('.bootstrap-single-select__option[data-value="id-2535 ML"]').click();
    assert.equal(ui.select.value, "id-2535 ML");
});

test("seçili variant və placeholder yeni sorğuda saxlanılır; köhnə cavab yenisini əzmir", async () => {
    const ui = setup();
    ui.select.value = "g2";
    ui.open();
    ui.type("2535 ml");
    ui.type("535 i");
    await wait(320);
    const values = Array.from(ui.select.options).map((o) => o.value);
    assert.deepEqual(values, ["", "g2", "id-535 İ"]);
    assert.equal(ui.select.value, "g2");
    assert.equal(ui.window.requests.filter((r) => r.includes("2535")).length, 0);
});

test("atributsuz select serverə sorğu göndərmir", async () => {
    const ui = setup();
    ui.select.removeAttribute("data-live-search-url");
    ui.open();
    ui.type("132");
    await wait(320);
    assert.deepEqual(ui.window.requests, []);
    assert.deepEqual(ui.visible(), ["132 P", "132 P RUS", "132 P ing"]);
});

test("köhnə cavab yeni sorğunun debounce müddətində də variantları əvəzləmir", async () => {
    const ui = setup();
    const pending = [];
    ui.window.fetch = (url) => new Promise((resolve) => pending.push({ url, resolve }));
    ui.open();
    ui.type("2535 ml");
    await wait(300);
    assert.equal(pending.length, 1);
    ui.type("535 i");
    pending[0].resolve({ ok: true, json: async () => ({ results: [{ id: "old", text: "OLD" }] }) });
    await wait(0);
    assert.equal(ui.select.querySelector('[value="old"]'), null);
    await wait(300);
    assert.equal(pending.length, 2);
    pending[1].resolve({ ok: true, json: async () => ({ results: [{ id: "new", text: "535 İ" }] }) });
    await wait(0);
    assert.deepEqual(ui.visible(), ["535 İ"]);
    ui.window.close();
});

test("remote seçimlər textContent ilə göstərilir, dublikatlar və yanlış payload atılır", async () => {
    const ui = setup();
    ui.window.fetch = async () => ({ ok: true, json: async () => ({ results: [
        { id: "safe", text: '<img src="x" onerror="alert(1)">' },
        { id: "safe", text: "duplicate" }, { id: {}, text: "bad" }, { id: "bad", text: {} },
    ] }) });
    ui.open();
    ui.type("anything");
    await wait(300);
    assert.equal(ui.select.querySelectorAll('[value="safe"]').length, 1);
    assert.equal(ui.select.querySelector("img"), null);
    assert.deepEqual(ui.visible(), ['<img src="x" onerror="alert(1)">']);
    ui.window.close();
});

test("başqa origin üçün server sorğusu göndərilmir", async () => {
    const ui = setup();
    ui.select.setAttribute("data-live-search-url", "https://other.test/groups/");
    ui.open();
    ui.type("535 i");
    await wait(300);
    assert.deepEqual(ui.window.requests, []);
    ui.window.close();
});
