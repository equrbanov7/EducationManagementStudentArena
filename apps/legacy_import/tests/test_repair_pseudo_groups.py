"""QA auditi P2-8 — ``legacy_repair_pseudo_groups`` (2026-09-05).

Tam hesabat: ``docs/audits/2026-09-05/LEVEL_GROUPS.md``. Bu dəst iki
təhlükəsiz əməli yoxlayır: ``mark_service`` (``OrgUnit.is_service_unit``) və
``expel`` (``apps.registrar.movements.create_movement`` ilə rəsmi EXPULSION),
hər ikisi dry-run-default, idempotent və audit izli.
"""

from django.core.management import call_command
from django.core.management.base import CommandError

import pytest

from apps.legacy_import.services import repair_pseudo_groups
from apps.organizations.models import Organization, OrgUnit
from apps.registrar.models import AcademicStatus, Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType

_SLUG = "pseudo-group-univ"


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
        username="pseudo_group_actor", email="pseudo-group-actor@example.test", password="test-only"
    )


@pytest.fixture()
def organization(actor):
    return Organization.objects.create(
        name="Pseudo Group University",
        slug=_SLUG,
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )


@pytest.fixture()
def specialty(organization):
    """Bir REAL fakültə/ixtisas — psevdo-qruplar bunun altına qoyulur."""

    faculty = OrgUnit.objects.create(
        organization=organization, name="Filologiya", slug="filologiya", unit_type=OrgUnitType.FACULTY
    )
    return OrgUnit.objects.create(
        organization=organization, name="Tərcümə", slug="tercume", unit_type=OrgUnitType.SPECIALTY, parent=faculty
    )


@pytest.fixture()
def academic_setup(organization, specialty):
    """Program + Curriculum — ``StudentAcademicRecord`` yaratmaq üçün."""

    program = Program.objects.create(
        organization=organization, name="Tərcümə", code="MYEDU-1", specialty_unit=specialty, degree_level="bachelor"
    )
    curriculum = Curriculum.objects.create(organization=organization, program=program, admission_year=2022)
    return program, curriculum


def _make_group(organization, specialty, name, *, slug):
    return OrgUnit.objects.create(
        organization=organization, name=name, slug=slug, unit_type=OrgUnitType.GROUP, parent=specialty
    )


def _make_student(organization, program, curriculum, group, *, username, status=AcademicStatus.ENROLLED):
    from django.contrib.auth import get_user_model

    from apps.organizations.models import Membership

    user = get_user_model().objects.create_user(username=username, email=f"{username}@example.test")
    # Postgres-də `registrar_guard_active_member` trigger-i akademik qeydin sahibindən
    # AKTİV «student» üzvlüyü tələb edir (sqlite-da trigger yoxdur — ona görə lokal
    # sürətli qaçışda görünmür, CI-də düşür).
    Membership.objects.create(
        user=user,
        organization=organization,
        role=organization.roles.get(name="student"),
        is_primary=True,
        is_active=True,
    )
    return StudentAcademicRecord.objects.create(
        organization=organization,
        student=user,
        program=program,
        curriculum=curriculum,
        group=group,
        admission_year=2022,
        status=status,
    )


# ---------------------------------------------------------------------------
# Ad naxışı — candidate_units
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_candidate_units_matches_level_prefix_and_both_expelled_spellings(organization, specialty):
    level = _make_group(organization, specialty, "Level - Group 1", slug="level-1")
    expelled_a = _make_group(organization, specialty, "Xaric olunanlar 2023", slug="xo-2023")
    expelled_b = _make_group(organization, specialty, "Xaric olanlar", slug="xo")
    real_group = _make_group(organization, specialty, "331 T1", slug="331-t1")

    ids = {unit.id for unit in repair_pseudo_groups.candidate_units(organization)}

    assert {level.id, expelled_a.id, expelled_b.id} <= ids
    assert real_group.id not in ids


