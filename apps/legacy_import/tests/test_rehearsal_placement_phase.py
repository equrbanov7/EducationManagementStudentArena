"""Phase ``student_placement`` tests: dependency gate, §4.5 matrix, digest seam."""

import datetime
import hashlib
from dataclasses import replace

import pytest

from apps.accounts.models import UserProfile
from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityObservation,
    LegacyImportBatch,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.services.field_contracts import STUDENT_IDENTITY_FIELDS
from apps.legacy_import.services.ledger import create_run, start_run, upsert_entity_map
from apps.legacy_import.services.rehearsal_authorizer import (
    ORG_UNIT_MODEL_LABEL,
    USER_MODEL_LABEL,
    build_target_validators,
)
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
    source_row_hash,
)
from apps.legacy_import.services.rehearsal_placement_phase import (
    DERIVED_DIGEST_NAMESPACE,
    ISSUE_SEVERITY,
    PLACEMENT_ENTITY_TYPE,
    GroupPlacement,
    StudentPlacementPhase,
    record_derivation_hash,
    resolve_placement,
)
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.services.rehearsal_structure_phase import GROUP_ENTITY_TYPE
from apps.legacy_import.services.source_extraction import LegacyDiscoveredTable
from apps.legacy_import.services.table_plan import TABLE_PLAN_VERSION, LegacyTablePlan, load_legacy_table_plan
from apps.organizations.models import Organization, OrgUnit
from apps.registrar.models import Program
from core.constants import OrganizationType, OrgUnitType

_SNAPSHOT_SHA256 = load_legacy_table_plan().source_snapshot_sha256
_STUDENT_ENTITY_TYPE = "student"
_PHASE_KEYS = ("academic_structure", "identity_cohort", "student_placement")
# Decoy authentication columns that must never leave the source.
_CREDENTIAL_COLUMNS = ("password", "show_password", "pin_for_lock")


# ---------------------------------------------------------------------------
# Fake source (same shape as the identity/structure fixtures)
# ---------------------------------------------------------------------------


class _FakeCursor:
    """Positional DB-API cursor over already-projected source values."""

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
    """Read-only source that only ever returns contract-projected columns."""

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
            column_names=(*STUDENT_IDENTITY_FIELDS.allowed_fields, *_CREDENTIAL_COLUMNS),
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


def _student_row(legacy_pk, **overrides):
    values = {field_name: None for field_name in STUDENT_IDENTITY_FIELDS.allowed_fields}
    values["id"] = legacy_pk
    values["password"] = "hunter2-raw-credential"
    values.update(overrides)
    return values


def _plan(students):
    canonical = load_legacy_table_plan()
    return LegacyTablePlan(
        version=canonical.version,
        fingerprint=canonical.fingerprint,
        source_snapshot_sha256=canonical.source_snapshot_sha256,
        expected_row_count=students,
        entries=(replace(canonical.entry_for("students"), expected_rows=students),),
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


def _context(*, plan, factory, policy=None, run_id=None, organization=None, actor=None, cancelled=False, notes=None):
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
        cancellation_requested=lambda: cancelled,
        stdout_note=(notes if notes is not None else []).append,
    )


# ---------------------------------------------------------------------------
# Pure resolution (no database)
# ---------------------------------------------------------------------------


def _group(**overrides):
    values = {
        "slug": "myedu-grp-20",
        "specialty_unit_id": "spec-10",
        "education_form": "full_time",
        "sector": "az",
        "degree_level": "bachelor",
        "admission_year": 2019,
    }
    values.update(overrides)
    return GroupPlacement(**values)


_GROUPS = {"20": _group()}
_PROGRAMS = {("spec-10", "bachelor"): "050620"}


