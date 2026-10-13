/* ═══════════════════════════════════════════════════════════════════════════
   2026-10-14 (sahib: «bütün search-lərdə debounce düzgün işləmir, çox sürətli
   olur; yazarkən search gedir, render olur, axtardığım itir»):
   vahid yazdıqca-axtarış qatı EMSSearchInput — ƏSL DOM-da (jsdom).

   Göndərilən fayllar OLDUĞU KİMİ icra olunur:
     static/js/ems_search_input.js  — debounce / Enter / IME / minChars / latest()
     static/js/ems_search_swap.js   — snapshot / restore / morph / submitForm
     static/js/ems_ajax_init.js + static/js/ems_ui/filter_bar.js — avto filtr paneli
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const CORE = read("static/js/ems_search_input.js");
const SWAP = read("static/js/ems_search_swap.js");
const INIT = read("static/js/ems_ajax_init.js");
const FILTER_BAR = read("static/js/ems_ui/filter_bar.js");
/** Sahib 2026-10-14: «0.5 saniyə azdır, 1500 ms edək». */
const D = 1500;

/** Əl ilə idarə olunan saat — testlər real gözləmir. */
function fakeClock(window) {
    let now = 0;
    let seq = 0;
    const queue = new Map();
    window.setTimeout = (fn, ms) => {
        seq += 1;
        queue.set(seq, { fn, at: now + (ms || 0) });
        return seq;
    };
    window.clearTimeout = (id) => queue.delete(id);
    return {
        tick(ms) {
            const until = now + ms;
            for (;;) {
                let next = null;
                for (const [id, job] of queue) {
                    if (job.at <= until && (!next || job.at < next[1].at)) {
                        next = [id, job];
                    }
                }
                if (!next) {
                    break;
                }
                queue.delete(next[0]);
                now = next[1].at;
                next[1].fn();
            }
            now = until;
        },
    };
}

function makePage(body, url) {
    const dom = new JSDOM("<!doctype html><html><body>" + (body || "") + "</body></html>", {
        runScripts: "outside-only",
        url: url || "http://localhost/accounts/profile/?section=people",
    });
    const { window } = dom;
    const clock = fakeClock(window);
    window.eval(CORE);
    window.eval(SWAP);
    return { window, document: window.document, clock };
}

/** İstifadəçi kimi yaz: dəyər + `input` hadisəsi (isteğe bağlı IME bayrağı). */
function type(window, input, value, extra) {
    input.value = value;
    input.dispatchEvent(new window.InputEvent("input", Object.assign({ bubbles: true }, extra || {})));
}

function key(window, input, name, extra) {
    const ev = new window.KeyboardEvent(
        "keydown",
        Object.assign({ key: name, bubbles: true, cancelable: true }, extra || {})
    );
    input.dispatchEvent(ev);
    return ev;
}

function bindLog(window, input, opts) {
    const calls = [];
    window.EMSSearchInput.bind(
        input,
        Object.assign(
            {
                onSearch(value, meta) {
                    calls.push([value, meta.reason]);
                },
            },
            opts || {}
        )
    );
    return calls;
}

test("waits 1500 ms (owner: «0.5 saniyə azdır») after the LAST keystroke (one request, not one per letter)", () => {
    const { window, document, clock } = makePage('<input type="search" id="q">');
    const input = document.getElementById("q");
    input.focus();
    const calls = bindLog(window, input);
    assert.equal(window.EMSSearchInput.EMS_SEARCH_DEBOUNCE_MS, 1500);
    assert.equal(window.EMSSearchInput.DELAY_MS, D);

    type(window, input, "al");
    clock.tick(1000);
    type(window, input, "ali");
    clock.tick(1000);
    type(window, input, "aliy");
    clock.tick(D - 1);
    assert.deepEqual(calls, [], "yazı davam edərkən sorğu getməməlidir");
    clock.tick(1);
    assert.deepEqual(calls, [["aliy", "typing"]]);
});

test("needs 2+ characters; clearing the field resets immediately", () => {
    const { window, document, clock } = makePage('<input type="search" id="q">');
    const input = document.getElementById("q");
    input.focus();
    const calls = bindLog(window, input);

    type(window, input, "a");
    clock.tick(2 * D);
    assert.deepEqual(calls, [], "1 simvolda server axtarışı yoxdur");

    type(window, input, "ab");
    clock.tick(D);
    type(window, input, "");
    assert.deepEqual(calls, [["ab", "typing"], ["", "clear"]], "boşaldanda gözləmədən sıfırlanır");

    type(window, input, "a");
    type(window, input, "");
    clock.tick(2 * D);
    assert.equal(calls.length, 2, "artıq boş olan sahə üçün təkrar sıfırlama yoxdur");
});

