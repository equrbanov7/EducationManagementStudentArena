/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-25: «Yük bölgüsü» — sağ paneldəki müəllimə görə süzgəc + tənbəl yükləmə.
   `workload_distribution_render.js` və `workload_distribution_list.js` ƏSL DOM-da (jsdom).

   Müqavilə:
     • müəllim kartı düymədir (`aria-pressed`), «Vakant» kartının açarı `vacant`;
     • karta klik süzgəci qoyur (URL-də `wl_teacher`), təkrar klik / «×» götürür; hər dəyişiklik siyahını
       SIFIRDAN yükləyir (`loadRows({fresh, panel:false})`);
     • səhifə yenilənəndə süzgəc URL-dən qayıdır, pozuq dəyər atılır;
     • sorğu ünvanı limit/offset/teacher daşıyır; mutasiyadan sonra yenidən yükləmə açılmış sətir sayını saxlayır;
     • IntersectionObserver zolağı görəndə növbəti dilim ƏLAVƏ olunur (təkrarsız), yüklənmə zamanı ikinci sorğu
       getmir, köhnə (süzgəc dəyişmiş) cavab atılır, xətada «yenidən cəhd» görünür;
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
  <div class="wl" data-wl-root data-rows-url="/ders-yuku/setirler/" data-teachers-url="/ders-yuku/muellimler/" data-focus-row="">
    <select data-wl-season><option value="">Hamısı</option><option value="fall">Payız</option></select>
    <input type="search" data-wl-search>
    <select data-wl-teacher-select><option value="">Hamısı</option></select>
    <select data-wl-status><option value="">Hamısı</option><option value="vacant">v</option><option value="full">f</option><option value="hourly">h</option></select>
    <select data-wl-activity><option value="">Hamısı</option><option value="lecture">l</option></select>
    <button type="button" data-wl-reset-filters hidden>reset</button>
    <div data-wl-teacher-filter hidden>
      <b data-wl-teacher-filter-name></b>
      <button type="button" data-wl-teacher-clear>x</button>
    </div>
    <p data-wl-count hidden></p>
    <div data-wl-empty hidden></div>
    <div data-wl-nomatch hidden></div>
    <div data-wl-rows></div>
    <div data-wl-more hidden>
      <button type="button" data-wl-load-more>more</button>
      <p data-wl-more-error hidden></p>
    </div>
    <div data-wl-teacher-panel></div>
  </div>
