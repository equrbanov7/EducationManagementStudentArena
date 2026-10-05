/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-05: «Sistem Monitorinqi» → «Təhlükəsizlik» tabının IP filtri
   (apps/accounts/static/accounts/js/monitoring/system_monitoring_security.js) ƏSL DOM-da.
   Yoxlanır: filtr zolağı + «×», IP xanası / Enter / «Axtar» filtri tətbiq edir, «Bu IP-dən
   uğurlu girişlər» bloku, hücumçunun idarə etdiyi user-agent/ad escape olunur (atribut da),
   yanlış IP (API 400) zolağı itirmir, avto-yeniləmə yazılan mətni və fokusu silmir.
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
const SECURITY = fs.readFileSync(path.join(DIR, "system_monitoring_security.js"), "utf8");

const TEXTS = {
    ipFilterBy: "Yalnız bu IP: {ip}",
    loginsMeta: "Girişlər: {logins} · Hesablar: {accounts}",
    loginsTruncated: "Ən son {limit} qeyd göstərilir",
    firstSeen: "ilk: {time}",
};

function setup() {
    const dom = new JSDOM("<!doctype html><html><body><div id='smx-body'></div></body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/accounts/profile/?section=system-monitoring",
    });
    const window = dom.window;
    window.gettext = (text) => text;
    window.interpolate = (text) => text;
    window.eval(FORMAT);
    window.eval(SECURITY);
    const F = window.EMSSystemMonitoring.format;
    const states = { "security-events": { page: 1, page_size: 20, type: "", ip: "" } };
    const reloads = [];
    const ctx = {
        states,
        t: (key) => TEXTS[key] || "[" + key + "]",
        fmt: (text, values) => String(text).replace(/\{(\w+)\}/g, (match, name) =>
            values && values[name] != null ? String(values[name]) : match),
        rowsFrom: F.rowsFrom,
        pill: F.pill,
        pager: (data, count) => F.pagerMarkup(data, count, states["security-events"]),
        reload: (tab) => reloads.push({ tab, state: { ...states[tab] } }),
    };
    const body = window.document.getElementById("smx-body");
    const render = (data) => window.EMSSystemMonitoring.security.render(body, data, ctx);
    return { window, body, states, reloads, render };
}

function event(row) {
    return Object.assign({
        id: 1, event_type: "login_failed", event_type_display: "Uğursuz giriş", severity: "low",
        user: "ad.soyad", ip: "10.1.1.1", message: "Uğursuz giriş cəhdi", count: 3,
        first_seen: "2026-10-05T08:00:00+00:00", last_seen: "2026-10-05T08:05:00+00:00", resolved: false,
    }, row || {});
}

function page(items, extra) {
    return Object.assign({ items, total: items.length, page: 1, page_size: 20, total_pages: 1 }, extra || {});
}

test("filter bar has the event-type select, the IP field and a hidden clear button", () => {
    const { window, body, render } = setup();
    render(page([event()]));
    assert.ok(body.querySelector("select#smx-sec-type[data-bootstrap-select]"));
    const input = body.querySelector("input#smx-sec-ip");
    assert.equal(input.value, "");
    assert.equal(input.getAttribute("maxlength"), "64");
    assert.equal(body.querySelector("#smx-sec-ip-clear").hidden, true);
    assert.ok(body.querySelector("#smx-sec-ip-go"));
    window.close();
});

test("clicking an IP cell applies it as the filter and reloads the tab", () => {
    const { window, body, reloads, render } = setup();
    render(page([event({ ip: "10.9.9.9" })]));
    const cell = body.querySelector("[data-smx-ip]");
    assert.equal(cell.tagName, "BUTTON");
    assert.equal(cell.getAttribute("aria-label"), "Yalnız bu IP: 10.9.9.9");
    cell.click();
    assert.deepEqual(reloads.map((item) => [item.tab, item.state.ip]), [["security-events", "10.9.9.9"]]);
    window.close();
});

test("Enter and «Axtar» apply the typed value; «×» clears the filter", () => {
    const { window, body, states, reloads, render } = setup();
    render(page([]));
    const input = body.querySelector("#smx-sec-ip");
    input.value = "  5.191.0.0/16 ";
    input.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    assert.equal(states["security-events"].ip, "5.191.0.0/16");

    render(page([]));
    body.querySelector("#smx-sec-ip").value = "10.0.0.1";
    body.querySelector("#smx-sec-ip-go").click();
    assert.equal(states["security-events"].ip, "10.0.0.1");

    render(page([]));
    const clear = body.querySelector("#smx-sec-ip-clear");
    assert.equal(clear.hidden, false);
    clear.click();
    assert.equal(states["security-events"].ip, "");
    assert.equal(reloads.length, 3);
    window.close();
});

