"""List authorship, scoped teacher filtering and approved/draft coexistence."""

from django.db import connection
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

import pytest

from apps.accounts.models import UserProfile
from apps.accounts.views.syllabus.section import build_syllabus_list_section
from apps.syllabus import services
from apps.syllabus.models import SyllabusVersion
from apps.syllabus.tests.reuse_fixtures import actor, approved_syllabus, build_world, draft_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(settings):
    settings.ACADEMIC_SELFWORK_ENABLED = True
    data = build_world("syllabus-attribution")
    UserProfile.objects.filter(user=data["teacher"]).update(patronymic="Ata qızı")
    syllabus, approved = approved_syllabus(data)
    draft = services.create_next_version(syllabus=syllabus, actor=actor(data, "teacher"), kind="minor")
    SyllabusVersion.objects.filter(pk=draft.pk).update(completion_percent=43)
    data.update(syllabus=syllabus, approved=approved, draft=draft)
    draft_for(data, "o5", user_key="teacher2")
    return data


def section(world, user="head", **params):
    request = RequestFactory().get("/accounts/profile/", params)
    request.user = world[user]
    return build_syllabus_list_section(request, organization=world["org"])["syllabus_list_section"]


def test_approved_fallback_visible_and_human_draft_unchanged(world):
    before = list(world["draft"].sections.order_by("pk").values())
    result = section(world, status="approved", teacher=str(world["teacher"].pk))
    row = next(r for r in result["rows"] if r["id"] == str(world["syllabus"].pk))
    assert row["author_name"] == "Nigar Həsənli Ata qızı"
    assert row["status_key"] == "approved"
    assert row["version_label"] == world["approved"].label
    assert row["read_version_id"] == str(world["approved"].pk)
    assert row["version_id"] == str(world["draft"].pk)
    assert row["draft_note"]
    world["syllabus"].refresh_from_db()
    world["draft"].refresh_from_db()
    assert world["syllabus"].current_version_id == world["draft"].pk
    assert world["draft"].status == "draft"
    assert world["draft"].completion_percent == 43
    assert list(world["draft"].sections.order_by("pk").values()) == before
    chips = {c["key"]: c["count"] for c in result["chips"]}
    assert chips["approved"] == 1
    assert chips["draft"] == 0


def test_real_unapproved_draft_stays_draft(world):
    result = section(world, status="draft")
    assert len(result["rows"]) == 1
    assert result["rows"][0]["author_name"] == "Elçin Quliyev"
    assert not result["rows"][0]["draft_note"]


def test_teacher_filter_cannot_expand_ordinary_teacher_scope(world):
    result = section(world, user="teacher", teacher=str(world["teacher2"].pk))
    assert not result["rows"]
    keys = {r["key"] for r in result["filter_options"]["teachers"]}
    assert str(world["teacher2"].pk) not in keys
    assert not section(world, teacher="1 OR 1=1")["rows"]


def test_missing_has_assigned_teacher_but_no_fabricated_author(world):
    result = section(world, user="teacher", status="missing", teacher=str(world["teacher"].pk))
    assert result["rows"]
    assert all(not row["author_name"] for row in result["rows"])
    assert all(row["teacher_name"] == "Nigar Həsənli Ata qızı" for row in result["rows"])


def test_assigned_teacher_filter_and_author_are_distinct(world):
    world["syllabus"].offering.instructor = world["teacher2"]
    world["syllabus"].offering.save(update_fields=["instructor"])
    result = section(world, teacher=str(world["teacher2"].pk), status="approved")
    row = result["rows"][0]
    assert row["author_name"] == "Nigar Həsənli Ata qızı"
    assert row["teacher_name"] == "Elçin Quliyev"


def test_year_semester_and_filter_survive_and_wrong_semester_empty(world):
    params = dict(
        year=world["period"].academic_year,
        semester=world["period"].name,
        teacher=str(world["teacher"].pk),
        sort="subject",
        status="approved",
    )
    result = section(world, **params)
    assert all(result["filters"][key] == value for key, value in params.items())
    assert result["page"]["total"] == 1
    assert not section(world, semester="Başqa", teacher=str(world["teacher"].pk))["rows"]


def test_table_and_cards_share_attribution_and_searchable_select(world):
    result = section(world)
    html = render_to_string(
        "accounts/profile/sections/_syllabus_list.html",
        {
            "allowed_sections": ["syllabus-list"],
            "active_section": "syllabus-list",
            "syllabus_list_section": result,
            "profile_base_url": "/accounts/profile/",
        },
    )
    assert html.count("data-syllabus-author") >= 4
    assert "Nigar Həsənli Ata qızı" in html
    assert 'data-syl-filter="teacher"' in html
    assert 'data-live-search="true"' in html
    assert "data-syllabus-draft-preserved" in html


def test_attribution_and_options_do_not_create_per_row_queries(world):
    section(world, status="draft")  # Warm actor/profile caches equally.
    with CaptureQueriesContext(connection) as one:
        first = section(world, status="draft")
    for key in ("o2", "o3", "o4"):
        draft_for(world, key)
    with CaptureQueriesContext(connection) as many:
        expanded = section(world, status="draft")
    assert len(expanded["rows"]) > len(first["rows"])
    assert len(many) == len(one)


def test_foreign_tenant_teacher_is_not_a_filter_option_or_result(world):
    foreign = build_world("foreign-syllabus-attribution")
    draft_for(foreign, "o1")
    result = section(world, teacher=str(foreign["teacher"].pk))
    assert not result["rows"]
    assert str(foreign["teacher"].pk) not in {r["key"] for r in result["filter_options"]["teachers"]}


def test_null_author_is_not_replaced_with_instructor_or_operator(world):
    from apps.syllabus.models import Syllabus

    Syllabus.objects.filter(pk=world["syllabus"].pk).update(author=None)
    row = section(world, status="approved")["rows"][0]
    assert row["author_name"] == ""
    assert row["teacher_name"] == "Nigar Həsənli Ata qızı"
