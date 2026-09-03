"""Phase ``journal_periods`` (J0) testləri: J-V9(F), digest seam, karantin."""

import datetime
import hashlib
from dataclasses import replace

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyImportBatch, LegacyMigrationIssue, LegacyMigrationRun
from apps.legacy_import.services.field_contracts import SEMESTR_JURNAL_FIELDS, is_credential_field
from apps.legacy_import.services.ledger import create_run, start_run
from apps.legacy_import.services.rehearsal_authorizer import ACADEMIC_PERIOD_MODEL_LABEL, build_target_validators
from apps.legacy_import.services.rehearsal_contracts import (
    DEFAULT_BATCH_ROWS,
    SOURCE_SYSTEM,
    EmailTrustPolicy,
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    LegacyRehearsalInterrupted,
    RehearsalContext,
    RehearsalPolicy,
    StudentIdentifierPolicy,
    UsernamePolicy,
    encoded_part,
)
from apps.legacy_import.services.rehearsal_journal_periods_phase import (
    ACADEMIC_PERIOD_ENTITY_TYPE,
    DERIVED_DIGEST_NAMESPACE,
    ISSUE_SEVERITY,
    JOURNAL_PERIODS_PHASE_KEY,
    JournalPeriodsPhase,
    parse_period,
    period_derivation_hash,
)
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.services.source_extraction import LegacyDiscoveredTable
from apps.organizations.models import AcademicPeriod, Organization
from core.constants import AcademicPeriodType, OrganizationType

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
_SOURCE_COLUMNS = SEMESTR_JURNAL_FIELDS.allowed_fields


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


def _period_row(legacy_pk, **overrides):
    values = {
        "id": legacy_pk,
        "name": "2021/2022 Payız",
        "type": "autumn",
        "is_current": "0",
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
        entries=(replace(canonical.entry_for("semestr_jurnal"), expected_rows=rows),),
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


def test_the_phase_declares_a_batch_less_shape():
    phase = JournalPeriodsPhase()

    assert phase.phase_key == JOURNAL_PERIODS_PHASE_KEY and phase.order == 32
    assert phase.source_tables == () and phase.entity_types == (ACADEMIC_PERIOD_ENTITY_TYPE,)
    assert phase.declared_source_rows(_plan(13)) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "period_materialised"
    assert phase.derived_state_key("skipped") == "period_deferred"
    assert phase.derived_state_key("quarantined") == "period_unresolved"


def test_issue_severity_map_covers_exactly_the_period_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_journal_period_invalid": "warning",
        "legacy_journal_period_created": "info",
        "legacy_journal_period_matched_existing": "info",
        "legacy_journal_period_current_flag": "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)
    assert all(rule_code.startswith("legacy_journal_period_") for rule_code in ISSUE_SEVERITY)


def test_the_contract_is_credential_free():
    assert SEMESTR_JURNAL_FIELDS.allowed_fields == ("id", "name", "type", "is_current")
    assert not any(is_credential_field(field_name) for field_name in SEMESTR_JURNAL_FIELDS.allowed_fields)


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        JournalPeriodsPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


def test_the_dependency_gate_is_evidence_not_config():
    context = _context(plan=_plan(0), factory=_factory([]), policy=_policy(phase_keys=("journal_periods",)))

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalPeriodsPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


def test_a_cancellation_request_stops_the_phase_before_it_reads_anything():
    factory = _factory([_period_row(1)])
    context = _context(plan=_plan(1), factory=factory, cancelled=lambda: True)

    with pytest.raises(LegacyRehearsalInterrupted) as exc_info:
        JournalPeriodsPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_cancelled"
    assert factory.connections == []


@pytest.mark.parametrize(
    "overrides, expected",
    [
        (
            {"name": "2021/2022 Payız", "type": "autumn"},
            ("2021/2022", "Payız", datetime.date(2021, 9, 15), datetime.date(2022, 1, 31)),
        ),
        (
            {"name": "2022/2023 Yaz", "type": "spring"},
            ("2022/2023", "Yaz", datetime.date(2023, 2, 1), datetime.date(2023, 6, 30)),
        ),
        (
            {"name": "2022/2023 Yay", "type": "summer"},
            ("2022/2023", "Yay", datetime.date(2023, 7, 1), datetime.date(2023, 8, 31)),
        ),
        # format_year sərbəst mətni də ilk 4 rəqəmli ilə qatlayır.
        (
            {"name": "2024-2025 payız dönəmi", "type": "autumn"},
            ("2024/2025", "Payız", datetime.date(2024, 9, 15), datetime.date(2025, 1, 31)),
        ),
    ],
)
def test_parse_period_derives_the_target_shape(overrides, expected):
    plan = parse_period(_period_row(1, **overrides))

    assert plan is not None
    assert (plan.academic_year, plan.name, plan.start_date, plan.end_date) == expected


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "Payız (ilsiz)"},
        {"type": "winter"},
        {"type": None},
        {"name": None},
        {"name": "9999/10000 Payız", "type": "autumn"},  # il aralığı qapısı
    ],
)
def test_parse_period_fails_closed_on_an_unrecognised_row(overrides):
    assert parse_period(_period_row(1, **overrides)) is None


