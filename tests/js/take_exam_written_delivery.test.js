/* ═══════════════════════════════════════════════════════════════════════════
   Təhlükəsizlik dizaynı 2026-10-08: vaxtlı YAZILI sualın gövdəsi səhifədə yoxdur —
   question-seen cavabı ilə gəlir (apps/exams/static/exams/js/take_exam/timers.js).

   * inject olunan gövdədə textarea autosave-ə, rəsm kartı EMSPaintAnswer-ə qoşulur,
     mövcud faylların sayı progress üçün yazılır;
   * şəbəkə xətası / 5xx → slide açıq ikən yenidən istənir (offline dayanıqlıq).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");

const BODY = `
<input type="hidden" name="q_present_7" value="1">
<div class="question-content" data-ems-math>
  <button type="button" class="mark-question-btn" data-mark-question data-question-id="7">
    <i class="far fa-bookmark"></i><span data-mark-label>Mark</span>
  </button>
  <div class="q-text">Gizli yazılı sual</div>
  <textarea name="q_7" class="written-answer"></textarea>
  <div class="paint-card" data-qid="7"></div>
  <div id="file-preview-7" class="file-preview-area">
    <div class="file-preview-item"></div><div class="file-preview-item"></div>
  </div>
</div>`;

function load(fetchImpl) {
    const dom = new JSDOM(
        `<!doctype html><html><body>
           <div class="question-slide active" data-question-id="7" data-time-limit="60" data-server-delivery="1">
             <div class="question-content" data-server-delivery-body></div>
           </div>
         </body></html>`,
        { runScripts: "outside-only", url: "http://localhost/exams/x/attempt/1/" }
    );
    const { window } = dom;
    window.EMSTakeExam = {};
    window.fetch = fetchImpl;
    window.eval(read("apps/exams/static/exams/js/take_exam/retry.js"));
    window.eval(read("apps/exams/static/exams/js/take_exam/draft.js"));
    window.eval(read("apps/exams/static/exams/js/take_exam/timers.js"));
    const ns = window.EMSTakeExam;
    const progressCalls = [];
    ns.config = { getCsrfToken: () => "csrf", getSecondsUntil: () => 60 };
    ns.progress = { updateProgress: () => progressCalls.push(1), toggleMarkedQuestion: () => {} };
    const painted = [];
    window.EMSPaintAnswer = { initWithin: (root) => painted.push(root) };
    const slide = window.document.querySelector(".question-slide");
    const ctx = {
        questionSeenUrl: "/exams/x/attempt/1/question-seen/",
        questionTimerSlide: slide,
        markedQuestionIds: new Set(),
        i18n: { mark: "Mark", marked: "Marked" },
        dirtyQuestionIds: new Set(),
        binaryDirtyQuestionIds: new Set(),
    };
    return { window, ns, ctx, slide, painted, progressCalls };
}

const okResponse = (payload) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test("delivered written body is hydrated and wired to autosave, paint and file progress", async () => {
    const env = load(() => okResponse({ success: true, html: BODY, limit_seconds: 60, remaining_seconds: 59 }));
    try {
        await env.ns.timers.syncQuestionTimerWithServer(env.ctx, env.slide);
        assert.equal(env.slide.getAttribute("data-server-delivery"), "hydrated");
        const textarea = env.slide.querySelector("textarea.written-answer");
        assert.equal(textarea.getAttribute("data-answer-bound"), "1");
        assert.deepEqual(env.painted, [env.slide]);
        assert.equal(env.slide.querySelector(".file-preview-area").dataset.existingFileCount, "2");
        assert.ok(env.progressCalls.length >= 1);
    } finally {
        env.window.close();
    }
});

test("a failed delivery is retried while the slide is still open", async () => {
    let calls = 0;
    const env = load(() => {
        calls += 1;
        if (calls === 1) {
            return Promise.reject(new TypeError("Failed to fetch"));
        }
        return okResponse({ success: true, html: BODY, limit_seconds: 60, remaining_seconds: 58 });
    });
    try {
        await env.ns.timers.syncQuestionTimerWithServer(env.ctx, env.slide);
        assert.equal(env.slide.getAttribute("data-server-delivery"), "1", "still a placeholder after the error");
        await sleep(1300);
        assert.equal(calls, 2);
        assert.equal(env.slide.getAttribute("data-server-delivery"), "hydrated");
    } finally {
        env.window.close();
    }
});

test("no retry once the student has moved to another slide", async () => {
    let calls = 0;
    const env = load(() => {
        calls += 1;
        return Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve({}) });
    });
    try {
        await env.ns.timers.syncQuestionTimerWithServer(env.ctx, env.slide);
        env.ctx.questionTimerSlide = null;
        await sleep(1300);
        assert.equal(calls, 1);
    } finally {
        env.window.close();
    }
});
