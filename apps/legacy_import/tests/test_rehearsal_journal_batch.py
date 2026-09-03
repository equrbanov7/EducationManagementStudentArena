"""Dəstə sərhədinin DAVRANIŞA təsir etmədiyinin sübutu (J2/J3/J4).

Sürət optimallaşdırması yazını buferləyir; yeganə real risk dəstə sərhədinin
qərarı dəyişməsidir (məs. eyni açar iki müxtəlif flush-a düşəndə).  Bu modul
həmin sərhədi qəsdən 1 sətrə endirib nəticəni defolt dəstə ilə müqayisə edir:
faza digest-i, vəziyyət sayları və yazılmış hədəf sətirləri EYNİ olmalıdır.
"""

import datetime
from decimal import Decimal

import pytest

from apps.legacy_import.services import rehearsal_journal_batch, rehearsal_journal_marks_targets
from apps.legacy_import.services.rehearsal_journal_batch import normalized_key
from apps.legacy_import.services.rehearsal_journal_enrollments_phase import JournalEnrollmentsPhase
from apps.legacy_import.services.rehearsal_journal_lessons_phase import JournalLessonsPhase
from apps.legacy_import.services.rehearsal_journal_marks_phase import JournalMarksPhase
from apps.legacy_import.services.rehearsal_journal_marks_targets import MarkWrite, classify_mark_write
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db


@pytest.fixture()
def batch_actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="journal_batch_actor", email="journal-batch@example.test", password="test-only"
    )


def _points(count):
    """Bir jurnalın iki dərs slotu üzərində ``count`` xana (iki tələbə)."""

    rows = []
    for index in range(count):
        rows.append(
            harness.point_row(
                100 + index,
                day_number="30" if index % 2 == 0 else "31",
                student_id=harness.STUDENT_A if index % 4 < 2 else harness.STUDENT_B,
                point="ie" if index % 3 else "8",
            )
        )
    return rows


def _run_marks(actor, slug, *, batch_rows, monkeypatch):
    monkeypatch.setattr(rehearsal_journal_marks_targets, "_MARK_BATCH", batch_rows)
    rows = harness.tables(points=_points(8))
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk)
    context = harness.context(rows_by_table=rows, run=run, organization=org, actor=actor)
    return JournalMarksPhase().run(context), org


def test_the_mark_writer_batch_size_does_not_change_the_phase_digest(batch_actor, monkeypatch):
    single, single_org = _run_marks(batch_actor, "marks-batch-1", batch_rows=1, monkeypatch=monkeypatch)
    bulk, bulk_org = _run_marks(batch_actor, "marks-batch-many", batch_rows=2_000, monkeypatch=monkeypatch)

    assert single.phase_digest == bulk.phase_digest
    assert dict(single.state_counts) == dict(bulk.state_counts)
    assert dict(single.issue_counts) == dict(bulk.issue_counts)
    assert _marks(single_org) == _marks(bulk_org)


def _marks(org):
    from django.apps import apps as django_apps

    model = django_apps.get_model("registrar", "LessonMark")
    return sorted(
        (str(row["lesson__date"]), str(row["lesson__start_time"]), row["status"], str(row["score"]))
        for row in model.objects.filter(organization=org).values(
            "lesson__date", "lesson__start_time", "status", "score"
        )
    )


def _run_enrollments(actor, slug, *, batch_rows, monkeypatch):
    monkeypatch.setattr(rehearsal_journal_batch, "BATCH_ROWS", batch_rows)
    rows = harness.tables(
        journals=[
            harness.journal_row(2, harness.UNIQID),
            harness.journal_row(3, harness.OTHER_UNIQID, students_id="not-json"),
        ]
    )
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk)
    context = harness.context(rows_by_table=rows, run=run, organization=org, actor=actor)
    return JournalEnrollmentsPhase().run(context), JournalLessonsPhase().run(context)


def test_the_journal_writer_batch_size_does_not_change_j2_or_j3(batch_actor, monkeypatch):
    single_j2, single_j3 = _run_enrollments(batch_actor, "j2-batch-1", batch_rows=1, monkeypatch=monkeypatch)
    bulk_j2, bulk_j3 = _run_enrollments(batch_actor, "j2-batch-many", batch_rows=2_000, monkeypatch=monkeypatch)

    assert single_j2.phase_digest == bulk_j2.phase_digest
    assert dict(single_j2.state_counts) == dict(bulk_j2.state_counts)
    assert dict(single_j2.issue_counts) == dict(bulk_j2.issue_counts)
    assert single_j3.phase_digest == bulk_j3.phase_digest
    assert dict(single_j3.state_counts) == dict(bulk_j3.state_counts)


def test_both_writers_read_their_batch_size_at_construction_time(monkeypatch):
    """Yuxarıdakı iki testin monkeypatch-i real təsir etməlidir (vacuous olmasın)."""

    monkeypatch.setattr(rehearsal_journal_batch, "BATCH_ROWS", 1)
    monkeypatch.setattr(rehearsal_journal_marks_targets, "_MARK_BATCH", 1)
    journal_writer = rehearsal_journal_batch.JournalBatchWriter(
        None, entity_type="lesson", source_table="journals", severity_for=str, materialiser=None
    )
    mark_writer = rehearsal_journal_marks_targets.LessonMarkWriter(None, None)

    assert journal_writer._batch_rows == 1
    assert mark_writer._batch_rows == 1


# ── saf yardımçılar ──────────────────────────────────────────────────────────


def test_the_normalised_key_folds_uuid_date_and_time_to_stable_text():
    key = normalized_key(("11111111-1111-1111-1111-111111111111", datetime.date(2021, 12, 30), datetime.time(14, 0)))

    assert key == ("11111111-1111-1111-1111-111111111111", "2021-12-30", "14:00:00")


@pytest.mark.parametrize(
    ("existing", "allow_existing", "expected"),
    [
        (None, True, "written"),
        (None, False, "written"),
        (("present", None), False, "superseded"),
        (("present", None), True, "written"),
        (("absent", None), True, "conflict"),
        (("present", Decimal("8")), True, "conflict"),
    ],
)
def test_the_mark_classification_ladder_matches_the_get_or_create_semantics(existing, allow_existing, expected):
    request = MarkWrite(
        lesson_pk="lesson", enrollment_pk="enrollment", status="present", score=None, allow_existing=allow_existing
    )

    assert classify_mark_write(existing, request) == expected
