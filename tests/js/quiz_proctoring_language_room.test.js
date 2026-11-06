/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-11-06: quiz + nəzarət — məcburi dil addımı və «Nəzarət otağı», ƏSL kodla (jsdom).

   1) Kabinet modalı (accounts/js/profile/assigned_exam.js): çoxdilli imtahanda dil radio-kartları qurulur,
      seçilmədən «İmtahana başla» heç yerə getmir (xəta vəziyyəti), seçiləndən sonra keçid/kod forması dili daşıyır.
   2) Start səhifəsi (exams/js/exam_language_step.js): dilsiz forma göndərilmir, «Geri» (formnovalidate) keçir.
   3) Nəzarət otağı (exams/js/supervision_room.js): sətirlər snapshot-dan qurulur, «Bərpa et» doğru URL-ə POST edir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const INIT = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const ASSIGNED = fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/profile/assigned_exam.js"), "utf8");
const STEP = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/exam_language_step.js"), "utf8");
const ROOM = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/supervision_room.js"), "utf8");

async function ready(window) {
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
}

function navCatcher() {
    const navigations = [];
    const virtualConsole = new VirtualConsole();
    virtualConsole.on("jsdomError", (error) => {
        if (String(error && error.message).includes("navigation")) navigations.push(error.message);
    });
    return { navigations, virtualConsole };
}

/* ── 1) Kabinet modalı ─────────────────────────────────────────────────── */

const LANGS = JSON.stringify([{ language: "az", label: "Azərbaycan dili" }, { language: "ru", label: "Русский" }]);

function cabinet({ requiresCode }) {
    const { navigations, virtualConsole } = navCatcher();
    const html = `<body>
      <script id="langs-7" type="application/json">${LANGS}</script>
      <button id="trigger" class="js-open-assigned-exam-modal" data-is-final="0"
              data-requires-code="${requiresCode ? "1" : "0"}" data-exam-slug="quiz-7"
              data-start-url="/exams/quiz-7/start/?si=tok" data-language-options-id="langs-7"></button>
      <div id="assignedExamInfoBackdrop" aria-hidden="true"><div class="assigned-exam-info-modal">
        <button id="assignedExamInfoClose"></button>
        <fieldset id="assignedExamLanguageStep" data-language-step hidden>
          <div id="assignedExamLanguageGrid"></div>
          <p data-language-step-error hidden data-default-message="Dil seçin"><span data-language-step-error-text></span></p>
        </fieldset>
        <p id="assignedExamLanguageSingle" hidden><b id="assignedExamLanguageSingleName"></b></p>
        <form id="assignedExamCodeForm" action="/exams/code/" class="is-hidden">
          <input id="assignedExamCodeSlug" name="exam_slug"><input id="assignedExamCodeLanguage" name="language">
          <input id="assignedExamAccessCodeInput" name="access_code"><div id="assignedExamCodeError" hidden></div>
        </form>
        <button id="assignedExamInfoStartBtn"></button><button id="assignedExamInfoCancelBtn"></button>
      </div></div></body>`;
    const dom = new JSDOM(html, { runScripts: "outside-only", url: "https://example.test/accounts/profile/", virtualConsole });
    const w = dom.window;
    const fetches = [];
    w.fetch = (url, opts) => {
        fetches.push({ url, body: opts && opts.body });
        return Promise.resolve({
            ok: true,
            headers: { get: () => "application/json" },
            json: () => Promise.resolve({ success: true, redirect_url: "/exams/quiz-7/attempt/1/" }),
        });
    };
    w.HTMLElement.prototype.scrollIntoView = function () {};
    w.gettext = (text) => text;
    w.EMSProfile = { register: (fn) => fn({ profilePage: true, sectionLinks: [1], sectionPanels: [1] }) };
    w.eval(ASSIGNED);
    return { w, doc: w.document, navigations, fetches };
}

