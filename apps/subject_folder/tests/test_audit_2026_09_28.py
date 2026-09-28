"""Audit 2026-09-28 — fənn qovluğu: SF-1 (ofis dekompressiya bombası), SF-2 (qaralama
gizliliyi), SF-3 (endirmə MIME-ı uzantıdan).
"""

from __future__ import annotations

import io
import zipfile

from django.core.files.base import ContentFile
from django.test import Client
from django.urls import reverse

import pytest

from apps.subject_folder import public
from apps.subject_folder.errors import FolderError
from apps.subject_folder.services.media import check_submission_media_access
from apps.subject_folder.services.plagiarism import extract
from apps.subject_folder.services.uploads import content_type_for_name, prepare_upload

from .conftest import upload

pytestmark = pytest.mark.django_db


def _client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def _pptx_bomb(slides=20, per_slide=8 * 1024 * 1024):
    """Kiçik, amma açılanda nəhəng .pptx (hər slayd ~8 MB eyni simvol)."""
    buffer = io.BytesIO()
    body = b"<a:t>" + b"A" * per_slide + b"</a:t>"
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index in range(1, slides + 1):
            archive.writestr(f"ppt/slides/slide{index}.xml", body)
    return buffer.getvalue()


# ── SF-1 ────────────────────────────────────────────────────────────────────


def test_office_extraction_caps_decompressed_bytes(monkeypatch):
    raw = _pptx_bomb()
    assert len(raw) < 2 * 1024 * 1024  # sıxılmış kiçikdir, açılmışı ~160 MB olardı

    read_sizes = []
    original_read = extract._ZipBudget.read

    def spy(self, archive, name):
        text = original_read(self, archive, name)
        read_sizes.append(len(text))
        return text

    monkeypatch.setattr(extract._ZipBudget, "read", spy)
    text, reason = extract.extract_text(ContentFile(raw, name="bomb.pptx"), extension=".pptx", size=len(raw))

    assert reason is None
    assert len(text) <= extract.MAX_TEXT_CHARS
    assert read_sizes and max(read_sizes) <= extract._MAX_MEMBER_BYTES
    # Cəmi büdcə (16 MB) dolan kimi dayanır — 20 slaydın hamısı açılmır.
    assert sum(read_sizes) <= extract._MAX_TOTAL_XML_BYTES
    assert len(read_sizes) < 20


def test_docx_member_is_capped():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"<w:t>" + b"B" * (6 * 1024 * 1024) + b"</w:t>")
    raw = buffer.getvalue()
    text, _reason = extract.extract_text(ContentFile(raw, name="x.docx"), extension=".docx", size=len(raw))
    # Üzv 2 MB-da kəsilir — bağlanan ``</w:t>`` teqi oxunmur, mətn boş qalır.
    assert len(text) <= extract._MAX_MEMBER_BYTES


def test_ooxml_upload_runs_zip_bomb_validation():
    bomb = _pptx_bomb(slides=2, per_slide=4 * 1024 * 1024)
    with pytest.raises(FolderError) as info:
        prepare_upload(
            upload("bomb.pptx", bomb, "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
            allowed_extensions={".pptx"},
            max_mb=20,
        )
    assert "zip" in str(info.value).lower()


# ── SF-2 ────────────────────────────────────────────────────────────────────


def test_teacher_cannot_open_student_draft(ready):
    student = ready.students[0]
    draft = public.save_draft(
        task=ready.homework,
        assignment=ready.assignment,
        student=student,
        files=[upload("qaralama.txt", b"gizli qaralama", "text/plain")],
    )
    row = draft.files.get()

    assert check_submission_media_access(student, row.file.name)
    assert not check_submission_media_access(ready.teacher, row.file.name)
    teacher = _client(ready.teacher, ready.org)
    url = reverse("subject_folder:submission_file_download", args=[row.pk])
    assert teacher.get(url).status_code == 404
    assert _client(student, ready.org).get(url).status_code == 200


# ── SF-3 ────────────────────────────────────────────────────────────────────


def test_content_type_is_derived_from_extension():
    assert content_type_for_name("hesabat.pdf") == "application/pdf"
    assert content_type_for_name("qeyd.txt") == "text/plain"
    assert content_type_for_name("x.html") == "application/octet-stream"
    assert content_type_for_name("x.svg") == "application/octet-stream"
    assert content_type_for_name("adsiz") == "application/octet-stream"


def test_client_declared_mime_is_ignored(ready):
    work = public.submit(
        task=ready.homework,
        assignment=ready.assignment,
        student=ready.students[0],
        files=[upload("qeyd.txt", b"salam", "text/html")],
    )
    row = work.files.get()
    assert row.content_type == "text/plain"

    response = _client(ready.students[0], ready.org).get(
        reverse("subject_folder:submission_file_download", args=[row.pk])
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "text/plain"
