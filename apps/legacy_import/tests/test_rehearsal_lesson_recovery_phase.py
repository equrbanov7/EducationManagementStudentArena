"""Phase ``journal_lesson_recovery`` (J12) testləri.

Sınanan müqavilə (tapşırığın 6 bəndi):

1. mənbədə dərs sətri OLMAYAN, amma bal xanası OLAN slot bərpa olunur;
2. bərpa olunan dərs AÇIQ nişanlıdır (``is_legacy_synthesised`` + ledger kodu);
3. saat J11-in ``saatliq_ders``-indən, DÖVR-şüurlu qayda ilə gəlir;
4. saat naməlum olanda dərs yenə yaranır, ``start_time`` boş qalır;
5. mövcud dərs/xana DƏYİŞMİR və faza idempotentdir;
6. bərpa olunan qayıb ``absence_hours``-a düşür;
7. hədəf toqquşmasında UDUZAN dəyər ``LegacyGradeFact``-a yazılır.
"""

import datetime
from decimal import Decimal

from django.apps import apps as django_apps

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
)
from apps.legacy_import.services.rehearsal_journal_marks_phase import JournalMarksPhase
from apps.legacy_import.services.rehearsal_lesson_recovery_evidence import MARK_UNRESOLVED_ENTITY_TYPE
from apps.legacy_import.services.rehearsal_lesson_recovery_phase import (
    DERIVED_DIGEST_NAMESPACE,
    JOURNAL_LESSON_RECOVERY_PHASE_KEY,
    OUTCOME_RULES,
    JournalLessonRecoveryPhase,
)
from apps.legacy_import.services.rehearsal_lesson_recovery_scan import recovered_schedule
from apps.legacy_import.services.rehearsal_lesson_recovery_source import (
    HOURS_FRACTIONAL_RULE_CODE,
    HOURS_PAIR_SEMANTICS_FROM,
    HOURS_UNRESOLVED_RULE_CODE,
    recovered_lesson_hours,
)
from apps.legacy_import.services.rehearsal_lesson_recovery_targets import (
    CONFLICT_ISSUE_SEVERITY,
    LESSON_ISSUE_SEVERITY,
    LESSON_SYNTH_ENTITY_TYPE,
    MARK_CONFLICT_ENTITY_TYPE,
    MARK_ISSUE_SEVERITY,
    MARK_RECOVERY_ENTITY_TYPE,
    SYNTHESISED_RULE_CODE,
    TIME_UNKNOWN_RULE_CODE,
)
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db

#: Xanaların defolt slotu; ``dates`` cədvəli BOŞ olduğu üçün J4 onu tapa bilmir.
MISSING_MONTH = "12"
MISSING_DAY = "30"


# ---------------------------------------------------------------------------
# Saf forma və saat semantikası (verilənlər bazasız)
# ---------------------------------------------------------------------------


def test_the_phase_declares_a_batch_less_four_entity_shape(db):
    phase = JournalLessonRecoveryPhase()

    assert phase.phase_key == JOURNAL_LESSON_RECOVERY_PHASE_KEY and phase.order == 41
    assert phase.source_tables == ()
    assert phase.entity_types == (
        LESSON_SYNTH_ENTITY_TYPE,
        MARK_CONFLICT_ENTITY_TYPE,
        MARK_UNRESOLVED_ENTITY_TYPE,
        MARK_RECOVERY_ENTITY_TYPE,
    )
    assert phase.declared_source_rows(harness.plan(harness.tables())) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    # Açarlar ``cf:``/``mr:``/``sl:`` prefikslidir → rebuild LEKSİKOQRAFİK sıralayır.
    assert phase.derived_ledger_sort_key is str
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "lesson_recovery_materialised"


def test_the_phase_refuses_a_foreign_context_and_a_missing_dependency():
    with pytest.raises(LegacyRehearsalConfigError):
        JournalLessonRecoveryPhase().run(object())
    rows = harness.tables()
    keys = tuple(key for key in harness.PHASE_KEYS if key != "journal_marks")
    with pytest.raises(LegacyRehearsalEvidenceError):
        JournalLessonRecoveryPhase().run(harness.context(rows_by_table=rows, phase_keys=keys))