test("cabinet modal: multilingual exam shows a required language step; start is blocked until a choice", () => {
    const { w, doc, navigations } = cabinet({ requiresCode: false });
    try {
        doc.getElementById("trigger").click();
        const step = doc.getElementById("assignedExamLanguageStep");
        assert.equal(step.hidden, false);
        const radios = step.querySelectorAll("input[type=radio]");
        assert.deepEqual(Array.from(radios, (r) => r.value), ["az", "ru"]);
        assert.equal(Array.from(radios).some((r) => r.checked), false, "nothing pre-selected");

        doc.getElementById("assignedExamInfoStartBtn").click();
        assert.equal(navigations.length, 0, "no navigation without a language");
        assert.ok(step.classList.contains("is-invalid"));
        assert.equal(step.querySelector("[data-language-step-error]").hidden, false);

        radios[1].checked = true;
        radios[1].dispatchEvent(new w.Event("change", { bubbles: true }));
        assert.equal(step.classList.contains("is-invalid"), false);
        assert.equal(doc.getElementById("assignedExamCodeLanguage").value, "ru");
        doc.getElementById("assignedExamInfoStartBtn").click();
        assert.equal(navigations.length, 1);
    } finally { w.close(); }
});

test("cabinet modal: access-code exam sends the chosen language with the code", async () => {
    const { w, doc, fetches } = cabinet({ requiresCode: true });
    try {
        doc.getElementById("trigger").click();
        doc.getElementById("assignedExamAccessCodeInput").value = "123456";
        doc.getElementById("assignedExamInfoStartBtn").click();
        assert.equal(fetches.length, 0, "code is not sent before a language is chosen");

        const radio = doc.querySelector('#assignedExamLanguageGrid input[value="az"]');
        radio.checked = true;
        radio.dispatchEvent(new w.Event("change", { bubbles: true }));
        doc.getElementById("assignedExamInfoStartBtn").click();
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(fetches.length, 1);
        assert.equal(fetches[0].body.get("language"), "az");
        assert.equal(fetches[0].body.get("access_code"), "123456");
    } finally { w.close(); }
});

/* ── 2) Start səhifəsinin dil addımı ──────────────────────────────────── */

async function startPage() {
    const html = `<form data-language-step-form action="/exams/q/start/" method="post">
        <fieldset data-language-step>
          <input type="radio" name="language" value="az"><input type="radio" name="language" value="ru">
          <p data-language-step-error hidden data-default-message="Dil seçin"><span data-language-step-error-text></span></p>
        </fieldset>
        <button type="submit" id="go">Başla</button>
        <button type="submit" id="back" formnovalidate>Geri</button>
      </form>`;
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/q/start/",
    });
    const w = dom.window;
    await ready(w);
    w.HTMLElement.prototype.scrollIntoView = function () {};
    w.eval(INIT);
    w.eval(STEP);
    return { w, doc: w.document };
}

function submitWith(w, form, submitter) {
    const event = new w.SubmitEvent("submit", { bubbles: true, cancelable: true, submitter });
    form.dispatchEvent(event);
    return event.defaultPrevented;
}

test("start page: submit without a language is blocked and flagged; back and chosen language pass", async () => {
    const { w, doc } = await startPage();
    try {
        const form = doc.querySelector("form");
        const step = doc.querySelector("[data-language-step]");
        assert.equal(submitWith(w, form, doc.getElementById("go")), true);
        assert.ok(step.classList.contains("is-invalid"));
        assert.equal(step.querySelector("[data-language-step-error-text]").textContent, "Dil seçin");

        assert.equal(submitWith(w, form, doc.getElementById("back")), false, "formnovalidate «Geri» is not blocked");

        const ru = doc.querySelector('input[value="ru"]');
        ru.checked = true;
        ru.dispatchEvent(new w.Event("change", { bubbles: true }));
        assert.equal(step.classList.contains("is-invalid"), false);
        assert.equal(submitWith(w, form, doc.getElementById("go")), false);
    } finally { w.close(); }
});

/* ── 3) Nəzarət otağı ─────────────────────────────────────────────────── */

