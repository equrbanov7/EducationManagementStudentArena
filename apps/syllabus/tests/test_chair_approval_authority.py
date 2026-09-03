"""SAHİBİN QƏRARI (2026-09-03): sillabusu TƏSDİQ EDƏN kafedra müdiridir.

Konteks
-------
FAZA 27 auditi (R-2) göstərdi ki, `chair_unit` ixtisasa bağlandığı üçün kafedra
müdiri sillabusu praktikada görmürdü; de-fakto təsdiqçi DEKAN idi, çünki
fakültə scope-u alt-ağacdakı bütün kafedraları örtür (`user_scope_covers_unit`
alt-ağac yoxlamasıdır).  Sahib qərar verdi: təsdiq/düzəliş/rədd YALNIZ kafedra
müdirinindir.

Burada dörd şey kilidlənir:

1. **Rol kataloqu** — `dean` qərar açarlarını itirir, `view`+`review` qalır;
   `chair_head` tam dəsti saxlayır; `rector`/`vice_rector`/`ikt_rehber`
   override-i qalır.
2. **Əhatə KAFEDRA SƏVİYYƏSİNDƏDİR** — qərar açarı ƏLİNDƏ OLAN fakültə-scope
   aktor da (məs. köhnə tenant-da əl ilə verilmiş açar) fail-closed dayanır.
3. **Başqa kafedranın müdiri** öz kafedrasından kənarda qərar verə bilmir.
4. **Bildiriş** kafedra müdirinə gedir; müdir yoxdursa dekana AÇIQ QEYDLƏ gedir
   (səssiz düşmə YOXDUR).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

import pytest

from apps.organizations.models import OrgUnit
from apps.syllabus import services
from apps.syllabus.services.notifications import FALLBACK_NOTE
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)
from core.constants import OrgUnitType, RoleScopeType

User = get_user_model()

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]
#: Sahibin qərarından SONRAKI dekan dəsti — qərar açarı YOXDUR.
DEAN_PERMS = ["syllabus.view", "syllabus.review"]
#: Köhnə (miqrasiyadan əvvəlki) dekan dəsti — açar var, ƏHATƏ olmamalıdır.
LEGACY_DEAN_PERMS = list(CHAIR_PERMS)

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    """Bir fakültə, iki kafedra; hər kafedrada müəllim + müdir; üstdə dekan/RİM."""
    org = make_org("syl-authority")
    faculty = OrgUnit.objects.create(
        organization=org,
        name="Mühəndislik fakültəsi",
        slug=f"{org.slug}-faculty",
        unit_type=OrgUnitType.FACULTY,
    )
    stack_a = make_academic_stack(org, code="AUA101")
    stack_b = make_academic_stack(org, code="AUB202")
    for stack in (stack_a, stack_b):
        chair = stack["chair"]
        chair.parent = faculty
        chair.save()
        chair.refresh_from_db()

    teacher = User.objects.create_user("au_teacher", "au_teacher@x.test", "pw")
    chair_a = User.objects.create_user("au_chair_a", "au_chair_a@x.test", "pw")
    chair_b = User.objects.create_user("au_chair_b", "au_chair_b@x.test", "pw")
    dean = User.objects.create_user("au_dean", "au_dean@x.test", "pw")
    legacy_dean = User.objects.create_user("au_legacy_dean", "au_legacy_dean@x.test", "pw")
    rim = User.objects.create_user("au_rim", "au_rim@x.test", "pw")

    activate_member(org, teacher, "teacher", permissions=TEACHER_PERMS)
    for user, name, chair in ((chair_a, "chair_head", stack_a["chair"]), (chair_b, "chair_head_b", stack_b["chair"])):
        activate_member(
            org, user, name, permissions=CHAIR_PERMS, scope_unit=chair, level=70, scope_type=RoleScopeType.UNIT
        )
    activate_member(
        org, dean, "dean", permissions=DEAN_PERMS, scope_unit=faculty, level=80, scope_type=RoleScopeType.UNIT
    )
    activate_member(
        org,
        legacy_dean,
        "dean_legacy",
        permissions=LEGACY_DEAN_PERMS,
        scope_unit=faculty,
        level=80,
        scope_type=RoleScopeType.UNIT,
    )
    activate_member(org, rim, "ikt_rehber", permissions=["syllabus.*"], level=88)

    return {
        "org": org,
        "faculty": faculty,
        "stack_a": stack_a,
        "stack_b": stack_b,
        "teacher": teacher,
        "chair_a": chair_a,
        "chair_b": chair_b,
        "dean": dean,
        "legacy_dean": legacy_dean,
        "rim": rim,
    }


def _actor(user, org):
    return services.resolve_actor(user, org)


def _submitted(world, stack=None):
    """Tam doldurulmuş, TƏSDİQƏ GÖNDƏRİLMİŞ versiya."""
    org = world["org"]
    stack = stack or world["stack_a"]
    actor = _actor(world["teacher"], org)
    offering = make_offering(org, stack, world["teacher"])
    _syllabus, version = services.create_draft(
        organization=org,
        subject=stack["subject"],
        period=stack["period"],
        actor=actor,
        offering=offering,
        program=stack["program"],
        chair_unit=stack["chair"],
        author=world["teacher"],
        plan_hours=dict(PLAN_HOURS),
    )
    for section_id, data in complete_section_data().items():
        if section_id in {"prev", "send"}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=actor)
    return services.submit(version=version, actor=actor)


def _decisions(version, actor):
    """Üç qərar keçidinin hər birini ayrı-ayrı sınayır."""
    return (
        lambda: services.approve(version=version, actor=actor),
        lambda: services.request_revision(version=version, actor=actor, reason="Qiymətləndirmə bölməsi natamamdır."),
        lambda: services.reject(version=version, actor=actor, reason="Sillabus universitet siyasətinə uyğun deyil."),
    )


# ── 1. Rol kataloqu ────────────────────────────────────────────────────────


def _role(name: str) -> dict:
    from apps.organizations.default_roles_university import UNIVERSITY_ROLES

    return next(role for role in UNIVERSITY_ROLES if role["name"] == name)


def test_dean_default_role_keeps_reading_but_loses_every_decision_key():
    permissions = _role("dean")["permissions"]

    assert "syllabus.view" in permissions
    assert "syllabus.review" in permissions
    for decision in ("syllabus.approve", "syllabus.revise", "syllabus.reject", "syllabus.edit"):
        assert decision not in permissions, decision


def test_chair_head_default_role_still_owns_the_decision():
    permissions = _role("chair_head")["permissions"]

    for decision in ("syllabus.approve", "syllabus.revise", "syllabus.reject"):
        assert decision in permissions, decision


def test_org_wide_overrides_are_untouched():
    from core.permissions import has_permission

    for name in ("rector", "vice_rector", "ikt_rehber"):
        permissions = _role(name)["permissions"]
        assert has_permission(permissions, "syllabus.approve"), name


# ── 2. Əhatə kafedra səviyyəsindədir ───────────────────────────────────────


def test_chair_head_of_the_owning_chair_can_decide(world):
    version = _submitted(world)

    approved = services.approve(version=version, actor=_actor(world["chair_a"], world["org"]))

    assert approved.status == "approved"


def test_dean_without_decision_keys_is_denied(world):
    version = _submitted(world)
    actor = _actor(world["dean"], world["org"])

    for call in _decisions(version, actor):
        with pytest.raises(TransitionDenied) as denied:
            call()
        assert denied.value.code == "transition.permission_denied"


def test_dean_holding_legacy_decision_keys_is_still_out_of_chair_scope(world):
    """Açar qalıbsa da (köhnə tenant, əl ilə verilmiş icazə) ƏHATƏ dayandırır."""
    version = _submitted(world)
    actor = _actor(world["legacy_dean"], world["org"])

    for call in _decisions(version, actor):
        with pytest.raises(TransitionDenied) as denied:
            call()
        assert denied.value.code == "transition.out_of_scope"


def test_chair_head_of_another_chair_is_denied(world):
    version = _submitted(world)
    actor = _actor(world["chair_b"], world["org"])

    for call in _decisions(version, actor):
        with pytest.raises(TransitionDenied) as denied:
            call()
        assert denied.value.code == "transition.out_of_scope"


def test_org_wide_actor_keeps_the_audited_override(world):
    version = _submitted(world)

    approved = services.approve(version=version, actor=_actor(world["rim"], world["org"]))

    assert approved.status == "approved"


def test_dean_can_still_read_and_open_the_review(world):
    """Dekan növbəni AÇIR — qərar açarı yoxdur, oxu bağlanmır."""
    version = _submitted(world)
    actor = _actor(world["dean"], world["org"])

    assert services.can_view(actor, version.syllabus) is True
    opened = services.start_review(version=version, actor=actor)
    assert opened.status == "review"


def test_available_actions_offer_no_decision_button_to_the_dean(world):
    version = _submitted(world)

    dean_actions = services.available_actions(version=version, actor=_actor(world["dean"], world["org"]))
    chair_actions = services.available_actions(version=version, actor=_actor(world["chair_a"], world["org"]))

    assert "approve" not in dean_actions
    assert "approve" in chair_actions


def test_decision_scope_flag_separates_the_dean_from_the_chair_head(world):
    org = world["org"]

    assert services.has_decision_scope(_actor(world["chair_a"], org)) is True
    assert services.has_decision_scope(_actor(world["dean"], org)) is False
    assert services.has_decision_scope(_actor(world["legacy_dean"], org)) is False
    assert services.has_decision_scope(_actor(world["rim"], org)) is True


# ── 3. Bildirişlər ─────────────────────────────────────────────────────────


def test_submit_notifies_the_chair_head_not_the_dean(django_capture_on_commit_callbacks, world):
    from apps.notifications.models import InAppNotification

    with django_capture_on_commit_callbacks(execute=True):
        _submitted(world)

    assert InAppNotification.objects.filter(recipient=world["chair_a"], metadata__event="syllabus_submit").count() == 1
    assert InAppNotification.objects.filter(recipient=world["dean"], metadata__event="syllabus_submit").count() == 0


def test_fallback_to_dean_carries_an_explicit_note(django_capture_on_commit_callbacks, world):
    """Kafedra müdiri yoxdursa bildiriş İTMİR — dekana izahla gedir."""
    from apps.notifications.models import InAppNotification

    with django_capture_on_commit_callbacks(execute=True):
        _submitted(world, stack=world["stack_b"])
    # stack_b-nin müdiri var (chair_b) — onu deaktiv edib fallback yolunu açırıq.
    from apps.organizations.models import Membership

    Membership.objects.filter(user=world["chair_b"]).update(is_active=False)
    InAppNotification.objects.all().delete()

    stack_c = make_academic_stack(world["org"], code="AUC303")
    chair_c = stack_c["chair"]
    chair_c.parent = world["faculty"]
    chair_c.save()
    with django_capture_on_commit_callbacks(execute=True):
        _submitted(world, stack=stack_c)

    note = InAppNotification.objects.filter(recipient=world["dean"], metadata__event="syllabus_submit").first()
    assert note is not None
    assert str(FALLBACK_NOTE) in note.message
