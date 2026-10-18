/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-19: «Müraciətlər» → «Arayış sorğusu» emalçısına «Arayışı hazırla» bloku
   (apps/accounts/static/accounts/js/profile/applications_arayis.js) ƏSL DOM-da (jsdom).
   Əlavə olunmuş arayışlar siyahısı (kod + yer + link), «Yeni arayış hazırla (başqa yer üçün)» formanı açır,
   göndəriş place sahəsini POST edir və cavabı `applyDetail` ilə tətbiq edir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/profile/applications_arayis.js"), "utf8");

function page() {
    const dom = new JSDOM(
        '<!doctype html><html><body><div data-panel><div class="apx-act">reply</div></div></body></html>',
        { runScripts: "outside-only" }
    );
    const window = dom.window;
    const handlers = [];
    window.EMSDelegate = {
        on(type, selector, fn) {
            handlers.push(selector);
            window.document.addEventListener(type, (event) => {
                const node = event.target.closest(selector);
                if (node) {
                    fn(event, node);
                }
            });
        },
    };
    window.__posts = [];
    window.__applied = [];
    window.EMSCore = {
        fetchJSON(url, options) {
            window.__posts.push({ url, place: options.body.get("place"), method: options.method });
            return Promise.resolve({ application: { id: "a1", arayis_tool: null } });
        },
    };
    window.EMSApplications = {
        current: { id: "a1" },
        csrfToken: () => "tok",
        applyDetail: (app) => window.__applied.push(app),
        errorList: () => ["xəta"],
    };
    window.eval(SCRIPT);
    return { window, handlers };
}

function tool(extra) {
    return Object.assign(
        {
            url: "/muraciet/api/a1/arayis/",
            place_max: 200,
            blocked: "",
            attached: [],
            title: "Təhsil aldığı yer haqqında arayış",
            hint: "hint",
            place_label: "Təqdim ediləcəyi yer",
            place_placeholder: "məs.",
            button: "Arayışı hazırla və əlavə et",
            attached_label: "Arayış əlavə olunub",
            code_label: "Kod",
            open_label: "Arayışı aç",
            again_label: "Yeni arayış hazırla (başqa yer üçün)",
            same_place_hint: "eyni yer",
        },
        extra || {}
    );
}

test("without attachments the form is visible and there is no 'again' button", () => {
    const { window } = page();
    const body = window.document.querySelector("[data-panel]");
    window.EMSApplications.arayis.decorate(body, { arayis_tool: tool() });
    const box = body.querySelector("[data-apx-arayis]");
    assert.ok(box);
    assert.equal(box.nextElementSibling.className, "apx-act"); // cavab qutusundan ƏVVƏL
    assert.equal(body.querySelector("[data-apx-arayis-form]").hidden, false);
    assert.equal(body.querySelector("[data-apx-arayis-again]"), null);
    assert.equal(body.querySelector("[data-apx-arayis-done]"), null);
    window.close();
});

test("attached arayış are all listed; 'again' reveals the hidden form", () => {
    const { window } = page();
    const body = window.document.querySelector("[data-panel]");
    const attached = [
        { code: "QKU-AAAA-BBBB-CCCC-DDDD", place: "Kapital Bank ASC-yə", name: "a.pdf", download_url: "/d/2/" },
        { code: "QKU-EEEE-FFFF-GGGG-HHHH", place: "<b>komissarlığa</b>", name: "b.pdf", download_url: "/d/1/" },
    ];
    window.EMSApplications.arayis.decorate(body, { arayis_tool: tool({ attached }) });
    const items = body.querySelectorAll("[data-apx-arayis-item]");
    assert.equal(items.length, 2);
    assert.match(items[0].textContent, /QKU-AAAA-BBBB-CCCC-DDDD/);
    assert.match(items[0].textContent, /Kapital Bank ASC-yə/);
    assert.equal(items[0].querySelector("a").getAttribute("href"), "/d/2/");
    assert.equal(items[0].querySelector("a").target, "_blank");
    assert.equal(items[1].querySelector("b"), null); // mətn textContent ilə — HTML icra olunmur
    assert.match(body.querySelector("[data-apx-arayis-done]").textContent, /Arayış əlavə olunub/);

    const form = body.querySelector("[data-apx-arayis-form]");
    const again = body.querySelector("[data-apx-arayis-again]");
    assert.equal(form.hidden, true);
    assert.equal(again.textContent, "Yeni arayış hazırla (başqa yer üçün)");
    again.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    assert.equal(form.hidden, false);
    assert.equal(again.hidden, true);
    assert.equal(again.getAttribute("aria-expanded"), "true");
    window.close();
});

test("submit posts the place and applies the returned detail", async () => {
    const { window } = page();
    const body = window.document.querySelector("[data-panel]");
    window.EMSApplications.arayis.decorate(body, { arayis_tool: tool() });
    body.querySelector("[data-apx-arayis-place]").value = "  Bakı şəhər hərbi komissarlığına ";
    body.querySelector("[data-apx-arayis-submit]").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(window.__posts, [
        { url: "/muraciet/api/a1/arayis/", place: "Bakı şəhər hərbi komissarlığına", method: "POST" },
    ]);
    assert.equal(window.__applied.length, 1);
    window.close();
});

test("a refused student shows the message and no form; decorate is idempotent", () => {
    const { window } = page();
    const body = window.document.querySelector("[data-panel]");
    const app = { arayis_tool: tool({ blocked: "Tələbə aktiv deyil" }) };
    window.EMSApplications.arayis.decorate(body, app);
    window.EMSApplications.arayis.decorate(body, app);
    assert.equal(body.querySelectorAll("[data-apx-arayis]").length, 1);
    assert.equal(body.querySelector("[data-apx-arayis-form]"), null);
    assert.match(body.querySelector(".apx-arayis__blocked").textContent, /aktiv deyil/);
    window.EMSApplications.arayis.decorate(body, { arayis_tool: null });
    window.close();
});
