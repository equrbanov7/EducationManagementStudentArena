"""Phase ``journal_offerings`` (J1) testləri: V5/V6/V7, merge, uniqid zənciri."""

import datetime
import hashlib
from dataclasses import replace

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyImportBatch, LegacyMigrationIssue, LegacyMigrationRun
from apps.legacy_import.services.field_contracts import JOURNAL_FIELDS, is_credential_field
from apps.legacy_import.services.ledger import TargetValidation, create_run, start_run, upsert_entity_map
from apps.legacy_import.services.rehearsal_authorizer import (
    ACADEMIC_PERIOD_MODEL_LABEL,
    COURSE_OFFERING_MODEL_LABEL,
    ORG_UNIT_MODEL_LABEL,
    SUBJECT_MODEL_LABEL,
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
from apps.legacy_import.services.rehearsal_journal_offerings_phase import (
    DERIVED_DIGEST_NAMESPACE,
    JOURNAL_OFFERINGS_PHASE_KEY,
    JournalOfferingsPhase,
)
from apps.legacy_import.services.rehearsal_journal_offerings_source import parse_group_ids
from apps.legacy_import.services.rehearsal_journal_offerings_targets import (
    COURSE_OFFERING_ENTITY_TYPE,
    ISSUE_SEVERITY,
    offering_derivation_hash,
)
from apps.legacy_import.services.rehearsal_journal_periods_phase import ACADEMIC_PERIOD_ENTITY_TYPE
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.services.source_extraction import LegacyDiscoveredTable
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType

_SUBJECT_ENTITY_TYPE = "lesson_subject"
_GROUP_ENTITY_TYPE = "group_unit"
_WORKER_ENTITY_TYPE = "worker"
_PHASE_KEYS = (
    "academic_structure",
    "academic_catalog",
    "identity_cohort",
    "student_placement",
    "worker_materialisation",
    "sar_materialisation",
    "journal_periods",
    "journal_offerings",
)
_SOURCE_COLUMNS = JOURNAL_FIELDS.allowed_fields


# ---------------------------------------------------------------------------
# Fake source (identity/worker fixture-ləri ilə eyni forma)
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
    phase = JournalOfferingsPhase()

    assert phase.phase_key == JOURNAL_OFFERINGS_PHASE_KEY and phase.order == 34
    assert phase.source_tables == () and phase.entity_types == (COURSE_OFFERING_ENTITY_TYPE,)
    assert phase.declared_source_rows(_plan(3)) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    # ``uniqid`` rəqəm deyil: rebuild sıralaması leksikoqrafikdir.
    assert phase.derived_ledger_sort_key("rooBx39tsK") == "rooBx39tsK"
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "offering_materialised"
    assert phase.derived_state_key("skipped") == "offering_discarded"
    assert phase.derived_state_key("quarantined") == "offering_unresolved"


def test_issue_severity_map_covers_exactly_the_offering_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_journal_groups_invalid": "warning",
        "legacy_journal_group_unresolved": "warning",
        "legacy_journal_subject_unresolved": "warning",
        "legacy_journal_period_unresolved": "warning",
        "legacy_journal_discarded_source": "info",
        "legacy_journal_multi_group": "info",
        "legacy_journal_instructor_unresolved": "info",
        "legacy_journal_offering_merged": "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)
    assert all(rule_code.startswith("legacy_journal_") for rule_code in ISSUE_SEVERITY)


def test_the_journal_contract_is_credential_free_and_carries_j2_fields():
    # ``students_id`` J2 üçün İNDİDƏN kontraktdadır: sonradan genişlətmə barmaq
    # izini və bütün yazılmış source_row_hash-ləri dəyişərdi.
    assert JOURNAL_FIELDS.allowed_fields == (
        "id",
        "uniqid",
        "lesson_id",
        "semestr",
        "groups_id",
        "students_id",
        "teacher_id",
        "fake",
        "sonra_sil",
        "active",
    )
    assert not any(is_credential_field(field_name) for field_name in JOURNAL_FIELDS.allowed_fields)


@pytest.mark.parametrize(
    "value, expected",
    [
        ('["2"]', (2,)),
        ('["2","7"]', (2, 7)),
        ("[2, 7]", (2, 7)),
        ('["2","2","7"]', (2, 7)),  # dublikat sıra qorunaraq tək nüsxəyə enir
        ("[]", None),
        ("", None),
        (None, None),
        ("not-json", None),
        ('{"a": 1}', None),
        ('["x"]', None),
        ('["0"]', None),
        ("[true]", None),
    ],
)
def test_parse_group_ids_is_strict(value, expected):
    assert parse_group_ids(value) == expected


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        JournalOfferingsPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


@pytest.mark.parametrize(
    "phase_keys",
    [
        ("journal_offerings",),
        ("journal_periods", "journal_offerings"),
        ("academic_structure", "academic_catalog", "identity_cohort", "journal_offerings"),
    ],
)
def test_the_dependency_gate_is_evidence_not_config(phase_keys):
    context = _context(plan=_plan(0), factory=_factory([]), policy=_policy(phase_keys=phase_keys))

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalOfferingsPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


def test_the_offering_derivation_hash_follows_the_documented_recipe():
    digest = hashlib.sha256(b"legacy-rehearsal-journal-offering-derivation-v1\x00")
    for part in (
        JOURNAL_FIELDS.fingerprint,
        "rooBx39tsK",
        "b" * 64,
        "materialised",
        "64",
        "1",
        "2",
        "resolved",
        "resolved:17",
        "0",
    ):
        digest.update(encoded_part(part))

    computed = offering_derivation_hash(
        uniqid="rooBx39tsK",
        row_hash="b" * 64,
        outcome_token="materialised",
        subject_ref="64",
        period_ref="1",
        groups_token="2",
        group_state="resolved",
        instructor_state="resolved:17",
        merged_text="0",
    )

    assert computed == digest.hexdigest()
    # V5: legacy teacher_id qərar kimliyində saxlanılır.
    assert computed != offering_derivation_hash(
        uniqid="rooBx39tsK",
        row_hash="b" * 64,
        outcome_token="materialised",
        subject_ref="64",
        period_ref="1",
        groups_token="2",
        group_state="resolved",
        instructor_state="unresolved:99",
        merged_text="0",
    )


# ---------------------------------------------------------------------------
# Ledger-li mühit
# ---------------------------------------------------------------------------


@pytest.fixture()
def offering_actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="journal_offerings_actor",
        email="journal-offerings-actor@example.test",
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


def _seed_references(organization, actor, run_id, *, django_user_model, group_pks=(2,)):
    """Əvvəlki fazaların (catalog/J0/structure/identity) qoyub getdiyi map-lar."""

    from django.apps import apps as django_apps

    subject = django_apps.get_model("registrar", "Subject").objects.create(
        organization=organization, code="MYEDU-64", name="Proqramlaşdırmanın əsasları", ects=5
    )
    _map(run_id, actor, entity_type=_SUBJECT_ENTITY_TYPE, legacy_pk=64, label=SUBJECT_MODEL_LABEL, target_pk=subject.pk)
    period = AcademicPeriod.objects.create(
        organization=organization,
        name="Payız",
        academic_year="2021/2022",
        period_type=AcademicPeriodType.SEMESTER,
        start_date=datetime.date(2021, 9, 15),
        end_date=datetime.date(2022, 1, 31),
    )
    _map(
        run_id,
        actor,
        entity_type=ACADEMIC_PERIOD_ENTITY_TYPE,
        legacy_pk=1,
        label=ACADEMIC_PERIOD_MODEL_LABEL,
        target_pk=period.pk,
    )
    groups = {}
    for legacy_pk in group_pks:
        group = OrgUnit.objects.create(
            organization=organization,
            slug=f"myedu-grp-{legacy_pk}",
            unit_type=OrgUnitType.GROUP,
            name=f"Qrup {legacy_pk}",
        )
        _map(
            run_id,
            actor,
            entity_type=_GROUP_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            label=ORG_UNIT_MODEL_LABEL,
            target_pk=group.pk,
        )
        groups[legacy_pk] = group
    instructor = django_user_model.objects.create_user(
        username=f"myedu.worker.{organization.slug}.17", email="", password=None
    )
    # PG-də ``registrar_guard_active_member`` offering.instructor üçün AKTİV
    # üzvlük tələb edir; real axında bunu ``worker_materialisation`` (order 26)
    # bu fazadan (34) ƏVVƏL verir, ona görə fixture həmin vəziyyəti qurur.
    _activate_member(organization, instructor, "teacher")
    # İşçi map-ı icazəli stub validatorla möhürlənir: identity fazası bu run-da
    # işləməyib, amma map onun buraxdığı formadadır (worker → auth.user).
    _map(
        run_id,
        actor,
        entity_type=_WORKER_ENTITY_TYPE,
        legacy_pk=17,
        label=USER_MODEL_LABEL,
        target_pk=instructor.pk,
        validators={USER_MODEL_LABEL: lambda **_kwargs: TargetValidation(True, True)},
    )
    return subject, period, groups, instructor


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
        run.entity_observations.filter(entity_map__entity_type=COURSE_OFFERING_ENTITY_TYPE).values_list(
            "entity_map__legacy_pk", "state"
        )
    )


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=COURSE_OFFERING_ENTITY_TYPE)
    }


