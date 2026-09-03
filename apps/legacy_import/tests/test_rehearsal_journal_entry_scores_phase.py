"""Phase ``journal_entry_scores`` (J5b) testləri: tarixi giriş balının arxivi.

Bu dəst spec B-nin BÜTÜN iddialarını sübut edir:

* ``entry_score_for`` GENERIC komponent varsa dərs-cəmini ƏVƏZ edir (B2 premisi);
* ``yekun.girish`` DƏQİQ köçür, digər semestrlər düsturla bərpa olunur (B3);
* gündəlik xanalar, kollokvium və sərbəst iş OLDUĞU KİMİ qalır (B4);
* arxiv komponenti OLMAYAN açılış (yeni semestr) təsirlənmir (B5).
"""

import datetime
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
)
from apps.legacy_import.services.rehearsal_journal_components_phase import JournalComponentsPhase
from apps.legacy_import.services.rehearsal_journal_entry_scores_phase import (
    ARCHIVE_COMPONENT_KIND,
    ARCHIVE_COMPONENT_MAX,
    ARCHIVE_COMPONENT_NAME,
    DERIVED_DIGEST_NAMESPACE,
    ENTRY_SCORES_ENTITY_TYPE,
    ISSUE_SEVERITY,
    JOURNAL_ENTRY_SCORES_PHASE_KEY,
    UNATTRIBUTED_SEAL_KEY,
    JournalEntryScoresPhase,
    group_enrollments,
    write_entry_score,
)
from apps.legacy_import.services.rehearsal_journal_entry_scores_source import (
    EntryScoreInputs,
    clamp,
    legacy_girish,
    round_half_up,
)
from apps.legacy_import.services.rehearsal_journal_marks_phase import JournalMarksPhase
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.tests import journal_points_harness as harness
from apps.organizations.models import AcademicPeriod
from apps.registrar.gradebook import entry_score_for
from core.constants import AcademicPeriodType

pytestmark = pytest.mark.django_db

SLICE_KEY = f"{harness.UNIQID}:2"
CAP = Decimal("50")


# ── faza forması / taksonomiya ───────────────────────────────────────────────


def test_the_phase_declares_a_batch_less_offering_keyed_shape(db):
    phase = JournalEntryScoresPhase()

    assert phase.phase_key == JOURNAL_ENTRY_SCORES_PHASE_KEY and phase.order == 43
    assert phase.source_tables == () and phase.entity_types == (ENTRY_SCORES_ENTITY_TYPE,)
    assert phase.declared_source_rows(harness.plan(harness.tables())) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_ledger_sort_key is str
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "journal_entry_scores_materialised"
    assert phase.derived_state_key(LegacyEntityMap.State.SKIPPED) == "journal_entry_scores_skipped"


def test_issue_severity_map_covers_exactly_the_entry_score_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_entry_score_exact": "info",
        "legacy_entry_score_derived": "info",
        "legacy_entry_score_residual_clamped": "warning",
        "legacy_entry_score_target_conflict": "warning",
        "legacy_entry_score_enrollment_unresolved": "warning",
        "legacy_entry_score_offering_incomplete": "warning",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        JournalEntryScoresPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


def test_the_dependency_gate_requires_marks_and_components():
    rows = harness.tables()
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalEntryScoresPhase().run(harness.context(rows_by_table=rows, phase_keys=("journal_entry_scores",)))

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


# ── saf funksiyalar ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value, expected",
    [(Decimal("-3"), Decimal("0.00")), (Decimal("22.5"), Decimal("22.50")), (Decimal("61"), Decimal("50.00"))],
)
def test_clamp_bounds_the_value_and_fixes_the_field_shape(value, expected):
    assert clamp(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (Decimal("72.5"), Decimal("73.00")),  # yarım YUXARI (bankir deyil!)
        (Decimal("72.4"), Decimal("72.00")),
        (Decimal("32.50"), Decimal("33.00")),
        (Decimal("15.00"), Decimal("15.00")),  # tam dəyərin təsviri dəyişmir
    ],
)
def test_round_half_up_rounds_halves_upward_to_a_whole_number(value, expected):
    rounded = round_half_up(value)

    assert rounded == expected
    assert str(rounded) == str(expected)  # sahə forması (2 onluq) qorunur


