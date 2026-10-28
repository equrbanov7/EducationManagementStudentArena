"""«Bir sillabus — bir neçə jurnal» (sahib 2026-10-27): müəllim öz sillabusunu eyni fənnin başqa qrupunda ÖZ YERİNDƏ
istifadə edir (surət yox) — servis qaydaları, jurnal/tələbə/plan həlli, tək təsdiq, HTTP səthi, siyahı və redaktor.
"""

from __future__ import annotations

import json

from django.test import Client, RequestFactory
from django.urls import reverse

import pytest

from apps.registrar.semester_readiness import approved_syllabus_offering_ids
from apps.syllabus import services
from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.models import ShareSource, Syllabus, SyllabusShare
from apps.syllabus.services import sharing
from apps.syllabus.services.reuse_rules import CODE_NOT_OWN, CODE_NOT_SIBLING
from apps.syllabus.services.week_rows import approved_week_rows_for_offerings
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.reuse_fixtures import (
    TEACHER_PERMS,
    actor,
    approve_version,
    build_world,
    draft_for,
    fill,
)

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    data = build_world("syl-share")
    data["source"], data["version"] = draft_for(data, "o1")
    return data


def _offering(world, key):
    from apps.registrar.models import CourseOffering

    return CourseOffering.objects.get(pk=world["offerings"][key].pk)


def _share(world, key="o2"):
    return sharing.share(source=world["source"], offering=_offering(world, key), actor=actor(world))


def test_share_links_the_same_syllabus_without_a_copy(world):
    row = _share(world)
    assert (row.syllabus_id, row.source, row.created_by_id) == (
        world["source"].pk,
        ShareSource.TEACHER.value,
        world["teacher"].pk,
    )
    assert Syllabus.objects.filter(organization=world["org"]).count() == 1
    found = services.syllabus_for_offering_obj(_offering(world, "o2"))
    assert found.pk == world["source"].pk
    # Jurnal banneri eyni vəziyyəti göstərir (qaralama) — təsdiq BİRDİR.
    assert services.offering_syllabus_state(found)["state"] == "draft"


def test_one_approval_serves_every_linked_journal(world):
    _share(world, "o2")
    _share(world, "o3")
    version = approve_version(world, fill(world["version"], actor(world)), actor(world))
    assert version.status == SyllabusStatus.APPROVED
    offerings = [_offering(world, key) for key in ("o1", "o2", "o3")]
    for offering in offerings:
        state = services.offering_syllabus_state(services.syllabus_for_offering_obj(offering))
        assert state["state"] == "approved"
    student = services.student_syllabus_map(world["org"], offerings)
    assert set(student.values()) == {world["source"].pk}
    weeks = approved_week_rows_for_offerings(offerings)
    assert weeks[offerings[1].pk] == weeks[offerings[0].pk] and weeks[offerings[0].pk]
    rows = [{"id": o.pk, "subject_id": o.subject_id, "instructor_id": o.instructor_id} for o in offerings]
    assert approved_syllabus_offering_ids(world["org"], world["period"], rows) == {o.pk for o in offerings}


def test_share_rules(world):
    teacher = actor(world)
    # Başqa müəllimin açılışı.
    with pytest.raises(TransitionDenied) as denied:
        sharing.share(source=world["source"], offering=_offering(world, "o5"), actor=teacher)
    assert denied.value.code == "transition.author_only"
    # Həmkarın sillabusu (sahib 2026-10-27: yalnız öz sillabusu).
    with pytest.raises(TransitionDenied) as denied:
        sharing.share(source=world["source"], offering=_offering(world, "o2"), actor=actor(world, "teacher2"))
    assert denied.value.code == CODE_NOT_OWN
    # Öz açılışına paylaşmaq olmaz.
    with pytest.raises(TransitionDenied) as denied:
        sharing.share(source=world["source"], offering=_offering(world, "o1"), actor=teacher)
    assert denied.value.code == CODE_NOT_SIBLING
    # Öz dosyesi olan qrup üstünə yazılmır (fill-only).
    draft_for(world, "o3")
    with pytest.raises(TransitionDenied) as denied:
        sharing.share(source=world["source"], offering=_offering(world, "o3"), actor=teacher)
    assert denied.value.code == sharing.CODE_HAS_OWN
    _share(world, "o2")
    with pytest.raises(TransitionDenied) as denied:
        _share(world, "o2")
    assert denied.value.code == sharing.CODE_ALREADY


