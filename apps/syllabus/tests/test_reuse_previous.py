"""«Keçən ildən köçür» — sillabussuz AÇILIŞDAN və boş qaralamadan (2026-10-08 düzəlişi).

Əvvəl «Sillabus yoxdur» sətrindəki düymə açılışın id-sini ``syllabus_action`` → ``copy``-yə
sillabus id-si kimi göndərirdi və 404 alırdı.  İndi təkrar istifadə dialoqu ``mode=previous``
ilə eyni fənnin BAŞQA semestrlərdəki dosyelərini göstərir və seçilən mənbədən hədəf açılış
üçün QARALAMA yaranır.  Əhatə ``copy_from_previous`` ilə eynidir.
"""

from __future__ import annotations

import json

from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import pytest

from apps.organizations.models import AcademicPeriod
from apps.syllabus import services
from apps.syllabus.constants import SectionKey, SyllabusStatus
from apps.syllabus.models import ChangeKind, Syllabus
from apps.syllabus.services import reuse_rules as rules
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.factories import PLAN_HOURS
from apps.syllabus.tests.reuse_fixtures import (
    TEACHER_PERMS,
    actor,
    approved_syllabus,
    build_world,
    draft_for,
    target,
)
from core.constants import AcademicPeriodType

pytestmark = pytest.mark.django_db


def _previous_period(world, *, year="2024/2025", start="2024-09-01", end="2025-01-31"):
    return AcademicPeriod.objects.create(
        organization=world["org"],
        name="Payız",
        period_type=AcademicPeriodType.SEMESTER,
        academic_year=year,
        start_date=start,
        end_date=end,
    )


def _move_to(syllabus, period):
    """Keçən ilin sillabusu: dosye köhnə semestrdədir, açılışı yoxdur (qrup bitirib)."""
    Syllabus.objects.filter(pk=syllabus.pk).update(period=period, offering=None)
    return Syllabus.objects.get(pk=syllabus.pk)


@pytest.fixture()
def world():
    data = build_world("syl-prev")
    source, version = approved_syllabus(data, "o1")
    data["last_year"] = _previous_period(data)
    data["source"] = _move_to(source, data["last_year"])
    data["source_version"] = version
    return data


def _client(world, key="teacher"):
    client = Client()
    client.force_login(world[key])
    session = client.session
    session["active_organization"] = world["org"].slug
    session.save()
    return client


def _options(client, **params):
    return client.get(reverse("accounts:syllabus_reuse_options"), {"mode": "previous", **params})


def _post(client, payload):
    return client.post(reverse("accounts:syllabus_reuse_action"), json.dumps(payload), content_type="application/json")


def _sections(version):
    return {row.section_id: row.data for row in version.sections.all()}


def test_previous_sources_are_other_periods_only(world):
    sibling, _sibling_version = draft_for(world, "o3")  # BU semestrin qonşusu — siyahıya düşmür
    rows = list(
        rules.previous_queryset(
            organization=world["org"], actor=actor(world), subject_id=world["subject"].pk, period_id=world["period"].pk
        )
    )
    assert [row.pk for row in rows] == [world["source"].pk]
    assert sibling.pk not in {row.pk for row in rows}
    pairs = rules.previous_source_pairs(
        organization=world["org"], actor=actor(world), subject_ids={world["subject"].pk}
    )
    assert (world["subject"].pk, world["last_year"].pk) in pairs
    assert rules.has_previous(pairs, subject_id=world["subject"].pk, period_id=world["period"].pk)
    # Kopyalaya bilməyən (syllabus.edit yoxdur) kafedra müdirinə mənbə təklif olunmur.
    assert rules.previous_source_pairs(organization=world["org"], actor=actor(world, "head"), subject_ids={1}) == set()


def test_copy_previous_creates_a_draft_for_the_offering(world):
    syllabus, version = services.reuse.copy_adjust(
        source=world["source"], target=target(world, "o2"), actor=actor(world), previous=True
    )
    version.refresh_from_db()
    assert syllabus.offering_id == world["offerings"]["o2"].pk
    assert syllabus.period_id == world["period"].pk
    assert syllabus.reused_from_id is None
    assert (version.status, version.change_kind) == (SyllabusStatus.DRAFT, ChangeKind.COPIED)
    assert version.source_version_id == world["source_version"].pk
    assert _sections(version)[SectionKey.LIT.value] == _sections(world["source_version"])[SectionKey.LIT.value]


def test_copy_previous_adjusts_hours_and_refuses_same_period_sources(world):
    _syllabus, version = services.reuse.copy_adjust(
        source=world["source"], target=target(world, "o3"), actor=actor(world), previous=True
    )
    rows = _sections(version)[SectionKey.WEEK.value]["rows"]
    assert sum(row["seminar"] for row in rows) == 30 and sum(row["lab"] for row in rows) == 0
    sibling, _sibling_version = draft_for(world, "o4")
    with pytest.raises(TransitionDenied) as denied:
        services.reuse.copy_adjust(source=sibling, target=target(world, "o2"), actor=actor(world), previous=True)
    assert denied.value.code == rules.CODE_NOT_PREVIOUS


