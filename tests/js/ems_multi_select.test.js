/* ═══════════════════════════════════════════════════════════════════════════
   2026-10-16 (sahib qaydası: «hər yerdə stilli select, uzun siyahıda menyu-daxili axtarış»):
   `static/js/ems_multi_select.js` (EMSMultiSelect) ƏSL DOM-da (jsdom).

   Müqavilə:
     • variant klikləri native `<select multiple>`-in `option.selected`-ini dəyişir və `change` atır;
     • toggle mətni: boş → placeholder, ≤ 2 → adlar, çox → «{count} … seçilib»;
     • menyu-daxili axtarış tolerantdır (EMSSearch: «aliyev» → «Əliyev»), «Hamısı» yalnız görünənləri seçir;
     • proqramla variant əlavəsi (MutationObserver) və `option.selected` + refresh() yenidən sinxronlaşır;
     • workload `Forms.fillRow` / `Render.options` qrupları çoxseçimə yazır;
     • init idempotentdir; klaviatura: ArrowDown açır, Escape bağlayır, Enter axtarışda ilk variantı seçir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const FOLD = read("static/js/search_fold.js");
const BSELECT = read("static/js/bootstrap_select.js");
const MULTI = read("static/js/ems_multi_select.js");
const FORMS = read("apps/accounts/static/accounts/js/profile/workload_distribution_forms.js");
const RENDER = read("apps/accounts/static/accounts/js/profile/workload_distribution_render.js");

function page(selectHtml) {
    const dom = new JSDOM(
        `<!doctype html><html><body><form data-wl-row-form>
           <label class="wl-form__field"><span>Qruplar</span>${selectHtml}</label>
           <select name="period_id"><option value="">—</option></select>
         </form><button id="outside">x</button></body></html>`,
        { runScripts: "outside-only", url: "http://localhost/accounts/profile/" }
    );
    const win = dom.window;
    win.eval(FOLD);
    win.eval(BSELECT);
    win.eval(MULTI);
    win.EMSMultiSelect.init(win.document); // jsdom: DOMContentLoaded hələ gəlməyib — açıq init
    const select = win.document.querySelector("select[multiple]");
    const root = select.nextElementSibling;
    return {
        win,
        doc: win.document,
        select,
        root,
        toggle: root.querySelector(".ems-multi-select__toggle"),
        menu: root.querySelector(".ems-multi-select__menu"),
        search: root.querySelector("input[type=search]"),
        options: () => Array.from(root.querySelectorAll(".ems-multi-select__option")),
        visible: () => Array.from(root.querySelectorAll(".ems-multi-select__option")).filter((b) => !b.hidden),
        picked: () => Array.from(select.selectedOptions).map((o) => o.value),
    };
}

const GROUPS = `<select name="group_ids" multiple data-ems-multi-select
     data-ms-count-format="{count} qrup seçilib">
  <option value="1">631 A1</option><option value="2">632 B1</option>
  <option value="3">Əliyev qrupu</option><option value="4">634 K2</option>
</select>`;

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

function key(win, target, name) {
    const ev = new win.KeyboardEvent("keydown", { key: name, bubbles: true, cancelable: true });
    target.dispatchEvent(ev);
    return ev;
}

test("qoşulma: native gizlənir, toggle/listbox ARIA, init idempotent", () => {
    const p = page(GROUPS);
    assert.ok(p.select.classList.contains("is-enhanced"));
    assert.equal(p.select.getAttribute("aria-hidden"), "true");
    assert.equal(p.toggle.getAttribute("aria-haspopup"), "listbox");
    assert.equal(p.toggle.getAttribute("aria-expanded"), "false");
    const list = p.root.querySelector("[role=listbox]");
    assert.equal(list.getAttribute("aria-multiselectable"), "true");
    assert.equal(list.getAttribute("aria-label"), "Qruplar");
    assert.equal(p.options().length, 4);
    assert.equal(p.toggle.textContent.trim(), "Seçilməyib");
    p.win.EMSMultiSelect.init(p.doc);
    p.win.EMSBootstrapSelect.init(p.doc);
    assert.equal(p.doc.querySelectorAll(".ems-multi-select").length, 1, "təkrar init ikinci qabıq yaratmır");
});

test("seç / çıxar native select-i sinxronlaşdırır və change atır", () => {
    const p = page(GROUPS);
    let changes = 0;
    p.select.addEventListener("change", () => (changes += 1));
    p.toggle.click();
    assert.equal(p.menu.hidden, false);
    assert.equal(p.toggle.getAttribute("aria-expanded"), "true");
    p.options()[0].click();
    p.options()[2].click();
    assert.deepEqual(p.picked(), ["1", "3"]);
    assert.equal(p.options()[0].getAttribute("aria-selected"), "true");
    assert.equal(p.menu.hidden, false, "çoxseçimdə menyu klikdən sonra açıq qalır");
    assert.equal(p.toggle.textContent.trim(), "631 A1, Əliyev qrupu");
    p.options()[1].click();
    assert.equal(p.toggle.textContent.trim(), "3 qrup seçilib");
    p.options()[0].click();
    assert.deepEqual(p.picked(), ["2", "3"]);
    assert.equal(p.options()[0].getAttribute("aria-selected"), "false");
    assert.equal(changes, 4);
    const data = new p.win.FormData(p.doc.querySelector("form"));
    assert.deepEqual(data.getAll("group_ids"), ["2", "3"]);
});

test("axtarış tolerant süzür; «Hamısı» görünənləri, «Təmizlə» hamısını", () => {
    const p = page(GROUPS);
    p.toggle.click();
    p.search.value = "aliyev";
    p.search.dispatchEvent(new p.win.Event("input", { bubbles: true }));
    assert.deepEqual(p.visible().map((b) => b.dataset.value), ["3"]);
    p.search.value = "63";
    p.search.dispatchEvent(new p.win.Event("input", { bubbles: true }));
    assert.deepEqual(p.visible().map((b) => b.dataset.value), ["1", "2", "4"]);
    p.root.querySelector('[data-ms-action="all"]').click();
    assert.deepEqual(p.picked(), ["1", "2", "4"]);
    p.search.value = "zzz";
    p.search.dispatchEvent(new p.win.Event("input", { bubbles: true }));
    assert.equal(p.visible().length, 0);
    assert.equal(p.root.querySelector(".ems-multi-select__empty").hidden, false);
    p.root.querySelector('[data-ms-action="clear"]').click();
    assert.deepEqual(p.picked(), []);
});

test("proqramla variant əlavəsi (MutationObserver) və option.selected + refresh() yenidən sinxronlaşır", async () => {
    const p = page(GROUPS);
    const option = p.doc.createElement("option");
    option.value = "9";
    option.textContent = "Yeni qrup";
    p.select.appendChild(option);
    await flush();
    assert.equal(p.options().length, 5);
    assert.equal(p.options()[4].textContent.trim(), "Yeni qrup");
    option.selected = true; // property — mutasiya vermir
    p.win.EMSMultiSelect.refresh(p.select);
    assert.equal(p.options()[4].getAttribute("aria-selected"), "true");
    assert.equal(p.toggle.textContent.trim(), "Yeni qrup");
    p.select.options[0].selected = true;
    p.win.EMSBootstrapSelect.sync(p.select); // ümumi köməkçi çoxseçimə ötürür
    assert.equal(p.toggle.textContent.trim(), "631 A1, Yeni qrup");
    p.select.innerHTML = '<option value="x">X</option>';
    await flush();
    assert.deepEqual(p.options().map((b) => b.dataset.value), ["x"]);
    assert.equal(p.toggle.textContent.trim(), "Seçilməyib");
});

test("workload: Render.options + Forms.fillRow qrupları çoxseçimə yazır", () => {
    const p = page('<select name="group_ids" multiple data-wl-option="groups" data-ems-multi-select></select>');
    p.win.eval(RENDER);
    p.win.eval(FORMS);
    p.win.EMSWorkloadRender.options(p.select, [
        { id: 1, name: "631 A1" },
        { id: 2, name: "632 B1" },
    ]);
    assert.equal(p.options().length, 2);
    const form = p.doc.querySelector("form");
    p.win.EMSWorkloadForms.fillRow(form, { id: 5, groups: [{ id: 2, name: "632 B1" }, { id: 7, name: "Başqa kafedra" }] });
    assert.deepEqual(p.picked(), ["2", "7"]);
    assert.equal(p.options().length, 3, "siyahıda olmayan qrup variant kimi əlavə olunur");
    assert.equal(p.toggle.textContent.trim(), "632 B1, Başqa kafedra");
    assert.deepEqual(Array.from(p.win.EMSWorkloadForms.values(form).group_ids), ["2", "7"]);
    p.win.EMSWorkloadForms.fillRow(form, null);
    assert.deepEqual(p.picked(), []);
    assert.equal(p.toggle.textContent.trim(), "Seçilməyib");
});

test("klaviatura: ArrowDown açır, Enter axtarışda ilk variantı seçir, Escape bağlayıb fokusu qaytarır", () => {
    const p = page(GROUPS.replace("data-ems-multi-select", 'data-ems-multi-select data-ms-search="true"'));
    p.toggle.focus();
    key(p.win, p.toggle, "ArrowDown");
    assert.equal(p.menu.hidden, false);
    assert.equal(p.doc.activeElement, p.search);
    p.search.value = "634";
    p.search.dispatchEvent(new p.win.Event("input", { bubbles: true }));
    const enter = key(p.win, p.search, "Enter");
    assert.equal(enter.defaultPrevented, true, "Enter formanı göndərmir");
    assert.deepEqual(p.picked(), ["4"]);
    key(p.win, p.search, "ArrowDown");
    assert.equal(p.doc.activeElement, p.visible()[0]);
    const esc = key(p.win, p.doc.activeElement, "Escape");
    assert.equal(esc.defaultPrevented, true);
    assert.equal(p.menu.hidden, true);
    assert.equal(p.doc.activeElement, p.toggle);
});

test("xarici klik menyunu bağlayır; az variantda axtarış gizlidir", () => {
    const p = page(GROUPS);
    assert.equal(p.search.hidden, true, "4 variant < 8 həddi → axtarış yoxdur");
    p.toggle.click();
    p.doc.getElementById("outside").dispatchEvent(new p.win.MouseEvent("mousedown", { bubbles: true }));
    assert.equal(p.menu.hidden, true);
    assert.equal(p.toggle.getAttribute("aria-expanded"), "false");
});

test("2026-10-29: toggle-da yazılan hərf menyunu açır və axtarışa düşür; variantda hərf → axtarış", () => {
    const p = page(GROUPS.replace("data-ems-multi-select", 'data-ems-multi-select data-ms-search="true"'));
    p.toggle.focus();
    key(p.win, p.toggle, "6");
    assert.equal(p.menu.hidden, false);
    assert.equal(p.doc.activeElement, p.search);
    assert.equal(p.search.value, "6", "ilk hərf sorğuya köçürülür");
    assert.deepEqual(p.visible().map((b) => b.dataset.value), ["1", "2", "4"]);
    key(p.win, p.search, "ArrowDown");
    assert.ok(p.doc.activeElement.classList.contains("ems-multi-select__option"));
    key(p.win, p.doc.activeElement, "k");
    assert.equal(p.doc.activeElement, p.search);
    assert.equal(p.search.value, "6k", "variant düyməsində yazılan hərf də köçürülür");
    p.search.value = "Aliyev";
    p.search.dispatchEvent(new p.win.Event("input", { bubbles: true }));
    assert.deepEqual(p.visible().map((b) => b.dataset.value), ["3"]);
});
