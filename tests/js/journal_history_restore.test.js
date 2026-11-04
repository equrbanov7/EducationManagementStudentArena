/* «Bu müəllimə bərpa et» (sahib 2026-11-04): /jurnal/ tam səhifəsində düymə ölü idi.

   Səbəb: registrar/js/journal_history_restore.js `{% block content %}` içində, js/core/http.js-dən (EMSCore)
   ƏVVƏL icra olunur və köhnə kod `!window.EMSCore` görüb heç nə bağlamırdı. Bu test real yükləmə sırasını
   (ems_early → partial skripti → ems_ajax_init → csrf/http) göndərilən fayllarla təkrarlayır. */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM, VirtualConsole } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const EARLY = read("static/js/ems_early.js");
const INIT = read("static/js/ems_ajax_init.js");
const CSRF = read("static/js/core/csrf.js");
const HTTP = read("static/js/core/http.js");
const RESTORE = read("apps/registrar/static/registrar/js/journal_history_restore.js");

const ROW = `
<div class="jl-page"><section data-profile-section-panel="my-journal"><table><tr data-jl-href="/jurnal/x/"><td>
  <div class="jl-hrestore jl-hrestore--ready">
    <button type="button" class="jl-restore-btn" data-jl-hrestore-open data-url="/ders-yuku/tarixce/abc/muellime-berpa/"
            data-teacher-id="42" data-teacher="Çiçək Seminarçı" data-subject="Alqoritmlər" data-group="HT-236"
            data-written-since="0"><i class="fas fa-rotate-left"></i>Bu müəllimə bərpa et</button>
    <ul data-jl-hrestore-steps hidden><li>Seminar yükü: Vahab → Çiçək (30 saat)</li></ul>
    <ul data-jl-hrestore-warnings hidden></ul>
  </div>
</td></tr></table>
<div class="jl-hr-modal" data-jl-hrestore-modal hidden data-generic-error="Əməliyyat alınmadı">
  <div data-jl-hrestore-close></div>
  <div role="dialog" aria-modal="true">
    <b data-jl-hrestore-teacher></b><span data-jl-hrestore-subject></span><span data-jl-hrestore-group></span>
    <ul data-jl-hrestore-plan></ul>
    <div data-jl-hrestore-warnbox hidden><ul data-jl-hrestore-warnlist></ul></div>
    <small data-jl-hrestore-required></small><small data-jl-hrestore-optional hidden></small>
    <textarea data-jl-hrestore-reason></textarea>
    <p data-jl-hrestore-error hidden></p>
    <button type="button" data-jl-hrestore-close>Ləğv et</button>
    <button type="button" data-jl-hrestore-submit>Bərpa et</button>
  </div>
</div></section></div>`;

async function fullPage(respond) {
    const calls = { fetch: [], toasts: [], reloads: 0 };
    // jsdom has no navigation: `location.reload()` surfaces as a «not implemented» jsdomError — count those.
    const virtualConsole = new VirtualConsole();
    virtualConsole.on("jsdomError", (error) => {
        if (/navigation/i.test(String(error && error.message))) calls.reloads += 1;
    });
    const dom = new JSDOM("<!doctype html><html><head></head><body>" + ROW + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/jurnal/?teaching=history",
        virtualConsole,
    });
    const w = dom.window;
    w.eval(EARLY); // <head>
    w.eval(RESTORE); // content block — EMSCore is NOT defined yet (the bug)
    assert.equal(w.EMSCore, undefined, "fixture must reproduce the real order: EMSCore comes later");
    w.eval(CSRF);
    w.eval(HTTP);
    w.eval(INIT); // body end — drains the early queue
    w.fetch = (url, opts) => {
        calls.fetch.push({ url, opts });
        return Promise.resolve(respond(url, opts));
    };
    w.EMSToast = { show: (text, level) => calls.toasts.push([level, text]) };
    w.setTimeout = (fn) => {
        fn();
        return 0;
    };
    return { w, calls };
}

function jsonResponse(status, body) {
    const text = typeof body === "string" ? body : JSON.stringify(body);
    return { ok: status >= 200 && status < 300, status, text: () => Promise.resolve(text) };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

test("full-page /jurnal/: the button opens the confirm modal although EMSCore loads after the partial", async () => {
    const { w } = await fullPage(() => jsonResponse(200, { ok: true }));
    const doc = w.document;
    doc.querySelector("[data-jl-hrestore-open] i").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    const modal = doc.querySelector("[data-jl-hrestore-modal]");
    assert.equal(modal.hidden, false, "modal must open");
    assert.equal(modal.parentNode, doc.body, "modal is lifted to <body> so shell containers cannot clip it");
    assert.equal(doc.querySelector("[data-jl-hrestore-teacher]").textContent, "Çiçək Seminarçı");
    assert.match(doc.querySelector("[data-jl-hrestore-plan]").textContent, /Vahab → Çiçək/);
    doc.querySelector("[data-jl-hrestore-close]").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    assert.equal(modal.hidden, true);
});

test("submit posts JSON with the teacher, shows a success toast and reloads", async () => {
    const { w, calls } = await fullPage(() =>
        jsonResponse(200, { ok: true, status: "restored", message: "Jurnal bərpa edildi." })
    );
    const doc = w.document;
    doc.querySelector("[data-jl-hrestore-open]").click();
    doc.querySelector("[data-jl-hrestore-reason]").value = "Səhvən başqasına verilmişdi";
    doc.querySelector("[data-jl-hrestore-submit]").click();
    await flush();
    assert.equal(calls.fetch.length, 1);
    const { url, opts } = calls.fetch[0];
    assert.equal(url, "/ders-yuku/tarixce/abc/muellime-berpa/");
    assert.equal(opts.method, "POST");
    assert.deepEqual(JSON.parse(opts.body), { reason: "Səhvən başqasına verilmişdi", teacher: "42" });
    assert.equal(opts.headers["X-Requested-With"], "XMLHttpRequest");
    assert.deepEqual(calls.toasts, [["success", "Jurnal bərpa edildi."]]);
    assert.equal(calls.reloads, 1);
});

test("server refusal is shown in the modal and as an error toast; an HTML error page never leaks", async () => {
    let reply = jsonResponse(409, { ok: false, error: "x", message: "Jurnal bağlanıb — əvvəlcə jurnalı açın." });
    const { w, calls } = await fullPage(() => reply);
    const doc = w.document;
    doc.querySelector("[data-jl-hrestore-open]").click();
    doc.querySelector("[data-jl-hrestore-submit]").click();
    await flush();
    const error = doc.querySelector("[data-jl-hrestore-error]");
    assert.equal(error.hidden, false);
    assert.equal(error.textContent, "Jurnal bağlanıb — əvvəlcə jurnalı açın.");
    assert.deepEqual(calls.toasts, [["danger", "Jurnal bağlanıb — əvvəlcə jurnalı açın."]]);
    assert.equal(doc.querySelector("[data-jl-hrestore-submit]").disabled, false, "operator can retry");
    assert.equal(calls.reloads, 0);

    reply = jsonResponse(500, "<!doctype html><html><body><h1>Server Error</h1></body></html>");
    doc.querySelector("[data-jl-hrestore-submit]").click();
    await flush();
    assert.equal(error.textContent, "Əməliyyat alınmadı");
    assert.equal(calls.reloads, 0);
});