@pytest.mark.django_db
def test_candidate_units_excludes_non_group_unit_types_named_level(organization, specialty):
    """«Level» adlı PSEVDO-İXTİSAS (unit_type='specialty') tutulmamalıdır — yalnız qrup."""

    fake_specialty = OrgUnit.objects.create(
        organization=organization,
        name="Level",
        slug="level-specialty",
        unit_type=OrgUnitType.SPECIALTY,
        parent=specialty.parent,
    )
    chair_with_xaric_substring = OrgUnit.objects.create(
        organization=organization, name="Xarici dillər", slug="xarici-diller", unit_type=OrgUnitType.CHAIR
    )

    ids = {unit.id for unit in repair_pseudo_groups.candidate_units(organization)}

    assert fake_specialty.id not in ids
    assert chair_with_xaric_substring.id not in ids


# ---------------------------------------------------------------------------
# plan_unit_decisions — mark_service
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_empty_and_small_level_groups_are_marked_but_large_holding_is_skipped_by_default(
    organization, specialty, academic_setup
):
    program, curriculum = academic_setup
    empty_group = _make_group(organization, specialty, "Level - Group 1", slug="level-1")
    small_group = _make_group(organization, specialty, "Level - Group 2", slug="level-2")
    _make_student(organization, program, curriculum, small_group, username="small-1")
    large_holding = _make_group(organization, specialty, repair_pseudo_groups.LARGE_HOLDING_GROUP_NAME, slug="lh")
    for index in range(3):
        _make_student(organization, program, curriculum, large_holding, username=f"lh-{index}")

    decisions = {d.unit_id: d for d in repair_pseudo_groups.plan_unit_decisions(organization)}

    assert decisions[str(empty_group.id)].action == "mark_service"
    assert decisions[str(empty_group.id)].record_count == 0
    assert decisions[str(small_group.id)].action == "mark_service"
    assert decisions[str(small_group.id)].record_count == 1
    assert decisions[str(large_holding.id)].action == "skip_large_holding"
    assert decisions[str(large_holding.id)].record_count == 3


@pytest.mark.django_db
def test_the_large_holding_group_is_included_when_the_flag_is_set(organization, specialty, academic_setup):
    program, curriculum = academic_setup
    large_holding = _make_group(organization, specialty, repair_pseudo_groups.LARGE_HOLDING_GROUP_NAME, slug="lh")
    _make_student(organization, program, curriculum, large_holding, username="lh-1")

    decisions = {
        d.unit_id: d for d in repair_pseudo_groups.plan_unit_decisions(organization, include_large_holding=True)
    }

    assert decisions[str(large_holding.id)].action == "mark_service"


@pytest.mark.django_db
def test_an_already_service_unit_is_reported_as_a_noop(organization, specialty):
    unit = _make_group(organization, specialty, "Level - Group 1", slug="level-1")
    unit.is_service_unit = True
    unit.save(update_fields=["is_service_unit"])

    decisions = {d.unit_id: d for d in repair_pseudo_groups.plan_unit_decisions(organization)}

    assert decisions[str(unit.id)].action == "already_service"


# ---------------------------------------------------------------------------
# plan_record_decisions — expel
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_only_enrolled_and_academic_leave_records_in_a_container_are_expel_candidates(
    organization, specialty, academic_setup
):
    program, curriculum = academic_setup
    container = _make_group(organization, specialty, "Xaric olanlar", slug="xo")
    enrolled = _make_student(organization, program, curriculum, container, username="stud-enrolled")
    leave = _make_student(
        organization, program, curriculum, container, username="stud-leave", status=AcademicStatus.ACADEMIC_LEAVE
    )
    already = _make_student(
        organization, program, curriculum, container, username="stud-already", status=AcademicStatus.EXPELLED
    )

    decisions = {d.record_id: d for d in repair_pseudo_groups.plan_record_decisions(organization)}

    assert decisions[str(enrolled.id)].action == "expel"
    assert decisions[str(leave.id)].action == "expel"
    assert decisions[str(already.id)].action == "already_expelled"


