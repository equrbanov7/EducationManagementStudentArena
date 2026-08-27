"""Markdown hesabatının qurulması (Azərbaycan dilində, sahib üçün)."""

from __future__ import annotations

import datetime

from .analysis import (
    DOMAIN_LABELS,
    DOMAINS,
    fmt_duration,
    fmt_int,
    fmt_pct,
    fmt_signed,
    ladder_table,
    md_table,
)
from .collect import out_of_scope_cells
from .render_detail import render_finals, render_quality, render_sample

# §1.2 üçün: ledger varlığı → onu doğuran mənbə cədvəli (yoxsa törəmə varlıqdır).
LEDGER_SOURCE_TABLE = {
    "course_offering": "journals",
    "curriculum_plan": "curricula",
    "curriculum_plan_row": "curricula_plan",
    "department_unit": "departments",
    "group_unit": "groups",
    "lesson": "journals_dates_added_by_teacher",
    "lesson_subject": "lessons",
    "speciality_unit": "speciality",
    "student": "students",
    "worker": "workers",
    "journal_reconcile": "yekun",
}

# J8 ``yekun`` sətirlərindən əlavə 4 yoxlama möhürü də yazır (``a-…`` açarları).
LEDGER_EXTRA_SEALS = {"journal_reconcile": 4}

# §2 üçün: mənbə cədvəli/ifadəsi → hədəf sayğacı → izah.
ENTITY_MATRIX = (
    (
        "Fakültə / kafedra (OrgUnit)",
        "departments",
        ("orgunit_faculty", "orgunit_department"),
        "Legacy `departments` düz siyahıdır; hədəfdə fakültə/kafedra iyerarxiyasına yığılır — say azalır.",
    ),
    ("İxtisas (OrgUnit)", "speciality", ("orgunit_specialty",), "Bire-bir."),
    (
        "İxtisas proqramı (Program)",
        "speciality",
        ("program",),
        "Bir ixtisas bakalavr/magistr üzrə ayrı proqrama bölünür → hədəfdə ÇOX olur.",
    ),
    (
        "Kurikulum (Curriculum)",
        "curricula",
        ("curriculum",),
        "Hədəfdə kurikulum (proqram + qəbul ili) cütünə görə açılır → say arta bilər.",
    ),
    (
        "Kurikulum fənni",
        "curricula_plan",
        ("curriculum_subject",),
        "Seçmə bloklar və istinad açılmaları sayı dəyişir (`legacy_plan_*` problem kodlarına bax).",
    ),
    (
        "Fənn (Subject)",
        "lessons",
        ("subject",),
        "Eyni adlı legacy fənlər bir Subject-ə birləşə bilər → hədəfdə az olur.",
    ),
    ("Qrup (OrgUnit)", "groups", ("orgunit_group",), "Bire-bir."),
    (
        "Tələbə (auth.user)",
        "students",
        ("auth_user",),
        "Hədəfə müəllim/işçi hesabları da daxildir — aşağıdakı rol cədvəlinə bax.",
    ),
    ("Müəllim / işçi", "workers", (), "Rol cədvəlində ayrıca görünür."),
    (
        "Jurnal → açılış (CourseOffering)",
        "journals",
        ("course_offering",),
        "⚠️ Gözləntinin ƏKSİ: eyni fənn+qrup+dövr üçün bir neçə legacy jurnal BİR açılışa BİRLƏŞİR (`legacy_journal_offering_merged`) → hədəfdə AZ olur, çox yox.",
    ),
    (
        "Dərs (Lesson)",
        "journals_dates_added_by_teacher",
        ("lesson",),
        "Eyni slot üçün bir neçə müəllim sətri bir dərsə düşür (`legacy_journal_lesson_duplicate`) → hədəfdə az olur.",
    ),
    (
        "Yekun cədvəli (`yekun`)",
        "yekun",
        ("finalgrade",),
        "Hədəfdə FinalGrade jurnalın `im` xanasından da doğur — `yekun` cədvəli yeganə mənbə deyil.",
    ),
)

