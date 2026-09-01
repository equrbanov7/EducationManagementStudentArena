"""Phase ``journal_excuse_documents`` (J13) — üzrlü qayıb SƏNƏDİNİN köçürülməsi.

Faza mövcud heç bir dəyəri dəyişmir: J4 qayıbı artıq ``allowed_qb`` pəncərəsi
ilə ``excused`` yazıb, burada YALNIZ sənəd sübutu əlavə olunur.  Testlər ona
görə iki şeyi ölçür: (1) hər mənbə sətri hədəfə düşür — tələbəsi tapılmasa da,
(2) heç bir ``LessonMark``/``Enrollment`` sətrinə toxunulmur.
"""

import datetime

from django.apps import apps as django_apps

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue
from apps.legacy_import.services.excuse_field_contracts import (
    ALLOWED_QB_DOCUMENT_FIELDS,
    EXCUSE_SUPERSET_INVARIANTS,
)
from apps.legacy_import.services.field_contracts import ALLOWED_QB_FIELDS
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
)
from apps.legacy_import.services.rehearsal_excuse_documents import (
    EXCUSE_ENTITY_TYPE,
    RULE_DOCUMENT_ABSENT,
    RULE_DOCUMENT_NAME_INVALID,
    RULE_NOTE_EMPTY,
    RULE_NOTE_TRUNCATED,
    RULE_STUDENT_UNRESOLVED,
    RULE_WINDOW_INVALID,
    build_request,
    excuse_materialization_digest,
    excuse_source_row_hash,
)
from apps.legacy_import.services.rehearsal_excuse_documents_phase import (
    DERIVED_DIGEST_NAMESPACE,
    EXCUSE_DOCUMENTS_PHASE_KEY,
    ISSUE_SEVERITY,
    JournalExcuseDocumentsPhase,
    severity_for,
)
from apps.legacy_import.services.source_extraction import _AUDITED_CONTRACTS
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db

_LEGACY_STUDENT = harness.STUDENT_A


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="excuse_docs_actor", email="excuse-docs-actor@example.test", password="test-only"
    )


def _documents(org):
    return django_apps.get_model("registrar", "LegacyExcuseDocument").objects.filter(organization=org)


def _issues(run):
    return set(
        LegacyMigrationIssue.objects.filter(run=run).values_list("entity_map__legacy_pk", "rule_code"),
    )


def _run_phase(actor, slug, rows, *, students=(_LEGACY_STUDENT,), notes=None):
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    for legacy_student in students:
        harness.seed_student_identity(org, actor, run.pk, legacy_student)
    report = JournalExcuseDocumentsPhase().run(
        harness.context(rows_by_table=rows, run=run, organization=org, actor=actor, notes=notes)
    )
    return org, run, report


# ---------------------------------------------------------------------------
# Forma / kontrakt (verilənlər bazasız)
# ---------------------------------------------------------------------------


def test_the_phase_declares_a_batch_less_row_keyed_shape(db):
    phase = JournalExcuseDocumentsPhase()

    assert phase.phase_key == EXCUSE_DOCUMENTS_PHASE_KEY and phase.order == 50
    # Cədvəl İDDİA edilmir: J4 onu pəncərə üçün oxuyur, bu faza sənəd üçün.
    assert phase.source_tables == () and phase.entity_types == (EXCUSE_ENTITY_TYPE,)
    assert phase.declared_source_rows(harness.plan(harness.tables())) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_ledger_sort_key is str
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "legacy_excuse_materialised"


def test_the_wide_contract_is_audited_and_supersets_the_narrow_one():
    """J4-ün dar kontraktı TOXUNULMAZ qalır; geniş olan onun üstünə gəlir."""

    assert ALLOWED_QB_DOCUMENT_FIELDS.source_table == ALLOWED_QB_FIELDS.source_table
    assert ALLOWED_QB_DOCUMENT_FIELDS.fingerprint != ALLOWED_QB_FIELDS.fingerprint
    assert set(ALLOWED_QB_FIELDS.allowed_fields) < set(ALLOWED_QB_DOCUMENT_FIELDS.allowed_fields)
    assert _AUDITED_CONTRACTS[ALLOWED_QB_DOCUMENT_FIELDS.fingerprint] is ALLOWED_QB_DOCUMENT_FIELDS
    for narrow, wide in EXCUSE_SUPERSET_INVARIANTS:
        assert set(narrow.allowed_fields) <= set(wide.allowed_fields)


