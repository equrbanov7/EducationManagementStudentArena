/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-25: «Yük bölgüsü» süzgəc panelində «Müəllim» axtarışlı seçici, «Vəziyyət» (vakantı olan / tam /
   qismən …), «Fəaliyyət» süzgəci və «Filtrləri sıfırla» — `workload_distribution_list.js` ƏSL DOM-da (jsdom).

   Müqavilə:
     • seçicidə dəyişiklik URL-ə (`wl_teacher` / `wl_status` / `wl_activity`) yazılır, siyahını sıfırdan yükləyir,
       sorğuya `teacher` / `status` / `activity` kimi düşür; eyni dəyər təkrar seçiləndə sorğu getmir;
     • «Müəllim» seçicisi = sağ panel kartları + kafedra hovuzu (təkrarsız), kart süzgəci ilə SİNXRONDUR;
     • «Filtrləri sıfırla» hamısını (üç süzgəc, semestr, axtarış) təmizləyir, düymə yalnız süzgəc varkən görünür;
     • süzgəcli boş nəticə «uyğun sətir yoxdur», süzgəcsiz boş — «tapşırıq yoxdur».
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const JS_DIR = path.join(ROOT, "apps/accounts/static/accounts/js/profile");
const RENDER = fs.readFileSync(path.join(JS_DIR, "workload_distribution_render.js"), "utf8");
const LIST = fs.readFileSync(path.join(JS_DIR, "workload_distribution_list.js"), "utf8");

const HTML = `<!doctype html><html><body>
<section data-profile-section-panel="workload-distribution">
  <div data-wl-root data-rows-url="/r/" data-teachers-url="/t/" data-focus-row="">
    <select data-wl-season><option value="">Hamısı</option><option value="fall">Payız</option></select>
    <input type="search" data-wl-search>
    <select data-wl-teacher-select><option value="">Hamısı</option></select>
    <select data-wl-status><option value="">Hamısı</option><option value="vacant">v</option><option value="full">f</option><option value="hourly">h</option></select>
    <select data-wl-activity><option value="">Hamısı</option><option value="lecture">l</option></select>
    <button type="button" data-wl-reset-filters hidden>reset</button>
    <div data-wl-teacher-filter hidden><b data-wl-teacher-filter-name></b></div>
    <p data-wl-count hidden></p>
    <div data-wl-empty hidden></div>
    <div data-wl-nomatch hidden></div>
    <div data-wl-more hidden><button data-wl-load-more></button><p data-wl-more-error hidden></p></div>
    <div data-wl-teacher-panel></div>
  </div>
</section></body></html>`;

const CARDS = [
    { teacher_id: 7, name: "Ana", hours: 100, norm_hours: 550, fill_percent: 18 },
    { teacher_id: "", is_vacant: true, name: "Vakant", hours: 30, norm_hours: 0, fill_percent: 0 },
    { teacher_id: 8, name: "Bob", hours: 10, norm_hours: 0, fill_percent: 0 },
];

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

function setup(options) {
    options = options || {};
    const dom = new JSDOM(HTML, {
        runScripts: "outside-only",
        url: "http://localhost/accounts/profile/?section=workload-distribution&chair=c1" + (options.query || ""),
    });
    const win = dom.window;
    const handlers = {};
    const fetched = [];
    const queue = (options.responses || []).slice();
    const loadCalls = [];
    const q = (sel) => win.document.querySelector(sel);
    win.EMSDelegate = { on: (evt, sel, fn) => { handlers[evt + "|" + sel] = fn; } };
    win.EMSReady = { once: (_key, fn) => fn() };
    win.EMSCore = {
        fetchJSON(url) {
            fetched.push(url);
            return Promise.resolve(queue.shift() || { ok: true });
        },
    };
    const state = { rows: [], task: { id: "t" }, rowsSeq: 1, loading: false, teachers: [] };
    win.EMSWorkloadDist = {
        state,
        q,
        root: () => q("[data-wl-root]"),
        filters: () => ({
            chair: "c1",
            year: "2026/2027",
            season: (q("[data-wl-season]") || {}).value || "",
            q: (q("[data-wl-search]") || {}).value || "",
        }),
        labels: () => ({}),
        loadRows: (arg) => loadCalls.push(JSON.stringify(arg)),
    };
    win.eval(RENDER);
    win.eval(LIST);
    const change = (selector, value) => {
        const field = q(selector);
        field.value = value;
        handlers["change|" + selector](new win.Event("change"), field);
    };
    const query = () => new URL(win.location.href).searchParams;
    return { win, q, handlers, fetched, loadCalls, state, change, query };
}

