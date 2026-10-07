/* ═══════════════════════════════════════════════════════════════════════════
   Təhlükəsizlik auditi 2026-10-07: kurs mövzu modalları (self-XSS)
   (apps/courses/static/courses/js/topic_form_modal.js, topic_edit_modal.js)
   ƏSL kodla, jsdom-da.

   Bug: forma xətaları (`{"errors": form.errors}`) `innerHTML` ilə qaçışsız
   yazılırdı. Django choice/validator xətaları istifadəçinin daxil etdiyi
   dəyəri əks etdirə bilər — `<img onerror>` kimi mətn DOM elementinə
   çevrilirdi. İndi xəta mətni `textContent` ilə yazılır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const INIT = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const FORM_JS = fs.readFileSync(path.join(ROOT, "apps/courses/static/courses/js/topic_form_modal.js"), "utf8");
const EDIT_JS = fs.readFileSync(path.join(ROOT, "apps/courses/static/courses/js/topic_edit_modal.js"), "utf8");

const PAYLOAD = '<img src=x onerror="window.__xss=1"> seçim mövcud deyil';

async function makeWindow(body) {
    const dom = new JSDOM("<!doctype html><html><body>" + body + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/courses/1/",
    });
    const { window } = dom;
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    return window;
}

async function flush() {
    for (let i = 0; i < 10; i += 1) await new Promise((resolve) => setImmediate(resolve));
}

function submit(window, form) {
    form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
}

function assertEscaped(window, container) {
    assert.equal(container.classList.contains("d-none"), false, "xəta bloku görünməlidir");
    assert.equal(container.querySelector("img"), null, "xəta mətni HTML kimi təfsir olunmamalıdır");
    assert.equal(window.__xss, undefined);
    const items = [...container.querySelectorAll("li")].map((li) => li.textContent);
    assert.deepEqual(items, [PAYLOAD], "xəta mətni olduğu kimi (mətn kimi) göstərilməlidir");
    assert.equal(container.querySelector("strong").textContent, "Xətalar:");
}

const FORM_HTML =
    '<div id="topicFormModalConfig" hidden data-i18n-adding="Əlavə edilir" data-i18n-error-retry="x"' +
    ' data-i18n-errors-header="Xətalar"></div>' +
    '<div id="topicFormModal"><form id="topicForm" method="post" action="/courses/1/topic/add/">' +
    '<input name="title" value="t"><div id="topicErrors" class="alert d-none"></div>' +
    '<button type="submit"><i class="fas fa-plus"></i> Əlavə et</button></form></div>';

test("add-topic modal renders form errors as text, not HTML", async () => {
    const window = await makeWindow(FORM_HTML);
    try {
        window.fetch = function () {
            return Promise.resolve({
                json: () => Promise.resolve({ success: false, errors: { kind: [PAYLOAD] } }),
            });
        };
        window.eval(INIT);
        window.eval(FORM_JS);
        const form = window.document.getElementById("topicForm");
        const button = form.querySelector("button");
        submit(window, form);
        assert.equal(button.disabled, true);
        assert.equal(button.textContent, " Əlavə edilir");
        await flush();
        assertEscaped(window, window.document.getElementById("topicErrors"));
        assert.equal(button.disabled, false);
        assert.ok(button.querySelector("i.fa-plus"), "düymənin ilkin məzmunu bərpa olunmalıdır");
    } finally {
        window.close();
    }
});

const EDIT_HTML =
    '<div id="topicEditModalConfig" hidden data-i18n-updating="Yenilənir" data-i18n-errors-header="Xətalar"' +
    ' data-i18n-error="Xəta" data-log-modal-not-found="nf" data-log-error="le"></div>' +
    '<div id="topicEditModal"><form id="topicEditForm" method="post">' +
    '<input id="editTopicId" name="id" value="7"><input id="editTopicTitle" name="title" value="t">' +
    '<textarea id="editTopicDescription" name="description"></textarea>' +
    '<div id="topicEditErrors" class="alert d-none"></div>' +
    '<button type="submit">Yadda saxla</button></form></div>';

async function editPage(fetchJSON) {
    const window = await makeWindow(EDIT_HTML);
    window.EMSCore = { fetchJSON };
    window.eval(INIT);
    window.eval(EDIT_JS);
    return window;
}

test("edit-topic modal renders success=false errors as text, not HTML", async () => {
    const window = await editPage(() => Promise.resolve({ success: false, errors: { kind: [PAYLOAD] } }));
    try {
        submit(window, window.document.getElementById("topicEditForm"));
        await flush();
        assertEscaped(window, window.document.getElementById("topicEditErrors"));
    } finally {
        window.close();
    }
});

test("edit-topic modal renders HTTP 400 payload errors as text, not HTML", async () => {
    const window = await editPage(() => {
        const error = new Error("400");
        error.payload = { success: false, errors: { kind: [PAYLOAD] } };
        return Promise.reject(error);
    });
    try {
        submit(window, window.document.getElementById("topicEditForm"));
        await flush();
        assertEscaped(window, window.document.getElementById("topicEditErrors"));
        assert.equal(window.document.querySelector("#topicEditForm button").textContent, "Yadda saxla");
    } finally {
        window.close();
    }
});