def test_issue_severity_map_covers_exactly_the_excuse_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        RULE_STUDENT_UNRESOLVED: LegacyMigrationIssue.Severity.WARNING,
        RULE_WINDOW_INVALID: LegacyMigrationIssue.Severity.WARNING,
        RULE_DOCUMENT_ABSENT: LegacyMigrationIssue.Severity.INFO,
        RULE_DOCUMENT_NAME_INVALID: LegacyMigrationIssue.Severity.INFO,
        RULE_NOTE_EMPTY: LegacyMigrationIssue.Severity.INFO,
        RULE_NOTE_TRUNCATED: LegacyMigrationIssue.Severity.INFO,
    }
    # Naməlum kod fail-closed olur — səssiz "info"ya düşmür.
    with pytest.raises(LegacyRehearsalEvidenceError):
        severity_for("legacy_excuse_unknown_rule")


def test_the_context_type_is_checked_before_anything_is_read():
    with pytest.raises(LegacyRehearsalConfigError):
        JournalExcuseDocumentsPhase().run(object())


# ---------------------------------------------------------------------------
# Sətir → qərar (saf funksiya)
# ---------------------------------------------------------------------------


def _request(row, students=None):
    return build_request(legacy_pk=row["id"], row=row, students=students or {})


def test_a_resolved_row_becomes_a_linked_decision():
    row = harness.allowed_qb_row(1, student_id=7, desc="Texnopark", uniq="05Izfa", file="1697461819.jpg")
    request = _request(row, {"7": "target-pk"})

    assert request.payload["mapping_status"] == "linked"
    assert request.student_target_pk == "target-pk"
    assert request.payload["starts_on_text"] == "2021-12-30"
    assert request.payload["ends_on_text"] == "2021-12-31"
    # Xam mətn itkisiz qalır: saat da daxil olmaqla mənbənin öz dəyəri.
    assert request.payload["source_window_text"] == "2021-12-30 08:30:00|2021-12-31 23:59:00"
    assert request.payload["note"] == "Texnopark"
    assert request.payload["document_name"] == "1697461819.jpg"
    assert request.payload["source_batch_ref"] == "05Izfa"
    assert request.payload["source_owner_ref"] == "51"
    assert request.seal_key == "allowed_qb:1"
    # Fayl HƏR sətirdə çatışmır — bu, gözlənilən müşahidədir, xəta deyil.
    assert RULE_DOCUMENT_ABSENT in request.rule_codes
    assert RULE_STUDENT_UNRESOLVED not in request.rule_codes


def test_an_unresolved_student_is_kept_but_never_linked():
    """Sahibin qaydası: sətir İTMİR, sadəcə kanonik tələbəyə bağlanmır."""

    request = _request(harness.allowed_qb_row(2, student_id=9_999), {"7": "target-pk"})

    assert request.payload["mapping_status"] == "student_unresolved"
    assert request.student_target_pk == ""
    assert RULE_STUDENT_UNRESOLVED in request.rule_codes
    assert request.payload["source_student_ref"] == "9999"


def test_a_reversed_window_is_quarantined_as_metadata():
    row = harness.allowed_qb_row(3, student_id=7, start="2021-12-31", end="2021-12-30")
    request = _request(row, {"7": "target-pk"})

    assert request.payload["mapping_status"] == "window_invalid"
    assert request.payload["starts_on_text"] == "" and request.payload["ends_on_text"] == ""
    assert RULE_WINDOW_INVALID in request.rule_codes
    # Yararsız olsa da mənbənin xam mətni saxlanır.
    assert request.payload["source_window_text"].startswith("2021-12-31")


def test_an_empty_note_and_an_unsafe_file_name_are_reported_not_invented():
    request = _request(harness.allowed_qb_row(4, student_id=7, desc="  ", file="../../etc/passwd"), {"7": "t"})

    assert request.payload["note"] == "" and RULE_NOTE_EMPTY in request.rule_codes
    assert request.payload["document_name"] == ""
    assert RULE_DOCUMENT_NAME_INVALID in request.rule_codes


def test_a_long_note_is_truncated_and_the_truncation_is_reported():
    request = _request(harness.allowed_qb_row(5, student_id=7, desc="x" * 2_500), {"7": "t"})

    assert len(request.payload["note"]) == 2_000
    assert RULE_NOTE_TRUNCATED in request.rule_codes


def test_the_row_hash_and_the_materialization_digest_react_to_every_column():
    base = harness.allowed_qb_row(6, student_id=7)
    changed = harness.allowed_qb_row(6, student_id=7, desc="fərqli izah")

    assert excuse_source_row_hash(legacy_pk=6, row=base) != excuse_source_row_hash(legacy_pk=6, row=changed)

    key = ("myedu_mariadb", "allowed_qb", 6)
    payload = {"a": "1"}
    same = excuse_materialization_digest(natural_key=key, source_row_hash="ab", payload=payload)
    assert same == excuse_materialization_digest(natural_key=key, source_row_hash="ab", payload={"a": "1"})
    assert same != excuse_materialization_digest(natural_key=key, source_row_hash="ab", payload={"a": "2"})


