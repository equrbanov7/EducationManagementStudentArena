"""Phase ``legacy_rooms`` (J10) testləri: legacy otaq reyestri → ``exams.ExamRoom``.

Müqavilələr: legacy açarlı kod, KORPUS formatı (tam ədədin onluq mətni), ad
təkrarlarının ayrılması, boş ad / yararsız tutum taksonomiyası, idempotentlik
və cross-run determinizm.
"""

from django.apps import apps as django_apps

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue
from apps.legacy_import.services.rehearsal_authorizer import EXAM_ROOM_MODEL_LABEL
from apps.legacy_import.services.rehearsal_contracts import LegacyRehearsalConfigError
from apps.legacy_import.services.rehearsal_lesson_rooms_phase import (
    DERIVED_DIGEST_NAMESPACE,
    ISSUE_SEVERITY,
    LEGACY_ROOM_ENTITY_TYPE,
    LEGACY_ROOMS_PHASE_KEY,
    LegacyRoomsPhase,
    room_capacity,
    room_code,
)
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db


def _rooms(org):
    return django_apps.get_model("exams", "ExamRoom").objects.filter(organization=org).order_by("code")


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=LEGACY_ROOM_ENTITY_TYPE)
    }


def _run_phase(actor, slug, *, rooms, notes=None):
    rows = harness.tables(rooms=rooms)
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    context = harness.context(rows_by_table=rows, run=run, organization=org, actor=actor, notes=notes)
    return org, run, LegacyRoomsPhase().run(context), context


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="legacy_rooms_actor", email="rooms-actor@example.test", password="test-only"
    )


# ── forma / taksonomiya ──────────────────────────────────────────────────────


def test_the_phase_declares_a_batch_less_room_keyed_shape(db):
    phase = LegacyRoomsPhase()

    assert phase.phase_key == LEGACY_ROOMS_PHASE_KEY and phase.order == 13
    # ``rooms`` review_gated-dir (iddia EDİLƏ bilər), amma faza onu iddia ETMİR.
    assert phase.source_tables == () and phase.entity_types == (LEGACY_ROOM_ENTITY_TYPE,)
    assert phase.declared_source_rows(harness.plan(harness.tables())) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_ledger_sort_key is int
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "legacy_room_materialised"


def test_issue_severity_map_covers_exactly_the_room_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_room_name_truncated": "info",
        "legacy_room_capacity_invalid": "info",
        "legacy_room_name_placeholder": "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)


def test_the_phase_refuses_a_foreign_context():
    with pytest.raises(LegacyRehearsalConfigError) as excinfo:
        LegacyRoomsPhase().run(object())

    assert excinfo.value.code == "legacy_rehearsal_context_invalid"


def test_room_code_is_legacy_keyed_and_fits_the_target_column():
    assert room_code(4) == "myedu-room-4"
    assert len(room_code(215)) <= 32


@pytest.mark.parametrize(
    ("value", "expected"),
    [("28", (28, "")), (" 30 ", (30, "")), (30, (30, "")), ("", (0, "legacy_room_capacity_invalid"))],
)
def test_room_capacity_parses_the_char_column_fail_closed(value, expected):
    assert room_capacity(value) == expected


# ── materiallaşma ────────────────────────────────────────────────────────────


def test_the_phase_materialises_every_room_with_its_building(actor):
    org, run, report, _context = _run_phase(
        actor,
        "rooms-basic",
        rooms=[
            harness.room_row(4, name="03/2", bina=3, max_student_count="28"),
            harness.room_row(195, name="11", bina=5, max_student_count="20"),
        ],
    )

    rows = {room.code: room for room in _rooms(org)}
    assert set(rows) == {"myedu-room-4", "myedu-room-195"}
    assert rows["myedu-room-4"].name == "03/2"
    assert rows["myedu-room-4"].capacity == 28
    assert rows["myedu-room-4"].is_active is True
    # KORPUS: tam ədədin ONLUQ MƏTNİ — "3-cü korpus" DEYİL (modul qeydi).
    assert rows["myedu-room-4"].building == "3"
    assert rows["myedu-room-195"].building == "5"
    assert report.state_counts == {"legacy_room_materialised": 2}
    assert report.source_tables == () and report.batches == ()