test("type select change keeps the IP and reloads", () => {
    const { window, body, states, reloads, render } = setup();
    states["security-events"].ip = "10.0.0.1";
    render(page([]));
    const select = body.querySelector("#smx-sec-type");
    select.value = "login_brute_force";
    select.dispatchEvent(new window.Event("change", { bubbles: true }));
    assert.deepEqual(reloads.map((item) => [item.state.type, item.state.ip]), [["login_brute_force", "10.0.0.1"]]);
    window.close();
});

test("logins block lists accounts; hostile user-agent and names stay inert text", () => {
    const { window, body, states, render } = setup();
    states["security-events"].ip = "10.30.0.5";
    const hostile = "\"><img src=x onerror=alert(1)>";
    render(page([event({ ip: "10.30.0.5" })], {
        ip_filter: { query: "10.30.0.5", normalized: "10.30.0.5", kind: "address" },
        logins: {
            items: [{
                ip: "10.30.0.5", user: "<b>mallory</b>", full_name: "Ad <i>Soyad</i>", user_agent: hostile,
                device: hostile, count: 2, first_seen: "2026-10-05T08:00:00+00:00", last_seen: "2026-10-05T09:00:00+00:00",
            }],
            total: 2, accounts: 1, limit: 50, truncated: true, org_scoped: true,
        },
    }));
    const block = body.querySelector("section.smx-logins");
    assert.ok(block);
    assert.equal(body.querySelectorAll("img, i:not(.fas), b b").length, 0);
    const device = block.querySelector(".smx-logins__device");
    assert.equal(device.getAttribute("title"), hostile);
    assert.equal(device.textContent, hostile);
    assert.match(block.textContent, /<b>mallory<\/b>/);
    assert.match(block.querySelector(".smx-logins__meta").textContent, /Girişlər: 2 · Hesablar: 1/);
    assert.match(block.textContent, /ilk: /);
    assert.match(block.textContent, /Ən son 50 qeyd/);
    assert.match(block.textContent, /\[loginsOrgNote\]/);
    // Aktiv IP cədvəldə düymə deyil (özünü təkrar tətbiq etməsin); hadisələr başlıqla ayrılır.
    assert.equal(body.querySelector("[data-smx-ip]"), null);
    assert.ok(body.querySelector(".smx-iplink.is-active"));
    assert.equal(body.querySelector("h4.smx-subhead").textContent, "[securityTitle]");
    window.close();
});

test("empty logins for a network filter and empty events say so", () => {
    const { window, body, states, render } = setup();
    states["security-events"].ip = "10.0.0.0/8";
    render(page([], {
        ip_filter: { query: "10.0.0.0/8", normalized: "10.0.0.0/8", kind: "network" },
        logins: { items: [], total: 0, accounts: 0, limit: 50, truncated: false, org_scoped: false },
    }));
    assert.match(body.querySelector(".smx-logins").textContent, /\[loginsTitleNet\].*10\.0\.0\.0\/8/);
    assert.match(body.querySelector(".smx-logins .smx-empty").textContent, /\[loginsEmptyNet\]/);
    assert.match(body.querySelector(":scope > .smx-empty").textContent, /\[eventsEmptyIp\]/);
    window.close();
});

test("invalid IP (API 400) keeps the bar, flags the field and shows the server message", () => {
    const { window, body, states, render } = setup();
    states["security-events"].ip = "999.1.1.1";
    render({ invalid: "IP ünvanı düzgün deyil. <script>x</script>" });
    const input = body.querySelector("#smx-sec-ip");
    assert.equal(input.value, "999.1.1.1");
    assert.equal(input.getAttribute("aria-invalid"), "true");
    const error = body.querySelector("#smx-sec-ip-error[role='alert']");
    assert.match(error.textContent, /IP ünvanı düzgün deyil\. <script>x<\/script>/);
    assert.equal(body.querySelectorAll("script, table").length, 0);
    window.close();
});

test("a re-render (auto-refresh) keeps the half-typed value, caret and focus", () => {
    const { window, body, render } = setup();
    render(page([event()]));
    const input = body.querySelector("#smx-sec-ip");
    input.focus();
    input.value = "10.20";
    input.setSelectionRange(2, 2);
    render(page([event()]));
    const fresh = body.querySelector("#smx-sec-ip");
    assert.notEqual(fresh, input);
    assert.equal(fresh.value, "10.20");
    assert.equal(window.document.activeElement, fresh);
    assert.equal(fresh.selectionStart, 2);
    assert.equal(body.querySelector("#smx-sec-ip-clear").hidden, false);
    window.close();
});