test("Enter searches at once (even 1 character) and blocks native submit", () => {
    const { window, document, clock } = makePage('<form id="f"><input type="search" id="q"></form>');
    const input = document.getElementById("q");
    input.focus();
    const calls = bindLog(window, input);

    type(window, input, "x");
    const ev = key(window, input, "Enter");
    assert.equal(ev.defaultPrevented, true, "native form göndərişi (səhifə yenilənməsi) olmamalıdır");
    assert.deepEqual(calls, [["x", "enter"]]);
    clock.tick(2 * D);
    assert.equal(calls.length, 1, "Enter-dən sonra gözləyən taymer qalmamalıdır");

    key(window, input, "Enter");
    assert.equal(calls.length, 1, "dəyər dəyişməyibsə Enter təkrar sorğu atmır");
});

test("IME composition: nothing is sent until compositionend", () => {
    const { window, document, clock } = makePage('<input type="search" id="q">');
    const input = document.getElementById("q");
    input.focus();
    const calls = bindLog(window, input);

    input.dispatchEvent(new window.CompositionEvent("compositionstart", { bubbles: true }));
    type(window, input, "şə", { isComposing: true });
    clock.tick(2 * D);
    const ime = key(window, input, "Enter", { isComposing: true });
    assert.equal(ime.defaultPrevented, false, "namizədi təsdiqləyən Enter axtarış deyil");
    assert.deepEqual(calls, []);

    input.dispatchEvent(new window.CompositionEvent("compositionend", { bubbles: true }));
    clock.tick(D - 1);
    assert.deepEqual(calls, []);
    clock.tick(1);
    assert.deepEqual(calls, [["şə", "typing"]]);
});

test("no request when the value did not change (arrows, Shift, typed-and-deleted)", () => {
    const { window, document, clock } = makePage('<input type="search" id="q" value="ab">');
    const input = document.getElementById("q");
    input.focus();
    const calls = bindLog(window, input);

    key(window, input, "ArrowLeft");
    key(window, input, "Shift", { shiftKey: true });
    type(window, input, "abc");
    type(window, input, "ab");
    clock.tick(2 * D);
    assert.deepEqual(calls, [], "server artıq «ab» üçün cavab verib");

    type(window, input, "abd");
    clock.tick(D);
    assert.deepEqual(calls, [["abd", "typing"]]);
});

test("delegate() covers inputs added later (AJAX swap) without stacking", () => {
    const { window, document, clock } = makePage('<div id="host"></div>');
    const calls = [];
    const opts = { onSearch: (value) => calls.push(value) };
    window.EMSSearchInput.delegate("[data-live-q]", opts);
    window.EMSSearchInput.delegate("[data-live-q]", opts); // təkrar qeydiyyat
    document.getElementById("host").innerHTML = '<input type="search" data-live-q>';
    const input = document.querySelector("[data-live-q]");
    input.focus();
    type(window, input, "qrup");
    clock.tick(D);
    assert.deepEqual(calls, ["qrup"], "bir dəfə, bir sorğu");
});

test("latest(): an older slow response is recognisably stale and aborted", () => {
    const { window } = makePage("");
    const seq = window.EMSSearchInput.latest();
    const first = seq.begin();
    const second = seq.begin();
    assert.equal(first.current(), false);
    assert.equal(first.signal.aborted, true, "köhnə fetch ləğv olunur");
    assert.equal(second.current(), true);
    seq.cancel();
    assert.equal(second.current(), false);
});

test("busy(): subtle «Axtarılır…» badge, no layout replacement", () => {
    const { window, document } = makePage('<div class="search-field" id="w"><input type="search" id="q"></div>');
    const host = document.getElementById("w");
    host.style.position = "relative";
    const input = document.getElementById("q");
    window.EMSSearchInput.busy(input, true);
    const badge = host.querySelector(".ems-search-status");
    assert.ok(badge, "nişan input-un yanında yaranır");
    assert.equal(badge.hidden, false);
    assert.equal(badge.getAttribute("role"), "status");
    assert.match(badge.textContent, /Axtarılır/);
    assert.equal(input.getAttribute("aria-busy"), "true");
    window.EMSSearchInput.busy(input, false);
    assert.equal(badge.hidden, true);
    assert.equal(input.hasAttribute("aria-busy"), false);
    assert.equal(host.children.length, 2, "panel yenidən render olunmur");
});

