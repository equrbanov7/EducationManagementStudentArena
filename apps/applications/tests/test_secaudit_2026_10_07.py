"""Təhlükəsizlik auditi 2026-10-07 SEC-04 — daxili qeydin sənədi müraciət sahibinə sızmır.

Daxili qeyd (``is_internal=True``) «emalçı sirridir»: zaman xəttində sahibə göstərilmir.
Amma həmin qeydə qoşulan sənəd detalın ÜMUMİ «Əlavə olunan sənədlər» siyahısına
(``detail_payload["attachments"]``) düşür, endirmə uc nöqtəsi və ``/media/applications/``
siyasəti isə yalnız müraciətin ``can_view``-unu yoxlayırdı — sahib daxili sənədin adını
görür və onu endirə bilirdi.
"""

from __future__ import annotations

import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

import pytest

from apps.applications.models import ApplicationAttachment
from apps.applications.services import submit, workflow
from apps.applications.tests.factories import kind_of, make_world
from core.media_policies import check_application_attachment_access

pytestmark = pytest.mark.django_db

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<</Root 1 0 R>>\n%%EOF\n"


@pytest.fixture()
def world():
    return make_world("sec07")


@pytest.fixture()
def application(world):
    return submit.submit_application(
        organization=world["organization"],
        user=world["student"],
        kind=kind_of(world, "diger"),
        subject="Daxili sənəd yoxlaması",
        body="Daxili qeydə qoşulan sənədin sahibə görünməməsi üçün kifayət qədər uzun mətn.",
    )


def _client(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


def _detail(client, application):
    response = client.get(reverse("applications:detail", kwargs={"application_id": application.pk}))
    return json.loads(response.content.decode())["application"]


@pytest.fixture()
def internal_attachment(world, application):
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.add_comment(
        application=application,
        user=world["coordinator"],
        text="Daxili qeyd — sahibə görünmür",
        is_internal=True,
        files=[SimpleUploadedFile("daxili-arayis.pdf", PDF_BYTES, content_type="application/pdf")],
    )
    return ApplicationAttachment.objects.get(application=application, event__is_internal=True)


def _download_url(application, attachment):
    return reverse(
        "applications:attachment_download",
        kwargs={"application_id": application.pk, "attachment_id": attachment.pk},
    )


def test_sender_does_not_see_internal_attachment_in_detail(world, application, internal_attachment):
    payload = _detail(_client(world["student"], world["organization"]), application)
    names = {item["name"] for item in payload["attachments"]}
    assert "daxili-arayis.pdf" not in names
    assert payload["attachment_count"] == 0


def test_sender_cannot_download_internal_attachment(world, application, internal_attachment):
    client = _client(world["student"], world["organization"])
    assert client.get(_download_url(application, internal_attachment)).status_code == 404


def test_sender_cannot_read_internal_attachment_through_media(world, application, internal_attachment):
    assert check_application_attachment_access(world["student"], internal_attachment.file.name) is False


def test_handler_keeps_full_access_to_internal_attachment(world, application, internal_attachment):
    client = _client(world["coordinator"], world["organization"])
    names = {item["name"] for item in _detail(client, application)["attachments"]}
    assert "daxili-arayis.pdf" in names
    assert client.get(_download_url(application, internal_attachment)).status_code == 200
    assert check_application_attachment_access(world["coordinator"], internal_attachment.file.name) is True


def test_sender_still_downloads_public_reply_attachment(world, application):
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.add_comment(
        application=application,
        user=world["coordinator"],
        text="Açıq cavab — sənəd əlavədədir",
        files=[SimpleUploadedFile("cavab.pdf", PDF_BYTES, content_type="application/pdf")],
    )
    attachment = ApplicationAttachment.objects.get(application=application, original_name="cavab.pdf")
    client = _client(world["student"], world["organization"])
    assert "cavab.pdf" in {item["name"] for item in _detail(client, application)["attachments"]}
    assert client.get(_download_url(application, attachment)).status_code == 200
    assert check_application_attachment_access(world["student"], attachment.file.name) is True
