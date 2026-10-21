/* ═══════════════════════════════════════════════════════════════════════════
   2026-10-21 (sahib hesabatı, zal imtahanı): «Qaralama saxla» / nəzarətçinin «Bərpa et»-indən
   sonra «Bitir» basılanda TƏK tabda «Bu imtahan başqa tabda yenilənib — cavablar bu tabdan
   saxlanılmır» bannerı çıxırdı və heç bir cavab saxlanmırdı.

   Kök səbəb: eyni tabın iki POST-u (fonda gedən autosave + «Qaralama saxla»/«Bitir») eyni
   `autosave_revision` ilə PARALEL gedirdi; server birini yazıb revision-u artırırdı, ikincisi
   isə özünə «başqa tab» 409-u alırdı → tab donurdu.

   ƏSL göndərilən skriptlərlə (config/draft/draft_send/resync/writer/sync_status/retry) və
   serverin OCC qaydasını (apps/exams/views/student/_helpers.py + _autosave_writer.py) təkrarlayan
   saxta serverlə yoxlanılır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (name) => fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/take_exam", name), "utf8");
const SCRIPTS = ["config.js", "sync_status.js", "writer.js", "retry.js", "draft.js", "draft_send.js", "resync.js"];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const QUESTIONS = { 11: ["tA", "tB"], 12: ["tC", "tD"] };

function pageHtml(revision, answers, writerAttrs, center) {
    const slides = Object.keys(QUESTIONS)
        .map((qid) => {
            const opts = QUESTIONS[qid]
                .map(
                    (tok) =>
                        `<input type="radio" name="q_${qid}" value="${tok}" data-question-id="${qid}"${
                            answers[qid] === tok ? " checked" : ""
                        }>`
                )
                .join("");
            return `<div class="question-slide" data-question-id="${qid}"><input type="hidden" name="q_present_${qid}" value="1">${opts}</div>`;
        })
        .join("");
    return `<!doctype html><html><body>
      <form id="exam-form" data-exam-id="5" data-attempt-id="9" data-exam-type="test" data-exam-type-extended="final"
            data-center-exam="${center ? "1" : "0"}" data-autosave-interval-ms="3000" data-answers-state-url="/exams/x/attempt/9/answers-state/">
        <input type="hidden" name="csrfmiddlewaretoken" value="tok">
        <input type="hidden" name="marked_question_ids" id="marked-question-ids-field" value="[]">
        <input type="hidden" name="autosave_revision" id="autosave-revision-field" ${writerAttrs || ""} value="${revision}">
        ${slides}
        <p id="exam-sync-status" hidden></p>
        <button type="button" id="exam-sync-reload" hidden></button>
        <button type="button" id="save-draft-btn">Save draft</button>
      </form></body></html>`;
}

/* Serverin OCC qaydası: base == rev → yaz; base geridədirsə yalnız aradakı bütün yazılar bu writer-in
   olub seq irəliləyirsə (writerAware) qəbul; əks halda 409. */
