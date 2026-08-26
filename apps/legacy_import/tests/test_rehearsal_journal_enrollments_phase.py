"""Phase ``journal_enrollments`` (J2) testləri: parse, orphan, unresolved, merge."""

import datetime
import hashlib
from dataclasses import replace
from types import SimpleNamespace

from django.contrib.auth import get_user_model

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyImportBatch, LegacyMigrationIssue, LegacyMigrationRun
from apps.legacy_import.services.field_contracts import JOURNAL_FIELDS
from apps.legacy_import.services.ledger import TargetValidation, create_run, start_run, upsert_entity_map
from apps.legacy_import.services.rehearsal_authorizer import (
    COURSE_OFFERING_MODEL_LABEL,
    ENROLLMENT_MODEL_LABEL,
    USER_MODEL_LABEL,
    build_target_validators,
)
from apps.legacy_import.services.rehearsal_contracts import (
    DEFAULT_BATCH_ROWS,
    SOURCE_SYSTEM,
    EmailTrustPolicy,
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    RehearsalContext,
    RehearsalPolicy,
    StudentIdentifierPolicy,
    UsernamePolicy,
    encoded_part,
)
from apps.legacy_import.services.rehearsal_journal_enrollments_phase import (
    DERIVED_DIGEST_NAMESPACE,
    ISSUE_SEVERITY,
    JOURNAL_ENROLLMENT_ENTITY_TYPE,
    JOURNAL_ENROLLMENTS_PHASE_KEY,
    JournalEnrollmentsPhase,
    enrollment_derivation_hash,
    parse_student_ids,
)
from apps.legacy_import.services.rehearsal_journal_offerings_source import parse_group_ids
from apps.legacy_import.services.rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.services.source_extraction import LegacyDiscoveredTable
from apps.organizations.models import AcademicPeriod, Membership, Organization, Role
from core.constants import AcademicPeriodType, OrganizationType

_STUDENT_ENTITY_TYPE = "student"
_PHASE_KEYS = (
    "academic_structure",
    "academic_catalog",
    "identity_cohort",
    "student_placement",
    "worker_materialisation",
    "sar_materialisation",
    "journal_periods",
    "journal_offerings",
    "journal_enrollments",
    "journal_lessons",
)
_SOURCE_COLUMNS = JOURNAL_FIELDS.allowed_fields


# ---------------------------------------------------------------------------
# Fake source (J1 fixture-ləri ilə eyni forma)
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, description, rows):
        self.description = description
        self._rows = list(rows)
        self._position = 0

    def fetchmany(self, size):
        chunk = self._rows[self._position : self._position + size]
        self._position += len(chunk)
        return chunk

    def close(self):
        return None


class _FakeSourceConnection:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.rolled_back = False
        self.closed = False

    def server_is_read_only(self):
        return True

    def begin_read_only_snapshot(self):
        return None

    def session_is_read_only(self):
        return True

    def discover_table(self, source_table):
        return LegacyDiscoveredTable(
            source_table=source_table,
            column_names=_SOURCE_COLUMNS,
            primary_key_fields=("id",),
        )

    def open_compiled_select(self, query):
        self.statements.append(query.mysql_statement())
        field_names = query.projection.field_names
        return _FakeCursor(
            tuple((field_name, None, None, None, None, None, None) for field_name in field_names),
            [tuple(row[field_name] for field_name in field_names) for row in self.rows],
        )

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _factory(rows):
    connections = []

    def build():
        connection = _FakeSourceConnection(rows)
        connections.append(connection)
        return connection

    build.connections = connections
    return build


def _journal_row(legacy_pk, uniqid, **overrides):
    values = {
        "id": legacy_pk,
        "uniqid": uniqid,
        "lesson_id": 64,
        "semestr": 1,
        "groups_id": '["2"]',
        "students_id": '["42","43"]',
        "teacher_id": 17,
        "fake": 0,
        "sonra_sil": 0,
        "active": 1,
    }
    values.update(overrides)
    return values


