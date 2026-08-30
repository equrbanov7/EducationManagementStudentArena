"""Phase ``journal_lesson_meta`` (J11) testləri: mövzu / otaq / dərs saatı.

Müqavilələr: J3-ün yaratdığı dərs sətrinin ZƏNGİNLƏŞDİRİLMƏSİ, ``fake`` süzgəci,
ambiqü slotun fail-closed atılması, kəsr saatın YUVARLAQLAŞDIRILMAMASI, mövcud
mövzu/otağın üstündən yazılmaması, idempotentlik və cross-run determinizm.
"""

from django.apps import apps as django_apps

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue
from apps.legacy_import.services.rehearsal_authorizer import LESSON_MODEL_LABEL
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
)
from apps.legacy_import.services.rehearsal_lesson_meta_phase import (
    DERIVED_DIGEST_NAMESPACE,
    JOURNAL_LESSON_META_PHASE_KEY,
    JournalLessonMetaPhase,
    ambiguous_slots,
)
from apps.legacy_import.services.rehearsal_lesson_meta_source import legacy_calendar_int, legacy_lesson_hours
from apps.legacy_import.services.rehearsal_lesson_meta_targets import ISSUE_SEVERITY, LESSON_META_ENTITY_TYPE
from apps.legacy_import.services.rehearsal_lesson_rooms_phase import LegacyRoomsPhase
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db

DEFAULT_ROOMS = (harness.room_row(harness.ROOM_ID, name="03/2", bina=3),)
DEFAULT_TOPICS = (harness.syllabus_topic_row(movzu="Sistemin arxitekturası"),)


def _lessons(org):
    return django_apps.get_model("registrar", "Lesson").objects.filter(organization=org).order_by("date")


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=LESSON_META_ENTITY_TYPE)
    }


def _maps(org):
    return {
        row.legacy_pk: (row.state, row.target_model_label)
        for row in LegacyEntityMap.objects.filter(organization=org, entity_type=LESSON_META_ENTITY_TYPE)
    }


def _rows(*, lesson_meta, rooms=DEFAULT_ROOMS, lesson_topics=DEFAULT_TOPICS, journals=None):
    return harness.tables(
        lesson_meta=list(lesson_meta),
        rooms=list(rooms),
        lesson_topics=list(lesson_topics),
        journals=journals,
    )


def _run_phase(actor, slug, *, lesson_meta, rooms=DEFAULT_ROOMS, lesson_topics=DEFAULT_TOPICS, notes=None, seed=True):
    """J10-u (otaq reyestri) qurub sonra J11-i işə salır — real sıra ilə."""

    rows = _rows(lesson_meta=lesson_meta, rooms=rooms, lesson_topics=lesson_topics)
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    offering = lessons = None
    if seed:
        offering, _enrollments, lessons = harness.seed_journal_target(org, actor, run.pk)

    def build():
        return harness.context(rows_by_table=rows, run=run, organization=org, actor=actor, notes=notes)

    LegacyRoomsPhase().run(build())
    report = JournalLessonMetaPhase().run(build())
    return org, run, report, offering, lessons


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="lesson_meta_actor", email="meta-actor@example.test", password="test-only"
    )


# ── forma / taksonomiya ──────────────────────────────────────────────────────


def test_the_phase_declares_a_batch_less_slot_keyed_shape(db):
    phase = JournalLessonMetaPhase()

    assert phase.phase_key == JOURNAL_LESSON_META_PHASE_KEY
    # 38 (journal_lessons) < 39 < 40 (journal_marks): saat düzəlişi
    # ``recompute_absence_hours``-dan ƏVVƏL oturmalıdır.
    assert phase.order == 39
    assert phase.source_tables == () and phase.entity_types == (LESSON_META_ENTITY_TYPE,)
    assert phase.declared_source_rows(harness.plan(harness.tables())) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_ledger_sort_key is str
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "lesson_meta_written"


def test_issue_severity_map_covers_exactly_the_metadata_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_lesson_meta_hours_fractional": "warning",
        "legacy_lesson_meta_hours_invalid": "warning",
        "legacy_lesson_meta_ambiguous": "warning",
        "legacy_lesson_meta_invalid": "warning",
        "legacy_lesson_meta_fake": "info",
        "legacy_lesson_meta_orphan": "info",
        "legacy_lesson_meta_lesson_absent": "info",
        "legacy_lesson_meta_topic_missing": "info",
        "legacy_lesson_meta_topic_truncated": "info",
        "legacy_lesson_meta_room_missing": "info",
        "legacy_lesson_meta_field_present": "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)


