/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-10: «AI buttonu gizlətmə, yerini dəyişmək və s. də olsun — bəzən hansısa
   button üstündə dayana bilir, user onun yerini tutaraq dəyişə bilsin».

   static/js/ai_assistant_fab.js + static/js/ai_assistant.js ƏSL DOM-da (jsdom), ƏSL
   şablon markup-ı ilə (templates/partials/_ai_assistant.html + navbar açarı — Django
   teqləri sadəcə açılır). Yoxlanılır: sürüşdürmə həddi və klik, yan kənara yapışma,
   ekran daxilində sıxma, gizlət/qaytar (nişan, menyu, bildiriş), saxlama, klaviatura.
   jsdom-da layout yoxdur: pəncərə 1024×768, düymə 56px, sağ-altda (left 946, top 690),
   yapışqan başlıq 64px.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const FAB_JS = read("static/js/ai_assistant_fab.js");
const MAIN_JS = read("static/js/ai_assistant.js");
const TOAST_JS = read("static/js/toast.js");
const PARTIAL = read("templates/partials/_ai_assistant.html");
const NAV_ITEM = read("templates/partials/_navbar.html").match(/<button[^>]*data-ai-fab-toggle[\s\S]*?<\/button>/)[0];
const PREF_KEY = "ems.aiFab.v1:7";