const FRESH = '{"fresh":true,"panel":false}';
const empty = { total: 0, next_offset: 0, has_more: false };

test("«Vəziyyət» və «Fəaliyyət»: URL-ə yazılır, siyahı sıfırdan yüklənir, sorğuya düşür", () => {
    const ctx = setup();
    ctx.change("[data-wl-status]", "vacant");
    assert.equal(ctx.query().get("wl_status"), "vacant");
    assert.equal(ctx.loadCalls.pop(), FRESH);
    ctx.change("[data-wl-activity]", "lecture");
    assert.equal(ctx.query().get("wl_activity"), "lecture");
    assert.equal(ctx.win.EMSWorkloadList.status(), "vacant");
    assert.equal(ctx.win.EMSWorkloadList.activity(), "lecture");
    const params = new URL(ctx.win.EMSWorkloadList.url("/r/", { chair: "c1", year: "y" }, {}), "http://x").searchParams;
    assert.equal(params.get("status"), "vacant");
    assert.equal(params.get("activity"), "lecture");
    assert.equal(params.has("teacher"), false);
    ctx.change("[data-wl-status]", "");
    assert.equal(ctx.query().has("wl_status"), false);
    assert.doesNotMatch(ctx.win.EMSWorkloadList.url("/r/", {}, {}), /status=/);
});

test("eyni dəyər təkrar seçiləndə sorğu getmir", () => {
    const ctx = setup();
    ctx.change("[data-wl-status]", "full");
    ctx.loadCalls.length = 0;
    ctx.change("[data-wl-status]", "full");
    assert.equal(ctx.loadCalls.length, 0);
});

test("URL-dən bərpa: üç süzgəc qayıdır, seçicilər onu göstərir; pozuq dəyər atılır", () => {
    const ctx = setup({ query: "&wl_teacher=7&wl_status=full&wl_activity=" + encodeURIComponent("a b") });
    ctx.win.EMSWorkloadList.restore();
    assert.equal(ctx.win.EMSWorkloadList.teacher(), "7");
    assert.equal(ctx.win.EMSWorkloadList.status(), "full");
    assert.equal(ctx.win.EMSWorkloadList.activity(), "");
    ctx.state.rows = [{ id: "a" }];
    ctx.win.EMSWorkloadList.afterLoad({ total: 1, next_offset: 1, has_more: false });
    assert.equal(ctx.q("[data-wl-status]").value, "full");
    assert.equal(ctx.q("[data-wl-teacher-select]").value, "7", "siyahıda olmayan müəllim seçici üçün əlavə olunur");
    assert.equal(ctx.q("[data-wl-reset-filters]").hidden, false);
});