def _plan(rows):
    from apps.legacy_import.services.table_plan import LegacyTablePlan, load_legacy_table_plan

    canonical = load_legacy_table_plan()
    return LegacyTablePlan(
        version=canonical.version,
        fingerprint=canonical.fingerprint,
        source_snapshot_sha256=canonical.source_snapshot_sha256,
        expected_row_count=rows,
        entries=(replace(canonical.entry_for("journals"), expected_rows=rows),),
    )


def _policy(**overrides):
    values = {
        "phase_keys": _PHASE_KEYS,
        "username_policy": UsernamePolicy.LEGACY_KEY,
        "student_identifier_policy": StudentIdentifierPolicy.LEGACY_PK,
        "email_trust_policy": EmailTrustPolicy.DENY_ALL,
        "email_trust_manifest_digest": "",
        "batch_rows": DEFAULT_BATCH_ROWS,
        "source_chunk_size": 1_000,
        "max_staged_accounts": 0,
        "student_role_name": "",
        "worker_role_name": "",
    }
    values.update(overrides)
    return RehearsalPolicy(**values)


def _allow(**_kwargs):
    return True


def _context(*, plan, factory, policy=None, run_id=None, organization=None, actor=None, cancelled=None, notes=None):
    return RehearsalContext(
        run_id=run_id,
        organization=organization,
        actor=actor,
        authorize=_allow,
        target_validators=build_target_validators(),
        policy=policy or _policy(),
        plan=plan,
        source_connection_factory=factory,
        target_identity_snapshot=None,
        authoritative_email_policy=None,
        cancellation_requested=cancelled if cancelled is not None else (lambda: False),
        stdout_note=(notes if notes is not None else []).append,
    )


# ---------------------------------------------------------------------------
# Saf forma / taksonomiya (verilənlər bazasız)
# ---------------------------------------------------------------------------


def test_the_phase_declares_a_batch_less_lexicographic_shape():
    phase = JournalEnrollmentsPhase()

    assert phase.phase_key == JOURNAL_ENROLLMENTS_PHASE_KEY and phase.order == 36
    assert phase.source_tables == () and phase.entity_types == (JOURNAL_ENROLLMENT_ENTITY_TYPE,)
    assert phase.declared_source_rows(_plan(3)) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    # Açar mətndir ("uniqid:student"): rebuild sıralaması leksikoqrafikdir.
    assert phase.derived_ledger_sort_key("rooBx39tsK:42") == "rooBx39tsK:42"
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "enrollment_materialised"
    assert phase.derived_state_key("skipped") == "enrollment_skipped"
    assert phase.derived_state_key("quarantined") == "enrollment_unresolved"


def test_issue_severity_map_covers_exactly_the_enrollment_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_journal_students_invalid": "warning",
        "legacy_journal_student_unresolved": "warning",
        "legacy_journal_student_inactive": "warning",
        "legacy_journal_enrollment_orphan": "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)
    assert all(rule_code.startswith("legacy_journal_") for rule_code in ISSUE_SEVERITY)


def test_the_student_parser_is_the_shared_strict_array_parser():
    # ``students_id`` ``groups_id`` ilə eyni formadadır — parser paylaşılır.
    assert parse_student_ids is parse_group_ids
    assert parse_student_ids('["42","43","42"]') == (42, 43)
    assert parse_student_ids("[]") is None
    assert parse_student_ids("not-json") is None


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        JournalEnrollmentsPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


@pytest.mark.parametrize(
    "phase_keys",
    [
        ("journal_enrollments",),
        ("journal_offerings", "journal_enrollments"),
        ("journal_offerings", "student_placement", "journal_enrollments"),
        ("student_placement", "sar_materialisation", "journal_enrollments"),
    ],
)
def test_the_dependency_gate_is_evidence_not_config(phase_keys):
    context = _context(plan=_plan(0), factory=_factory([]), policy=_policy(phase_keys=phase_keys))

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalEnrollmentsPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


