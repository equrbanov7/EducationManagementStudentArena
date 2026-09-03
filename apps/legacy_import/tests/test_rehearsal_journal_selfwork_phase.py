"""Phase ``journal_selfwork`` (J9) testləri: sillabus mövzuları → ``SelfWorkTopic``.

Müqavilələr: adlı/adsız mövzu, HTML entity, 255 kəsimi, 10 tavanı, ``SelfWorkMark``
YARADILMIR, mövcud komponent balı POZULMUR, idempotentlik və determinizm.
"""

from django.apps import apps as django_apps

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue
from apps.legacy_import.services.rehearsal_authorizer import COURSE_OFFERING_MODEL_LABEL
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
)
from apps.legacy_import.services.rehearsal_journal_selfwork_phase import (
    DERIVED_DIGEST_NAMESPACE,
    ISSUE_SEVERITY,
    JOURNAL_SELFWORK_PHASE_KEY,
    SELFWORK_ENTITY_TYPE,
    JournalSelfWorkPhase,
)
from apps.legacy_import.services.rehearsal_journal_selfwork_source import SELF_WORK_MAX_TOPICS
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db


def _topics(org):
    return django_apps.get_model("registrar", "SelfWorkTopic").objects.filter(organization=org)


def _titles(org, offering):
    return list(_topics(org).filter(offering=offering).order_by("order").values_list("title", flat=True))


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=SELFWORK_ENTITY_TYPE)
    }


def _run_phase(actor, slug, *, topics, journals=None, syllabi=None, notes=None, seed=True):
    rows = harness.tables(topics=topics, journals=journals, syllabi=syllabi)
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    offering = None
    if seed:
        offering, _enrollments, _lessons = harness.seed_journal_target(org, actor, run.pk)
    report = JournalSelfWorkPhase().run(
        harness.context(rows_by_table=rows, run=run, organization=org, actor=actor, notes=notes)
    )
    return org, run, report, offering


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="journal_selfwork_actor", email="jsw-actor@example.test", password="test-only"
    )


# ── forma / taksonomiya ──────────────────────────────────────────────────────


def test_the_phase_declares_a_batch_less_journal_keyed_shape(db):
    phase = JournalSelfWorkPhase()

    assert phase.phase_key == JOURNAL_SELFWORK_PHASE_KEY and phase.order == 45
    # ``sillabus``/``sillabus_serbest_is`` design_gated-dir → İDDİA EDİLMİR.
    assert phase.source_tables == () and phase.entity_types == (SELFWORK_ENTITY_TYPE,)
    assert phase.declared_source_rows(harness.plan(harness.tables())) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_ledger_sort_key is str
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "journal_selfwork_topics_written"
    assert phase.derived_state_key("skipped") == "journal_selfwork_topics_absent"


def test_issue_severity_map_covers_exactly_the_selfwork_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_selfwork_syllabus_missing": "info",
        "legacy_selfwork_topics_absent": "info",
        "legacy_selfwork_topic_placeholder": "info",
        "legacy_selfwork_title_truncated": "info",
        "legacy_selfwork_topics_truncated": "info",
        "legacy_selfwork_topics_present": "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        JournalSelfWorkPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


def test_the_dependency_gate_requires_the_offerings_phase():
    rows = harness.tables()
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalSelfWorkPhase().run(harness.context(rows_by_table=rows, phase_keys=("journal_selfwork",)))

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


# ── köçürmə ──────────────────────────────────────────────────────────────────


def test_named_topics_are_written_in_source_id_order(actor):
    notes = []
    org, run, report, offering = _run_phase(
        actor,
        "sw-named",
        topics=[
            harness.selfwork_topic_row(3, name="2. İkinci mövzu"),
            harness.selfwork_topic_row(7, name="1. Birinci mövzu"),
        ],
        notes=notes,
    )

    # Sıra mənbə PK-sınındır (3 → 7), mətndəki öz nömrələməsinin DEYİL: legacy
    # nömrələmə boşluqlu/səhv ola bilər, onu "düzəltmək" tarixi faktı dəyişərdi.
    assert _titles(org, offering) == ["2. İkinci mövzu", "1. Birinci mövzu"]
    assert dict(report.state_counts) == {"journal_selfwork_topics_written": 1}
    assert _issues(run) == {}
    assert notes == [f"{JOURNAL_SELFWORK_PHASE_KEY}.records.1"]
    observation = run.entity_observations.get(entity_map__entity_type=SELFWORK_ENTITY_TYPE)
    assert observation.target_model_label == COURSE_OFFERING_MODEL_LABEL
    assert observation.target_pk == str(offering.pk)


def test_html_entities_are_decoded_and_whitespace_collapsed(actor):
    org, _run, _report, offering = _run_phase(
        actor,
        "sw-entities",
        topics=[harness.selfwork_topic_row(1, name="1. Ətraf t&#601;bii   m&uuml;hit &amp; &ccedil;ay")],
    )

    assert _titles(org, offering) == ["1. Ətraf təbii mühit & çay"]


def test_a_blank_name_becomes_a_numbered_placeholder_with_an_info(actor):
    org, run, _report, offering = _run_phase(
        actor,
        "sw-blank",
        topics=[
            harness.selfwork_topic_row(1, name="Real mövzu"),
            harness.selfwork_topic_row(2, name="   "),
        ],
    )

    # Sətir ATILMIR — atmaq sonrakı mövzunun nömrəsini sürüşdürərdi.
    assert _titles(org, offering) == ["Real mövzu", "Sərbəst iş 2"]
    assert _issues(run) == {(harness.UNIQID, "legacy_selfwork_topic_placeholder"): "info"}