def test_the_phase_refuses_a_foreign_context():
    with pytest.raises(LegacyRehearsalConfigError) as excinfo:
        JournalLessonMetaPhase().run(object())

    assert excinfo.value.code == "legacy_rehearsal_context_invalid"


def test_the_phase_requires_its_upstream_phases(actor):
    rows = _rows(lesson_meta=[harness.lesson_meta_row(500)])
    org = harness.organization(actor, "meta-deps")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    context = harness.context(
        rows_by_table=rows,
        run=run,
        organization=org,
        actor=actor,
        phase_keys=("journal_periods", "journal_offerings"),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as excinfo:
        JournalLessonMetaPhase().run(context)

    assert excinfo.value.code == "legacy_rehearsal_phase_dependency_missing"


# ── mənbə tipləri (canlı sxem ``float``-dur) ─────────────────────────────────


def test_calendar_columns_accept_the_float_shape_of_the_live_schema():
    assert legacy_calendar_int(12.0) == 12
    assert legacy_calendar_int(None) == 0

    with pytest.raises(LegacyRehearsalEvidenceError):
        legacy_calendar_int(12.5)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.0, (1, "")),
        (2.0, (2, "")),
        (3.0, (3, "")),
        # 0.5 REAL dəyərdir və YUVARLAQLAŞDIRILMIR — saat yazılmır, işarələnir.
        (0.5, (0, "legacy_lesson_meta_hours_fractional")),
        (0.0, (0, "legacy_lesson_meta_hours_invalid")),
        (99.0, (0, "legacy_lesson_meta_hours_invalid")),
    ],
)
def test_lesson_hours_never_round_a_fractional_source_value(value, expected):
    assert legacy_lesson_hours(value) == expected


# ── zənginləşdirmə ───────────────────────────────────────────────────────────


def test_the_phase_writes_topic_room_and_hours_onto_the_lesson(actor):
    org, run, report, _offering, lessons = _run_phase(
        actor,
        "meta-basic",
        lesson_meta=[harness.lesson_meta_row(500, month=12.0, day=30.0, times="14:00", saatliq_ders=1.0)],
    )

    lesson = lessons[10]
    lesson.refresh_from_db()
    assert lesson.topic == "Sistemin arxitekturası"
    assert lesson.room.code == "myedu-room-4"
    assert lesson.room.building == "3"
    # J3 sabit 2 yazmışdı; mənbə 1 saat deyir → saxta qayıb blokunun kök səbəbi.
    assert lesson.hours == 1
    assert report.state_counts == {"lesson_meta_written": 1}
    assert _maps(org) == {"500:2": (LegacyEntityMap.State.MIGRATED, LESSON_MODEL_LABEL)}
    assert _issues(run) == {}


def test_a_slot_without_a_target_lesson_is_skipped(actor):
    org, run, report, _offering, _seeded = _run_phase(
        actor,
        "meta-absent",
        # 12/28 üçün J3 dərs yaratmayıb (fixture yalnız 30 və 31-i qurur).
        lesson_meta=[harness.lesson_meta_row(500, day=28.0)],
    )

    assert report.state_counts == {"lesson_meta_skipped": 1}
    assert _issues(run) == {("500:2", "legacy_lesson_meta_lesson_absent"): "info"}
    assert list(_lessons(org).values_list("topic", flat=True)) == ["", ""]


def test_fake_rows_are_skipped_by_the_existing_filter_rule(actor):
    org, run, report, _offering, lessons = _run_phase(
        actor, "meta-fake", lesson_meta=[harness.lesson_meta_row(500, fake=1)]
    )

    lessons[10].refresh_from_db()
    assert lessons[10].topic == "" and lessons[10].hours == 2
    assert report.state_counts == {"lesson_meta_skipped": 1}
    assert _issues(run) == {("500", "legacy_lesson_meta_fake"): "info"}


def test_an_unknown_journal_is_an_orphan(actor):
    _org, run, report, _offering, _lessons = _run_phase(
        actor, "meta-orphan", lesson_meta=[harness.lesson_meta_row(500, journal_id=9999)]
    )

    assert report.state_counts == {"lesson_meta_skipped": 1}
    assert _issues(run) == {("500", "legacy_lesson_meta_orphan"): "info"}