QUALITY_LABELS_SOURCE = {
    "students_no_name": "Adı və ya soyadı boş olan tələbə",
    "students_no_group": "Qrupu olmayan tələbə",
    "students_orphan_group": "Mövcud olmayan qrupa istinad edən tələbə (orfan)",
    "students_dup_fincode": "Təkrarlanan FİN (dublikat namizədi)",
    "students_dup_name": "Eyni ad+soyad+ata adı (dublikat namizədi)",
    "workers_no_name": "Adı və ya soyadı boş olan işçi",
    "journals_no_teacher": "Müəllimi olmayan jurnal",
    "journals_orphan_teacher": "Mövcud olmayan müəllimə istinad edən jurnal (orfan)",
    "journals_orphan_lesson": "Mövcud olmayan fənnə istinad edən jurnal (orfan)",
    "journals_dup_uniqid": "Təkrarlanan jurnal `uniqid`",
    "groups_orphan_speciality": "Mövcud olmayan ixtisasa istinad edən qrup (orfan)",
    "yekun_orphan_journal": "Mövcud olmayan jurnala istinad edən `yekun` sətri",
    "yekun_orphan_student": "Mövcud olmayan tələbəyə istinad edən `yekun` sətri",
}

QUALITY_LABELS_TARGET = {
    "user_no_name": "Adı və ya soyadı boş olan hesab",
    "student_no_record": "Akademik qeydi (SAR) olmayan tələbə",
    "record_no_group": "Qrupsuz akademik qeyd",
    "offering_no_instructor": "Müəllimsiz açılış",
    "lesson_no_offering": "Açılışsız dərs",
    "mark_orphan_enrollment": "Yazılışı olmayan bal xanası (orfan)",
    "mark_orphan_lesson": "Dərsi olmayan bal xanası (orfan)",
    "score_orphan_component": "Komponenti olmayan komponent balı (orfan)",
    "enrollment_dup": "Təkrarlanan yazılış (açılış + tələbə)",
    "record_dup": "Eyni tələbənin iki aktiv akademik qeydi",
    "subject_dup_name": "Eyni adlı fənn (dublikat namizədi)",
    "offering_dup": "Eyni fənn+qrup+dövr üçün iki açılış",
    "mark_dup": "Eyni yazılış+dərs üçün iki bal xanası",
}


def render_report(*, context: dict) -> str:
    """Bütün bölmələri birləşdirən Markdown mətni."""

    parts = [
        _header(context),
        _summary(context),
        _row_accounting(context),
        _entity_matrix(context),
        render_sample(context),
        render_finals(context),
        render_quality(context, QUALITY_LABELS_SOURCE, QUALITY_LABELS_TARGET),
        _issues(context),
        _timings(context),
    ]
    return "\n\n".join(part for part in parts if part) + "\n"


