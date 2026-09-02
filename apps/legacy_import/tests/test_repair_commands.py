"""2026-09-02 audit təmir əmrləri: qapılar, qərar qaydası, idempotentlik.

Bu dəst məhsul qapılarını REAL şəkildə keçir: hesablar
``stage_imported_account`` → ``archive_staged_account`` ilə qurulur, bərpa isə
``restore_archived_account`` ilə edilir — yəni PostgreSQL-dəki 0013/0016
trigger-ləri (evidence qapısı) bu testlərdə həqiqətən işləyir.
"""

import hashlib

from django.core.management import call_command
from django.core.management.base import CommandError

import pytest

from apps.accounts.models import UserProfile
from apps.accounts.public import archive_staged_account, stage_imported_account
from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationRun
from apps.legacy_import.services import (
    repair_archive,
    repair_demographics,
    repair_periods,
    repair_rooms,
    repair_sar,
    repair_support,
)
from apps.legacy_import.services.ledger import TargetValidation, create_run, start_run, upsert_entity_map, upsert_issue
from apps.legacy_import.services.rehearsal_authorizer import USER_MODEL_LABEL
from apps.legacy_import.services.rehearsal_contracts import SOURCE_SYSTEM
from apps.organizations.models import AcademicPeriod, Membership, Organization, Role
from core.constants import AcademicPeriodType, OrganizationType

_SLUG = "repair-univ"
_TRANSFORM = "rehearsal-identity-v2.0123456789ab"


def _allow(**_kwargs):
    return True


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _summary_value(output, key):
    """``render_summary`` açarları ljust ilə doldurulur — boşluğa bağlanmırıq."""

    for line in output.splitlines():
        left, separator, right = line.partition(":")
        if separator and left.strip() == key:
            return right.strip()
    raise AssertionError(f"xülasədə açar tapılmadı: {key!r}\n{output}")


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="repair_actor", email="repair-actor@example.test", password="test-only"
    )


@pytest.fixture()
def organization(actor):
    organization = Organization.objects.create(
        name="Repair University",
        slug=_SLUG,
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )
    for name, display in (("student", "Tələbə"), ("alumni", "Məzun"), ("teacher", "Müəllim")):
        Role.objects.get_or_create(
            organization=organization,
            name=name,
            defaults={"display_name": display, "level": 10, "permissions": [], "is_active": True},
        )
    Role.objects.filter(organization=organization).update(is_active=True)
    return organization


@pytest.fixture()
def run(organization, actor):
    created = create_run(
        actor=actor,
        authorize=_allow,
        organization=organization,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=_digest("snapshot"),
        snapshot_size_bytes=1024,
        source_row_count=3,
        schema_version="legacy-table-plan-v1.0123456789ab",
        transform_version=_TRANSFORM,
        mode=LegacyMigrationRun.Mode.REHEARSAL,
        accounting_mode=LegacyMigrationRun.AccountingMode.BATCH,
        origin=LegacyMigrationRun.Origin.COMMAND,
    )
    return start_run(run_id=created.pk, actor=actor, authorize=_allow)


def _validators():
    from django.contrib.auth import get_user_model

    def validate_user(*, target_pk, organization):
        exists = get_user_model()._default_manager.filter(pk=target_pk).exists()
        return TargetValidation(exists=exists, organization_matches=exists)

    return {USER_MODEL_LABEL: validate_user}


def _archived_student(organization, actor, legacy_pk):
    """Mənbədəki kimi: staged hesab → arxiv (giriş bağlı, üzvlük aktiv)."""

    alumni = Role.objects.get(organization=organization, name="alumni")
    staged = stage_imported_account(
        organization=organization,
        role=Role.objects.get(organization=organization, name="student"),
        actor=actor,
        username=f"myedu.student.{legacy_pk}",
        email=f"myedu.student.{legacy_pk}@placeholder.invalid",
        student_identifier=f"myedu-student-{legacy_pk}",
    )
    Membership.objects.filter(user=staged.user, organization=organization).update(role=alumni)
    archive_staged_account(
        user=staged.user,
        organization=organization,
        expected_role=alumni,
        actor=actor,
        email_authoritative=True,
        email_authority_evidence_digest=_digest(f"archive-{legacy_pk}"),
        email_authority_reason_code="institution_registry_match",
    )
    return staged.user


