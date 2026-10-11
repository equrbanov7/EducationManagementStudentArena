/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-10: «Jurnal təmizliyi» paneli — journal_hygiene_render.js ƏSL DOM-da (jsdom).
   Server mətni HTML kimi şərh OLUNMUR (textContent), seçim vəziyyəti çek-qutulara düşür, tarixçədə
   yalnız geri qaytarıla bilən qərar seçilir, sıfır saylı çip gizlənir, önizləmə xülasəsi qurulur.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(
    path.join(ROOT, "apps/accounts/static/accounts/js/profile/journal_hygiene_render.js"),
    "utf8"
);

const I18N = {
    has_data: "Məlumat var",
    no_data: "Boş",
    absence: "{n} saat qayıb",
    journal_closed: "Jurnal bağlıdır",
    chip_all: "Hamısı",
    active: "Qüvvədədir",
    reverted: "Geri qaytarılıb",
    not_revertable: "Status dəyişib",
    prev: "Əvvəlki",
    next: "Sonrakı",
    page: "Səhifə {page} / {pages} · {total} sətir",
    rows: "Sətir",
    journals: "Jurnal",
    students: "Tələbə",
    with_evidence: "Məlumatı olan",
    new_status: "Yeni status",
    evidence_totals: "Qeydiyyatlardakı məlumat",
    no_evidence: "Heç nə yoxdur",
    journal_list: "Toxunulan jurnallar",
    journal_more: "və daha {n} jurnal",
    rows_unit: "sətir",
    missing: "{n} sətir artıq siyahıda deyil",
    blocked: "{n} sətirdə məlumat var",
    sources: { marks: "Dərs xanası" },
};

function load() {
    const dom = new JSDOM("<!doctype html><html><body><table><tbody id='b'></tbody></table><div id='c'></div></body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/profil/",
    });
    dom.window.eval(SCRIPT);
    return dom.window;
}

function row(extra) {
    return Object.assign(
        {
            id: "e1",
            student: "<b>Vəliyev</b> Əli",
            username: "ali.veliyev",
            subject: "JH-1 — Alqoritmlər",
            group: "JH-101",
            period: "2026/2027 · Payız",
            reason: "expelled",
            reason_label: "Xaric olunub",
            tags: [{ code: "group_changed", label: "Qrupu dəyişib" }],
            strong: true,
            strength_label: "Güclü siqnal",
            has_evidence: false,
            absence_hours: 4,
            journal_closed: false,
            status_label: "Qeydiyyatlı",
        },
        extra || {}
    );
}

test("sətirlər textContent ilə qurulur, seçim çek-qutuya düşür", () => {
    const window = load();
    const R = window.EMSJournalHygieneRender;
    const tbody = window.document.getElementById("b");
    R.rowsBody(tbody, [row(), row({ id: "e2", strong: false })], {
        selection: new Set(["e2"]),
        canSelect: true,
        i18n: I18N,
    });
    const rows = tbody.querySelectorAll("tr[data-jh-row]");
    assert.equal(rows.length, 2);
    assert.equal(tbody.querySelector("b"), null, "server mətni HTML kimi şərh olunmamalıdır");
    assert.ok(rows[0].textContent.includes("<b>Vəliyev</b> Əli"));
    assert.ok(rows[0].classList.contains("is-strong"));
    assert.equal(rows[0].querySelector("[data-jh-check]").checked, false);
    assert.equal(rows[1].querySelector("[data-jh-check]").checked, true);
    assert.ok(rows[0].textContent.includes("Qrupu dəyişib"));
    assert.ok(rows[0].textContent.includes("4 saat qayıb"));
});