def _offerings(organization):
    from django.apps import apps as django_apps

    return django_apps.get_model("registrar", "CourseOffering").objects.filter(organization=organization)


def _schemes(organization):
    from django.apps import apps as django_apps

    return django_apps.get_model("registrar", "AssessmentScheme").objects.filter(organization=organization)


@pytest.mark.django_db
def test_the_happy_path_creates_the_offering_and_a_draft_scheme(offering_actor, django_user_model):
    actor = offering_actor
    organization = _organization(actor, "journal-offerings-primary")
    rows = [_journal_row(2, "rooBx39tsK")]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    subject, period, groups, instructor = _seed_references(
        organization, actor, run.pk, django_user_model=django_user_model
    )
    notes = []

    report = JournalOfferingsPhase().run(_seeded_context(organization, actor, run, rows=rows, notes=notes))

    assert dict(report.state_counts) == {"offering_materialised": 1}
    assert _states(run) == {"rooBx39tsK": "migrated"}
    assert _issues(run) == {}
    assert notes == [f"{JOURNAL_OFFERINGS_PHASE_KEY}.records.1"]
    assert LegacyImportBatch.objects.filter(run=run).count() == 0
    offering = _offerings(organization).get()
    assert offering.subject_id == subject.pk
    assert offering.period_id == period.pk
    assert offering.group_id == groups[2].pk
    assert offering.instructor_id == instructor.pk
    # E-qaydası: sxem yaranıb, amma DRAFT/kilidsizdir — kilid J7-nin işidir.
    scheme = _schemes(organization).get()
    assert scheme.offering_id == offering.pk
    assert scheme.approval_status == "draft"
    assert scheme.is_published is False
    observation = run.entity_observations.get(entity_map__entity_type=COURSE_OFFERING_ENTITY_TYPE)
    assert observation.target_model_label == COURSE_OFFERING_MODEL_LABEL
    assert observation.target_pk == str(offering.pk)