def test_a_long_title_is_truncated_to_the_column_width_with_an_info(actor):
    org, run, _report, offering = _run_phase(actor, "sw-long", topics=[harness.selfwork_topic_row(1, name="ə" * 400)])

    assert _titles(org, offering) == ["ə" * 255]
    assert _issues(run) == {(harness.UNIQID, "legacy_selfwork_title_truncated"): "info"}


def test_more_than_ten_topics_are_capped_and_reported(actor):
    org, run, _report, offering = _run_phase(
        actor,
        "sw-cap",
        topics=[harness.selfwork_topic_row(index, name=f"Mövzu {index}") for index in range(1, 14)],
    )

    titles = _titles(org, offering)
    assert len(titles) == SELF_WORK_MAX_TOPICS == 10
    assert titles[0] == "Mövzu 1" and titles[-1] == "Mövzu 10"
    assert _issues(run) == {(harness.UNIQID, "legacy_selfwork_topics_truncated"): "info"}


def test_a_journal_without_a_resolvable_syllabus_is_skipped_with_an_info(actor):
    org, run, report, offering = _run_phase(
        actor,
        "sw-no-syllabus",
        topics=[harness.selfwork_topic_row(1, name="Mövzu")],
        journals=[harness.journal_row(2, harness.UNIQID, sillabus_id=0)],
    )

    assert _titles(org, offering) == []
    assert dict(report.state_counts) == {"journal_selfwork_topics_absent": 1}
    assert _issues(run) == {(harness.UNIQID, "legacy_selfwork_syllabus_missing"): "info"}


def test_a_syllabus_without_topics_is_skipped_with_an_info(actor):
    org, run, report, offering = _run_phase(actor, "sw-no-topics", topics=[])

    assert _titles(org, offering) == []
    assert dict(report.state_counts) == {"journal_selfwork_topics_absent": 1}
    assert _issues(run) == {(harness.UNIQID, "legacy_selfwork_topics_absent"): "info"}


# ── müqavilələr: nə DƏYİŞMİR ─────────────────────────────────────────────────


def test_no_self_work_mark_is_ever_created(actor):
    """Legacy ``si`` balı aqreqatdır — mövzu-başına təhvil işarəsi UYDURULMUR."""

    org, _run, _report, _offering = _run_phase(
        actor,
        "sw-no-marks",
        topics=[harness.selfwork_topic_row(index, name=f"Mövzu {index}") for index in range(1, 4)],
    )

    assert django_apps.get_model("registrar", "SelfWorkMark").objects.filter(organization=org).count() == 0


def test_an_existing_component_score_is_left_untouched(actor):
    """J5-in yazdığı ``si`` komponent balı bu fazadan sonra bayt-bəbayt eynidir."""

    from decimal import Decimal

    rows = harness.tables(topics=[harness.selfwork_topic_row(1, name="Mövzu 1")])
    org = harness.organization(actor, "sw-component")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    offering, enrollments, _lessons = harness.seed_journal_target(org, actor, run.pk)
    component = django_apps.get_model("registrar", "AssessmentComponent").objects.create(
        organization=org, offering=offering, name="Sərbəst iş", kind="self_work", max_score=10, order=4
    )
    score = django_apps.get_model("registrar", "ComponentScore").objects.create(
        organization=org, component=component, enrollment=enrollments[harness.STUDENT_A], score=Decimal("7.00")
    )

    JournalSelfWorkPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    score.refresh_from_db()
    component.refresh_from_db()
    assert score.score == Decimal("7.00")
    assert (component.kind, component.max_score) == ("self_work", 10)
    assert _titles(org, offering) == ["Mövzu 1"]


def test_a_second_run_neither_duplicates_nor_overwrites(actor):
    """İdempotentlik + determinizm: eyni möhür, eyni digest, əlavə sətir yox."""

    rows = harness.tables(topics=[harness.selfwork_topic_row(1, name="Mövzu 1")])
    org = harness.organization(actor, "sw-idempotent")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    offering, _enrollments, _lessons = harness.seed_journal_target(org, actor, run.pk)

    first = JournalSelfWorkPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    second = JournalSelfWorkPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert first.phase_digest == second.phase_digest
    assert dict(second.state_counts) == {"journal_selfwork_topics_written": 1}
    assert _titles(org, offering) == ["Mövzu 1"]


def test_an_offering_that_already_has_topics_is_never_overwritten(actor):
    """Canlı müəllim işi (və ya başqa run) import tərəfindən silinmir."""

    rows = harness.tables(topics=[harness.selfwork_topic_row(1, name="Legacy mövzu")])
    org = harness.organization(actor, "sw-occupied")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    offering, _enrollments, _lessons = harness.seed_journal_target(org, actor, run.pk)
    django_apps.get_model("registrar", "SelfWorkTopic").objects.create(
        organization=org, offering=offering, title="Müəllimin mövzusu", order=1
    )

    report = JournalSelfWorkPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert _titles(org, offering) == ["Müəllimin mövzusu"]
    assert dict(report.state_counts) == {"journal_selfwork_topics_absent": 1}
    assert _issues(run) == {(harness.UNIQID, "legacy_selfwork_topics_present"): "info"}


def test_out_of_order_source_primary_keys_fail_closed(actor):
    """Mənbə PK sırası pozulubsa faza təxmin etmir — fail-closed dayanır."""

    rows = harness.tables(
        topics=[
            harness.selfwork_topic_row(7, name="Sonrakı"),
            harness.selfwork_topic_row(3, name="Əvvəlki"),
        ]
    )
    org = harness.organization(actor, "sw-order")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk)

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalSelfWorkPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert exc_info.value.code == "legacy_rehearsal_source_pk_order_invalid"
