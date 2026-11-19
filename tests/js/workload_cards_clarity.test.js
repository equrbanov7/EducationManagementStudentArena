/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-11-19: «Yük bölgüsü» — «patokda, seminar bölünəndə qarışıqdır, axın yazısı aydın deyil; dəyişəndən
   sonra yuxarı scroll gedir, adamı axtarıb tapası oluram».
   `workload_distribution_cards.js` + `workload_distribution_anchor.js` ƏSL DOM-da (jsdom).

   Müqavilə:
     • mühazirə axını nömrəli sətirdir («Axın 1»), qruplar ayrı nişan, «N qrup birlikdə» / «tək qrup» yazılır,
       patokun nə olduğu kartda izah olunur; tək axınlı kartda «axın» sözü ümumiyyətlə yoxdur;
     • seminar/lab: bütün sətrə yazılmış saat TƏK xətdir («Qruplara ayrılmayıb»), qrup xətləri «təyin olunmayıb»
       demir; qarışıq halda boş qrup xətti «Ümumi bölgüyə daxildir»;
     • kartın vəziyyəti: «Tam bölünüb» / «Vakant: N s» / «Bölünməyib: N s»;
     • qardaş qruplardan fərqlənən saat (45 əvəzinə 38, 30 əvəzinə 37) «saatı yoxlayın» nişanı alır;
     • yenidən çəkilişdən sonra: işlənən kart ekranda eyni yerdə, açıq «Tapşırıq sətirləri» açıq qalır, sağ panelin
       sürüşməsi saxlanır, saatı dəyişən müəllim «+7 s» ilə vurğulanır; sağ panel axtarışı süzür.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const JS_DIR = path.join(ROOT, "apps/accounts/static/accounts/js/profile");
const CARDS = fs.readFileSync(path.join(JS_DIR, "workload_distribution_cards.js"), "utf8");
const ANCHOR = fs.readFileSync(path.join(JS_DIR, "workload_distribution_anchor.js"), "utf8");

const HTML = `<!doctype html><html><body>
<section data-profile-section-panel="workload-distribution">
  <div data-wl-rows></div>
  <input type="search" data-wl-teacher-search>
  <div data-wl-teacher-panel></div>
  <p data-wl-teacher-none hidden></p>
</section></body></html>`;

function boot() {
    const dom = new JSDOM(HTML, { runScripts: "outside-only", pretendToBeVisual: true, url: "https://ems.test/" });
    const { window } = dom;
    window.EMSReady = Object.assign(function (fn) { fn(); }, { once: function (key, fn) { fn(); } });
    window.eval(CARDS);
    return window;
}

function entry(id, name, hours, extra) {
    return Object.assign({ id, teacher_id: id, teacher_name: name, hours, is_vacant: false, sub_number: null }, extra || {});
}

function stream(rowId, groups, plan, entries, extra) {
    return Object.assign(
        {
            lead_row_id: rowId, row_ids: [rowId], groups: groups.map((name) => ({ id: name, name })), plan, hours: plan,
            union_count: 1, assigned: plan, remaining: 0, is_complete: true, entries, orphan: false, warning: "",
        },
        extra || {}
    );
}

function line(rowId, label, plan, total, entries, extra) {
    return Object.assign(
        {
            row_id: rowId, group_id: label, label, plan, total, assigned: total, remaining: 0, is_complete: true,
            joint: false, joint_elsewhere: false, entries, sections: [],
        },
        extra || {}
    );
}

function card(extra) {
    return Object.assign(
        {
            id: "c1", key: "task|teaching|subj|fall|p|6", subject: "Biznesin əsasları", row_kind: "teaching",
            season_label: "Payız", credits: "6", groups: [{ id: "a", name: "534 Bİ az" }, { id: "b", name: "534 Bİ ing" }],
            total_hours: 150, student_count: 0, specialties: [], teaching_complete: true, intensive: null, warnings: [],
            rows: [], other: [],
            lecture: { plan: 45, load_hours: 83, without_groups: [], streams: [] },
            seminar: { label: "Seminar/təcrübi", plan: 30, total: 67, lines: [] },
            lab: { label: "Laboratoriya", plan: 0, total: 0, lines: [] },
        },
        extra || {}
    );
}

function render(window, data) {
    const host = window.document.querySelector("[data-wl-rows]");
    window.EMSWorkloadRender.cards(host, [].concat(data), { lecture: "Mühazirə", seminar: "Seminar/təcrübi", lab: "Laboratoriya" }, {});
    return host;
}

