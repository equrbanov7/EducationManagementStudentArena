"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.resolve(__dirname, "../..");

async function setup() {
    const fields = { year: "2026/2027", semester: "Payiz", unit: "chair", teacher: "42", sort: "recent" };
    const controls = Object.entries(fields).map(([key, value]) =>
        `<select data-syl-filter="${key}"><option selected value="${value}">${value}</option></select>`
    ).join("");
    const dom = new JSDOM(`<div data-syllabus-list data-profile-url="/accounts/profile/">${controls}
        <input data-syl-search value="QKU1855"><button class="is-on" data-syl-filter="status" data-value="missing"></button>
        <button data-syl-page="2">2</button><button data-syl-reset>Reset</button></div>`,
        { runScripts: "outside-only", url: "http://localhost/accounts/profile/" });
    const window = dom.window;
    if (window.document.readyState === "loading") {
        await new Promise(resolve => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    const calls = [];
    window.EMSProfileLoadSection = (section, url) => calls.push({ section, url });
    window.eval(fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8"));
    window.eval(fs.readFileSync(path.join(ROOT, "static/js/ems_search_input.js"), "utf8"));
    window.eval(fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/profile/syllabus_list.js"), "utf8"));
    return { window, calls, fields };
}

test("teacher change preserves existing filters and resets pagination", async () => {
    const { window, calls, fields } = await setup();
    try {
        window.document.querySelector('[data-syl-filter="teacher"]').dispatchEvent(new window.Event("change", { bubbles: true }));
        const url = new URL(calls[0].url, window.location.origin);
        for (const [key, value] of Object.entries(fields)) assert.equal(url.searchParams.get(key), value);
        assert.equal(url.searchParams.get("q"), "QKU1855");
        assert.equal(url.searchParams.get("status"), "missing");
        assert.equal(url.searchParams.has("page"), false);
        window.document.querySelector("[data-syl-page]").click();
        const paged = new URL(calls[1].url, window.location.origin);
        assert.equal(paged.searchParams.get("teacher"), "42");
        assert.equal(paged.searchParams.get("page"), "2");
    } finally { window.close(); }
});

test("reset removes teacher together with the existing filters", async () => {
    const { window, calls } = await setup();
    try {
        window.document.querySelector("[data-syl-reset]").click();
        assert.equal(calls[0].url, "/accounts/profile/?section=syllabus-list");
    } finally { window.close(); }
});