# ---------------------------------------------------------------------------
# Əmr — dry-run / apply / idempotentlik
# ---------------------------------------------------------------------------


@pytest.mark.postgres  # `database_is_disposable_target()` yalnız Postgres-də mənalıdır (GUC oxuyur)
@pytest.mark.django_db
def test_apply_is_refused_without_the_disposable_marker(organization):
    with pytest.raises(CommandError) as refusal:
        call_command("legacy_repair_pseudo_groups", "--organization", _SLUG, "--apply")
    assert "legacy_repair_target_not_disposable" in str(refusal.value)


@pytest.mark.django_db
def test_a_dry_run_writes_absolutely_nothing(organization, specialty, academic_setup, capsys):
    program, curriculum = academic_setup
    unit = _make_group(organization, specialty, "Level - Group 1", slug="level-1")
    container = _make_group(organization, specialty, "Xaric olanlar", slug="xo")
    record = _make_student(organization, program, curriculum, container, username="stud-1")

    call_command("legacy_repair_pseudo_groups", "--organization", _SLUG)

    output = capsys.readouterr().out
    assert "DRY-RUN" in output
    unit.refresh_from_db()
    record.refresh_from_db()
    assert unit.is_service_unit is False
    assert record.status == AcademicStatus.ENROLLED


@pytest.mark.django_db
def test_apply_marks_units_and_expels_the_container_students(organization, specialty, academic_setup, capsys):
    from django.apps import apps as django_apps

    program, curriculum = academic_setup
    empty_unit = _make_group(organization, specialty, "Level - Group 1", slug="level-1")
    container = _make_group(organization, specialty, "Xaric olanlar", slug="xo")
    record = _make_student(organization, program, curriculum, container, username="stud-1")
    real_group = _make_group(organization, specialty, "331 T1", slug="331-t1")
    real_record = _make_student(organization, program, curriculum, real_group, username="stud-real")

    call_command("legacy_repair_pseudo_groups", "--organization", _SLUG, "--apply", "--i-know-this-is-production")

    empty_unit.refresh_from_db()
    container.refresh_from_db()
    record.refresh_from_db()
    real_group.refresh_from_db()
    real_record.refresh_from_db()

    assert empty_unit.is_service_unit is True
    assert container.is_service_unit is True
    assert record.status == AcademicStatus.EXPELLED
    # Real qrup/tələbə TOXUNULMUR.
    assert real_group.is_service_unit is False
    assert real_record.status == AcademicStatus.ENROLLED

    movement_model = django_apps.get_model("registrar", "StudentMovement")
    movement = movement_model.objects.get(record=record)
    assert movement.kind == "expulsion"
    assert movement.from_status == AcademicStatus.ENROLLED
    assert movement.to_status == AcademicStatus.EXPELLED
    assert movement.order_number

    audit_model = django_apps.get_model("audit", "AuditLog")
    assert (
        audit_model.objects.filter(
            organization=organization, reason__startswith=repair_pseudo_groups.AUDIT_REASON
        ).count()
        == 2
    )

    output = capsys.readouterr().out
    assert _summary_value(output, "FAKTİKİ işarələnən") == "2"
    assert _summary_value(output, "FAKTİKİ xaric edilən") == "1"


