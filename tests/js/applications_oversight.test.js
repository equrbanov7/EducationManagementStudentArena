/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-24: «Müraciətlərim → Bütün müraciətlər» (RİM nəzarəti) — şöbə süzgəcləri
   (apps/accounts/static/accounts/js/profile/applications_oversight.js) ƏSL DOM-da (jsdom).
   Süzgəc YALNIZ «all» tabında görünür və sorğuya düşür; seçim siyahını yenidən yükləyir;
   «Sıfırla» vəziyyəti təmizləyir. `NS.api.list` parametrləri `applications_core.js`-də birləşir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const JS = (name) => fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/profile", name), "utf8");

const PANEL =
    '<div data-apx-root><div class="apx-oversight" data-apx-oversight hidden>' +
    '<div data-apx-oversight-field="unit"><select data-apx-oversight-unit>' +
    '<option value="">all</option><option value="dekan">Dekanlıq</option></select></div>' +
    '<div data-apx-oversight-field="sender"><select data-apx-oversight-sender>' +
    '<option value="">all</option><option value="u-1">Fakültə</option></select></div>' +
    "</div></div>";

function page() {
    const dom = new JSDOM("<!doctype html><html><body>" + PANEL + "</body></html>", { runScripts: "outside-only" });
    const window = dom.window;
    window.EMSDelegate = {
        on(type, selector, fn) {
            window.document.addEventListener(type, (event) => {
                const node = event.target.closest(selector);
                if (node) {
                    fn(event, node);
                }
            });
        },
    };
    window.EMSReady = function (fn) {
        fn();
    };
    window.__synced = [];
    window.EMSBootstrapSelect = {
        sync(select) {
            window.__synced.push(select.getAttribute("data-apx-oversight-unit") !== null ? "unit" : "sender");
        },
    };
    window.__urls = [];
    window.__loads = 0;
    window.EMSCore = {
        fetchJSON(url) {
            window.__urls.push(url);
            return Promise.resolve({});
        },
    };
    window.eval(JS("applications_core.js"));
    window.eval(JS("applications_oversight.js"));
    const NS = window.EMSApplications;
    NS.root = window.document.querySelector("[data-apx-root]");
    NS.urls = { list: "/list/" };
    NS.state = { tab: "mine", page: 3 };
    NS.loadList = () => {
        window.__loads += 1;
    };
    return { window, NS };
}

function change(window, selector, value) {
    const node = window.document.querySelector(selector);
    node.value = value;
    node.dispatchEvent(new window.Event("change", { bubbles: true }));
}

test("filters are hidden and never sent outside the «all» tab", () => {
    const { window, NS } = page();
    NS.state.unit = "dekan";
    NS.api.list({ tab: "mine", stat: "open" });
    assert.equal(window.__urls[0], "/list/?tab=mine&stat=open");
    assert.equal(window.document.querySelector("[data-apx-oversight]").hidden, true);
});

test("on the «all» tab the selection is shown and sent with the list request", () => {
    const { window, NS } = page();
    NS.state.tab = "all";
    change(window, "[data-apx-oversight-unit]", "dekan");
    change(window, "[data-apx-oversight-sender]", "u-1");
    assert.equal(window.__loads, 2);
    assert.equal(NS.state.page, 1);
    NS.api.list({ tab: "all", stat: "all" });
    assert.equal(window.__urls[0], "/list/?tab=all&stat=all&unit=dekan&sender_unit=u-1");
    assert.equal(window.document.querySelector("[data-apx-oversight]").hidden, false);
    assert.ok(window.document.querySelector('[data-apx-oversight-field="unit"]').classList.contains("is-active"));
});

test("reset clears both selectors", () => {
    const { window, NS } = page();
    NS.state.tab = "all";
    change(window, "[data-apx-oversight-unit]", "dekan");
    window.__synced = [];
    NS.oversight.reset();
    // Proqramla dəyişən dəyər stilli düymənin etiketinə də ötürülür (yalnız dəyişən seçici).
    assert.deepEqual(window.__synced, ["unit"]);
    assert.equal(NS.state.unit, "");
    assert.equal(NS.state.senderUnit, "");
    assert.equal(window.document.querySelector("[data-apx-oversight-unit]").value, "");
    NS.api.list({ tab: "all" });
    assert.equal(window.__urls[0], "/list/?tab=all");
});
