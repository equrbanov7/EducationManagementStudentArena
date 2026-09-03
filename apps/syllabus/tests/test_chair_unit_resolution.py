"""R-2 — sillabusun `chair_unit`-i KAFEDRA olmalıdır, ixtisas yox.

FAZA 27 auditinin tapıntısı: müəllim UI-dan yaradılan sillabusun `chair_unit`-i
`offering.group.parent` təyin olunurdu.  Köçürülmüş strukturda 766 qrupun
766-sının valideyni **ixtisasdır** (`specialty`), yəni `chair_unit` heç vaxt
kafedra olmurdu → kafedra əhatəli `chair_head` sillabusu nə növbədə görürdü,
nə də qərar verə bilirdi (404); faktiki təsdiqçi yalnız dekan qalırdı.

Burada üç şey kilidlənir:

1. qrup → ixtisas → **kafedra** zəncirində yaradılan qaralama kafedraya bağlanır;
2. həmin kafedranın müdiri onu növbədə GÖRÜR və qərar VERƏ bilir; dekan (org
   səviyyəli aktor) əvvəlki kimi görür;
3. kafedra əcdadı OLMAYAN ağacda davranış DƏYİŞMİR (köhnə fallback qalır).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

import pytest

from apps.organizations.models import OrgUnit
from apps.syllabus import services
from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.models import SyllabusVersion
from apps.syllabus.services.units import resolve_chair_unit, resolve_syllabus_chair_unit
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    make_academic_stack,
    make_offering,
    make_org,
)
from core.constants import OrgUnitType, RoleScopeType

User = get_user_model()

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]

pytestmark = pytest.mark.django_db


def _migrated_tree(org, stack, *, code):
    """Köçürülmüş universitetin real forması: fakültə → kafedra → ixtisas → qrup."""
    faculty = OrgUnit.objects.create(
        organization=org,
        name=f"{code}-fakültə",
        slug=f"{org.slug}-{code.lower()}-faculty",
        unit_type=OrgUnitType.FACULTY,
    )
    chair = OrgUnit.objects.create(
        organization=org,
        name=f"{code}-kafedra",
        slug=f"{org.slug}-{code.lower()}-chair2",
        unit_type=OrgUnitType.CHAIR,
        parent=faculty,
    )
    specialty = OrgUnit.objects.create(
        organization=org,
        name=f"{code}-ixtisas",
        slug=f"{org.slug}-{code.lower()}-specialty",
        unit_type=OrgUnitType.SPECIALTY,
        parent=chair,
    )
    group = stack["group"]
    group.parent = specialty
    group.save()  # `OrgUnit.save` materialized path/level-i özü yenidən hesablayır.
    group.refresh_from_db()
    return {"faculty": faculty, "chair": chair, "specialty": specialty, "group": group}


@pytest.fixture()
def world():
    org = make_org("syl-chair-fix")
    teacher = User.objects.create_user("chairfix_t", "chairfix_t@x.test", "pw")
    chair_head = User.objects.create_user("chairfix_ch", "chairfix_ch@x.test", "pw")
    dean = User.objects.create_user("chairfix_dean", "chairfix_dean@x.test", "pw")

    stack = make_academic_stack(org, code="CHF101")
    tree = _migrated_tree(org, stack, code="CHF101")

    activate_member(org, teacher, "teacher", permissions=TEACHER_PERMS)
    activate_member(
        org,
        chair_head,
        "chair_head",
        permissions=CHAIR_PERMS,
        scope_unit=tree["chair"],
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    activate_member(org, dean, "vice_rector", permissions=CHAIR_PERMS, level=95)
    return {"org": org, "stack": stack, "tree": tree, "teacher": teacher, "chair_head": chair_head, "dean": dean}


def _draft_from_offering(world):
    """Müəllim səthinin ötürdüyü DƏYƏR ilə eyni: `offering.group.parent` (= ixtisas)."""
    org, stack = world["org"], world["stack"]
    offering = make_offering(org, stack, world["teacher"])
    actor = services.resolve_actor(world["teacher"], org)
    return services.create_draft(
        organization=org,
        subject=stack["subject"],
        period=stack["period"],
        actor=actor,
        offering=offering,
        program=stack["program"],
        chair_unit=offering.group.parent,
        author=world["teacher"],
        plan_hours=dict(PLAN_HOURS),
    )


# ── 1. Həll ────────────────────────────────────────────────────────────────


def test_resolver_walks_from_specialty_up_to_the_chair(world):
    tree = world["tree"]

    assert resolve_chair_unit(tree["specialty"]) == tree["chair"]
    assert resolve_chair_unit(tree["group"]) == tree["chair"]
    # Kafedranın özü verilsə dəyişmir; kafedra əcdadı yoxdursa dəyər QALIR.
    assert resolve_chair_unit(tree["chair"]) == tree["chair"]
    assert resolve_chair_unit(tree["faculty"]) == tree["faculty"]
    assert resolve_chair_unit(None) is None


def test_draft_created_from_an_offering_binds_to_the_chair_not_the_specialty(world):
    syllabus, _version = _draft_from_offering(world)

    assert syllabus.chair_unit_id == world["tree"]["chair"].pk
    assert syllabus.chair_unit.unit_type == OrgUnitType.CHAIR


# ── 2. Təsdiq səthi ────────────────────────────────────────────────────────


def test_chair_head_sees_and_can_decide_the_submitted_syllabus(world):
    from apps.syllabus.tests.factories import complete_section_data

    org = world["org"]
    _syllabus, version = _draft_from_offering(world)
    teacher_actor = services.resolve_actor(world["teacher"], org)
    for section_id, data in complete_section_data().items():
        if section_id in {"prev", "send"}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=teacher_actor)
    version = services.submit(version=version, actor=teacher_actor)

    chair_actor = services.resolve_actor(world["chair_head"], org)
    dean_actor = services.resolve_actor(world["dean"], org)

    assert [row.pk for row in services.review_queue(organization=org, actor=chair_actor)] == [version.pk]
    assert version.pk in {row.pk for row in services.review_queue(organization=org, actor=dean_actor)}

    approved = services.approve(version=version, actor=chair_actor)
    assert approved.status == "approved"


# ── 3. Mövcud sətirlərin bərpası (idempotent) ──────────────────────────────


def test_repair_command_is_dry_by_default_and_idempotent(world):
    from io import StringIO

    from django.core.management import call_command

    syllabus, _version = _draft_from_offering(world)
    # Defektli vəziyyəti bərpa et: köhnə kod məhz belə yazırdı.
    type(syllabus).objects.filter(pk=syllabus.pk).update(chair_unit=world["tree"]["specialty"])

    dry = StringIO()
    call_command("syllabus_repair_chair_units", stdout=dry)
    syllabus.refresh_from_db()
    assert syllabus.chair_unit_id == world["tree"]["specialty"].pk
    assert "1" in dry.getvalue()

    applied = StringIO()
    call_command("syllabus_repair_chair_units", "--apply", stdout=applied)
    syllabus.refresh_from_db()
    assert syllabus.chair_unit_id == world["tree"]["chair"].pk

    again = StringIO()
    call_command("syllabus_repair_chair_units", "--apply", stdout=again)
    syllabus.refresh_from_db()
    assert syllabus.chair_unit_id == world["tree"]["chair"].pk
    assert "0" in again.getvalue()


def test_new_version_heals_a_stale_specialty_binding(world):
    """Yeni versiya açılışı bağı ÖZÜ kafedraya çəkir (əmr gözləmədən).

    Sahibin qərarı ilə (2026-09-03) qərar əhatəsi KAFEDRA səviyyəsindədir —
    ixtisasa bağlı qalmış köhnə dosyedə kafedra müdiri qərar verə bilməzdi.
    """
    syllabus, version = _draft_from_offering(world)
    type(syllabus).objects.filter(pk=syllabus.pk).update(chair_unit=world["tree"]["specialty"])
    syllabus.refresh_from_db()
    # Versiyanı «açıq» olmayan vəziyyətə gətiririk (keçid axını burada
    # yoxlanılmır — `test_state_machine` onu ayrıca kilidləyir).
    SyllabusVersion.objects.filter(pk=version.pk).update(
        status=SyllabusStatus.REJECTED.value,
        decision_reason="Struktur bağı yoxlanılır.",  # DB check: rədd səbəbi məcburidir
    )

    services.create_next_version(
        syllabus=syllabus,
        actor=services.resolve_actor(world["teacher"], world["org"]),
        kind="major",
    )

    syllabus.refresh_from_db()
    assert syllabus.chair_unit_id == world["tree"]["chair"].pk


# ── 4. Struktur bağı OLMAYAN tenant (köçürülmüş real forma) ────────────────


@pytest.fixture()
def flat_world():
    """Klondakı forma: ixtisas KAFEDRAYA yox, birbaşa FAKÜLTƏYƏ bağlıdır.

    Mənbədə (`speciality.department_id`) 83 ixtisasın 80-i fakültəni göstərir,
    18 kafedranın isə heç bir övladı yoxdur — yəni qrupdan yuxarı qalxmaqla
    kafedra TAPILMIR.  Yeganə real bağ müəllimin öz kafedra üzvlüyüdür.
    """
    org = make_org("syl-chair-flat")
    teacher = User.objects.create_user("flat_t", "flat_t@x.test", "pw")
    chair_head = User.objects.create_user("flat_ch", "flat_ch@x.test", "pw")
    stack = make_academic_stack(org, code="FLT101")

    faculty = OrgUnit.objects.create(
        organization=org, name="FLT-fakültə", slug="flt-faculty", unit_type=OrgUnitType.FACULTY
    )
    chair = OrgUnit.objects.create(
        organization=org, name="FLT-kafedra", slug="flt-chair", unit_type=OrgUnitType.CHAIR, parent=faculty
    )
    specialty = OrgUnit.objects.create(
        organization=org, name="FLT-ixtisas", slug="flt-specialty", unit_type=OrgUnitType.SPECIALTY, parent=faculty
    )
    group = stack["group"]
    group.parent = specialty
    group.save()

    activate_member(org, teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=chair, scope_type=RoleScopeType.UNIT)
    activate_member(
        org,
        chair_head,
        "chair_head",
        permissions=CHAIR_PERMS,
        scope_unit=chair,
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    return {
        "org": org,
        "stack": stack,
        "teacher": teacher,
        "chair_head": chair_head,
        "chair": chair,
        "specialty": specialty,
    }


def test_author_chair_membership_is_used_when_the_tree_has_no_chair_ancestor(flat_world):
    org = flat_world["org"]
    offering = make_offering(org, flat_world["stack"], flat_world["teacher"])
    actor = services.resolve_actor(flat_world["teacher"], org)

    syllabus, _version = services.create_draft(
        organization=org,
        subject=flat_world["stack"]["subject"],
        period=flat_world["stack"]["period"],
        actor=actor,
        offering=offering,
        program=flat_world["stack"]["program"],
        chair_unit=offering.group.parent,
        author=flat_world["teacher"],
        plan_hours=dict(PLAN_HOURS),
    )

    assert syllabus.chair_unit_id == flat_world["chair"].pk
    queue_actor = services.resolve_actor(flat_world["chair_head"], org)
    assert services.has_review_scope(actor=queue_actor) is True


def test_structural_ancestor_wins_over_the_author_membership(world):
    """Ağacda kafedra VARSA üzvlük onu ƏVƏZ ETMİR — struktur həqiqətin özüdür."""
    org = world["org"]
    other_chair = OrgUnit.objects.create(
        organization=org, name="Yad kafedra", slug="syl-chair-fix-other", unit_type=OrgUnitType.CHAIR
    )
    activate_member(
        org,
        world["teacher"],
        "teacher",
        permissions=TEACHER_PERMS,
        scope_unit=other_chair,
        scope_type=RoleScopeType.UNIT,
    )

    resolved = resolve_syllabus_chair_unit(unit=world["tree"]["specialty"], author=world["teacher"], organization=org)

    assert resolved == world["tree"]["chair"]


def test_resolver_keeps_the_given_unit_when_nothing_maps(world):
    """Nə əcdad, nə üzvlük — dəyər DƏYİŞMİR (fail-soft, sahibsiz sillabus yox)."""
    stranger = User.objects.create_user("flat_stranger", "flat_stranger@x.test", "pw")

    resolved = resolve_syllabus_chair_unit(unit=world["tree"]["faculty"], author=stranger, organization=world["org"])

    assert resolved == world["tree"]["faculty"]