test("«Müəllim» seçicisi: sağ panel + kafedra hovuzu (təkrarsız); seçim və kart eyni süzgəcdir", async () => {
    const ctx = setup({ responses: [{ ok: true, results: [{ id: 7, full_name: "Ana (hovuz)" }, { id: 9, full_name: "Zoya" }] }] });
    ctx.state.teachers = CARDS;
    ctx.win.EMSWorkloadRender.teachers(ctx.q("[data-wl-teacher-panel]"), CARDS, {});
    ctx.win.EMSWorkloadList.afterLoad(Object.assign({ teachers: CARDS }, empty));
    await tick();
    await tick();
    assert.equal(ctx.fetched[0], "/t/?chair=c1&year=2026%2F2027");
    const options = Array.from(ctx.q("[data-wl-teacher-select]").options).map((o) => o.value + "|" + o.textContent);
    assert.equal(options.join(";"), "|Hamısı;7|Ana · 100s;vacant|Vakant · 30s;8|Bob · 10s;9|Zoya");

    ctx.change("[data-wl-teacher-select]", "9");
    assert.equal(ctx.win.EMSWorkloadList.teacher(), "9");
    assert.equal(ctx.query().get("wl_teacher"), "9");
    assert.equal(ctx.loadCalls.pop(), FRESH);

    const card = () => ctx.win.document.querySelector('[data-wl-teacher-id="7"]');
    ctx.handlers["click|[data-wl-teacher-id]"]({}, card());
    assert.equal(ctx.q("[data-wl-teacher-select]").value, "7");
    ctx.handlers["click|[data-wl-teacher-id]"]({}, card());
    assert.equal(ctx.q("[data-wl-teacher-select]").value, "");
});

test("kafedra hovuzu eyni kafedra/il üçün yalnız bir dəfə soruşulur", async () => {
    const ctx = setup({ responses: [{ ok: true, results: [] }] });
    const payload = Object.assign({ teachers: [] }, empty);
    ctx.win.EMSWorkloadList.afterLoad(payload);
    ctx.win.EMSWorkloadList.afterLoad(payload);
    await tick();
    assert.equal(ctx.fetched.length, 1);
});

test("«Filtrləri sıfırla»: üç süzgəc, semestr və axtarış təmizlənir; düymə yalnız süzgəc varkən görünür", () => {
    const ctx = setup({ query: "&wl_teacher=7&wl_status=full&wl_activity=lecture" });
    ctx.win.EMSWorkloadList.restore();
    ctx.q("[data-wl-season]").value = "fall";
    ctx.q("[data-wl-search]").value = "kimya";
    ctx.state.rows = [{ id: "a" }];
    ctx.win.EMSWorkloadList.afterLoad({ total: 1, next_offset: 1, has_more: false });
    assert.equal(ctx.q("[data-wl-reset-filters]").hidden, false);

    ctx.handlers["click|[data-wl-reset-filters]"]({}, null);
    ["wl_teacher", "wl_status", "wl_activity"].forEach((key) => assert.equal(ctx.query().has(key), false, key));
    assert.equal(ctx.query().get("chair"), "c1", "digər parametrlər qalır");
    assert.equal(ctx.q("[data-wl-season]").value, "");
    assert.equal(ctx.q("[data-wl-search]").value, "");
    assert.equal(ctx.q("[data-wl-status]").value, "");
    assert.equal(ctx.win.EMSWorkloadList.teacher() + ctx.win.EMSWorkloadList.status() + ctx.win.EMSWorkloadList.activity(), "");
    assert.equal(ctx.loadCalls.pop(), FRESH);

    ctx.win.EMSWorkloadList.afterLoad({ total: 1, next_offset: 1, has_more: false });
    assert.equal(ctx.q("[data-wl-reset-filters]").hidden, true);
});

test("yalnız vəziyyət süzgəci olan boş nəticə «uyğun sətir yoxdur» göstərir", () => {
    const ctx = setup();
    ctx.change("[data-wl-status]", "hourly");
    ctx.win.EMSWorkloadList.afterLoad(empty);
    assert.equal(ctx.q("[data-wl-nomatch]").hidden, false);
    assert.equal(ctx.q("[data-wl-empty]").hidden, true);

    const plain = setup();
    plain.win.EMSWorkloadList.afterLoad(empty);
    assert.equal(plain.q("[data-wl-nomatch]").hidden, true);
    assert.equal(plain.q("[data-wl-empty]").hidden, false);
});