@pytest.mark.django_db
def test_v6_fake_and_sonra_sil_journals_are_skipped_with_their_uniqid_kept(offering_actor, django_user_model):
    """J-V6: süzgəc SKIPPED-dir — uniqid ledger-də qalır, mənbədə heç nə silinmir."""

    actor = offering_actor
    organization = _organization(actor, "journal-offerings-discarded")
    rows = [
        _journal_row(2, "fakeAAAAAA", fake=1),
        _journal_row(3, "silBBBBBBB", sonra_sil=1),
        _journal_row(4, "bothCCCCCC", fake=1, sonra_sil=1),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model)

    report = JournalOfferingsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"offering_discarded": 3}
    assert _states(run) == {"fakeAAAAAA": "skipped", "silBBBBBBB": "skipped", "bothCCCCCC": "skipped"}
    assert _issues(run) == {
        ("fakeAAAAAA", "legacy_journal_discarded_source"): "info",
        ("silBBBBBBB", "legacy_journal_discarded_source"): "info",
        ("bothCCCCCC", "legacy_journal_discarded_source"): "info",
    }
    assert _offerings(organization).count() == 0


@pytest.mark.django_db
def test_v5_an_unresolved_teacher_leaves_the_instructor_null(offering_actor, django_user_model):
    actor = offering_actor
    organization = _organization(actor, "journal-offerings-orphan-teacher")
    rows = [_journal_row(2, "rooBx39tsK", teacher_id=999)]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model)

    report = JournalOfferingsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"offering_materialised": 1}
    assert _issues(run) == {("rooBx39tsK", "legacy_journal_instructor_unresolved"): "info"}
    offering = _offerings(organization).get()
    assert offering.instructor_id is None