def test_an_unbuildable_time_is_quarantined(actor):
    _org, run, report, _offering, lessons = _run_phase(
        actor, "meta-invalid", lesson_meta=[harness.lesson_meta_row(500, times="25:99")]
    )

    lessons[10].refresh_from_db()
    assert lessons[10].hours == 2
    assert report.state_counts == {"lesson_meta_unresolved": 1}
    assert _issues(run) == {("500", "legacy_lesson_meta_invalid"): "warning"}


# ── ambiqüllük: fail closed, heç bir təxmin ──────────────────────────────────


def test_two_rows_claiming_one_slot_write_nothing(actor):
    """Canlı mənbədə 28 belə açar var; hansının doğru olduğu bilinmir."""

    org, run, report, _offering, lessons = _run_phase(
        actor,
        "meta-ambiguous",
        lesson_meta=[
            harness.lesson_meta_row(500, room=4, saatliq_ders=1.0),
            harness.lesson_meta_row(501, room=9, saatliq_ders=3.0),
        ],
    )

    lessons[10].refresh_from_db()
    assert lessons[10].topic == "" and lessons[10].room_id is None and lessons[10].hours == 2
    assert report.state_counts == {"lesson_meta_skipped": 2}
    assert _issues(run) == {
        ("500", "legacy_lesson_meta_ambiguous"): "warning",
        ("501", "legacy_lesson_meta_ambiguous"): "warning",
    }
    assert ambiguous_slots  # imzanın modul səthində qaldığını qeyd edir


def test_a_fake_duplicate_does_not_make_a_slot_ambiguous(actor):
    _org, _run, report, _offering, lessons = _run_phase(
        actor,
        "meta-fake-dup",
        lesson_meta=[
            harness.lesson_meta_row(500, saatliq_ders=1.0),
            harness.lesson_meta_row(501, saatliq_ders=3.0, fake=1),
        ],
    )

    lessons[10].refresh_from_db()
    assert lessons[10].hours == 1
    assert report.state_counts == {"lesson_meta_written": 1, "lesson_meta_skipped": 1}


# ── kəsr saat / çatışmayan istinadlar ────────────────────────────────────────


def test_a_fractional_hour_leaves_the_lesson_hours_untouched(actor):
    _org, run, _report, _offering, lessons = _run_phase(
        actor, "meta-half", lesson_meta=[harness.lesson_meta_row(500, saatliq_ders=0.5)]
    )

    lesson = lessons[10]
    lesson.refresh_from_db()
    # Saat YAZILMIR (yuvarlaqlaşdırma qadağandır), mövzu və otaq YENƏ yazılır.
    assert lesson.hours == 2
    assert lesson.topic == "Sistemin arxitekturası" and lesson.room is not None
    assert _issues(run) == {("500:2", "legacy_lesson_meta_hours_fractional"): "warning"}


def test_a_deleted_room_reference_is_recorded_not_invented(actor):
    _org, run, _report, _offering, lessons = _run_phase(
        actor, "meta-room-gone", lesson_meta=[harness.lesson_meta_row(500, room=9999)]
    )

    lessons[10].refresh_from_db()
    assert lessons[10].room_id is None and lessons[10].hours == 1
    assert _issues(run) == {("500:2", "legacy_lesson_meta_room_missing"): "info"}


def test_a_missing_syllabus_topic_is_recorded(actor):
    _org, run, _report, _offering, lessons = _run_phase(
        actor, "meta-topic-gone", lesson_meta=[harness.lesson_meta_row(500, sillabus=0)], lesson_topics=()
    )

    lessons[10].refresh_from_db()
    assert lessons[10].topic == ""
    assert _issues(run) == {("500:2", "legacy_lesson_meta_topic_missing"): "info"}


def test_a_row_with_nothing_writable_is_not_counted_as_written(actor):
    """Mövzu yox, otaq yox, saat kəsr → «yazıldı» sayılmamalıdır."""

    _org, run, report, _offering, lessons = _run_phase(
        actor,
        "meta-noop",
        lesson_meta=[harness.lesson_meta_row(500, sillabus=0, room=0, saatliq_ders=0.5)],
        lesson_topics=(),
    )

    lessons[10].refresh_from_db()
    assert lessons[10].topic == "" and lessons[10].room_id is None and lessons[10].hours == 2
    assert report.state_counts == {"lesson_meta_skipped": 1}
    assert _issues(run) == {
        ("500:2", "legacy_lesson_meta_topic_missing"): "info",
        ("500:2", "legacy_lesson_meta_room_missing"): "info",
        ("500:2", "legacy_lesson_meta_hours_fractional"): "warning",
    }


