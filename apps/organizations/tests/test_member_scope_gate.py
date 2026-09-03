"""QA B-2 (2026-08-28): üzv siyahısının scope qapısı.

Tapıntı: ``scope_unit``-i TƏYİN EDİLMƏMİŞ unit-rolu (dekan, kafedra müdiri)
``build_organization_members_context``-də filtrsiz keçir və BÜTÜN təşkilatın
üzvlərini (rektor/sahib daxil, ad+email+rol) görürdü.  Sahəsi müəyyən olmayan
rol heç nə görməməlidir; org-səviyyəli rollar (HR, org_admin) təsirlənmir.
"""

from django.contrib.auth import get_user_model
from django.test import RequestFactory

import pytest

from apps.organizations.models import Membership, Organization, Role
from apps.organizations.views.org_admin.context import build_organization_members_context
from core.constants import OrganizationType, RoleScopeType

pytestmark = pytest.mark.django_db

User = get_user_model()


def _org(owner):
    return Organization.objects.create(
        name="Scope Test University",
        slug="scope-test-university",
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )


def _role(org, name, level, scope_type):
    role, _created = Role.objects.get_or_create(
        organization=org,
        name=name,
        defaults={
            "display_name": name.title(),
            "level": level,
            "scope_type": scope_type,
            "permissions": ["member.view"],
        },
    )
    Role.objects.filter(pk=role.pk).update(is_active=True, level=level, scope_type=scope_type)
    role.refresh_from_db()
    return role


def _member(org, username, role, scope_unit=None):
    user = User.objects.create_user(username, f"{username}@example.test", "test-only")
    Membership.objects.create(organization=org, user=user, role=role, scope_unit=scope_unit, is_active=True)
    return user


def _members_seen(user, org):
    request = RequestFactory().get("/organizations/scope-test-university/members/")
    request.user = user
    request.organization = org
    request.org_memberships = list(Membership.objects.filter(user=user, organization=org, is_active=True))
    context = build_organization_members_context(request, org)
    return len(list(context["members"]))


def test_unit_role_without_scope_unit_sees_nobody():
    """Dekan/kafedra müdiri sahəsi təyin edilməyibsə üzv siyahısı BOŞ olmalıdır."""
    owner = User.objects.create_user("scope_owner", "scope-owner@example.test", "test-only")
    org = _org(owner)
    dean_role = _role(org, "dean", 80, RoleScopeType.UNIT)
    _member(org, "scope_other_member", _role(org, "teacher", 50, RoleScopeType.COURSE))
    dean = _member(org, "scope_dean", dean_role)  # scope_unit=None

    assert _members_seen(dean, org) == 0


def test_organization_role_without_scope_unit_still_sees_the_org():
    """HR kimi ORGANIZATION scope-lu rol köhnə davranışı saxlayır (regresiya qoruması)."""
    owner = User.objects.create_user("scope_owner2", "scope-owner2@example.test", "test-only")
    org = _org(owner)
    hr_role = _role(org, "hr", 65, RoleScopeType.ORGANIZATION)
    _member(org, "scope_member_a", _role(org, "teacher", 50, RoleScopeType.COURSE))
    hr = _member(org, "scope_hr", hr_role)

    # HR özü + müəllim + (sahib üzvlüyü varsa o da) — sıfırdan böyük olmalıdır.
    assert _members_seen(hr, org) >= 2


def test_owner_sees_every_member():
    """Təşkilat sahibi org-wide qalır."""
    owner = User.objects.create_user("scope_owner3", "scope-owner3@example.test", "test-only")
    org = _org(owner)
    _member(org, "scope_member_b", _role(org, "teacher", 50, RoleScopeType.COURSE))

    assert _members_seen(owner, org) >= 1