</section></body></html>`;

function row(id, extra) {
    return Object.assign(
        {
            id,
            subject: "Fənn " + id,
            season_label: "Payız",
            total_hours: 45,
            teaching_complete: true,
            activities: {},
            assignments: [],
        },
        extra || {}
    );
}

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
    const observed = [];
    const q = (sel) => win.document.querySelector(sel);
    win.EMSDelegate = { on: (evt, sel, fn) => { handlers[evt + "|" + sel] = fn; } };
    win.EMSReady = { once: (_key, fn) => fn() };
    win.EMSCore = {
        fetchJSON(url) {
            fetched.push(url);
            const next = queue.shift();
            if (next && next.__reject) return Promise.reject(new Error("net"));
            return Promise.resolve(next || { ok: true, rows: [], total: 0, next_offset: 0, has_more: false });
        },
    };
    win.IntersectionObserver = function (cb) {
        this.observe = (node) => observed.push(["observe", node]);
        this.unobserve = (node) => observed.push(["unobserve", node]);
        this.disconnect = () => observed.push(["disconnect"]);
        win.__fire = (intersecting) => cb([{ isIntersecting: intersecting }]);
    };
    const state = { rows: [], task: { id: "t" }, rowsSeq: 1, loading: false, total: 0, nextOffset: 0, hasMore: false };
    win.EMSWorkloadDist = {
        state,
        q: (sel) => q(sel),
        root: () => q("[data-wl-root]"),
        filters: () => ({
            chair: "c1",
            year: "2026/2027",
            season: options.season !== undefined ? options.season : (q("[data-wl-season]") || {}).value || "",
            q: options.search !== undefined ? options.search : (q("[data-wl-search]") || {}).value || "",
        }),
        labels: () => ({}),
        loadRows: (arg) => loadCalls.push(arg),
    };
    win.eval(RENDER);
    win.eval(LIST);
    const change = (selector, value) => {
        const field = q(selector);
        field.value = value;
        handlers["change|" + selector](new win.Event("change"), field);
    };
    return { change, win, q, handlers, fetched, loadCalls, observed, state };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

const CARDS = [
    { teacher_id: 7, name: "Ana", hours: 100, norm_hours: 550, fill_percent: 18 },
    { teacher_id: "", is_vacant: true, name: "Vakant", hours: 30, norm_hours: 0, fill_percent: 0 },
];

test("müəllim kartları düymədir; Vakant açarı `vacant`; aktiv kart aria-pressed=true", () => {
    const ctx = setup();
    ctx.win.EMSWorkloadRender.teachers(ctx.q("[data-wl-teacher-panel]"), CARDS, { active: "vacant" });
    const cards = ctx.win.document.querySelectorAll("button[data-wl-teacher-id]");
    assert.equal(cards.length, 2);
    assert.equal(cards[0].getAttribute("data-wl-teacher-id"), "7");
    assert.equal(cards[0].getAttribute("aria-pressed"), "false");
    assert.equal(cards[1].getAttribute("data-wl-teacher-id"), "vacant");
    assert.equal(cards[1].getAttribute("aria-pressed"), "true");
    assert.ok(cards[1].classList.contains("is-active"));
    assert.equal(cards[0].type, "button");
});

test("sətirlər `append` ilə ardına əlavə olunur, seçilmiş müəllimin çipi vurğulanır", () => {
    const ctx = setup();
    const host = ctx.q("[data-wl-rows]");
    const withChip = (id, teacherId) =>
        row(id, { assignments: [{ id: "a" + id, teacher_id: teacherId, teacher_name: "T", activity_label: "M", hours: 3, is_vacant: teacherId === "" }] });
    ctx.win.EMSWorkloadRender.rows(host, [withChip("r1", "7")], {}, { teacher: "7" });
    ctx.win.EMSWorkloadRender.rows(host, [withChip("r2", "8"), withChip("r3", "")], {}, { append: true, teacher: "7" });
    assert.equal(host.querySelectorAll("[data-wl-row]").length, 3);
    assert.equal(host.querySelectorAll(".wl-assign-chip.is-match").length, 1);
    ctx.win.EMSWorkloadRender.rows(host, [withChip("r3", "")], {}, { teacher: "vacant" });
    assert.equal(host.querySelectorAll(".wl-assign-chip.is-match").length, 1);
});

test("karta klik: süzgəc qoyulur, URL yazılır, siyahı sıfırdan yüklənir; təkrar klik götürür", () => {
    const ctx = setup();
    ctx.win.EMSWorkloadRender.teachers(ctx.q("[data-wl-teacher-panel]"), CARDS, {});
    const card = ctx.win.document.querySelector('[data-wl-teacher-id="7"]');
    const onCard = ctx.handlers["click|[data-wl-teacher-id]"];
    onCard({}, card);
    assert.equal(ctx.win.EMSWorkloadList.teacher(), "7");
    assert.equal(new URL(ctx.win.location.href).searchParams.get("wl_teacher"), "7");
    assert.equal(new URL(ctx.win.location.href).searchParams.get("chair"), "c1", "digər parametrlər qalır");
    assert.equal(JSON.stringify(ctx.loadCalls.pop()), '{"fresh":true,"panel":false}');
    assert.equal(card.getAttribute("aria-pressed"), "true");
    assert.equal(ctx.q("[data-wl-teacher-filter]").hidden, false);
    assert.equal(ctx.q("[data-wl-teacher-filter-name]").textContent, "Ana");

    onCard({}, card);
    assert.equal(ctx.win.EMSWorkloadList.teacher(), "");
    assert.equal(new URL(ctx.win.location.href).searchParams.has("wl_teacher"), false);
    assert.equal(card.getAttribute("aria-pressed"), "false");
    assert.equal(ctx.q("[data-wl-teacher-filter]").hidden, true);
    assert.equal(JSON.stringify(ctx.loadCalls.pop()), '{"fresh":true,"panel":false}');
});

test("«×» süzgəci götürür və yenidən yükləyir; süzgəc yoxdursa heç nə etmir", () => {
    const ctx = setup({ query: "&wl_teacher=7" });
    ctx.win.EMSWorkloadList.restore();
    ctx.handlers["click|[data-wl-teacher-clear]"]({}, null);
    assert.equal(ctx.win.EMSWorkloadList.teacher(), "");
    assert.equal(ctx.loadCalls.length, 1);
    ctx.handlers["click|[data-wl-teacher-clear]"]({}, null);
    assert.equal(ctx.loadCalls.length, 1);
});

test("URL-dən bərpa: düzgün dəyər qayıdır, pozuq dəyər atılır", () => {
    const good = setup({ query: "&wl_teacher=vacant" });
    good.win.EMSWorkloadList.restore();
    assert.equal(good.win.EMSWorkloadList.teacher(), "vacant");
    const bad = setup({ query: "&wl_teacher=" + encodeURIComponent("1;DROP TABLE") });
    bad.win.EMSWorkloadList.restore();
    assert.equal(bad.win.EMSWorkloadList.teacher(), "");
});

test("sorğu ünvanı: limit/offset/teacher/panel; keep açılmış sətir sayını saxlayır", () => {
    const ctx = setup({ query: "&wl_teacher=7" });
    ctx.win.EMSWorkloadList.restore();
    const params = { chair: "c 1", year: "2026/2027", season: "fall", q: "ə b" };
    const first = ctx.win.EMSWorkloadList.url("/r/", params, {});
    assert.match(first, /^\/r\/\?chair=c%201&year=2026%2F2027&season=fall&q=%C9%99%20b&teacher=7&limit=30&offset=0$/);
    assert.match(ctx.win.EMSWorkloadList.url("/r/", params, { keep: 90, panel: false }), /limit=90&offset=0&panel=0$/);
    assert.match(ctx.win.EMSWorkloadList.url("/r/", params, { keep: 5 }), /limit=30&/, "dilimdən kiçik keep → ilk dilim");
    assert.match(ctx.win.EMSWorkloadList.url("/r/", params, { offset: 60, panel: false }), /limit=30&offset=60&panel=0$/);
    ctx.win.EMSWorkloadList.setTeacher("");
    assert.doesNotMatch(ctx.win.EMSWorkloadList.url("/r/", params, {}), /teacher=/);
});

test("fokus sətri yalnız ilk dilimdə və bir dəfə göndərilir", () => {
    const ctx = setup();
    ctx.q("[data-wl-root]").dataset.focusRow = "abc-123";
    assert.match(ctx.win.EMSWorkloadList.url("/r/", {}, {}), /&focus=abc-123$/);
    assert.doesNotMatch(ctx.win.EMSWorkloadList.url("/r/", {}, { offset: 30 }), /focus=/);
    ctx.state.focusedRow = "abc-123";
    assert.doesNotMatch(ctx.win.EMSWorkloadList.url("/r/", {}, {}), /focus=/);
});

test("afterLoad: say, «daha çox» zolağı və boş vəziyyətlər", () => {
    const ctx = setup({ search: "x" });
    ctx.state.rows = [row("a"), row("b")];
    ctx.win.EMSWorkloadList.afterLoad({ total: 5, next_offset: 2, has_more: true });
    assert.equal(ctx.q("[data-wl-count]").textContent, "Göstərilir: 2 / 5 sətir");
    assert.equal(ctx.q("[data-wl-more]").hidden, false);
    assert.ok(ctx.observed.some((entry) => entry[0] === "observe"), "zolaq izlənir");
    assert.equal(ctx.state.nextOffset, 2);

    ctx.state.rows = [];
    ctx.win.EMSWorkloadList.afterLoad({ total: 0, next_offset: 0, has_more: false });
    assert.equal(ctx.q("[data-wl-nomatch]").hidden, false, "axtarış var → uyğun sətir yoxdur");
    assert.equal(ctx.q("[data-wl-empty]").hidden, true);
    assert.equal(ctx.q("[data-wl-more]").hidden, true);
    assert.equal(ctx.q("[data-wl-count]").hidden, true);

    const plain = setup();
    plain.win.EMSWorkloadList.afterLoad({ total: 0, next_offset: 0, has_more: false });
    assert.equal(plain.q("[data-wl-empty]").hidden, false, "süzgəcsiz boş → tapşırıq yoxdur");
    assert.equal(plain.q("[data-wl-nomatch]").hidden, true);
});

test("zolaq görünəndə növbəti dilim ƏLAVƏ olunur; təkrar sətir düşmür; offset serverdən gəlir", async () => {
    const ctx = setup({
        responses: [{ ok: true, rows: [row("b"), row("c")], total: 3, next_offset: 3, has_more: false }],
    });
    ctx.state.rows = [row("a"), row("b")];
    ctx.win.EMSWorkloadRender.rows(ctx.q("[data-wl-rows]"), ctx.state.rows, {});
    ctx.win.EMSWorkloadList.afterLoad({ total: 3, next_offset: 2, has_more: true });
    ctx.win.__fire(true);
    await tick();
    await tick();
    assert.match(ctx.fetched[0], /limit=30&offset=2&panel=0$/);
    assert.deepEqual(Array.from(ctx.state.rows.map((r) => r.id)), ["a", "b", "c"]);
    assert.equal(ctx.win.document.querySelectorAll("[data-wl-row]").length, 3, "'b' ikinci dəfə çəkilmir");
    assert.equal(ctx.q("[data-wl-more]").hidden, true);
    assert.equal(ctx.q("[data-wl-count]").textContent, "Göstərilir: 3 / 3 sətir");
});

test("görünməyən zolaq sorğu açmır; yüklənmə zamanı ikinci sorğu getmir", async () => {
    const ctx = setup({ responses: [{ ok: true, rows: [row("c")], total: 3, next_offset: 3, has_more: false }] });
    ctx.state.rows = [row("a"), row("b")];
    ctx.win.EMSWorkloadList.afterLoad({ total: 3, next_offset: 2, has_more: true });
    ctx.win.__fire(false);
    assert.equal(ctx.fetched.length, 0);
    ctx.state.loading = true; // əsas siyahı yenilənir
    ctx.win.__fire(true);
    assert.equal(ctx.fetched.length, 0);
    ctx.state.loading = false;
    ctx.win.__fire(true);
    ctx.win.__fire(true); // yüklənən zaman təkrar
    await tick();
    await tick();
    assert.equal(ctx.fetched.length, 1);
});

test("süzgəc dəyişəndə (rowsSeq artır) gec gələn köhnə dilim atılır", async () => {
    const ctx = setup({ responses: [{ ok: true, rows: [row("z")], total: 9, next_offset: 3, has_more: true }] });
    ctx.state.rows = [row("a"), row("b")];
    ctx.win.EMSWorkloadList.afterLoad({ total: 9, next_offset: 2, has_more: true });
    ctx.win.__fire(true);
    ctx.state.rowsSeq += 1; // `loadRows` başladı
    await tick();
    await tick();
    assert.deepEqual(Array.from(ctx.state.rows.map((r) => r.id)), ["a", "b"]);
    assert.equal(ctx.win.document.querySelectorAll("[data-wl-row]").length, 0);
});

test("şəbəkə xətası: «yenidən cəhd» görünür, zolaq yenidən izlənmir, düymə ilə təkrar işləyir", async () => {
    const ctx = setup({
        responses: [{ __reject: true }, { ok: true, rows: [row("c")], total: 3, next_offset: 3, has_more: false }],
    });
    ctx.state.rows = [row("a"), row("b")];
    ctx.win.EMSWorkloadList.afterLoad({ total: 3, next_offset: 2, has_more: true });
    ctx.win.__fire(true);
    await tick();
    await tick();
    assert.equal(ctx.q("[data-wl-more-error]").hidden, false);
    assert.equal(ctx.q("[data-wl-more]").hidden, false);
    assert.equal(ctx.state.loadingMore, false);
    assert.equal(ctx.q("[data-wl-load-more]").disabled, false);
    ctx.handlers["click|[data-wl-load-more]"]({}, null);
    await tick();
    await tick();
    assert.deepEqual(Array.from(ctx.state.rows.map((r) => r.id)), ["a", "b", "c"]);
    assert.equal(ctx.q("[data-wl-more-error]").hidden, true);
});

test("təsdiq dialoqu üçün hazırlıq tapşırığın hamısı üzrə ayrıca soruşulur", async () => {
    const ctx = setup({ responses: [{ ok: true, rows: [], readiness: { row_count: 185 } }] });
    const readiness = await ctx.win.EMSWorkloadList.loadReadiness("/r/", { chair: "c1", year: "2026/2027" });
    assert.equal(readiness.row_count, 185);
    assert.equal(ctx.fetched[0], "/r/?chair=c1&year=2026%2F2027&limit=0&readiness=1");
});
