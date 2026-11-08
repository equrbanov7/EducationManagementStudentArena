"""Jurnal banneri: «Bu fənn üzrə mövcud sillabuslar» + «dəyişmədən bu jurnala tətbiq et» (sahib 2026-11-08).

Yoxlanılır:
* siyahı sətrində qrup, müəllif və status var; baxış rolu (bir neçə müəllimin jurnalını görən) başqa müəllimlərin
  sillabuslarını da görür;
* müəllimin başqa qrup üçün sillabusu varsa «Sillabus yarat» əvvəl təsdiq təklifini açır; «Bəli» mövcud
  ``share`` ucundan keçir — yeni dosye yaranmır, mənbəyə toxunulmur;
* baxan rəhbər üçün nə təklif, nə «Sillabus yarat» düyməsi var, paylaşa da bilmir;
* tələbə / kənar müəllim JSON-u ala bilmir (404); sorğu sayı sətir sayı ilə böyümür.
"""

from __future__ import annotations

import json

from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import pytest

from apps.registrar.models import Enrollment
from apps.syllabus import services
from apps.syllabus.models import Syllabus, SyllabusShare
from apps.syllabus.tests.factories import activate_member
from apps.syllabus.tests.reuse_fixtures import CHAIR_PERMS, approved_syllabus, build_world, draft_for

pytestmark = pytest.mark.django_db

VIEWER_PERMS = [*CHAIR_PERMS, "journal.view", "course.view"]


@pytest.fixture()
def world(settings):
    # Sillabus testlərinin fixture-ı 8 bölməni doldurur — sərbəst iş açarı yanılı (apps/syllabus/tests/conftest.py).
    settings.ACADEMIC_SELFWORK_ENABLED = True
    data = build_world("jsp-peers")
    data["source"], data["version"] = approved_syllabus(data, "o1")
    viewer = data["teacher"].__class__.objects.create_user(
        "jsp-peers_v", "jsp-peers_v@x.test", "pw", first_name="Rəna", last_name="Baxışlı"
    )
    activate_member(data["org"], viewer, "journal_viewer", permissions=VIEWER_PERMS, level=70)
    data["viewer"] = viewer
    return data


def _client(world, key="teacher"):
    client = Client()
    client.force_login(world[key])
    session = client.session
    session["active_organization"] = world["org"].slug
    session.save()
    return client


def _peers(world, key="teacher", offering="o2"):
    url = reverse("registrar:journal_syllabus_peers", args=[world["offerings"][offering].pk])
    return _client(world, key).get(url)


def _journal(world, key="teacher", offering="o2"):
    response = _client(world, key).get(reverse("registrar:journal_detail", args=[world["offerings"][offering].pk]))
    assert response.status_code == 200
    return response.content.decode()


def _share(client, world, offering="o2"):
    return client.post(
        reverse("accounts:syllabus_reuse_action"),
        json.dumps(
            {"action": "share", "source": str(world["source"].pk), "offering": str(world["offerings"][offering].pk)}
        ),
        content_type="application/json",
    )


def test_list_shows_group_author_and_status(world):
    data = _peers(world).json()
    assert data["state"] == "missing"
    [row] = data["rows"]
    assert row["id"] == str(world["source"].pk)
    assert row["groups"] == ["101A"]
    assert row["author"] == "Nigar Həsənli"
    assert (row["status_key"], row["status_label"]) == ("approved", "Təsdiqlənib")
    assert row["by_instructor"] is True
    assert row["url"].endswith(f"section=syllabus-editor&syllabus={world['source'].pk}")


def test_reuse_prompt_offered_to_teacher_with_syllabus_for_another_group(world):
    data = _peers(world).json()
    [source] = data["reuse"]
    assert source["id"] == str(world["source"].pk)
    assert "101A qrupuna hazırladığınız sillabus var" in source["question"]
    assert "dəyişmədən bu jurnala da tətbiq edilsin" in source["question"]
    assert data["can_create"] is True
    html = _journal(world)
    assert "data-jd-syl-peers" in html and "data-jd-syl-reuse" in html and "data-jd-syl-cta" in html
    assert "journal_syllabus_peers.js" in html


def test_accepting_shares_the_same_syllabus_unchanged(world):
    source = world["source"]
    before = (source.current_version_id, source.approved_version_id, Syllabus.objects.count())
    response = _share(_client(world), world)
    assert response.status_code == 200, response.content
    source.refresh_from_db()
    assert (source.current_version_id, source.approved_version_id, Syllabus.objects.count()) == before
    offering = world["offerings"]["o2"]
    assert SyllabusShare.objects.filter(syllabus=source, offering=offering).exists()
    assert services.syllabus_for_offering_obj(offering).pk == source.pk
    # Jurnal artıq «sillabus yoxdur» deyil — təklif və banner yoxa çıxır; mənbənin sətrində qrup siyahısı böyüyür.
    after = _peers(world, offering="o3").json()
    assert after["rows"][0]["groups"] == ["101A", "102A"]
    assert _peers(world).json()["reuse"] == []
    assert "data-jd-syl-reuse" not in _journal(world)


def test_draft_on_target_blocks_reuse_prompt(world):
    draft_for(world, "o2")
    data = _peers(world).json()
    assert data["state"] == "draft"
    assert data["reuse"] == []
    assert [row["id"] for row in data["rows"]] == [str(world["source"].pk)]


def test_viewer_sees_all_teachers_syllabi_but_cannot_share_or_create(world):
    other, _version = approved_syllabus(world, "o5", user_key="teacher2")
    data = _peers(world, "viewer").json()
    rows = {row["id"]: row for row in data["rows"]}
    assert set(rows) == {str(world["source"].pk), str(other.pk)}
    assert rows[str(other.pk)]["author"] == "Elçin Quliyev"
    assert rows[str(other.pk)]["groups"] == ["105A"]
    assert rows[str(other.pk)]["by_instructor"] is False
    assert data["reuse"] == [] and data["can_create"] is False
    html = _journal(world, "viewer")
    assert "data-jd-syl-peers" in html
    assert "data-jd-syl-reuse" not in html and "data-jd-syl-cta" not in html
    assert "Sillabusu bu jurnalın müəllimi yaradır." in html
    response = _share(_client(world, "viewer"), world)
    assert response.status_code in {403, 404}
    assert not SyllabusShare.objects.exists()


def test_teacher_does_not_get_colleagues_syllabus_as_source(world):
    approved_syllabus(world, "o5", user_key="teacher2")
    data = _peers(world).json()
    assert [row["id"] for row in data["rows"]] == [str(world["source"].pk)]
    assert [row["id"] for row in data["reuse"]] == [str(world["source"].pk)]


def test_student_and_outsider_get_404(world):
    student = world["teacher"].__class__.objects.create_user("jsp-peers_s", "jsp-peers_s@x.test", "pw")
    activate_member(world["org"], student, "student", permissions=[])
    Enrollment.objects.create(organization=world["org"], student=student, offering=world["offerings"]["o2"])
    world["student"] = student
    assert _peers(world, "student").status_code == 404
    assert _peers(world, "teacher2").status_code == 404


def test_peer_queries_do_not_grow_with_rows(world):
    client = _client(world, "viewer")
    url = reverse("registrar:journal_syllabus_peers", args=[world["offerings"]["o2"].pk])
    client.get(url)  # sessiya / üzvlük keşləri

    def measure():
        with CaptureQueriesContext(connection) as ctx:
            assert client.get(url).status_code == 200
        return len(ctx.captured_queries)

    one = measure()
    approved_syllabus(world, "o3")
    approved_syllabus(world, "o5", user_key="teacher2")
    assert measure() == one
