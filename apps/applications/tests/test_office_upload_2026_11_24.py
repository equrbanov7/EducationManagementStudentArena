"""Müraciətə Word / Excel faylı əlavə etmək (sahib 2026-11-24: «word docx göndərməyə icazə ver»).

Prod-da `.docx` cavabı HTML 400 ilə qayıdırdı — müəllimlər sənədi ZIP-ə qoyub göndərirdi.
"""

from __future__ import annotations

import io
import json
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

import pytest

from apps.applications.services import submit, workflow
from apps.applications.tests.factories import kind_of, make_world

pytestmark = pytest.mark.django_db

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _office_bytes(main_part: str, xml: str) -> bytes:
    """Word-ün özü kimi DEFLATE ilə sıxılmış minimal OOXML paketi."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
            'content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships/>')
        archive.writestr(main_part, xml)
    return buffer.getvalue()


DOCX_BYTES = _office_bytes(
    "word/document.xml",
    '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
    'wordprocessingml/2006/main"><w:body>'
    + "<w:p><w:r><w:t>Dərs yükü</w:t></w:r></w:p>" * 400
    + "</w:body></w:document>",
)
XLSX_BYTES = _office_bytes("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook/>')


@pytest.fixture()
def world():
    return make_world("office")


def _client(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


def _json(response):
    assert response["Content-Type"].startswith("application/json"), response.content[:200]
    return json.loads(response.content.decode())


@pytest.mark.parametrize(
    ("name", "data", "content_type"),
    [
        ("Dərs yükü.docx", DOCX_BYTES, DOCX_TYPE),
        ("ders-yuku.docx", DOCX_BYTES, "application/octet-stream"),
        ("Cədvəl.xlsx", XLSX_BYTES, XLSX_TYPE),
    ],
)
def test_office_file_is_accepted_on_create(world, name, data, content_type):
    client = _client(world["student"], world["organization"])
    response = client.post(
        reverse("applications:create"),
        {
            "kind": "diger",
            "subject": "Word sənədli müraciət",
            "body": "Dərs yükü cədvəlini Word faylı kimi əlavə edirəm, zəhmət olmasa baxın.",
            "files": SimpleUploadedFile(name, data, content_type=content_type),
        },
    )
    payload = _json(response)
    assert payload["ok"] is True, payload
    assert [item["name"] for item in payload["application"]["attachments"]] == [name]


def test_docx_reply_attachment_is_accepted(world):
    application = submit.submit_application(
        organization=world["organization"],
        user=world["student"],
        kind=kind_of(world, "diger"),
        subject="Seçmə fənn bloku",
        body="İxtisas üzrə seçmə fənn blokunu dəyişmək istəyirəm, izah lazımdır.",
    )
    workflow.mark_seen(application=application, user=world["coordinator"])
    client = _client(world["coordinator"], world["organization"])
    response = client.post(
        reverse("applications:action", kwargs={"application_id": application.pk}),
        {
            "action": "add_comment",
            "text": "Siyahı Word faylı kimi əlavə olunur.",
            "files": SimpleUploadedFile("siyahi.docx", DOCX_BYTES, content_type=DOCX_TYPE),
        },
    )
    payload = _json(response)
    assert payload["ok"] is True, payload
