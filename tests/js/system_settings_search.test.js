/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-21: «Sistem tənzimləmələri» alt səhifələri — system_settings_search.js ƏSL DOM-da (jsdom).
   Axtarış BÜTÜN qruplar üzrə süzür (EMSSearch: ə/e, ı/i, İ/I, ü/u, ş/s … qatlama, tokenlər — söz sırası fərq
   etmir), nəticəsiz qrup gizlənir, məzmun gizlənir (silinmir), boş sorğu / Esc geri qaytarır; cari qrupdakı
   nəticə səhifəni yükləmədən sətri vurğulayır; `data-ss-focus-key` (deep link) sətri vurğulayır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const FOLD = fs.readFileSync(path.join(ROOT, "static/js/search_fold.js"), "utf8");
const SCRIPT = fs.readFileSync(
    path.join(ROOT, "apps/accounts/static/accounts/js/profile/system_settings_search.js"),
    "utf8"
);

const INDEX = {
    login: {
        label: "Giriş və parol cəhdləri",
        items: [
            ["login.device_rate", "Bir cihazdan səhv parol cəhdi", "Pəncərə ərzində icazə verilən say."],
            ["login.ip_rate", "Bir İP ünvanından giriş cəhdi", "Universitet Wi-Fi-ı."],
        ],
    },
    otp: {
        label: "E-poçt kodu (OTP)",
        items: [
            ["otp.max_attempts", "Bir kod üçün səhv yazma cəhdi", ""],
            ["otp.expiry_minutes", "Kodun etibarlılıq müddəti", "6 rəqəmli kod."],
        ],
    },
    session: {
        label: "Sessiya",
        items: [["session.idle_hours", "Hərəkətsizlikdən sonra avtomatik çıxış", "Sessiya ən çox 24 saat."]],
    },
};

function markup(currentGroup, focusKey) {
    const groups = Object.entries(INDEX)
        .map(([key, group]) => {
            const items = group.items
                .map(
                    ([k, label, help]) =>
                        `<li data-ss-hit data-ss-hit-group="${key}" data-ss-hit-key="${k}" ` +
                        `data-ss-text="${label} ${help} ${k} ${group.label}">` +
                        `<a href="/accounts/profile/?section=system-settings&amp;ss_group=${key}&amp;ss_key=${k}" data-ss-hit-link>${label}</a></li>`
                )
                .join("");
            return `<section data-ss-result-group="${key}"><h3>${group.label}</h3><ul>${items}</ul></section>`;
        })
        .join("");
    const rows = currentGroup
        ? INDEX[currentGroup].items
              .map(([k]) => `<div class="sysset__row" data-ss-field="${k}"><input name="${k}" value="1"></div>`)
              .join("")
        : "";
    return (
        `<section data-profile-section-panel="system-settings">` +
        `<div class="sysset" data-ss-root data-ss-group="${currentGroup || ""}" data-ss-focus-key="${focusKey || ""}">` +
        `<input type="search" data-ss-search>` +
        `<div data-ss-results hidden><p data-ss-results-status data-empty-text="Heç nə tapılmadı" data-count-text="Tapıldı: {n}"></p>${groups}</div>` +
        `<div data-ss-main><form data-ss-form>${rows}</form></div>` +
        `</div></section>`
    );
}

function load(currentGroup, focusKey) {
    const dom = new JSDOM(`<!doctype html><html><body>${markup(currentGroup, focusKey)}</body></html>`, {
        runScripts: "outside-only",
        url: "http://localhost/accounts/profile/?section=system-settings",
    });
    dom.window.eval(FOLD);
    dom.window.eval(SCRIPT);
    return dom.window;
}

function type(win, value) {
    const input = win.document.querySelector("[data-ss-search]");
    input.value = value;
    input.dispatchEvent(new win.Event("input", { bubbles: true }));
}

function visibleKeys(win) {
    return Array.from(win.document.querySelectorAll("[data-ss-hit]"))
        .filter((node) => !node.hidden)
        .map((node) => node.getAttribute("data-ss-hit-key"));
}

function visibleGroups(win) {
    return Array.from(win.document.querySelectorAll("[data-ss-result-group]"))
        .filter((node) => !node.hidden)
        .map((node) => node.getAttribute("data-ss-result-group"));
}

