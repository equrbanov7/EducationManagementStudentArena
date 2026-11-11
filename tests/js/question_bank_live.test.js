/*
 * Sual bankı — səhifəni yenidən yükləməyən axın (sahib 2026-11-11: «burada da ləngdir»):
 *   - teacher_questions_bank/live.js: `X-QB-Partial` fraqmenti → `data-qb-live` bölgələri əvəz olunur;
 *   - teacher_questions_bank/guarded_submit.js: uğurda mesajlar toast + fraqment yeniləməsi;
 *     «istifadə olunmuş suallar silinmir — deaktiv edilsin?» təsdiqi (`on_used=deactivate`);
 *   - teacher_exam_results_reset.js: başlıq qutusu + «Bütün N nəticəni seç» (ID yox, süzgəc + say).
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const LIVE = read("apps/exams/static/exams/js/teacher_questions_bank/live.js");
const GUARDED = read("apps/exams/static/exams/js/teacher_questions_bank/guarded_submit.js");
const RESET = read("apps/exams/static/exams/js/teacher_exam_results_reset.js");

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

const BANK_HTML = `
<div class="etp-page eqb-page" data-qm-context="exam">
  <form id="questionSearchForm" action="/exams/x/questions-bank/">
    <input name="q" value=""><select name="status"><option value="all" selected>all</option><option value="active">active</option></select>
  </form>
  <div data-qb-live="kpis"><b id="kpi">731</b></div>
  <div data-qb-live="export"><a class="dropdown-item" id="exportLink" href="/exams/x/questions-bank/?export=report">Excel</a></div>
  <div data-qb-live="quality"><a class="eqb-chip" id="chip" href="/exams/x/questions-bank/?flag=has-dup">Dublikat</a></div>
  <div data-qb-live="list">
    <form id="bulkForm" method="post" action="/exams/x/questions-bank/"><input type="hidden" name="bulk_action" value="delete">
      <article class="qb-card" id="qcard-1">köhnə</article></form>
    <div class="pagination-wrapper"><a class="page-link" id="page2" href="?page=2">2</a></div>
  </div>
  <div data-qb-live="danger"><span id="dangerCount">731</span></div>
</div>`;

const FRAGMENT = `
<div data-qb-live="kpis"><b id="kpi">730</b></div>
<div data-qb-live="export"><a class="dropdown-item" id="exportLink" href="/exams/x/questions-bank/?page=2&export=report">Excel</a></div>
<div data-qb-live="quality"><a class="eqb-chip" id="chip" href="/exams/x/questions-bank/?flag=has-dup">Dublikat</a></div>
<div data-qb-live="list"><form id="bulkForm" method="post"><article class="qb-card" id="qcard-13">yeni</article></form></div>
<div data-qb-live="danger"><span id="dangerCount">730</span></div>`;

function bankPage({ fetchImpl } = {}) {
    const dom = new JSDOM("<!doctype html><html><body>" + BANK_HTML + "</body></html>", {
        virtualConsole: new VirtualConsole(), // jsdom «navigation not implemented» səs-küyü (endirmə linki)
        runScripts: "outside-only",
        url: "http://localhost/exams/x/questions-bank/",
    });
    const { window } = dom;
    const log = { fetches: [], toasts: [], events: 0 };
    window.EMSReady = (fn) => fn();
    window.EMSToast = { show: (text, level) => log.toasts.push([level, text]) };
    window.fetch = (url, options) => {
        log.fetches.push({ url: String(url), headers: (options && options.headers) || {} });
        return fetchImpl
            ? fetchImpl(url, options)
            : Promise.resolve({ ok: true, redirected: false, text: () => Promise.resolve(FRAGMENT) });
    };
    window.eval(LIVE);
    window.document.querySelector(".eqb-page").addEventListener("qb:live:updated", () => { log.events += 1; });
    return { window, log, $: (sel) => window.document.querySelector(sel) };
}

test("live refresh swaps only the live regions, updates the URL and announces the swap", async () => {
    const { window, log, $ } = bankPage();
    assert.equal(window.QBLive.enabled(), true);
    const ok = await window.QBLive.refresh("/exams/x/questions-bank/?page=2", { push: true });
    assert.equal(ok, true);
    assert.equal(log.fetches[0].headers["X-QB-Partial"], "1");
    assert.equal($("#kpi").textContent, "730");
    assert.equal($("#dangerCount").textContent, "730");
    assert.ok($("#qcard-13"));
    assert.equal($("#qcard-1"), null);
    assert.equal(window.location.search, "?page=2");
    assert.equal(log.events, 1);
    assert.ok($("#questionSearchForm"), "the filter form (focus) is never replaced");
    assert.equal($(".eqb-page").classList.contains("eqb-page--busy"), false);
});

test("pagination and quality chips are intercepted; download links are left alone", async () => {
    const { window, log, $ } = bankPage();
    const click = (node) => {
        const event = new window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });
        node.dispatchEvent(event);
        return event.defaultPrevented;
    };
    assert.equal(click($("#exportLink")), false);
    assert.equal(log.fetches.length, 0);
    assert.equal(click($("#chip")), true);
    assert.equal(click($("#page2")), true);
    await flush();
    assert.equal(log.fetches.length, 2);
    assert.match(log.fetches[0].url, /flag=has-dup/);
    assert.match(log.fetches[1].url, /page=2/);
});

test("the filter form becomes a URL without empty / default values", () => {
    const { window, $ } = bankPage();
    const form = $("#questionSearchForm");
    form.querySelector('[name="q"]').value = "  hüceyrə ";
    assert.equal(window.QBLive.urlFromFilterForm(form).search, "?q=h%C3%BCceyr%C9%99");
    form.querySelector('[name="status"]').value = "active";
    assert.match(window.QBLive.urlFromFilterForm(form).search, /status=active/);
});

function guardedPage(responses) {
    const page = bankPage();
    const { window, log } = page;
    log.posts = [];
    log.confirms = [];
    log.refreshes = [];
    window.FormData = window.FormData;
    window.EMSConfirm = {
        open(opts) {
            log.confirms.push(opts);
            return Promise.resolve(true);
        },
    };
    window.EMSCore = {
        fetchJSON(url, options) {
            const fields = {};
            options.body.forEach((value, key) => { fields[key] = value; });
            log.posts.push({ fields, headers: options.headers || {} });
            const next = responses.shift();
            if (next.status && next.status >= 400) {
                const error = new Error("HTTP " + next.status);
                error.payload = next.payload;
                return Promise.reject(error);
            }
            return Promise.resolve(next.payload);
        },
    };
    window.QBLive.refresh = (url, opts) => { log.refreshes.push([String(url), opts]); return Promise.resolve(true); };
    window.eval(GUARDED);
    return page;
}

test("used questions: the server's «deactivate instead?» offer is confirmed and resent with on_used", async () => {
    const { window, log, $ } = guardedPage([
        {
            status: 409,
            payload: {
                ok: false,
                code: "questions_have_answers",
                message: "silinmir",
                fallback_field: "on_used",
                fallback_value: "deactivate",
                confirm: { title: "İstifadə olunmuş suallar silinmir", body: "3 sual … deaktiv edilsin?", confirm_label: "Bəli" },
            },
        },
        { payload: { ok: true, redirect_url: "/exams/x/questions-bank/?page=1", messages: [{ level: "success", text: "2 sual silindi." }] } },
    ]);
    window.QBGuardedSubmit.submit($("#bulkForm"), { bulk_action: "delete" });
    await flush();
    await flush();
    assert.equal(log.confirms.length, 1);
    assert.match(log.confirms[0].body, /deaktiv/);
    assert.equal(log.posts.length, 2);
    assert.equal(log.posts[0].fields.on_used, undefined);
    assert.equal(log.posts[1].fields.on_used, "deactivate");
    assert.equal(log.posts[1].headers["X-QB-Partial"], "1");
    // Uğur: mesaj toast olur, səhifə yenidən yüklənmir — yalnız fraqment.
    assert.deepEqual(log.toasts, [["success", "2 sual silindi."]]);
    assert.equal(log.refreshes.length, 1);
    assert.match(log.refreshes[0][0], /page=1/);
});

const RESULTS_HTML = `
<table><thead><tr><th><input type="checkbox" data-reset-page-all></th></tr></thead><tbody>
  <tr><td><input type="checkbox" class="js-reset-checkbox" value="11"></td></tr>
  <tr><td><input type="checkbox" class="js-reset-checkbox" value="12"></td></tr>
</tbody></table>
<strong data-reset-selected-count>0</strong>
<button type="button" data-reset-all-matching aria-pressed="false" data-total="408" data-filter-query="status=submitted&amp;group=unit%3Aabc">Bütün 408 nəticəni seç</button>
<button type="button" data-reset-selected disabled>Seçilmişlərin nəticəsini sil</button>
<div id="resetAttemptsModal"><form data-reset-form><div data-reset-inputs></div>
  <p data-reset-one></p><strong data-reset-name></strong><p data-reset-many hidden></p><strong data-reset-count></strong>
  <p data-reset-all-note hidden>hamısı</p><textarea name="reason"></textarea></form></div>`;

function resultsPage() {
    const dom = new JSDOM("<!doctype html><html><body>" + RESULTS_HTML + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/results/",
    });
    const { window } = dom;
    const handlers = [];
    window.EMSDelegate = { on: (type, selector, fn) => handlers.push({ type, selector, fn }) };
    const ready = (fn) => fn();
    ready.once = (key, fn) => fn();
    window.EMSReady = ready;
    window.bootstrap = { Modal: { getOrCreateInstance: () => ({ show() {} }) } };
    ["click", "change"].forEach((type) => {
        window.document.addEventListener(type, (event) => {
            handlers.filter((h) => h.type === type).forEach((h) => {
                const node = event.target.closest ? event.target.closest(h.selector) : null;
                if (node) h.fn(event, node);
            });
        });
    });
    window.eval(RESET);
    const $ = (sel) => window.document.querySelector(sel);
    const fire = (node, type) => node.dispatchEvent(new window.Event(type, { bubbles: true, cancelable: true }));
    return { window, $, fire };
}

function inputs($) {
    const out = {};
    $("[data-reset-inputs]").querySelectorAll("input").forEach((input) => {
        (out[input.name] = out[input.name] || []).push(input.value);
    });
    return out;
}

test("results: the header checkbox selects the page; the modal posts exactly those ids", () => {
    const { window, $, fire } = resultsPage();
    const header = $("[data-reset-page-all]");
    header.checked = true;
    fire(header, "change");
    assert.equal($("[data-reset-selected-count]").textContent, "2");
    assert.equal($("[data-reset-selected]").disabled, false);
    fire($("[data-reset-selected]"), "click");
    assert.deepEqual(inputs($), { attempt_ids: ["11", "12"] });
    assert.equal($("[data-reset-count]").textContent, "2");
    assert.equal($("[data-reset-all-note]").hidden, true);

    const first = window.document.querySelector(".js-reset-checkbox");
    first.checked = false;
    fire(first, "change");
    assert.equal(header.checked, false);
    assert.equal(header.indeterminate, true);
    assert.equal($("[data-reset-selected-count]").textContent, "1");
});

test("results: «Bütün N nəticəni seç» posts the filter + expected count, never an id list", () => {
    const { window, $, fire } = resultsPage();
    const all = $("[data-reset-all-matching]");
    fire(all, "click");
    assert.equal(all.getAttribute("aria-pressed"), "true");
    assert.equal($("[data-reset-selected-count]").textContent, "408");
    fire($("[data-reset-selected]"), "click");
    assert.deepEqual(inputs($), {
        select_scope: ["all_matching"],
        filter_query: ["status=submitted&group=unit%3Aabc"],
        expected_count: ["408"],
    });
    assert.equal($("[data-reset-count]").textContent, "408");
    assert.equal($("[data-reset-all-note]").hidden, false);

    // Bir sətir əl ilə çıxarılır → «hamısı» rejimi bitir, yalnız işarəlilər göndərilir.
    const first = window.document.querySelector(".js-reset-checkbox");
    first.checked = false;
    fire(first, "change");
    assert.equal(all.getAttribute("aria-pressed"), "false");
    fire($("[data-reset-selected]"), "click");
    assert.deepEqual(inputs($), { attempt_ids: ["12"] });
    assert.equal($("[data-reset-all-note]").hidden, true);
});

/* ── EMSConfirm: zəncirvari təsdiq (birinci dialoq bağlanarkən ikinci sual) ─────────────── */
const CONFIRM = read("static/js/ems_confirm.js");