def test_every_outcome_code_the_journal_seal_can_emit_has_a_severity():
    """Fail-closed qapısının SƏSSİZ pozulmasına qarşı invariant.

    ``_report`` jurnal möhürünə ``OUTCOME_RULES``-un HƏR kodunu yazır; kod
    ``MARK_ISSUE_SEVERITY``-də yoxdursa möhür yazılan anda
    ``legacy_rehearsal_issue_severity_unmapped`` atılır — yəni faza MİLYONLARLA
    xanadan SONRA çökür.  2026-08-31 real-data icrasında məhz belə oldu
    (``legacy_journal_component_target_conflict`` xəritələnməmişdi).
    """

    assert {code for code, _fatal in OUTCOME_RULES.values()} <= set(MARK_ISSUE_SEVERITY)
    assert set(MARK_ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)
    assert set(LESSON_ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)
    assert set(CONFLICT_ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)
    # Toqquşma möhürü domen kodunu da daşıyır → o da xəritələnməlidir.
    assert {
        "legacy_journal_mark_recovered_target_conflict",
        "legacy_journal_component_target_conflict",
    } <= set(CONFLICT_ISSUE_SEVERITY)


@pytest.mark.parametrize(
    ("value", "date", "expected"),
    [
        # Köhnə dövr: sütun AKADEMİK SAAT sayır.
        (2.0, datetime.date(2023, 10, 1), (2, "")),
        (1.0, datetime.date(2023, 10, 1), (1, "")),
        # Yeni dövr: sütun CÜT sayır — bir cüt = 2 akademik saat.
        (1.0, datetime.date(2025, 10, 1), (2, "")),
        (2.0, datetime.date(2025, 10, 1), (4, "")),
        # Yarım cüt yeni dövrdə tam ədədə düşür, köhnə dövrdə düşmür.
        (0.5, datetime.date(2025, 10, 1), (1, "")),
        (0.5, datetime.date(2023, 10, 1), (0, HOURS_FRACTIONAL_RULE_CODE)),
        # Diapazondan kənar / oxunmayan → defolt saat qalır, sətir işarələnir.
        (0.0, datetime.date(2025, 10, 1), (0, HOURS_UNRESOLVED_RULE_CODE)),
        (None, datetime.date(2025, 10, 1), (0, HOURS_UNRESOLVED_RULE_CODE)),
        ("2", datetime.date(2025, 10, 1), (0, HOURS_UNRESOLVED_RULE_CODE)),
    ],
)
def test_recovered_lesson_hours_follows_the_measured_unit_change(value, date, expected):
    assert recovered_lesson_hours(value, date) == expected


def test_the_unit_change_boundary_is_the_measured_february_2024_cut():
    assert HOURS_PAIR_SEMANTICS_FROM == datetime.date(2024, 2, 1)
    before = HOURS_PAIR_SEMANTICS_FROM - datetime.timedelta(days=1)
    assert recovered_lesson_hours(1.0, before) == (1, "")
    assert recovered_lesson_hours(1.0, HOURS_PAIR_SEMANTICS_FROM) == (2, "")


@pytest.mark.parametrize(
    ("month", "day", "time_text", "expected"),
    [
        (12, 30, "14:00", (datetime.date(2021, 12, 30), datetime.time(14, 0))),
        (3, 15, "13:30", (datetime.date(2022, 3, 15), datetime.time(13, 30))),
        # Saat oxunmur → dərs YENƏ yaranır, saat boş qalır.
        (12, 30, "", (datetime.date(2021, 12, 30), None)),
        # Mövcud olmayan tarix → bərpa YOXDUR (təxmin edilmir).
        (11, 31, "14:00", None),
    ],
)
def test_recovered_schedule_reuses_the_j3_academic_year_split(month, day, time_text, expected):
    assert recovered_schedule(first_year=2021, month=month, day=day, time_text=time_text) == expected


