"""2026-11-10 (sahib): prorektor seçimində vəzifə görünür; brauzerin qəribə MIME-i real sənədi rədd etmir."""

import io
import zipfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

import pytest

from apps.accounts.models import UserProfile
from apps.applications.constants import ALLOWED_ATTACHMENT_EXTENSIONS, MAX_ATTACHMENT_MB
from apps.applications.services.recipients import destination_payload
from core.upload_security import validate_uploaded_file

from .factories import MANAGE, add_member, make_user, make_world

pytestmark = pytest.mark.django_db


def _xlsx_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    return buffer.getvalue()


def test_recipient_payload_carries_membership_title_then_staff_position():
    world = make_world("prorector-titles")
    org = world["organization"]
    vice_a, vice_b, vice_c = make_user("vice_ta"), make_user("vice_tb"), make_user("vice_tc")
    membership = add_member(org, vice_a, "vice_rector", permissions=MANAGE)
    membership.title = "Tədris işləri üzrə prorektor"
    membership.save(update_fields=["title"])
    add_member(org, vice_b, "vice_rector", permissions=MANAGE)
    UserProfile.objects.update_or_create(
        user=vice_b, defaults={"staff_position": "Elm və innovasiyalar üzrə prorektor"}
    )
    add_member(org, vice_c, "vice_rector", permissions=MANAGE)
    vice_d = make_user("vice_td")
    add_member(org, vice_d, "vice_rector", permissions=MANAGE)
    UserProfile.objects.update_or_create(user=vice_d, defaults={"staff_position": "Ümumi işlər üzrə"})

    unit = world["kinds"]["prorektor"].target_unit
    titles = {row["id"]: row["title"] for row in destination_payload(unit)}
    assert titles[str(vice_a.pk)] == "Tədris işləri üzrə prorektor"
    assert titles[str(vice_b.pk)] == "Elm və innovasiyalar üzrə prorektor"
    assert titles[str(vice_c.pk)] == ""
    assert titles[str(vice_d.pk)] == "Ümumi işlər üzrə prorektor"


@pytest.mark.parametrize(
    ("name", "content", "client_type"),
    [
        ("cedvel.xlsx", "xlsx", "application/octet-stream"),
        ("cedvel.xlsx", "xlsx", "application/haansoftxlsx"),
        ("erize.pdf", b"%PDF-1.7\n", "application/x-pdf"),
        ("erize.pdf", b"%PDF-1.7\n", "application/octet-stream"),
        ("teqdimat.pptx", "xlsx", "application/octet-stream"),
    ],
)
def test_real_document_with_odd_browser_mime_is_accepted(name, content, client_type):
    data = _xlsx_bytes() if content == "xlsx" else content
    upload = SimpleUploadedFile(name, data, content_type=client_type)
    validate_uploaded_file(upload, allowed_extensions=ALLOWED_ATTACHMENT_EXTENSIONS, max_size_mb=MAX_ATTACHMENT_MB)
    # allow-list-siz ümumi çağırış da (köhnə sahələr) eyni qaydanı alır
    validate_uploaded_file(SimpleUploadedFile(name, data, content_type=client_type))


def test_unknown_binary_and_fake_content_are_still_rejected():
    with pytest.raises(ValidationError):
        validate_uploaded_file(SimpleUploadedFile("data.bin", b"blob", content_type="application/octet-stream"))
    with pytest.raises(ValidationError):
        validate_uploaded_file(
            SimpleUploadedFile("fake.pdf", b"not a pdf", content_type="application/octet-stream"),
            allowed_extensions=ALLOWED_ATTACHMENT_EXTENSIONS,
        )
    with pytest.raises(ValidationError):
        validate_uploaded_file(SimpleUploadedFile("x.pdf", b"MZ\x90\x00", content_type="application/octet-stream"))