function confirmPage() {
    const dom = new JSDOM(`<!doctype html><html><body>
      <div class="modal" id="emsConfirmModal"><h5 id="emsConfirmModalTitle"></h5><div id="emsConfirmModalBody"></div>
        <button id="emsConfirmCancelBtn">Ləğv et</button><button id="emsConfirmOkBtn">Təsdiqlə</button></div>
    </body></html>`, { runScripts: "outside-only" });
    const { window } = dom;
    const el = window.document.getElementById("emsConfirmModal");
    const shows = [];
    // Bootstrap davranışının minimal modeli: show() bağlanma animasiyası zamanı UDULUR;
    // hide() `show` sinfini dərhal götürür, `hidden.bs.modal` isə animasiyadan SONRA gəlir.
    const instance = {
        transitioning: false,
        show() {
            if (instance.transitioning) return;
            el.style.display = "block";
            el.classList.add("show");
            shows.push(window.document.getElementById("emsConfirmModalBody").textContent);
        },
        hide() {
            el.classList.remove("show");
            instance.transitioning = true;
        },
        finishHide() {
            instance.transitioning = false;
            el.style.display = "none";
            el.dispatchEvent(new window.Event("hidden.bs.modal"));
        },
    };
    window.bootstrap = { Modal: { getOrCreateInstance: () => instance, getInstance: () => instance } };
    window.eval(CONFIRM);
    return { window, instance, shows, ok: window.document.getElementById("emsConfirmOkBtn") };
}