@pytest.mark.parametrize(
    ("entry_year", "expected_year", "expected_source"),
    [
        ("2019", "2019", "student"),
        (" 2019 ", "2019", "student"),  # clean_code kills the padding
        ("2019\t", "2019", "student"),
        ("19", "2019", "group"),  # not ^\d{4}$ ⇒ the group backstop answers
        ("1800", "2019", "group"),  # a real four-digit year outside 1950..2100
        ("", "2019", "group"),
        (None, "2019", "group"),
    ],
)
def test_entry_year_matrix_then_group_backstop(entry_year, expected_year, expected_source):
    placement = resolve_placement(
        _student_row(1, group_id=20, entry_year=entry_year), groups=_GROUPS, programs=_PROGRAMS
    )

    assert (placement.admission_year_text, placement.admission_year_source) == (expected_year, expected_source)
    assert placement.state == LegacyEntityMap.State.SKIPPED
    assert "legacy_record_admission_year_missing" not in placement.rule_codes


def test_admission_year_missing_from_both_sources_is_info_and_still_deferred():
    """V-2: 2,427 live students land here — it must stay normal information flow."""

    groups = {"20": _group(admission_year=None)}

    placement = resolve_placement(_student_row(1, group_id=20, entry_year=""), groups=groups, programs=_PROGRAMS)

    assert placement.admission_year_text == "" and placement.admission_year_source == "none"
    assert placement.rule_codes == ("legacy_record_admission_year_missing",)
    assert placement.state == LegacyEntityMap.State.SKIPPED and placement.outcome_token == "deferred"
    assert ISSUE_SEVERITY["legacy_record_admission_year_missing"] == LegacyMigrationIssue.Severity.INFO


@pytest.mark.parametrize("group_id", [0, None, 999])
def test_a_dangling_group_id_is_unresolved(group_id):
    placement = resolve_placement(
        _student_row(1, group_id=group_id, entry_year="2019"), groups=_GROUPS, programs=_PROGRAMS
    )

    assert placement.state == LegacyEntityMap.State.QUARANTINED and placement.outcome_token == "unresolved"
    assert placement.rule_codes == ("legacy_record_group_unresolved",)
    # Every group-derived part of the derivation collapses to "".
    assert (placement.group_slug, placement.degree_level, placement.education_form, placement.sector) == (
        "",
        "",
        "",
        "",
    )
    assert placement.program_code == ""
    # entry_year alone still answers the admission year.
    assert (placement.admission_year_text, placement.admission_year_source) == ("2019", "student")


def test_a_group_without_a_matching_degree_program_is_unresolved():
    groups = {"20": _group(degree_level="phd")}

    placement = resolve_placement(_student_row(1, group_id=20), groups=groups, programs=_PROGRAMS)

    assert placement.state == LegacyEntityMap.State.QUARANTINED
    assert placement.rule_codes == ("legacy_record_program_unresolved",)
    # The group IS known, so its attributes stay in the derivation…
    assert placement.group_slug == "myedu-grp-20" and placement.degree_level == "phd"
    # …only the program code is empty.
    assert placement.program_code == ""


def test_a_non_integer_group_id_fails_closed():
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        resolve_placement(_student_row(1, group_id="20"), groups=_GROUPS, programs=_PROGRAMS)

    assert exc_info.value.code == "legacy_rehearsal_source_value_type_unsupported"


def test_issue_severity_map_covers_exactly_the_placement_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_record_group_unresolved": "warning",
        "legacy_record_program_unresolved": "warning",
        "legacy_record_admission_year_missing": "info",
        "legacy_fin_invalid_format": "warning",
        "legacy_fin_duplicate_source": "warning",
        "legacy_fin_collision": "warning",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)


def test_the_phase_declares_a_batch_less_shape():
    phase = StudentPlacementPhase()

    assert phase.phase_key == "student_placement" and phase.order == 25
    assert phase.source_tables == () and phase.entity_types == (PLACEMENT_ENTITY_TYPE,)
    assert phase.declared_source_rows(_plan(3)) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_state_key(LegacyEntityMap.State.SKIPPED) == "record_deferred"
    assert phase.derived_state_key("quarantined") == "record_unresolved"


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        StudentPlacementPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


@pytest.mark.parametrize("phase_keys", [("student_placement",), ("identity_cohort", "student_placement")])
def test_the_dependency_gate_is_evidence_not_config(phase_keys):
    context = _context(plan=_plan(0), factory=_factory([]), policy=_policy(phase_keys=phase_keys))

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        StudentPlacementPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