test("axın nömrəli sətirdir, birlikdə dinləyən qruplar yazılır, patok kartda izah olunur", () => {
    const window = boot();
    const host = render(window, card({
        lecture: { plan: 45, load_hours: 90, without_groups: [], streams: [
            stream("r1", ["236 İT", "236 K"], 45, [entry("1", "Balayev Mehdi", 45)]),
            stream("r2", ["236 YDK"], 45, [entry("2", "Səlimov İlham", 45)]),
        ] },
    }));
    const streams = host.querySelectorAll(".wl-stream");
    assert.equal(streams.length, 2);
    assert.equal(streams[0].querySelector(".wl-stream__tag").textContent, "Axın 1");
    assert.deepEqual([...streams[0].querySelectorAll(".wl-pill")].map((n) => n.textContent), ["236 İT", "236 K"]);
    assert.match(streams[0].querySelector(".wl-stream__mode").textContent, /2 qrup birlikdə/);
    assert.match(streams[1].querySelector(".wl-stream__mode").textContent, /tək qrup/);
    assert.match(host.querySelector(".wl-kind__rule").textContent, /Axın \(patok\)/);
    assert.match(host.querySelector("[data-wl-streams-open]").textContent, /Axınları dəyiş/);
    assert.equal(host.querySelector(".wl-kind--lecture .wl-kind__step").textContent, "1");
});

test("qruplar ayrıca keçirsə «axın» sözü yoxdur — «N qrup ayrıca keçir» və «Patok qur»", () => {
    const window = boot();
    const host = render(window, card({
        lecture: { plan: 45, load_hours: 90, without_groups: [], streams: [
            stream("r1", ["534 Bİ az"], 45, [entry("1", "Rəfiyev Aydın", 45)]),
            stream("r2", ["534 Bİ ing"], 45, [entry("2", "Axundlu Aynur", 45)]),
        ] },
    }));
    assert.equal(host.querySelectorAll(".wl-stream").length, 2);
    assert.equal(host.querySelector(".wl-stream__tag"), null);
    assert.equal(host.querySelector(".wl-stream__mode"), null);
    assert.equal(host.querySelector(".wl-kind__rule"), null);
    assert.match(host.querySelector(".wl-kind--lecture .wl-kind__sum").textContent, /2 qrup ayrıca keçir · müəllim yükünə cəmi 90 s/);
    assert.match(host.querySelector("[data-wl-streams-open]").textContent, /Patok qur/);
});

test("tək qruplu fəndə «axın» sözü yoxdur — yalnız mühazirəçi seçilir", () => {
    const window = boot();
    const host = render(window, card({
        groups: [{ id: "a", name: "235 KE" }],
        lecture: { plan: 30, load_hours: 30, without_groups: [], streams: [stream("r1", ["235 KE"], 30, [entry("1", "Quliyeva", 30)])] },
    }));
    assert.equal(host.querySelector(".wl-stream__tag"), null);
    assert.equal(host.querySelector(".wl-kind__rule"), null);
    assert.match(host.querySelector("[data-wl-streams-open]").textContent, /Mühazirəçi seç/);
});

test("bütün sətrə yazılmış seminar saatı TƏK xətdir — qrup xətləri «təyin olunmayıb» demir", () => {
    const window = boot();
    const shared = line("r1", "236 İT · 236 K", 15, 30, [entry("9", "Vakant", 30, { is_vacant: true })], { group_id: "", shared: true });
    const host = render(window, card({
        seminar: { label: "Seminar/təcrübi", plan: 15, total: 30, lines: [
            line("r1", "236 İT", 15, 30, []), line("r1", "236 K", 15, 30, []), shared,
        ] },
    }));
    const lines = host.querySelectorAll(".wl-kind--seminar .wl-line");
    assert.equal(lines.length, 1);
    assert.equal(lines[0].querySelector(".wl-line__group").textContent, "236 İT · 236 K");
    assert.match(lines[0].querySelector(".wl-line__plan").textContent, /2 qrup · 30 s/);
    assert.match(lines[0].querySelector(".wl-line__badges").textContent, /Qruplara ayrılmayıb/);
    assert.doesNotMatch(host.textContent, /Müəllim təyin olunmayıb/);
});