/** Django şablon sintaksisini açır — yalnız bu partial-lar üçün kifayətdir. */
function renderDjango(source) {
    return source
        .replace(/\{% comment %\}[\s\S]*?\{% endcomment %\}/g, "")
        .replace(/\{#[\s\S]*?#\}/g, "")
        .replace(/\{% (?:trans|translate) (["'])(.*?)\1[^%]*%\}/g, "$2")
        .replace(/\{% blocktrans[^%]*%\}([\s\S]*?)\{% endblocktrans %\}/g, "$1")
        .replace(/\{% url [^%]*%\}/g, "/api/ai-assistant/x/")
        .replace(/\{\{ user\.id \}\}/g, "7")
        .replace(/\{\{[^}]*\}\}/g, "")
        .replace(/\{%[^%]*%\}/g, "");
}

function rectOf(box) {
    return Object.assign({ x: box.left, y: box.top, right: box.left + box.width, bottom: box.top + box.height }, box);
}

async function page(options) {
    const opts = options || {};
    const html =
        "<!doctype html><html><body>" +
        '<header class="blog-header" style="position: sticky; top: 0"></header>' +
        '<div class="blog-header__user-menu blog-header__user-menu--open">' + renderDjango(NAV_ITEM) + "</div>" +
        renderDjango(PARTIAL) +
        "</body></html>";
    const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/accounts/profile/" });
    const { window } = dom;
    const doc = window.document;
    // Real səhifədəki kimi: skriptlər DOM hazır olandan sonra (toast.js bağlamalarını dərhal qursun).
    if (doc.readyState === "loading") {
        await new Promise((resolve) => doc.addEventListener("DOMContentLoaded", resolve));
    }
    // jsdom 24-də PointerEvent yoxdur — MouseEvent üzərində minimal əvəz.
    window.eval(
        "window.PointerEvent = class PointerEvent extends MouseEvent {" +
            " constructor(type, init) { super(type, init); this.pointerId = (init && init.pointerId) || 1;" +
            " this.pointerType = (init && init.pointerType) || 'mouse'; } };"
    );
    if (opts.stored !== undefined) window.localStorage.setItem(PREF_KEY, opts.stored);
    if (opts.blockStorage) {
        window.eval("Object.defineProperty(window, 'localStorage', { configurable: true, get() { throw new Error('denied'); } })");
    }
    if (opts.phone) {
        window.matchMedia = (query) => ({ matches: true, media: query, addEventListener() {} });
        Object.defineProperty(doc.documentElement, "scrollHeight", { configurable: true, value: 5000 });
        Object.defineProperty(doc.documentElement, "scrollTop", { configurable: true, writable: true, value: 0 });
    }
    // 6 s-lik «diqqət çəkmə» taymerini tutub əl ilə işlədirik (gözləmədən).
    const teaser = [];
    const realSetTimeout = window.setTimeout.bind(window);
    window.setTimeout = (fn, ms) => (ms === 6000 ? (teaser.push(fn), 0) : realSetTimeout(fn, ms));
    const popovers = [];
    doc.addEventListener("ems:popover:open", (event) => popovers.push(event.detail && event.detail.source));

    const btn = doc.getElementById("ai-bot-btn");
    let box = { left: 946, top: 690, width: 56, height: 56 };
    btn.getBoundingClientRect = () => rectOf(box);
    doc.querySelector(".blog-header").getBoundingClientRect = () => rectOf({ left: 0, top: 0, width: 1024, height: 64 });

    window.eval(TOAST_JS);
    if (!opts.withoutFab) window.eval(FAB_JS);
    window.eval(MAIN_JS);
    return {
        window,
        doc,
        btn,
        root: doc.getElementById("ai-fab"),
        panel: doc.getElementById("ai-chat-panel"),
        restore: doc.getElementById("ai-fab-restore"),
        live: doc.getElementById("ai-fab-live"),
        menuItem: doc.querySelector("[data-ai-fab-toggle]"),
        teaser,
        popovers,
        setBox: (next) => { box = next; },
        stored: () => JSON.parse(window.localStorage.getItem(PREF_KEY) || "null"),
        fabY: () => doc.getElementById("ai-fab").style.getPropertyValue("--ai-fab-y"),
    };
}

function pointer(p, type, x, y, target, init) {
    const event = new p.window.PointerEvent(type, Object.assign({ bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 }, init));
    (target || p.btn).dispatchEvent(event);
    return event;
}
function click(p, target) {
    (target || p.btn).dispatchEvent(new p.window.MouseEvent("click", { bubbles: true, cancelable: true }));
}
function key(p, name, init, target) {
    const event = new p.window.KeyboardEvent("keydown", Object.assign({ key: name, bubbles: true, cancelable: true }, init));
    (target || p.btn).dispatchEvent(event);
    return event;
}
function drag(p, from, to) {
    pointer(p, "pointerdown", from[0], from[1]);
    pointer(p, "pointermove", to[0], to[1]);
    pointer(p, "pointerup", to[0], to[1]);
}
const nextFrame = (window) => new Promise((resolve) => window.requestAnimationFrame(() => resolve()));

test("a press without movement — or under the 6 px threshold — is a click: the panel opens", async () => {
    for (const offset of [0, 3]) {
        const p = await page();
        try {
            assert.ok(p.root.classList.contains("ai-fab--ready"));
            pointer(p, "pointerdown", 970, 710);
            pointer(p, "pointermove", 970 + offset, 710 + offset);
            pointer(p, "pointerup", 970 + offset, 710 + offset);
            click(p);
            assert.equal(p.panel.hidden, false, "panel opened");
            assert.equal(p.btn.getAttribute("aria-expanded"), "true");
            assert.equal(p.root.classList.contains("ai-fab--dragging"), false);
            assert.equal(p.stored(), null, "nothing saved for a click");
        } finally {
            p.window.close();
        }
    }
});

test("dragging past the threshold follows the pointer, snaps to the nearest side and swallows the click", async () => {
    const p = await page();
    try {
        pointer(p, "pointerdown", 970, 710);
        pointer(p, "pointermove", 100, 300);
        assert.ok(p.root.classList.contains("ai-fab--dragging"));
        assert.equal(p.root.style.getPropertyValue("--ai-fab-x"), "76px");
        assert.equal(p.fabY(), "280px");
        pointer(p, "pointerup", 100, 300);
        click(p); // brauzer buraxmadan sonra click göndərir — panel açılmamalıdır
        assert.equal(p.panel.hidden, true, "click after a drag does not open the panel");
        assert.ok(p.root.classList.contains("ai-fab--left"));
        assert.ok(p.root.classList.contains("ai-fab--placed"));
        assert.equal(p.root.classList.contains("ai-fab--dragging"), false);
        assert.equal(p.root.style.getPropertyValue("--ai-fab-x"), "");
        assert.equal(p.fabY(), "280px");
        assert.deepEqual(p.stored(), { hidden: false, side: "left", y: 0.401 });
        assert.equal(p.live.textContent, "AI köməkçi sol kənara köçürüldü");
        // Növbəti adi klik yenə paneli açır.
        click(p);
        assert.equal(p.panel.hidden, false);
    } finally {
        p.window.close();
    }
});

test("a drop is clamped below the sticky header and above the bottom edge", async () => {
    const p = await page();
    try {
        drag(p, [970, 710], [990, -200]);
        assert.equal(p.fabY(), "76px", "64px header + 12px margin");
        assert.ok(p.root.classList.contains("ai-fab--right"));
        assert.equal(p.stored().side, "right");
        assert.equal(p.stored().y, Math.round(((76 + 28) / 768) * 1000) / 1000);
        p.setBox({ left: 946, top: 76, width: 56, height: 56 });
        drag(p, [970, 100], [960, 2000]);
        assert.equal(p.fabY(), "700px", "768 - 12 margin - 56 button");
    } finally {
        p.window.close();
    }
});

test("keyboard: Alt+←/→ switch side, Alt+↑/↓ move by 10 % and announce; plain arrows do nothing", async () => {
    const p = await page();
    try {
        p.btn.focus();
        assert.equal(key(p, "ArrowLeft").defaultPrevented, false);
        assert.equal(p.stored(), null);
        const left = key(p, "ArrowLeft", { altKey: true });
        assert.equal(left.defaultPrevented, true, "Alt+← must not navigate back");
        assert.deepEqual(p.stored(), { hidden: false, side: "left", y: 0.935 });
        assert.equal(p.live.textContent, "AI köməkçi sol kənara köçürüldü");
        key(p, "ArrowUp", { altKey: true });
        assert.equal(p.stored().y, 0.835);
        assert.equal(p.fabY(), "613px");
        assert.equal(p.live.textContent, "AI köməkçi yuxarı çəkildi");
        key(p, "ArrowDown", { altKey: true });
        key(p, "ArrowDown", { altKey: true });
        assert.equal(p.fabY(), "700px", "cannot leave the viewport");
        assert.equal(p.live.textContent.trim(), "AI köməkçi aşağı endirildi");
        key(p, "ArrowRight", { altKey: true });
        assert.equal(p.stored().side, "right");
        assert.ok(p.root.classList.contains("ai-fab--right"));
        assert.equal(p.btn.getAttribute("aria-describedby"), "ai-fab-hint");
        assert.ok(p.doc.getElementById("ai-fab-hint").textContent.includes("Alt"));
    } finally {
        p.window.close();
    }
});

test("the corner × hides the button (no panel), shows the restore tab and offers undo", async () => {
    const p = await page();
    try {
        assert.equal(p.restore.hidden, true);
        click(p, p.btn.querySelector("[data-ai-fab-hide]"));
        assert.equal(p.panel.hidden, true, "× does not open the panel");
        assert.equal(p.btn.hidden, true);
        assert.equal(p.restore.hidden, false);
        assert.ok(p.root.classList.contains("ai-fab--hidden"));
        assert.equal(p.stored().hidden, true);
        assert.equal(p.menuItem.getAttribute("aria-checked"), "false");
        const toast = p.doc.querySelector(".toast-container [data-toast-item]");
        assert.ok(toast, "toast shown");
        assert.match(toast.textContent, /AI köməkçi gizlədildi/);
        // «Geri qaytar» düyməni qaytarır, fokusu ona verir, bildirişi bağlayır.
        toast.querySelector(".ai-fab-undo").dispatchEvent(new p.window.MouseEvent("click", { bubbles: true }));
        assert.equal(p.btn.hidden, false);
        assert.equal(p.restore.hidden, true);
        assert.equal(p.doc.activeElement, p.btn);
        assert.equal(toast.dataset.dismissing, "1");
        assert.equal(p.stored().hidden, false);
    } finally {
        p.window.close();
    }
});

test("the restore tab brings the button back on its saved side and focuses it", async () => {
    const p = await page({ stored: JSON.stringify({ hidden: true, side: "left", y: 0.5 }) });
    try {
        assert.equal(p.btn.hidden, true);
        assert.equal(p.restore.hidden, false);
        assert.ok(p.root.classList.contains("ai-fab--left"));
        assert.equal(p.restore.getAttribute("aria-label"), "AI köməkçini göstər");
        assert.equal(p.root.style.getPropertyValue("--ai-fab-tab-y"), "336px", "tab centred on the saved height");
        click(p, p.restore);
        assert.equal(p.btn.hidden, false);
        assert.equal(p.restore.hidden, true);
        assert.equal(p.doc.activeElement, p.btn);
        assert.ok(p.popovers.includes("ai-assistant"), "open header menus are closed first");
        assert.deepEqual(p.stored(), { hidden: false, side: "left", y: 0.5 });
        assert.equal(p.fabY(), "356px");
    } finally {
        p.window.close();
    }
});

test("panel «Gizlət» closes the panel, hides the button and moves focus to the restore tab", async () => {
    const p = await page();
    try {
        const hideBtn = p.doc.getElementById("ai-chat-hide");
        assert.equal(hideBtn.hidden, false, "enabled by the script");
        click(p);
        assert.equal(p.panel.hidden, false);
        hideBtn.focus();
        click(p, hideBtn);
        assert.equal(p.btn.getAttribute("aria-expanded"), "false", "panel closed");
        assert.equal(p.btn.hidden, true);
        assert.equal(p.doc.activeElement, p.restore);
    } finally {
        p.window.close();
    }
});

test("the user-menu switch is enabled by the script and toggles the button both ways", async () => {
    const p = await page();
    try {
        assert.equal(p.menuItem.hidden, false);
        assert.equal(p.menuItem.getAttribute("role"), "switch");
        assert.equal(p.menuItem.getAttribute("aria-checked"), "true");
        p.menuItem.focus();
        click(p, p.menuItem);
        assert.equal(p.btn.hidden, true);
        assert.equal(p.menuItem.getAttribute("aria-checked"), "false");
        assert.equal(p.doc.activeElement, p.menuItem, "hiding keeps focus in the menu");
        click(p, p.menuItem);
        assert.equal(p.btn.hidden, false);
        assert.equal(p.menuItem.getAttribute("aria-checked"), "true");
        assert.equal(p.doc.activeElement, p.btn, "restoring moves focus to the button");
        assert.ok(p.popovers.includes("ai-assistant"));
    } finally {
        p.window.close();
    }
});

test("Delete hides the focused button; Escape cancels a drag in progress", async () => {
    const p = await page({ stored: JSON.stringify({ hidden: false, side: "right", y: 0.5 }) });
    try {
        pointer(p, "pointerdown", 970, 380);
        pointer(p, "pointermove", 200, 100);
        assert.ok(p.root.classList.contains("ai-fab--dragging"));
        key(p, "Escape", {}, p.doc);
        assert.equal(p.root.classList.contains("ai-fab--dragging"), false);
        assert.equal(p.fabY(), "356px", "back to the saved place");
        assert.deepEqual(p.stored(), { hidden: false, side: "right", y: 0.5 });
        pointer(p, "pointerup", 200, 100); // gec gələn buraxma heç nə etmir
        assert.deepEqual(p.stored(), { hidden: false, side: "right", y: 0.5 });

        p.btn.focus();
        assert.equal(key(p, "Delete").defaultPrevented, true);
        assert.equal(p.btn.hidden, true);
        assert.equal(p.doc.activeElement, p.restore);
    } finally {
        p.window.close();
    }
});

test("saved preferences are applied on load and re-clamped when the window resizes", async () => {
    const p = await page({ stored: JSON.stringify({ hidden: false, side: "left", y: 0.95 }) });
    try {
        assert.ok(p.root.classList.contains("ai-fab--left"));
        assert.ok(p.root.classList.contains("ai-fab--placed"));
        assert.equal(p.fabY(), "700px");
        p.window.innerHeight = 400;
        p.window.dispatchEvent(new p.window.Event("resize"));
        await nextFrame(p.window);
        await nextFrame(p.window);
        assert.equal(p.fabY(), "332px", "400 - 12 - 56");
    } finally {
        p.window.close();
    }
});

test("another tab's change is applied through the storage event", async () => {
    const p = await page();
    try {
        p.window.localStorage.setItem(PREF_KEY, JSON.stringify({ hidden: true, side: "right", y: null }));
        p.window.dispatchEvent(new p.window.StorageEvent("storage", { key: PREF_KEY }));
        assert.equal(p.btn.hidden, true);
        assert.equal(p.restore.hidden, false);
    } finally {
        p.window.close();
    }
});

test("corrupt or blocked storage falls back to the default corner and hiding still works", async () => {
    for (const opts of [{ stored: "{not json" }, { stored: JSON.stringify({ side: "top", y: "x", hidden: "yes" }) }, { blockStorage: true }]) {
        const p = await page(opts);
        try {
            assert.equal(p.btn.hidden, false);
            assert.ok(p.root.classList.contains("ai-fab--right"));
            assert.equal(p.root.classList.contains("ai-fab--placed"), false);
            assert.equal(p.fabY(), "");
            click(p, p.menuItem);
            assert.equal(p.btn.hidden, true, "in-memory state still works");
        } finally {
            p.window.close();
        }
    }
});

test("while hidden the attention teaser and the phone tuck are skipped", async () => {
    const hidden = await page({ stored: JSON.stringify({ hidden: true, side: "right", y: null }), phone: true });
    const visible = await page({ phone: true });
    try {
        const tip = (p) => p.doc.getElementById("ai-bot-tooltip").classList.contains("ai-bot-tooltip--visible");
        for (const p of [hidden, visible]) p.teaser.forEach((fn) => fn());
        assert.equal(tip(hidden), false);
        assert.equal(tip(visible), true, "harness sanity: the teaser runs for a visible button");
        for (const p of [hidden, visible]) {
            p.doc.documentElement.scrollTop = 600;
            p.window.dispatchEvent(new p.window.Event("scroll"));
            await nextFrame(p.window);
            await nextFrame(p.window);
        }
        assert.equal(hidden.btn.classList.contains("ai-bot-btn--tucked"), false);
        assert.equal(visible.btn.classList.contains("ai-bot-btn--tucked"), true, "harness sanity: tuck runs");
    } finally {
        hidden.window.close();
        visible.window.close();
    }
});

test("without the fab module the widget still works and becomes visible", async () => {
    const p = await page({ withoutFab: true });
    try {
        assert.ok(p.root.classList.contains("ai-fab--ready"));
        assert.equal(p.menuItem.hidden, true, "switch stays hidden without its script");
        assert.equal(p.doc.getElementById("ai-chat-hide").hidden, true);
        click(p);
        assert.equal(p.panel.hidden, false);
    } finally {
        p.window.close();
    }
});