# ---------------------------------------------------------------------------
# Hədəf davranışı
# ---------------------------------------------------------------------------


@pytest.fixture
def actor(django_user_model):
    return django_user_model.objects.create_user(username="recovery-actor", password="x")


def _rows(points, **kwargs):
    """Dərs cədvəli BOŞ olan mənbə — məhz sahibin şikayət etdiyi vəziyyət."""

    return harness.tables(dates=kwargs.pop("dates", []), points=points, **kwargs)


def _run_recovery(actor, slug, rows, *, seed_kwargs=None, notes=None, marks_first=True):
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk, **(seed_kwargs or {"lesson_slots": ()}))
    harness.authorize_import_actor(org, actor)
    try:
        if marks_first:
            JournalMarksPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
        report = JournalLessonRecoveryPhase().run(
            harness.context(rows_by_table=rows, run=run, organization=org, actor=actor, notes=notes)
        )
    finally:
        harness.clear_import_actor()
    return org, run, report


def _lessons(org):
    return django_apps.get_model("registrar", "Lesson").objects.filter(organization=org)


def _marks(org):
    return django_apps.get_model("registrar", "LessonMark").objects.filter(organization=org)


def test_a_cell_without_a_source_lesson_row_is_recovered_and_marked(actor):
    rows = _rows(
        [
            harness.point_row(1, point="7", sem_muh=0, month_id=MISSING_MONTH, day_number=MISSING_DAY),
            harness.point_row(2, point="qb", student_id=harness.STUDENT_B),
        ]
    )
    org, run, report = _run_recovery(actor, "recover-basic", rows)

    lesson = _lessons(org).get()
    # 1) Dərs BƏRPA olundu — mənbədə onun öz sətri yox idi.
    assert lesson.date == datetime.date(2021, 12, 30) and lesson.start_time == datetime.time(14, 0)
    # 2) Nişan AÇIQdır: sahib bunun uydurma dərs olmadığını görə bilir.
    assert lesson.is_legacy_synthesised is True
    assert lesson.created_by_id is None
    # 3) Növ xanalardan törəyir — ballı xana LECTURE altında gizlənmir.
    assert lesson.kind == "seminar"
    # 4) Xanaların DƏYƏRİ mənbədəndir.
    written = {(mark.enrollment.student.username, mark.status, mark.score) for mark in _marks(org)}
    assert written == {
        ("myedu.student.42", "present", Decimal("7.00")),
        ("myedu.student.43", "absent", None),
    }
    assert report.state_counts["lesson_recovery_materialised"] >= 2
    assert run is not None


def test_the_recovered_lesson_carries_the_synthesised_ledger_code(actor):
    rows = _rows([harness.point_row(1, point="ie")])
    _org, run, _report = _run_recovery(actor, "recover-ledger", rows)

    maps = LegacyEntityMap.objects.filter(
        created_run=run, entity_type=LESSON_SYNTH_ENTITY_TYPE, state=LegacyEntityMap.State.MIGRATED
    )
    assert maps.count() == 1
    assert maps.get().target_model_label == "registrar.lesson"
    codes = set(
        LegacyMigrationIssue.objects.filter(run=run, entity_type=LESSON_SYNTH_ENTITY_TYPE).values_list(
            "rule_code", flat=True
        )
    )
    assert SYNTHESISED_RULE_CODE in codes


def test_existing_lessons_and_marks_are_never_touched(actor):
    """J3-ün yazdığı dərs və J4-ün yazdığı xana olduğu kimi qalır."""

    rows = harness.tables(points=[harness.point_row(1, point="5")])
    org, _run_obj, _report = _run_recovery(
        actor, "recover-untouched", rows, seed_kwargs={"lesson_slots": harness.DEFAULT_LESSON_SLOTS}
    )

    lesson = _lessons(org).get(date=datetime.date(2021, 12, 30))
    assert lesson.is_legacy_synthesised is False
    assert lesson.hours == 2 and lesson.kind == "lecture" and lesson.topic == ""
    assert _lessons(org).filter(is_legacy_synthesised=True).count() == 0
    mark = _marks(org).get()
    assert mark.score == Decimal("5.00") and mark.entered_by_id is None