test("morph(): the focused input survives the swap — focus, caret and typed letters stay", () => {
    const panel =
        '<section id="p" data-profile-section-panel="people">' +
        '<form data-x-bound="1"><div class="row"><input type="search" name="q" id="q" value="ab">' +
        '<span class="count">5</span></div></form>' +
        '<ul class="results"><li>old-1</li><li>old-2</li></ul></section>';
    const { window, document } = makePage(panel);
    const oldPanel = document.getElementById("p");
    const input = document.getElementById("q");
    input.focus();
    input.value = "abc"; // cavab gələnə qədər istifadəçi yazmağa davam edib
    input.setSelectionRange(2, 2);

    const fresh = new window.DOMParser().parseFromString(
        '<section id="p" data-profile-section-panel="people" class="is-active">' +
            '<div class="notice">2 nəticə</div>' +
            '<form><div class="row"><input type="search" name="q" id="q" value="ab">' +
            '<span class="count">2</span></div></form>' +
            '<ul class="results"><li>new-1</li></ul></section>',
        "text/html"
    ).querySelector("section");

    assert.equal(window.EMSSearchInput.morph(oldPanel, fresh, input), true);
    assert.equal(document.getElementById("q"), input, "input elementi ƏVƏZLƏNMƏDİ");
    assert.equal(document.activeElement, input, "fokus yerində");
    assert.equal(input.value, "abc", "yükləmə gedərkən yazılan hərf itmədi");
    assert.equal(input.selectionStart, 2, "kursor yerində");
    assert.equal(document.querySelector(".results").textContent, "new-1", "nəticələr yeniləndi");
    assert.equal(document.querySelector(".count").textContent, "2");
    assert.ok(document.querySelector(".notice"), "yeni qardaş elementlər də gəlir");
    assert.ok(oldPanel.classList.contains("is-active"), "panel atributları sinxronlaşır");
    assert.equal(document.querySelector("form").getAttribute("data-x-bound"), "1", "JS bağlama nişanı qalır");
});

test("restore(): full replacement falls back to focus + value + caret and re-queues the typed text", () => {
    const { window, document, clock } = makePage('<div id="host"><input type="search" name="q" value="ab"></div>');
    const calls = [];
    window.EMSSearchInput.delegate('input[name="q"]', { onSearch: (v) => calls.push(v) });
    const host = document.getElementById("host");
    const oldInput = host.querySelector("input");
    oldInput.focus();
    type(window, oldInput, "abcd");
    const snap = window.EMSSearchInput.snapshot(host);
    host.innerHTML = '<input type="search" name="q" value="abc">'; // server «abc» üçün cavab verdi
    const el = window.EMSSearchInput.restore(snap, host);
    assert.notEqual(el, oldInput);
    assert.equal(document.activeElement, el);
    assert.equal(el.value, "abcd");
    assert.equal(el.selectionStart, 4);
    clock.tick(D);
    assert.deepEqual(calls, ["abcd"], "köhnə element DOM-dan çıxıb — yalnız yeni element üçün bir sorğu");
});

test("submitForm(): cabinet GET form → quiet section load, no full page reload", () => {
    const { window, document } = makePage(
        '<section data-profile-section-panel="assigned-courses"><form method="get">' +
            '<input type="hidden" name="section" value="assigned-courses">' +
            '<input type="search" name="assigned_course_search" value="riy"></form></section>'
    );
    const loads = [];
    window.EMSProfileLoadSection = (section, url, opts) => loads.push([section, url, opts]);
    const form = document.querySelector("form");
    let nativeSubmit = 0;
    form.addEventListener("submit", () => (nativeSubmit += 1));
    window.EMSSearchInput.submitForm(form, { input: form.querySelector('[type="search"]') });
    assert.equal(nativeSubmit, 0);
    assert.equal(loads.length, 1);
    assert.equal(loads[0][0], "assigned-courses");
    assert.match(loads[0][1], /assigned_course_search=riy/);
    assert.equal(loads[0][2].quiet, true);
});