def _seal(run, actor, *, entity_type, legacy_pk, state, label="", target_pk=""):
    return upsert_entity_map(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        entity_type=entity_type,
        legacy_pk=str(legacy_pk),
        source_row_hash=_digest(f"{entity_type}:{legacy_pk}"),
        state=state,
        target_model_label=label,
        target_pk=str(target_pk),
        target_validators=_validators(),
    )


def _issue(run, actor, entity_map, *, legacy_pk, rule_code, severity="info"):
    return upsert_issue(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        source_table="students",
        entity_type=repair_archive.SAR_ENTITY_TYPE,
        legacy_pk=str(legacy_pk),
        rule_code=rule_code,
        severity=severity,
        payload_digest=_digest(f"{legacy_pk}:{rule_code}"),
        entity_map_id=entity_map.pk,
    )


@pytest.fixture()
def archived_cohort(organization, actor, run):
    """Üç arxiv sətri: (1) səhv arxiv, (2) həqiqətən buraxılmış, (3) ledger-siz."""

    users = {}
    for legacy_pk in (1970, 200, 999):
        users[legacy_pk] = _archived_student(organization, actor, legacy_pk)
    for legacy_pk in (1970, 200):
        _seal(
            run,
            actor,
            entity_type="student",
            legacy_pk=legacy_pk,
            state=LegacyEntityMap.State.MIGRATED,
            label=USER_MODEL_LABEL,
            target_pk=users[legacy_pk].pk,
        )
        sar_map = _seal(
            run,
            actor,
            entity_type=repair_archive.SAR_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            state=LegacyEntityMap.State.SKIPPED,
        )
        _issue(run, actor, sar_map, legacy_pk=legacy_pk, rule_code="legacy_sar_archived_student")
        if legacy_pk == 1970:
            _issue(run, actor, sar_map, legacy_pk=legacy_pk, rule_code=repair_archive.ARCHIVED_NO_YEAR_RULE)
        else:
            _issue(run, actor, sar_map, legacy_pk=legacy_pk, rule_code=repair_archive.DEPARTED_RULE)
    return users


# ---------------------------------------------------------------------------
# Ortaq qapılar
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_apply_is_refused_without_the_disposable_marker(organization):
    """Fail-closed: markersiz bazada yazmaq üçün açıq bayraq lazımdır."""

    with pytest.raises(CommandError) as refusal:
        call_command("legacy_repair_archive_status", "--organization", _SLUG, "--apply")
    assert "legacy_repair_target_not_disposable" in str(refusal.value)


@pytest.mark.django_db
def test_dry_run_needs_no_marker_at_all(organization, capsys):
    call_command("legacy_repair_archive_status", "--organization", _SLUG)
    assert "DRY-RUN" in capsys.readouterr().out


@pytest.mark.django_db
def test_an_unknown_organization_is_refused(db):
    with pytest.raises(CommandError):
        call_command("legacy_repair_archive_status", "--organization", "no-such-tenant")


@pytest.mark.django_db
def test_apply_and_dry_run_cannot_be_combined(organization):
    with pytest.raises(CommandError):
        call_command("legacy_repair_archive_status", "--organization", _SLUG, "--apply", "--dry-run")


# ---------------------------------------------------------------------------
# P0-1 — arxiv statusu
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_only_the_no_admission_year_row_is_a_restore_candidate(organization, archived_cohort):
    decisions = {item.legacy_pk: item for item in repair_archive.plan_decisions(organization)}

    assert decisions["1970"].action == "restore"
    assert decisions["1970"].reason == "no_admission_year_only"
    assert decisions["200"].action == "keep_archived"
    assert decisions["200"].reason == "source_azadedildi"
    assert decisions["-"].action == "keep_archived"
    assert decisions["-"].reason == "ledger_map_missing"


