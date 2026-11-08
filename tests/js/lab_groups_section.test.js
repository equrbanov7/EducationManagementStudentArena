/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-11-07: kabinetin «Lab qrupları» bölməsi (accounts/profile/sections/_lab_groups.html).
   ƏSL göndərilən fayllar jsdom-da: static/js/ems_ajax_init.js (EMSReady / EMSDelegate) +
   apps/accounts/static/accounts/js/profile/lab_groups.js.
   Yoxlanır: seçim sayğacı və «Köçür»-ün açılması; sütunun «hamısını seç»-i yalnız görünən və kilidsiz sətirləri
   seçir; axtarış (az hərfləri / diakritik) sətirləri gizlədir; «Köçür», sürüşdür-at, yaratmaq, ad və silmək
   (təsdiqlə) düzgün POST gövdəsi ilə EMSCore.fetchJSON çağırır və bölməni yeniləyir; yalnız-oxu rejimində heç nə
   göndərilmir; AJAX swap-dan sonra yenidən yüklənmə işləyiciləri yığmır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const INIT = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const PANEL_JS = fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/profile/lab_groups.js"), "utf8");

function row(id, name, extra) {
    const locked = (extra || "").indexOf("disabled") !== -1;
    return (
        '<li class="lgx-stu" data-lgx-row data-lgx-name="' + name.toLowerCase() + '" data-enrollment="' + id + '"' +
        (locked ? "" : ' draggable="true"') + ">" +
        '<label><input type="checkbox" value="' + id + '" data-lgx-pick' + (extra || "") + ">" +
        "<span>" + name + "</span></label></li>"
    );
}

async function page(options) {
    const readonly = options && options.readonly ? "1" : "0";
    const html =
        '<div data-lgx-ws data-action-url="/jurnal/o1/lab-qruplari/emel/" data-readonly="' + readonly + '"' +
        ' data-msg-generic="Alınmadı" data-msg-pick="Seçin" data-msg-target="Qrup seçin"' +
        ' data-msg-delete-title="Sil?" data-msg-delete-body="«%(label)s» — %(n)s tələbə" data-msg-delete-ok="Sil">' +
        '<input type="search" data-lgx-search>' +
        '<strong data-lgx-selected>0</strong>' +
        '<select data-lgx-target><option value="">—</option><option value="1">Lab-1</option>' +
        '<option value="none">Qrupsuz et</option></select>' +
        '<button type="button" data-lgx-move>Köçür</button><button type="button" data-lgx-clear hidden>x</button>' +
        '<section data-lgx-col="none"><input type="checkbox" data-lgx-col-all><ul>' +
        row("e1", "Əliyev Şahin") +
        row("e2", "İsmayılova Günel") +
        row("e3", "Quliyev Orxan", " disabled") +
        "</ul></section>" +
        '<section data-lgx-col="1"><button type="button" data-lgx-rename-toggle>r</button>' +
        '<button type="button" data-lgx-delete data-group="1" data-label="Səhər" data-members="1">d</button>' +
        '<form data-lgx-rename-form hidden><input type="hidden" name="group" value="1">' +
        '<input name="name" value=" Axşam "><button type="submit">ok</button></form>' +
        '<input type="checkbox" data-lgx-col-all><ul>' + row("e4", "Məmmədova Ayan") + "</ul></section>" +
        '<form data-lgx-create-form><input name="name" value="  Yeni "><button type="submit">+</button></form>' +
        "</div>";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/profile/?section=lab-groups&lg_offering=o1",
    });
    const { window } = dom;
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    const calls = [];
    const reloads = [];
    const toasts = [];
    window.EMSCore = {
        fetchJSON(url, opts) {
            const fields = {};
            for (const [key, value] of opts.body.entries()) {
                (fields[key] = fields[key] || []).push(value);
            }
            calls.push({ url, method: opts.method, fields });
            return Promise.resolve({ ok: true, messages: [{ level: "success", text: "OK" }] });
        },
    };
    window.EMSToast = { show: (text, level) => toasts.push([text, level]) };
    window.EMSProfileLoadSection = (section, href) => reloads.push([section, href]);
    window.EMSConfirm = { open: (opts) => { window.__confirmed = opts; return Promise.resolve(true); } };
    window.eval(INIT);
    window.eval(PANEL_JS);
    const $ = (selector) => window.document.querySelector(selector);
    const change = (el) => el.dispatchEvent(new window.Event("change", { bubbles: true }));
    const pick = (id, on) => {
        const box = $('[data-lgx-pick][value="' + id + '"]');
        box.checked = on !== false;
        change(box);
    };
    const target = (value) => {
        $("[data-lgx-target]").value = value;
        change($("[data-lgx-target]"));
    };
    const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
    return { window, $, pick, target, change, calls, reloads, toasts, flush };
}

