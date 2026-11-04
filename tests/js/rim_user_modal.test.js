"use strict";
// RİM istifadəçi kartı (2026-11-04): bölmələr, fakültə → kafedra kaskadı, vəzifə «Digər», inline yoxlama, əməl payload-ları.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {JSDOM} = require("jsdom");

const root = path.resolve(__dirname, "../..");
const dir = path.join(root, "apps/accounts/static/accounts/js/rim_center");
const FILES = ["namespace.js", "modals.js", "render.js", "detail_view.js", "actions.js", "detail_events.js"];

function user(overrides) {
    return Object.assign({
        id: 7, username: "leyla.budaqova", full_name: "Budaqova Leyla", first_name: "Leyla", last_name: "Budaqova",
        patronymic: "", email: "", fin: "", phone: "", phone_country: "AZ", phone_national: "", staff_position: "",
        status: "active", archive_kind: "", manageable: true, not_manageable_message: "", roles: [{role_label: "Müəllim"}],
        email_verified: true, last_login: "", can_edit_position: true,
        position_options: [{value: "Müəllim", label: "Müəllim"}, {value: "Dosent", label: "Dosent<b>"}],
        actions: {edit: true, set_password: true, block: true, archive_staff: true, graduate: false},
        graduation: null,
        staff_archive: {archived: false, can_archive: true, roles: ["Müəllim"], disabled_reason: ""},
        placement: {
            memberships: [
                {id: "m1", role_label: "Müəllim", kind: "teacher", unit_id: "", unit_name: "", faculty_id: "",
                    faculty_name: "", editable: true, locked_reason: ""},
                {id: "m2", role_label: "Dekan", kind: "", unit_id: "f1", unit_name: "İT fakültəsi", faculty_id: "f1",
                    faculty_name: "", editable: false, locked_reason: "Rol təyinatında dəyişir"}
            ],
            units: [
                {id: "c1", name: "Proqram mühəndisliyi", faculty_id: "f1", faculty: "İT fakültəsi", code: "", kinds: "teacher staff"},
                {id: "c2", name: "Fizika<script>x()</script>", faculty_id: "f2", faculty: "Təbiət", code: "", kinds: "teacher staff"},
                {id: "f1", name: "İT fakültəsi", faculty_id: "f1", faculty: "", code: "", kinds: "staff"}
            ],
            faculties: [{id: "f1", name: "İT fakültəsi"}, {id: "f2", name: "Təbiət"}]
        }
    }, overrides || {});
}

function setup(data) {
    const dom = new JSDOM(
        '<body><div data-rim-root data-action-url="/rim/action/" data-search-url="/rim/search/"></div>' +
        '<div data-rim-detail-modal><h3 data-rim-detail-title></h3><div data-rim-detail-body></div></div>' +
        '<script type="application/json" data-rim-i18n>{"faculty":"Fakültə","unit":"Kafedra","no_roles":"—"}</script></body>',
        {runScripts: "outside-only"}
    );
    const w = dom.window;
    const handlers = {};
    w.EMSReady = Object.assign(function () {}, {once: (_, fn) => fn()});
    w.EMSDelegate = {on: (event, selector, fn) => { handlers[event + "|" + selector] = fn; }};
    const sent = [];
    w.EMSCore = {fetchJSON: (url, options) => {
        sent.push(options.data);
        return Promise.resolve({user: data, message: "ok"});
    }};
    FILES.forEach((file) => w.eval(fs.readFileSync(path.join(dir, file), "utf8")));
    const ns = w.EMSRimCenter;
    ns.actions.search = () => {};
    ns.state.selectedUser = data;
    ns.render.detail(data);
    return {w, ns, handlers, sent, doc: w.document};
}

test("sections render with escaped labels, kind-filtered searchable unit select and locked rows", () => {
    const {w, doc} = setup(user());
    const titles = Array.from(doc.querySelectorAll(".rim-sec__title")).map((el) => el.textContent.trim());
    assert.equal(titles.length, 4);
    const host = doc.querySelector('[data-rim-place="m1"]');
    const unit = host.querySelector("select[data-rim-place-unit]");
    assert.equal(unit.dataset.liveSearch, "true");
    assert.equal(unit.hasAttribute("data-bootstrap-select"), true);
    // Fakültənin özü yalnız əməkdaş vəzifəsi üçündür — müəllim seçicisində yoxdur.
    assert.deepEqual(Array.from(unit.options).map((o) => o.value), ["", "c1", "c2"]);
    assert.equal(unit.options[2].textContent, "Fizika<script>x()</script>");
    assert.equal(doc.querySelector("[data-rim-detail-body] script"), null);
    const locked = doc.querySelectorAll(".rim-place.is-locked");
    assert.equal(locked.length, 1);
    assert.match(locked[0].textContent, /Rol təyinatında dəyişir/);
    assert.ok(doc.querySelector('[data-rim-act="archive_staff"]'));
    w.close();
});