@pytest.mark.django_db
def test_require_activity_keeps_a_student_without_any_enrolment(organization, archived_cohort):
    decisions = {item.legacy_pk: item for item in repair_archive.plan_decisions(organization, require_activity=True)}

    assert decisions["1970"].action == "keep_archived"
    assert decisions["1970"].reason == "no_enrolment_evidence"


@pytest.mark.django_db
def test_a_dry_run_writes_absolutely_nothing(organization, archived_cohort, capsys):
    call_command("legacy_repair_archive_status", "--organization", _SLUG)

    output = capsys.readouterr().out
    assert "restore" in output
    for user in archived_cohort.values():
        assert UserProfile.objects.get(user=user).access_state == UserProfile.AccessState.ARCHIVED


@pytest.mark.django_db
def test_apply_restores_only_the_wrongly_archived_student(organization, actor, archived_cohort, capsys):
    call_command("legacy_repair_archive_status", "--organization", _SLUG, "--apply", "--i-know-this-is-production")

    restored = archived_cohort[1970]
    assert UserProfile.objects.get(user=restored).access_state == UserProfile.AccessState.ACTIVE
    membership = Membership.objects.get(user=restored, organization=organization)
    assert membership.role.name == "student" and membership.is_active is True
    # Həqiqətən buraxılmış və ledger-siz sətirlər TOXUNULMUR.
    for legacy_pk in (200, 999):
        assert UserProfile.objects.get(user=archived_cohort[legacy_pk]).access_state == UserProfile.AccessState.ARCHIVED
    assert _summary_value(capsys.readouterr().out, "FAKTİKİ bərpa olunan") == "1"


@pytest.mark.django_db
def test_a_restored_student_can_pass_the_login_gate(organization, archived_cohort):
    from apps.accounts.identity import user_access_is_login_blocked

    restored = archived_cohort[1970]
    assert user_access_is_login_blocked(restored) is True

    call_command("legacy_repair_archive_status", "--organization", _SLUG, "--apply", "--i-know-this-is-production")

    restored.refresh_from_db()
    assert user_access_is_login_blocked(restored) is False


@pytest.mark.django_db
def test_the_repair_is_idempotent(organization, archived_cohort, capsys):
    call_command("legacy_repair_archive_status", "--organization", _SLUG, "--apply", "--i-know-this-is-production")
    capsys.readouterr()  # birinci icranın çıxışını təmizlə ki, ikinci ölçülsün
    call_command("legacy_repair_archive_status", "--organization", _SLUG, "--apply", "--i-know-this-is-production")
    second = capsys.readouterr().out
    # İkinci icrada arxivdə yalnız iki sətir qalır və heç biri bərpa namizədi deyil.
    assert _summary_value(second, "bərpa namizədi (restore)") == "0"
    assert _summary_value(second, "FAKTİKİ bərpa olunan") == "0"


@pytest.mark.django_db
def test_the_repair_writes_an_audit_row_per_changed_user(organization, archived_cohort):
    from django.apps import apps as django_apps

    call_command("legacy_repair_archive_status", "--organization", _SLUG, "--apply", "--i-know-this-is-production")

    audit_model = django_apps.get_model("audit", "AuditLog")
    assert audit_model.objects.filter(organization=organization, reason=repair_archive.AUDIT_REASON).count() == 1


@pytest.mark.django_db
def test_the_limit_bounds_the_decision_table(organization, archived_cohort):
    assert len(repair_archive.plan_decisions(organization, limit=2)) == 2


def test_the_evidence_digest_is_deterministic_and_hex():
    first = repair_archive.evidence_digest(organization_pk="org", user_pk=7, legacy_pk="1970")
    second = repair_archive.evidence_digest(organization_pk="org", user_pk=7, legacy_pk="1970")
    other = repair_archive.evidence_digest(organization_pk="org", user_pk=8, legacy_pk="1970")

    assert first == second != other
    assert len(first) == 64 and int(first, 16) >= 0


def test_the_cohort_year_is_derived_from_the_earliest_enrolment_year():
    decision = repair_archive.ArchiveDecision(
        legacy_pk="1970",
        user_pk=1,
        username="u",
        full_name="",
        group="",
        enrollments=3,
        earliest_year="2022/2023",
        latest_year="2025/2026",
        departed=False,
        action="restore",
        reason="",
    )
    assert repair_archive.derived_admission_year(decision) == 2022
    assert (
        repair_archive.derived_admission_year(decision.__class__(**{**decision.__dict__, "earliest_year": ""})) is None
    )