def test_duplicate_room_names_stay_separate_rows(actor):
    """Canlı reyestrdə 25 ad təkrarı var — kimlik ADDAN qurula bilməz."""

    org, _run, _report, _context = _run_phase(
        actor,
        "rooms-dupname",
        rooms=[harness.room_row(6, name="11", bina=3), harness.room_row(195, name="11", bina=5)],
    )

    assert [(room.code, room.name, room.building) for room in _rooms(org)] == [
        ("myedu-room-195", "11", "5"),
        ("myedu-room-6", "11", "3"),
    ]


def test_the_ledger_binds_every_room_to_its_target(actor):
    org, run, _report, _context = _run_phase(actor, "rooms-ledger", rooms=[harness.room_row(4)])

    entity_map = LegacyEntityMap.objects.get(organization=org, entity_type=LEGACY_ROOM_ENTITY_TYPE)
    assert entity_map.legacy_pk == "4"
    assert entity_map.state == LegacyEntityMap.State.MIGRATED
    assert entity_map.target_model_label == EXAM_ROOM_MODEL_LABEL
    assert entity_map.target_pk == str(_rooms(org).get().pk)
    assert _issues(run) == {}


def test_a_blank_name_falls_back_to_the_legacy_code(actor):
    org, run, _report, _context = _run_phase(actor, "rooms-blank", rooms=[harness.room_row(4, name="   ")])

    assert _rooms(org).get().name == "myedu-room-4"
    assert _issues(run) == {("4", "legacy_room_name_placeholder"): "info"}


def test_an_unparseable_capacity_lands_on_zero_with_an_issue(actor):
    org, run, _report, _context = _run_phase(actor, "rooms-cap", rooms=[harness.room_row(4, max_student_count="n/a")])

    assert _rooms(org).get().capacity == 0
    assert _issues(run) == {("4", "legacy_room_capacity_invalid"): "info"}


def test_html_entities_in_the_name_are_decoded(actor):
    org, _run, _report, _context = _run_phase(
        actor, "rooms-entity", rooms=[harness.room_row(4, name="Auditoriya &uuml;st")]
    )

    assert _rooms(org).get().name == "Auditoriya üst"


# ── idempotentlik / determinizm ──────────────────────────────────────────────


def test_a_second_run_neither_duplicates_nor_overwrites(actor):
    rows = harness.tables(rooms=[harness.room_row(4, name="03/2", bina=3)])
    org = harness.organization(actor, "rooms-idempotent")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    first = LegacyRoomsPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    # İmtahan mərkəzi otağı sonradan adlandırır — import onu ƏVƏZ ETMİR.
    _rooms(org).update(name="Böyük zal", building="A")
    second = LegacyRoomsPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert _rooms(org).count() == 1
    assert _rooms(org).get().name == "Böyük zal" and _rooms(org).get().building == "A"
    assert second.phase_digest == first.phase_digest
    assert second.state_counts == first.state_counts


def test_the_phase_digest_is_stable_across_organizations(actor):
    _org_a, _run_a, first, _ctx_a = _run_phase(actor, "rooms-det-a", rooms=[harness.room_row(4), harness.room_row(9)])
    _org_b, _run_b, second, _ctx_b = _run_phase(actor, "rooms-det-b", rooms=[harness.room_row(4), harness.room_row(9)])

    # Digest-də HEÇ BİR hədəf UUID-si yoxdur → iki fərqli tenant eyni zənciri verir.
    assert second.phase_digest == first.phase_digest


def test_a_changed_room_value_changes_the_seal(actor):
    _org_a, _run_a, first, _ctx_a = _run_phase(actor, "rooms-seal-a", rooms=[harness.room_row(4, bina=3)])
    _org_b, _run_b, second, _ctx_b = _run_phase(actor, "rooms-seal-b", rooms=[harness.room_row(4, bina=5)])

    assert second.phase_digest != first.phase_digest


def test_the_phase_notes_its_record_count(actor):
    notes: list[str] = []
    _org, _run, _report, _context = _run_phase(
        actor, "rooms-notes", rooms=[harness.room_row(4), harness.room_row(9)], notes=notes
    )

    assert notes == ["legacy_rooms.records.2"]