def test_a_cancellation_request_stops_the_phase_before_it_reads_anything():
    factory = _factory([_student_row(1)])
    context = _context(plan=_plan(1), factory=factory, cancelled=True)

    with pytest.raises(LegacyRehearsalInterrupted) as exc_info:
        StudentPlacementPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_cancelled"
    assert factory.connections == []


# ---------------------------------------------------------------------------
# Ledger-backed behaviour
# ---------------------------------------------------------------------------


@pytest.fixture()
def placement_environment(db, django_user_model):
    actor = django_user_model.objects.create_superuser(
        username="placement_phase_actor",
        email="placement-phase-actor@example.test",
        password="test-only",
    )
    return actor


def _organization(actor, slug):
    return Organization.objects.create(
        name=f"Placement {slug}",
        slug=slug,
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )


def _running_run(organization, actor, *, policy, plan):
    run = create_run(
        actor=actor,
        authorize=_allow,
        organization=organization,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=_SNAPSHOT_SHA256,
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


def _map(run_id, actor, *, entity_type, legacy_pk, label, target_pk):
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
        target_validators=build_target_validators(),
    )


# (legacy_pk, degree_level, education_form, sector, admission_year)
_SEEDED_GROUPS = (
    (20, "bachelor", "full_time", "az", 2019),
    (21, "master", "part_time", "en", None),
    (22, "phd", "full_time", "az", 2021),  # no program of that degree ⇒ unresolved
)


def _seed_structure(organization, actor, run_id):
    """Everything the ``academic_structure`` phase would have left behind."""

    speciality = OrgUnit.objects.create(
        organization=organization,
        slug="myedu-spec-10",
        unit_type=OrgUnitType.SPECIALTY,
        name="İxtisas A",
        code="050620",
        settings={"legacy": {"table": "speciality", "id": 10}},
    )
    for code, degree, ects in (("050620", "bachelor", 240), ("050620-M", "master", 120)):
        Program.objects.create(
            organization=organization,
            specialty_unit=speciality,
            code=code,
            name="İxtisas A",
            degree_level=degree,
            ects_total=ects,
        )
    for legacy_pk, degree, form, sector, year in _SEEDED_GROUPS:
        unit = OrgUnit.objects.create(
            organization=organization,
            slug=f"myedu-grp-{legacy_pk}",
            unit_type=OrgUnitType.GROUP,
            name=f"Qrup {legacy_pk}",
            parent=speciality,
            settings={
                "education_form": form,
                "admission_year": year,
                "sector": sector,
                "degree_level": degree,
                "legacy": {"table": "groups", "id": legacy_pk},
            },
        )
        _map(
            run_id,
            actor,
            entity_type=GROUP_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            label=ORG_UNIT_MODEL_LABEL,
            target_pk=unit.pk,
        )
    return speciality


def _stage_students(organization, actor, run_id, users, legacy_pks, *, names=(), fins=()):
    staged = {}
    preset_names = dict(names)
    preset_fins = dict(fins)
    for legacy_pk in legacy_pks:
        user = users.objects.create(
            username=f"myedu.student.{organization.slug}.{legacy_pk}",
            email=f"student{legacy_pk}@{organization.slug}.test",
            is_active=False,
            **dict(zip(("first_name", "last_name"), preset_names.get(legacy_pk, ("", "")))),
        )
        UserProfile.objects.filter(user=user).update(
            organization=organization,
            access_state=UserProfile.AccessState.STAGED,
            fin=preset_fins.get(legacy_pk),
        )
        _map(
            run_id,
            actor,
            entity_type=_STUDENT_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            label=USER_MODEL_LABEL,
            target_pk=user.pk,
        )
        staged[legacy_pk] = user
    return staged