def test_the_enrollment_derivation_hash_follows_the_documented_recipe():
    digest = hashlib.sha256(b"legacy-rehearsal-journal-enrollment-derivation-v1\x00")
    for part in (
        JOURNAL_FIELDS.fingerprint,
        "rooBx39tsK:42",
        "b" * 64,
        "materialised",
        "42",
        "resolved",
        "resolved",
    ):
        digest.update(encoded_part(part))

    computed = enrollment_derivation_hash(
        seal_key="rooBx39tsK:42",
        row_hash="b" * 64,
        outcome_token="materialised",
        student_ref="42",
        offering_state="resolved",
        student_state="resolved",
    )

    assert computed == digest.hexdigest()
    assert computed != enrollment_derivation_hash(
        seal_key="rooBx39tsK:42",
        row_hash="b" * 64,
        outcome_token="unresolved",
        student_ref="42",
        offering_state="resolved",
        student_state="missing",
    )


# ---------------------------------------------------------------------------
# Ledger-li mühit
# ---------------------------------------------------------------------------


@pytest.fixture()
def enrollment_actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="journal_enrollments_actor",
        email="journal-enrollments-actor@example.test",
        password="test-only",
    )


def _activate_member(organization, user, role_name):
    """Aktiv üzvlük (PG ``registrar_guard_active_member`` tələbi)."""

    role, _created = Role.objects.get_or_create(
        organization=organization,
        name=role_name,
        defaults={"display_name": role_name.title(), "level": 50, "permissions": []},
    )
    Role.objects.filter(pk=role.pk).update(is_active=True)
    Membership.objects.get_or_create(organization=organization, user=user, role=role, defaults={"is_active": True})
    return role


def _organization(actor, slug):
    return Organization.objects.create(
        name=f"Journal {slug}",
        slug=slug,
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )


def _running_run(organization, actor, *, policy, plan):
    from apps.legacy_import.services.table_plan import TABLE_PLAN_VERSION

    run = create_run(
        actor=actor,
        authorize=_allow,
        organization=organization,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=plan.source_snapshot_sha256,
        snapshot_size_bytes=2_142_912_818,
        source_row_count=plan.expected_row_count,
        schema_version=f"{TABLE_PLAN_VERSION}.{plan.fingerprint[:12]}",
        transform_version=policy.transform_version(),
        mode=LegacyMigrationRun.Mode.REHEARSAL,
        accounting_mode=LegacyMigrationRun.AccountingMode.BATCH,
        origin=LegacyMigrationRun.Origin.COMMAND,
    )
    return start_run(run_id=run.pk, actor=actor, authorize=_allow)


def _seed_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _map(run_id, actor, *, entity_type, legacy_pk, label, target_pk, validators=None):
    return upsert_entity_map(
        run_id=run_id,
        actor=actor,
        authorize=_allow,
        entity_type=entity_type,
        legacy_pk=str(legacy_pk),
        source_row_hash=_seed_hash(f"{entity_type}:{legacy_pk}"),
        state=LegacyEntityMap.State.MIGRATED,
        target_model_label=label,
        target_pk=str(target_pk),
        target_validators=validators if validators is not None else build_target_validators(),
    )


def _make_offering(organization):
    from django.apps import apps as django_apps

    subject = django_apps.get_model("registrar", "Subject").objects.create(
        organization=organization, code="MYEDU-64", name="Proqramlaşdırmanın əsasları", ects=5
    )
    period = AcademicPeriod.objects.create(
        organization=organization,
        name="Payız",
        academic_year="2021/2022",
        period_type=AcademicPeriodType.SEMESTER,
        start_date=datetime.date(2021, 9, 15),
        end_date=datetime.date(2022, 1, 31),
    )
    return django_apps.get_model("registrar", "CourseOffering").objects.create(
        organization=organization, subject=subject, period=period, lesson_hours=0, is_active=True
    )


