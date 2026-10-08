/* ═══════════════════════════════════════════════════════════════════════════
   «Keçən ildən köçür» — sillabussuz açılış sətrindən (2026-10-08 düzəlişi).

   Əvvəl düymə siyahının öz dialoqunu açıb `{action: "copy", syllabus: <AÇILIŞ id>}`
   göndərirdi və 404 alırdı.  İndi təkrar istifadə dialoqu `mode=previous` ilə
   açılır, mənbə seçilir və `copy_previous` HƏDƏF AÇILIŞLA göndərilir.

   Göndərilən fayllar OLDUĞU KİMİ icra olunur (ems_ajax_init + syllabus_list +
   syllabus_reuse); şəbəkə `EMSCore.fetchJSON` stub-u ilə tutulur.
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

/* `_reuse_dialog.html`-in JS-in toxunduğu hook-ları (mətnlər data-t-* ilə). */
const DIALOG =
    '<div data-syl-reuse-modal hidden data-options-url="/reuse/" data-action-url="/reuse/action/" data-create-url="/action/">' +
    '<div role="dialog" tabindex="-1"><h3 data-syl-reuse-title>reuse</h3><p data-syl-reuse-target></p>' +
    "<p data-syl-reuse-loading></p><p data-syl-reuse-blocked hidden></p>" +
    '<div data-syl-reuse-sources-wrap hidden><div data-syl-reuse-sources></div></div>' +
    '<div data-syl-reuse-choice hidden><div data-syl-reuse-link-option><button data-syl-reuse-do="link"></button>' +
    '<p data-syl-reuse-hint="link"></p></div><button data-syl-reuse-do="copy"></button><p data-syl-reuse-hint="copy"></p>' +
    "<p data-syl-reuse-replace hidden></p></div>" +
    '<div data-syl-reuse-bulk hidden><div data-syl-reuse-cands></div><button data-syl-reuse-do="bulk"></button></div>' +
    "<ul data-syl-reuse-results hidden></ul>" +
    '<div class="syl-modal__foot"><button data-syl-reuse-blank hidden></button><button data-syl-reuse-close>x</button></div>' +
    "</div></div>" +
    '<span data-syl-reuse-i18n hidden data-t-title-previous="Keçmiş semestrin sillabusundan köçür" ' +
    'data-t-title-reuse="reuse" data-t-copy-previous-ok="ok-previous" data-t-cancel="Ləğv et"></span>';

const PAGE =
    '<section data-profile-section-panel="syllabus-list"><div data-syllabus-list data-profile-url="/accounts/profile/" ' +
    'data-action-url="/action/">' +
    '<button data-syl-action="copy" data-row-kind="missing" data-id="OFF-1">Keçən ildən köçür</button>' +
    '<div data-syl-toast hidden><span data-syl-toast-text></span></div>' +
    DIALOG +
    "</div></section>";

const OPTIONS = {
    ok: true,
    mode: "previous",
    target: { kind: "offering", id: "OFF-1", offering: "OFF-1", group: "102A", subject: "RSE101", blocked: false },
    siblings: [
        {
            id: "SRC-1",
            group: "2024/2025 · Payız",
            author: "Müəllif: siz",
            status_tone: "success",
            status_label: "Təsdiqlənib",
            version_label: "v1.0",
            hours_text: "Mühazirə 30",
            hours_same: true,
            can_link: false,
            link_reason: "",
            can_copy: true,
            copy_reason: "",
            modes: {},
        },
    ],
    candidates: [],
    can_create_blank: true,
};

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

async function makeWindow() {
    const dom = new JSDOM("<!doctype html><html><body>" + PAGE + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/accounts/profile/?section=syllabus-list",
    });
    const { window } = dom;
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    const calls = [];
    const loads = [];
    window.EMSCore = {
        fetchJSON(url, options) {
            calls.push({ url, options: options || null });
            if (!options) {
                return Promise.resolve(OPTIONS);
            }
            return Promise.resolve({ ok: true, message: "Köçürüldü", version: "VER-1", status: "draft" });
        },
    };
    window.EMSProfileLoadSection = (section, url) => loads.push({ section, url });
    window.eval(INIT);
    window.eval(LIST);
    window.eval(REUSE);
    return { window, calls, loads };
}

test("copy from an offering row asks for previous sources and creates the target offering", async () => {
    const { window, calls, loads } = await makeWindow();
    try {
        const doc = window.document;
        doc.querySelector("[data-syl-action='copy']").click();
        await flush();

        const modal = doc.querySelector("[data-syl-reuse-modal]");
        assert.equal(modal.hidden, false);
        assert.equal(calls.length, 1);
        const query = new URL(calls[0].url, "http://localhost").searchParams;
        assert.equal(query.get("offering"), "OFF-1");
        assert.equal(query.get("mode"), "previous");
        assert.equal(doc.querySelector("[data-syl-reuse-title]").textContent, "Keçmiş semestrin sillabusundan köçür");
        assert.equal(doc.querySelector("[data-syl-reuse-link-option]").hidden, true); // bağlama YOX
        const copy = doc.querySelector("[data-syl-reuse-do='copy']");
        assert.equal(copy.disabled, false);
        assert.equal(doc.querySelector("[data-syl-reuse-hint='copy']").textContent, "ok-previous");

        copy.click();
        await flush();
        assert.equal(calls.length, 2);
        assert.equal(calls[1].url, "/reuse/action/");
        assert.deepEqual(JSON.parse(JSON.stringify(calls[1].options.data)), {
            action: "copy_previous",
            source: "SRC-1",
            offering: "OFF-1",
        });
        // Köhnə yol (siyahının öz «copy» dialoqu → /action/) heç çağırılmadı.
        assert.ok(calls.every((call) => call.url !== "/action/"));
        assert.equal(modal.hidden, true);
        assert.equal(loads.length, 1);
        assert.equal(loads[0].section, "syllabus-editor");
        assert.match(loads[0].url, /version=VER-1/);
        assert.equal(JSON.parse(window.sessionStorage.getItem("ems.syllabus.flash")).section, "syllabus-editor");
    } finally {
        window.close();
    }
});
