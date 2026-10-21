/* ═══════════════════════════════════════════════════════════════════════════
   «İmtahan zalları» — dialoq xətası dialoqda qalır (superadmin_exam_rooms_ajax.js), 2026-10-21.
   Sahib: «Kompüter əlavə edərkən səhv edəndə səhvi göstərmir, yazdığım tabdan atır — deyirsə yer var,
   modalda göstərsin, bütöv atır.»

   Göndərilən skriptlər OLDUĞU KİMİ window.eval ilə (ems_early → ems_ajax_init → core/csrf+http →
   ems_ui/overlay → teaching_office → superadmin_exam_rooms → superadmin_exam_rooms_ajax).

   Müqavilə:
     • 400 → dialoq açıq, yazılanlar yerində, xəta SAHƏNİN yanında (aria-invalid + aria-describedby) +
       dialoqun başında xülasə; heç bir naviqasiya/yenidən yükləmə yoxdur;
     • 200 → dialoq bağlanır, fraqment alınıb çekmecə gövdəsi YERİNDƏ əvəzlənir (çekmecə açıq qalır,
       sürüşmə yeri qorunur), KPI/siyahı yenilənir, uğur tostu;
     • boş məcburi sahə → server sorğusu getmir, sahə xətası;
     • adi POST xətasından sonra `#sar-form-state` → dialoq yenidən açılır, dəyərlər + xətalar bərpa olunur.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const SCRIPTS = [
    "static/js/ems_early.js",
    "static/js/ems_ajax_init.js",
    "static/js/core/csrf.js",
    "static/js/core/http.js",
    "static/js/ems_ui/overlay.js",
    "apps/accounts/static/accounts/js/profile/teaching_office.js",
    "apps/accounts/static/accounts/js/superadmin_exam_rooms.js",
    "apps/accounts/static/accounts/js/superadmin_exam_rooms_ajax.js",
].map(read);

const ACTION_URL = "/accounts/superadmin/exam-rooms/";
const FRAGMENT_URL = "/accounts/profile/api/sections/superadmin-exam-rooms/";
const ADD_PREFILL = JSON.stringify({
    action: "add_computer",
    room_id: "5",
    computer_id: "",
    label: "",
    seat_number: "",
    mac_address: "",
    ip_address: "",
    notes: "",
    is_active: "1",
});

function drawerHtml(rows, count) {
    return (
        '<div class="ems-overlay ems-overlay--drawer" id="sarRoomDrawer-5" hidden>' +
        '<div class="ems-drawer" role="dialog" aria-modal="true">' +
        '<div class="ems-drawer__head"><div><h2 class="ems-drawer__title">Zal X</h2>' +
        '<p class="ems-drawer__sub">ZX</p></div>' +
        '<button type="button" class="ems-drawer__x" data-ems-overlay-close>×</button></div>' +
        '<div class="ems-drawer__body"><div class="sar-room" data-sar-room="5">' +
        '<span class="sar-count" data-test-count>' + count + "</span>" +
        "<button type=\"button\" id=\"add-btn\" data-tof-open=\"sarComputerDialog\" data-tof-title=\"Kompüter əlavə et\" " +
        "data-tof-prefill='" + ADD_PREFILL + "' data-sar-subtitle=\"Zal X · ZX\" data-sar-submit=\"Əlavə et\">+</button>" +
        "<table><tbody>" +
        rows.map((r) => '<tr data-comp-row="' + r[0] + '"><th scope="row">' + r[1] + "</th></tr>").join("") +
        "</tbody></table></div></div>" +
        '<div class="ems-drawer__foot"><button type="button" data-ems-overlay-close>Bağla</button></div>' +
        "</div></div>"
    );
}

const DIALOG =
    '<div class="ems-overlay ems-overlay--dialog" id="sarComputerDialog" hidden>' +
    '<div class="ems-dialog" role="dialog" aria-modal="true">' +
    '<form method="post" action="' + ACTION_URL + '" data-sar-form="1" data-sar-ajax="1" novalidate>' +
    '<input type="hidden" name="csrfmiddlewaretoken" value="tok-123">' +
    '<input type="hidden" name="action" value="add_computer">' +
    '<input type="hidden" name="room_id" value="">' +
    '<input type="hidden" name="computer_id" value="">' +
    '<input type="hidden" name="organization_id" value="9" data-tof-keep="1">' +
    '<input type="hidden" name="next" value="/accounts/profile/?section=superadmin-exam-rooms" data-tof-keep="1">' +
    '<div class="ems-dialog__head"><div><h2 class="ems-dialog__title">Kompüter</h2><p class="ems-dialog__sub">sub</p></div>' +
    '<button type="button" class="ems-dialog__x" data-ems-overlay-close>×</button></div>' +
    '<div class="ems-dialog__body"><p class="ems-msg ems-msg--error" data-ems-form-error role="alert" hidden></p>' +
    '<div class="sar-formgrid">' +
    '<div class="ems-field"><label for="sar-comp-label">Ad</label><input class="ems-input" id="sar-comp-label" name="label" required></div>' +
    '<div class="ems-field"><label for="sar-comp-seat">Yer</label><input class="ems-input" type="number" id="sar-comp-seat" name="seat_number" min="1"></div>' +
    '<div class="ems-field"><label for="sar-comp-mac">MAC</label><input class="ems-input" id="sar-comp-mac" name="mac_address" required data-mac-input></div>' +
    '<div class="ems-field"><label for="sar-comp-ip">IP</label><input class="ems-input" id="sar-comp-ip" name="ip_address">' +
    '<span class="ems-field__hint" id="sar-comp-ip-hint">hint</span></div>' +
    '<div class="ems-field"><label for="sar-comp-notes">Qeyd</label><input class="ems-input" id="sar-comp-notes" name="notes"></div>' +
    '<label class="sar-check" data-sar-edit-only><input type="checkbox" name="is_active" value="1"> Aktiv</label>' +
    "</div></div>" +
    '<div class="ems-dialog__foot"><button type="button" class="ems-btn" data-ems-overlay-close>Ləğv et</button>' +
    '<button type="submit" class="ems-btn ems-btn--primary">Yadda saxla</button></div>' +
    "</form></div></div>";

function sectionHtml({ rows, count, kpi, state }) {
    return (
        '<div class="sar" data-sar-root data-sar-fragment-url="' + FRAGMENT_URL + '"' +
        ' data-sar-msg-required="REQUIRED" data-sar-msg-invalid="INVALID"' +
        ' data-sar-msg-check="CHECK" data-sar-msg-failed="FAILED">' +
        '<div class="sar-region" data-sar-region="kpi"><div class="ems-kpis"><span class="ems-kpi__value" data-test-kpi>' +
        kpi + "</span></div></div>" +
        '<div class="sar-region" data-sar-region="list"><table><tbody><tr>' +
        '<th scope="row"><div data-sar-room-row="5">Zal X</div></th><td data-test-list>' + count + "</td>" +
        "</tr></tbody></table></div>" +
        drawerHtml(rows, count) +
        DIALOG +
        (state ? '<script id="sar-form-state" type="application/json">' + JSON.stringify(state) + "</script>" : "") +
        "</div>"
    );
}

function jsonResponse(status, payload) {
    return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        text: () => Promise.resolve(JSON.stringify(payload)),
    });
}

async function page({ state = null } = {}) {
    const html = sectionHtml({ rows: [[1, "PC-01"]], count: 1, kpi: 1, state });
    const dom = new JSDOM(
        '<!doctype html><html><body><section data-profile-section-panel="superadmin-exam-rooms">' + html +
            "</section></body></html>",
        { runScripts: "outside-only", url: "http://localhost/accounts/profile/?section=superadmin-exam-rooms&room_org=9" }
    );
    const { window } = dom;
    const doc = window.document;
    if (doc.readyState === "loading") {
        await new Promise((resolve) => doc.addEventListener("DOMContentLoaded", resolve));
    }
    const calls = [];
    const responses = [];
    window.fetch = (url, opts) => {
        calls.push({ url: String(url), opts: opts || {} });
        const next = responses.shift();
        return next ? next(String(url), opts || {}) : jsonResponse(500, { ok: false });
    };
    const toasts = [];
    window.EMSToast = { show: (message, kind) => toasts.push([kind, message]) };
    const navigations = [];
    window.EMSProfileLoadSection = (section, url) => navigations.push([section, url]);
    // jsdom: `scrollIntoView` yoxdur (vurğu üçün çağırılır).
    window.HTMLElement.prototype.scrollIntoView = function () {};
    SCRIPTS.forEach((src) => window.eval(src));
    const tick = async (n = 6) => {
        for (let i = 0; i < n; i += 1) {
            await new Promise((resolve) => setTimeout(resolve, 0));
        }
    };
    const $ = (sel) => doc.querySelector(sel);
    const form = () => $("#sarComputerDialog form");
    const type = (name, value) => {
        const el = form().querySelector('[name="' + name + '"]');
        el.value = value;
    };
    const submit = () => {
        const f = form();
        f.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    };
    return { window, doc, calls, responses, toasts, navigations, tick, $, form, type, submit };
}

async function openAddDialog(p) {
    p.window.EMSOverlay.open(p.$("#sarRoomDrawer-5"));
    p.$("#add-btn").click();
    assert.equal(p.$("#sarComputerDialog").hidden, false, "dialog opens");
    assert.equal(p.form().querySelector('[name="room_id"]').value, "5", "prefill from opener");
    p.type("label", "PC-02");
    p.type("seat_number", "1");
    p.type("mac_address", "AA:BB:CC:DD:EE:02");
    p.type("ip_address", "10.0.0.12");
    p.type("notes", "pəncərə yanı");
}

test("400 «yer tutulub»: dialog stays open, typed values kept, error next to the field + summary, no navigation", async () => {
    const p = await page();
    await openAddDialog(p);
    const seatMsg = "Bu yer nömrəsi artıq tutulub: 1";
    p.responses.push(() => jsonResponse(400, { ok: false, message: seatMsg, errors: { seat_number: seatMsg } }));
    const startHref = p.window.location.href;
    p.submit();
    await p.tick();

    assert.equal(p.calls.length, 1, "exactly one POST, no fragment refresh");
    assert.equal(p.calls[0].url, ACTION_URL);
    assert.equal(p.calls[0].opts.method, "POST");
    assert.equal(p.calls[0].opts.headers["X-Requested-With"], "XMLHttpRequest");
    assert.equal(p.calls[0].opts.headers["X-CSRFToken"], "tok-123");
    const body = p.calls[0].opts.body;
    assert.equal(body.get("label"), "PC-02");
    assert.equal(body.get("room_id"), "5");
    assert.equal(body.get("organization_id"), "9");

    assert.equal(p.$("#sarComputerDialog").hidden, false, "dialog still open");
    assert.equal(p.$("#sarRoomDrawer-5").hidden, false, "drawer still open");
    const f = p.form();
    assert.equal(f.querySelector('[name="label"]').value, "PC-02");
    assert.equal(f.querySelector('[name="seat_number"]').value, "1");
    assert.equal(f.querySelector('[name="mac_address"]').value, "AA:BB:CC:DD:EE:02");
    assert.equal(f.querySelector('[name="notes"]').value, "pəncərə yanı");

    const seat = f.querySelector('[name="seat_number"]');
    const note = f.querySelector('[data-sar-field-error="seat_number"]');
    assert.ok(note, "field error rendered");
    assert.equal(note.textContent, seatMsg);
    assert.equal(note.parentNode, seat.closest(".ems-field"), "error sits next to the seat field");
    assert.equal(seat.getAttribute("aria-invalid"), "true");
    assert.ok(seat.getAttribute("aria-describedby").split(" ").includes(note.id));
    const summary = f.querySelector("[data-ems-form-error]");
    assert.equal(summary.hidden, false);
    assert.equal(summary.textContent, seatMsg);
    assert.equal(p.doc.activeElement, seat, "focus moves to the bad field");

    assert.deepEqual(p.navigations, []);
    assert.equal(p.window.location.href, startHref);
    assert.deepEqual(p.toasts, [], "error is in the dialog, not a toast");
    assert.equal(f.querySelector('[type="submit"]').disabled, false, "submit re-enabled");
});

test("several field errors at once; re-opening the dialog clears them", async () => {
    const p = await page();
    await openAddDialog(p);
    p.responses.push(() =>
        jsonResponse(400, {
            ok: false,
            message: "MAC ünvanı düzgün deyil: zz",
            errors: { mac_address: "MAC ünvanı düzgün deyil: zz", ip_address: "Bu IP artıq «Zal Y» zalında" },
        })
    );
    p.submit();
    await p.tick();
    const f = p.form();
    assert.ok(f.querySelector('[data-sar-field-error="mac_address"]'));
    assert.ok(f.querySelector('[data-sar-field-error="ip_address"]'));
    const ip = f.querySelector('[name="ip_address"]');
    assert.equal(ip.getAttribute("aria-invalid"), "true");

    p.window.EMSOverlay.close(p.$("#sarComputerDialog"));
    p.$("#add-btn").click();
    assert.equal(f.querySelectorAll("[data-sar-field-error]").length, 0);
    assert.equal(f.querySelector("[data-ems-form-error]").hidden, true);
    assert.notEqual(ip.getAttribute("aria-invalid"), "true");
    assert.equal(ip.hasAttribute("aria-describedby"), false, "our describedby link removed");
    assert.equal(f.querySelector('[name="label"]').value, "", "fresh prefill on re-open");
});

test("empty required field: no request, error next to the field", async () => {
    const p = await page();
    await openAddDialog(p);
    p.type("mac_address", "");
    p.submit();
    await p.tick();
    assert.equal(p.calls.length, 0, "client validation stops the round trip");
    const note = p.form().querySelector('[data-sar-field-error="mac_address"]');
    assert.ok(note);
    assert.equal(note.textContent, "REQUIRED");
    assert.equal(p.form().querySelector("[data-ems-form-error]").textContent, "CHECK");
    assert.equal(p.$("#sarComputerDialog").hidden, false);
});

test("200: dialog closes, drawer body replaced in place and stays open, KPI/list refreshed, toast", async () => {
    const p = await page();
    await openAddDialog(p);
    p.type("seat_number", "2");
    const drawer = p.$("#sarRoomDrawer-5");
    const body = drawer.querySelector(".ems-drawer__body");
    body.scrollTop = 40;
    p.responses.push(() => jsonResponse(200, { ok: true, message: "Kompüter əlavə edildi.", hl_comp: 2, room_id: 5 }));
    p.responses.push((url) => {
        assert.ok(url.startsWith("http://localhost" + FRAGMENT_URL), "fragment endpoint: " + url);
        assert.ok(url.includes("room_org=9"), "keeps filters / org");
        assert.ok(!url.includes("section="), "no section param on the fragment url");
        return jsonResponse(200, {
            ok: true,
            html:
                '<section data-profile-section-panel="superadmin-exam-rooms">' +
                sectionHtml({ rows: [[1, "PC-01"], [2, "PC-02"]], count: 2, kpi: 2 }) +
                "</section>",
        });
    });
    p.submit();
    await p.tick(10);

    assert.equal(p.calls.length, 2);
    assert.equal(p.$("#sarComputerDialog").hidden, true, "dialog closed");
    assert.equal(p.doc.getElementById("sarRoomDrawer-5"), drawer, "same drawer element (not re-created)");
    assert.equal(drawer.hidden, false, "drawer stays open");
    assert.equal(drawer.querySelector(".ems-drawer__body"), body, "body container kept");
    assert.ok(drawer.querySelector('[data-comp-row="2"]'), "new computer row is in the drawer");
    assert.equal(drawer.querySelector("[data-test-count]").textContent, "2");
    assert.ok(drawer.querySelector('[data-comp-row="2"]').classList.contains("sar-flash-row"), "row highlighted");
    assert.equal(p.$("[data-test-kpi]").textContent, "2", "KPI refreshed");
    assert.equal(p.$("[data-test-list]").textContent, "2", "list refreshed");
    assert.equal(p.doc.querySelectorAll("#sarComputerDialog").length, 1, "dialog not duplicated");
    assert.deepEqual(p.toasts, [["success", "Kompüter əlavə edildi."]]);
    assert.deepEqual(p.navigations, [], "no full reload");
});

test("network/HTML failure keeps the dialog open with the generic message", async () => {
    const p = await page();
    await openAddDialog(p);
    p.responses.push(() =>
        Promise.resolve({ ok: false, status: 404, text: () => Promise.resolve("<html>404</html>") })
    );
    p.submit();
    await p.tick();
    assert.equal(p.$("#sarComputerDialog").hidden, false);
    assert.equal(p.form().querySelector("[data-ems-form-error]").textContent, "FAILED");
    assert.equal(p.form().querySelector('[name="label"]').value, "PC-02");
});

test("non-AJAX fallback: #sar-form-state reopens the drawer + dialog with values and errors", async () => {
    const seatMsg = "Bu yer nömrəsi artıq tutulub: 1";
    const p = await page({
        state: {
            dialog: "sarComputerDialog",
            action: "add_computer",
            room_id: "5",
            computer_id: "",
            values: {
                action: "add_computer",
                room_id: "5",
                computer_id: "",
                organization_id: "9",
                label: "PC-02",
                seat_number: "1",
                mac_address: "AA:BB:CC:DD:EE:02",
                ip_address: "",
                notes: "pəncərə yanı",
            },
            errors: { seat_number: seatMsg },
            message: seatMsg,
        },
    });
    await p.tick();
    assert.equal(p.$("#sarRoomDrawer-5").hidden, false, "drawer reopened");
    assert.equal(p.$("#sarComputerDialog").hidden, false, "dialog reopened");
    const f = p.form();
    assert.equal(p.$("#sarComputerDialog .ems-dialog__title").textContent, "Kompüter əlavə et", "opener title used");
    assert.equal(f.querySelector('[name="label"]').value, "PC-02");
    assert.equal(f.querySelector('[name="notes"]').value, "pəncərə yanı");
    assert.equal(f.querySelector('[name="room_id"]').value, "5");
    assert.equal(f.querySelector('[data-sar-field-error="seat_number"]').textContent, seatMsg);
    assert.equal(f.querySelector("[data-ems-form-error]").textContent, seatMsg);
    assert.equal(p.$("#sar-form-state"), null, "state block consumed once");
});

test("drawer action (no dialog) error → error toast, drawer stays open, no navigation", async () => {
    const p = await page();
    const drawer = p.$("#sarRoomDrawer-5");
    p.window.EMSOverlay.open(drawer);
    drawer.querySelector(".ems-drawer__foot").insertAdjacentHTML(
        "beforeend",
        '<form method="post" action="' + ACTION_URL + '" class="sar-inline-form" data-sar-ajax="1" id="del-room">' +
            '<input type="hidden" name="csrfmiddlewaretoken" value="tok-123">' +
            '<input type="hidden" name="action" value="delete_room"><button type="submit">Sil</button></form>'
    );
    const msg = "«Zal X» zalının oturum tarixçəsi var — silinə bilməz. Zalı deaktiv edin.";
    p.responses.push(() => jsonResponse(400, { ok: false, message: msg, errors: { __all__: msg } }));
    p.$("#del-room").dispatchEvent(new p.window.Event("submit", { bubbles: true, cancelable: true }));
    await p.tick();
    assert.deepEqual(p.toasts, [["error", msg]]);
    assert.equal(drawer.hidden, false);
    assert.deepEqual(p.navigations, []);
});

test("bulk partial success keeps the dialog open with only the failed lines", async () => {
    const p = await page();
    // Toplu dialoqu sadələşdirilmiş şəkildə — eyni forma müqaviləsi (`bulk_text`).
    p.doc.querySelector("[data-sar-root]").insertAdjacentHTML(
        "beforeend",
        '<div class="ems-overlay ems-overlay--dialog" id="sarBulkDialog"><div class="ems-dialog">' +
            '<form method="post" action="' + ACTION_URL + '" data-sar-form="1" data-sar-ajax="1" novalidate>' +
            '<input type="hidden" name="csrfmiddlewaretoken" value="tok-123">' +
            '<div class="ems-dialog__body"><p data-ems-form-error hidden></p>' +
            '<div class="ems-field"><textarea name="bulk_text" required></textarea></div></div>' +
            '<button type="submit">OK</button></form></div></div>'
    );
    const dialog = p.$("#sarBulkDialog");
    p.window.EMSOverlay.open(dialog);
    dialog.querySelector("textarea").value = "PC-20, AA:BB:CC:DD:EE:20\nPC-21, bad";
    p.responses.push(() =>
        jsonResponse(200, {
            ok: true,
            message: "1 kompüter əlavə edildi.",
            keep_open: true,
            summary: "1 sətir əlavə edilmədi — düzəldib yenidən göndərin.",
            errors: { bulk_text: "Sətir 2: MAC ünvanı düzgün deyil: bad" },
            error_list: ["Sətir 2: MAC ünvanı düzgün deyil: bad"],
            remaining_text: "PC-21, bad",
        })
    );
    p.responses.push(() =>
        jsonResponse(200, { ok: true, html: sectionHtml({ rows: [[1, "PC-01"], [3, "PC-20"]], count: 2, kpi: 2 }) })
    );
    dialog.querySelector("form").dispatchEvent(new p.window.Event("submit", { bubbles: true, cancelable: true }));
    await p.tick(10);
    assert.equal(dialog.hidden, false, "dialog stays open");
    assert.equal(dialog.querySelector("textarea").value, "PC-21, bad");
    assert.equal(dialog.querySelectorAll("[data-sar-error-list] li").length, 1);
    assert.match(dialog.querySelector('[data-sar-field-error="bulk_text"]').textContent, /Sətir 2/);
    assert.deepEqual(p.toasts, [["success", "1 kompüter əlavə edildi."]]);
    assert.ok(p.$('#sarRoomDrawer-5 [data-comp-row="3"]'), "drawer refreshed behind the dialog");
});
