/* ═══════════════════════════════════════════════════════════════════════════
   PROC 2026-10-01: imtahan səhifəsinin evristik anti-cheat qatı
   (apps/exams/static/exams/js/exam_supervision/proctor_signals.js) və İM monitorunun
   kimlik render köməkçisi (apps/exams/static/exams/js/final_center/proctor_identity.js)
   ƏSL DOM-da (jsdom). Fayllar olduğu kimi icra olunur; `fetch` yalnız tutulur.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SIGNALS = fs.readFileSync(
    path.join(ROOT, "apps/exams/static/exams/js/exam_supervision/proctor_signals.js"), "utf8");
const IDENTITY = fs.readFileSync(
    path.join(ROOT, "apps/exams/static/exams/js/final_center/proctor_identity.js"), "utf8");

function tick() {
    return new Promise((resolve) => setTimeout(resolve, 0));
}

async function examPage(opts) {
    opts = opts || {};
    const cfg = Object.assign({
        antiAi: "1", devtools: "0", monitor: "1", text: "1", blockCopyPaste: true, shortcuts: true
    }, opts);
    const html =
        '<!doctype html><html><head></head><body>' +
        '<nav class="navbar">menu</nav>' +
        '<div class="exam-shell"><div class="question-content"><p class="q-text">2+2?</p></div>' +
        '<textarea class="written-answer" name="q_7"></textarea>' +
        '<div class="file-dropzone" data-exam-dropzone-qid="7"></div></div>' +
        '<script id="supervision-config-data" type="application/json">' +
        JSON.stringify({ block_copy_paste: cfg.blockCopyPaste, restrict_keyboard_shortcuts: cfg.shortcuts }) +
        "</script>" +
        '<div id="supervision-bootstrap" hidden data-log-endpoint="/exams/supervision/api/log/5/" data-csrf-token="tok"></div>' +
        '<div id="proctor-signals-config" hidden data-supervised="1" data-attempt-id="5"' +
        ' data-signal-url="/exams/supervision/api/signal/5/" data-heartbeat-url="/exams/supervision/api/heartbeat/5/"' +
        ' data-heartbeat-interval="60" data-anti-ai="' + cfg.antiAi + '" data-detect-devtools="' + cfg.devtools + '"' +
        ' data-detect-multi-monitor="' + cfg.monitor + '" data-detect-text-injection="' + cfg.text + '"></div>' +
        "</body></html>";
    const dom = new JSDOM(html, { runScripts: "outside-only", url: "http://127.0.0.1:8015/exams/x/attempt/5/" });
    const { window } = dom;
    const calls = [];
    window.fetch = (url, init) => {
        calls.push({ url, body: JSON.parse(init.body) });
        return Promise.resolve({ status: 200 });
    };
    if (opts.extended) {
        Object.defineProperty(window.screen, "isExtended", { value: true, configurable: true });
    }
    if (opts.webdriver) {
        Object.defineProperty(window.navigator, "webdriver", { value: true, configurable: true });
    }
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    window.eval(SIGNALS);
    return { window, calls, api: window.EMSProctorSignals };
}

function signals(calls, kind) {
    return calls.filter((c) => c.url.indexOf("/signal/") !== -1 && (!kind || c.body.kind === kind));
}

test("boots once, marks <html> and hardens answer fields against writing assistants", async () => {
    const { window, api } = await examPage();
    try {
        const root = window.document.documentElement;
        assert.ok(api._started);
        assert.ok(root.classList.contains("proctor-on"));
        assert.ok(root.classList.contains("proctor-guard"));
        const ta = window.document.querySelector("textarea");
        assert.equal(ta.getAttribute("data-gramm"), "false");
        assert.equal(ta.getAttribute("writingsuggestions"), "false");
        window.eval(SIGNALS); // ikinci yükləmə yeni nüsxə yaratmır
        assert.equal(window.EMSProctorSignals, api);
    } finally {
        api.stop();
        window.close();
    }
});

test("injected AI-helper element is reported once; own/navbar elements are not", async () => {
    const { window, calls, api } = await examPage();
    try {
        assert.deepEqual(signals(calls).map((c) => c.body), [], "page-load baseline (navbar, exam shell) must stay silent");
        const doc = window.document;
        const helper = doc.createElement("div");
        helper.id = "monica-content-root";
        doc.body.appendChild(helper);
        const again = doc.createElement("div");
        again.className = "monica-sidebar";
        doc.body.appendChild(again);
        const own = doc.createElement("div");
        own.className = "toast-container";
        doc.body.appendChild(own);
        await tick();
        const ai = signals(calls, "ai_extension");
        assert.equal(ai.length, 1);
        assert.equal(ai[0].body.detail.token, "monica");
        assert.equal(signals(calls, "dom_injection").length, 0);
    } finally {
        api.stop();
        window.close();
    }
});

test("extension iframe, extension resource and unknown top-level element are classified", async () => {
    const { window, calls, api } = await examPage();
    try {
        const doc = window.document;
        const frame = doc.createElement("iframe");
        frame.setAttribute("src", "about:blank");
        doc.body.appendChild(frame);
        const img = doc.createElement("img");
        img.setAttribute("src", "chrome-extension://abcdefgh/icon.png");
        doc.querySelector(".exam-shell").appendChild(img);
        const blob = doc.createElement("section");
        doc.body.appendChild(blob);
        const custom = doc.createElement("helper-widget");
        doc.querySelector(".exam-shell").appendChild(custom);
        await tick();
        assert.equal(signals(calls, "extension_frame").length, 1);
        assert.equal(signals(calls, "extension_resource")[0].body.detail.origin, "chrome-extension://abcdefgh");
        const dom = signals(calls, "dom_injection").map((c) => c.body.detail.tag).sort();
        assert.deepEqual(dom, ["helper-widget", "section"]);
    } finally {
        api.stop();
        window.close();
    }
});

test("paste / drop / bulk text into an answer is blocked and reported; typing stays free", async () => {
    const { window, calls, api } = await examPage();
    try {
        const ta = window.document.querySelector("textarea");
        // `isTrusted` [LegacyUnforgeable]-dır — brauzerin ƏSL hadisəsini təqlid etmək üçün
        // handler hadisəyə bənzər obyektlə birbaşa çağırılır.
        function trusted(inputType, data) {
            return {
                isTrusted: true, target: ta, inputType: inputType, data: data, defaultPrevented: false,
                preventDefault() { this.defaultPrevented = true; }
            };
        }
        const paste = trusted("insertFromPaste", null);
        api.onBeforeInput(paste);
        assert.equal(paste.defaultPrevented, true);
        const drop = trusted("insertFromDrop", null);
        api.onBeforeInput(drop);
        assert.equal(drop.defaultPrevented, true);
        const bulk = trusted("insertText", "x".repeat(60));
        api.onBeforeInput(bulk);
        assert.equal(bulk.defaultPrevented, true);
        const typed = trusted("insertText", "a");
        api.onBeforeInput(typed);
        assert.equal(typed.defaultPrevented, false);
        const autocorrect = trusted("insertReplacementText", "düzəliş");
        api.onBeforeInput(autocorrect);
        assert.equal(autocorrect.defaultPrevented, false);
        assert.equal(signals(calls, "paste_input").length, 2);
        assert.equal(signals(calls, "bulk_insert")[0].body.detail.chars, 60);
    } finally {
        api.stop();
        window.close();
    }
});

test("superhuman typing speed is reported as fast_input", async () => {
    const { window, calls, api } = await examPage();
    try {
        const ta = window.document.querySelector("textarea");
        for (let i = 0; i < 80; i++) {
            api.onBeforeInput({ isTrusted: true, target: ta, inputType: "insertText", data: "ab", preventDefault() {} });
        }
        const fast = signals(calls, "fast_input");
        assert.equal(fast.length, 1);
        assert.ok(fast[0].body.detail.chars > 150);
    } finally {
        api.stop();
        window.close();
    }
});

test("script-driven (untrusted) input into an answer is reported as programmatic_input", async () => {
    const { window, calls, api } = await examPage();
    try {
        const ta = window.document.querySelector("textarea");
        ta.value = "answer written by an extension";
        ta.dispatchEvent(new window.Event("input", { bubbles: true }));
        ta.dispatchEvent(new window.KeyboardEvent("keydown", { key: "a", bubbles: true }));
        const hits = signals(calls, "programmatic_input");
        assert.equal(hits.length, 2);
        assert.deepEqual(hits.map((c) => c.body.detail.via).sort(), ["input", "keydown"]);
    } finally {
        api.stop();
        window.close();
    }
});

test("file drops on the upload zone are NOT blocked; text drops elsewhere are", async () => {
    const { window, api } = await examPage();
    try {
        const zone = window.document.querySelector(".file-dropzone");
        const fileDrop = new window.Event("drop", { bubbles: true, cancelable: true });
        zone.dispatchEvent(fileDrop);
        assert.equal(fileDrop.defaultPrevented, false);
        const textDrop = new window.Event("drop", { bubbles: true, cancelable: true });
        window.document.querySelector(".q-text").dispatchEvent(textDrop);
        assert.equal(textDrop.defaultPrevented, true);
        const select = new window.Event("selectstart", { bubbles: true, cancelable: true });
        window.document.querySelector(".q-text").dispatchEvent(select);
        assert.equal(select.defaultPrevented, true);
        const selectAnswer = new window.Event("selectstart", { bubbles: true, cancelable: true });
        window.document.querySelector("textarea").dispatchEvent(selectAnswer);
        assert.equal(selectAnswer.defaultPrevented, false);
    } finally {
        api.stop();
        window.close();
    }
});

test("Mac / Firefox DevTools shortcuts are blocked and logged as keyboard_shortcut incidents", async () => {
    const { window, calls, api } = await examPage();
    try {
        const mac = new window.KeyboardEvent("keydown", { code: "KeyI", key: "ˆ", metaKey: true, altKey: true, bubbles: true, cancelable: true });
        window.document.body.dispatchEvent(mac);
        assert.equal(mac.defaultPrevented, true);
        const ff = new window.KeyboardEvent("keydown", { code: "KeyK", key: "K", ctrlKey: true, shiftKey: true, bubbles: true, cancelable: true });
        window.document.body.dispatchEvent(ff);
        assert.equal(ff.defaultPrevented, true);
        const plain = new window.KeyboardEvent("keydown", { code: "KeyI", key: "i", bubbles: true, cancelable: true });
        window.document.body.dispatchEvent(plain);
        assert.equal(plain.defaultPrevented, false);
        const incidents = calls.filter((c) => c.url.indexOf("/log/") !== -1);
        assert.deepEqual(incidents.map((c) => c.body.metadata.combo), ["mac_devtools", "firefox_devtools"]);
        assert.ok(incidents.every((c) => c.body.event_type === "keyboard_shortcut"));
    } finally {
        api.stop();
        window.close();
    }
});

test("multi-monitor and webdriver are reported; heartbeat carries page state", async () => {
    const { window, calls, api } = await examPage({ extended: true, webdriver: true });
    try {
        assert.equal(signals(calls, "multi_monitor").length, 1);
        assert.equal(signals(calls, "automation").length, 1);
        api.beat();
        const beats = calls.filter((c) => c.url.indexOf("/heartbeat/") !== -1);
        assert.equal(beats.length, 1);
        assert.equal(beats[0].body.state.ext, true);
        assert.equal(typeof beats[0].body.state.vis, "boolean");
    } finally {
        api.stop();
        window.close();
    }
});

test("devtools size heuristic needs a sustained jump over the load-time baseline", async () => {
    const { window, calls, api } = await examPage({ devtools: "1" });
    try {
        const set = (ow, iw, oh, ih) => {
            Object.defineProperty(window, "outerWidth", { value: ow, configurable: true });
            Object.defineProperty(window, "innerWidth", { value: iw, configurable: true });
            Object.defineProperty(window, "outerHeight", { value: oh, configurable: true });
            Object.defineProperty(window, "innerHeight", { value: ih, configurable: true });
        };
        set(1400, 1400, 900, 780);
        api.checkDevtoolsSize(); // baseline (brauzer paneli ~120px)
        set(1400, 1400, 900, 780);
        assert.equal(api.checkDevtoolsSize(), false);
        set(1400, 1000, 900, 780); // yan panel 400px açıldı
        assert.equal(api.checkDevtoolsSize(), false); // bir ölçü kifayət deyil
        assert.equal(api.checkDevtoolsSize(), true);
        assert.equal(signals(calls, "devtools_open")[0].body.detail.method, "size");
    } finally {
        api.stop();
        window.close();
    }
});

test("unsupervised page does nothing", async () => {
    const dom = new JSDOM('<!doctype html><html><body><div id="proctor-signals-config" data-supervised="0"></div></body></html>',
        { runScripts: "outside-only", url: "http://127.0.0.1:8015/" });
    const calls = [];
    dom.window.fetch = (url) => { calls.push(url); return Promise.resolve({}); };
    if (dom.window.document.readyState === "loading") {
        await new Promise((resolve) => dom.window.document.addEventListener("DOMContentLoaded", resolve));
    }
    dom.window.eval(SIGNALS);
    try {
        assert.equal(dom.window.EMSProctorSignals._started, false);
        assert.equal(dom.window.document.documentElement.classList.contains("proctor-on"), false);
        assert.equal(calls.length, 0);
    } finally {
        dom.window.close();
    }
});

test("monitor identity helper escapes names and only accepts same-origin photo paths", async () => {
    const dom = new JSDOM(
        '<!doctype html><html><body><script id="fxc-proctor-i18n" type="application/json">' +
        JSON.stringify({ group: "Qrup", studentNumber: "Tələbə №", flagged: "Şübhəli", risk: "Risk",
            hbMissing: "Nəzarət siqnalı yoxdur", severity: { high: "Yüksək" }, sourceSignal: "Siqnal" }) +
        "</script></body></html>",
        { runScripts: "outside-only", url: "http://127.0.0.1:8015/" });
    const { window } = dom;
    try {
        window.eval(IDENTITY);
        const P = window.FXCProctor;
        const evil = P.avatarHtml({ name: "<img src=x onerror=alert(1)>", photo_url: "javascript:alert(1)", initials: "AB" }, "sm");
        assert.ok(!/javascript:/.test(evil));
        assert.ok(!/<img src=x/.test(evil));
        const good = P.avatarHtml({ name: "Aysel", photo_url: "/exams/supervision/photo/5/?v=1", initials: "A" }, "sm");
        assert.ok(good.indexOf('src="/exams/supervision/photo/5/?v=1"') !== -1);
        const external = P.avatarHtml({ name: "X", photo_url: "//evil.example/p.png" }, "sm");
        assert.ok(external.indexOf("<img") === -1);
        const badges = P.badgesHtml({ flagged: true, risk_score: 9, risk_threshold: 6, max_severity: "high", heartbeat: { status: "missing" } });
        assert.ok(badges.indexOf("Şübhəli") !== -1);
        assert.ok(badges.indexOf("Nəzarət siqnalı yoxdur") !== -1);
        assert.ok(P.metaLine({ group: "634 ing", student_number: "N7" }).indexOf("634 ing") !== -1);
        const tl = P.timelineHtml([{ source: "signal", label: "<b>AI</b>", severity: "high", at: "2026-10-01T10:00:00Z" }]);
        assert.ok(tl.indexOf("&lt;b&gt;AI&lt;/b&gt;") !== -1);
        assert.ok(tl.indexOf("Yüksək") !== -1);
    } finally {
        window.close();
    }
});

test("when the teacher allows copy/paste, pasting is neither blocked nor reported", async () => {
    const { window, calls, api } = await examPage({ blockCopyPaste: false });
    try {
        const ta = window.document.querySelector("textarea");
        const paste = { isTrusted: true, target: ta, inputType: "insertFromPaste", data: null, defaultPrevented: false,
            preventDefault() { this.defaultPrevented = true; } };
        api.onBeforeInput(paste);
        assert.equal(paste.defaultPrevented, false);
        assert.equal(signals(calls, "paste_input").length, 0);
    } finally {
        api.stop();
        window.close();
    }
});