test("submitForm() soft mode: a slow older response never overwrites newer results", async () => {
    const { window, document } = makePage(
        '<div class="jl-page"><form method="get" data-ems-soft-search=".jl-page">' +
            '<input type="search" name="q" id="q"></form><ul class="rows"><li>start</li></ul></div>',
        "http://localhost/jurnal/"
    );
    const pending = [];
    window.fetch = (url) =>
        new Promise((resolve) => {
            pending.push(() =>
                resolve({
                    ok: true,
                    text: () =>
                        Promise.resolve(
                            '<div class="jl-page"><form method="get" data-ems-soft-search=".jl-page">' +
                                '<input type="search" name="q" id="q"></form><ul class="rows"><li>' +
                                new URL(url).searchParams.get("q") +
                                "</li></ul></div>"
                        ),
                })
            );
        });
    const form = document.querySelector("form");
    const input = document.getElementById("q");
    input.focus();
    input.value = "ri";
    window.EMSSearchInput.submitForm(form, { input });
    input.value = "riyaz";
    window.EMSSearchInput.submitForm(form, { input });
    pending[1](); // yeni cavab əvvəl gəlir
    await new Promise((r) => setImmediate(r));
    pending[0](); // köhnə yavaş cavab sonra
    await new Promise((r) => setImmediate(r));
    assert.equal(document.querySelector(".rows").textContent, "riyaz", "köhnə cavab atıldı");
    assert.equal(document.getElementById("q"), input, "forma/input əvəzlənmədi");
    assert.equal(document.activeElement, input);
    assert.match(window.location.search, /q=riyaz/, "URL sinxron (replaceState)");
});

test("filter_bar auto mode: debounced quiet load, Enter immediate, blur does not fire half-typed query", () => {
    const html =
        '<section data-profile-section-panel="people">' +
        '<form class="ems-filters" data-ems-filters data-section="people" data-param-prefix="pd_" data-ems-filters-auto="1">' +
        '<div class="ems-field"><input class="ems-input" type="search" name="pd_q" value="" data-ems-filter data-ems-filter-search></div>' +
        '<div class="ems-field"><select name="pd_role" data-ems-filter><option value="">*</option><option value="t">t</option></select></div>' +
        "</form><div class=\"ems-tablewrap\"><table><tbody><tr><td>x</td></tr></tbody></table></div></section>";
    const { window, document, clock } = makePage(html);
    window.eval(INIT);
    const loads = [];
    window.EMSProfileLoadSection = (section, url, opts) => loads.push({ section, url, opts });
    window.eval(FILTER_BAR);

    const input = document.querySelector('[name="pd_q"]');
    input.focus();
    type(window, input, "ə");
    clock.tick(2 * D);
    assert.equal(loads.length, 0, "1 simvol — sorğu yoxdur");
    type(window, input, "əli");
    clock.tick(D - 1);
    assert.equal(loads.length, 0);
    clock.tick(1);
    assert.equal(loads.length, 1);
    assert.equal(loads[0].opts.quiet, true, "yazdıqca axtarış skeletsiz/fokus oğurlamadan yüklənir");
    assert.match(decodeURIComponent(loads[0].url), /pd_q=əli/);
    assert.equal(document.querySelector("tbody").textContent, "x", "cədvəl skeleton-a çevrilmir, yalnız solur");
    assert.ok(document.querySelector(".ems-tablewrap").classList.contains("ems-search-pending"));

    type(window, input, "əliy");
    input.dispatchEvent(new window.Event("change", { bubbles: true })); // blur
    assert.equal(loads.length, 1, "sahədən çıxmaq yarımçıq sorğu atmır");
    key(window, input, "Enter");
    assert.equal(loads.length, 2, "Enter — dərhal");

    const select = document.querySelector('[name="pd_role"]');
    select.value = "t";
    select.dispatchEvent(new window.Event("change", { bubbles: true }));
    assert.equal(loads.length, 3, "select dəyişən kimi tətbiq olunur");
    assert.equal(loads[2].opts, undefined, "select dəyişikliyi adi (skeletli) yükləmədir");
});

