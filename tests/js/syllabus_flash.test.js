/* ═══════════════════════════════════════════════════════════════════════════
   Sillabus siyahısı — bir dəfəlik FLASH (2026-10-08): əməldən sonra bölmə AJAX
   ilə yenidən yüklənir və toast qovşağı köhnə panellə silinir; mesaj
   sessionStorage-dan YENİ panelin toast-ında bir dəfə göstərilməlidir.

   Göndərilən fayllar OLDUĞU KİMİ icra olunur:
     static/js/ems_ajax_init.js                          — EMSReady / EMSDelegate
     apps/accounts/static/accounts/js/profile/syllabus_list.js
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const INIT = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const LIST = fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/profile/syllabus_list.js"), "utf8");

const PANEL =
    '<div class="syl" data-syllabus-list data-profile-url="/accounts/profile/">' +
    '<div class="syl-toast" data-syl-toast hidden><span data-syl-toast-text></span></div></div>';

async function makeWindow() {
    const dom = new JSDOM(
        '<!doctype html><html><body><section data-profile-section-panel="syllabus-list">' +
            PANEL +
            "</section></body></html>",
        { runScripts: "outside-only", url: "http://localhost/accounts/profile/?section=syllabus-list" }
    );
    const { window } = dom;
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    window.eval(INIT);
    window.eval(LIST);
    return window;
}

/* section_loader.js ilə eyni: panelin içi əvəzlənir, sonra hadisə buraxılır. */
function swapList(window) {
    const panel = window.document.querySelector("[data-profile-section-panel='syllabus-list']");
    panel.innerHTML = PANEL;
    window.document.dispatchEvent(
        new window.CustomEvent("profile:section:loaded", { detail: { section: "syllabus-list", panel: panel } })
    );
    return panel;
}

test("flash survives the section reload and is shown exactly once", async () => {
    const window = await makeWindow();
    try {
        window.EMSSyllabusList.flash("syllabus-list", "Sillabus bağlandı");
        const panel = swapList(window);
        const toast = panel.querySelector("[data-syl-toast]");
        assert.equal(toast.hidden, false);
        assert.equal(panel.querySelector("[data-syl-toast-text]").textContent, "Sillabus bağlandı");
        assert.equal(window.sessionStorage.getItem("ems.syllabus.flash"), null);

        const again = swapList(window);
        assert.equal(again.querySelector("[data-syl-toast]").hidden, true);
    } finally {
        window.close();
    }
});

test("a flash for another section waits and a stale flash is dropped", async () => {
    const window = await makeWindow();
    try {
        window.EMSSyllabusList.flash("syllabus-editor", "Qaralama açıldı");
        const panel = swapList(window);
        assert.equal(panel.querySelector("[data-syl-toast]").hidden, true);
        assert.notEqual(window.sessionStorage.getItem("ems.syllabus.flash"), null);

        window.sessionStorage.setItem(
            "ems.syllabus.flash",
            JSON.stringify({ section: "syllabus-list", message: "köhnə", at: Date.now() - 120000 })
        );
        const stale = swapList(window);
        assert.equal(stale.querySelector("[data-syl-toast]").hidden, true);
        assert.equal(window.sessionStorage.getItem("ems.syllabus.flash"), null);
    } finally {
        window.close();
    }
});

test("blocked storage never breaks the list", async () => {
    const window = await makeWindow();
    try {
        Object.defineProperty(window, "sessionStorage", {
            configurable: true,
            get() {
                throw new window.DOMException("blocked", "SecurityError");
            },
        });
        assert.doesNotThrow(() => window.EMSSyllabusList.flash("syllabus-list", "x"));
        const panel = swapList(window);
        assert.equal(panel.querySelector("[data-syl-toast]").hidden, true);
    } finally {
        window.close();
    }
});