def test_copy_previous_scope_matches_copy_from_previous(world):
    foreign, _version = approved_syllabus(world, "o5", user_key="teacher2")
    foreign = _move_to(foreign, _previous_period(world, year="2023/2024", start="2023-09-01", end="2024-01-31"))
    with pytest.raises(TransitionDenied) as denied:
        services.reuse.copy_adjust(source=foreign, target=target(world, "o2"), actor=actor(world), previous=True)
    assert denied.value.code == rules.CODE_COPY_OUT_OF_SCOPE
    with pytest.raises(TransitionDenied) as denied:
        services.reuse.copy_adjust(
            source=world["source"], target=target(world, "o5"), actor=actor(world), previous=True
        )
    assert denied.value.code == "transition.author_only"


# ── HTTP ──────────────────────────────────────────────────────────────────────


def test_offering_row_copy_previous_end_to_end(world):
    client = _client(world)
    offering = world["offerings"]["o2"]
    options = _options(client, offering=str(offering.pk)).json()
    assert options["mode"] == "previous"
    assert options["candidates"] == [] and options["can_create_blank"] is True
    [row] = options["siblings"]
    assert row["id"] == str(world["source"].pk)
    assert (row["can_copy"], row["can_link"]) == (True, False)
    assert row["group"] == f"{world['last_year'].year_display} · Payız"

    response = _post(client, {"action": "copy_previous", "source": row["id"], "offering": str(offering.pk)})
    assert response.status_code == 200, response.content
    assert response.json()["status"] == SyllabusStatus.DRAFT
    assert Syllabus.objects.filter(offering=offering).count() == 1
    # Oxuya bilmədiyi mənbə və başqasının açılışı — 404.
    foreign, _version = approved_syllabus(world, "o5", user_key="teacher2")
    foreign = _move_to(foreign, _previous_period(world, year="2023/2024", start="2023-09-01", end="2024-01-31"))
    assert (
        _post(client, {"action": "copy_previous", "source": str(foreign.pk), "offering": str(offering.pk)}).status_code
        == 404
    )
    assert _options(client, offering=str(world["offerings"]["o5"].pk)).status_code == 404


# ── Siyahı və redaktor ───────────────────────────────────────────────────────


def _list(world):
    from apps.accounts.views.syllabus.section import build_syllabus_list_section

    request = RequestFactory().get("/accounts/profile/")
    request.user = world["teacher"]
    request.org_permissions = list(TEACHER_PERMS)
    request.organization = world["org"]
    return build_syllabus_list_section(request, organization=world["org"])["syllabus_list_section"]


def _keys(rows, pk):
    return [action["key"] for action in rows[str(pk)]["actions"]]


def test_list_offers_copy_previous_on_missing_and_blank_draft_rows(world):
    rows = {row["id"]: row for row in _list(world)["rows"]}
    assert _keys(rows, world["offerings"]["o2"].pk) == ["create", "copy"]

    draft, _version = draft_for(world, "o3")
    rows = {row["id"]: row for row in _list(world)["rows"]}
    # Bu semestrdə də qonşu var — «Mövcud sillabusdan istifadə et» birinci, «Keçən ildən köçür» yanında.
    assert _keys(rows, world["offerings"]["o2"].pk) == ["reuse", "copy", "create"]
    assert _keys(rows, draft.pk) == ["resume", "copy"]
    # Keçmiş semestr dosyesinin öz sətrində («Keçən ildən köçür» özünə) — təklif yoxdur.
    assert "copy" not in [action["key"] for action in rows[str(world["source"].pk)]["actions"]]


def test_list_hides_copy_previous_without_a_source(world):
    Syllabus.objects.filter(pk=world["source"].pk).update(is_active=False)
    rows = {row["id"]: row for row in _list(world)["rows"]}
    assert [action["key"] for action in rows[str(world["offerings"]["o2"].pk)]["actions"]] == ["create"]


def test_list_query_count_does_not_grow_with_previous_sources(world):
    draft_for(world, "o3")  # səhifədə qaralama sətri var — bayraq sorğusu hər iki ölçmədə işləyir
    _list(world)
    with CaptureQueriesContext(connection) as small:
        _list(world)
    for index in range(3):
        period = _previous_period(
            world, year=f"20{20 + index}/20{21 + index}", start=f"20{20 + index}-09-01", end=f"20{21 + index}-01-31"
        )
        services.create_draft(
            organization=world["org"],
            subject=world["subject"],
            period=period,
            actor=actor(world),
            author=world["teacher"],
            plan_hours=dict(PLAN_HOURS),
        )
    with CaptureQueriesContext(connection) as large:
        _list(world)
    assert len(large.captured_queries) == len(small.captured_queries)


def test_editor_banner_offers_copy_previous_on_a_blank_draft(world):
    _draft, version = draft_for(world, "o2")
    html = (
        _client(world)
        .get(reverse("accounts:profile"), {"section": "syllabus-editor", "version": str(version.pk)})
        .content.decode()
    )
    assert 'data-syl-action="copy"' in html
    assert "data-syl-reuse-modal" in html