test("axtarış bütün qruplar üzrə süzür, diakritikaya dözümlüdür və tokenlidir", () => {
    const win = load("");
    const results = win.document.querySelector("[data-ss-results]");
    const main = win.document.querySelector("[data-ss-main]");
    assert.equal(results.hidden, true);

    type(win, "cehdi");
    assert.deepEqual(visibleKeys(win), ["login.device_rate", "login.ip_rate", "otp.max_attempts"]);
    assert.deepEqual(visibleGroups(win), ["login", "otp"]);
    assert.equal(results.hidden, false);
    assert.equal(main.hidden, true);
    assert.equal(win.document.querySelector("[data-ss-results-status]").textContent, "Tapıldı: 3");

    // Söz sırası fərq etmir; «sehv parol» → «səhv parol».
    type(win, "parol sehv");
    assert.deepEqual(visibleKeys(win), ["login.device_rate"]);
    type(win, "SEHV PAROL");
    assert.deepEqual(visibleKeys(win), ["login.device_rate"]);

    // İ/I və ü/u; ç/c, ı/i.
    type(win, "ip unvanindan");
    assert.deepEqual(visibleKeys(win), ["login.ip_rate"]);
    type(win, "avtomatik cixis");
    assert.deepEqual(visibleKeys(win), ["session.idle_hours"]);
    assert.deepEqual(visibleGroups(win), ["session"]);

    // Açar adı və qrup adı da axtarılır.
    type(win, "otp.expiry_minutes");
    assert.deepEqual(visibleKeys(win), ["otp.expiry_minutes"]);
    type(win, "e-poçt kodu");
    assert.deepEqual(visibleKeys(win), ["otp.max_attempts", "otp.expiry_minutes"]);

    type(win, "yoxdur-belə-şey");
    assert.deepEqual(visibleKeys(win), []);
    assert.deepEqual(visibleGroups(win), []);
    assert.equal(win.document.querySelector("[data-ss-results-status]").textContent, "Heç nə tapılmadı");

    type(win, "   ");
    assert.equal(results.hidden, true);
    assert.equal(main.hidden, false);
});

test("Esc sorğunu təmizləyir və məzmunu qaytarır", () => {
    const win = load("login");
    type(win, "kod");
    const input = win.document.querySelector("[data-ss-search]");
    input.dispatchEvent(new win.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    assert.equal(input.value, "");
    assert.equal(win.document.querySelector("[data-ss-results]").hidden, true);
    assert.equal(win.document.querySelector("[data-ss-main]").hidden, false);
});

test("cari qrupdakı nəticə yükləmədən sətri vurğulayır; başqa qrup adi keçiddir", () => {
    const win = load("login");
    let bubbled = 0;
    win.document.addEventListener("click", () => {
        bubbled += 1;
    });
    type(win, "ip");
    const same = win.document.querySelector('[data-ss-hit-key="login.ip_rate"] a');
    const sameEvent = new win.MouseEvent("click", { bubbles: true, cancelable: true });
    same.dispatchEvent(sameEvent);
    assert.equal(sameEvent.defaultPrevented, true);
    assert.equal(bubbled, 0, "ajax.js-in sənəd dinləyicisinə çatmır");
    assert.equal(win.document.querySelector("[data-ss-search]").value, "");
    assert.equal(win.document.querySelector("[data-ss-main]").hidden, false);
    const row = win.document.querySelector('[data-ss-field="login.ip_rate"]');
    assert.ok(row.classList.contains("is-target"));
    assert.equal(win.document.activeElement, row.querySelector("input"));

    type(win, "kod");
    const other = win.document.querySelector('[data-ss-hit-key="otp.max_attempts"] a');
    const otherEvent = new win.MouseEvent("click", { bubbles: true, cancelable: true });
    other.addEventListener("click", (event) => event.preventDefault()); // naviqasiyanı jsdom-da dayandır
    other.dispatchEvent(otherEvent);
    assert.equal(bubbled, 1, "başqa qrupun nəticəsi ajax.js-ə çatır (panel keçidi)");
});

test("data-ss-focus-key (deep link) sətri vurğulayır", async () => {
    const win = load("otp", "otp.expiry_minutes");
    await new Promise((resolve) => win.setTimeout(resolve, 120));
    const row = win.document.querySelector('[data-ss-field="otp.expiry_minutes"]');
    assert.ok(row.classList.contains("is-target"));
    assert.equal(win.document.querySelector('[data-ss-field="otp.max_attempts"]').classList.contains("is-target"), false);
    assert.equal(typeof win.EMSSystemSettingsSearch.apply, "function");
});
