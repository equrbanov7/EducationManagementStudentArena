"""Təhlükəsizlik auditi 2026-10-07 SEC-06 — İKT/RİM rəhbərinin «inzibatçı» statusu yalnız ÖZ təşkilatında.

``lookups.is_org_admin(user, organization)`` ``user.is_ikt_rehber``-ə (AKTİV təşkilatdakı
rol) baxırdı, ``organization``-a yox. ``/media/subject_folder/...`` siyasəti faylı yol ilə
(təşkilat süzgəcsiz) tapır, ona görə B-nin İKT rəhbəri A-nın tələbə işinə / materialına
tətbiq qatında «inzibatçı» kimi buraxılırdı — yalnız DB-nin RLS qatı dayandırırdı
(2026-09-28 auditində PLAUSIBLE qeydi).
"""

from __future__ import annotations

from django.test import Client

import pytest

from apps.subject_folder import public
from apps.subject_folder.services import lookups

from . import factories as f
from .conftest import upload

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 sec07"


def _client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def _ikt_head(organization):
    user = f.make_user("ikt")
    f.activate_member(organization, user, "ikt_rehber", permissions=["*"], level=95)
    return user


@pytest.fixture
def submission_path(ready):
    work = public.submit(
        task=ready.homework,
        assignment=ready.assignment,
        student=ready.students[0],
        files=[upload("isim.pdf", PDF, "application/pdf")],
    )
    return work.files.get().file.name


def test_is_org_admin_is_bound_to_the_object_organization(ready):
    other_org = f.make_org()
    foreign_head = _ikt_head(other_org)
    foreign_head.set_active_organization_context(other_org)

    assert lookups.is_org_admin(foreign_head, other_org) is True
    assert lookups.is_org_admin(foreign_head, ready.org) is False


def test_foreign_ikt_head_cannot_read_submission_through_media(ready, submission_path, settings):
    settings.SERVE_MEDIA = True
    settings.MEDIA_ACCEL_REDIRECT_URL = ""
    settings.OBJECT_STORAGE_ENABLED = False
    other_org = f.make_org()
    foreign_head = _ikt_head(other_org)

    assert _client(foreign_head, other_org).get(f"/media/{submission_path}").status_code == 404


def test_own_ikt_head_still_reads_submission_through_media(ready, submission_path, settings):
    settings.SERVE_MEDIA = True
    settings.MEDIA_ACCEL_REDIRECT_URL = ""
    settings.OBJECT_STORAGE_ENABLED = False
    own_head = _ikt_head(ready.org)

    assert _client(own_head, ready.org).get(f"/media/{submission_path}").status_code == 200
