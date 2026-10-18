/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-18: «Alt qrupa tələbə əlavə et» — subgroup_placement_render.js ƏSL DOM-da (jsdom).
   Server mətni HTML kimi şərh OLUNMUR (textContent), kredit KPI-ları, kəsilmiş fənn çipləri, jurnal kartının
   bloklanması (bağlı / dolub / artıq orada), toqquşma xəbərdarlığı, önbaxış və tarixçədə geri götürmə düyməsi.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(
    path.join(ROOT, "apps/accounts/static/accounts/js/profile/subgroup_placement_render.js"),
    "utf8"
);

const S = {
    this_semester: "Bu semestr",
    own: "Öz fənləri",
    subgroup: "Alt qrup",
    remaining: "Qalan",
    limit: "Hədd",
    credits: "kredit",
    over_limit: "Kredit həddi keçilib",
    failed_title: "Kəsilmiş fənlər",
    failed_none: "Kəsilmiş fənn yoxdur.",
    failed_pick: "Bu fənni seç",
    current_title: "Bu semestrin fənləri",
    history_title: "Yerləşdirmə tarixçəsi",
    history_none: "Hələ yerləşdirmə olmayıb.",
    teacher: "Müəllim",
    no_teacher: "—",
    schedule: "Cədvəl",
    no_schedule: "Cədvəl hələ qurulmayıb",
    students: "tələbə",
    free: "boş yer",
    credit_impact: "Kredit",
    clash: "Toqquşma",
    no_clash: "Toqquşma yoxdur",
    clash_with: "üst-üstə düşür",
    locked: "Jurnal bağlıdır",
    already_here: "Artıq bu jurnaldadır",
    full: "Dolub",
    releases_own: "azad ediləcək",
    retake: "Təkrar",
    checks_ok: "Uyğundur",
    checks_fail: "Mümkün deyil:",
    warning: "Xəbərdarlıq",
    after: "Sonra",
    placed: "Yerləşdirildi",
    undone: "Geri götürüldü",
    undo: "Geri götür",
    document: "Sənədə bax",
    order: "Sərəncam",
    by: "Kim",
    at: "Nə vaxt",
    reason: "Səbəb",
    recent_none: "Hələ yerləşdirmə yoxdur.",
    no_offerings: "Açılmayıb",
    error: "Xəta",
};

function load() {
    const dom = new JSDOM("<!doctype html><html><body><div id='c'></div><ul id='l'></ul></body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/profil/",
    });
    dom.window.eval(SCRIPT);
    return dom.window;
}

function placement(extra) {
    return Object.assign(
        {
            id: "p1",
            student: "<b>Əliyev</b> Vəli",
            subject_name: "Fizika",
            source_group: "G2",
            target_group: "G1",
            created_at: "18.10.2026 10:00",
            actor: "Dekan",
            credits_before: 10,
            credits_after: 16,
            credit_limit: 36,
            order_number: "45/S",
            order_date: "12.10.2026",
            document_url: "/media/protected/x.pdf",
            reason: "Dekanlığın təqdimatı",
            undone: false,
            undo: null,
            retake: true,
        },
        extra || {}
    );
}

test("xülasə: kredit KPI-ları, kəsilmiş fənn çipi, alt qrup nişanı — mətn textContent ilə", () => {
    const window = load();
    const box = window.document.getElementById("c");
    window.EMSSubgroupPlacementRender.summary(
        box,
        {
            name: "<img src=x onerror=alert(1)>",
            group: "G2",
            program: "Tarix",
            period: "2025/2026 · Payız",
            credit: { total: 33, own: 27, subgroup: 6, limit: 36, remaining: 3, over_limit: false },
            failed: [{ subject_id: "s1", name: "Riyaziyyat", code: "RIY", ects: 5, last_period: "2024/2025 · Yaz" }],
            subjects: [{ subject_name: "Fizika", credits: 6, is_subgroup: true, group_name: "G1" }],
            placements: [placement()],
        },
        S,
        true
    );
    assert.equal(box.querySelector("img"), null);
    assert.match(box.querySelector(".sgp-ctx__name").textContent, /<img/);
    assert.equal(box.querySelector(".ems-kpi__value").textContent, "33 / 36");
    assert.ok(box.querySelector(".ems-kpi--accent-warning"), "3 kredit qalıb → xəbərdarlıq tonu");
    const chip = box.querySelector("[data-sgp-pick-subject]");
    assert.equal(chip.getAttribute("data-sgp-pick-subject"), "s1");
    assert.equal(chip.getAttribute("data-sgp-pick-text"), "Riyaziyyat · RIY");
    assert.match(box.querySelector(".sgp-subjects__item .ems-badge").textContent, /Alt qrup · G1/);
    assert.ok(box.querySelector("[data-sgp-undo='p1']"), "yazı icazəsi varsa geri götür düyməsi");
});