def test_the_period_derivation_hash_follows_the_documented_recipe():
    digest = hashlib.sha256(b"legacy-rehearsal-journal-period-derivation-v1\x00")
    for part in (
        SEMESTR_JURNAL_FIELDS.fingerprint,
        "1",
        "b" * 64,
        "materialised",
        "2021/2022",
        "Payız",
        "created",
        "0",
    ):
        digest.update(encoded_part(part))

    computed = period_derivation_hash(
        legacy_pk=1,
        row_hash="b" * 64,
        outcome_token="materialised",
        academic_year="2021/2022",
        period_name="Payız",
        target_state="created",
        is_current_text="0",
    )

    assert computed == digest.hexdigest()
    # created/existing qərar kimliyin hissəsidir.
    assert computed != period_derivation_hash(
        legacy_pk=1,
        row_hash="b" * 64,
        outcome_token="materialised",
        academic_year="2021/2022",
        period_name="Payız",
        target_state="existing",
        is_current_text="0",
    )


# ---------------------------------------------------------------------------
# Ledger-li mühit
# ---------------------------------------------------------------------------


@pytest.fixture()
def period_actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="journal_periods_actor",
        email="journal-periods-actor@example.test",
        password="test-only",
    )


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
        run.entity_observations.filter(entity_map__entity_type=ACADEMIC_PERIOD_ENTITY_TYPE).values_list(
            "entity_map__legacy_pk", "state"
        )
    )


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=ACADEMIC_PERIOD_ENTITY_TYPE)
    }


@pytest.mark.django_db
def test_the_happy_path_creates_periods_and_the_mapping_table(period_actor):
    actor = period_actor
    organization = _organization(actor, "journal-periods-primary")
    rows = [
        _period_row(1, name="2021/2022 Payız", type="autumn"),
        _period_row(2, name="2021/2022 Yaz", type="spring"),
        _period_row(3, name="2022/2023 Yay", type="summer", is_current="1"),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    notes = []

    report = JournalPeriodsPhase().run(_seeded_context(organization, actor, run, rows=rows, notes=notes))

    assert dict(report.state_counts) == {"period_materialised": 3}
    assert _states(run) == {"1": "migrated", "2": "migrated", "3": "migrated"}
    assert notes == [f"{JOURNAL_PERIODS_PHASE_KEY}.records.3"]
    # Derived faza heç bir batch zəncirinə sahib deyil.
    assert LegacyImportBatch.objects.filter(run=run).count() == 0
    periods = {
        (period.name, period.academic_year): period
        for period in AcademicPeriod.objects.filter(organization=organization)
    }
    assert set(periods) == {("Payız", "2021/2022"), ("Yaz", "2021/2022"), ("Yay", "2022/2023")}
    for period in periods.values():
        assert period.period_type == AcademicPeriodType.SEMESTER
        assert period.is_active is True
        # V9: cari-dövr qərarı istifadəçinindir — import HEÇ VAXT qoymur.
        assert period.is_current is False
    # J-V9(F): uyğunluq cədvəli sətir-başına İNFO kimi ledger-dədir.
    assert _issues(run) == {
        ("1", "legacy_journal_period_created"): "info",
        ("2", "legacy_journal_period_created"): "info",
        ("3", "legacy_journal_period_created"): "info",
        ("3", "legacy_journal_period_current_flag"): "info",
    }
    labels = set(
        run.entity_observations.filter(entity_map__entity_type=ACADEMIC_PERIOD_ENTITY_TYPE).values_list(
            "target_model_label", flat=True
        )
    )
    assert labels == {ACADEMIC_PERIOD_MODEL_LABEL}


@pytest.mark.django_db
def test_an_existing_tenant_period_is_matched_not_duplicated(period_actor):
    """J-V9(F): tenant-da artıq mövcud dövr → "mövcud idi" sütunu, dublikat yox."""

    actor = period_actor
    organization = _organization(actor, "journal-periods-existing")
    existing = AcademicPeriod.objects.create(
        organization=organization,
        name="Payız",
        academic_year="2021/2022",
        period_type=AcademicPeriodType.SEMESTER,
        start_date=datetime.date(2021, 9, 1),
        end_date=datetime.date(2022, 1, 15),
        is_current=True,
    )
    rows = [_period_row(1, name="2021/2022 Payız", type="autumn")]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))

    report = JournalPeriodsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"period_materialised": 1}
    assert _issues(run) == {("1", "legacy_journal_period_matched_existing"): "info"}
    assert AcademicPeriod.objects.filter(organization=organization).count() == 1
    existing.refresh_from_db()
    # Mövcud dövrün heç bir sahəsinə toxunulmur — tarixlər və cari bayraq qalır.
    assert existing.start_date == datetime.date(2021, 9, 1)
    assert existing.is_current is True
    observation = run.entity_observations.get(entity_map__entity_type=ACADEMIC_PERIOD_ENTITY_TYPE)
    assert observation.target_pk == str(existing.pk)