@pytest.mark.parametrize("value", ["30", None, True])
def test_legacy_girish_refuses_anything_that_is_not_a_number(value):
    assert legacy_girish({"girish": value}) is None


def test_legacy_girish_reads_the_numeric_column_without_coercion():
    assert legacy_girish({"girish": 30.0}) == Decimal("30.0")
    assert legacy_girish({"girish": 17}) == Decimal(17)


def test_the_residual_is_the_part_kollokvium_does_not_already_explain():
    inputs = EntryScoreInputs(
        absences={"e1": 2}, kollokvium={"e1": Decimal("18")}, selfwork={"e1": Decimal("6")}, checklist={}, exact={}
    )
    value = inputs.resolve("e1")

    # 10 − 0.5×2 + 18 + 6 = 33 ; qalıq = 33 − 18 = 15
    assert (value.entry, value.residual, value.token, value.clamped) == (
        Decimal("33.00"),
        Decimal("15.00"),
        "derived",
        False,
    )


def test_an_exact_value_never_runs_the_formula():
    inputs = EntryScoreInputs(
        absences={"e1": 40}, kollokvium={"e1": Decimal("9")}, selfwork={}, checklist={}, exact={"e1": Decimal("30")}
    )
    value = inputs.resolve("e1")

    assert (value.entry, value.residual, value.token) == (Decimal("30.00"), Decimal("21.00"), "exact")


@pytest.mark.parametrize(
    "girish, residual",
    [(Decimal("32.5"), Decimal("33.00")), (Decimal("32.4"), Decimal("32.00"))],
)
def test_a_fractional_girish_residual_is_rounded_half_up_to_a_whole_number(girish, residual):
    """Sahibin qaydası: köhnə FLOAT ``girish``-in kəsiri hədəfə köçmür (32.5 → 33)."""

    inputs = EntryScoreInputs(absences={}, kollokvium={}, selfwork={}, checklist={}, exact={"e1": girish})
    value = inputs.resolve("e1")

    assert (value.residual, value.token) == (residual, "exact")
    # Yuvarlaqlaşdırma sərhəd hadisəsi DEYİL — ``clamped`` bayrağı qalxmır.
    assert value.clamped is False


def test_group_enrollments_reports_the_ones_without_an_offering():
    grouped, unresolved = group_enrollments({"u:2": "e1", "u:3": "e2"}, {"e1": "off"})

    assert grouped == {"off": [("u:2", "e1")]} and unresolved == 1


# ── B2 premisi: GENERIC komponent dərs-cəmini ƏVƏZ edir ──────────────────────


def test_a_generic_component_replaces_the_lesson_total_and_kollokvium_is_added(actor):
    """``entry_score_for``-un müqaviləsi — bütün faza məhz bunun üzərində qurulub."""

    org, _run_row, _report = _run(actor, "entry-premise", harness.tables(points=[harness.point_row(1, point="9")]))
    enrollment = _enrollment(org, harness.STUDENT_A)
    kollokvium = django_apps.get_model("registrar", "AssessmentComponent").objects.create(
        organization=org, offering=enrollment.offering, name="Kollokvium X", kind="kollokvium", max_score=10, order=9
    )
    django_apps.get_model("registrar", "ComponentScore").objects.create(
        organization=org, component=kollokvium, enrollment=enrollment, score=Decimal("4")
    )

    # Arxiv qalığı 10-dur (düstur: 10 − 0 + 0), dərs balı isə 9.  GENERIC dərs
    # cəmini ƏVƏZ edir, kollokvium isə ÜSTƏGƏL: 10 + 4 = 14 (nə 9, nə 13).
    assert _archive_score(org, enrollment) == Decimal("10.00")
    assert entry_score_for(enrollment, CAP) == Decimal("14")