test("jurnal kartları: bağlı / dolu / artıq orada olan seçilmir, toqquşma və kredit göstərilir", () => {
    const window = load();
    const box = window.document.getElementById("c");
    const base = {
        teacher: "Müəllim A",
        slots: [{ weekday_label: "Bazar ertəsi", start: "09:00", end: "10:20", kind_label: "Mühazirə", room: "" }],
        enrolled: 12,
        free: 3,
        credits: 6,
        projection: { total_after: 16, limit: 36, fits: true },
        clashes: [],
        locked: false,
        full: false,
        already_enrolled: false,
        releases_own: false,
    };
    window.EMSSubgroupPlacementRender.offerings(
        box,
        [
            Object.assign({}, base, { id: "o1", group_name: "G1" }),
            Object.assign({}, base, { id: "o2", group_name: "G3", locked: true }),
            Object.assign({}, base, {
                id: "o3",
                group_name: "G4",
                projection: { total_after: 40, limit: 36, fits: false },
                clashes: [
                    {
                        weekday_label: "Bazar ertəsi",
                        start: "09:30",
                        end: "10:50",
                        kind_label: "Seminar",
                        room: "",
                        with_subject: "Riyaziyyat",
                        with_time: "09:00–10:20",
                    },
                ],
            }),
        ],
        S,
        "o1"
    );
    const cards = box.querySelectorAll("[data-sgp-offering]");
    assert.equal(cards.length, 3);
    assert.equal(cards[0].getAttribute("aria-checked"), "true");
    assert.ok(cards[0].classList.contains("is-selected"));
    assert.equal(cards[1].disabled, true);
    assert.match(cards[1].textContent, /Jurnal bağlıdır/);
    assert.match(cards[2].querySelector(".ems-pick__warn").textContent, /Riyaziyyat \(09:00–10:20\)/);
    assert.ok(cards[2].querySelector(".sgp-pick__credit.is-over"));
    assert.match(cards[0].textContent, /12 tələbə · 3 boş yer/);
});

test("önbaxış: imtina səbəbləri siyahı kimi, xəbərdarlıq ayrıca", () => {
    const window = load();
    const box = window.document.getElementById("c");
    const R = window.EMSSubgroupPlacementRender;
    R.checks(
        box,
        {
            ok: false,
            errors: [{ code: "credit_limit", message: "Semestr kredit həddi keçilir" }],
            warnings: [{ code: "schedule_clash", message: "Toqquşur" }],
            projection: { total_after: 40, limit: 36, fits: false },
            retake: false,
        },
        S
    );
    assert.ok(box.querySelector(".ems-banner--danger"));
    assert.equal(box.querySelector(".sgp-checks__list li").textContent, "Semestr kredit həddi keçilir");
    assert.match(box.querySelector(".ems-banner--warning").textContent, /Xəbərdarlıq: Toqquşur/);
    assert.ok(box.querySelector(".sgp-checks__credit.is-over"));
    R.checks(box, { ok: true, errors: [], warnings: [], projection: { total_after: 16, limit: 36, fits: true } }, S);
    assert.ok(box.querySelector(".ems-banner--success"));
});

test("tarixçə: geri götürülmüş sətirdə düymə yoxdur, iz yazılır; boş siyahı mətni", () => {
    const window = load();
    const list = window.document.getElementById("l");
    const R = window.EMSSubgroupPlacementRender;
    R.history(
        list,
        [placement({ undone: true, undo: { created_at: "19.10.2026", actor: "Dekan", reason: "Səhv" } })],
        S,
        { canWrite: true }
    );
    assert.equal(list.querySelector("[data-sgp-undo]"), null);
    assert.match(list.querySelector(".sgp-history__undo").textContent, /Səhv/);
    assert.equal(list.querySelector(".sgp-history__doc").getAttribute("href"), "/media/protected/x.pdf");
    R.history(list, [], S, {});
    assert.equal(list.querySelector(".sgp-history__empty").textContent, S.recent_none);
    R.history(list, [placement()], S, { canWrite: false });
    assert.equal(list.querySelector("[data-sgp-undo]"), null, "yazı icazəsi yoxdursa düymə yoxdur");
});
