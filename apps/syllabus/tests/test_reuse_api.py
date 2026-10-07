"""Təkrar istifadənin HTTP səthi + siyahı/redaktor/tələbə inteqrasiyası + sorğu büdcəsi."""

from __future__ import annotations

import json

from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import pytest

from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Enrollment
from apps.syllabus import services
from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.models import ApprovalSource, ChangeKind, Syllabus
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org
from apps.syllabus.tests.reuse_fixtures import (
    TEACHER_PERMS,
    actor,
    approve_version,
    approved_syllabus,
    build_world,
    draft_for,
    target,
)
from core.constants import OrgUnitType

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    return build_world("syl-reuse-api")


def _client(world, key="teacher", org=None):
    client = Client()
    client.force_login(world[key])
    session = client.session
    session["active_organization"] = (org or world["org"]).slug
    session.save()
    return client


def _options(client, **params):
    return client.get(reverse("accounts:syllabus_reuse_options"), {k: str(v) for k, v in params.items()})


def _post(client, payload):
    return client.post(
        reverse("accounts:syllabus_reuse_action"),
        data=json.dumps({k: (str(v) if not isinstance(v, list) else v) for k, v in payload.items()}),
        content_type="application/json",
    )


# ── Dialoq seçimləri ─────────────────────────────────────────────────────────


def test_options_list_the_siblings_with_hours_and_bulk_candidates(world):
    source, _version = approved_syllabus(world, "o1")
    offerings = world["offerings"]
    payload = _options(_client(world), offering=offerings["o2"].pk).json()
    assert payload["ok"] is True
    assert payload["target"]["kind"] == "offering"
    assert payload["target"]["hours_known"] is True
    assert payload["can_create_blank"] is True
    [row] = payload["siblings"]
    assert row["id"] == str(source.pk)
    assert row["group"] == world["groups"]["g1"].name
    assert (row["own"], row["hours_same"], row["can_link"], row["can_copy"]) == (True, True, True, True)
    states = {entry["offering"]: entry["state"] for entry in payload["candidates"]}
    assert states == {str(offerings["o1"].pk): "has", str(offerings["o3"].pk): "none", str(offerings["o4"].pk): "none"}
    # g3-ün saatı fərqlidir, g4-ün kafedrası fərqlidir → ikisi də kopyalanacaq.
    assert row["modes"] == {str(offerings["o3"].pk): "copy", str(offerings["o4"].pk): "copy"}

    different = _options(_client(world), offering=offerings["o3"].pk).json()["siblings"][0]
    assert different["hours_same"] is False and different["can_link"] is False and different["can_copy"] is True
    assert different["link_reason"]
    assert [item["same"] for item in different["hours_rows"]] == [True, False, False]


def test_options_are_fail_closed(world):
    approved_syllabus(world, "o1")
    client = _client(world)
    # Başqa müəllimin açılışı → 404 (mövcudluq sızmır).
    assert _options(client, offering=world["offerings"]["o5"].pk).status_code == 404
    other = make_org("syl-reuse-api-foreign")
    stack = make_academic_stack(other, code="RSEX")
    activate_member(other, world["teacher2"], "teacher", permissions=TEACHER_PERMS)
    foreign_offering = make_offering(other, stack, world["teacher2"])
    assert _options(client, offering=foreign_offering.pk).status_code == 404
    assert _options(client, offering="yanlış").status_code == 404
    # `syllabus.edit` açarı olmayan kafedra müdiri — 403.
    assert _options(_client(world, "head"), offering=world["offerings"]["o2"].pk).status_code == 403
    # Oxuya bilmədiyi qonşu dialoqa düşmür.
    approved_syllabus(world, "o5", user_key="teacher2")
    siblings = _options(client, offering=world["offerings"]["o2"].pk).json()["siblings"]
    assert [row["group"] for row in siblings] == [world["groups"]["g1"].name]