function makeServer(opts) {
    const options = Object.assign({ writerAware: true, delayMs: 40 }, opts || {});
    const server = { rev: 0, answers: { 11: "", 12: "" }, w: null, finished: false, posts: [], conflicts: 0, gets: 0 };
    server.write = function (form) {
        const action = form.get("submit_action");
        const base = Number(form.get("autosave_revision"));
        const writer = form.get("autosave_writer") || "";
        const seq = Number(form.get("autosave_seq") || 0);
        server.posts.push({ action, base, writer, seq });
        if (server.finished) return { status: 200, body: { success: true, finished: true, redirect_url: "/result/" } };
        if (base !== server.rev) {
            const w = server.w;
            const own =
                options.writerAware && w && writer && w.writer === writer && base >= w.since && seq > w.seq;
            if (!own) {
                server.conflicts += 1;
                const reason = w && w.writer && w.writer !== writer ? "foreign_writer" : "unknown";
                return { status: 409, body: { success: false, conflict: true, server_revision: server.rev, reason } };
            }
        }
        const ids = action === "autosave" ? form.getAll("changed_questions[]") : Object.keys(QUESTIONS);
        ids.forEach((qid) => {
            server.answers[qid] = form.getAll("q_" + qid).sort().join(",");
        });
        server.rev += 1;
        const prev = server.w;
        const streak = prev && writer && prev.writer === writer && prev.rev === server.rev - 1;
        server.w = { rev: server.rev, writer, since: streak ? prev.since : server.rev - 1, seq: streak ? Math.max(seq, prev.seq) : seq };
        if (action === "finish") {
            server.finished = true;
            return { status: 200, body: { success: true, finished: true, redirect_url: "/result/" } };
        }
        return { status: 200, body: { success: true, finished: false, server_revision: server.rev } };
    };
    // Başqa tab / kompüter: serverdə birbaşa yazır.
    server.foreignWrite = function (qid, value) {
        server.answers[qid] = value;
        server.rev += 1;
        server.w = { rev: server.rev, writer: "foreign-tab-0001", since: server.rev - 1, seq: 1 };
    };
    server.fetch = function (window, url, init) {
        const respond = (status, body) => ({
            ok: status >= 200 && status < 300,
            status,
            redirected: false,
            headers: { get: (name) => (name.toLowerCase() === "content-type" ? "application/json" : null) },
            json: () => Promise.resolve(body),
        });
        if (!init || init.method === "GET") {
            server.gets += 1;
            const ids = new window.URL(url, "http://localhost").searchParams.get("q").split(",").filter(Boolean);
            const answers = {};
            ids.forEach((qid) => (answers[qid] = server.answers[qid]));
            return sleep(5).then(() =>
                respond(200, { success: true, finished: server.finished, server_revision: server.rev, writer: server.w ? server.w.writer : "", answers })
            );
        }
        if (server.dropNextResponse) {
            // Server yazır, amma cavab klientə çatmır (nginx 504 / şəbəkə).
            server.dropNextResponse = false;
            return sleep(options.delayMs).then(() => {
                server.write(init.body);
                throw new TypeError("network");
            });
        }
        return sleep(options.delayMs).then(() => {
            const result = server.write(init.body);
            return respond(result.status, result.body);
        });
    };
    return server;
}

function boot(server, extra) {
    const settings = Object.assign(
        { revision: 0, answers: {}, writerAttrs: "", storage: null, channelBus: null, center: true },
        extra || {}
    );
    const dom = new JSDOM(pageHtml(settings.revision, settings.answers, settings.writerAttrs, settings.center), {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/attempt/9/",
        virtualConsole: new VirtualConsole(), // nəticəyə keçid (location.href) jsdom-da «not implemented»dir
    });
    const { window } = dom;
    if (settings.storage) {
        Object.keys(settings.storage).forEach((key) => window.sessionStorage.setItem(key, settings.storage[key]));
    }
    if (settings.channelBus) window.BroadcastChannel = settings.channelBus.factory();
    window.EMSCore = { getCookie: () => "tok" };
    window.gettext = (s) => s;
    window.alert = () => {};
    window.fetch = (url, init) => server.fetch(window, url, init);
    window.EMSTakeExam = {};
    SCRIPTS.forEach((name) => window.eval(read(name)));
    const ns = window.EMSTakeExam;
    const shown = [];
    ns.notifications = { show: (msg, type) => (shown.push({ msg, type }), {}), hide: () => {} };
    ns.progress = { syncMarkedQuestionInput: () => {}, updateProgress: () => {} };
    const navigation = { finished: 0 };
    ns.navigation = { prepareExamFinishNavigation: () => (navigation.finished += 1) };
    ns.timers = { handleTimerNotStarted: () => Promise.reject(new Error("question_timer_sync_required")) };
    const ctx = ns.config.createContext();
    ctx.i18n.autosaveConflict = "CONFLICT";
    ctx.i18n.autosaveShared = "SHARED";
    ns.writer.init(ctx);
    ns.draft.init(ctx);
    ns.resync.init(ctx);
    const pick = (qid, token) => {
        const input = window.document.querySelector(`input[name="q_${qid}"][value="${token}"]`);
        input.checked = true;
        input.dispatchEvent(new window.Event("change"));
    };
    return { window, ns, ctx, shown, navigation, pick, status: () => window.document.getElementById("exam-sync-status") };
}