def _cohort_rows():
    return [
        _student_row(1, group_id=20, entry_year="2019", first_name="Elvin", last_name="Qurbanov", fincode="ab12345"),
        _student_row(2, group_id=21, entry_year="", first_name="Aysel", last_name="Məmmədova", fincode=""),
        _student_row(3, group_id=999, entry_year="2020", fincode="TOOSHORT"),
        _student_row(4, group_id=22, entry_year="2021", fincode="6CHARS"),
        _student_row(5, group_id=20, entry_year="2019", fincode="DUP1234"),
        _student_row(6, group_id=20, entry_year="2019", fincode=" dup1234 "),
        _student_row(7, group_id=20, entry_year="2019"),  # never staged
    ]


def _seeded_context(organization, actor, run, *, rows=None, notes=None, policy=None):
    source_rows = _cohort_rows() if rows is None else rows
    context = _context(
        plan=_plan(len(source_rows)),
        factory=_factory(source_rows),
        policy=policy or _policy(),
        organization=organization,
        actor=actor,
        notes=notes,
    )
    return replace(context, run_id=run.pk)


@pytest.fixture()
def seeded(placement_environment, django_user_model):
    actor = placement_environment
    organization = _organization(actor, "placement-primary")
    policy = _policy()
    plan = _plan(len(_cohort_rows()))
    run = _running_run(organization, actor, policy=policy, plan=plan)
    _seed_structure(organization, actor, run.pk)
    users = _stage_students(
        organization,
        actor,
        run.pk,
        django_user_model,
        (1, 2, 3, 4, 5, 6),
        names={2: ("Köhnə", "Ad")},
    )
    return organization, actor, run, users


@pytest.mark.django_db
def test_phase_run_records_every_staged_placement(seeded):
    organization, actor, run, _users = seeded
    notes = []

    report = StudentPlacementPhase().run(_seeded_context(organization, actor, run, notes=notes))

    assert report.phase_key == "student_placement" and report.order == 25
    assert report.source_tables == () and report.batches == ()
    assert report.declared_source_rows == 0 and report.observed_source_rows == 0
    assert report.staged_account_count == 0
    # Student 7 is not staged by this run, so it is not counted anywhere.
    assert dict(report.state_counts) == {"record_deferred": 4, "record_unresolved": 2}
    assert "record_created" not in report.state_counts
    assert notes == ["student_placement.records.6"]
    # A derived phase owns no batch chain at all.
    assert LegacyImportBatch.objects.filter(run=run).count() == 0
    placements = dict(
        LegacyEntityObservation.objects.filter(run=run, entity_map__entity_type=PLACEMENT_ENTITY_TYPE).values_list(
            "entity_map__legacy_pk", "state"
        )
    )
    assert placements == {
        "1": "skipped",
        "2": "skipped",
        "3": "quarantined",  # dangling group_id
        "4": "quarantined",  # phd group has no program
        "5": "skipped",
        "6": "skipped",
    }
    assert all(
        observation.target_model_label == "" and observation.target_pk == ""
        for observation in LegacyEntityObservation.objects.filter(
            run=run, entity_map__entity_type=PLACEMENT_ENTITY_TYPE
        )
    )


@pytest.mark.django_db
def test_an_unstaged_student_produces_no_map_no_issue_no_counter(seeded):
    organization, actor, run, _users = seeded

    StudentPlacementPhase().run(_seeded_context(organization, actor, run))

    assert not LegacyEntityMap.objects.filter(entity_type=PLACEMENT_ENTITY_TYPE, legacy_pk="7").exists()
    assert not LegacyMigrationIssue.objects.filter(run=run, legacy_pk="7").exists()


@pytest.mark.django_db
def test_issue_rows_follow_the_placement_taxonomy(seeded):
    organization, actor, run, _users = seeded

    StudentPlacementPhase().run(_seeded_context(organization, actor, run))

    issues = {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=PLACEMENT_ENTITY_TYPE)
    }
    assert issues == {
        ("2", "legacy_record_admission_year_missing"): "info",  # master group has no start_year
        ("3", "legacy_record_group_unresolved"): "warning",
        ("3", "legacy_fin_invalid_format"): "warning",
        ("4", "legacy_record_program_unresolved"): "warning",
        ("4", "legacy_fin_invalid_format"): "warning",
        ("5", "legacy_fin_duplicate_source"): "warning",
        ("6", "legacy_fin_duplicate_source"): "warning",
    }
    assert all(
        issue.source_table == "students"
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=PLACEMENT_ENTITY_TYPE)
    )