def _header(context: dict) -> str:
    run = context["target"]["run"]
    lines = [
        "# Legacy → EMS Arena köçürmə uzlaşdırma hesabatı",
        "",
        "> Bu «testlər keçdi» hesabatı DEYİL.  Bu, **hər mənbə xanasına nə olduğunun**",
        "> mühasibatıdır.  Tutmayan hər rəqəm aşağıda **İZAH OLUNMAMIŞ FƏRQ** kimi",
        "> açıq göstərilir — gizlədilmir.",
        "",
        "**Rejim:** hər iki bazaya YALNIZ OXU (`SET TRANSACTION READ ONLY`).  Heç bir",
        "`INSERT` / `UPDATE` / `DELETE` icra olunmur.",
        "",
    ]
    meta = [
        ["Hesabat vaxtı", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ["Mənbə (MariaDB)", f"`{context['source_label']}`"],
        ["Hədəf (PostgreSQL)", f"`{context['target_label']}`"],
    ]
    if run:
        mode, status, snapshot, source_rows, started, finished = run[0], run[1], run[2], run[3], run[4], run[5]
        meta += [
            ["Repetisiya rejimi / statusu", f"`{mode}` / `{status}`"],
            ["Snapshot SHA-256", f"`{snapshot[:16]}…`"],
            ["Ledger-in gördüyü mənbə sətri", fmt_int(source_rows)],
            ["Başlama → bitmə", f"{started} → {finished}"],
        ]
    lines.append(md_table(["Sahə", "Dəyər"], meta))
    return "\n".join(lines)


def _summary(context: dict) -> str:
    ladders = context["ladders"]
    source_cells = sum(ladder.source_total for ladder in ladders.values()) + out_of_scope_cells(context["source"])
    target_cells = sum(ladder.target for ladder in ladders.values())
    unexplained = sum(ladder.unexplained for ladder in ladders.values())
    verdict = "✅ Bütün domenlər tutur" if unexplained == 0 else f"🔴 {fmt_int(abs(unexplained))} sətir izahsızdır"
    rows = [
        ["Mənbə jurnal xanası (canlı + arxiv, xam)", fmt_int(source_cells), "100 %"],
        ["Hədəfdə yaradılan sətir", fmt_int(target_cells), fmt_pct(target_cells, source_cells)],
        [
            "İzah olunmuş fərq (boş / oxunmayan / orphan / dublikat / həll olunmayan)",
            fmt_int(source_cells - target_cells - unexplained),
            fmt_pct(source_cells - target_cells - unexplained, source_cells),
        ],
        ["**İZAH OLUNMAMIŞ FƏRQ**", f"**{fmt_signed(unexplained)}**", fmt_pct(abs(unexplained), source_cells)],
    ]
    return "\n".join(
        [
            "## 0. Bir baxışda",
            "",
            md_table(["Göstərici", "Say", "Mənbənin %-i"], rows),
            "",
            f"**Nəticə:** {verdict}.",
            "",
            "### Ən diqqətçəkən rəqəmlər",
            "",
            _highlights(context),
        ]
    )


def _role_count(context: dict, role: str, *, active: bool) -> int:
    for name, active_count, inactive_count in context["target"]["roles"]:
        if name == role:
            return active_count if active else inactive_count
    return 0


def _highlights(context: dict) -> str:
    """Sahibin ilk baxışda görməli olduğu 5-6 rəqəm."""

    ledger: dict = {}
    for entity_type, state, count in context["target"]["ledger_states"]:
        ledger.setdefault(entity_type, {})[state] = count
    offering = ledger.get("course_offering", {})
    enrollment = ledger.get("journal_enrollment", {})
    counts = context["target"]["entity_counts"]
    issues = {rule: count for _table, rule, _severity, count in context["target"]["issues"]}
    lines = [
        f"1. **{fmt_int(enrollment.get('skipped', 0))}** jurnal-yazılışı ötürülüb "
        f"({fmt_pct(enrollment.get('skipped', 0), sum(enrollment.values()))}) — əsas səbəb "
        f"`legacy_journal_student_inactive` ({fmt_int(issues.get('legacy_journal_student_inactive', 0))} hadisə). "
        "Həmin tələbələrin bal xanaları da hədəfə düşmür.",
        f"2. **{fmt_int(offering.get('skipped', 0) + offering.get('quarantined', 0))}** legacy jurnal açılışa "
        "çevrilməyib; onlara bağlı bütün xanalar nərdivanda «orphan jurnal» pilləsindədir.",
        f"3. **{fmt_int(_role_count(context, 'student', active=False))}** tələbə arxiv üzvlüyü ilə köçüb "
        f"(aktiv: {fmt_int(_role_count(context, 'student', active=True))}) — heç bir hesab silinməyib.",
        f"4. **{fmt_int(counts.get('lessonmark_absent', 0))}** qayıb və "
        f"**{fmt_int(counts.get('lessonmark_present', 0))}** iştirak xanası davamiyyət kimi oturub; "
        f"bal daşıyan xana isə **{fmt_int(counts.get('lessonmark_scored', 0))}**.",
        f"5. `yekun` cədvəlinin **{fmt_int(context['finals']['unresolved'])}** sətri hədəfdəki yazılışa "
        "bağlana bilməyib (yazılış köçürülmədiyi üçün).",
    ]
    stray = out_of_scope_cells(context["source"])
    if stray:
        lines.append(
            f"6. **{fmt_int(stray)}** xana heç bir domenə düşmür (naməlum `month_id`) — "
            "import-un say balansı onları görmür, bu hesabat görür (§1.3)."
        )
    return "\n".join(lines)


def _row_accounting(context: dict) -> str:
    """§1 — ən vacib bölmə: hər domen üçün mənbədən hədəfə nərdivan."""

    source = context["source"]
    target = context["target"]
    lines = ["## 1. Sətir mühasibatı", "", "### 1.1 Mənbə cədvəllərinin xam sayları", ""]
    lines.append(
        md_table(
            ["Mənbə cədvəli", "Sətir sayı"],
            [[f"`{table}`", fmt_int(count)] for table, count in sorted(source["table_counts"].items())],
        )
    )

    lines += [
        "",
        "### 1.2 Struktur varlıqları — ledger möhürləri",
        "",
        "Ledger hər mənbə sətri üçün bir möhür saxlayır: `migrated` / `skipped` /",
        "`quarantined`.  «Mənbə sətri» sütunu bu hesabatın MÜSTƏQİL saydığı xam",
        "sətir sayıdır: möhür cəmi ona bərabər olmalıdır, yoxsa sətir səssizcə",
        "itib.",
        "",
    ]
    ledger: dict = {}
    for entity_type, state, count in target["ledger_states"]:
        ledger.setdefault(entity_type, {})[state] = count
    rows = []
    for entity_type in sorted(ledger):
        states = ledger[entity_type]
        total = sum(states.values())
        expected_table = LEDGER_SOURCE_TABLE.get(entity_type)
        expected = source["table_counts"].get(expected_table) if expected_table else None
        extra = LEDGER_EXTRA_SEALS.get(entity_type, 0)
        if expected is None:
            verdict, expected_text = "— (törəmə varlıq)", "—"
        else:
            verdict = "✅ tutur" if total == expected + extra else f"🔴 {fmt_signed(total - expected - extra)}"
            expected_text = f"`{expected_table}` = {fmt_int(expected)}"
        rows.append(
            [
                f"`{entity_type}`",
                expected_text,
                fmt_int(total),
                fmt_int(states.get("migrated", 0)),
                fmt_int(states.get("skipped", 0)),
                fmt_int(states.get("quarantined", 0)),
                verdict,
            ]
        )
    lines.append(
        md_table(
            ["Varlıq", "Mənbə sətri", "Möhür cəmi", "Köçürülən", "Ötürülən", "Karantin", "Tutur?"],
            rows,
        )
    )

    lines += [
        "",
        "### 1.3 Jurnal xanaları — mənbədən hədəfə nərdivan",
        "",
        "Bu, hesabatın **ürəyidir**.  Hər pillə mənbə sayından nə qədər və NİYƏ",
        "çıxıldığını göstərir; sonuncu sətir tutmayan qalığı açıq elan edir.",
    ]
    if not source["cells_by_enrollment"]:
        lines += [
            "",
            "> ⚠️ `--skip-deep` ilə işlədilib: orphan / dublikat / həll olunmayan yazılış",
            "> pillələri hesablanmayıb, ona görə qalıq süni şəkildə böyükdür.",
        ]
    for domain in DOMAINS:
        ladder = context["ladders"][domain]
        lines += [
            "",
            f"#### {DOMAIN_LABELS[domain]}",
            "",
            md_table(["Pillə", "Dəyişiklik", "Qalıq"], ladder_table(ladder)),
        ]

    if source["cells_by_enrollment"]:
        lines += ["", "#### Qalan izahsız fərq haqqında", "", _residual_note(context)]

    stray = out_of_scope_cells(source)
    if stray:
        lines += [
            "",
            "#### ⚠️ Heç bir domenə düşməyən xanalar",
            "",
            f"Mənbədə **{fmt_int(stray)}** xananın `month_id` kodu nə təqvim ayı, nə",
            "`k1/k2/k3/si`, nə də `im/im2`-dir.  İmport-un say balansı bu sətirləri",
            "tamamilə kənarda saxlayır — bu hesabat onları GÖRÜNƏN edir.",
        ]
    return "\n".join(lines)


def _residual_note(context: dict) -> str:
    """Qalıq sıfır deyilsə — nə OLA BİLƏR və növbəti addım nədir (fərziyyə kimi)."""

    ladders = context["ladders"]
    total = sum(ladder.unexplained for ladder in ladders.values())
    if total == 0:
        return "✅ Hər üç domen tam tutur — mənbənin hər xanası ya hədəfdədir, ya da adlandırılmış səbəblə çıxılıb."
    source_total = sum(ladder.source_total for ladder in ladders.values())
    issues = {rule: count for _table, rule, _severity, count in context["target"]["issues"]}
    return "\n".join(
        [
            f"Qalıq **{fmt_signed(total)}** sətirdir (mənbənin {fmt_pct(abs(total), source_total)}-i).",
            "Bu hesabat onu **fərziyyə ilə bağlamır** — açıq qalıq kimi saxlayır.  Ən ehtimallı",
            "mənbələr (yoxlanılmalıdır, sübut deyil):",
            "",
            "1. **Dərs slotu tapılmayan bal xanası** — bir `LessonMark` yalnız mövcud `Lesson`-a",
            "   bağlana bilər; xananın (ay, gün, saat) slotu üçün `journals_dates_added_by_teacher`",
            "   sətri yoxdursa xana yazılmır.  Ledger-də bunun izi: "
            f"`legacy_journal_lesson_orphan` = {fmt_int(issues.get('legacy_journal_lesson_orphan', 0))}.",
            "2. **Hədəf toqquşması** — eyni (yazılış, dərs) cütü üçün ikinci xana yazıla bilmir "
            f"(`legacy_journal_mark_target_conflict` = {fmt_int(issues.get('legacy_journal_mark_target_conflict', 0))}).",
            "3. **Üzrlü qayıb çevrilməsi** — `excusable` bayrağı olan xanalar `excused` statusuna "
            f"düşür (`legacy_journal_mark_excused` = {fmt_int(issues.get('legacy_journal_mark_excused', 0))}).",
            "",
            "Növbəti addım: bu üç ehtimalı ayrıca sorğu ilə ölçüb nərdivana yeni pillə kimi əlavə etmək.",
        ]
    )


def _entity_matrix(context: dict) -> str:
    source_counts = context["source"]["table_counts"]
    target_counts = context["target"]["entity_counts"]
    rows = []
    for label, source_table, target_keys, note in ENTITY_MATRIX:
        source_value = source_counts.get(source_table)
        target_value = sum(target_counts.get(key, 0) for key in target_keys) if target_keys else None
        delta = None if (source_value is None or target_value is None) else target_value - source_value
        rows.append([label, fmt_int(source_value), fmt_int(target_value), fmt_signed(delta), note])

    role_rows = [
        [f"`{slug}`", fmt_int(active), fmt_int(inactive)] for slug, active, inactive in context["target"]["roles"]
    ]
    cells = context["ladders"]
    cell_rows = [
        [
            DOMAIN_LABELS[domain],
            fmt_int(cells[domain].source_total),
            fmt_int(cells[domain].target),
            fmt_signed(cells[domain].target - cells[domain].source_total),
            "Nərdivan üçün §1.3-ə bax.",
        ]
        for domain in DOMAINS
    ]
    return "\n".join(
        [
            "## 2. Varlıq-varlıq müqayisə cədvəli",
            "",
            md_table(["Sahə", "Mənbə", "Hədəf", "Fərq", "İzah"], rows + cell_rows),
            "",
            "### Hədəf tərəfdə rol üzrə üzvlüklər",
            "",
            "Məzun / qeyri-aktiv tələbələr **arxiv üzvlüyü** kimi köçür — hesabdan silinmir,",
            "sadəcə `is_active = false` olur.",
            "",
            md_table(["Rol", "Aktiv üzvlük", "Arxiv (qeyri-aktiv)"], role_rows),
        ]
    )


def _issues(context: dict) -> str:
    rows = [
        [f"`{table}`", f"`{rule}`", severity, fmt_int(count)]
        for table, rule, severity, count in context["target"]["issues"][:30]
    ]
    return "\n".join(
        [
            "## 6. Ledger problem kodları (ilk 30)",
            "",
            "Bunlar səssiz itki DEYİL: hər biri qeydə alınmış, səbəbi adlandırılmış hadisədir.",
            "",
            md_table(["Mənbə cədvəli", "Kod", "Ciddilik", "Say"], rows),
        ]
    )


def _timings(context: dict) -> str:
    timer = context["timer"]
    rows = [
        [entry.label, fmt_duration(entry.seconds), fmt_int(entry.rows)]
        for entry in sorted(timer.entries, key=lambda item: -item.seconds)[:20]
    ]
    return "\n".join(
        [
            "## Əlavə: sorğu vaxtları",
            "",
            f"Ümumi sorğu vaxtı: **{fmt_duration(timer.total_seconds)}** "
            f"({len(timer.entries)} sorğu, hamısı yalnız-oxu).",
            "",
            md_table(["Sorğu", "Müddət", "Qaytarılan sətir"], rows),
        ]
    )