# ── B3: dəyər mənbəyi ────────────────────────────────────────────────────────


def test_the_yekun_value_is_written_exactly_and_flagged_as_exact(actor):
    rows = harness.tables(
        points=[harness.point_row(1, point="9"), _pseudo(2, "k1", "8")],
        yekun=[harness.yekun_row(1, student_id=harness.STUDENT_A, girish=30.0)],
    )
    org, run, report = _run(actor, "entry-exact", rows)

    student_a = _enrollment(org, harness.STUDENT_A)
    # Qalıq 30 − 8 = 22; kanonik hesablama isə yenidən 22 + 8 = 30 verir.
    assert _archive_score(org, student_a) == Decimal("22.00")
    assert entry_score_for(student_a, CAP) == Decimal("30")
    # ``yekun`` sətri olmayan tələbə düsturla bərpa olunur: 10 − 0 + 0 = 10.
    assert entry_score_for(_enrollment(org, harness.STUDENT_B), CAP) == Decimal("10")
    assert dict(report.state_counts) == {"journal_entry_scores_materialised": 1}
    assert _issues(run) == {
        (SLICE_KEY, "legacy_entry_score_exact"): "info",
        (SLICE_KEY, "legacy_entry_score_derived"): "info",
    }


def test_a_fractional_yekun_girish_lands_as_a_whole_number(actor):
    """Kök səbəbin sübutu: FLOAT ``girish`` (32.5) hədəfdə tam ədəddir (33)."""

    rows = harness.tables(
        points=[harness.point_row(1, point="9")],
        yekun=[harness.yekun_row(1, student_id=harness.STUDENT_A, girish=32.5)],
    )
    org, run, _report = _run(actor, "entry-fractional", rows)

    student_a = _enrollment(org, harness.STUDENT_A)
    assert _archive_score(org, student_a) == Decimal("33.00")
    assert entry_score_for(student_a, CAP) == Decimal("33")
    # Yuvarlaqlaşdırma clamp deyil — sərhəd xəbərdarlığı yaranmır.
    assert (SLICE_KEY, "legacy_entry_score_residual_clamped") not in _issues(run)


def test_a_semester_without_yekun_is_rebuilt_from_the_legacy_formula(actor):
    rows = harness.tables(
        points=[harness.point_row(1, point="qb"), _pseudo(2, "k1", "8"), _pseudo(3, "si", "5")],
    )
    org, run, _report = _run(actor, "entry-derived", rows)

    # 10 − 0.5×1 + 8 + 5 = 22.5 ; qalıq = 22.5 − 8 = 14.5 → yarım-yuxarı 15
    # (``si`` çeklisti boşdur; sahibin qaydası: yazılan qalıq tam ədəddir).
    student_a = _enrollment(org, harness.STUDENT_A)
    assert _archive_score(org, student_a) == Decimal("15.00")
    assert entry_score_for(student_a, CAP) == Decimal("23")
    assert (SLICE_KEY, "legacy_entry_score_derived") in _issues(run)
    assert (SLICE_KEY, "legacy_entry_score_exact") not in _issues(run)


def test_every_enrollment_of_the_offering_receives_a_row(actor):
    """Fail-closed: GENERIC komponent AÇILIŞA aiddir — xanası olmayan tələbə 0 görərdi."""

    org, _run_row, _report = _run(actor, "entry-coverage", harness.tables(points=[harness.point_row(1, point="9")]))

    assert _archive_scores(org).count() == 2
    assert entry_score_for(_enrollment(org, harness.STUDENT_B), CAP) == Decimal("10")


def test_a_negative_residual_is_clamped_and_reported(actor):
    rows = harness.tables(
        points=[_pseudo(1, "k1", "8"), _pseudo(2, "k2", "9")],
        yekun=[harness.yekun_row(1, student_id=harness.STUDENT_A, girish=5.0)],
    )
    org, run, _report = _run(actor, "entry-clamped", rows)

    assert _archive_score(org, _enrollment(org, harness.STUDENT_A)) == Decimal("0.00")
    assert _issues(run)[(SLICE_KEY, "legacy_entry_score_residual_clamped")] == "warning"