async function waitFor(predicate, ms) {
    const deadline = Date.now() + (ms || 4000);
    while (!predicate() && Date.now() < deadline) await sleep(10);
    return predicate();
}

test("REPRO: «Qaralama saxla» while an autosave is in flight never yields a self-conflict (strict server)", async () => {
    // writerAware=false — yalnız klient növbəsi: iki yazı heç vaxt eyni revision ilə paralel getmir.
    const server = makeServer({ writerAware: false, delayMs: 60 });
    const env = boot(server);
    try {
        env.pick(11, "tA");
        // Autosave debounce (1 s) bitsin və sorğu yola düşsün, sonra cavabı gəlməmiş «Qaralama saxla».
        const inFlight = () => Boolean(env.ctx.saveInFlight || env.ctx.autoSaveRequestInFlight);
        await waitFor(inFlight, 2500);
        assert.ok(inFlight(), "autosave must be in flight");
        const draft = env.ns.draft.sendDraft(env.ctx, "save_draft");
        env.pick(12, "tD");
        await draft;
        await waitFor(() => !env.ctx.hasUnsavedChanges && !env.ctx.saveInFlight, 4000);
        env.ctx.finishRequestInFlight = true;
        await env.ns.draft.sendDraft(env.ctx, "finish");
        assert.equal(server.conflicts, 0, "no 409 for a single tab");
        assert.equal(env.ctx.autosaveConflict, false);
        assert.equal(server.finished, true);
        assert.deepEqual(server.answers, { 11: "tA", 12: "tD" });
        assert.equal(env.status().hidden, true, "no conflict banner");
    } finally {
        env.window.close();
    }
});

test("finish right after a lost autosave response succeeds (writer-aware server, no 409)", async () => {
    const server = makeServer();
    const env = boot(server);
    try {
        env.pick(11, "tB");
        server.dropNextResponse = true;
        await env.ns.draft.sendDraft(env.ctx, "autosave", { silent: true }).catch(() => {});
        assert.equal(server.rev, 1, "server applied the write");
        assert.equal(env.ctx.autosaveRevisionField.value, "0", "client never saw the new revision");
        env.pick(12, "tC");
        env.ctx.finishRequestInFlight = true;
        await env.ns.draft.sendDraft(env.ctx, "finish");
        assert.equal(server.conflicts, 0);
        assert.equal(server.finished, true);
        assert.deepEqual(server.answers, { 11: "tB", 12: "tC" });
    } finally {
        env.window.close();
    }
});

test("without the server writer record a 409 re-syncs and finishes with every answer", async () => {
    const server = makeServer({ writerAware: false });
    const env = boot(server);
    try {
        env.pick(11, "tB");
        server.dropNextResponse = true;
        await env.ns.draft.sendDraft(env.ctx, "autosave", { silent: true }).catch(() => {});
        env.pick(11, "tA"); // yenidən dəyişdi — server «tB»-ni bu tabın öz (cavabsız) yazısından bilir
        env.pick(12, "tD");
        env.ctx.finishRequestInFlight = true;
        await env.ns.draft.sendDraft(env.ctx, "finish");
        assert.equal(server.conflicts, 1, "one 409, then re-sync");
        assert.equal(server.gets, 1);
        assert.equal(env.ctx.autosaveConflict, false, "tab is not frozen");
        assert.equal(server.finished, true);
        assert.deepEqual(server.answers, { 11: "tA", 12: "tD" });
    } finally {
        env.window.close();
    }
});