@pytest.mark.django_db
def test_v7_a_multi_group_journal_becomes_one_group_null_offering(offering_actor, django_user_model):
    actor = offering_actor
    organization = _organization(actor, "journal-offerings-multi-group")
    rows = [_journal_row(2, "rooBx39tsK", groups_id='["2","7"]')]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model, group_pks=(2, 7))

    report = JournalOfferingsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"offering_materialised": 1}
    assert _issues(run) == {("rooBx39tsK", "legacy_journal_multi_group"): "info"}
    offering = _offerings(organization).get()
    assert offering.group_id is None


@pytest.mark.django_db
def test_v7_a_broken_groups_array_quarantines_the_whole_journal(offering_actor, django_user_model):
    actor = offering_actor
    organization = _organization(actor, "journal-offerings-broken-groups")
    rows = [
        _journal_row(2, "brokenAAAA", groups_id="not-json"),
        _journal_row(3, "emptyBBBBB", groups_id="[]"),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model)

    report = JournalOfferingsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"offering_unresolved": 2}
    assert _states(run) == {"brokenAAAA": "quarantined", "emptyBBBBB": "quarantined"}
    assert _issues(run) == {
        ("brokenAAAA", "legacy_journal_groups_invalid"): "warning",
        ("emptyBBBBB", "legacy_journal_groups_invalid"): "warning",
    }
    assert _offerings(organization).count() == 0


@pytest.mark.django_db
def test_unresolved_references_quarantine_with_their_precise_codes(offering_actor, django_user_model):
    actor = offering_actor
    organization = _organization(actor, "journal-offerings-orphans")
    rows = [
        _journal_row(2, "noSubjAAAA", lesson_id=999),
        _journal_row(3, "noPerBBBBB", semestr=99),
        _journal_row(4, "noGrpCCCCC", groups_id='["55"]'),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model)

    report = JournalOfferingsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"offering_unresolved": 3}
    assert _issues(run) == {
        ("noSubjAAAA", "legacy_journal_subject_unresolved"): "warning",
        ("noPerBBBBB", "legacy_journal_period_unresolved"): "warning",
        ("noGrpCCCCC", "legacy_journal_group_unresolved"): "warning",
    }
    assert _offerings(organization).count() == 0
    # Karantin müşahidəsi heç bir hədəf daşımır.
    for observation in run.entity_observations.filter(entity_map__entity_type=COURSE_OFFERING_ENTITY_TYPE):
        assert observation.target_model_label == "" and observation.target_pk == ""