test("qarışıq sətir: boş qrup xətti «Ümumi bölgüyə daxildir», həqiqi boşluq «Müəllim təyin olunmayıb»", () => {
    const window = boot();
    const host = render(window, card({
        seminar: { label: "Seminar/təcrübi", plan: 45, total: 135, lines: [
            line("r1", "536 ML", 45, 135, [entry("1", "Orucova", 45)]),
            line("r1", "536 MU", 45, 135, []),
            line("r1", "536 ML · 536 MU", 45, 135, [entry("2", "Orucova", 90)], { group_id: "", shared: true }),
            line("r2", "536 İ", 45, 45, [], { assigned: 0, remaining: 45, is_complete: false }),
        ] },
    }));
    const lines = [...host.querySelectorAll(".wl-kind--seminar .wl-line")];
    assert.equal(lines.length, 4);
    assert.match(lines[1].textContent, /Ümumi bölgüyə daxildir/);
    assert.ok(lines[1].classList.contains("is-covered"));
    assert.match(lines[3].textContent, /Müəllim təyin olunmayıb/);
    assert.match(lines[3].querySelector(".wl-line__badges").textContent, /Bölünməyib: 45 s/);
    assert.match(host.querySelector(".wl-state").textContent, /Natamam|Bölünməyib/);
});

test("kartın vəziyyəti: tam bölünüb / vakant saat / bölünməyib", () => {
    const window = boot();
    const full = card({ lecture: { plan: 45, load_hours: 45, without_groups: [], streams: [stream("r1", ["A"], 45, [entry("1", "X", 45)])] } });
    assert.match(render(window, full).querySelector(".wl-state").textContent, /Tam bölünüb/);
    const vacant = card({
        rows: [{ id: "r1", assignments: [{ activity: "seminar", hours: 30, is_vacant: true }, { activity: "exam", hours: 5, is_vacant: true }] }],
    });
    assert.match(render(window, vacant).querySelector(".wl-state").textContent, /Vakant: 30 s/);
    const open = card({
        teaching_complete: false,
        lecture: { plan: 45, load_hours: 45, without_groups: [], streams: [stream("r1", ["A"], 45, [], { remaining: 45, is_complete: false })] },
    });
    const state = render(window, open).querySelector(".wl-state");
    assert.match(state.textContent, /Bölünməyib: 45 s/);
    assert.ok(state.classList.contains("wl-state--open"));
});

test("qardaş qruplardan fərqlənən saat «saatı yoxlayın» nişanı alır (38 / 37 — 45 / 30 əvəzinə)", () => {
    const window = boot();
    const host = render(window, card({
        lecture: { plan: 45, load_hours: 128, without_groups: [], streams: [
            stream("r1", ["534 Bİ az"], 45, [entry("1", "Rəfiyev", 45)]),
            stream("r3", ["534 MRK"], 45, [entry("3", "Quliyev", 45)]),
            stream("r2", ["534 Bİ ing"], 38, [entry("2", "Axundlu", 38)]),
        ] },
        seminar: { label: "Seminar/təcrübi", plan: 37, total: 97, lines: [
            line("r1", "534 Bİ az", 30, 30, [entry("1", "Rəfiyev", 30)]),
            line("r3", "534 MRK", 30, 30, [entry("3", "Quliyev", 30)]),
            line("r2", "534 Bİ ing", 37, 37, [entry("2", "Axundlu", 37)]),
        ] },
    }));
    const odd = [...host.querySelectorAll(".wl-badge--odd")];
    assert.equal(odd.length, 2);
    assert.match(odd[0].textContent, /digər qruplarda 45 s/);
    assert.match(odd[1].textContent, /digər qruplarda 30 s/);
    // Qiyabi qrupun az saatı səhv deyil — müqayisə təhsil forması üzrədir.
    const mixed = render(window, card({
        rows: [{ id: "r1", education_form: "eyani" }, { id: "r3", education_form: "eyani" }, { id: "q1", education_form: "qiyabi" }],
        lecture: { plan: 45, load_hours: 105, without_groups: [], streams: [
            stream("r1", ["536 ML"], 45, [entry("1", "A", 45)]),
            stream("r3", ["536 MU"], 45, [entry("3", "B", 45)]),
            stream("q1", ["2536 MU"], 15, [entry("2", "C", 15)]),
        ] },
    }));
    assert.equal(mixed.querySelectorAll(".wl-badge--odd").length, 0);
    // İki qrup, iki fərqli saat — hansının səhv olduğu bilinmir: nişan qoyulmur.
    assert.equal(window.EMSWorkloadCards.typical([45, 38]), 0);
    assert.equal(window.EMSWorkloadCards.typical([45, 45]), 0);
});

// ── Yer saxlanması ──────────────────────────────────────────────────────────
function bootAnchor() {
    const window = boot();
    const document = window.document;
    const state = { teachers: [], cards: [] };
    window.EMSWorkloadDist = {
        state,
        q: (selector) => document.querySelector('[data-profile-section-panel="workload-distribution"]').querySelector(selector),
    };
    const scrolled = [];
    window.scrollBy = (opts) => scrolled.push(opts.top);
    window.eval(ANCHOR);
    return { window, document, state, scrolled };
}

