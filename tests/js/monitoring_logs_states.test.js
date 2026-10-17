/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-17: «Sistem monitorinqində loglar boş göstərir». «Loglar» tabı
   (system_monitoring.js → system_monitoring_renderers.js) ƏSL DOM-da, fetch saxta:
   Loki xətası «Log mənbəyinə qoşulmaq olmadı: <səbəb>» (HTTP status/timeout/bağlantı)
   kimi göstərilir — ümumi «məlumat yoxdur» deyil; boş nəticə «Son <aralıq> ərzində …»
   + LogQL sorğusunu adlandırır; Loki heç bir axın tanımırsa promtail ipucu çıxır;
   sətirlər cədvəldə; filtr zolağı hər vəziyyətdə qalır; hücumçu mətni escape olunur.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const DIR = path.join(ROOT, "apps/accounts/static/accounts/js/monitoring");
const FORMAT = fs.readFileSync(path.join(DIR, "system_monitoring_format.js"), "utf8");
const RENDERERS = fs.readFileSync(path.join(DIR, "system_monitoring_renderers.js"), "utf8");
const MAIN = fs.readFileSync(path.join(DIR, "system_monitoring.js"), "utf8");
const ISLAND_TEMPLATE = fs.readFileSync(
    path.join(ROOT, "apps/accounts/templates/accounts/profile/sections/superadmin/_system_monitoring_i18n.html"),
    "utf8"
);

// Şablondakı az msgid-lər (tərcümə yoxdursa göstərilən mətn) — açarlar adada olmalıdır.
function islandTexts() {
    const texts = {};
    const re = /"(\w+)": "\{% filter escapejs %\}\{% trans '([^']*)' context 'monitoring\.ui' %\}/g;
    let match;
    while ((match = re.exec(ISLAND_TEMPLATE))) texts[match[1]] = match[2];
    return texts;
}

const TEXTS = islandTexts();

function setup(payload) {
    const html = `<!doctype html><html><body>
      <section data-profile-section-panel="system-monitoring">
        <div id="smx-root" data-api-base="/api/superadmin/monitoring/" data-csrf="x">
          <select id="smx-range"><option value="900">15 dəq</option><option value="3600" selected>1 saat</option>
            <option value="604800">7 gün</option></select>
          <input type="checkbox" id="smx-auto" checked><button id="smx-refresh"></button><span id="smx-updated"></span>
          <button class="smx-tab active" data-tab="summary"></button><button class="smx-tab" data-tab="logs"></button>
          <div id="smx-degraded" hidden><span id="smx-degraded-text"></span></div>
          <div id="smx-body"></div>
        </div>
        <script id="smx-i18n" type="application/json">${JSON.stringify(TEXTS)}</script>
      </section></body></html>`;
    const dom = new JSDOM(html, { runScripts: "outside-only", url: "http://localhost/accounts/profile/" });
    const window = dom.window;
    const requests = [];
    window.gettext = (text) => text;
    window.interpolate = (text, values) => String(text).replace(/%\((\w+)\)s/g, (m, name) => values[name]);
    window.fetch = (url) => {
        requests.push(String(url));
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) });
    };
    window.EMSSystemMonitoring = { pendingRoots: [window.document.getElementById("smx-root")] };
    window.eval(FORMAT);
    window.eval(RENDERERS);
    window.eval(MAIN);
    const body = window.document.getElementById("smx-body");
    return { window, body, requests };
}

async function openLogs(payload) {
    const ctx = setup(payload);
    ctx.window.document.querySelector('.smx-tab[data-tab="logs"]').click();
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setImmediate(resolve));
    return ctx;
}

function degraded(error, query) {
    return {
        status: "degraded",
        service: "loki",
        message: "Log servisi müvəqqəti əlçatmazdır",
        last_successful_update: null,
        error,
        query: query || { logql: '{job="docker"}', range_seconds: 3600 },
    };
}

function ok(data) {
    return {
        status: "ok",
        data: Object.assign(
            { items: [], lines: [], total: 0, page: 1, page_size: 20, total_pages: 0, containers: [],
                streams_known: 3, anchor_ns: "1760000000000000000", next_cursor_ns: null,
                query: { logql: '{job="docker"}', range_seconds: 3600 } },
            data || {}
        ),
    };
}

