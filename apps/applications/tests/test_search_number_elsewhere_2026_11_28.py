"""Sahib 2026-11-28: «MR-886» axtarışı «MR-000886»-ni tapmırdı; tapılmayanda başqa bölmə göstərilir."""

from __future__ import annotations

from django.urls import reverse

import pytest

from apps.applications.tests.test_endpoints import application, body, client_for, world  # noqa: F401

pytestmark = pytest.mark.django_db


def _list(world, **params):  # noqa: F811
    student = client_for(world["student"], world["organization"])
    return body(student.get(reverse("applications:list"), params))


def test_short_number_forms_find_the_padded_number(world, application):  # noqa: F811
    digits = str(int(application.number.split("-")[1]))
    for query in (f"MR-{digits}", f"mr {digits}", f"MR{digits}", digits, application.number):
        assert _list(world, tab="mine", q=query)["total"] == 1, query
    assert _list(world, tab="mine", q=f"MR-{digits}9")["total"] == 0


def test_empty_tab_points_to_the_tab_that_has_the_match(world, application):  # noqa: F811
    digits = str(int(application.number.split("-")[1]))
    payload = _list(world, tab="inbox", stat="open", q=f"MR-{digits}")
    assert payload["total"] == 0
    assert {"tab": "mine", "stat": "all", "count": 1} in payload["elsewhere"]
    # Status filtri gizlədəndə eyni tab da göstərilir; «Bütün müraciətlər» nəzarətçi olmayana təklif olunmur.
    closed = _list(world, tab="mine", stat="closed", q=f"MR-{digits}")
    assert closed["total"] == 0
    assert [spot["tab"] for spot in closed["elsewhere"]] == ["mine"]


def test_no_hint_without_search_or_when_results_exist(world, application):  # noqa: F811
    assert _list(world, tab="inbox", stat="open")["elsewhere"] == []
    assert _list(world, tab="mine", stat="open", q="Seçmə")["elsewhere"] == []