@pytest.mark.django_db
def test_two_journals_on_one_key_merge_into_a_single_offering(offering_actor, django_user_model):
    """V7 qoruması: map əsas qoruyucudur — eyni açar EYNİ offering-ə qatlanır."""

    actor = offering_actor
    organization = _organization(actor, "journal-offerings-merge")
    rows = [
        _journal_row(2, "firstAAAAA"),
        _journal_row(3, "secondBBBB"),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model)

    report = JournalOfferingsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"offering_materialised": 2}
    assert _issues(run) == {("secondBBBB", "legacy_journal_offering_merged"): "info"}
    assert _offerings(organization).count() == 1
    assert _schemes(organization).count() == 1
    # Hər iki uniqid EYNİ hədəfi göstərir.
    target_pks = set(
        run.entity_observations.filter(entity_map__entity_type=COURSE_OFFERING_ENTITY_TYPE).values_list(
            "target_pk", flat=True
        )
    )
    assert len(target_pks) == 1


@pytest.mark.django_db
def test_a_repeated_invocation_replays_the_sealed_decisions(offering_actor, django_user_model):
    actor = offering_actor
    organization = _organization(actor, "journal-offerings-replay")
    rows = [
        _journal_row(2, "rooBx39tsK"),
        _journal_row(3, "fakeAAAAAA", fake=1),
        _journal_row(4, "brokenBBBB", groups_id="not-json"),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model)
    phase = JournalOfferingsPhase()

    first = phase.run(_seeded_context(organization, actor, run, rows=rows))
    second = phase.run(_seeded_context(organization, actor, run, rows=rows))

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert LegacyEntityMap.objects.filter(entity_type=COURSE_OFFERING_ENTITY_TYPE).count() == 3
    assert _offerings(organization).count() == 1
    assert _schemes(organization).count() == 1


@pytest.mark.django_db
def test_the_live_phase_digest_equals_the_lexicographic_ledger_rebuild(offering_actor, django_user_model):
    """SA-2: uniqid-lər QƏSDƏN id sırasının əksinədir — zəncir yenə üst-üstə düşür."""

    actor = offering_actor
    organization = _organization(actor, "journal-offerings-rebuild")
    rows = [
        _journal_row(2, "zzLastAAAA"),
        _journal_row(3, "aaFirstBBB", fake=1),
        _journal_row(4, "mmMidCCCCC", groups_id="not-json"),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model)
    phase = JournalOfferingsPhase()
    plan = _plan(len(rows))

    live = phase.run(_seeded_context(organization, actor, run, rows=rows))
    rebuilt = phase_report_from_ledger(run, phase=phase, plan=plan)

    assert rebuilt.phase_digest == live.phase_digest
    assert (
        dict(rebuilt.state_counts)
        == dict(live.state_counts)
        == {"offering_materialised": 1, "offering_discarded": 1, "offering_unresolved": 1}
    )
    assert rebuilt.source_tables == live.source_tables == ()
    assert rebuilt.batches == live.batches == ()


@pytest.mark.django_db
def test_a_duplicate_uniqid_contradicts_the_attested_source_and_fails_closed(offering_actor, django_user_model):
    actor = offering_actor
    organization = _organization(actor, "journal-offerings-duplicate")
    rows = [
        _journal_row(2, "rooBx39tsK"),
        _journal_row(3, "rooBx39tsK"),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_references(organization, actor, run.pk, django_user_model=django_user_model)

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalOfferingsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert exc_info.value.code == "legacy_rehearsal_journal_uniqid_duplicate"


@pytest.mark.django_db
def test_the_phase_digest_is_identical_across_two_independent_runs(offering_actor, django_user_model):
    """Cross-run determinizm: zəncirə heç bir UUID və target kimliyi girmir."""

    actor = offering_actor
    rows = [
        _journal_row(2, "rooBx39tsK"),
        _journal_row(3, "fakeAAAAAA", fake=1),
        _journal_row(4, "orphanBBBB", teacher_id=999),
    ]
    digests = []
    for slug in ("journal-offerings-run-a", "journal-offerings-run-b"):
        organization = _organization(actor, slug)
        run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
        _seed_references(organization, actor, run.pk, django_user_model=django_user_model)
        digests.append(JournalOfferingsPhase().run(_seeded_context(organization, actor, run, rows=rows)).phase_digest)

    assert digests[0] == digests[1]