test("the new logs* keys exist in the i18n island", () => {
    for (const key of ["logsErrTitle", "logsErrTimeout", "logsErrConnection", "logsErrHttp", "logsErrInvalid",
        "logsErrUnknown", "logsEmpty", "logsNoStreams"]) {
        assert.ok(TEXTS[key], key);
    }
});

test("HTTP error from Loki shows the reason with status and keeps the filter bar", async () => {
    const { window, body, requests } = await openLogs(
        degraded({ kind: "http", status: 400, detail: "parse error <b>x</b>" }, { logql: '{job="docker"} |= `a`', range_seconds: 900 })
    );
    assert.match(requests[0], /\/api\/superadmin\/monitoring\/logs\/\?range=3600/);
    const error = body.querySelector('[data-smx-log-state="error"]');
    assert.ok(error, body.innerHTML);
    assert.match(error.textContent, /Log mənbəyinə qoşulmaq olmadı: Loki HTTP 400 xətası qaytardı — parse error <b>x<\/b>/);
    assert.equal(error.querySelector("b"), null, "Loki detail must be escaped");
    assert.ok(body.querySelector("#smx-log-go"), "filter bar stays");
    assert.match(body.querySelector(".smx-log-query").textContent, /\{job="docker"\} \|= `a` · 15 dəq/);
    assert.doesNotMatch(body.textContent, /Monitorinq asılılığı bərpa olunana qədər/);
    assert.equal(window.document.getElementById("smx-degraded").hidden, false);
    window.close();
});

test("timeout and connection failures name the cause", async () => {
    let ctx = await openLogs(degraded({ kind: "timeout", status: null, detail: "5 s" }));
    assert.match(ctx.body.textContent, /Log mənbəyinə qoşulmaq olmadı: Loki 5 s ərzində cavab vermədi/);
    ctx.window.close();
    ctx = await openLogs(degraded({ kind: "connection", status: null, detail: "" }));
    assert.match(ctx.body.textContent, /Loki xidmətinə bağlantı qurulmadı/);
    ctx.window.close();
    ctx = await openLogs(degraded(undefined));
    assert.match(ctx.body.textContent, /Log mənbəyinə qoşulmaq olmadı: Log servisi müvəqqəti əlçatmazdır/);
    ctx.window.close();
});

test("empty result names the range and the selector, not a bare «Log tapılmadı»", async () => {
    const { window, body } = await openLogs(ok({ query: { logql: '{container="emsarena-nginx"}', range_seconds: 604800 } }));
    const empty = body.querySelector('[data-smx-log-state="empty"]');
    assert.ok(empty, body.innerHTML);
    assert.equal(empty.textContent, "Son 7 gün ərzində bu sorğuya uyğun log yoxdur");
    assert.match(body.querySelector(".smx-log-query").textContent, /\{container="emsarena-nginx"\} · 7 gün/);
    assert.equal(body.querySelector(".smx-log-hint"), null, "streams exist → no shipper hint");
    window.close();
});

test("Loki without any stream shows the promtail hint; unknown range falls back to a duration", async () => {
    const { window, body } = await openLogs(ok({ streams_known: 0, query: { logql: '{job="docker"}', range_seconds: 7200 } }));
    assert.match(body.querySelector(".smx-log-hint").textContent, /promtail/);
    assert.match(body.querySelector(".smx-log-query").textContent, /2 saat 0 dəq/);
    window.close();
});

test("rows render as a table with escaped content", async () => {
    const line = { ts: 1760000000000, container: "educationmanagementstudentarena-app-1", line: "<img src=x onerror=1>" };
    const { window, body } = await openLogs(ok({ items: [line], lines: [line], total: 1, total_pages: 1 }));
    assert.equal(body.querySelector('[data-smx-log-state]'), null);
    assert.equal(body.querySelectorAll(".smx-table tr").length, 1);
    assert.equal(body.querySelector("img"), null);
    assert.match(body.querySelector(".smx-log").textContent, /<img src=x onerror=1>/);
    window.close();
});
