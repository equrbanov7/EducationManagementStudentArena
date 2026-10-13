/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-14: «yadda saxla click etməyi unudulsa da avtomatik yadda saxlanılsın».
   journal_grid_autosave.js ƏSL DOM-da (jsdom), journal_grid.js ilə birgə: debounce, yalnız dəyişən
   xanalar, eyni anda bir sorğu, 5xx-də geri çəkilmə ilə təkrar, 4xx-də dayanma, səhifə bağlananda
   sendBeacon, «Yadda saxla» tam POST-u avtomatik göndərişi ləğv edir, uğurdan sonra qaralama silinir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const JS = (name) => fs.readFileSync(path.join(ROOT, "apps/registrar/static/registrar/js", name), "utf8");
const GRID = JS("journal_grid.js");
const AUTOSAVE = JS("journal_grid_autosave.js");

function cell(lesson, enrollment, att) {
    const opt = (value, label) =>
        '<option value="' + value + '"' + ((att === "absent" ? "qb" : att === "present" ? "ie" : "") === value ? " selected" : "") + ">" + label + "</option>";
    return (
        "<td>" +
        '<input type="hidden" name="att__' + lesson + "__" + enrollment + '" value="' + att + '" data-jd-att data-jd-sem-att>' +
        '<div class="jd2-semselect"><select data-jd-semselect data-lesson="' + lesson + '">' +
        opt("", "—") + opt("qb", "q/b") + opt("ie", "i/e") +
        "</select></div></td>"
    );
}

function page({ draft } = {}) {
    const html =
        '<div class="jd-page" data-offering-id="o1">' +
        '<form method="post" data-jd-draft="grid" data-jd-autosave data-jd-autosave-url="/jurnal/o1/">' +
        '<input type="hidden" name="csrfmiddlewaretoken" value="tok">' +
        '<input type="hidden" name="action" value="save_marks">' +
        "<table><tbody><tr>" + cell("L1", "E1", "") + cell("L1", "E2", "absent") + cell("L1", "E3", "") + "</tr></tbody></table>" +
        '<div class="jd2-savebar"><span data-jd-autosave-status data-msg-saving="saving" data-msg-saved="saved" ' +
        'data-msg-partial="partial {n}" data-msg-retrying="retrying" data-msg-failed="failed"></span>' +
        '<button type="button" data-jd-autosave-retry hidden>retry</button>' +
        '<button type="submit">save</button></div>' +
        '</form><button type="button" data-jd-bulk="present" data-lesson="L1">i/e</button><input id="outside"></div>';
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/jurnal/o1/",
    });
    const { window } = dom;
    if (draft) window.localStorage.setItem("jdDraft:o1", JSON.stringify(draft));

    // İdarə olunan saat: taymerlər yalnız `tick(ms)` ilə işləyir.
    let now = 0;
    let seq = 0;
    const timers = new Map();
    window.setTimeout = (fn, ms) => {
        seq += 1;
        timers.set(seq, { fn, at: now + (ms || 0) });
        return seq;
    };
    window.clearTimeout = (id) => timers.delete(id);
    const tick = (ms) => {
        now += ms;
        for (;;) {
            const due = [...timers.entries()].filter(([, t]) => t.at <= now).sort((a, b) => a[1].at - b[1].at)[0];
            if (!due) break;
            timers.delete(due[0]);
            due[1].fn();
        }
    };

    const calls = [];
    window.EMSCore = {
        fetchJSON: (url, options) =>
            new Promise((resolve, reject) => {
                calls.push({ url, body: options.body, resolve, reject });
            }),
    };
    const beacons = [];
    window.navigator.sendBeacon = (url, body) => {
        beacons.push({ url, body });
        return true;
    };
    const handlers = [];
    window.EMSDelegate = {
        on: (type, selector, fn) => {
            window.document.addEventListener(type, (event) => {
                const match = event.target && event.target.closest && event.target.closest(selector);
                if (match) fn(event, match);
            });
            handlers.push(type);
        },
    };
    window.EMSReady = (fn) => fn();
    window.EMSReady.once = (key, fn) => fn();
    window.gettext = (s) => s;
    window.interpolate = (s) => s;
    window.eval(GRID);
    window.eval(AUTOSAVE);
    const selects = [...window.document.querySelectorAll("[data-jd-semselect]")];
    const choose = (i, value) => {
        selects[i].value = value;
        selects[i].dispatchEvent(new window.Event("change", { bubbles: true }));
    };
    const fields = (call) => Object.fromEntries([...call.body.entries()]);
    const statusText = () => window.document.querySelector("[data-jd-autosave-status]").textContent;
    const settle = () => new Promise((resolve) => setImmediate(resolve));
    return { window, tick, calls, beacons, selects, choose, fields, statusText, settle };
}

test("changes are debounced into ONE request carrying only the changed cells + csrf/action/autosave", async () => {
    const p = page();
    p.choose(0, "ie");
    p.tick(500);
    p.choose(2, "qb");
    p.tick(500);
    assert.equal(p.calls.length, 0, "still inside the 800 ms debounce");
    p.tick(400);
    assert.equal(p.calls.length, 1);
    assert.equal(p.calls[0].url, "/jurnal/o1/");
    assert.deepEqual(p.fields(p.calls[0]), {
        csrfmiddlewaretoken: "tok",
        action: "save_marks",
        autosave: "1",
        att__L1__E1: "present",
        att__L1__E3: "absent",
    });
    assert.equal(p.statusText(), "saving");
});

