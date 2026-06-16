"""Form validation tests for the trial-exam request form."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile

import pytest

from apps.trial_exams.forms import TrialExamRequestForm

pytestmark = pytest.mark.django_db


def _files(pdf):
    return {"questions_file": pdf}


def test_valid_form(valid_post_data, pdf_upload):
    form = TrialExamRequestForm(valid_post_data, _files(pdf_upload()))
    assert form.is_valid(), form.errors


def test_missing_file_is_rejected(valid_post_data):
    form = TrialExamRequestForm(valid_post_data, {})
    assert not form.is_valid()
    assert "questions_file" in form.errors


def test_non_pdf_extension_is_rejected(valid_post_data):
    bad = SimpleUploadedFile("questions.txt", b"hello", content_type="text/plain")
    form = TrialExamRequestForm(valid_post_data, _files(bad))
    assert not form.is_valid()
    assert "questions_file" in form.errors


def test_fake_pdf_mime_is_rejected(valid_post_data):
    # .pdf extension but a non-PDF MIME type → rejected.
    bad = SimpleUploadedFile("questions.pdf", b"not a pdf", content_type="text/plain")
    form = TrialExamRequestForm(valid_post_data, _files(bad))
    assert not form.is_valid()
    assert "questions_file" in form.errors


def test_honeypot_blocks_bots(valid_post_data, pdf_upload):
    data = dict(valid_post_data, website="http://spam.example")
    form = TrialExamRequestForm(data, _files(pdf_upload()))
    assert not form.is_valid()


def test_short_name_is_rejected(valid_post_data, pdf_upload):
    data = dict(valid_post_data, full_name="A")
    form = TrialExamRequestForm(data, _files(pdf_upload()))
    assert not form.is_valid()
    assert "full_name" in form.errors


def test_short_subject_is_rejected(valid_post_data, pdf_upload):
    data = dict(valid_post_data, subject_name="X")
    form = TrialExamRequestForm(data, _files(pdf_upload()))
    assert not form.is_valid()
    assert "subject_name" in form.errors


def test_link_in_name_is_rejected(valid_post_data, pdf_upload):
    data = dict(valid_post_data, full_name="http://evil.example")
    form = TrialExamRequestForm(data, _files(pdf_upload()))
    assert not form.is_valid()
    assert "full_name" in form.errors
