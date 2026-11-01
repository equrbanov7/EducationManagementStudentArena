"use strict";
const test = require("node:test"), assert = require("node:assert/strict"), fs = require("node:fs"), path = require("node:path");
const { JSDOM } = require("jsdom");
const base = path.resolve(__dirname, "../../apps/accounts/static/accounts");
const read = name => fs.readFileSync(path.join(base, "js/profile", name), "utf8");
function setup() {
    const dom = new JSDOM("<main></main>", { runScripts: "outside-only" });
    dom.window.eval(read("applications_core.js"));
    dom.window.eval(read("applications_requester.js"));
    return dom;
}
const person = { full_name: "Səbinə Məmmədova Natiq", username: "sebine.memmedova.2", position: "Baş laborant", roles: ["Laborant"],
    chairs: ["Təbiət elmləri kafedrası"], schools: ["İnnovativ məktəb"], units: ["Təbiət elmləri kafedrası", "İnnovativ məktəb"] };

test("requester card shows full name username actual position chair and school without duplicate units", () => {
    const dom = setup(), w = dom.window;
    w.document.querySelector("main").innerHTML = w.EMSApplications.requesterHTML(person, "old scope");
    const card = w.document.querySelector(".apx-person");
    assert.equal(card.querySelector("strong").textContent, person.full_name);
    assert.match(card.textContent, /@sebine.memmedova.2/);
    assert.match(card.textContent, /Baş laborant/);
    assert.equal(card.textContent.split("Təbiət elmləri kafedrası").length, 2);
    assert.match(card.textContent, /İnnovativ məktəb/);
    dom.window.close();
});

test("all sender fields are escaped; missing metadata has safe fallback", () => {
    const dom = setup(), w = dom.window;
    w.document.querySelector("main").innerHTML = w.EMSApplications.requesterHTML({ full_name: "<img src=x onerror=alert(1)>",
        username: "<script>", position: "<b>Job</b>", units: ["<iframe>"] });
    assert.equal(w.document.querySelector("img, script, iframe, b"), null);
    assert.match(w.document.querySelector("main").textContent, /<img/);
    assert.match(w.EMSApplications.requesterHTML({ name: "Known" }, "Original scope"), /Original scope/);
    dom.window.close();
});

test("detail header and original sender message both carry full sender metadata and mobile wraps it", () => {
    const dom = setup(), w = dom.window, ns = w.EMSApplications;
    ns.i18n = {}; ns.rules = {};
    w.eval(read("applications_thread.js"));
    const app = { number: "MR-1", subject: "Load", body: "Content", submitted_at: "2026-10-30", requester: person,
        requester_scope: "Old scope", kind: {}, status: {}, current_unit: {}, events: [], allowed_actions: [], viewer: {} };
    w.document.querySelector("main").innerHTML = ns.thread.html(app, {});
    assert.equal(w.document.querySelector(".apx-modal__head .apx-person__name").textContent, person.full_name);
    assert.match(w.document.querySelector(".apx-msg").textContent, /sebine.memmedova.2/);
    assert.match(w.document.querySelector(".apx-msg").textContent, /İnnovativ məktəb/);
    const css = fs.readFileSync(path.join(base, "css/profile/applications_requester.css"), "utf8");
    assert.match(css, /overflow-wrap:\s*anywhere/);
    assert.match(css, /white-space:\s*normal/);
    assert.match(css, /max-width:\s*640px/);
    dom.window.close();
});


test("compact identity has separate account/job units without losing full name", () => {
    const dom = setup(), w = dom.window;
    w.document.querySelector("main").innerHTML = w.EMSApplications.requesterHTML(person);
    assert.equal(w.document.querySelector(".apx-person__account").textContent, "@" + person.username);
    assert.match(w.document.querySelector(".apx-person__job").textContent, /Baş laborant/);
    assert.match(w.document.querySelector(".apx-person__units").textContent, /İnnovativ məktəb/);
    dom.window.close();
});

test("opening a request prioritizes messages; folding the composer keeps draft and dirty-close protection", () => {
    const dom = setup(), w = dom.window, ns = w.EMSApplications;
    ns.i18n = {}; ns.rules = { note: 10 }; ns.api = {}; w.EMSDelegate = { on() {} };
    let confirmations = 0;
    ns.dialogs = { confirm() { confirmations++; } };
    ns.root = w.document.querySelector("main");
    ns.root.innerHTML = '<div data-apx-detail><section data-apx-modal-panel></section></div>';
    w.eval(read("applications_content.js"));
    w.eval(read("applications_thread.js"));
    const app = { number: "MR-1", subject: "Load", body: "Original message", submitted_at: "2026-10-30",
        requester: person, kind: {}, status: {}, current_unit: {}, events: [],
        allowed_actions: ["resolve", "forward"], content_actions: { can_delete: true }, viewer: {}, is_open: true };
    const panel = ns.root.querySelector("[data-apx-modal-panel]");
    panel.innerHTML = ns.thread.html(app, { resolve: { min: "note", files: true } });
    const editor = panel.querySelector("details.apx-composer");
    assert.ok(editor);
    assert.equal(editor.open, false);
    assert.match(panel.querySelector("[data-apx-modal-body]").textContent, /Original message/);
    assert.ok(panel.querySelector("[data-apx-modal-body] .apx-content-tools"));
    editor.open = true;
    const field = editor.querySelector("[data-apx-reply]");
    field.value = "Unsent draft, preserve this";
    editor.open = false;
    w.eval(read("applications_detail.js"));
    assert.equal(ns.detail.isDirty(), true);
    assert.equal(ns.detail.requestClose(), true);
    assert.equal(confirmations, 1);
    assert.equal(field.value, "Unsent draft, preserve this");
    assert.equal(ns.root.querySelector("[data-apx-detail]").hidden, false);
    dom.window.close();
});