# ---------------------------------------------------------------------------
# P0-3 — cari dövr
# ---------------------------------------------------------------------------


def _period(organization, name, year, start, end, **kwargs):
    return AcademicPeriod.objects.create(
        organization=organization,
        name=name,
        academic_year=year,
        period_type=AcademicPeriodType.SEMESTER,
        start_date=start,
        end_date=end,
        **kwargs,
    )


@pytest.mark.django_db
def test_the_current_period_defaults_to_the_one_containing_today(organization):
    import datetime

    today = datetime.date(2026, 10, 1)
    _period(organization, "Yay", "2025/2026", datetime.date(2026, 7, 1), datetime.date(2026, 8, 31))
    payiz = _period(organization, "Payız", "2026/2027", datetime.date(2026, 9, 15), datetime.date(2027, 1, 31))

    rows = repair_periods.period_rows(organization)
    selected, reason = repair_periods.select_period(rows, selector="", today=today)

    assert selected.pk == payiz.pk and reason == "contains_today"


@pytest.mark.django_db
def test_an_explicit_selector_wins(organization):
    import datetime

    yay = _period(organization, "Yay", "2025/2026", datetime.date(2026, 7, 1), datetime.date(2026, 8, 31))
    _period(organization, "Payız", "2026/2027", datetime.date(2026, 9, 15), datetime.date(2027, 1, 31))

    rows = repair_periods.period_rows(organization)
    selected, reason = repair_periods.select_period(rows, selector="2025/2026 Yay", today=datetime.date(2026, 10, 1))

    assert selected.pk == yay.pk and reason == "explicit_selector"


@pytest.mark.django_db
def test_setting_the_current_period_is_idempotent_and_exclusive(organization, actor):
    import datetime

    first = _period(organization, "Yaz", "2025/2026", datetime.date(2026, 2, 1), datetime.date(2026, 6, 30))
    second = _period(organization, "Payız", "2026/2027", datetime.date(2026, 9, 15), datetime.date(2027, 1, 31))

    assert repair_periods.set_current(organization, first, actor=actor) is True
    assert repair_periods.set_current(organization, first, actor=actor) is False
    assert repair_periods.set_current(organization, second, actor=actor) is True

    first.refresh_from_db()
    assert first.is_current is False and AcademicPeriod.objects.filter(is_current=True).count() == 1


@pytest.mark.django_db
def test_creating_a_year_adds_three_seasons_once(organization):
    created = repair_periods.create_year(organization, "2026/2027")
    again = repair_periods.create_year(organization, "2026/2027")

    assert {period.name for period in created} == {"Payız", "Yaz", "Yay"}
    assert again == []
    assert AcademicPeriod.objects.filter(organization=organization, is_current=True).count() == 0


# ---------------------------------------------------------------------------
# P1 — demoqrafiya / qrup nömrəsi
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_group_number_repair_only_fills_blank_profiles(organization, actor, archived_cohort):
    from apps.organizations.models import OrgUnit
    from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
    from core.constants import OrgUnitType

    faculty = OrgUnit.objects.create(
        organization=organization, name="Fakültə", slug="fak", unit_type=OrgUnitType.FACULTY
    )
    specialty = OrgUnit.objects.create(
        organization=organization, name="İxtisas", slug="ixt", unit_type=OrgUnitType.SPECIALTY, parent=faculty
    )
    group = OrgUnit.objects.create(
        organization=organization, name="529 BI", slug="529-bi", unit_type=OrgUnitType.GROUP, parent=specialty
    )
    program = Program.objects.create(
        organization=organization, name="P", code="P-1", specialty_unit=specialty, degree_level="bachelor"
    )
    curriculum = Curriculum.objects.create(organization=organization, program=program, admission_year=1950)
    user = archived_cohort[1970]
    StudentAcademicRecord.objects.create(
        organization=organization,
        student=user,
        program=program,
        curriculum=curriculum,
        group=group,
        admission_year=1950,
    )

    candidates = repair_demographics.group_number_candidates(organization)
    assert candidates == [(user.pk, "529 BI")]

    assert repair_demographics.write_group_numbers(organization, candidates) == 1
    assert UserProfile.objects.get(user=user).student_group_number == "529 BI"
    # İdempotent: ikinci icra artıq dolu sahəyə toxunmur.
    assert repair_demographics.group_number_candidates(organization) == []