@pytest.mark.django_db
def test_an_unparseable_row_is_quarantined_without_a_target(period_actor):
    actor = period_actor
    organization = _organization(actor, "journal-periods-invalid")
    rows = [_period_row(1, name="Payız (ilsiz)"), _period_row(2, type="winter")]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))

    report = JournalPeriodsPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"period_unresolved": 2}
    assert _states(run) == {"1": "quarantined", "2": "quarantined"}
    assert _issues(run) == {
        ("1", "legacy_journal_period_invalid"): "warning",
        ("2", "legacy_journal_period_invalid"): "warning",
    }
    assert AcademicPeriod.objects.filter(organization=organization).count() == 0


@pytest.mark.django_db
def test_a_repeated_invocation_replays_the_sealed_decisions(period_actor):
    actor = period_actor
    organization = _organization(actor, "journal-periods-replay")
    rows = [
        _period_row(1, name="2021/2022 Payız", type="autumn"),
        _period_row(2, name="Payız (ilsiz)"),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    phase = JournalPeriodsPhase()

    first = phase.run(_seeded_context(organization, actor, run, rows=rows))
    second = phase.run(_seeded_context(organization, actor, run, rows=rows))

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert LegacyEntityMap.objects.filter(entity_type=ACADEMIC_PERIOD_ENTITY_TYPE).count() == 2
    assert AcademicPeriod.objects.filter(organization=organization).count() == 1


@pytest.mark.django_db
def test_the_live_phase_digest_equals_the_ledger_rebuild(period_actor):
    """SA-2: derived zəncir ledger-dən bayt-bəbayt yenidən qurulur."""

    actor = period_actor
    organization = _organization(actor, "journal-periods-rebuild")
    rows = [
        _period_row(1, name="2021/2022 Payız", type="autumn"),
        _period_row(2, name="2021/2022 Yaz", type="spring"),
        _period_row(3, name="Payız (ilsiz)"),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    phase = JournalPeriodsPhase()
    plan = _plan(len(rows))

    live = phase.run(_seeded_context(organization, actor, run, rows=rows))
    rebuilt = phase_report_from_ledger(run, phase=phase, plan=plan)

    assert rebuilt.phase_digest == live.phase_digest
    assert dict(rebuilt.state_counts) == dict(live.state_counts) == {"period_materialised": 2, "period_unresolved": 1}
    assert rebuilt.source_tables == live.source_tables == ()
    assert rebuilt.batches == live.batches == ()


@pytest.mark.django_db
def test_the_phase_digest_is_identical_across_two_independent_runs(period_actor):
    """Cross-run determinizm: zəncirə heç bir UUID və target kimliyi girmir."""

    actor = period_actor
    rows = [
        _period_row(1, name="2021/2022 Payız", type="autumn", is_current="1"),
        _period_row(2, name="Payız (ilsiz)"),
    ]
    digests = []
    for slug in ("journal-periods-run-a", "journal-periods-run-b"):
        organization = _organization(actor, slug)
        run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
        digests.append(JournalPeriodsPhase().run(_seeded_context(organization, actor, run, rows=rows)).phase_digest)

    assert digests[0] == digests[1]
