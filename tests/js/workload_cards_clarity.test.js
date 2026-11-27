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
     • qardaş qruplardan fərqlənən saat (45 əvəzinə 38, 30 əvəzinə 37) neytral müqayisə ilə göstərilir;
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
const EXPLORER = fs.readFileSync(path.join(JS_DIR, "workload_card_explorer.js"), "utf8");
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
    window.eval(EXPLORER);
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
    assert.match(host.querySelector(".wl-kind--lecture .wl-kind__sum").textContent, /2 qrup ayrıca keçir · Plan 90 s · bölünüb 90 s · qalıq 0 s/);
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

test("qardaş qruplardan fərqlənən saat neytral müqayisə ilə göstərilir (38 / 37 — 45 / 30 əvəzinə)", () => {
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
    assert.match(odd[0].textContent, /Digər qruplarda 45 s/);
    assert.match(odd[1].textContent, /Digər qruplarda 30 s/);
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

function bigCard() {
    const lines = Array.from({ length: 25 }, (_, i) => {
        const n = i + 1;
        return line("row-" + n, "Qrup-" + n, 30, 30, [entry("id-" + n, n === 25 ? "Rəfiyev Əli" : "Müəllim " + n, 30)]);
    });
    return card({
        groups: lines.map(item => ({ id: item.group_id, name: item.label })),
        seminar: { total: 750, lines }, lab: { total: 750, lines },
    });
}

function searchCard(window, host, query) {
    const input = host.querySelector("[data-wl-card-search]");
    input.value = query;
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
    return input;
}

test("25 seminar və laboratoriya bölgüsü dörd nəticədən başlayır, bütün sətrlər və ayrıca müəllim tapılır", () => {
    const window = boot();
    const data = bigCard();
    const host = render(window, data);
    const seminar = ".wl-kind--seminar";
    const lab = ".wl-kind--lab";
    const visible = kind => [...host.querySelectorAll(kind + " .wl-line:not([hidden])")];
    const toggle = kind => host.querySelector(kind + " > [data-wl-preview-toggle]");
    assert.equal(visible(seminar).length, 4);
    assert.equal(visible(lab).length, 4);
    const button = toggle(seminar);
    assert.equal(button.getAttribute("aria-expanded"), "false");
    assert.equal(host.querySelector(".wl-card__group-list").open, false);
    button.click();
    assert.equal(visible(seminar).length, 25);
    assert.equal(button.getAttribute("aria-expanded"), "true");
    assert.equal(visible(lab).length, 4);
    searchCard(window, host, "refiyev eli");
    assert.deepEqual(visible(seminar).map(row => row.dataset.rowId), ["row-25"]);
    assert.equal(host.querySelector("[data-wl-search-status]").textContent, "2 nəticə");
    assert.equal(visible(lab)[0].querySelector("[data-wl-assign-edit]").dataset.assignmentId, "id-25");
    assert.equal(toggle(seminar).hidden, true);
    searchCard(window, host, "Heç bir uyğun qrup");
    assert.equal(host.querySelector(seminar).hidden, true);
    assert.equal(host.querySelector("[data-wl-search-status]").textContent, "Uyğun nəticə tapılmadı.");
    assert.equal(host.querySelector("[data-wl-card-rows]").hidden, false);
    searchCard(window, host, "qrup-25");
    const updated = render(window, data);
    assert.equal(updated.querySelector("[data-wl-card-search]").value, "qrup-25");
    assert.equal(visible(seminar).length, 1);
    searchCard(window, host, "");
    assert.equal(visible(seminar).length, 25);
    toggle(seminar).click();
    assert.equal(visible(seminar).length, 4);
    searchCard(window, host, "qrup-20");
    window.EMSWorkloadRender.cards(host, [data], {}, { fresh: true, teacher: "id-25" });
    assert.equal(host.querySelector("[data-wl-card-search]").value, "");
    assert.equal(visible(seminar).length, 4);
    assert.ok(visible(seminar).some(row => row.querySelector(".is-match")));
});

test("mənbə sətri, axın və alt qrupun bölgüsü öz həqiqi cəmini saxlayır", () => {
    const window = boot();
    const data = card({
        groups: [{ id: "A", name: "A" }, { id: "B", name: "B" }],
        rows: [{ id: "r1", groups: [{ id: "A", name: "A" }, { id: "B", name: "B" }] }],
        seminar: { total: 60, lines: [
            line("r1", "A", 30, 60, [entry("1", "Müəllim", 24)], { assigned: 24, remaining: 36 }),
            line("r1", "B", 30, 60, [], { assigned: 24, remaining: 36 }),
        ] },
        lab: { total: 20, lines: [line("r1", "A · B", 20, 20, [entry("2", "Müəllim", 20)], { joint: true, group_id: "" })] },
        lecture: { load_hours: 22, streams: [
            stream("r1", ["A", "B"], 22, [], { assigned: 18, remaining: 4 }),
            stream("r2", ["Kənar"], 27, [], { orphan: true, assigned: 27, remaining: 27 }),
        ] },
    });
    const host = render(window, data);
    assert.match(host.querySelector(".wl-kind--seminar .wl-kind__sum").textContent, /2 qrup · Plan 60 s · bölünüb 24 s · qalıq 36 s/);
    assert.match(host.querySelector(".wl-kind--lab .wl-kind__sum").textContent, /2 qrup · Plan 20 s · bölünüb 20 s · qalıq 0 s/);
    assert.match(host.querySelector(".wl-kind--lecture .wl-kind__sum").textContent, /Plan 22 s · bölünüb 18 s · qalıq 4 s/);
    assert.match(host.querySelector(".wl-state").textContent, /40 s/);
    assert.equal(host.querySelector("[data-wl-card-search]"), null);
    const source = host.querySelector("[data-wl-card-rows-toggle]");
    assert.equal(host.querySelector("[data-wl-card-rows]").id, source.getAttribute("aria-controls"));
    assert.match(source.textContent, /Plan sətirləri \(1\)/);
});

test("bir qrupun seminar və lab alt qrup planları, çox müəllim və seçilən bölgünün redaktə hədəfi", () => {
    const window = boot();
    const groups = [{ id: "G", name: "G" }];
    const names = Array.from({ length: 9 }, (_, i) => entry(String(i + 1), "Şəxs " + (i + 1), 10, { sub_number: i + 1 }));
    const lines = [line("r", "G", 30, 90, names, { sections: [{ number: 9, label: "Lab Son" }] })];
    const data = card({ groups, rows: [{ id: "r", groups, subgroup_count: 2, lab_group_count: 4 }],
        seminar: { total: 90, lines }, lab: { total: 90, lines } });
    const host = render(window, data);
    assert.ok(host.querySelector(".wl-card--simple .wl-lines--simple"));
    assert.match(host.querySelector(".wl-kind--seminar .wl-line__badges").textContent, /Planda 2 alt qrup/);
    assert.match(host.querySelector(".wl-kind--lab .wl-line__badges").textContent, /Planda 4 alt qrup/);
    const list = host.querySelector(".wl-kind--lab .wl-line__entries");
    assert.equal(list.querySelectorAll(".wl-chip:not([hidden])").length, 4);
    searchCard(window, host, "sexs 9");
    assert.equal(list.querySelectorAll(".wl-chip:not([hidden])").length, 1);
    const chip = list.querySelector(".wl-chip:not([hidden])");
    assert.equal(chip.querySelector("[data-wl-assign-edit]").dataset.assignmentId, "9");
    assert.equal(chip.querySelector(".wl-chip__section").textContent, "Lab Son");
    searchCard(window, host, "");
    list.querySelector("[data-wl-preview-toggle]").click();
    assert.equal(list.querySelectorAll(".wl-chip:not([hidden])").length, 9);
    window.EMSWorkloadRender.cards(host, [card({ id: "extra", key: "extra" })], {}, { append: true });
    assert.equal(list.querySelectorAll(".wl-chip:not([hidden])").length, 9);
    assert.equal(host.querySelectorAll("[data-wl-card-search]").length, 1);
});

test("birgə axında və seminar sətrində 25 qrupun sonuncusu da axtarılır", () => {
    const window = boot();
    const groups = Array.from({ length: 25 }, (_, i) => ({ id: "Q" + i, name: "Q" + i }));
    const names = groups.map(g => g.name);
    const data = card({ groups, rows: [{ id: "r", groups }],
        lecture: { load_hours: 20, streams: [stream("r", names, 20, [entry("a", "Mahir", 20)])] },
        seminar: { total: 20, lines: [line("r", names.join(" · "), 20, 20, [entry("b", "Nigar", 20)], { joint: true, group_id: "" })] },
    });
    const host = render(window, data);
    const displayed = () => [...host.querySelectorAll(".wl-kind .wl-pill:not([hidden])")].map(node => node.textContent);
    assert.equal(displayed().length, 8);
    searchCard(window, host, "q24");
    assert.deepEqual(displayed(), ["Q24", "Q24"]);
    searchCard(window, host, "Mahir");
    assert.equal(host.querySelector(".wl-kind--seminar").hidden, true);
    assert.equal(host.querySelector(".wl-kind--lecture .wl-stream__groups [data-wl-preview-toggle]").hidden, false);
});