def test_running_the_phase_twice_creates_no_duplicates(actor):
    rows = _rows([harness.point_row(1, point="ie"), harness.point_row(2, point="qb", student_id=harness.STUDENT_B)])
    org = harness.organization(actor, "recover-idempotent")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk, lesson_slots=())
    harness.authorize_import_actor(org, actor)
    try:
        context_kwargs = {"rows_by_table": rows, "run": run, "organization": org, "actor": actor}
        first = JournalLessonRecoveryPhase().run(harness.context(**context_kwargs))
        second = JournalLessonRecoveryPhase().run(harness.context(**context_kwargs))
    finally:
        harness.clear_import_actor()

    assert _lessons(org).count() == 1 and _marks(org).count() == 2
    # Resume: ikinci icra eyni möhürü təsdiqləyir, yeni sətir yaratmır.
    assert first.phase_digest == second.phase_digest


def test_a_half_finished_run_resumes_and_still_writes_the_missing_marks(actor):
    """Dərs möhürü yazılıb, xanalar yazılmayıb — davam onları YAZMALIDIR.

    Bu, real bir boşluq idi (2026-08-31 klon icrasında ölçüldü): dərs möhürü
    resume-dan gələndə yazıcının slot indeksi BOŞ qalırdı, ona görə davam
    xanaları «dərs tapılmadı» sayıb keçirdi və bal İKİNCİ dəfə də itirdi.

    Ssenari kəsilmiş icranın dəqiq vəziyyətidir: ``Lesson`` sətri və onun
    ``lesson_synthesised`` möhürü VAR, jurnalın xana möhürü YOXDUR.
    """

    rows = _rows([harness.point_row(1, point="6"), harness.point_row(2, point="qb", student_id=harness.STUDENT_B)])
    org = harness.organization(actor, "recover-resume")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    offering, _enrollments, _seeded = harness.seed_journal_target(org, actor, run.pk, lesson_slots=())
    lesson = django_apps.get_model("registrar", "Lesson").objects.create(
        organization=org,
        offering=offering,
        date=datetime.date(2021, 12, 30),
        start_time=datetime.time(14, 0),
        kind="seminar",
        hours=2,
        is_legacy_synthesised=True,
    )
    # Möhür açarı slotu AÇAN xananın sətridir: əsas cədvəl (``p``), pk 1, qrup "2".
    harness._map(
        run.pk,
        actor,
        entity_type=LESSON_SYNTH_ENTITY_TYPE,
        legacy_pk="sl:p:1:2",
        label="registrar.lesson",
        target_pk=lesson.pk,
    )
    harness.authorize_import_actor(org, actor)
    try:
        JournalLessonRecoveryPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    finally:
        harness.clear_import_actor()

    # Dərs TƏKRARLANMIR, xanalar isə mövcud dərsə YAZILIR.
    assert _lessons(org).count() == 1
    assert {(mark.status, mark.score) for mark in _marks(org)} == {
        ("present", Decimal("6.00")),
        ("absent", None),
    }


def test_recovered_absences_reach_absence_hours(actor):
    rows = _rows(
        [
            harness.point_row(1, point="qb"),
            harness.point_row(2, point="qb", month_id="12", day_number="31"),
        ],
        lesson_meta=[],
    )
    org, _run_obj, _report = _run_recovery(actor, "recover-absence", rows)

    enrollment = (
        django_apps.get_model("registrar", "Enrollment")
        .objects.filter(organization=org, student__username="myedu.student.42")
        .get()
    )
    # İki bərpa dərsi × J3 spec defoltu (2 saat) = 4 saat.
    assert _lessons(org).filter(is_legacy_synthesised=True).count() == 2
    assert enrollment.absence_hours == 4