test("non-centre exam: a REAL second tab that changed another question is merged, not overwritten", async () => {
    const server = makeServer();
    const env = boot(server, { center: false });
    try {
        server.foreignWrite(12, "tC"); // digər tab Q12-ni cavablayır
        env.pick(11, "tA");
        await waitFor(() => server.rev === 2 && !env.ctx.saveInFlight, 4000);
        assert.equal(server.conflicts, 1);
        assert.deepEqual(server.answers, { 11: "tA", 12: "tC" }, "other tab's answer survives");
        assert.equal(env.window.document.querySelector('input[name="q_12"]:checked').value, "tC", "DOM adopts it");
        assert.equal(env.ctx.autosaveConflict, false);
        assert.equal(env.status().textContent, "SHARED", "persistent multi-tab warning");
    } finally {
        env.window.close();
    }
});

test("non-centre exam: a REAL second tab that changed the SAME question blocks this tab", async () => {
    const server = makeServer();
    const env = boot(server, { center: false });
    try {
        server.foreignWrite(11, "tB");
        env.pick(11, "tA");
        env.pick(12, "tD");
        await waitFor(() => env.ctx.autosaveConflict, 4000);
        await waitFor(() => !env.ctx.saveInFlight, 2000);
        assert.equal(server.answers[11], "tB", "other tab's answer is not overwritten");
        assert.equal(server.answers[12], "tD", "the safe answer was still submitted");
        assert.equal(env.status().textContent, "CONFLICT");
        assert.equal(env.window.document.getElementById("exam-sync-reload").hidden, false);
        const posts = server.posts.length;
        await env.ns.draft.sendDraft(env.ctx, "finish").catch(() => {});
        assert.equal(server.posts.length, posts, "blocked tab cannot finish over the other tab");
        const draft = JSON.parse(env.window.sessionStorage.getItem(env.ctx.draftStorageKey));
        assert.equal("11" in draft.selectedAnswers, false, "conflicting answer is not restored after reload");
    } finally {
        env.window.close();
    }
});

test("a draft persisted before a reload is restored when the later writes were this tab's own", () => {
    const server = makeServer();
    const storage = {
        exam_5_attempt_9_writer: JSON.stringify({ id: "tabwriter0001", seq: 4 }),
        exam_5_attempt_9_draft: JSON.stringify({
            version: 1,
            baseRevision: "3",
            writer: "tabwriter0001",
            selectedAnswers: { 11: "tB", 12: "tD" },
            textAnswers: {},
        }),
    };
    // Köhnə səhifənin yolda qalan autosave-i render-dən əvvəl yazıldı (rev 4, eyni writer, since 3).
    const env = boot(server, {
        revision: 4,
        answers: { 11: "tB" },
        writerAttrs: 'data-writer="tabwriter0001" data-writer-since="3"',
        storage,
    });
    try {
        env.ns.draft.restoreLocalDraft(env.ctx);
        assert.equal(env.window.document.querySelector('input[name="q_12"]:checked').value, "tD");
        assert.ok(env.ctx.dirtyQuestionIds.has("12"));
    } finally {
        env.window.close();
    }
});

test("a duplicated tab (copied sessionStorage) gets its own writer id", async () => {
    const listeners = [];
    const bus = {
        factory: () =>
            class {
                constructor() {
                    listeners.push(this);
                }
                postMessage(data) {
                    listeners.filter((l) => l !== this).forEach((l) => setTimeout(() => l.onmessage && l.onmessage({ data }), 0));
                }
                close() {}
            },
    };
    const storage = { exam_5_attempt_9_writer: JSON.stringify({ id: "tabwriter0001", seq: 2 }) };
    const original = boot(makeServer(), { storage, channelBus: bus });
    const duplicate = boot(makeServer(), { storage, channelBus: bus });
    try {
        await sleep(30);
        assert.equal(original.ctx.writerId, "tabwriter0001", "the live tab keeps its id");
        assert.notEqual(duplicate.ctx.writerId, "tabwriter0001", "the duplicate regenerates");
    } finally {
        original.window.close();
        duplicate.window.close();
    }
});

/* ── 2026-10-21 (sahib): zal (final/midterm) imtahanında HƏQİQİ ikinci tab TAM bloklanır ───────────── */