def test_unshare_and_own_draft_release_the_link(world):
    _share(world, "o2")
    sharing.unshare(syllabus=world["source"], offering_id=world["offerings"]["o2"].pk, actor=actor(world))
    assert services.syllabus_for_offering_obj(_offering(world, "o2")) is None
    with pytest.raises(TransitionDenied) as denied:
        sharing.unshare(syllabus=world["source"], offering_id=world["offerings"]["o2"].pk, actor=actor(world))
    assert denied.value.code == sharing.CODE_NOT_SHARED
    _share(world, "o2")
    own, _version = draft_for(world, "o2")  # müəllim sonradan ayrıca sillabus yazmaq istəyir
    assert not SyllabusShare.objects.filter(offering=world["offerings"]["o2"]).exists()
    assert services.syllabus_for_offering_obj(_offering(world, "o2")).pk == own.pk


def test_share_does_not_follow_a_handover_to_another_teacher(world):
    _share(world, "o2")
    from apps.registrar.models import CourseOffering

    CourseOffering.objects.filter(pk=world["offerings"]["o2"].pk).update(instructor=world["teacher2"])
    offering = _offering(world, "o2")
    assert services.syllabus_for_offering_obj(offering) is None
    assert services.student_syllabus_map(world["org"], [offering]) == {}
    assert services.shared_syllabus_ids([offering.pk]) == {}


# ── HTTP + siyahı + redaktor ───────────────────────────────────────────────────


def _client(world, key="teacher"):
    client = Client()
    client.force_login(world[key])
    session = client.session
    session["active_organization"] = world["org"].slug
    session.save()
    return client


def _post(client, payload):
    return client.post(reverse("accounts:syllabus_reuse_action"), json.dumps(payload), content_type="application/json")


def test_dialog_offers_share_and_post_shares(world):
    client = _client(world)
    offering = world["offerings"]["o2"]
    options = client.get(reverse("accounts:syllabus_reuse_options"), {"offering": str(offering.pk)}).json()
    [row] = options["siblings"]
    assert (row["id"], row["can_share"], row["share_reason"]) == (str(world["source"].pk), True, "")
    response = _post(client, {"action": "share", "source": row["id"], "offering": str(offering.pk)})
    assert response.status_code == 200, response.content
    assert "101A" in response.json()["message"]
    assert SyllabusShare.objects.filter(syllabus=world["source"], offering=offering).exists()
    # Başqa qrupun dialoqunda paylaşılmış qrup «eyni sillabusu istifadə edir» kimi görünür, toplu əməl onu əzmir.
    options = client.get(reverse("accounts:syllabus_reuse_options"), {"offering": str(world["offerings"]["o3"].pk)})
    states = {row["offering"]: row["state"] for row in options.json()["candidates"]}
    assert states[str(offering.pk)] == "shared"
    # Başqasının açılışı / oxuya bilmədiyi mənbə — 404.
    assert (
        _post(
            client, {"action": "share", "source": row["id"], "offering": str(world["offerings"]["o5"].pk)}
        ).status_code
        == 404
    )
    response = _post(client, {"action": "unshare", "syllabus": row["id"], "offering": str(offering.pk)})
    assert response.status_code == 200, response.content
    assert not SyllabusShare.objects.exists()
    response = _post(client, {"action": "unshare", "syllabus": row["id"], "offering": str(offering.pk)})
    assert (response.status_code, response.json()["code"]) == (409, sharing.CODE_NOT_SHARED)


def _list(world):
    from apps.accounts.views.syllabus.section import build_syllabus_list_section

    request = RequestFactory().get("/accounts/profile/")
    request.user = world["teacher"]
    request.org_permissions = list(TEACHER_PERMS)
    request.organization = world["org"]
    return build_syllabus_list_section(request, organization=world["org"])["syllabus_list_section"]


def test_list_hides_shared_journal_from_missing_rows_and_notes_groups(world):
    before = {row["id"] for row in _list(world)["rows"]}
    assert str(world["offerings"]["o2"].pk) in before
    _share(world, "o2")
    rows = {row["id"]: row for row in _list(world)["rows"]}
    assert str(world["offerings"]["o2"].pk) not in rows
    assert "102A" in rows[str(world["source"].pk)]["reuse_note"]


def test_editor_shows_shared_groups_and_free_groups_with_project_select(world):
    _share(world, "o2")
    html = (
        _client(world)
        .get(reverse("accounts:profile"), {"section": "syllabus-editor", "version": str(world["version"].pk)})
        .content.decode()
    )
    assert "data-syl-share" in html
    assert 'data-syl-action="unshare"' in html and f'data-offering="{world["offerings"]["o2"].pk}"' in html
    assert "bootstrap-single-select__native" in html and "data-syl-share-select" in html
    assert f'value="{world["offerings"]["o3"].pk}"' in html  # sillabussuz öz qrupu
    assert f'value="{world["offerings"]["o5"].pk}"' not in html  # həmkarın qrupu
    assert "data-syl-reuse-confirm" in html