# ---------------------------------------------------------------------------
# Faza icrası (hədəf + ledger)
# ---------------------------------------------------------------------------


def test_the_happy_path_materialises_one_document_per_source_row(actor):
    rows = harness.tables(
        allowed=[
            harness.allowed_qb_row(1, student_id=_LEGACY_STUDENT, desc="Texnopark"),
            harness.allowed_qb_row(2, student_id=_LEGACY_STUDENT, start="2022-01-10", end="2022-01-12"),
        ]
    )
    notes = []
    org, run, report = _run_phase(actor, "excuse-happy", rows, notes=notes)

    assert dict(report.state_counts) == {"legacy_excuse_materialised": 2}
    assert report.source_tables == () and report.declared_source_rows == 0
    assert notes == [f"{EXCUSE_DOCUMENTS_PHASE_KEY}.records.2"]

    documents = list(_documents(org).order_by("source_pk"))
    assert [d.source_pk for d in documents] == [1, 2]
    assert {d.mapping_status for d in documents} == {"linked"}
    assert documents[0].note == "Texnopark"
    assert documents[0].document_name == "1697461819.jpg"
    assert documents[0].starts_on == datetime.date(2021, 12, 30)
    assert documents[1].ends_on == datetime.date(2022, 1, 12)
    # Fayl hədəfdə YOXDUR — yalnız adı köçüb.
    assert all(not d.document for d in documents)
    assert all(not d.document_available for d in documents)
    assert ("allowed_qb:1", RULE_DOCUMENT_ABSENT) in _issues(run)


def test_an_unresolved_student_still_produces_a_stored_row(actor):
    rows = harness.tables(allowed=[harness.allowed_qb_row(1, student_id=9_999)])
    org, run, report = _run_phase(actor, "excuse-unresolved", rows)

    # Sətir SAXLANIR (ledger vəziyyəti J-facts ilə eyni: MIGRATED),
    # mapping problemi isə metadata + issue kimi görünür.
    assert dict(report.state_counts) == {"legacy_excuse_materialised": 1}
    document = _documents(org).get()
    assert document.mapping_status == "student_unresolved" and document.student_id is None
    assert ("allowed_qb:1", RULE_STUDENT_UNRESOLVED) in _issues(run)


def test_the_phase_never_touches_marks_or_enrolments(actor):
    """«Köhnə datanı dəyişmirik» — bu faza YALNIZ sübut əlavə edir."""

    rows = harness.tables(allowed=[harness.allowed_qb_row(1, student_id=_LEGACY_STUDENT)])
    org = harness.organization(actor, "excuse-readonly")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_student_identity(org, actor, run.pk, _LEGACY_STUDENT)
    harness.seed_journal_target(org, actor, run.pk)
    mark_model = django_apps.get_model("registrar", "LessonMark")
    enrollment_model = django_apps.get_model("registrar", "Enrollment")
    before = (
        set(mark_model.objects.filter(organization=org).values_list("id", "status", "score")),
        set(enrollment_model.objects.filter(organization=org).values_list("id", "absence_hours")),
    )

    JournalExcuseDocumentsPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    after = (
        set(mark_model.objects.filter(organization=org).values_list("id", "status", "score")),
        set(enrollment_model.objects.filter(organization=org).values_list("id", "absence_hours")),
    )
    assert before == after
    assert _documents(org).count() == 1


def test_a_resumed_run_reuses_its_seals_and_creates_no_duplicate(actor):
    rows = harness.tables(allowed=[harness.allowed_qb_row(1, student_id=_LEGACY_STUDENT)])
    org, run, first = _run_phase(actor, "excuse-resume", rows)

    second = JournalExcuseDocumentsPhase().run(
        harness.context(rows_by_table=rows, run=run, organization=org, actor=actor)
    )

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert _documents(org).count() == 1


def test_the_phase_refuses_to_run_without_the_identity_phase(actor):
    rows = harness.tables(allowed=[harness.allowed_qb_row(1)])
    org = harness.organization(actor, "excuse-nodep")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))

    with pytest.raises(LegacyRehearsalEvidenceError):
        JournalExcuseDocumentsPhase().run(
            harness.context(
                rows_by_table=rows,
                run=run,
                organization=org,
                actor=actor,
                phase_keys=(EXCUSE_DOCUMENTS_PHASE_KEY,),
            )
        )