def test_options_query_count_does_not_grow_with_siblings(world):
    approved_syllabus(world, "o1")
    draft_for(world, "o3")
    client = _client(world)
    url_offering = world["offerings"]["o2"].pk
    _options(client, offering=url_offering)  # isinmə
    with CaptureQueriesContext(connection) as small:
        assert len(_options(client, offering=url_offering).json()["siblings"]) == 2
    spec = world["groups"]["g1"].parent
    for index in range(4):
        group = OrgUnit.objects.create(
            organization=world["org"],
            name=f"9{index}A",
            slug=f"rse-extra-{index}",
            unit_type=OrgUnitType.GROUP,
            parent=spec,
        )
        offering = CourseOffering.objects.create(
            organization=world["org"],
            subject=world["subject"],
            period=world["period"],
            group=group,
            instructor=world["teacher"],
            lesson_hours=60,
        )
        services.create_draft(
            organization=world["org"],
            subject=world["subject"],
            period=world["period"],
            actor=actor(world),
            offering=offering,
            chair_unit=spec,
            author=world["teacher"],
        )
    with CaptureQueriesContext(connection) as large:
        assert len(_options(client, offering=url_offering).json()["siblings"]) == 6
    assert len(large.captured_queries) == len(small.captured_queries), [q["sql"] for q in large.captured_queries]


# ── Əməllər ──────────────────────────────────────────────────────────────────


def test_link_endpoint_and_the_student_sees_the_linked_content(world):
    source, source_version = approved_syllabus(world, "o1")
    offering = world["offerings"]["o2"]
    response = _post(_client(world), {"action": "link", "source": source.pk, "offering": offering.pk})
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == SyllabusStatus.APPROVED
    assert world["groups"]["g1"].name in body["message"]

    student = world["teacher2"].__class__.objects.create_user("rse_student", "rse_student@x.test", "pw")
    activate_member(world["org"], student, "student", permissions=[])
    Enrollment.objects.create(organization=world["org"], student=student, offering=offering)
    shown = _client({**world, "student": student}, "student").get(
        reverse("registrar:offering_syllabus_json", args=[offering.pk])
    )
    assert shown.status_code == 200
    document = shown.json()
    assert document["mode"] == "student"
    assert document["status"] == SyllabusStatus.APPROVED
    assert document["approved_by"] == ""
    assert world["groups"]["g1"].name in document["approval_note"]
    from apps.syllabus.public import build_document

    assert document["blocks"] == build_document(source, source_version)["blocks"]


def test_link_with_an_unreadable_source_is_404(world):
    foreign, _version = approved_syllabus(world, "o5", user_key="teacher2")
    response = _post(_client(world), {"action": "link", "source": foreign.pk, "offering": world["offerings"]["o2"].pk})
    assert response.status_code == 404
    assert not Syllabus.objects.filter(offering=world["offerings"]["o2"]).exists()


def test_copy_endpoint_returns_a_draft_and_refuses_double_submit(world):
    source, _version = approved_syllabus(world, "o1")
    client = _client(world)
    payload = {"action": "copy", "source": source.pk, "offering": world["offerings"]["o3"].pk}
    first = _post(client, payload)
    assert first.status_code == 200 and first.json()["status"] == SyllabusStatus.DRAFT
    # İkinci klik mövcud qaralamanın üstünə yazır (açıq DRAFT) — yeni dosye YARANMIR.
    second = _post(client, payload)
    assert second.status_code == 200
    assert Syllabus.objects.filter(offering=world["offerings"]["o3"]).count() == 1


def test_bulk_endpoint_only_touches_own_offerings_and_is_idempotent(world):
    source, _version = approved_syllabus(world, "o1")
    offerings = world["offerings"]
    payload = {"action": "bulk", "source": source.pk, "offerings": [str(offerings[k].pk) for k in ("o2", "o3", "o5")]}
    client = _client(world)
    first = _post(client, payload).json()
    assert {row["offering"]: row["status"] for row in first["results"]} == {
        str(offerings["o2"].pk): "linked",
        str(offerings["o3"].pk): "copied",
    }
    assert not Syllabus.objects.filter(offering=offerings["o5"]).exists()
    second = _post(client, payload).json()
    assert sorted(row["status"] for row in second["results"]) == ["already", "exists"]
    assert second["counts"] == {"linked": 0, "copied": 0, "skipped": 2}
    assert _post(client, {"action": "bulk", "source": source.pk, "offerings": []}).status_code == 400