def _seed_references(organization, actor, run_id, *, django_user_model, uniqids=("rooBx39tsK",), student_pks=(42, 43)):
    """Əvvəlki fazaların (J1/identity) qoyub getdiyi map-lar."""

    offering = _make_offering(organization)
    for uniqid in uniqids:
        _map(
            run_id,
            actor,
            entity_type=COURSE_OFFERING_ENTITY_TYPE,
            legacy_pk=uniqid,
            label=COURSE_OFFERING_MODEL_LABEL,
            target_pk=offering.pk,
        )
    students = {}
    for legacy_pk in student_pks:
        student = django_user_model.objects.create_user(
            username=f"myedu.student.{organization.slug}.{legacy_pk}", email="", password=None
        )
        # PG-də ``registrar_guard_active_member`` Enrollment.student üçün AKTİV
        # üzvlük tələb edir; real axında bunu ``sar_materialisation`` (order 28)
        # bu fazadan (36) ƏVVƏL verir, ona görə fixture həmin vəziyyəti qurur.
        _activate_member(organization, student, "student")
        # Tələbə map-ı icazəli stub validatorla möhürlənir: identity fazası bu
        # run-da işləməyib, amma map onun buraxdığı formadadır (student → auth.user).
        _map(
            run_id,
            actor,
            entity_type=_STUDENT_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            label=USER_MODEL_LABEL,
            target_pk=student.pk,
            validators={USER_MODEL_LABEL: lambda **_kwargs: TargetValidation(True, True)},
        )
        students[legacy_pk] = student
    return offering, students


def _seeded_context(organization, actor, run, *, rows, policy=None, notes=None, cancelled=None):
    context = _context(
        plan=_plan(len(rows)),
        factory=_factory(rows),
        policy=policy or _policy(),
        organization=organization,
        actor=actor,
        notes=notes,
        cancelled=cancelled,
    )
    return replace(context, run_id=run.pk)


def _states(run):
    return dict(
        run.entity_observations.filter(entity_map__entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE).values_list(
            "entity_map__legacy_pk", "state"
        )
    )


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE)
    }


def _enrollments(organization):
    from django.apps import apps as django_apps

    return django_apps.get_model("registrar", "Enrollment").objects.filter(organization=organization)


@pytest.mark.django_db
def test_the_happy_path_creates_one_mandatory_enrollment_per_student(enrollment_actor, django_user_model):
    actor = enrollment_actor
    organization = _organization(actor, "journal-enrollments-primary")
    rows = [_journal_row(2, "rooBx39tsK")]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    offering, students = _seed_references(organization, actor, run.pk, django_user_model=django_user_model)
    notes = []

    report = JournalEnrollmentsPhase().run(_seeded_context(organization, actor, run, rows=rows, notes=notes))

    assert dict(report.state_counts) == {"enrollment_materialised": 2}
    assert _states(run) == {"rooBx39tsK:42": "migrated", "rooBx39tsK:43": "migrated"}
    assert _issues(run) == {}
    assert notes == [f"{JOURNAL_ENROLLMENTS_PHASE_KEY}.records.2"]
    assert LegacyImportBatch.objects.filter(run=run).count() == 0
    enrollments = {enrollment.student_id: enrollment for enrollment in _enrollments(organization)}
    assert set(enrollments) == {students[42].pk, students[43].pk}
    for enrollment in enrollments.values():
        assert enrollment.offering_id == offering.pk
        # A.2: kind defoltu mandatory, status modelin öz defoltu (enrolled).
        assert enrollment.kind == "mandatory"
        assert enrollment.status == "enrolled"
    observation = run.entity_observations.get(entity_map__legacy_pk="rooBx39tsK:42")
    assert observation.target_model_label == ENROLLMENT_MODEL_LABEL
    assert observation.target_pk == str(enrollments[students[42].pk].pk)