@pytest.mark.django_db
def test_target_coverage_counts_the_profile_fields(organization, archived_cohort):
    coverage = repair_demographics.target_coverage(organization)

    assert coverage["profil"] >= 3
    assert coverage["birth_date"] == 0
    assert coverage["gender"] == 0
    assert coverage["student_group_number"] == 0


def test_the_repair_support_table_renderer_is_deterministic():
    rendered = repair_support.render_table(("a", "bb"), [("1", "2"), ("333", "4")])

    assert rendered.splitlines()[0].startswith("a  ")
    assert rendered.splitlines()[2].startswith("1  ")


# ---------------------------------------------------------------------------
# R-5 — legacy otaq reyestri
# ---------------------------------------------------------------------------


class _FakeRoomStream:
    """``open_audited_identity_stream`` kontekstinin minimal əvəzi."""

    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return iter(self._rows)

    def __exit__(self, *_exc):
        return False


def _room_rows(monkeypatch, rows):
    from apps.legacy_import.services import repair_rooms as module

    monkeypatch.setattr(module, "open_audited_identity_stream", lambda **_kw: _FakeRoomStream(rows))


def _room(legacy_pk, name, bina, capacity):
    return {"id": legacy_pk, "name": name, "bina": bina, "max_student_count": capacity}


@pytest.mark.django_db
def test_rooms_plan_maps_the_phase_shape(organization, monkeypatch):
    _room_rows(monkeypatch, [_room(4, "03/2", 3, "28"), _room(5, "04", 1, "16")])

    plan = repair_rooms.plan_rooms(organization, connection_factory=object())

    assert [item.code for item in plan] == ["myedu-room-4", "myedu-room-5"]
    assert [item.building for item in plan] == ["3", "1"]
    assert [item.capacity for item in plan] == [28, 16]
    assert {item.action for item in plan} == {"create"}


@pytest.mark.django_db
def test_rooms_materialise_is_idempotent(organization, monkeypatch):
    from apps.exams.models import ExamRoom

    _room_rows(monkeypatch, [_room(4, "03/2", 3, "28"), _room(5, "04", 1, "16")])

    assert repair_rooms.materialise(organization, connection_factory=object()) == 2
    assert repair_rooms.materialise(organization, connection_factory=object()) == 0
    assert ExamRoom.objects.filter(organization=organization).count() == 2
    assert repair_rooms.coverage(organization) == {"otaq": 2, "aktiv otaq": 2, "korpus": 2}


@pytest.mark.django_db
def test_rooms_never_overwrite_a_renamed_room(organization, monkeypatch):
    """İmport insan işinin üstünə yazmır: sonradan adlandırılmış otaq qorunur."""

    from apps.exams.models import ExamRoom

    _room_rows(monkeypatch, [_room(4, "03/2", 3, "28")])
    repair_rooms.materialise(organization, connection_factory=object())
    ExamRoom.objects.filter(organization=organization, code="myedu-room-4").update(name="İmtahan zalı A")

    repair_rooms.materialise(organization, connection_factory=object())

    assert ExamRoom.objects.get(organization=organization, code="myedu-room-4").name == "İmtahan zalı A"


@pytest.mark.django_db
def test_a_non_numeric_capacity_degrades_to_zero(organization, monkeypatch):
    _room_rows(monkeypatch, [_room(9, "28", 3, "x")])

    plan = repair_rooms.plan_rooms(organization, connection_factory=object())

    assert plan[0].capacity == 0
    assert "legacy_room_capacity_invalid" in plan[0].rule_codes