test("a specific registration beats the generic fallback rule, whatever the script order", () => {
    const { window, document, clock } = makePage('<form method="get"><input type="search" name="wl_search" id="q"></form>');
    const calls = [];
    window.EMSSearchInput.delegate('input[name*="search" i]', { fallback: true, onSearch: () => calls.push("generic") });
    window.EMSSearchInput.delegate("#q", { onSearch: () => calls.push("own") });
    const input = document.getElementById("q");
    input.focus();
    type(window, input, "riyaziyyat");
    clock.tick(D);
    assert.deepEqual(calls, ["own"], "ümumi qayda yalnız xüsusi qeydiyyat yoxdursa işləyir");
});

test("clear() (× button) resets at once without waiting", () => {
    const { window, document } = makePage('<input type="search" id="q" value="abc">');
    const input = document.getElementById("q");
    input.focus();
    const calls = bindLog(window, input);
    assert.equal(window.EMSSearchInput.handles(input), true);
    assert.equal(window.EMSSearchInput.clear(input), true);
    assert.equal(input.value, "");
    assert.deepEqual(calls, [["", "clear"]]);
});

/* ── Kabinet bölmə yükləyicisi: «quiet» (yazdıqca axtarış) yükləmə ─────────── */
const SECTION_LOADER = read("apps/accounts/static/accounts/js/profile/section_loader.js");

function sectionHtml(value, rows) {
    return (
        '<section class="profile-section-panel" data-profile-section-panel="people">' +
        '<form method="get"><input type="hidden" name="section" value="people">' +
        '<input type="search" name="pd_search" id="pd-q" value="' + value + '"></form>' +
        '<ul class="rows">' + rows.map((r) => "<li>" + r + "</li>").join("") + "</ul></section>"
    );
}

async function cabinet() {
    const page = makePage(
        '<div class="profile-page"><h1 id="profileSectionTitle">İnsanlar</h1>' +
            '<div id="profileSectionsContainer">' + sectionHtml("", ["a", "b"]).replace('class="profile-section-panel"', 'class="profile-section-panel is-active"') +
            "</div></div>"
    );
    const { window, document } = page;
    window.eval(INIT);
    let installer = null;
    window.EMSProfile = { register: (fn) => (installer = fn) };
    window.eval(SECTION_LOADER);
    const host = document.getElementById("profileSectionsContainer");
    const ctx = {
        profilePage: document.querySelector(".profile-page"),
        ajaxSafeSections: ["people"],
        sectionFragmentUrlTemplate: "/accounts/profile/section/__SECTION__/",
        sectionsHost: host,
        profileBaseUrl: "/accounts/profile/",
        sectionTitle: document.getElementById("profileSectionTitle"),
        sectionPanels: document.querySelectorAll("[data-profile-section-panel]"),
        updateSidebarActiveState() {},
        isMobileViewport: () => false,
        setSidebarCollapsed() {},
        initDebouncedSearchForms() {},
    };
    installer(ctx);
    page.respond = (html) => {
        window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true, html }) });
    };
    return page;
}

const settle = () => new Promise((r) => setTimeout(r, 10));

test("cabinet quiet load keeps the typed-in input: no title focus steal, no skeleton, no lost letters", async () => {
    const { window, document, respond } = await cabinet();
    const input = document.getElementById("pd-q");
    input.focus();
    input.value = "əliy";
    input.setSelectionRange(4, 4);
    respond(sectionHtml("əli", ["Əliyev Ramin"]));
    const done = window.EMSProfileLoadSection("people", "/accounts/profile/?section=people&pd_search=%C9%99li", { quiet: true });
    await done;
    await settle();
    assert.equal(document.getElementById("pd-q"), input, "input əvəzlənmədi");
    assert.equal(document.activeElement, input, "fokus başlığa keçmədi");
    assert.equal(input.value, "əliy", "yükləmə gedərkən yazılan hərf qaldı");
    assert.equal(input.selectionStart, 4);
    assert.equal(document.querySelector(".rows").textContent, "Əliyev Ramin", "nəticə yeniləndi");
    assert.equal(document.querySelector(".profile-section-skeleton"), null);
    assert.match(window.location.search, /pd_search=/);
});

test("cabinet normal (non-quiet) navigation still moves focus to the section title (a11y F5)", async () => {
    const { window, document, respond } = await cabinet();
    respond(sectionHtml("", ["x"]));
    await window.EMSProfileLoadSection("people", "/accounts/profile/?section=people");
    await settle();
    assert.equal(document.activeElement, document.getElementById("profileSectionTitle"));
});