@pytest.mark.django_db
def test_students_of_an_unmaterialised_journal_are_skipped_as_orphans(enrollment_actor, django_user_model):
    """J1-də süzülmüş/karantinlənmiş jurnalın tələbələri yeni anomaliya deyil."""

    actor = enrollment_actor
    organization = _organization(actor, "journal-enrollments-orphan")
    rows = [_journal_row(2, "fakeAAAAAA", fake=1)]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    # J1 bu jurnalı SKIPPED möhürləyib — offering map-ı yoxdur; yalnız tələbələr var.
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model, uniqids=())

    report = JournalEnrollmentsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"enrollment_skipped": 2}
    assert _states(run) == {"fakeAAAAAA:42": "skipped", "fakeAAAAAA:43": "skipped"}
    assert _issues(run) == {
        ("fakeAAAAAA:42", "legacy_journal_enrollment_orphan"): "info",
        ("fakeAAAAAA:43", "legacy_journal_enrollment_orphan"): "info",
    }
    assert _enrollments(organization).count() == 0


@pytest.mark.django_db
def test_an_unresolved_student_skips_only_its_own_row(enrollment_actor, django_user_model):
    """Spec J2: tələbə EntityMap-da yoxdursa o sətir SKIPPED, jurnalın qalanı davam edir."""

    actor = enrollment_actor
    organization = _organization(actor, "journal-enrollments-unresolved")
    rows = [_journal_row(2, "rooBx39tsK", students_id='["42","999"]')]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model, student_pks=(42,))

    report = JournalEnrollmentsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"enrollment_materialised": 1, "enrollment_skipped": 1}
    assert _states(run) == {"rooBx39tsK:42": "migrated", "rooBx39tsK:999": "skipped"}
    assert _issues(run) == {("rooBx39tsK:999", "legacy_journal_student_unresolved"): "warning"}
    assert _enrollments(organization).count() == 1


@pytest.mark.django_db
def test_a_broken_students_array_quarantines_at_the_journal_level(enrollment_actor, django_user_model):
    actor = enrollment_actor
    organization = _organization(actor, "journal-enrollments-broken")
    rows = [
        _journal_row(2, "brokenAAAA", students_id="not-json"),
        _journal_row(3, "emptyBBBBB", students_id="[]"),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model)

    report = JournalEnrollmentsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"enrollment_unresolved": 2}
    # Seal açarı jurnalın özüdür — tələbə açarları hamısı ":" daşıdığından toqquşmur.
    assert _states(run) == {"brokenAAAA": "quarantined", "emptyBBBBB": "quarantined"}
    assert _issues(run) == {
        ("brokenAAAA", "legacy_journal_students_invalid"): "warning",
        ("emptyBBBBB", "legacy_journal_students_invalid"): "warning",
    }
    assert _enrollments(organization).count() == 0
    for observation in run.entity_observations.filter(entity_map__entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE):
        assert observation.target_model_label == "" and observation.target_pk == ""


@pytest.mark.django_db
def test_two_journals_sharing_one_offering_fold_into_one_enrollment(enrollment_actor, django_user_model):
    """V7 merge nəticəsi: eyni (student, offering) cütü EYNİ Enrollment-ə qatlanır."""

    actor = enrollment_actor
    organization = _organization(actor, "journal-enrollments-merge")
    rows = [
        _journal_row(2, "firstAAAAA", students_id='["42"]'),
        _journal_row(3, "secondBBBB", students_id='["42"]'),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(
        organization,
        actor,
        run.pk,
        django_user_model=django_user_model,
        uniqids=("firstAAAAA", "secondBBBB"),
        student_pks=(42,),
    )

    report = JournalEnrollmentsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"enrollment_materialised": 2}
    assert _enrollments(organization).count() == 1
    target_pks = set(
        run.entity_observations.filter(entity_map__entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE).values_list(
            "target_pk", flat=True
        )
    )
    assert len(target_pks) == 1


@pytest.mark.django_db
def test_a_repeated_invocation_replays_the_sealed_decisions(enrollment_actor, django_user_model):
    actor = enrollment_actor
    organization = _organization(actor, "journal-enrollments-replay")
    rows = [
        _journal_row(2, "rooBx39tsK", students_id='["42","999"]'),
        _journal_row(3, "brokenAAAA", students_id="not-json"),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model, student_pks=(42,))
    phase = JournalEnrollmentsPhase()

    first = phase.run(_seeded_context(organization, actor, run, rows=rows))
    second = phase.run(_seeded_context(organization, actor, run, rows=rows))

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert LegacyEntityMap.objects.filter(entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE).count() == 3
    assert _enrollments(organization).count() == 1