test("move opens only with a selection and a target, then posts assign and reloads the section", async () => {
    const { $, pick, target, calls, reloads, toasts, flush } = await page();
    const move = $("[data-lgx-move]");
    assert.equal(move.disabled, true);
    pick("e1");
    assert.equal($("[data-lgx-selected]").textContent, "1");
    assert.equal(move.disabled, true, "hədəf seçilməyib");
    assert.equal($("[data-lgx-clear]").hidden, false);
    target("1");
    assert.equal(move.disabled, false);
    pick("e2");
    move.click();
    await flush();
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "/jurnal/o1/lab-qruplari/emel/");
    assert.equal(calls[0].method, "POST");
    assert.deepEqual(calls[0].fields, { action: ["assign"], target: ["1"], enrollment: ["e1", "e2"] });
    assert.deepEqual(reloads[0][0], "lab-groups");
    assert.deepEqual(toasts[0], ["OK", "success"]);
});

test("column select-all skips locked and hidden rows; search hides rows but keeps the selection", async () => {
    const { window, $, change } = await page();
    const all = $('[data-lgx-col="none"] [data-lgx-col-all]');
    all.checked = true;
    change(all);
    assert.equal($('[value="e1"]').checked, true);
    assert.equal($('[value="e2"]').checked, true);
    assert.equal($('[value="e3"]').checked, false, "kilidli sətir seçilmir");
    assert.equal($('[value="e4"]').checked, false, "başqa sütun");
    const search = $("[data-lgx-search]");
    search.value = "ismayil";
    search.dispatchEvent(new window.Event("input", { bubbles: true }));
    assert.equal($('[data-enrollment="e1"]').hidden, true);
    assert.equal($('[data-enrollment="e2"]').hidden, false);
    assert.equal($('[value="e1"]').checked, true, "gizlənən sətrin seçimi qalır");
    assert.equal($('[data-enrollment="e2"]').classList.contains("is-picked"), true);
});

test("drag a row onto another column posts assign for that student", async () => {
    const { window, $, calls, flush } = await page();
    const fire = (el, type) => {
        const event = new window.Event(type, { bubbles: true, cancelable: true });
        event.dataTransfer = { setData() {}, effectAllowed: "", dropEffect: "" };
        el.dispatchEvent(event);
        return event;
    };
    fire($('[data-enrollment="e2"]'), "dragstart");
    const column = $('[data-lgx-col="1"]');
    const over = fire(column, "dragover");
    assert.equal(over.defaultPrevented, true);
    assert.equal(column.classList.contains("is-drop"), true);
    fire(column, "drop");
    await flush();
    assert.deepEqual(calls[0].fields, { action: ["assign"], target: ["1"], enrollment: ["e2"] });
    assert.equal(column.classList.contains("is-drop"), false);
});

test("create, rename and confirmed delete post the right actions", async () => {
    const { window, $, calls, flush } = await page();
    const submit = (form) => form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    submit($("[data-lgx-create-form]"));
    await flush();
    $("[data-lgx-rename-toggle]").click();
    assert.equal($("[data-lgx-rename-form]").hidden, false);
    submit($("[data-lgx-rename-form]"));
    await flush();
    $("[data-lgx-delete]").click();
    await flush();
    await flush();
    assert.deepEqual(
        calls.map((call) => call.fields),
        [
            { action: ["create"], name: ["Yeni"] },
            { action: ["rename"], group: ["1"], name: ["Axşam"] },
            { action: ["delete"], group: ["1"], confirm: ["1"] },
        ]
    );
    assert.equal(window.__confirmed.danger, true);
    assert.equal(window.__confirmed.body, "«Səhər» — 1 tələbə");
});

test("read-only workspace sends nothing; re-running the script after a swap does not stack handlers", async () => {
    const ro = await page({ readonly: true });
    ro.pick("e1");
    ro.target("1");
    ro.$("[data-lgx-move]").click();
    await ro.flush();
    assert.equal(ro.calls.length, 0);

    const { window, $, pick, target, calls, flush } = await page();
    window.eval(PANEL_JS);
    window.document.dispatchEvent(new window.CustomEvent("profile:section:loaded", { detail: {} }));
    pick("e1");
    target("none");
    $("[data-lgx-move]").click();
    await flush();
    assert.equal(calls.length, 1);
    assert.deepEqual(calls[0].fields.target, ["none"]);
});