# ── B4: köhnə data toxunulmur ────────────────────────────────────────────────


def test_the_existing_cells_and_components_are_left_untouched(actor):
    rows = harness.tables(
        points=[
            harness.point_row(1, point="9"),
            harness.point_row(2, point="qb", day_number="31"),
            _pseudo(3, "k1", "8"),
            _pseudo(4, "si", "5"),
        ]
    )
    org = harness.organization(actor, "entry-untouched")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk)
    for phase in (JournalMarksPhase(), JournalComponentsPhase()):
        phase.run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    before_marks, before_scores, before_components = _snapshot(org)

    JournalEntryScoresPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    after_marks, after_scores, after_components = _snapshot(org)

    assert after_marks == before_marks  # gündəlik xanalar toxunulmadı
    assert after_scores == before_scores  # kollokvium/sərbəst iş balları toxunulmadı
    assert after_components == before_components  # köhnə komponentlərin forması eynidir
    assert _archive_scores(org).count() == 2  # YALNIZ yeni arxiv sətirləri əlavə olundu


def test_the_archive_component_has_the_pinned_shape(actor):
    org, _run_row, _report = _run(actor, "entry-shape", harness.tables(points=[harness.point_row(1, point="9")]))
    component = django_apps.get_model("registrar", "AssessmentComponent").objects.get(
        organization=org, name=ARCHIVE_COMPONENT_NAME
    )

    assert (component.kind, component.max_score) == (ARCHIVE_COMPONENT_KIND, ARCHIVE_COMPONENT_MAX)
    assert (ARCHIVE_COMPONENT_KIND, ARCHIVE_COMPONENT_MAX) == ("generic", 50)
    assert component.held_on is None


def test_an_existing_target_row_is_never_overwritten(actor):
    rows = harness.tables(points=[harness.point_row(1, point="9")])
    org = harness.organization(actor, "entry-conflict")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    offering, enrollments, _lessons = harness.seed_journal_target(org, actor, run.pk)
    for phase in (JournalMarksPhase(), JournalComponentsPhase()):
        phase.run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    component = django_apps.get_model("registrar", "AssessmentComponent").objects.create(
        organization=org,
        offering=offering,
        name=ARCHIVE_COMPONENT_NAME,
        kind=ARCHIVE_COMPONENT_KIND,
        max_score=ARCHIVE_COMPONENT_MAX,
        order=0,
    )
    django_apps.get_model("registrar", "ComponentScore").objects.create(
        organization=org, component=component, enrollment=enrollments[harness.STUDENT_A], score=Decimal("3")
    )

    JournalEntryScoresPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert _archive_score(org, enrollments[harness.STUDENT_A]) == Decimal("3.00")
    assert _issues(run)[(SLICE_KEY, "legacy_entry_score_target_conflict")] == "warning"


def test_write_entry_score_is_idempotent_for_an_identical_value(actor):
    rows = harness.tables(points=[harness.point_row(1, point="9")])
    org, run, _report = _run(actor, "entry-write-twice", rows)
    enrollment = _enrollment(org, harness.STUDENT_A)
    component = django_apps.get_model("registrar", "AssessmentComponent").objects.get(
        organization=org, name=ARCHIVE_COMPONENT_NAME
    )
    context = harness.context(rows_by_table=rows, run=run, organization=org, actor=actor)

    result = write_entry_score(
        context, component_pk=str(component.pk), enrollment_pk=str(enrollment.pk), score=Decimal("10.00")
    )

    assert result == "written" and _archive_scores(org).count() == 2


# ── B5: yeni semestrlər təsirlənmir ──────────────────────────────────────────