test("oxu rejimində çek-qutular bağlıdır; tarixçədə yalnız geri qaytarıla bilən seçilir", () => {
    const window = load();
    const R = window.EMSJournalHygieneRender;
    const tbody = window.document.getElementById("b");
    R.rowsBody(tbody, [row()], { selection: new Set(), canSelect: false, i18n: I18N });
    assert.equal(tbody.querySelector("[data-jh-check]").disabled, true);

    const history = [
        { id: "d1", reverted: false, can_revert: true, student: "A", from_label: "Qeydiyyatlı", to_label: "Dondurulub", to_status: "suspended", category_label: "Ayrılmış tələbə", reason_label: "Xaric olunub", decided_by: "RİM", reason: "Səbəb" },
        { id: "d2", reverted: true, can_revert: false, reverted_at: "10.10.2026 12:00", reverted_by: "RİM", student: "B", from_label: "Qeydiyyatlı", to_label: "Çıxarılıb", to_status: "dropped", category_label: "Boş fənn", reason_label: "Mənbəsi bəlli deyil" },
    ];
    R.historyBody(tbody, history, { selection: new Set(), canSelect: true, i18n: I18N });
    const boxes = tbody.querySelectorAll("[data-jh-check]");
    assert.equal(boxes[0].disabled, false);
    assert.equal(boxes[1].disabled, true);
    assert.ok(tbody.querySelectorAll("tr")[1].classList.contains("is-reverted"));
    assert.ok(tbody.textContent.includes("Geri qaytarılıb"));
});

test("çiplər: sıfır saylı gizlənir, «yoxlanmalı» = cəm − güclü, aktiv çip basılıdır", () => {
    const window = load();
    const R = window.EMSJournalHygieneRender;
    const box = window.document.getElementById("c");
    const options = [
        { value: "expelled", label: "Xaric olunub" },
        { value: "graduated", label: "Məzun olub" },
        { value: "review", label: "Yoxlanmalı" },
    ];
    R.chips(box, options, { total: 5, strong: 3, expelled: 3, graduated: 0 }, "expelled", I18N);
    const chips = Array.from(box.querySelectorAll("[data-jh-chip]"));
    assert.deepEqual(
        chips.map((chip) => chip.getAttribute("data-jh-chip")),
        ["", "expelled", "review"]
    );
    assert.equal(chips[1].getAttribute("aria-pressed"), "true");
    assert.ok(chips[2].textContent.endsWith("· 2"));
});

test("önizləmə xülasəsi və səhifələmə", () => {
    const window = load();
    const R = window.EMSJournalHygieneRender;
    const box = window.document.getElementById("c");
    R.preview(
        box,
        {
            rows: 3,
            journals: 14,
            students: 3,
            with_evidence: 1,
            to_label: "Dondurulub",
            missing: 1,
            blocked_total: 0,
            evidence_totals: { marks: 2 },
            journal_list: [{ subject: "JH-1", group: "JH-101", period: "Payız", rows: 2 }],
        },
        I18N
    );
    assert.ok(box.textContent.includes("1 sətir artıq siyahıda deyil"));
    assert.ok(box.textContent.includes("Dərs xanası: 2"));
    assert.ok(box.textContent.includes("JH-1 · JH-101 · Payız — 2 sətir"));
    assert.ok(box.textContent.includes("və daha 13 jurnal"));

    R.pager(box, { total: 120, page: 2, num_pages: 3, has_previous: true, has_next: true }, I18N);
    const buttons = box.querySelectorAll("[data-jh-page]");
    assert.equal(buttons[0].getAttribute("data-jh-page"), "1");
    assert.equal(buttons[1].getAttribute("data-jh-page"), "3");
    assert.ok(box.textContent.includes("Səhifə 2 / 3 · 120 sətir"));
    R.pager(box, { total: 0 }, I18N);
    assert.equal(box.textContent, "");
});

/* Sahib 2026-10-11: «Keçirilməyən fənlər» — sətirdə açılışın tələbə sayı, önizləmədə yarımçıq açılış xəbərdarlığı. */
test("keçirilməyən fənn: tələbə sayı və yarımçıq açılış xəbərdarlığı", () => {
    const window = load();
    const R = window.EMSJournalHygieneRender;
    const i18n = Object.assign({}, I18N, { group_size: "açılışda {n} tələbə", partial: "{n} açılış yarımçıq seçilib" });
    const tbody = window.document.getElementById("b");
    R.rowsBody(tbody, [row({ group_size: 12, has_evidence: true })], { selection: new Set(), canSelect: true, i18n: i18n });
    assert.match(tbody.textContent, /açılışda 12 tələbə/);

    const box = window.document.getElementById("c");
    R.preview(box, { rows: 2, journals: 1, students: 2, with_evidence: 2, to_label: "Tərk edib", partial_total: 1, evidence_totals: {}, journal_list: [] }, i18n);
    assert.match(box.textContent, /1 açılış yarımçıq seçilib/);
    assert.equal(box.querySelectorAll(".ems-msg--error").length, 1);
});
