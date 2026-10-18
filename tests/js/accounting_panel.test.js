/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-19: «Mühasibatlıq» — apps/accounts/static/accounts/js/profile/accounting.js ƏSL DOM-da (jsdom).
   Sətrə klik müəllim pəncərəsini açıb JSON-la doldurur (başlıq textContent ilə), xəta mesajı statusa görədir,
   «Daha çox» sətirləri əlavə edir, tarix aralığı yalnız tam + hüdudda + «başlanğıc ≤ son» olanda tətbiq olunur,
   «Ay» aralıqdan çıxanda gizli tarixlər boşalır. ems_ajax_init.js (EMSDelegate / EMSReady) əsl fayldır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const INIT = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/profile/accounting.js"), "utf8");

const HTML =
    '<div data-ac-root>' +
    '<form data-ems-filters>' +
    '<input type="hidden" name="ac_from" value="2026-10-01" data-ems-filter data-ac-range-applied="from">' +
    '<input type="hidden" name="ac_to" value="2026-10-31" data-ems-filter data-ac-range-applied="to">' +
    '<select name="ac_semester"><option value="a" selected>A</option><option value="b">B</option></select>' +
    '<select name="ac_month"><option value="2026-10">Okt</option><option value="range" selected>Aralıq</option></select>' +
    '<input type="date" data-ac-range-input="from" value="2026-10-01" min="2026-09-15" max="2027-01-31">' +
    '<input type="date" data-ac-range-input="to" value="2026-10-31" min="2026-09-15" max="2027-01-31">' +
    '<p data-ac-range-error hidden data-msg-order="order-msg" data-msg-bounds="bounds-msg"></p>' +
    "</form>" +
    "<table><tbody>" +
    '<tr data-ac-row data-ac-detail-url="/d/5/"><th><a href="/p?ac_teacher=5" data-ac-open data-ac-detail-url="/d/5/">Ad</a></th><td id="cell">1</td></tr>' +
    "</tbody></table>" +
    '<div class="ems-overlay" id="ac-teacher-dialog" hidden data-ac-dialog data-ac-loading="load" data-ac-error="err" ' +
    'data-ac-not-found="nf" data-ac-forbidden="fb"><div role="dialog">' +
    "<h2 data-ac-dialog-title></h2><p data-ac-dialog-sub></p><div data-ac-dialog-body></div><div data-ac-dialog-foot><button data-ems-overlay-close>Bağla</button></div>" +
    "</div></div></div>";

function load(responses) {
    const dom = new JSDOM("<!doctype html><html><body>" + HTML + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/accounts/profile/?section=accounting",
    });
    const w = dom.window;
    w.eval(INIT);
    const calls = { fetch: [], applied: 0, opened: 0 };
    w.EMSOverlay = {
        open(el) {
            calls.opened += 1;
            el.hidden = false;
            return el;
        },
        close() {},
    };
    w.EMSCore = {
        fetchJSON(url) {
            calls.fetch.push(url);
            const next = responses.shift();
            return next && next.reject ? Promise.reject(next.reject) : Promise.resolve(next);
        },
    };
    w.EMSFilterBar = {
        apply() {
            calls.applied += 1;
        },
    };
    w.eval(SCRIPT);
    return { w, calls };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test("row click opens the dialog and fills it from JSON (title as text)", async () => {
    const { w, calls } = load([
        {
            ok: true,
            title: "<b>Quliyeva</b>",
            subtitle: "Kafedra · Dövr",
            html: '<div data-ac-modal><table><tbody data-ac-lessons-body><tr><th>1</th></tr></tbody></table>' +
                '<div class="ac-more"><button type="button" data-ac-more="/d/5/?ac_part=lessons"><span data-ac-more-label>Daha çox · 9 qalıb</span></button></div></div>',
            foot: '<a href="/x">X</a>',
        },
        { ok: true, rows: "<tr><th>2</th></tr><tr><th>3</th></tr>", more_url: "", remaining: 0 },
    ]);
    const doc = w.document;
    doc.getElementById("cell").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    await tick();
    const dialog = doc.getElementById("ac-teacher-dialog");
    assert.equal(dialog.hidden, false);
    assert.deepEqual(calls.fetch, ["/d/5/"]);
    assert.equal(doc.querySelector("[data-ac-dialog-title]").textContent, "<b>Quliyeva</b>");
    assert.equal(doc.querySelector("[data-ac-dialog-title] b"), null);
    assert.equal(doc.querySelector("[data-ac-dialog-sub]").textContent, "Kafedra · Dövr");
    assert.ok(doc.querySelector("[data-ac-dialog-foot] a"));

    doc.querySelector("[data-ac-more]").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    await tick();
    assert.equal(doc.querySelectorAll("[data-ac-lessons-body] tr").length, 3);
    assert.equal(doc.querySelector(".ac-more"), null);
    assert.equal(doc.activeElement.textContent, "2");
    w.close();
});

test("name link click is intercepted; modifier click stays a normal link", async () => {
    const { w, calls } = load([{ ok: true, title: "A", html: "<p>x</p>" }]);
    const link = w.document.querySelector("[data-ac-open]");
    const plain = new w.MouseEvent("click", { bubbles: true, cancelable: true });
    link.dispatchEvent(plain);
    assert.equal(plain.defaultPrevented, true);
    const meta = new w.MouseEvent("click", { bubbles: true, cancelable: true, metaKey: true });
    link.dispatchEvent(meta);
    assert.equal(meta.defaultPrevented, false);
    assert.equal(calls.opened, 1);
    w.close();
});