test("EMSConfirm: a second question asked while the first dialog is still closing is shown, not dropped", async () => {
    const { window, instance, shows, ok } = confirmPage();
    const first = window.EMSConfirm.open({ body: "Seçilmiş 40 sual deaktiv ediləcək?" });
    ok.click(); // «Bəli» → dialoq bağlanmağa başlayır (animasiya)
    assert.equal(await first, true);

    // Server cavabı animasiyadan TEZ gəldi → ikinci sual dərhal soruşulur.
    let secondResult = "pending";
    window.EMSConfirm.open({ body: "İmtahan da deaktiv ediləcək — davam?" }).then((value) => { secondResult = value; });
    await flush();
    assert.equal(secondResult, "pending", "the closing dialog must not cancel the new question");
    assert.equal(shows.length, 1);

    instance.finishHide();
    await flush();
    await flush();
    assert.equal(shows.length, 2);
    assert.match(shows[1], /İmtahan da deaktiv/);
    ok.click();
    await flush();
    assert.equal(secondResult, true);
});

test("EMSConfirm: dismissing the dialog still resolves false", async () => {
    const { window, instance } = confirmPage();
    const answer = window.EMSConfirm.open({ body: "Silinsin?" });
    instance.hide();
    instance.finishHide();
    assert.equal(await answer, false);
});