@pytest.mark.django_db
def test_fin_matrix_writes_only_the_unambiguous_values(seeded):
    organization, actor, run, users = seeded

    StudentPlacementPhase().run(_seeded_context(organization, actor, run))

    fins = {legacy_pk: UserProfile.objects.get(user=user).fin for legacy_pk, user in users.items()}
    assert fins[1] == "AB12345"  # lower-case source is normalised, then written
    assert fins[2] is None  # blank ⇒ no write, no issue
    assert fins[3] is None  # "TOOSHORT" is 8 chars ⇒ invalid format
    assert fins[4] is None  # "6CHARS" is 6 chars ⇒ invalid format
    # Both occurrences of the same FİN are refused, neither is written.
    assert fins[5] is None and fins[6] is None


@pytest.mark.django_db
def test_a_fin_already_held_by_another_profile_is_a_collision(placement_environment, django_user_model):
    actor = placement_environment
    organization = _organization(actor, "placement-fin-collision")
    policy = _policy()
    rows = [_student_row(1, group_id=20, entry_year="2019", fincode="AB12345")]
    plan = _plan(len(rows))
    run = _running_run(organization, actor, policy=policy, plan=plan)
    _seed_structure(organization, actor, run.pk)
    users = _stage_students(organization, actor, run.pk, django_user_model, (1,))
    incumbent = django_user_model.objects.create(username="incumbent", email="incumbent@example.test")
    UserProfile.objects.filter(user=incumbent).update(organization=organization, fin="AB12345")

    StudentPlacementPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert UserProfile.objects.get(user=users[1]).fin is None
    assert LegacyMigrationIssue.objects.filter(run=run, legacy_pk="1", rule_code="legacy_fin_collision").exists()
    # The savepoint rolled the failed write back without losing the ledger row.
    assert LegacyEntityMap.objects.filter(entity_type=PLACEMENT_ENTITY_TYPE, legacy_pk="1").exists()


@pytest.mark.django_db
def test_names_are_written_only_into_blank_target_fields(seeded):
    organization, actor, run, users = seeded

    StudentPlacementPhase().run(_seeded_context(organization, actor, run))

    first = users[1]
    first.refresh_from_db()
    assert (first.first_name, first.last_name) == ("Elvin", "Qurbanov")
    preserved = users[2]
    preserved.refresh_from_db()
    assert (preserved.first_name, preserved.last_name) == ("Köhnə", "Ad")


@pytest.mark.django_db
def test_the_patronymic_is_written_only_into_a_blank_profile_field(seeded):
    """2026-08-28 finding (B-1): not one of 8,441 profiles carried a patronymic.

    RİM resolves an account by name + surname + PATRONYMIC, so a blank
    ``UserProfile.patronymic`` breaks "find by patronymic" on the real data.
    Same §4.5 contract as the names: fill a blank field, never overwrite.
    """

    organization, actor, run, users = seeded
    UserProfile.objects.filter(user=users[2]).update(patronymic="Mövcud")
    rows = [
        _student_row(
            1,
            group_id=20,
            entry_year="2019",
            first_name="Elvin",
            last_name="Qurbanov",
            father_name="C&uuml;c&uuml;",
        ),
        _student_row(2, group_id=21, entry_year="2019", father_name="Şahin"),
        _student_row(3, group_id=20, entry_year="2019"),
    ]

    StudentPlacementPhase().run(_seeded_context(organization, actor, run, rows=rows))

    # The dump stores HTML entities raw; ``clean_text`` unescapes on the way out.
    assert UserProfile.objects.get(user=users[1]).patronymic == "Cücü"
    assert UserProfile.objects.get(user=users[2]).patronymic == "Mövcud"
    assert UserProfile.objects.get(user=users[3]).patronymic == ""


