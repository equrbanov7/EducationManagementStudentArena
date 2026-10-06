"""Elan testləri üçün kiçik «universitet».

Struktur: Fakültə F1 → Kafedra A → Qrup G1;  Fakültə F2 → Qrup G2.
Üzvlər: tələbə s1 (G1), tələbə s2 (G2), müəllim t1 (Kafedra A), dekan d1 (F1, ``announcement.manage``
rol şablonundan), sahib (org-wide). İkinci təşkilat B — öz tələbəsi ilə (tenant izolyasiyası).
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.announcements.forms import AnnouncementForm
from apps.announcements.models import Announcement
from apps.announcements.services import manage, snapshot
from apps.applications.services.catalog import seed_catalog
from apps.organizations.models import Membership, Organization, OrgUnit
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
PW = "AnnouncePass123!"


def member(org, username, role_name, *, unit=None):
    user = User.objects.create_user(username, f"{username}@qku.edu.az", PW, first_name="Ad", last_name=username)
    Membership.objects.create(
        user=user, organization=org, role=org.roles.get(name=role_name), scope_unit=unit, is_primary=True, is_active=True
    )
    return user


def _unit(org, name, unit_type, parent=None):
    return OrgUnit.objects.create(
        organization=org, name=name, slug=f"{org.slug}-{name}".lower().replace(" ", "-"), unit_type=unit_type, parent=parent
    )


def _record(org, student, group, program, curriculum):
    StudentAcademicRecord.objects.create(
        organization=org, student=student, program=program, curriculum=curriculum, group=group, admission_year=2025
    )


def build_world(slug: str) -> dict:
    owner = User.objects.create_user(f"{slug}_owner", f"{slug}_owner@qku.edu.az", PW)
    with bypass_rls():
        org = Organization.objects.create(
            name=f"{slug} Univ", slug=slug, org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
        )
        f1 = _unit(org, "Fakulte F1", OrgUnitType.FACULTY)
        chair_a = _unit(org, "Kafedra A", OrgUnitType.CHAIR, parent=f1)
        g1 = _unit(org, "Qrup G1", OrgUnitType.GROUP, parent=chair_a)
        f2 = _unit(org, "Fakulte F2", OrgUnitType.FACULTY)
        g2 = _unit(org, "Qrup G2", OrgUnitType.GROUP, parent=f2)
        program = Program.objects.create(organization=org, code=f"P-{slug}", name="Proqram")
        curriculum = Curriculum.objects.create(organization=org, program=program, admission_year=2025)
        s1 = member(org, f"{slug}_s1", "student")
        s2 = member(org, f"{slug}_s2", "student")
        _record(org, s1, g1, program, curriculum)
        _record(org, s2, g2, program, curriculum)
        t1 = member(org, f"{slug}_t1", "teacher", unit=chair_a)
        dean = member(org, f"{slug}_dean", "dean", unit=f1)
        units, kinds = seed_catalog(org)
    return {
        "org": org,
        "owner": owner,
        "f1": f1,
        "f2": f2,
        "chair_a": chair_a,
        "g1": g1,
        "g2": g2,
        "s1": s1,
        "s2": s2,
        "t1": t1,
        "dean": dean,
        "units": units,
        "kinds": kinds,
    }


class _Req:
    """``save_announcement`` / ``transition`` üçün minimal request (audit + istifadəçi)."""

    def __init__(self, user, org):
        self.user = user
        self.organization = org
        self.META = {}
        self.is_view_as = False


def make_announcement(world, *, author=None, publish=True, **fields) -> Announcement:
    """Forma + servis yolu ilə elan (əhatə yoxlaması daxil)."""
    from apps.announcements.services.access import manage_scope

    org = world["org"]
    author = author or world["owner"]
    data = {
        "title": fields.pop("title", "İmtahan cədvəli dərc olundu"),
        "summary": fields.pop("summary", "Qış sessiyasının cədvəli"),
        "body": fields.pop("body", "Ətraflı məlumat aşağıdadır."),
        "category": fields.pop("category", "exam"),
        "priority": str(fields.pop("priority", 0)),
        "audience_families": fields.pop("families", ["students"]),
        "audience_units": ",".join(str(unit) for unit in fields.pop("units", [])),
        "apply_mode": fields.pop("apply_mode", "none"),
    }
    for key in ("show_as_popup", "is_pinned"):
        if fields.pop(key, False):
            data[key] = "1"
    for key in ("publish_at", "expires_at", "deadline_at"):
        value = fields.pop(key, None)
        if value is not None:
            data[key] = timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")
    data.update({key: str(value) for key, value in fields.items()})
    with bypass_rls():
        form = AnnouncementForm(data, organization=org)
        assert form.is_valid(), form.errors
        request = _Req(author, org)
        scope = manage_scope(author, org)
        announcement = manage.save_announcement(request, org, scope, form.cleaned_data)
        if publish:
            manage.transition(request, org, scope, announcement, "publish")
        announcement.refresh_from_db()
        org.refresh_from_db()
        snapshot.read_snapshot(org)
    return announcement


def client_for(org, user):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def days(n):
    return timezone.now() + datetime.timedelta(days=n)