@pytest.mark.django_db
def test_the_rooms_command_refuses_apply_without_the_marker(organization):
    with pytest.raises(CommandError):
        call_command("legacy_repair_rooms", "--organization", _SLUG, "--from-source", "--apply")


# ---------------------------------------------------------------------------
# R-9 — təmirlə yaradılmış tələbələr üçün SAR
# ---------------------------------------------------------------------------


def _student_row(legacy_pk, *, group_id, entry_year="2022"):
    return {"id": legacy_pk, "group_id": group_id, "entry_year": entry_year, "fincode": None}


@pytest.fixture()
def academic_tree(organization):
    from apps.organizations.models import OrgUnit
    from apps.registrar.models import Curriculum, Program
    from core.constants import OrgUnitType

    faculty = OrgUnit.objects.create(organization=organization, name="Fakültə", slug="f", unit_type=OrgUnitType.FACULTY)
    specialty = OrgUnit.objects.create(
        organization=organization, name="İxtisas", slug="sp", unit_type=OrgUnitType.SPECIALTY, parent=faculty
    )
    group = OrgUnit.objects.create(
        organization=organization,
        name="130 T",
        slug="130-t",
        unit_type=OrgUnitType.GROUP,
        parent=specialty,
        settings={"legacy": {"id": 42}, "degree_level": "bachelor", "admission_year": 2021},
    )
    program = Program.objects.create(
        organization=organization, name="P", code="MYEDU-1", specialty_unit=specialty, degree_level="bachelor"
    )
    curriculum = Curriculum.objects.create(organization=organization, program=program, admission_year=2022)
    return group, program, curriculum


@pytest.mark.django_db
def test_the_sar_repair_uses_entry_year_then_group_then_sentinel(organization, academic_tree):
    group, _program, _curriculum = academic_tree
    groups = repair_sar.group_index(organization)

    assert repair_sar.resolve_admission_year("2022", groups["42"]) == 2022
    assert repair_sar.resolve_admission_year("", groups["42"]) == 2021  # qrupun ili
    assert repair_sar.resolve_admission_year("", None) == 1950  # sentinel — «bilinmir»
    assert group.slug == "130-t"


@pytest.mark.django_db
def test_the_sar_repair_creates_a_record_and_is_idempotent(organization, actor, academic_tree):
    from apps.registrar.models import StudentAcademicRecord

    _group, program, curriculum = academic_tree
    user = _archived_student(organization, actor, 5001)
    rows = [(5001, user.pk, user.username, _student_row(5001, group_id=42))]

    created, sources = repair_sar.materialise(organization, rows)
    again, sources_again = repair_sar.materialise(organization, rows)

    assert (created, again) == (1, 0)
    assert sources["curriculum_exact"] == 1 and sources_again["already_present"] == 1
    record = StudentAcademicRecord.objects.get(organization=organization, student=user)
    assert record.program_id == program.pk and record.curriculum_id == curriculum.pk
    assert record.admission_year == 2022 and record.is_active is True


@pytest.mark.django_db
def test_an_unresolvable_group_never_invents_a_record(organization, actor, academic_tree):
    """Mənbədə orphan ``group_id`` — SAR mümkün deyil, sətir toxunulmadan qalır."""

    from apps.registrar.models import StudentAcademicRecord

    user = _archived_student(organization, actor, 5002)
    rows = [(5002, user.pk, user.username, _student_row(5002, group_id=197))]

    created, sources = repair_sar.materialise(organization, rows)

    assert created == 0 and sources["skip_group_unresolved"] == 1
    assert not StudentAcademicRecord.objects.filter(student=user).exists()


@pytest.mark.django_db
def test_a_missing_curriculum_year_falls_back_then_creates(organization, academic_tree):
    _group, program, curriculum = academic_tree
    curricula = repair_sar.curriculum_index(organization)

    same, source = repair_sar.resolve_curriculum(
        organization, program_pk=program.pk, admission_year=2022, curricula=curricula
    )
    near, near_source = repair_sar.resolve_curriculum(
        organization, program_pk=program.pk, admission_year=2019, curricula=curricula
    )

    assert (same, source) == (curriculum.pk, "exact")
    assert (near, near_source) == (curriculum.pk, "substituted")