function row(id, extra) {
    return Object.assign({
        attempt_id: id, name: "Tələbə " + id, username: "st" + id, group: "", state: "active",
        manual_lock: false, violation_count: 0, max_violations: 3, answered: 1, question_total: 5,
        remaining_seconds: 600, started_at: "2026-11-06T09:00:00+00:00", finished_at: null,
        heartbeat: { status: "ok" }, can_resume: false, resume_refusal: "", can_pause: true, flagged: false,
    }, extra || {});
}

async function room(snapshot) {
    const html = `<div id="svr-root" data-snapshot-url="/exams/q/supervision/snapshot/"
          data-attempt-url-template="/exams/q/supervision/attempts/0/"
          data-resume-url-template="/exams/q/supervision/attempts/0/resume/"
          data-pause-url-template="/exams/q/supervision/attempts/0/pause/" data-poll-seconds="5">
        <span data-svr-count="locked"></span><span data-svr-count="in_exam"></span>
        <span id="svr-conn"></span><input id="svr-filter"><select id="svr-state-filter"><option value=""></option>
        <option value="locked">L</option></select>
        <table><tbody id="svr-rows"></tbody></table><div id="svr-empty" hidden></div></div>
      <div id="svr-resume-dialog" hidden><span data-svr-dialog-student></span>
        <label data-svr-extra-wrap><input type="checkbox" id="svr-resume-extra"></label>
        <p data-svr-dialog-error hidden></p><button data-svr-confirm="resume">OK</button></div>
      <script id="svr-initial-snapshot" type="application/json">${JSON.stringify(snapshot)}</script>
      <script id="svr-i18n" type="application/json">{"resume":"Bərpa et","pause":"Dayandır","details":"Bax"}</script>`;
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/q/supervision/",
    });
    const w = dom.window;
    await ready(w);
    const calls = [];
    const opened = [];
    w.EMSCore = {
        fetchJSON: (url, opts) => {
            calls.push({ url, opts: opts || {} });
            return Promise.resolve(snapshot);
        },
    };
    w.EMSOverlay = { open: (id) => opened.push(id), close: () => {} };
    w.setTimeout = () => 0; // poll dövrəsi testdə işləməsin
    w.eval(INIT);
    w.eval(ROOM);
    return { w, doc: w.document, calls, opened };
}

test("supervision room: renders locked first-class rows with «Bərpa et» and posts to the attempt's resume URL", async () => {
    const snapshot = {
        counts: { locked: 1, in_exam: 2 },
        rows: [row(11, { state: "locked", can_resume: true, can_pause: false, violation_count: 3 }), row(12)],
    };
    const { w, doc, calls, opened } = await room(snapshot);
    try {
        assert.equal(doc.querySelectorAll("#svr-rows tr").length, 2);
        assert.equal(doc.querySelector('[data-svr-count="locked"]').textContent, "1");
        const resume = doc.querySelector('#svr-rows [data-svr-action="resume"][data-attempt-id="11"]');
        assert.ok(resume, "locked row has a restore button");
        assert.equal(doc.querySelector('[data-svr-action="resume"][data-attempt-id="12"]'), null);
        assert.ok(doc.querySelector('[data-svr-action="pause"][data-attempt-id="12"]'));

        resume.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
        assert.deepEqual(opened, ["svr-resume-dialog"]);
        doc.getElementById("svr-resume-extra").checked = true;
        doc.querySelector('[data-svr-confirm="resume"]').dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
        const post = calls.find((call) => call.opts.method === "POST");
        assert.equal(post.url, "/exams/q/supervision/attempts/11/resume/");
        assert.equal(post.opts.body.get("grant_extra_chance"), "1");

        doc.getElementById("svr-state-filter").value = "locked";
        doc.getElementById("svr-state-filter").dispatchEvent(new w.Event("change", { bubbles: true }));
        assert.equal(doc.querySelectorAll("#svr-rows tr").length, 1);
    } finally { w.close(); }
});