@pytest.mark.django_db
def test_demographics_are_written_only_into_blank_profile_fields(seeded):
    """``sex``/``birthday`` artıq proyeksiyadadır — faza onları yalnız oxuyur.

    Mənbədə hər iki sütun seyrəkdir (cins 21 %, doğum tarixi 28 %), ona görə
    yarımçıq sətir normadır və pozuq dəyər fail-closed NULL qalır.  Yazı
    müqaviləsi ad/ata adı ilə eynidir (§4.5): boşluğu doldur, üzərinə yazma.
    """

    organization, actor, run, users = seeded
    UserProfile.objects.filter(user=users[2]).update(
        gender=UserProfile.Gender.FEMALE, birth_date=datetime.date(1999, 1, 2)
    )
    rows = [
        _student_row(1, group_id=20, entry_year="2019", sex=1, birthday="19/10/2003"),
        _student_row(2, group_id=21, entry_year="2019", sex=1, birthday="01/01/2001"),
        _student_row(3, group_id=20, entry_year="2019", sex=2, birthday="12/16/2001"),
        _student_row(4, group_id=22, entry_year="2019", sex=0, birthday=""),
    ]

    StudentPlacementPhase().run(_seeded_context(organization, actor, run, rows=rows))

    written = UserProfile.objects.get(user=users[1])
    assert (written.gender, written.birth_date) == ("male", datetime.date(2003, 10, 19))
    # Mövcud dəyər idxal tərəfindən heç vaxt üzərinə yazılmır.
    preserved = UserProfile.objects.get(user=users[2])
    assert (preserved.gender, preserved.birth_date) == ("female", datetime.date(1999, 1, 2))
    # ``12/16/2001`` yalnız MM/DD kimi oxuna bilər — təxmin edilmir, NULL qalır;
    # cins isə eyni sətirdə yenə də yazılır (iki müstəqil sütun).
    partial = UserProfile.objects.get(user=users[3])
    assert (partial.gender, partial.birth_date) == ("female", None)
    absent = UserProfile.objects.get(user=users[4])
    assert (absent.gender, absent.birth_date) == ("unspecified", None)


@pytest.mark.django_db
def test_the_live_phase_digest_equals_the_ledger_rebuild(seeded):
    """SA-2: ``--emit-report-only`` must reproduce a batch-less phase exactly."""

    organization, actor, run, _users = seeded
    phase = StudentPlacementPhase()
    plan = _plan(len(_cohort_rows()))

    live = phase.run(_seeded_context(organization, actor, run))
    rebuilt = phase_report_from_ledger(run, phase=phase, plan=plan)

    assert rebuilt.phase_digest == live.phase_digest
    assert dict(rebuilt.state_counts) == dict(live.state_counts)
    assert (rebuilt.phase_key, rebuilt.order) == (live.phase_key, live.order)
    assert rebuilt.source_tables == live.source_tables == ()
    assert rebuilt.batches == live.batches == ()
    assert rebuilt.declared_source_rows == rebuilt.observed_source_rows == 0
    assert rebuilt.staged_account_count == live.staged_account_count == 0
    # C5 always re-derives issue counts from the ledger, never from a phase pass.
    assert dict(rebuilt.issue_counts) == {}
    assert dict(live.issue_counts) != {}


@pytest.mark.django_db
def test_a_repeated_invocation_replays_the_sealed_decisions(seeded):
    """Resume: re-deriving would flip ``name_state`` and break the ledger."""

    organization, actor, run, _users = seeded
    phase = StudentPlacementPhase()

    first = phase.run(_seeded_context(organization, actor, run))
    second = phase.run(_seeded_context(organization, actor, run))

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert LegacyEntityMap.objects.filter(entity_type=PLACEMENT_ENTITY_TYPE).count() == 6
    assert LegacyEntityObservation.objects.filter(run=run, entity_map__entity_type=PLACEMENT_ENTITY_TYPE).count() == 6