def test_an_offering_outside_the_run_keeps_the_lesson_total(actor):
    org, _run_row, _report = _run(
        actor, "entry-untouched-new", harness.tables(points=[harness.point_row(1, point="9")])
    )
    fresh = _fresh_offering(org, actor)

    assert not django_apps.get_model("registrar", "AssessmentComponent").objects.filter(offering=fresh.offering)
    assert entry_score_for(fresh, CAP) == Decimal("7")


# ── determinizm / idempotentlik ──────────────────────────────────────────────


def test_a_repeated_invocation_replays_the_sealed_offering(actor):
    rows = harness.tables(
        points=[harness.point_row(1, point="9"), _pseudo(2, "k1", "8")],
        yekun=[harness.yekun_row(1, student_id=harness.STUDENT_A, girish=30.0)],
    )
    org, run, first = _run(actor, "entry-replay", rows)
    second = JournalEntryScoresPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert _archive_scores(org).count() == 2
    assert _archive_score(org, _enrollment(org, harness.STUDENT_A)) == Decimal("22.00")


def test_the_live_phase_digest_equals_the_ledger_rebuild(actor):
    rows = harness.tables(
        points=[harness.point_row(1, point="qb"), _pseudo(2, "k1", "8")],
        yekun=[harness.yekun_row(1, student_id=harness.STUDENT_B, girish=44.0)],
    )
    _org, run, live = _run(actor, "entry-rebuild", rows)
    rebuilt = phase_report_from_ledger(run, phase=JournalEntryScoresPhase(), plan=harness.plan(rows))

    assert rebuilt.phase_digest == live.phase_digest
    assert dict(rebuilt.state_counts) == dict(live.state_counts)


def test_an_offering_with_an_unmapped_enrollment_gets_no_archive_component(actor):
    """Fail-closed: ledger-dən kənar tələbə GENERIC komponentlə sıfırlanardı."""

    rows = harness.tables(points=[harness.point_row(1, point="9")])
    org = harness.organization(actor, "entry-incomplete")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    offering, _enrollments, _lessons = harness.seed_journal_target(org, actor, run.pk)
    for phase in (JournalMarksPhase(), JournalComponentsPhase()):
        phase.run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    outsider = _outsider_enrollment(org, actor, offering)

    report = JournalEntryScoresPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert _archive_scores(org).count() == 0
    assert not django_apps.get_model("registrar", "AssessmentComponent").objects.filter(
        organization=org, name=ARCHIVE_COMPONENT_NAME
    )
    assert report.state_counts["journal_entry_scores_unresolved"] == 1
    assert _issues(run)[(SLICE_KEY, "legacy_entry_score_offering_incomplete")] == "warning"
    # Kənar tələbənin giriş balı toxunulmadan qalır: dərs cəmi (xanası yoxdur → 0).
    assert entry_score_for(outsider, CAP) == Decimal("0")


def test_a_merged_journal_writes_each_enrollment_exactly_once():
    """§C6: iki legacy jurnal EYNİ açılışa baxa bilər — yazılış təkrarlanmır."""

    grouped, unresolved = group_enrollments({"b:42": "e1", "a:42": "e1"}, {"e1": "off"})

    assert grouped == {"off": [("a:42", "e1")]} and unresolved == 0


def test_an_enrollment_without_an_offering_row_is_sealed_as_unattributed(actor):
    rows = harness.tables(points=[harness.point_row(1, point="9")])
    org = harness.organization(actor, "entry-unattributed")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    _offering, enrollments, _lessons = harness.seed_journal_target(org, actor, run.pk)
    for phase in (JournalMarksPhase(), JournalComponentsPhase()):
        phase.run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    enrollments[harness.STUDENT_B].delete()

    report = JournalEntryScoresPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert report.state_counts["journal_entry_scores_unresolved"] == 1
    assert _issues(run)[(UNATTRIBUTED_SEAL_KEY, "legacy_entry_score_enrollment_unresolved")] == "warning"


# ── köməkçilər ───────────────────────────────────────────────────────────────


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="journal_entry_scores_actor", email="jes-actor@example.test", password="test-only"
    )


