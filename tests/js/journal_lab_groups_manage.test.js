/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-11-06: jurnalın «Lab qrupları» ekranı (journal_lab_groups.html).
   ƏSL göndərilən fayllar jsdom-da: static/js/ems_ajax_init.js (EMSReady / EMSDelegate) +
   apps/registrar/static/registrar/js/journal_lab_groups_manage.js.
   Yoxlanır: seçim sayğacı; «Köçür» yalnız tələbə + hədəf seçiləndə açılır; bölmənin «hamısını seç»
   checkbox-u yalnız görünən və bağlı olmayan sətirləri seçir, yarımçıq seçimdə indeterminate olur;
   axtarış (az hərfləri, registr və diakritik fərqi sayılmır) sətirləri gizlədir, seçimi saxlayır;
   AJAX swap-dan (profile:section:loaded) sonra yenidən yüklənmə işləyiciləri yığmır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const INIT = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const PANEL_JS = fs.readFileSync(
    path.join(ROOT, "apps/registrar/static/registrar/js/journal_lab_groups_manage.js"),
    "utf8"
);

function row(id, name, extra) {
    return (
        '<li data-lgm-row data-lgm-name="' + name.toLowerCase() + '">' +
        '<label><input type="checkbox" name="enrollment" value="' + id + '" data-lgm-pick' + (extra || "") + ">" +
        "<span>" + name + "</span></label></li>"
    );
}

async function page() {
    const html =
        '<main data-lgm><input type="search" data-lgm-search>' +
        '<form data-lgm-assign-form>' +
        '<fieldset data-lgm-bucket="none"><legend><input type="checkbox" data-lgm-bucket-all></legend><ul>' +
        row("e1", "Əliyev Şahin") +
        row("e2", "İsmayılova Günel") +
        row("e3", "Quliyev Orxan", " disabled") +
        "</ul></fieldset>" +
        '<fieldset data-lgm-bucket="1"><legend><input type="checkbox" data-lgm-bucket-all></legend><ul>' +
        row("e4", "Məmmədova Ayan") +
        "</ul></fieldset>" +
        '<div data-lgm-bar><strong data-lgm-selected>0</strong>' +
        '<select name="target" data-lgm-target><option value="">—</option><option value="1">Lab-1</option>' +
        '<option value="none">Qrupsuz et</option></select>' +
        "<button type=\"submit\" data-lgm-submit>Köçür</button></div>" +
        "</form></main>";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/jurnal/o1/lab-qruplari/",
    });
    const { window } = dom;
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    window.eval(INIT);
    window.eval(PANEL_JS);
    const $ = (selector) => window.document.querySelector(selector);
    const change = (el) => el.dispatchEvent(new window.Event("change", { bubbles: true }));
    const pick = (id, on) => {
        const box = $('[value="' + id + '"]');
        box.checked = on !== false;
        change(box);
    };
    const target = (value) => {
        $("[data-lgm-target]").value = value;
        change($("[data-lgm-target]"));
    };
    const search = (text) => {
        $("[data-lgm-search]").value = text;
        $("[data-lgm-search]").dispatchEvent(new window.Event("input", { bubbles: true }));
    };
    return { window, $, pick, target, search, change };
}

test("move button opens only with a selection and a target; counter follows the picks", async () => {
    const { $, pick, target } = await page();
    const submit = $("[data-lgm-submit]");
    assert.equal(submit.disabled, true, "ilkin vəziyyət: heç nə seçilməyib");
    assert.equal($("[data-lgm-selected]").textContent, "0");
    pick("e1");
    assert.equal($("[data-lgm-selected]").textContent, "1");
    assert.equal(submit.disabled, true, "hədəf seçilməyib");
    target("1");
    assert.equal(submit.disabled, false);
    pick("e1", false);
    assert.equal(submit.disabled, true);
    pick("e4");
    target("none");
    assert.equal(submit.disabled, false, "«Qrupsuz et» də hədəfdir");
});

test("bucket select-all skips locked rows and shows a partial state", async () => {
    const { $, pick, change } = await page();
    const all = $('[data-lgm-bucket="none"] [data-lgm-bucket-all]');
    all.checked = true;
    change(all);
    assert.equal($('[value="e1"]').checked, true);
    assert.equal($('[value="e2"]').checked, true);
    assert.equal($('[value="e3"]').checked, false, "qeydi olan (bağlı) tələbə seçilmir");
    assert.equal($('[value="e4"]').checked, false, "başqa bölmə toxunulmur");
    assert.equal($("[data-lgm-selected]").textContent, "2");
    pick("e2", false);
    assert.equal(all.checked, false);
    assert.equal(all.indeterminate, true);
    pick("e2");
    assert.equal(all.checked, true);
    assert.equal(all.indeterminate, false);
});

test("search hides non-matching rows (Azerbaijani letters, case and diacritics) and keeps the selection", async () => {
    const { $, pick, search, change } = await page();
    pick("e4");
    search("ISMAYIL");
    assert.equal($('[value="e2"]').closest("[data-lgm-row]").hidden, false, "İ/ı registri fərq etmir");
    assert.equal($('[value="e1"]').closest("[data-lgm-row]").hidden, true);
    assert.equal($('[value="e4"]').closest("[data-lgm-row]").hidden, true);
    assert.equal($("[data-lgm-selected]").textContent, "1", "gizlənən seçim saxlanır");
    search("sahin");
    assert.equal($('[value="e1"]').closest("[data-lgm-row]").hidden, false, "ş → s diakritiki sayılmır");
    const all = $('[data-lgm-bucket="none"] [data-lgm-bucket-all]');
    all.checked = true;
    change(all);
    assert.equal($('[value="e1"]').checked, true);
    assert.equal($('[value="e2"]').checked, false, "«hamısını seç» yalnız görünən sətirlər");
    search("");
    assert.equal($('[value="e2"]').closest("[data-lgm-row]").hidden, false);
});

test("re-running the script after an AJAX swap does not stack handlers", async () => {
    const { window, $, pick } = await page();
    window.eval(PANEL_JS);
    window.document.dispatchEvent(new window.CustomEvent("profile:section:loaded", { detail: {} }));
    const counter = $("[data-lgm-selected]");
    const writes = [];
    Object.defineProperty(counter, "textContent", {
        configurable: true,
        get() {
            return writes.length ? writes[writes.length - 1] : "0";
        },
        set(value) {
            writes.push(value);
        },
    });
    pick("e1");
    assert.deepEqual(writes, ["1"], "bir dəyişiklik — bir yenilənmə (işləyici yığılmır)");
});
