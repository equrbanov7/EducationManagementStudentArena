/* ═══════════════════════════════════════════════════════════════════════════
   «Fənləri birləşdir» dialoqu (2026-10-19) — subject_merge.js ƏSL DOM-da (jsdom).
   Server mətni HTML kimi şərh OLUNMUR, link yalnız eyni-sayt yoludur, iz (digest) yalnız
   toqquşmasız önizləmədə yazılır, «Birləşdir» səbəb ≥20 olmadan açılmır, seçim dəyişəndə
   iz sıfırlanır və POST hədəf/mənbə/iz/səbəbi göndərir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/profile/subject_merge.js"), "utf8");

const HTML = `<!doctype html><html><body>
<button data-sm-open id="open"></button>
<div class="ems-overlay" data-sm-root data-sm-lookup-url="/l/" data-sm-groups-url="/g/" data-sm-preview-url="/p/"
     data-sm-apply-url="/a/" data-sm-text-stale="STALE" data-sm-text-ready="READY" data-sm-text-blocking="BLOCK"
     data-sm-text-moves="köçür" data-sm-text-keeps="qalır" data-sm-text-archive="Arxiv:" data-sm-text-more="və daha {n}"
     data-sm-text-pick="PICK">
  <form data-sm-form>
    <input type="hidden" name="csrfmiddlewaretoken" value="tok">
    <input type="hidden" name="digest" data-sm-digest>
    <p data-ems-form-error hidden></p>
    <details data-sm-groups-box><div data-sm-groups></div></details>
    <div data-sm-target-picker><div><input></div><div></div></div>
    <div data-sm-sources-picker><div><input></div><div></div></div>
    <button type="button" data-sm-preview>Önizlə</button>
    <div data-sm-result hidden></div>
    <div data-sm-reason-box hidden><textarea data-sm-reason></textarea></div>
    <button type="submit" data-sm-submit disabled>Birləşdir</button>
  </form>
</div></body></html>`;

function load() {
    const dom = new JSDOM(HTML, { runScripts: "outside-only", url: "http://localhost/profil/" });
    const win = dom.window;
    const calls = [];
    const pickers = [];
    win.EMSDelegate = {
        on(evt, selector, fn) {
            win.document.addEventListener(evt, (event) => {
                const target = event.target && event.target.closest && event.target.closest(selector);
                if (target) {
                    fn(event, target);
                }
            });
        },
    };
    win.EMSSearchableSelect = {
        create(el, opts) {
            const selected = {};
            const api = {
                el,
                opts,
                value: () => Object.keys(selected)[0] || "",
                ids: () => Object.keys(selected),
                reset() {
                    Object.keys(selected).forEach((key) => delete selected[key]);
                },
                setValue(id, label) {
                    if (!opts.multi) {
                        api.reset();
                    }
                    selected[id] = label;
                    opts.onChange();
                },
            };
            pickers.push(api);
            return api;
        },
    };
    win.EMSOverlay = { open() {}, close() {} };
    win.EMSCore = {
        fetchJSON(url, options) {
            calls.push({ url, body: new win.URLSearchParams(options.body) });
            return Promise.resolve(win.__next || { ok: true });
        },
    };
    win.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({ groups: [] }) });
    win.eval(SCRIPT);
    return { win, calls, pickers };
}

function preview(extra) {
    return Object.assign(
        {
            tables: [
                { key: "a", title: "<i>Açılış</i>", strategy: "repoint", count: 2, by_source: [{ code: "S", count: 2 }] },
                { key: "b", title: "Şans", strategy: "keep", count: 1, by_source: [] },
                { key: "c", title: "Boş", strategy: "repoint", count: 0, by_source: [] },
            ],
            blocking: [],
            blocking_total: 0,
            resolvable: [],
            resolvable_total: 0,
            warnings: [],
            info: [],
            archive_reason: "Birləşdirildi → T",
            digest: "abc",
            can_apply: true,
        },
        extra || {}
    );
}

test("ilk açılışda seçicilər qurulur, mənbə seçicisi arxivi də axtarır", () => {
    const { win, pickers } = load();
    win.document.getElementById("open").click();
    assert.equal(pickers.length, 2);
    assert.equal(pickers[0].opts.multi, false);
    assert.equal(pickers[1].opts.multi, true);
    assert.equal(pickers[1].opts.url, "/l/?archived=1");
});

test("önizləmə mətnləri textContent ilə yazılır; iz və səbəb yalnız toqquşmasız halda", () => {
    const { win } = load();
    const root = win.document.querySelector("[data-sm-root]");
    win.EMSSubjectMerge.renderPreview(root, preview());
    const result = root.querySelector("[data-sm-result]");
    assert.equal(result.hidden, false);
    assert.equal(result.querySelector("i"), null, "server mətni HTML kimi şərh olunmamalıdır");
    assert.match(result.textContent, /<i>Açılış<\/i>/);
    assert.doesNotMatch(result.textContent, /Boş/, "sıfır saylı cədvəl göstərilmir");
    assert.match(result.textContent, /READY/);
    assert.equal(root.querySelector("[data-sm-digest]").value, "abc");
    assert.equal(root.querySelector("[data-sm-reason-box]").hidden, false);

    win.EMSSubjectMerge.renderPreview(
        root,
        preview({
            can_apply: false,
            blocking: [{ message: "Toqquşma", links: [{ label: "J", url: "/jurnal/1/" }, { label: "X", url: "https://evil.example/" }] }],
            blocking_total: 3,
        })
    );
    assert.equal(root.querySelector("[data-sm-digest]").value, "");
    assert.equal(root.querySelector("[data-sm-reason-box]").hidden, true);
    const links = Array.from(result.querySelectorAll("a")).map((a) => a.getAttribute("href"));
    assert.deepEqual(links, ["/jurnal/1/"]);
    assert.match(result.textContent, /və daha 2/);
});

test("«Birləşdir» səbəb ≥20 olmadan bağlıdır; seçim dəyişəndə iz sıfırlanır", () => {
    const { win, pickers } = load();
    win.document.getElementById("open").click();
    const root = win.document.querySelector("[data-sm-root]");
    win.EMSSubjectMerge.renderPreview(root, preview());
    const submit = root.querySelector("[data-sm-submit]");
    const reason = root.querySelector("[data-sm-reason]");
    reason.value = "qısa";
    reason.dispatchEvent(new win.Event("input", { bubbles: true }));
    assert.equal(submit.disabled, true);
    reason.value = "Tədris şöbəsinin təklifi: eyni fənn";
    reason.dispatchEvent(new win.Event("input", { bubbles: true }));
    assert.equal(submit.disabled, false);
    pickers[1].setValue("s2", "S2");
    assert.equal(root.querySelector("[data-sm-digest]").value, "");
    assert.equal(submit.disabled, true);
    assert.match(root.querySelector("[data-sm-result]").textContent, /STALE/);
});

test("təsdiq POST-u hədəf, mənbələr, iz və səbəbi göndərir", async () => {
    const { win, pickers, calls } = load();
    win.document.getElementById("open").click();
    const root = win.document.querySelector("[data-sm-root]");
    pickers[0].setValue("t1", "T");
    pickers[1].setValue("s1", "S");
    pickers[1].setValue("t1", "T"); // hədəf mənbədə də seçilibsə göndərilmir
    win.EMSSubjectMerge.renderPreview(root, preview());
    root.querySelector("[data-sm-reason]").value = "Tədris şöbəsinin təklifi: eyni fənn";
    root.querySelector("form").dispatchEvent(new win.Event("submit", { bubbles: true, cancelable: true }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "/a/");
    assert.equal(calls[0].body.get("target"), "t1");
    assert.deepEqual(calls[0].body.getAll("sources"), ["s1"]);
    assert.equal(calls[0].body.get("digest"), "abc");
});

test("seçim yoxdursa önizləmə sorğu göndərmir", () => {
    const { win, calls } = load();
    win.document.getElementById("open").click();
    win.document.querySelector("[data-sm-preview]").click();
    assert.equal(calls.length, 0);
    assert.equal(win.document.querySelector("[data-ems-form-error]").textContent, "PICK");
});
