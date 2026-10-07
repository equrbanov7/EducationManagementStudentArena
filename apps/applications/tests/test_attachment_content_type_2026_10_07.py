"""Təhlükəsizlik auditi 2026-10-07 — müraciət sənədinin ``Content-Type``-ı klient bəyanından gəlmir.

``attachment_download`` saxlanmış ``content_type``-ı (yükləmədə brauzerin bəyan
etdiyi dəyər) qaytarırdı. İndi tip yalnız adın uzantısından (ağ siyahı) çıxarılır.
"""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

import pytest

from apps.applications.models import ApplicationAttachment
from apps.applications.services import submit
from apps.applications.tests.factories import kind_of, make_world

pytestmark = pytest.mark.django_db

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<</Root 1 0 R>>\n%%EOF\n"


@pytest.fixture()
def world():
    return make_world("ctype07")


def _client(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


def _submit_with(world, upload):
    return submit.submit_application(
        organization=world["organization"],
        user=world["student"],
        kind=kind_of(world, "diger"),
        subject="Sənəd tipi yoxlaması",
        body="Sənədin endirmə tipinin klientin bəyanından asılı olmadığını yoxlayan mətn.",
        files=[upload],
    )


def _download(world, application, attachment):
    url = reverse(
        "applications:attachment_download",
        kwargs={"application_id": application.pk, "attachment_id": attachment.pk},
    )
    return _client(world["student"], world["organization"]).get(url)


def test_html_claim_on_pdf_is_not_echoed(world):
    application = _submit_with(world, SimpleUploadedFile("arayis.pdf", PDF_BYTES, content_type="text/html"))
    attachment = ApplicationAttachment.objects.get(application=application)
    assert attachment.content_type == "application/pdf"

    response = _download(world, application, attachment)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert "attachment" in response["Content-Disposition"]
    assert response["X-Content-Type-Options"] == "nosniff"


def test_legacy_stored_claim_is_ignored_on_download(world):
    application = _submit_with(world, SimpleUploadedFile("arayis.pdf", PDF_BYTES, content_type="application/pdf"))
    attachment = ApplicationAttachment.objects.get(application=application)
    # Düzəlişdən ƏVVƏL yazılmış sətir: klient bəyanı saxlanıb.
    ApplicationAttachment.objects.filter(pk=attachment.pk).update(content_type="text/html")

    response = _download(world, application, attachment)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["X-Content-Type-Options"] == "nosniff"
