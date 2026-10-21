/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-21: bir bölmənin bir neçə sidebar alt bəndi («Sistem tənzimləmələri» → qruplar) —
   ui.js `updateSidebarActiveState` aktiv bəndi panelin `data-profile-section-sub`-u ilə seçir: eyni
   `data-section`-lı bəndlərdən YALNIZ biri aktivdir; `data-section-sub`-suz adi bəndlər əvvəlki kimi işləyir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const NAMESPACE = read("apps/accounts/static/accounts/js/profile/namespace.js");
const UI = read("apps/accounts/static/accounts/js/profile/ui.js");

function link(section, sub, label) {
    const subAttr = sub === null ? "" : ` data-section-sub="${sub}"`;
    return (
        `<li class="sidebar-menu-item"><a href="#" data-section="${section}"${subAttr} data-title="${label}" ` +
        `class="sidebar-menu-link js-profile-section-link">${label}</a></li>`
    );
}

function load() {
    const html =
        `<!doctype html><html><body><div class="profile-page" data-title-suffix="EMS">` +
        `<aside class="profile-sidebar" id="profileSidebar"><nav><ul class="sidebar-menu">` +
        link("rim-center", null, "RİM") +
        `<li class="sidebar-menu-group"><details class="sidebar-group"><summary>S</summary><ul>` +
        link("system-settings", "overview", "Ümumi baxış") +
        link("system-settings", "login", "Giriş") +
        link("system-settings", "otp", "OTP") +
        `</ul></details></li></ul></nav></aside>` +
        `<h1 id="profileSectionTitle"></h1><div id="profileSectionsContainer"></div></div></body></html>`;
    const dom = new JSDOM(html, { runScripts: "outside-only", url: "http://localhost/accounts/profile/" });
    const win = dom.window;
    win.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {} });
    win.eval(NAMESPACE);
    win.eval(UI);
    const ctx = win.EMSProfile.createContext();
    win.EMSProfile._installers.forEach((installer) => installer(ctx));
    return { win, ctx };
}

function setPanel(win, section, sub) {
    const host = win.document.getElementById("profileSectionsContainer");
    const subAttr = sub === null ? "" : ` data-profile-section-sub="${sub}"`;
    host.innerHTML = `<section data-profile-section-panel="${section}"${subAttr}></section>`;
}

function active(win) {
    return Array.from(win.document.querySelectorAll(".sidebar-menu-link.active")).map(
        (node) => `${node.getAttribute("data-section")}:${node.getAttribute("data-section-sub") || ""}`
    );
}

test("eyni bölmənin alt bəndlərindən yalnız panelə uyğun olanı aktivdir", () => {
    const { win, ctx } = load();
    setPanel(win, "system-settings", "login");
    ctx.updateSidebarActiveState("system-settings");
    assert.deepEqual(active(win), ["system-settings:login"]);
    const current = win.document.querySelector('[aria-current="page"]');
    assert.equal(current.getAttribute("data-section-sub"), "login");

    setPanel(win, "system-settings", "overview");
    ctx.updateSidebarActiveState("system-settings");
    assert.deepEqual(active(win), ["system-settings:overview"]);
    assert.equal(win.document.querySelectorAll('[aria-current="page"]').length, 1);
});

test("alt bəndsiz bölmə əvvəlki kimi aktivləşir və alt bəndləri söndürür", () => {
    const { win, ctx } = load();
    setPanel(win, "system-settings", "otp");
    ctx.updateSidebarActiveState("system-settings");
    setPanel(win, "rim-center", null);
    ctx.updateSidebarActiveState("rim-center");
    assert.deepEqual(active(win), ["rim-center:"]);
    assert.equal(win.document.getElementById("profileSectionTitle").textContent, "RİM");
});