def _pseudo(legacy_pk, month_id, point, **overrides):
    return harness.point_row(legacy_pk, month_id=month_id, day_number=month_id, point=point, **overrides)


def _run(actor, slug, rows):
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk)
    for phase in (JournalMarksPhase(), JournalComponentsPhase()):
        phase.run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    report = JournalEntryScoresPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    return org, run, report


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=ENTRY_SCORES_ENTITY_TYPE)
    }


def _enrollment(org, legacy_student):
    return django_apps.get_model("registrar", "Enrollment").objects.get(
        organization=org, student__username=f"myedu.student.{legacy_student}"
    )


def _archive_scores(org):
    return django_apps.get_model("registrar", "ComponentScore").objects.filter(
        organization=org, component__name=ARCHIVE_COMPONENT_NAME
    )


def _archive_score(org, enrollment):
    return _archive_scores(org).get(enrollment=enrollment).score


def _snapshot(org):
    marks = sorted(
        django_apps.get_model("registrar", "LessonMark")
        .objects.filter(organization=org)
        .values_list("lesson_id", "enrollment_id", "status", "score")
    )
    # ARXİV komponenti qəsdən kənarda: sual «köhnə sətirlər dəyişdimi», «yeni
    # sətir əlavə olundumu» deyil (əlavə olunmasını ayrıca assert sübut edir).
    scores = sorted(
        django_apps.get_model("registrar", "ComponentScore")
        .objects.filter(organization=org)
        .exclude(component__name=ARCHIVE_COMPONENT_NAME)
        .values_list("component__name", "enrollment_id", "score")
    )
    components = sorted(
        django_apps.get_model("registrar", "AssessmentComponent")
        .objects.filter(organization=org)
        .exclude(name=ARCHIVE_COMPONENT_NAME)
        .values_list("name", "kind", "max_score")
    )
    return marks, scores, components


def _outsider_enrollment(org, actor, offering):
    """Ledger-də OLMAYAN, amma HƏMİN açılışda oturan yazılış."""

    student, _created = get_user_model().objects.get_or_create(username="outsider.1", defaults={"email": ""})
    profile = student.profile
    profile.organization = org
    profile.save(update_fields=["organization"])
    harness.activate_member(org, student, "student")
    return django_apps.get_model("registrar", "Enrollment").objects.create(
        organization=org, student=student, offering=offering, kind="mandatory"
    )


def _fresh_offering(org, actor):
    """Ledger-də OLMAYAN açılış: yeni semestrin güzgüsü (spec B5)."""

    subject = django_apps.get_model("registrar", "Subject").objects.create(
        organization=org, code="NEW-2026", name="Yeni fənn", ects=5
    )
    period = AcademicPeriod.objects.create(
        organization=org,
        name="Payız 2026",
        academic_year="2026/2027",
        period_type=AcademicPeriodType.SEMESTER,
        start_date=datetime.date(2026, 9, 15),
        end_date=datetime.date(2027, 1, 31),
    )
    offering = django_apps.get_model("registrar", "CourseOffering").objects.create(
        organization=org, subject=subject, period=period, lesson_hours=0, is_active=True
    )
    student, _created = get_user_model().objects.get_or_create(username="new.student.1", defaults={"email": ""})
    profile = student.profile
    profile.organization = org
    profile.save(update_fields=["organization"])
    harness.activate_member(org, student, "student")
    enrollment = django_apps.get_model("registrar", "Enrollment").objects.create(
        organization=org, student=student, offering=offering, kind="mandatory"
    )
    lesson = django_apps.get_model("registrar", "Lesson").objects.create(
        organization=org,
        offering=offering,
        date=datetime.date(2026, 10, 1),
        start_time=datetime.time(14, 0),
        kind="seminar",
        hours=2,
    )
    django_apps.get_model("registrar", "LessonMark").objects.create(
        organization=org, lesson=lesson, enrollment=enrollment, status="present", score=Decimal("7")
    )
    return enrollment
