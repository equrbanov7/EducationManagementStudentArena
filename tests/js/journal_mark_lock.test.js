/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-25: müəllimin yazdığı q/b, i/e, bal 15 dəqiqə sonra kilidlənir; kilidli xana kliklənəndə
   «… dəyişdirilə bilməz. Dəyişiklik üçün RİM-ə müraciət edib təqdimat yazın.» dialoqu + müraciət keçidi.
   ƏSL göndərilən fayl jsdom-da: journal_mark_lock.js. Yoxlanır: səbəbə görə mətn (time / legacy) formanın
   data-atributundan götürülür; təsdiq → Müraciətlər keçidi; ləğv → keçid yoxdur.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const LOCK_JS = fs.readFileSync(path.join(ROOT, "apps/registrar/static/registrar/js/journal_mark_lock.js"), "utf8");

function page(answer) {
    const html =
        '<form data-jd-marks-form data-jd-lock-url="/profil/?section=applications&new_kind=texniki"' +
        ' data-jd-lock-msg-time="Bu qiymət 15 dəqiqədən çox əvvəl yazılıb" data-jd-lock-msg-legacy="Köçürülüb"' +
        ' data-jd-lock-title="Xana kilidlidir" data-jd-lock-confirm="RİM-ə müraciət yaz" data-jd-lock-cancel="Bağla">' +
        '<table><tbody><tr><td><span id="t" class="jd2-ro jd2-ro--locked" data-jd-lock="time">q/b</span></td>' +
        '<td><span id="l" class="jd2-ro jd2-ro--locked" data-jd-lock="legacy">i/e</span></td></tr></tbody></table>' +
        "</form>";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/jurnal/o1/",
    });
    const { window } = dom;
    const handlers = [];
    window.EMSReady = (fn) => fn();
    window.EMSReady.once = (key, fn) => fn();
    window.EMSDelegate = {
        on(type, selector, fn) {
            handlers.push({ type, selector, fn });
        },
    };
    const calls = [];
    window.EMSConfirm = {
        open(opts) {
            calls.push(opts);
            return Promise.resolve(answer);
        },
    };
    window.eval(LOCK_JS);
    const click = (id) => {
        const el = window.document.getElementById(id);
        handlers
            .filter((h) => h.type === "click" && el.matches(h.selector))
            .forEach((h) => h.fn({ preventDefault() {} }, el));
    };
    return { window, calls, click };
}

test("time-locked cell opens the RİM dialog with the 15-minute text", async () => {
    const { calls, click } = page(false);
    click("t");
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(calls.length, 1);
    assert.equal(calls[0].body, "Bu qiymət 15 dəqiqədən çox əvvəl yazılıb");
    assert.equal(calls[0].title, "Xana kilidlidir");
    assert.equal(calls[0].confirmLabel, "RİM-ə müraciət yaz");
    assert.equal(calls[0].cancelLabel, "Bağla");
});

test("legacy cell shows the migrated-cell text", async () => {
    const { calls, click } = page(false);
    click("l");
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(calls[0].body, "Köçürülüb");
});

test("confirm navigates to the applications deep link", async () => {
    const { window, click } = page(true);
    let target = "";
    window.EMSJournalMarkLock.go = (url) => {
        target = url;
    };
    click("t");
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(target, "/profil/?section=applications&new_kind=texniki");
});

test("cancel does not navigate", async () => {
    const { window, click } = page(false);
    let target = "";
    window.EMSJournalMarkLock.go = (url) => {
        target = url;
    };
    click("t");
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(target, "");
});
