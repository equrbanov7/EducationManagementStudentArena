/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-11-04: «Yük bölgüsü» — «Bütün kafedralar» rejimi (`chair=all`), ƏSL DOM-da (jsdom).

   Müqavilə:
     • `applyChairMode(true)` kökə `is-all-chairs` qoyur və izah zolağını açır, `false` geri qaytarır;
     • kafedrası olan sətir (server `chair_name` verir) YALNIZ OXU kartıdır: kafedra + fakültə adı, heç bir
       yazı düyməsi (Redaktə / Sil / Bölüşdür / çip redaktəsi) yoxdur;
     • `edit_url` olan sətirdə «Kafedrada redaktə et» keçidi, olmayanda «Yalnız baxış» nişanı;
     • kafedrasız rejimdə boş nəticə «uyğun sətir yoxdur» deyir (tək tapşırıq olmasa da), müəllim hovuzu
       soruşulmur.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const JS_DIR = path.join(ROOT, "apps/accounts/static/accounts/js/profile");
const RENDER = fs.readFileSync(path.join(JS_DIR, "workload_distribution_render.js"), "utf8");
const LIST = fs.readFileSync(path.join(JS_DIR, "workload_distribution_list.js"), "utf8");

const HTML = `<!doctype html><html><body>
<section data-profile-section-panel="workload-distribution">
  <div class="wl" data-wl-root data-rows-url="/ders-yuku/setirler/" data-teachers-url="/ders-yuku/muellimler/" data-focus-row="">
    <input type="search" data-wl-search value="riyazi">
    <p data-wl-all-note hidden></p>
    <p data-wl-count hidden></p>
    <div data-wl-empty hidden></div>
    <div data-wl-nomatch hidden></div>
    <div data-wl-rows></div>
    <div data-wl-more hidden><button type="button" data-wl-load-more>more</button><p data-wl-more-error hidden></p></div>
  </div>
</section></body></html>`;

function setup() {
    const dom = new JSDOM(HTML, { runScripts: "outside-only", url: "http://localhost/accounts/profile/" });
    const win = dom.window;
    const fetched = [];
    const q = (sel) => win.document.querySelector(sel);
    win.EMSDelegate = { on: () => {} };
    win.EMSReady = { once: (_key, fn) => fn() };
    win.EMSCore = { fetchJSON: (url) => { fetched.push(url); return Promise.resolve({ ok: true, results: [] }); } };
    const state = { rows: [], task: null, allChairs: true, rowsSeq: 1 };
    win.EMSWorkloadDist = {
        state,
        q: (sel) => q(sel),
        root: () => q("[data-wl-root]"),
        filters: () => ({ chair: "all", year: "2026/2027", season: "", q: "riyazi" }),
        labels: () => ({ lecture: "Mühazirə" }),
        loadRows: () => {},
    };
    win.eval(RENDER);
    win.eval(LIST);
    return { win, q, state, fetched };
}

function row(id, extra) {
    return Object.assign(
        {
            id,
            subject: "Riyazi analiz " + id,
            season_label: "Payız",
            total_hours: 45,
            teaching_complete: false,
            activities: { lecture: { total: 30, assigned: 30, remaining: 0, is_complete: true } },
            assignments: [{ id: "a" + id, teacher_name: "Kamran", activity_label: "Mühazirə", hours: 30 }],
            chair_id: "c-" + id,
            chair_name: "Kafedra " + id,
            faculty_name: "Fakültə",
            task_status_label: "Təsdiqlənib",
            can_edit: false,
            edit_url: "",
        },
        extra || {}
    );
}

test("applyChairMode kökün sinfini və izah zolağını idarə edir", () => {
    const { win, q } = setup();
    assert.equal(win.EMSWorkloadList.applyChairMode(true), true);
    assert.ok(q("[data-wl-root]").classList.contains("is-all-chairs"));
    assert.equal(q("[data-wl-all-note]").hidden, false);
    assert.equal(win.EMSWorkloadList.applyChairMode(false), false);
    assert.ok(!q("[data-wl-root]").classList.contains("is-all-chairs"));
    assert.equal(q("[data-wl-all-note]").hidden, true);
});

test("kafedralı sətir yalnız oxu kartıdır: kafedra adı, yazı düyməsi yoxdur", () => {
    const { win, q } = setup();
    const editable = row("1", { can_edit: true, edit_url: "/accounts/profile/?section=workload-distribution&chair=c-1&row=1" });
    win.EMSWorkloadRender.rows(q("[data-wl-rows]"), [editable, row("2")], { lecture: "Mühazirə" }, {});
    const cards = win.document.querySelectorAll("[data-wl-row]");
    assert.equal(cards.length, 2);
    assert.match(cards[0].querySelector(".wl-row__chair-name").textContent, /Kafedra 1/);
    assert.match(cards[0].textContent, /Fakültə/);
    for (const selector of ["[data-wl-row-edit]", "[data-wl-row-remove]", "[data-wl-assign-open]", "[data-wl-assign-edit]", "[data-wl-assign-remove]", "[data-wl-activity-remove]"]) {
        assert.equal(win.document.querySelector(selector), null, selector);
    }
    const link = cards[0].querySelector("a.wl-btn");
    assert.equal(link.getAttribute("href"), editable.edit_url);
    assert.equal(cards[1].querySelector("a"), null);
    assert.ok(cards[1].querySelector(".wl-row__readonly"));
});

test("kafedrasız rejimdə boş axtarış «uyğun sətir yoxdur» deyir, müəllim hovuzu soruşulmur", () => {
    const { win, q, fetched } = setup();
    win.EMSWorkloadList.afterLoad({ ok: true, all_chairs: true, rows: [], total: 0, next_offset: 0, has_more: false });
    assert.equal(q("[data-wl-nomatch]").hidden, false);
    assert.equal(q("[data-wl-empty]").hidden, true);
    assert.equal(fetched.length, 0);
});