def test_metadata_supplies_topic_room_and_period_aware_hours(actor):
    """J11 metadatası varsa bərpa dərsinə qoşulur; saat dövrə görə çevrilir."""

    rows = _rows(
        [harness.point_row(1, point="ie")],
        rooms=[harness.room_row(harness.ROOM_ID)],
        lesson_meta=[harness.lesson_meta_row(1, saatliq_ders=1.0)],
        lesson_topics=[harness.syllabus_topic_row(movzu="Bərpa mövzusu")],
    )
    org = harness.organization(actor, "recover-meta")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk, lesson_slots=())
    room = django_apps.get_model("exams", "ExamRoom").objects.create(
        organization=org, name="03/2", building="3", capacity=28
    )
    harness._map(
        run.pk,
        actor,
        entity_type="legacy_room",
        legacy_pk=str(harness.ROOM_ID),
        label="exams.examroom",
        target_pk=room.pk,
    )
    harness.authorize_import_actor(org, actor)
    try:
        JournalLessonRecoveryPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    finally:
        harness.clear_import_actor()

    lesson = _lessons(org).get()
    assert lesson.topic == "Bərpa mövzusu" and lesson.room_id == room.pk
    # Dərs 2021-12-30-dadır → KÖHNƏ dövr: ``saatliq_ders=1`` bir akademik saatdır.
    assert lesson.hours == 1


def test_an_unreadable_time_still_recovers_the_lesson_without_a_start_time(actor):
    rows = _rows([harness.point_row(1, point="4", time_value=datetime.timedelta(hours=30))])
    org, run, _report = _run_recovery(actor, "recover-no-time", rows)

    lesson = _lessons(org).get()
    assert lesson.start_time is None and lesson.is_legacy_synthesised is True
    assert _marks(org).get().score == Decimal("4.00")
    codes = set(
        LegacyMigrationIssue.objects.filter(run=run, entity_type=LESSON_SYNTH_ENTITY_TYPE).values_list(
            "rule_code", flat=True
        )
    )
    assert TIME_UNKNOWN_RULE_CODE in codes


def test_an_impossible_date_is_quarantined_rather_than_guessed(actor):
    rows = _rows([harness.point_row(1, point="6", month_id="11", day_number="31")])
    org, run, _report = _run_recovery(actor, "recover-bad-date", rows)

    assert _lessons(org).count() == 0 and _marks(org).count() == 0
    codes = set(
        LegacyMigrationIssue.objects.filter(run=run, entity_type=MARK_RECOVERY_ENTITY_TYPE).values_list(
            "rule_code", flat=True
        )
    )
    assert "legacy_lesson_synth_date_invalid" in codes


def test_a_divergent_target_collision_stores_the_losing_value(actor):
    """İki jurnal bir açılışa birləşir; uduzan dəyər sübut qatına düşür."""

    rows = harness.tables(
        journals=[
            harness.journal_row(2, harness.UNIQID),
            harness.journal_row(3, harness.OTHER_UNIQID),
        ],
        dates=[harness.dates_row(10, journal_id=2, month=12, day=30)],
        points=[
            harness.point_row(1, uniqid=harness.UNIQID, point="8"),
            harness.point_row(2, uniqid=harness.OTHER_UNIQID, point="3"),
        ],
    )
    org = harness.organization(actor, "recover-conflict")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    offering, _enrollments, _lessons_seeded = harness.seed_journal_target(
        org,
        actor,
        run.pk,
        uniqid=harness.UNIQID,
        lesson_slots=((10, datetime.date(2021, 12, 30), datetime.time(14, 0)),),
    )
    # İkinci jurnal EYNİ açılışa və EYNİ yazılışa baxır (C6 birləşməsi).
    harness.seed_journal_target(
        org, actor, run.pk, uniqid=harness.OTHER_UNIQID, offering=offering, lesson_slots=(), students=()
    )
    harness._map(
        run.pk,
        actor,
        entity_type="journal_enrollment",
        legacy_pk=f"{harness.OTHER_UNIQID}:{harness.STUDENT_A}",
        label="registrar.enrollment",
        target_pk=_enrollments[harness.STUDENT_A].pk,
    )
    harness.authorize_import_actor(org, actor)
    try:
        JournalMarksPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
        JournalLessonRecoveryPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    finally:
        harness.clear_import_actor()

    # Qalib DƏYİŞMƏYİB.
    assert _marks(org).get().score == Decimal("8.00")
    fact = django_apps.get_model("registrar", "LegacyGradeFact").objects.get(
        organization=org, source_table="journals_dates_points", source_pk=2
    )
    assert fact.mapping_status == "conflict"
    assert fact.raw_score_text == "3"  # uduzan dəyər saxlanıldı
    assert fact.source_journal_ref == harness.OTHER_UNIQID
    # ``registrar_guard_legacy_grade_fact_insert`` bu kodu BAĞLAYIR; domen kodu
    # ledger issue-sunda qalır, ona görə heç bir məlumat itmir.
    assert fact.mapping_issue_code == "legacy_grade_fact_conflict"
    assert LegacyEntityMap.objects.filter(created_run=run, entity_type=MARK_CONFLICT_ENTITY_TYPE).count() == 1
    codes = set(
        LegacyMigrationIssue.objects.filter(run=run, entity_type=MARK_CONFLICT_ENTITY_TYPE).values_list(
            "rule_code", flat=True
        )
    )
    assert codes == {"legacy_mark_conflict_evidence", "legacy_journal_mark_recovered_target_conflict"}