@pytest.mark.django_db
def test_the_repair_is_idempotent(organization, specialty, academic_setup, capsys):
    program, curriculum = academic_setup
    _make_group(organization, specialty, "Level - Group 1", slug="level-1")
    container = _make_group(organization, specialty, "Xaric olanlar", slug="xo")
    _make_student(organization, program, curriculum, container, username="stud-1")

    call_command("legacy_repair_pseudo_groups", "--organization", _SLUG, "--apply", "--i-know-this-is-production")
    capsys.readouterr()  # birinci icranın çıxışını təmizlə
    call_command("legacy_repair_pseudo_groups", "--organization", _SLUG, "--apply", "--i-know-this-is-production")
    second = capsys.readouterr().out

    assert _summary_value(second, "mark_service namizədi") == "0"
    assert _summary_value(second, "FAKTİKİ işarələnən") == "0"
    assert _summary_value(second, "expel namizədi") == "0"
    assert _summary_value(second, "FAKTİKİ xaric edilən") == "0"


@pytest.mark.django_db
def test_skip_expel_leaves_student_status_untouched_while_still_marking_units(organization, specialty, academic_setup):
    program, curriculum = academic_setup
    unit = _make_group(organization, specialty, "Level - Group 1", slug="level-1")
    container = _make_group(organization, specialty, "Xaric olanlar", slug="xo")
    record = _make_student(organization, program, curriculum, container, username="stud-1")

    call_command(
        "legacy_repair_pseudo_groups",
        "--organization",
        _SLUG,
        "--apply",
        "--i-know-this-is-production",
        "--skip-expel",
    )

    unit.refresh_from_db()
    container.refresh_from_db()
    record.refresh_from_db()
    assert unit.is_service_unit is True
    assert container.is_service_unit is True
    assert record.status == AcademicStatus.ENROLLED


@pytest.mark.django_db
def test_skip_mark_service_leaves_units_untouched_while_still_expelling(organization, specialty, academic_setup):
    program, curriculum = academic_setup
    unit = _make_group(organization, specialty, "Level - Group 1", slug="level-1")
    container = _make_group(organization, specialty, "Xaric olanlar", slug="xo")
    record = _make_student(organization, program, curriculum, container, username="stud-1")

    call_command(
        "legacy_repair_pseudo_groups",
        "--organization",
        _SLUG,
        "--apply",
        "--i-know-this-is-production",
        "--skip-mark-service",
    )

    unit.refresh_from_db()
    container.refresh_from_db()
    record.refresh_from_db()
    assert unit.is_service_unit is False
    assert container.is_service_unit is False
    assert record.status == AcademicStatus.EXPELLED


# ---------------------------------------------------------------------------
# Servis funksiyaları — apply_* birbaşa
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_apply_mark_service_is_a_noop_for_non_mark_service_decisions(organization, specialty):
    unit = _make_group(organization, specialty, "Level - Group 1", slug="level-1")
    skip_decision = repair_pseudo_groups.UnitDecision(
        unit_id=str(unit.id),
        name=unit.name,
        specialty="",
        faculty="",
        record_count=0,
        is_expelled_container=False,
        action="already_service",
    )

    changed = repair_pseudo_groups.apply_mark_service(
        organization=organization, actor=organization.owner, decision=skip_decision
    )

    assert changed is False
    unit.refresh_from_db()
    assert unit.is_service_unit is False


@pytest.mark.django_db
def test_apply_expel_is_a_noop_for_non_expel_decisions(organization, specialty, academic_setup):
    program, curriculum = academic_setup
    container = _make_group(organization, specialty, "Xaric olanlar", slug="xo")
    record = _make_student(
        organization, program, curriculum, container, username="stud-1", status=AcademicStatus.GRADUATED
    )
    skip_decision = repair_pseudo_groups.RecordDecision(
        record_id=str(record.id),
        container_name=container.name,
        student_username="stud-1",
        student_full_name="",
        current_status=AcademicStatus.GRADUATED,
        action="already_expelled",
    )

    changed = repair_pseudo_groups.apply_expel(
        organization=organization,
        actor=organization.owner,
        decision=skip_decision,
        order_number="X",
        reason="bu tetbiq olunmamalidir cunki artiq expelled deyil",
    )

    assert changed is False
    record.refresh_from_db()
    assert record.status == AcademicStatus.GRADUATED