def test_propagate_unlink_and_sync_endpoints(world):
    source, _version = approved_syllabus(world, "o1")
    act = actor(world)
    linked, _first = services.reuse.link(source=source, target=target(world, "o2"), actor=act)
    draft = services.create_next_version(syllabus=source, actor=act, kind=ChangeKind.MINOR.value)
    newest = approve_version(world, draft, act)
    client = _client(world)

    propagated = _post(client, {"action": "propagate", "syllabus": source.pk})
    assert propagated.status_code == 200
    assert propagated.json()["counts"] == {"synced": 1, "already": 0, "skipped": 0}
    linked.refresh_from_db()
    assert linked.approved_version.source_version_id == newest.pk
    assert _post(client, {"action": "sync", "syllabus": linked.pk}).json()["code"] == "reuse.up_to_date"

    unlinked = _post(client, {"action": "unlink", "syllabus": linked.pk})
    assert unlinked.status_code == 200 and unlinked.json()["status"] == SyllabusStatus.DRAFT
    assert _post(client, {"action": "unlink", "syllabus": linked.pk}).status_code == 409
    # Başqa müəllim bağlı dosyeni idarə edə bilmir (oxuya bilmədiyi üçün 404).
    assert _post(_client(world, "teacher2"), {"action": "unlink", "syllabus": linked.pk}).status_code == 404


# ── Siyahı və redaktor ───────────────────────────────────────────────────────


def _list_rows(world):
    from apps.accounts.views.syllabus.section import build_syllabus_list_section

    request = RequestFactory().get("/accounts/profile/")
    request.user = world["teacher"]
    request.org_permissions = list(TEACHER_PERMS)
    request.organization = world["org"]
    return build_syllabus_list_section(request, organization=world["org"])["syllabus_list_section"]["rows"]


def test_list_offers_reuse_for_other_groups_and_marks_linked_rows(world):
    source, _version = approved_syllabus(world, "o1")
    linked, _approved = services.reuse.link(source=source, target=target(world, "o2"), actor=actor(world))
    rows = {row["id"]: row for row in _list_rows(world)}
    # o3/o4 — sillabussuz qruplar ARTIQ gizlənmir (əvvəl başqa qrupun dosyesi onları «örtürdü»).
    for key in ("o3", "o4"):
        missing = rows[str(world["offerings"][key].pk)]
        assert missing["kind"] == "missing"
        assert [action["key"] for action in missing["actions"]] == ["reuse", "create"]
    linked_row = rows[str(linked.pk)]
    keys = [action["key"] for action in linked_row["actions"]]
    assert "unlink" in keys and "new_version" not in keys
    assert world["groups"]["g1"].name in linked_row["approver"]
    assert world["groups"]["g1"].name in linked_row["reuse_note"]
    assert rows[str(source.pk)]["reuse_note"]


def test_list_offers_reuse_on_blank_drafts_but_not_on_copies(world):
    approved_syllabus(world, "o1")
    blank, _blank_version = draft_for(world, "o2")
    copied, _copied_version = services.reuse.copy_adjust(
        source=Syllabus.objects.get(offering=world["offerings"]["o1"]), target=target(world, "o3"), actor=actor(world)
    )
    rows = {row["id"]: row for row in _list_rows(world)}
    assert rows[str(blank.pk)]["actions"][0]["key"] == "reuse"
    assert rows[str(blank.pk)]["reuse_note"]
    assert "reuse" not in [action["key"] for action in rows[str(copied.pk)]["actions"]]


def test_editor_banner_offers_reuse_on_a_blank_draft_and_unlink_on_a_linked_one(world):
    source, _version = approved_syllabus(world, "o1")
    _draft, draft_version = draft_for(world, "o2")
    client = _client(world)
    html = client.get(
        reverse("accounts:profile"), {"section": "syllabus-editor", "version": str(draft_version.pk)}
    ).content.decode()
    assert 'data-syl-action="reuse"' in html
    assert "data-syl-reuse-modal" in html
    linked, approved = services.reuse.link(
        source=source, target=target(world, "o2", syllabus=Syllabus.objects.get(pk=_draft.pk)), actor=actor(world)
    )
    html = client.get(
        reverse("accounts:profile"), {"section": "syllabus-editor", "version": str(approved.pk)}
    ).content.decode()
    assert 'data-syl-action="unlink"' in html
    assert approved.approval_source == ApprovalSource.REUSE


# ── registrar paritet ────────────────────────────────────────────────────────


def test_batched_plan_hours_match_the_single_lookup(world):
    from apps.registrar.public import plan_hours_by_offering, plan_hours_for_offering

    offerings = list(world["offerings"].values())
    lonely = make_offering(
        world["org"], {"subject": world["subject"], "period": world["period"], "group": None}, world["teacher"]
    )
    offerings.append(lonely)
    batched = plan_hours_by_offering(offerings)
    assert batched == {offering.pk: plan_hours_for_offering(offering) for offering in offerings}
