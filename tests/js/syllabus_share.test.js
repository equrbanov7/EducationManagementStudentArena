/* ═══════════════════════════════════════════════════════════════════════════
   «Bir sillabus — bir neçə jurnal» (sahib 2026-10-27).

   1. Təkrar istifadə dialoqunda «Eyni sillabusu bu qrupda da istifadə et» →
      `{action: "share", source, offering}`;
   2. redaktorun paylaşım blokunda «Ayır» → təsdiq → `{action: "unshare", syllabus, offering}`;
   3. «Bu qrupda da istifadə et» (layihənin seçim komponenti) → `share` → redaktor yenidən yüklənir.

   Göndərilən fayllar OLDUĞU KİMİ icra olunur (ems_ajax_init + syllabus_list + syllabus_reuse +
   syllabus_share); şəbəkə `EMSCore.fetchJSON` stub-u ilə tutulur.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const INIT = read("static/js/ems_ajax_init.js");
const LIST = read("apps/accounts/static/accounts/js/profile/syllabus_list.js");
const REUSE = read("apps/accounts/static/accounts/js/profile/syllabus_reuse.js");
const SHARE = read("apps/accounts/static/accounts/js/profile/syllabus_share.js");

const DIALOG =
    '<div data-syl-reuse-modal hidden data-options-url="/reuse/" data-action-url="/reuse/action/" data-create-url="/action/">' +
    '<div role="dialog" tabindex="-1"><h3 data-syl-reuse-title>reuse</h3><p data-syl-reuse-target></p>' +
    "<p data-syl-reuse-loading></p><p data-syl-reuse-blocked hidden></p>" +
    '<div data-syl-reuse-sources-wrap hidden><div data-syl-reuse-sources></div></div>' +
    '<div data-syl-reuse-choice hidden><div data-syl-reuse-share-option><button data-syl-reuse-do="share"></button>' +
    '<p data-syl-reuse-hint="share"></p></div>' +
    '<div data-syl-reuse-link-option><button data-syl-reuse-do="link"></button>' +
    '<p data-syl-reuse-hint="link"></p></div><button data-syl-reuse-do="copy"></button><p data-syl-reuse-hint="copy"></p>' +
    "<p data-syl-reuse-replace hidden></p></div>" +
    '<div data-syl-reuse-bulk hidden><div data-syl-reuse-cands></div><button data-syl-reuse-do="bulk"></button></div>' +
    "<ul data-syl-reuse-results hidden></ul>" +
    '<div class="syl-modal__foot"><button data-syl-reuse-blank hidden></button><button data-syl-reuse-close>x</button></div>' +
    "</div></div>" +
    '<div data-syl-reuse-confirm hidden data-action-url="/reuse/action/"><div data-syl-reuse-confirm-box>' +
    "<h3 data-syl-reuse-confirm-title></h3><p data-syl-reuse-confirm-body></p>" +
    "<button data-syl-reuse-confirm-close>x</button><button data-syl-reuse-confirm-ok></button></div></div>" +
    '<span data-syl-reuse-i18n hidden data-t-title-reuse="reuse" data-t-share-ok="share-ok" data-t-cancel="Ləğv et" ' +
    'data-t-unshare-title="Paylaşım ayrılsın?" data-t-unshare-body="body" data-t-unshare-ok="Ayır"></span>';

const LIST_PAGE =
    '<section data-profile-section-panel="syllabus-list"><div data-syllabus-list data-profile-url="/accounts/profile/" ' +
    'data-action-url="/action/">' +
    '<button data-syl-action="reuse" data-row-kind="missing" data-id="OFF-2">Mövcud sillabusdan istifadə et</button>' +
    '<div data-syl-toast hidden><span data-syl-toast-text></span></div>' +
    DIALOG +
    "</div></section>";

const EDITOR_PAGE =
    '<section data-profile-section-panel="syllabus-editor"><div data-profile-url="/accounts/profile/">' +
    '<div data-syllabus-editor data-version="VER-1"></div>' +
    '<div data-syl-share data-action-url="/reuse/action/">' +
    '<button data-syl-action="unshare" data-row-kind="syllabus" data-id="SYL-1" data-offering="OFF-2">Ayır</button>' +
    '<div class="bootstrap-single-select"><select class="bootstrap-single-select__native" data-bootstrap-select ' +
    'data-syl-share-select><option value="OFF-3">103A</option><option value="OFF-4">104A</option></select></div>' +
    '<button data-syl-share-add data-id="SYL-1">Bu qrupda da istifadə et</button></div>' +
    '<div data-syl-toast hidden><span data-syl-toast-text></span></div>' +
    DIALOG +
    "</div></section>";

const OPTIONS = {
    ok: true,
    mode: "reuse",
    target: { kind: "offering", id: "OFF-2", offering: "OFF-2", group: "102A", subject: "RSE101", blocked: false },
    siblings: [
        {
            id: "SYL-1",
            group: "101A",
            author: "Müəllif: siz",
            status_tone: "neutral",
            status_label: "Qaralama",
            version_label: "v1.0",
            hours_text: "Mühazirə 30",
            hours_same: true,
            can_share: true,
            share_reason: "",
            can_link: false,
            link_reason: "təsdiqlənməyib",
            can_copy: true,
            copy_reason: "",
            modes: {},
        },
    ],
    candidates: [],
    can_create_blank: true,
};

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

async function makeWindow(page, url) {
    const dom = new JSDOM("<!doctype html><html><body>" + page + "</body></html>", { runScripts: "outside-only", url });
    const { window } = dom;
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    const calls = [];
    const loads = [];
    window.EMSCore = {
        fetchJSON(target, options) {
            calls.push({ url: target, options: options || null });
            if (!options) {
                return Promise.resolve(OPTIONS);
            }
            return Promise.resolve({ ok: true, message: "Hazırdır" });
        },
    };
    window.EMSProfileLoadSection = (section, target) => loads.push({ section, url: target });
    window.eval(INIT);
    window.eval(LIST);
    window.eval(REUSE);
    window.eval(SHARE);
    return { window, calls, loads };
}

test("reuse dialog shares the same syllabus with the missing group", async () => {
    const { window, calls } = await makeWindow(LIST_PAGE, "http://localhost/accounts/profile/?section=syllabus-list");
    try {
        const doc = window.document;
        doc.querySelector("[data-syl-action='reuse']").click();
        await flush();
        const share = doc.querySelector("[data-syl-reuse-do='share']");
        assert.equal(doc.querySelector("[data-syl-reuse-share-option]").hidden, false);
        assert.equal(share.disabled, false);
        assert.equal(doc.querySelector("[data-syl-reuse-hint='share']").textContent, "share-ok");
        assert.equal(doc.querySelector("[data-syl-reuse-do='link']").disabled, true);
        share.click();
        await flush();
        assert.deepEqual(JSON.parse(JSON.stringify(calls[1].options.data)), {
            action: "share",
            source: "SYL-1",
            offering: "OFF-2",
        });
        assert.equal(doc.querySelector("[data-syl-reuse-modal]").hidden, true);
    } finally {
        window.close();
    }
});

test("editor: unshare asks for confirmation and sends the offering", async () => {
    const { window, calls, loads } = await makeWindow(
        EDITOR_PAGE,
        "http://localhost/accounts/profile/?section=syllabus-editor"
    );
    try {
        const doc = window.document;
        doc.querySelector("[data-syl-action='unshare']").click();
        const confirm = doc.querySelector("[data-syl-reuse-confirm]");
        assert.equal(confirm.hidden, false);
        assert.equal(doc.querySelector("[data-syl-reuse-confirm-title]").textContent, "Paylaşım ayrılsın?");
        doc.querySelector("[data-syl-reuse-confirm-ok]").click();
        await flush();
        assert.deepEqual(JSON.parse(JSON.stringify(calls[0].options.data)), {
            action: "unshare",
            syllabus: "SYL-1",
            offering: "OFF-2",
        });
        assert.equal(confirm.hidden, true);
        assert.equal(loads[0].section, "syllabus-editor");
        assert.match(loads[0].url, /version=VER-1/);
    } finally {
        window.close();
    }
});

test("editor: add group shares the syllabus with the selected offering and reloads the editor", async () => {
    const { window, calls, loads } = await makeWindow(
        EDITOR_PAGE,
        "http://localhost/accounts/profile/?section=syllabus-editor"
    );
    try {
        const doc = window.document;
        doc.querySelector("[data-syl-share-select]").value = "OFF-4";
        doc.querySelector("[data-syl-share-add]").click();
        await flush();
        assert.equal(calls.length, 1);
        assert.equal(calls[0].url, "/reuse/action/");
        assert.deepEqual(JSON.parse(JSON.stringify(calls[0].options.data)), {
            action: "share",
            source: "SYL-1",
            offering: "OFF-4",
        });
        assert.equal(loads.length, 1);
        assert.equal(loads[0].section, "syllabus-editor");
        assert.match(loads[0].url, /version=VER-1/);
    } finally {
        window.close();
    }
});