test("error status maps to the matching message", async () => {
    const { w } = load([{ reject: { status: 404 } }]);
    w.EMSAccounting.openTeacher("/d/9/");
    await tick();
    await tick();
    const body = w.document.querySelector("[data-ac-dialog-body]");
    assert.equal(body.textContent.trim(), "nf");
    assert.equal(body.querySelector("[role=alert]") !== null, true);
    w.close();
});

test("range validation: incomplete, bounds, order and a valid commit", () => {
    const { w, calls } = load([]);
    const v = w.EMSAccounting.validateRange;
    assert.equal(v("", "2026-10-01", "2026-09-15", "2027-01-31").code, "incomplete");
    assert.equal(v("0002-10-01", "2026-10-01", "2026-09-15", "2027-01-31").code, "bounds");
    assert.equal(v("2026-10-20", "2026-10-01", "2026-09-15", "2027-01-31").code, "order");
    assert.equal(v("2026-10-01", "2026-10-20", "2026-09-15", "2027-01-31").ok, true);

    const doc = w.document;
    const form = doc.querySelector("form");
    const from = doc.querySelector('[data-ac-range-input="from"]');
    const to = doc.querySelector('[data-ac-range-input="to"]');
    from.value = "2026-10-25";
    to.value = "2026-10-05";
    assert.equal(w.EMSAccounting.commitRange(form), false);
    const error = doc.querySelector("[data-ac-range-error]");
    assert.equal(error.hidden, false);
    assert.equal(error.textContent, "order-msg");
    assert.equal(from.getAttribute("aria-invalid"), "true");

    to.value = "2026-11-05";
    assert.equal(w.EMSAccounting.commitRange(form), true);
    assert.equal(doc.querySelector('[name="ac_from"]').value, "2026-10-25");
    assert.equal(doc.querySelector('[name="ac_to"]').value, "2026-11-05");
    assert.equal(error.hidden, true);
    assert.equal(calls.applied, 1);
    assert.equal(w.EMSAccounting.commitRange(form), false); // dəyişiklik yoxdur — təkrar yükləmə yox
    w.close();
});

test("Enter in a date field commits without submitting the form", () => {
    const { w, calls } = load([]);
    const doc = w.document;
    doc.querySelector('[data-ac-range-input="to"]').value = "2026-10-15";
    const key = new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    doc.querySelector('[data-ac-range-input="to"]').dispatchEvent(key);
    assert.equal(key.defaultPrevented, true);
    assert.equal(calls.applied, 1);
    assert.equal(doc.querySelector('[name="ac_to"]').value, "2026-10-15");
    w.close();
});

test("leaving range mode clears the applied dates before the filter bar reads them", () => {
    const { w } = load([]);
    const doc = w.document;
    const select = doc.querySelector('select[name="ac_month"]');
    let seen = null;
    doc.addEventListener("change", () => {
        seen = doc.querySelector('[name="ac_from"]').value;
    });
    select.value = "2026-10";
    select.dispatchEvent(new w.Event("change", { bubbles: true }));
    assert.equal(seen, "");
    assert.equal(doc.querySelector('[name="ac_to"]').value, "");
    w.close();
});

test("next teacher and errors reset the footer (no stale export button)", async () => {
    const { w } = load([
        { ok: true, title: "A", html: "<p>a</p>", foot: '<a class="exp" href="/export?ac_teacher=5">X</a>' },
        new Promise(() => {}), // ikinci müəllim hələ yüklənir
    ]);
    const doc = w.document;
    const foot = doc.querySelector("[data-ac-dialog-foot]");
    w.EMSAccounting.openTeacher("/d/5/");
    await tick();
    assert.ok(foot.querySelector("a.exp"));
    w.EMSAccounting.openTeacher("/d/6/");
    assert.equal(foot.querySelector("a.exp"), null);
    assert.ok(foot.querySelector("[data-ems-overlay-close]"));
    w.close();
});

test("an error after a loaded teacher also resets the footer", async () => {
    const { w } = load([
        { ok: true, title: "A", html: "<p>a</p>", foot: '<a class="exp" href="/x">X</a>' },
        { reject: { status: 403 } },
    ]);
    const doc = w.document;
    const foot = doc.querySelector("[data-ac-dialog-foot]");
    w.EMSAccounting.openTeacher("/d/5/");
    await tick();
    // Yükləmə gedərkən altlığı kimsə dəyişsə belə (məs. köhnə cavab), xəta onu ilkin halına qaytarır.
    foot.innerHTML = '<a class="exp" href="/x">X</a>';
    w.EMSAccounting.openTeacher("/d/7/");
    foot.innerHTML = '<a class="exp" href="/x">X</a>';
    await tick();
    await tick();
    assert.equal(doc.querySelector("[data-ac-dialog-body]").textContent.trim(), "fb");
    assert.equal(foot.querySelector("a.exp"), null);
    assert.ok(foot.querySelector("[data-ems-overlay-close]"));
    w.close();
});

test("changing the semester clears the applied range before the filter bar reads it", () => {
    const { w } = load([]);
    const doc = w.document;
    let seen = null;
    doc.addEventListener("change", () => {
        seen = [doc.querySelector('[name="ac_from"]').value, doc.querySelector('[name="ac_to"]').value];
    });
    const select = doc.querySelector('select[name="ac_semester"]');
    select.value = "b";
    select.dispatchEvent(new w.Event("change", { bubbles: true }));
    assert.deepEqual(seen, ["", ""]);
    assert.equal(doc.querySelector('select[name="ac_month"]').value, "range"); // rejim qalır, tarixlər server defoltu
    w.close();
});
