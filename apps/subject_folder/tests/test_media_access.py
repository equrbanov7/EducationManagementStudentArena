"""Qorunan fayllar: kim nəyi endirə bilər (media checker + endirmə view-ları + /media/ marşrutu)."""

from __future__ import annotations

from django.test import Client
from django.urls import reverse

import pytest

from apps.subject_folder import public
from apps.subject_folder.constants import MATERIALS_MEDIA_PREFIX, SUBMISSIONS_MEDIA_PREFIX
from apps.subject_folder.services.media import check_material_media_access, check_submission_media_access
from core import media_policies

from . import factories as f
from .conftest import upload

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 material"


def _client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


@pytest.fixture
def files(ready):
    published = public.create_material(
        ready.folder,
        by_user=ready.teacher,
        kind="file",
        title="Slayd",
        file=upload("slayd.pdf", PDF, "application/pdf"),
        is_published=True,
    )
    hidden = public.create_material(
        ready.folder, by_user=ready.teacher, kind="file", title="Qaralama", file=upload("q.pdf", PDF, "application/pdf")
    )
    attachment = public.add_task_attachment(
        ready.homework, by_user=ready.teacher, file=upload("sert.pdf", PDF, "application/pdf")
    )
    work = public.submit(
        task=ready.homework,
        assignment=ready.assignment,
        student=ready.students[0],
        files=[upload("isim.pdf", b"%PDF-1.4 is", "application/pdf")],
    )
    return {"published": published, "hidden": hidden, "attachment": attachment, "file": work.files.get()}


def test_policies_are_registered_for_both_prefixes():
    assert MATERIALS_MEDIA_PREFIX in media_policies.registered_prefixes()
    assert SUBMISSIONS_MEDIA_PREFIX in media_policies.registered_prefixes()
    assert media_policies.resolve_checker(MATERIALS_MEDIA_PREFIX) is check_material_media_access
    assert media_policies.resolve_checker(SUBMISSIONS_MEDIA_PREFIX) is check_submission_media_access


def test_storage_paths_are_private_randomized_and_org_scoped(ready, files):
    name = files["published"].file.name
    assert name.startswith(f"{MATERIALS_MEDIA_PREFIX}{ready.org.pk}/{ready.folder.pk}/")
    assert "slayd" not in name and files["published"].original_name == "slayd.pdf"
    assert files["file"].file.name.startswith(f"{SUBMISSIONS_MEDIA_PREFIX}{ready.org.pk}/")


def test_material_checker(ready, files):
    student, teacher = ready.students[0], ready.teacher
    stranger_student = f.make_student(ready.org)
    other_org_student = f.make_student(f.make_org())
    published = files["published"].file.name
    hidden = files["hidden"].file.name
    attachment = files["attachment"].file.name
    assert check_material_media_access(student, published)
    assert check_material_media_access(student, attachment)
    assert not check_material_media_access(student, hidden)  # dərc olunmayıb
    assert check_material_media_access(teacher, hidden)
    assert not check_material_media_access(stranger_student, published)
    assert not check_material_media_access(other_org_student, published)
    assert not check_material_media_access(student, f"{MATERIALS_MEDIA_PREFIX}yoxdur.pdf")


def test_submission_checker(ready, files):
    path = files["file"].file.name
    assert check_submission_media_access(ready.students[0], path)
    assert check_submission_media_access(ready.teacher, path)
    assert not check_submission_media_access(ready.students[1], path)  # qrup yoldaşı
    assert not check_submission_media_access(f.make_teacher(ready.org), path)


def test_download_views_serve_attachment_with_safe_headers(ready, files):
    client = _client(ready.students[0], ready.org)
    response = client.get(reverse("subject_folder:material_download", args=[files["published"].pk]))
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment") and "slayd.pdf" in response["Content-Disposition"]
    assert response["X-Content-Type-Options"] == "nosniff" and response["Cache-Control"] == "private, no-store"
    assert b"".join(response.streaming_content) == PDF
    assert client.get(reverse("subject_folder:material_download", args=[files["hidden"].pk])).status_code == 404
    assert (
        client.get(reverse("subject_folder:task_attachment_download", args=[files["attachment"].pk])).status_code == 200
    )
    assert client.get(reverse("subject_folder:submission_file_download", args=[files["file"].pk])).status_code == 200
    other = _client(ready.students[1], ready.org)
    assert other.get(reverse("subject_folder:submission_file_download", args=[files["file"].pk])).status_code == 404
    teacher = _client(ready.teacher, ready.org)
    assert teacher.get(reverse("subject_folder:submission_file_download", args=[files["file"].pk])).status_code == 200


def test_download_requires_login(ready, files):
    response = Client().get(reverse("subject_folder:material_download", args=[files["published"].pk]))
    assert response.status_code == 302 and "login" in response["Location"]


def test_protected_media_route_uses_the_policy(ready, files, settings):
    settings.SERVE_MEDIA = True
    settings.MEDIA_ACCEL_REDIRECT_URL = ""
    settings.OBJECT_STORAGE_ENABLED = False
    path = files["file"].file.name
    owner = _client(ready.students[0], ready.org)
    assert owner.get(f"/media/{path}").status_code == 200
    assert _client(ready.students[1], ready.org).get(f"/media/{path}").status_code == 404
