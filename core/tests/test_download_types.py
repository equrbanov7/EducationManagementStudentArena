"""``core.download_types`` — endirmə tipi uzantıdan, ağ siyahı ilə (audit SF-3 / 2026-10-07)."""

from __future__ import annotations

from django.core.files.base import ContentFile
from django.http import Http404

import pytest

from core.download_types import OCTET_STREAM, attachment_file_response, content_type_for_name


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("hesabat.pdf", "application/pdf"),
        ("HESABAT.PDF", "application/pdf"),
        ("qeyd.txt", "text/plain"),
        ("foto.JPG", "image/jpeg"),
        ("cedvel.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("arxiv.zip", "application/zip"),
    ],
)
def test_known_extensions_map_to_allowlisted_type(name, expected):
    assert content_type_for_name(name) == expected


@pytest.mark.parametrize(
    "name",
    ["x.html", "x.htm", "x.xhtml", "x.svg", "x.svgz", "x.xml", "x.xsl", "x.js", "x.mjs", "x.mht", "adsiz", "", None],
)
def test_active_or_unknown_extensions_fall_back_to_octet_stream(name):
    assert content_type_for_name(name) == OCTET_STREAM


def test_attachment_response_ignores_claim_and_sets_safety_headers():
    field_file = ContentFile(b"%PDF-1.4\n%%EOF\n", name="x/abc.pdf")

    response = attachment_file_response(field_file, filename='hesabat".pdf')

    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("attachment")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Cache-Control"] == "private, no-store"


def test_attachment_response_404_without_file():
    with pytest.raises(Http404):
        attachment_file_response(None, filename="x.pdf")