@pytest.mark.django_db
def test_the_live_phase_digest_equals_the_lexicographic_ledger_rebuild(enrollment_actor, django_user_model):
    """SA-2: qərarların axın sırası ledger-in leksikoqrafik rebuild-i ilə üst-üstə düşür."""

    actor = enrollment_actor
    organization = _organization(actor, "journal-enrollments-rebuild")
    rows = [
        _journal_row(2, "zzLastAAAA", students_id='["43","42"]'),
        _journal_row(3, "aaFirstBBB", students_id="not-json"),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model, uniqids=("zzLastAAAA",))
    phase = JournalEnrollmentsPhase()
    plan = _plan(len(rows))

    live = phase.run(_seeded_context(organization, actor, run, rows=rows))
    rebuilt = phase_report_from_ledger(run, phase=phase, plan=plan)

    assert rebuilt.phase_digest == live.phase_digest
    assert (
        dict(rebuilt.state_counts)
        == dict(live.state_counts)
        == {"enrollment_materialised": 2, "enrollment_unresolved": 1}
    )
    assert rebuilt.source_tables == live.source_tables == ()
    assert rebuilt.batches == live.batches == ()


@pytest.mark.django_db
def test_a_duplicate_uniqid_contradicts_the_attested_source_and_fails_closed(enrollment_actor, django_user_model):
    actor = enrollment_actor
    organization = _organization(actor, "journal-enrollments-duplicate")
    rows = [
        _journal_row(2, "rooBx39tsK"),
        _journal_row(3, "rooBx39tsK"),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model)

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalEnrollmentsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert exc_info.value.code == "legacy_rehearsal_journal_uniqid_duplicate"


@pytest.mark.django_db
def test_the_phase_digest_is_identical_across_two_independent_runs(enrollment_actor, django_user_model):
    """Cross-run determinizm: zəncirə heç bir UUID və target kimliyi girmir."""

    actor = enrollment_actor
    rows = [
        _journal_row(2, "rooBx39tsK", students_id='["42","999"]'),
        _journal_row(3, "brokenAAAA", students_id="not-json"),
        _journal_row(4, "fakeBBBBBB", fake=1, students_id='["42"]'),
    ]
    digests = []
    for slug in ("journal-enrollments-run-a", "journal-enrollments-run-b"):
        organization = _organization(actor, slug)
        run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
        _seed_references(organization, actor, run.pk, django_user_model=django_user_model, student_pks=(42,))
        digests.append(JournalEnrollmentsPhase().run(_seeded_context(organization, actor, run, rows=rows)).phase_digest)

    assert digests[0] == digests[1]


def test_a_staged_student_is_skipped_before_the_database_gate(enrollment_actor):
    """Rehearsal #7 reqressiyası: hesabı hələ aktivləşməmiş tələbə üçün
    ``Enrollment`` DB qapısından (``registrar_guard_active_member``) keçmir.

    Faza bunu ÖNCƏDƏN bilməlidir: sətir SKIPPED + ``legacy_journal_student_inactive``,
    jurnalın qalanı davam edir və run çökmür (əvvəl tutulmamış IntegrityError idi).
    """

    from apps.legacy_import.services.rehearsal_journal_enrollments_phase import active_member_ids

    organization = _organization(enrollment_actor, "enrollments-inactive")
    student = get_user_model().objects.create_user(username="myedu.student.inactive.1", email="", password=None)
    # Üzvlük var, amma HESAB aktiv deyil → indeksdə görünməməlidir.
    _activate_member(organization, student, "student")
    get_user_model().objects.filter(pk=student.pk).update(is_active=False)

    context = SimpleNamespace(organization=organization)
    assert str(student.pk) not in active_member_ids(context)

    # Hesab aktivləşəndə indeks onu buraxır.
    get_user_model().objects.filter(pk=student.pk).update(is_active=True)
    assert str(student.pk) in active_member_ids(context)
