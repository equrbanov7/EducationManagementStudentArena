"""Müraciət limitləri (sahib 2026-11-04) — sənəd sayı/ölçüsü/tipi və gündəlik müraciət limiti.

Sahib: «müraciət panelində word, pdf, şəkil və s. sənəd göndərmə limitini artır; bir gündə müraciət göndərmə
limitini də artır, max 5-10 olsun».

Kilidlənən qaydalar:

* bir əməldə 10 fayl qəbul olunur, 11-ci rədd edilir (səssizcə atılmır);
* bir fayl ən çox 25 MB; köhnə Word (``.doc``) və Excel (``.xls``/``.xlsx``) məzmun imzası ilə qəbul olunur,
  imzası yoxlanmayan ``.heic``/``.txt`` qəbul olunmur;
* bir istifadəçi gündə ən çox N müraciət (``applications.daily_limit``, defolt 10) — limit dolanda
  ``TransitionDenied("limit.daily")`` və API 400 + aydın mətn; ertəsi gün yenə açıqdır; silinmiş müraciət sayılmır;
* «Sistem tənzimləmələri»ndəki dəyər (RİM) limiti dəyişir; RİM emalçısı limitdən azaddır.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

import pytest

from apps.accounts.models import RuntimeSetting
from apps.applications.constants import ALLOWED_ATTACHMENT_EXTENSIONS, MAX_ATTACHMENT_MB, MAX_ATTACHMENTS_PER_ACTION
from apps.applications.models import Application, ApplicationAttachment
from apps.applications.services import submit
from apps.applications.state_machine import TransitionDenied
from apps.applications.tests.factories import kind_of, make_world
from core import runtime_settings as rs
from core.runtime_settings_applications import KEY_DAILY_LIMIT, daily_limit
from core.upload_security import validate_uploaded_file

pytestmark = pytest.mark.django_db

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<</Root 1 0 R>>\n%%EOF\n"
OLE_HEADER = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "app-limits"}}


@pytest.fixture()
def world():
    return make_world("applim")


def _pdf(index):
    return SimpleUploadedFile(f"sened-{index}.pdf", PDF_BYTES, content_type="application/pdf")


def _submit(world, index=0, *, user="student", files=None):
    return submit.submit_application(
        organization=world["organization"],
        user=world[user],
        kind=kind_of(world, "diger"),
        subject=f"Gündəlik limit {index}",
        body=f"Gündəlik müraciət limitini yoxlayan kifayət qədər uzun mətn nömrə {index}.",
        files=files,
    )


def _client(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


# ── Sənəd hədləri ─────────────────────────────────────────────────────────────


def test_new_attachment_limits_are_ten_files_of_50_mb():
    # 2026-11-10 (sahib): 25 → 50 MB, PowerPoint əlavə olundu.
    assert (MAX_ATTACHMENTS_PER_ACTION, MAX_ATTACHMENT_MB) == (10, 50)
    assert {".ppt", ".pptx", ".gif"} <= ALLOWED_ATTACHMENT_EXTENSIONS
    assert {".doc", ".xls", ".xlsx", ".docx", ".pdf", ".zip"} <= ALLOWED_ATTACHMENT_EXTENSIONS
    # Məzmunu validator-da yoxlanmayan tiplər QƏSDƏN əlavə olunmayıb.
    assert not {".heic", ".txt"} & ALLOWED_ATTACHMENT_EXTENSIONS


def test_ten_files_in_one_submission_are_accepted(world):
    application = _submit(world, files=[_pdf(i) for i in range(10)])
    assert ApplicationAttachment.objects.filter(application=application).count() == 10


def test_eleven_files_are_rejected_not_silently_dropped(world):
    with pytest.raises(ValidationError) as excinfo:
        _submit(world, files=[_pdf(i) for i in range(11)])
    assert "10" in excinfo.value.message_dict["files"][0]
    assert not Application.objects.filter(organization=world["organization"]).exists()


def test_file_over_50_mb_is_rejected(world):
    big = SimpleUploadedFile(
        "boyuk.pdf", PDF_BYTES + b"0" * (50 * 1024 * 1024 + 1 - len(PDF_BYTES)), content_type="application/pdf"
    )
    with pytest.raises(ValidationError) as excinfo:
        _submit(world, files=[big])
    assert "50 MB" in str(excinfo.value)


def test_file_of_exactly_50_mb_passes_the_field_validator():
    exact = SimpleUploadedFile(
        "tam.pdf", PDF_BYTES + b"0" * (50 * 1024 * 1024 - len(PDF_BYTES)), content_type="application/pdf"
    )
    validate_uploaded_file(exact, allowed_extensions=ALLOWED_ATTACHMENT_EXTENSIONS, max_size_mb=MAX_ATTACHMENT_MB)


@pytest.mark.parametrize(
    ("name", "content_type"),
    [
        ("erize.doc", "application/msword"),
        ("cedvel.xls", "application/vnd.ms-excel"),
    ],
)
def test_legacy_office_files_with_ole_signature_are_accepted(world, name, content_type):
    upload = SimpleUploadedFile(name, OLE_HEADER, content_type=content_type)
    application = _submit(world, files=[upload])
    attachment = ApplicationAttachment.objects.get(application=application)
    assert attachment.content_type == content_type


def test_xlsx_must_carry_a_zip_signature(world):
    fake = SimpleUploadedFile(
        "cedvel.xlsx",
        b"<html><script>alert(1)</script></html>",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    with pytest.raises(ValidationError):
        _submit(world, files=[fake])


def test_heic_is_not_accepted(world):
    with pytest.raises(ValidationError):
        _submit(world, files=[SimpleUploadedFile("foto.heic", b"\x00" * 32, content_type="image/heic")])


# ── Gündəlik müraciət limiti ────────────────────────────────────────────────


@override_settings(APPLICATIONS_DAILY_LIMIT=3)
def test_daily_limit_denies_the_next_application(world):
    for index in range(3):
        _submit(world, index)
    with pytest.raises(TransitionDenied) as excinfo:
        _submit(world, 99)
    assert excinfo.value.code == "limit.daily"
    assert excinfo.value.params == {"limit": 3}
    assert "3" in str(excinfo.value)
    assert Application.objects.filter(created_by=world["student"]).count() == 3


@override_settings(APPLICATIONS_DAILY_LIMIT=2)
def test_denied_submission_does_not_consume_a_number(world):
    first, second = _submit(world, 1), _submit(world, 2)
    with pytest.raises(TransitionDenied):
        _submit(world, 3)
    third = _submit(world, 4, user="teacher")
    numbers = [first.number, second.number, third.number]
    assert numbers == ["MR-000001", "MR-000002", "MR-000003"]


@override_settings(APPLICATIONS_DAILY_LIMIT=2)
def test_limit_is_per_user(world):
    _submit(world, 1)
    _submit(world, 2)
    _submit(world, 3, user="teacher")  # başqa istifadəçinin limiti ayrıdır


@override_settings(APPLICATIONS_DAILY_LIMIT=2)
def test_next_day_is_open_again(world):
    _submit(world, 1)
    _submit(world, 2)
    yesterday = timezone.now() - timedelta(days=1)
    Application.objects.filter(created_by=world["student"]).update(created_at=yesterday)
    assert submit.submitted_today(world["organization"], world["student"]) == 0
    _submit(world, 3)


@override_settings(APPLICATIONS_DAILY_LIMIT=2)
def test_deleted_applications_are_not_counted(world):
    _submit(world, 1)
    _submit(world, 2)
    Application.objects.filter(created_by=world["student"]).update(deleted_at=timezone.now())
    _submit(world, 3)


@override_settings(APPLICATIONS_DAILY_LIMIT=1)
def test_rim_responder_is_exempt(world):
    for index in range(3):
        _submit(world, index, user="rim")


@override_settings(APPLICATIONS_DAILY_LIMIT=1)
def test_create_endpoint_returns_a_clear_400(world):
    _submit(world, 1)
    client = _client(world["student"], world["organization"])
    response = client.post(
        reverse("applications:create"),
        {
            "kind": "diger",
            "subject": "API limit yoxlaması",
            "body": "Gündəlik limit dolanda API aydın xəta mətni qaytarmalıdır.",
        },
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["errors"]["code"] == ["limit.daily"]
    assert "1" in payload["errors"]["__all__"][0]


# ── «Sistem tənzimləmələri» ─────────────────────────────────────────────────


def test_spec_is_registered_in_its_own_group():
    spec = rs.SPECS[KEY_DAILY_LIMIT]
    assert (spec.group, spec.kind, spec.min, spec.max) == ("applications", "int", 1, 50)
    assert spec.default() == 10
    assert "applications" in {code for code, _label in rs.GROUPS}


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM, APPLICATIONS_DAILY_LIMIT=10)
def test_runtime_setting_override_changes_the_cap(world):
    rs.invalidate()
    try:
        assert daily_limit() == 10
        RuntimeSetting.objects.create(key=KEY_DAILY_LIMIT, value=2)
        rs.invalidate()
        assert daily_limit() == 2
        _submit(world, 1)
        _submit(world, 2)
        with pytest.raises(TransitionDenied) as excinfo:
            _submit(world, 3)
        assert excinfo.value.params == {"limit": 2}
        # Hədddən kənar saxlanmış dəyər nəzərə alınmır — defolt işləyir.
        RuntimeSetting.objects.filter(key=KEY_DAILY_LIMIT).update(value=500)
        rs.invalidate()
        assert daily_limit() == 10
        _submit(world, 3)
    finally:
        rs.invalidate()