function fakeTop(node, top) {
    node.getBoundingClientRect = () => ({ top, bottom: top + 300, left: 0, right: 100, width: 100, height: 300 });
}

function drawTeachers(document, teachers) {
    document.querySelector("[data-wl-teacher-panel]").innerHTML = teachers
        .map((t) => `<button class="wl-teacher" data-wl-teacher-id="${t.teacher_id}" data-wl-teacher-name="${t.name}">` +
            `<span class="wl-teacher__name">${t.name}</span><span class="wl-teacher__numbers">${t.hours}</span></button>`)
        .join("");
}

test("yenidən çəkilişdən sonra işlənən kart eyni yerdə, açıq sətirlər açıq, dəyişən müəllim vurğulu", () => {
    const { window, document, state, scrolled } = bootAnchor();
    const cards = [card({ id: "c1", key: "k1" }), card({ id: "c2", key: "k2" })];
    state.teachers = [{ teacher_id: 7, name: "Rəfiyev Aydın", hours: 150 }, { teacher_id: 8, name: "Axundlu Aynur", hours: 330 }];
    render(window, cards);
    drawTeachers(document, state.teachers);
    let nodes = document.querySelectorAll("[data-wl-card]");
    fakeTop(nodes[0], -400);
    fakeTop(nodes[1], 180);
    nodes[1].querySelector("[data-wl-card-rows]").open = true;
    nodes[1].querySelector("[data-wl-card-rows-toggle]").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));

    const snap = window.EMSWorkloadAnchor.capture(false);
    assert.equal(snap.key, "k2");
    assert.equal(snap.top, 180);
    assert.equal(snap.open.join(","), "k2"); // jsdom massivi başqa realm-dəndir

    // Yenidən çəkiliş: kart 95px aşağı düşüb (yuxarıdakı kart böyüyüb), açıq hissə bağlanıb, bir müəllim +7 s.
    state.teachers = [{ teacher_id: 7, name: "Rəfiyev Aydın", hours: 157 }, { teacher_id: 8, name: "Axundlu Aynur", hours: 330 }];
    render(window, cards);
    drawTeachers(document, state.teachers);
    nodes = document.querySelectorAll("[data-wl-card]");
    fakeTop(nodes[0], -400);
    fakeTop(nodes[1], 275);
    window.EMSWorkloadAnchor.restore(snap);

    assert.equal(scrolled[0], 95);
    assert.equal(nodes[1].querySelector("[data-wl-card-rows]").open, true);
    assert.ok(nodes[1].classList.contains("is-updated"));
    const tiles = document.querySelectorAll("[data-wl-teacher-id]");
    assert.ok(tiles[0].classList.contains("is-changed"));
    assert.equal(tiles[0].querySelector(".wl-teacher__delta").textContent, "+7 s");
    assert.equal(tiles[1].querySelector(".wl-teacher__delta"), null);
});

test("süzgəc dəyişəndə (fresh) kart lövbəri yoxdur — səhifə tərpədilmir", () => {
    const { window, document, state, scrolled } = bootAnchor();
    render(window, [card({ id: "c1", key: "k1" })]);
    state.teachers = [{ teacher_id: 7, name: "Rəfiyev Aydın", hours: 150 }];
    drawTeachers(document, state.teachers);
    const snap = window.EMSWorkloadAnchor.capture(true);
    assert.equal(snap.key, "");
    window.EMSWorkloadAnchor.restore(snap);
    assert.equal(scrolled.length, 0);
    assert.equal(document.querySelector(".wl-teacher__delta"), null);
});

test("sağ panel axtarışı: ad ilə süzür (ə/ı fərqinə dözümlü), uyğun yoxdursa xəbər verir", () => {
    const { window, document, state } = bootAnchor();
    state.teachers = [{ teacher_id: 7, name: "Rəfiyev Aydın", hours: 150 }, { teacher_id: 8, name: "Axundlu Aynur", hours: 330 }];
    drawTeachers(document, state.teachers);
    const field = document.querySelector("[data-wl-teacher-search]");
    const type = (value) => {
        field.value = value;
        field.dispatchEvent(new window.Event("input", { bubbles: true }));
    };
    type("refiyev");
    const tiles = document.querySelectorAll("[data-wl-teacher-id]");
    assert.equal(tiles[0].classList.contains("is-filtered-out"), false);
    assert.equal(tiles[1].classList.contains("is-filtered-out"), true);
    assert.equal(document.querySelector("[data-wl-teacher-none]").hidden, true);
    type("yoxdur");
    assert.equal(document.querySelector("[data-wl-teacher-none]").hidden, false);
    type("");
    assert.equal(document.querySelectorAll(".is-filtered-out").length, 0);
});