function makeBus() {
    const listeners = [];
    return {
        factory: () =>
            class {
                constructor() {
                    listeners.push(this);
                }
                postMessage(data) {
                    listeners
                        .filter((l) => l !== this)
                        .forEach((l) => setTimeout(() => l.onmessage && l.onmessage({ data }), 0));
                }
                close() {}
            },
    };
}

test("centre exam: a 409 from another writer blocks this tab at once — no merge, no further writes", async () => {
    const server = makeServer();
    const env = boot(server);
    try {
        server.foreignWrite(12, "tC");
        env.pick(11, "tA");
        await waitFor(() => env.ctx.secondTabBlocked, 4000);
        await waitFor(() => !env.ctx.saveInFlight, 2000);
        assert.equal(server.gets, 0, "no answers-state merge for a centre exam");
        assert.equal(server.posts.length, 1, "only the rejected request");
        assert.deepEqual(server.answers, { 11: "", 12: "tC" }, "the other tab's data is untouched");
        assert.equal(env.status().className.includes("secondTab"), true);
        assert.equal(env.window.document.getElementById("exam-sync-reload").hidden, false);
        assert.equal(env.window.document.querySelector('input[name="q_11"]').disabled, true, "answers locked");
        await env.ns.draft.sendDraft(env.ctx, "finish").catch(() => {});
        assert.equal(server.posts.length, 1, "blocked tab cannot finish");
    } finally {
        env.window.close();
    }
});

test("centre exam: a second tab of the same browser is blocked on load; the first tab keeps working", async () => {
    const bus = makeBus();
    const server = makeServer();
    const first = boot(server, { channelBus: bus });
    await sleep(5);
    const second = boot(server, { channelBus: bus });
    try {
        await waitFor(() => second.ctx.secondTabBlocked, 1000);
        assert.equal(second.ctx.secondTabBlocked, true);
        assert.equal(Boolean(first.ctx.secondTabBlocked), false);
        assert.notEqual(second.ctx.writerId, first.ctx.writerId);
        // Bloklu tab heç nə yazmır; birinci tab adi qaydada yazır.
        await second.ns.draft.sendDraft(second.ctx, "autosave").catch(() => {});
        second.ctx.hasUnsavedChanges = true;
        await second.ns.draft.sendDraft(second.ctx, "save_draft").catch(() => {});
        assert.equal(server.posts.length, 0, "second tab never writes");
        first.pick(11, "tB");
        await first.ns.draft.sendDraft(first.ctx, "autosave", { silent: true });
        assert.equal(server.answers[11], "tB");
        assert.equal(server.conflicts, 0);
        assert.equal(first.status().hidden, true, "first tab shows no banner");
    } finally {
        first.window.close();
        second.window.close();
    }
});

test("centre exam: a blocked tab does not block the first tab's reload", async () => {
    const bus = makeBus();
    const server = makeServer();
    const first = boot(server, { channelBus: bus });
    await sleep(5);
    const second = boot(server, { channelBus: bus });
    await waitFor(() => second.ctx.secondTabBlocked, 1000);
    first.ctx.writerChannel.onmessage = null; // birinci tab yenilənir: köhnə səhifənin kanalı yoxa çıxır
    first.window.close();
    const reloaded = boot(server, {
        channelBus: bus,
        storage: { exam_5_attempt_9_writer: JSON.stringify({ id: first.ctx.writerId, seq: first.ctx.writerSeq }) },
    });
    try {
        await sleep(40);
        assert.equal(Boolean(reloaded.ctx.secondTabBlocked), false, "bloklu tab «present» cavabı vermir");
        assert.equal(reloaded.ctx.writerId, first.ctx.writerId, "reload keeps the same writer");
    } finally {
        second.window.close();
        reloaded.window.close();
    }
});

test("non-centre exam: a second tab is NOT blocked on load (merge behaviour kept)", async () => {
    const bus = makeBus();
    const server = makeServer();
    const first = boot(server, { channelBus: bus, center: false });
    await sleep(5);
    const second = boot(server, { channelBus: bus, center: false });
    try {
        await sleep(40);
        assert.equal(Boolean(second.ctx.secondTabBlocked), false);
    } finally {
        first.window.close();
        second.window.close();
    }
});