test("faculty filter hides other faculties' chairs and clears a hidden selection", () => {
    const {w, handlers, doc} = setup(user());
    const host = doc.querySelector('[data-rim-place="m1"]');
    const faculty = host.querySelector("select[data-rim-place-faculty]");
    const unit = host.querySelector("select[data-rim-place-unit]");
    unit.value = "c2";
    faculty.value = "f1";
    handlers["change|select[data-rim-place-faculty]"]({}, faculty);
    assert.equal(unit.querySelector('option[value="c2"]').hidden, true);
    assert.equal(unit.querySelector('option[value="c1"]').hidden, false);
    assert.equal(unit.value, "");
    assert.equal(host.querySelector("[data-rim-place-save]").disabled, true);
    unit.value = "c1";
    handlers["change|select[data-rim-place-unit]"]({}, unit);
    assert.equal(host.querySelector("[data-rim-place-save]").disabled, false);
    w.close();
});

test("placement save sends only the chosen membership, unit and expected source", async () => {
    const {w, handlers, sent, doc} = setup(user());
    const host = doc.querySelector('[data-rim-place="m1"]');
    host.querySelector("select[data-rim-place-unit]").value = "c1";
    handlers["click|[data-rim-place-save]"]({preventDefault() {}}, host.querySelector("[data-rim-place-save]"));
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(JSON.parse(JSON.stringify(sent[0])), {
        action: "place_unit", membership_id: "m1", unit_id: "c1", expected_unit_id: "", reason: "", user_id: 7
    });
    w.close();
});

test("position «Digər» reveals free text and saves it as staff_position", async () => {
    const {w, ns, handlers, sent, doc} = setup(user({staff_position: "Elmi katib"}));
    const select = doc.querySelector("[data-rim-position-select]");
    assert.equal(select.value, "Elmi katib"); // cari (siyahıda olmayan) dəyər itmir
    select.value = ns.detailView.OTHER;
    handlers["change|[data-rim-position-select]"]({}, select);
    const other = doc.querySelector("[data-rim-position-other]");
    assert.equal(other.hidden, false);
    const save = doc.querySelector("[data-rim-position-save]");
    assert.equal(save.disabled, true);
    other.value = "Baş metodist";
    handlers["input|[data-rim-position-other]"]({}, other);
    assert.equal(save.disabled, false);
    handlers["click|[data-rim-position-save]"]({preventDefault() {}}, save);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(sent[0].action, "edit");
    assert.equal(sent[0].staff_position, "Baş metodist");
    assert.equal(Object.prototype.hasOwnProperty.call(sent[0], "first_name"), false);
    w.close();
});

test("inline validation flags bad FİN / email only when changed; save stays disabled until dirty", () => {
    const {w, ns, doc} = setup(user({fin: "ab"}));
    const fin = doc.querySelector('[data-rim-edit-field="fin"]');
    assert.equal(ns.actions.validateField(fin), true); // köhnə (dəyişməyən) dəyər yoxlanmır
    fin.value = "12345";
    assert.equal(ns.actions.validateField(fin), false);
    assert.equal(doc.querySelector('[data-rim-field-error="fin"]').hidden, false);
    const email = doc.querySelector('[data-rim-edit-field="email"]');
    email.value = "not-an-email";
    assert.equal(ns.actions.validateField(email), false);
    const save = doc.querySelector("[data-rim-edit-save]");
    assert.equal(save.disabled, true);
    ns.actions.syncEditState();
    assert.equal(save.disabled, false);
    w.close();
});

test("student card shows academic records and a disabled graduation tile with its reason", () => {
    const {w, doc} = setup(user({
        placement: null, staff_archive: null, actions: {graduate: false},
        graduation: {records: [{id: "r1", group: "231 PM", program: "PM", status: "enrolled", status_label: "Oxuyur"}],
            enrolled: [], can_graduate: false, disabled_reason: "İcazə yoxdur", order_optional: false}
    }));
    assert.equal(doc.querySelector("[data-rim-position-select]"), null);
    assert.match(doc.querySelector("[data-rim-detail-body]").textContent, /231 PM · PM/);
    const tile = doc.querySelector(".rim-tile.is-disabled");
    assert.ok(tile);
    assert.match(tile.textContent, /İcazə yoxdur/);
    assert.equal(doc.querySelector("[data-rim-graduate-open]"), null);
    w.close();
});