def test_a_divergent_component_collision_stores_the_losing_value(actor):
    """C keçidi: iki jurnal bir yazılışa baxır, kollokvium balları fərqlidir."""

    rows = harness.tables(
        journals=[
            harness.journal_row(2, harness.UNIQID),
            harness.journal_row(3, harness.OTHER_UNIQID),
        ],
        points=[
            harness.point_row(1, uniqid=harness.UNIQID, month_id="k1", day_number="0", point="9"),
            harness.point_row(2, uniqid=harness.OTHER_UNIQID, month_id="k1", day_number="0", point="4"),
        ],
    )
    org = harness.organization(actor, "recover-comp-conflict")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    offering, enrollments, _lessons_seeded = harness.seed_journal_target(org, actor, run.pk, uniqid=harness.UNIQID)
    harness.seed_journal_target(
        org, actor, run.pk, uniqid=harness.OTHER_UNIQID, offering=offering, lesson_slots=(), students=()
    )
    harness._map(
        run.pk,
        actor,
        entity_type="journal_enrollment",
        legacy_pk=f"{harness.OTHER_UNIQID}:{harness.STUDENT_A}",
        label="registrar.enrollment",
        target_pk=enrollments[harness.STUDENT_A].pk,
    )
    harness.authorize_import_actor(org, actor)
    try:
        JournalLessonRecoveryPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    finally:
        harness.clear_import_actor()

    fact = django_apps.get_model("registrar", "LegacyGradeFact").objects.get(
        organization=org, source_table="journals_dates_points", source_pk=2
    )
    assert fact.raw_score_text == "4" and fact.score_code == "k1"
    assert fact.mapping_status == "conflict"
    # Jurnal möhürü də komponent kodunu daşıyır — severity xəritəsi onu tanımalıdır.
    codes = set(
        LegacyMigrationIssue.objects.filter(run=run, entity_type=MARK_RECOVERY_ENTITY_TYPE).values_list(
            "rule_code", flat=True
        )
    )
    assert "legacy_journal_component_target_conflict" in codes


def test_the_ledger_rebuild_reproduces_the_phase_digest(actor):
    rows = _rows([harness.point_row(1, point="9"), harness.point_row(2, point="qb", student_id=harness.STUDENT_B)])
    _org, run, report = _run_recovery(actor, "recover-rebuild", rows)

    rebuilt = phase_report_from_ledger(run, phase=JournalLessonRecoveryPhase(), plan=harness.plan(rows))
    assert rebuilt.phase_digest == report.phase_digest
    assert rebuilt.state_counts == report.state_counts