@pytest.mark.django_db
def test_the_phase_digest_is_identical_across_two_independent_runs(placement_environment, django_user_model):
    """Cross-run determinism: no UUID and no target identity enters the chain."""

    actor = placement_environment
    rows = [
        _student_row(1, group_id=20, entry_year="2019", first_name="Elvin", last_name="Qurbanov"),
        _student_row(2, group_id=999, entry_year=""),
    ]
    digests = []
    for slug in ("placement-run-a", "placement-run-b"):
        organization = _organization(actor, slug)
        policy = _policy()
        run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
        _seed_structure(organization, actor, run.pk)
        _stage_students(organization, actor, run.pk, django_user_model, (1, 2))
        digests.append(StudentPlacementPhase().run(_seeded_context(organization, actor, run, rows=rows)).phase_digest)

    assert digests[0] == digests[1]


@pytest.mark.django_db
def test_two_ledger_keys_pointing_at_one_group_unit_are_ambiguous(placement_environment, django_user_model):
    actor = placement_environment
    organization = _organization(actor, "placement-ambiguous")
    policy = _policy()
    rows = [_student_row(1, group_id=20)]
    run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
    _seed_structure(organization, actor, run.pk)
    _stage_students(organization, actor, run.pk, django_user_model, (1,))
    duplicate = OrgUnit.objects.get(organization=organization, slug="myedu-grp-20")
    _map(
        run.pk, actor, entity_type=GROUP_ENTITY_TYPE, legacy_pk=999, label=ORG_UNIT_MODEL_LABEL, target_pk=duplicate.pk
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        StudentPlacementPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert exc_info.value.code == "legacy_rehearsal_structure_index_ambiguous"


@pytest.mark.django_db
def test_the_source_row_hash_never_leaks_a_credential_column(seeded):
    organization, actor, run, _users = seeded
    factory = _factory(_cohort_rows())
    context = replace(
        _context(
            plan=_plan(len(_cohort_rows())),
            factory=factory,
            organization=organization,
            actor=actor,
        ),
        run_id=run.pk,
    )

    StudentPlacementPhase().run(context)

    statements = [statement for connection in factory.connections for statement in connection.statements]
    assert len(statements) == 2  # one FİN histogram pass, one decision pass
    assert all("password" not in statement for statement in statements)
    assert all(connection.rolled_back and connection.closed for connection in factory.connections)


def test_record_derivation_hash_follows_the_documented_recipe():
    """The recipe is a public contract: the SAR slice will recompute it."""

    row = _student_row(1, group_id=20, entry_year="2019")
    placement = resolve_placement(row, groups=_GROUPS, programs=_PROGRAMS)
    row_hash = source_row_hash(contract=STUDENT_IDENTITY_FIELDS, legacy_pk=1, projected_row=row)

    digest = hashlib.sha256(b"legacy-rehearsal-placement-derivation-v1\x00")
    for part in (
        STUDENT_IDENTITY_FIELDS.fingerprint,
        "1",
        row_hash,
        "deferred",
        "050620",
        "myedu-grp-20",
        "bachelor",
        "full_time",
        "az",
        "2019",
        "student",
        "written",
        "preserved",
        # The patronymic is a SEPARATE decision (own target column, own source field).
        "written",
        # 2026-08-30: demographics (gender + birth date) are two more target
        # columns fed by ``sex``/``birthday``, so their write state joins the
        # recipe exactly like the name and patronymic states before it.
        "blank",
    ):
        digest.update(encoded_part(part))

    assert (
        record_derivation_hash(
            legacy_pk=1,
            row_hash=row_hash,
            placement=placement,
            fin_state="written",
            name_state="preserved",
            patronymic_state="written",
            demographics_state="blank",
        )
        == digest.hexdigest()
    )
    # No target primary key and no run identity may ever enter it.
    assert (
        record_derivation_hash(
            legacy_pk=1,
            row_hash=row_hash,
            placement=placement,
            fin_state="blank",
            name_state="preserved",
            patronymic_state="written",
            demographics_state="blank",
        )
        != digest.hexdigest()
    )
    # Demoqrafiya yazısı da qərarın kimliyini dəyişir: boş sahəni doldurmaq ≠
    # mənbədə heç nə olmaması.
    assert record_derivation_hash(
        legacy_pk=1,
        row_hash=row_hash,
        placement=placement,
        fin_state="written",
        name_state="preserved",
        patronymic_state="written",
        demographics_state="written",
    ) != digest.hexdigest()