test("bulk «i/e» fills empty cells and is saved in a single request", () => {
    const p = page();
    p.window.document.querySelector("[data-jd-bulk]").click();
    p.tick(900);
    assert.equal(p.calls.length, 1);
    const sent = p.fields(p.calls[0]);
    assert.equal(sent.att__L1__E1, "present");
    assert.equal(sent.att__L1__E3, "present");
    assert.ok(!("att__L1__E2" in sent), "the existing q/b is untouched and not re-sent");
});

test("one request in flight; a change made meanwhile goes in a second request after the reply", async () => {
    const p = page();
    p.choose(0, "ie");
    p.tick(900);
    assert.equal(p.calls.length, 1);
    p.choose(2, "ie");
    p.tick(900);
    assert.equal(p.calls.length, 1, "no second request while the first is in flight");
    p.calls[0].resolve({ ok: true, sent: 1, written: 1, rejected: 0, skipped: 0 });
    await p.settle();
    p.tick(900);
    assert.equal(p.calls.length, 2);
    assert.deepEqual(Object.keys(p.fields(p.calls[1])).filter((k) => k.startsWith("att__")), ["att__L1__E3"]);
    p.calls[1].resolve({ ok: true, sent: 1, written: 1, rejected: 0, skipped: 0 });
    await p.settle();
    assert.match(p.statusText(), /^saved · \d\d:\d\d$/);
    assert.equal(p.window.localStorage.getItem("jdDraft:o1"), null, "draft cleared after a clean save");
    assert.equal(p.window.EMSJournalGrid.isDirty(), false);
});

test("a server-side skip (lock / lesson day) is reported, not hidden", async () => {
    const p = page();
    p.choose(0, "ie");
    p.tick(900);
    p.calls[0].resolve({ ok: true, sent: 1, written: 0, rejected: 0, skipped: 1 });
    await p.settle();
    assert.equal(p.statusText(), "partial 1");
});

test("network / 5xx errors retry with backoff; the retry button forces an immediate attempt", async () => {
    const p = page();
    p.choose(0, "ie");
    p.tick(900);
    p.calls[0].reject(Object.assign(new Error("HTTP 502"), { status: 502 }));
    await p.settle();
    assert.equal(p.statusText(), "retrying");
    assert.equal(p.window.document.querySelector("[data-jd-autosave-retry]").hidden, false);
    p.tick(1500);
    assert.equal(p.calls.length, 1, "first retry waits 2 s");
    p.tick(600);
    assert.equal(p.calls.length, 2);
    p.calls[1].reject(new TypeError("Failed to fetch"));
    await p.settle();
    p.tick(3000);
    assert.equal(p.calls.length, 2, "second retry waits 4 s");
    p.window.document.querySelector("[data-jd-autosave-retry]").click();
    assert.equal(p.calls.length, 3);
    assert.equal(p.fields(p.calls[2]).att__L1__E1, "present");
});

test("a 4xx refusal (closed journal) stops retrying and shows the server message", async () => {
    const p = page();
    p.choose(0, "ie");
    p.tick(900);
    p.calls[0].reject(Object.assign(new Error("HTTP 409"), { status: 409, payload: { ok: false, message: "Jurnal bağlıdır" } }));
    await p.settle();
    assert.equal(p.statusText(), "Jurnal bağlıdır");
    p.choose(2, "ie");
    p.tick(60000);
    assert.equal(p.calls.length, 1, "no automatic retries after a refusal");
    assert.notEqual(p.window.localStorage.getItem("jdDraft:o1"), null, "the draft stays in the browser");
});

test("closing the page sends the pending cells with sendBeacon exactly once", () => {
    const p = page();
    p.choose(0, "qb");
    p.window.dispatchEvent(new p.window.Event("beforeunload"));
    p.window.dispatchEvent(new p.window.Event("pagehide"));
    assert.equal(p.beacons.length, 1);
    const sent = Object.fromEntries([...p.beacons[0].body.entries()]);
    assert.equal(sent.att__L1__E1, "absent");
    assert.equal(sent.autosave, "1");
    assert.equal(sent.csrfmiddlewaretoken, "tok");
    p.tick(900);
    assert.equal(p.calls.length, 0, "the debounced fetch was cancelled");
});

test("leaving the form (blur) flushes immediately", () => {
    const p = page();
    p.choose(0, "ie");
    p.selects[0].dispatchEvent(
        new p.window.FocusEvent("focusout", { bubbles: true, relatedTarget: p.window.document.getElementById("outside") })
    );
    assert.equal(p.calls.length, 1);
});

test("the manual «Yadda saxla» submit cancels the pending autosave", () => {
    const p = page();
    p.choose(0, "ie");
    const form = p.window.document.querySelector("form");
    form.dispatchEvent(new p.window.Event("submit", { bubbles: true, cancelable: true }));
    p.tick(5000);
    assert.equal(p.calls.length, 0);
});

test("a cell restored from the browser draft is saved automatically on load", () => {
    const p = page({ draft: { att__L1__E1: "absent", att__L1__E2: "absent", att__L1__E3: "" } });
    assert.equal(p.selects[0].value, "qb");
    p.tick(900);
    assert.equal(p.calls.length, 1);
    const sent = p.fields(p.calls[0]);
    assert.equal(sent.att__L1__E1, "absent");
    assert.ok(!("att__L1__E2" in sent) && !("att__L1__E3" in sent));
});