def test_a_long_topic_is_truncated_to_the_target_column(actor):
    _org, run, _report, _offering, lessons = _run_phase(
        actor,
        "meta-topic-long",
        lesson_meta=[harness.lesson_meta_row(500)],
        lesson_topics=(harness.syllabus_topic_row(movzu="ə" * 400),),
    )

    lesson = lessons[10]
    lesson.refresh_from_db()
    assert len(lesson.topic) == 255
    assert _issues(run) == {("500:2", "legacy_lesson_meta_topic_truncated"): "info"}


def test_html_entities_in_the_topic_are_decoded(actor):
    _org, _run, _report, _offering, lessons = _run_phase(
        actor,
        "meta-topic-entity",
        lesson_meta=[harness.lesson_meta_row(500)],
        lesson_topics=(harness.syllabus_topic_row(movzu="M&uuml;hazir&#601;"),),
    )

    lessons[10].refresh_from_db()
    assert lessons[10].topic == "Mühazirə"


# ── mövcud akademik məzmun qorunur ───────────────────────────────────────────


def test_an_existing_topic_or_room_is_never_overwritten(actor):
    rows = _rows(lesson_meta=[harness.lesson_meta_row(500)])
    org = harness.organization(actor, "meta-present")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    _offering, _enrollments, lessons = harness.seed_journal_target(org, actor, run.pk)

    def build():
        return harness.context(rows_by_table=rows, run=run, organization=org, actor=actor)

    LegacyRoomsPhase().run(build())
    existing = django_apps.get_model("exams", "ExamRoom").objects.create(
        organization=org, name="Müəllim seçimi", code="teacher-pick"
    )
    _lessons(org).filter(pk=lessons[10].pk).update(topic="Müəllimin öz mövzusu", room=existing)

    JournalLessonMetaPhase().run(build())

    lesson = lessons[10]
    lesson.refresh_from_db()
    assert lesson.topic == "Müəllimin öz mövzusu" and lesson.room_id == existing.pk
    # Saat isə QƏSDƏN düzəlir — J3-ün sabit 2-si məhz düzəldilməli dəyərdir.
    assert lesson.hours == 1
    assert _issues(run) == {("500:2", "legacy_lesson_meta_field_present"): "info"}


# ── idempotentlik / determinizm ──────────────────────────────────────────────


def test_a_second_run_repeats_the_decision_without_a_second_write(actor):
    rows = _rows(lesson_meta=[harness.lesson_meta_row(500)])
    org = harness.organization(actor, "meta-idempotent")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    _offering, _enrollments, lessons = harness.seed_journal_target(org, actor, run.pk)

    def build():
        return harness.context(rows_by_table=rows, run=run, organization=org, actor=actor)

    LegacyRoomsPhase().run(build())
    first = JournalLessonMetaPhase().run(build())
    second = JournalLessonMetaPhase().run(build())

    lessons[10].refresh_from_db()
    assert lessons[10].hours == 1
    assert second.phase_digest == first.phase_digest
    assert second.state_counts == first.state_counts
    assert LegacyEntityMap.objects.filter(organization=org, entity_type=LESSON_META_ENTITY_TYPE).count() == 1


def test_the_phase_digest_is_stable_across_organizations(actor):
    _org_a, _run_a, first, _off_a, _les_a = _run_phase(actor, "meta-det-a", lesson_meta=[harness.lesson_meta_row(500)])
    _org_b, _run_b, second, _off_b, _les_b = _run_phase(actor, "meta-det-b", lesson_meta=[harness.lesson_meta_row(500)])

    assert second.phase_digest == first.phase_digest


def test_a_changed_metadata_value_changes_the_seal(actor):
    _org_a, _run_a, first, _off_a, _les_a = _run_phase(
        actor, "meta-seal-a", lesson_meta=[harness.lesson_meta_row(500, saatliq_ders=1.0)]
    )
    _org_b, _run_b, second, _off_b, _les_b = _run_phase(
        actor, "meta-seal-b", lesson_meta=[harness.lesson_meta_row(500, saatliq_ders=2.0)]
    )

    assert second.phase_digest != first.phase_digest


def test_the_phase_notes_its_record_count(actor):
    notes: list[str] = []
    _org, _run, _report, _offering, _lessons = _run_phase(
        actor,
        "meta-notes",
        lesson_meta=[harness.lesson_meta_row(500), harness.lesson_meta_row(501, day=31.0)],
        notes=notes,
    )

    assert notes[-1] == "journal_lesson_meta.records.2"
