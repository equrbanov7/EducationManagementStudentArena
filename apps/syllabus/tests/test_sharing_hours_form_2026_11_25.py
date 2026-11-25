"""Sahib 2026-11-25: eyni fənnin əyani qrupu üçün bir sillabus (məs. 45 saat), qiyabi qrupu üçün başqası (25 saat) —
birini dəyişmək o birinə TOXUNMAMALIDIR.

* «Bir sillabus — bir neçə jurnal» paylaşımı (``SyllabusShare``) hədəf jurnalın plan saatı mənbənin saatından
  fərqlidirsə rədd olunur (``reuse.hours_differ``, «bağla» ilə eyni kod) və heç yerdə təklif olunmur: dialoq kartı,
  redaktorun «Bu qrupda da istifadə et» siyahısı, jurnalın «dəyişmədən tətbiq edilsin?» təklifi;
* ``program_for_offering`` qrupun təhsil formasına uyğun proqramı seçir — qiyabi qrup eyni ixtisas bölməsindəki
  əyani proqramın plan saatını götürmür.
"""

from __future__ import annotations

import json

from django.test import Client
from django.urls import reverse

import pytest

from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Program
from apps.registrar.plan_hours import plan_hours_for_offering, program_for_offering
from apps.syllabus.models import SyllabusShare
from apps.syllabus.services import sharing
from apps.syllabus.services.reuse_rules import CODE_HOURS_DIFFER
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.factories import PLAN_HOURS
from apps.syllabus.tests.reuse_fixtures import _plan, actor, approved_syllabus, build_world
from core.constants import OrgUnitType

pytestmark = pytest.mark.django_db

QIYABI_HOURS = {"lecture": 16, "seminar": 8}


@pytest.fixture()
def world():
    data = build_world("syl-form")
    spec_a = data["groups"]["g1"].parent
    # Eyni ixtisas bölməsində QİYABİ proqram + öz planı; adı əyani proqramdan sonra gəlir (köhnə ``.first()``
    # əyanini seçirdi).
    data["programs"]["a_part"] = Program.objects.create(
        organization=data["org"],
        code="PAQ",
        name="Proqram A qiyabi",
        specialty_unit=spec_a,
        education_form="part_time",
    )
    data["curricula"]["a_part"] = _plan(data["org"], data["programs"]["a_part"], data["subject"], QIYABI_HOURS)
    data["groups"]["g6"] = OrgUnit.objects.create(
        organization=data["org"],
        name="1106A",
        slug="syl-form-1106a",
        unit_type=OrgUnitType.GROUP,
        parent=spec_a,
        settings={"education_form": "part_time"},
    )
    data["offerings"]["o6"] = CourseOffering.objects.create(
        organization=data["org"],
        subject=data["subject"],
        period=data["period"],
        group=data["groups"]["g6"],
        instructor=data["teacher"],
        lesson_hours=60,
    )
    data["source"], data["version"] = approved_syllabus(data, "o1")
    return data


def _client(world, key="teacher"):
    client = Client()
    client.force_login(world[key])
    session = client.session
    session["active_organization"] = world["org"].slug
    session.save()
    return client


def _post_share(client, world, key):
    payload = {"action": "share", "source": str(world["source"].pk), "offering": str(world["offerings"][key].pk)}
    return client.post(reverse("accounts:syllabus_reuse_action"), json.dumps(payload), content_type="application/json")


def _peers(world, key):
    url = reverse("registrar:journal_syllabus_peers", args=[world["offerings"][key].pk])
    return _client(world).get(url).json()


# ── program_for_offering: təhsil forması ───────────────────────────────────────


def test_part_time_group_resolves_the_part_time_programme_and_its_hours(world):
    offering = world["offerings"]["o6"]
    assert program_for_offering(offering) == world["programs"]["a_part"]
    assert plan_hours_for_offering(offering) == QIYABI_HOURS
    # Əyani qrup (forma yazılmayıb) — köhnə qayda: bölmənin ilk proqramı.
    assert program_for_offering(world["offerings"]["o1"]) == world["programs"]["a"]
    assert plan_hours_for_offering(world["offerings"]["o1"]) == PLAN_HOURS


def test_full_time_group_keeps_the_full_time_programme(world):
    group = world["groups"]["g2"]
    group.settings = {"education_form": "full_time"}
    group.save(update_fields=["settings"])
    offering = CourseOffering.objects.select_related("group").get(pk=world["offerings"]["o2"].pk)
    assert program_for_offering(offering) == world["programs"]["a"]


def test_form_without_a_matching_programme_falls_back_to_the_old_rule(world):
    group = world["groups"]["g2"]
    group.settings = {"education_form": "distance"}
    group.save(update_fields=["settings"])
    offering = CourseOffering.objects.select_related("group").get(pk=world["offerings"]["o2"].pk)
    assert program_for_offering(offering) == world["programs"]["a"]


# ── Paylaşım: saat fərqlidirsə yox ─────────────────────────────────────────────


@pytest.mark.parametrize("key", ["o3", "o6"])  # o3 — başqa ixtisasın 30/30 planı; o6 — eyni ixtisasın qiyabi planı
def test_service_refuses_share_when_hours_differ(world, key):
    offering = world["offerings"][key]
    with pytest.raises(TransitionDenied) as denied:
        sharing.share(
            source=world["source"],
            offering=offering,
            actor=actor(world),
            target_hours=plan_hours_for_offering(offering),
        )
    assert denied.value.code == CODE_HOURS_DIFFER
    assert not SyllabusShare.objects.exists()


def test_http_share_refused_with_copy_hint_and_nothing_changes(world):
    response = _post_share(_client(world), world, "o6")
    assert response.status_code == 409, response.content
    body = response.json()
    assert body["code"] == CODE_HOURS_DIFFER
    assert "«Kopyala və uyğunlaşdır»" in body["error"]
    assert not SyllabusShare.objects.exists()


def test_share_still_works_when_hours_match(world):
    response = _post_share(_client(world), world, "o2")
    assert response.status_code == 200, response.content
    assert SyllabusShare.objects.filter(syllabus=world["source"], offering=world["offerings"]["o2"]).exists()


def test_dialog_card_does_not_offer_share_on_hours_mismatch(world):
    client = _client(world)

    def card(key):
        url = reverse("accounts:syllabus_reuse_options")
        options = client.get(url, {"offering": str(world["offerings"][key].pk)}).json()
        [row] = [row for row in options["siblings"] if row["id"] == str(world["source"].pk)]
        return row

    mismatch = card("o6")
    assert mismatch["can_share"] is False
    assert "«Kopyala və uyğunlaşdır»" in mismatch["share_reason"]
    assert card("o2")["can_share"] is True


def test_journal_peers_prompt_not_offered_on_hours_mismatch(world):
    assert _peers(world, "o6")["reuse"] == []
    assert _peers(world, "o3")["reuse"] == []
    # Saat eynidir — təklif qalır.
    assert [row["id"] for row in _peers(world, "o2")["reuse"]] == [str(world["source"].pk)]


def test_editor_free_list_skips_other_form_group(world):
    html = (
        _client(world)
        .get(reverse("accounts:profile"), {"section": "syllabus-editor", "version": str(world["version"].pk)})
        .content.decode()
    )
    assert f'value="{world["offerings"]["o2"].pk}"' in html
    assert f'value="{world["offerings"]["o6"].pk}"' not in html
    assert f'value="{world["offerings"]["o3"].pk}"' not in html


# ── Toplu yol (``syllabus_reuse_targets``) — tək açılışla EYNİ seçim ───────────


def test_batched_programme_and_hours_match_the_single_lookup(world):
    from apps.registrar.public import plan_hours_by_offering, programs_by_offering

    offerings = list(
        CourseOffering.objects.filter(pk__in=[row.pk for row in world["offerings"].values()]).select_related(
            "group", "group__parent"
        )
    )
    assert plan_hours_by_offering(offerings) == {row.pk: plan_hours_for_offering(row) for row in offerings}
    assert programs_by_offering(offerings) == {row.pk: program_for_offering(row) for row in offerings}
    o6 = next(row for row in offerings if row.pk == world["offerings"]["o6"].pk)
    assert plan_hours_by_offering([o6]) == {o6.pk: QIYABI_HOURS}
    assert programs_by_offering([o6]) == {o6.pk: world["programs"]["a_part"]}


def test_bulk_apply_copies_into_the_part_time_journal_with_its_own_hours(world):
    from apps.syllabus.models import Syllabus

    client = _client(world)
    options = client.get(reverse("accounts:syllabus_reuse_options"), {"offering": str(world["offerings"]["o2"].pk)})
    [row] = [row for row in options.json()["siblings"] if row["id"] == str(world["source"].pk)]
    assert row["modes"][str(world["offerings"]["o6"].pk)] == "copy"  # «bağla» YOX — saat fərqlidir
    payload = {
        "action": "bulk",
        "source": str(world["source"].pk),
        "offerings": [str(world["offerings"][key].pk) for key in ("o2", "o6")],
    }
    response = client.post(
        reverse("accounts:syllabus_reuse_action"), json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200, response.content
    statuses = {item["offering"]: item["status"] for item in response.json()["results"]}
    assert statuses == {str(world["offerings"]["o2"].pk): "linked", str(world["offerings"]["o6"].pk): "copied"}
    copy = Syllabus.objects.select_related("current_version").get(offering=world["offerings"]["o6"])
    assert copy.reused_from_id is None
    assert copy.program_id == world["programs"]["a_part"].pk
    assert copy.current_version.plan_hours == QIYABI_HOURS


# ── Versiyasında saat olmayan (köçürülmüş) mənbə: təklif = POST qərarı ─────────


@pytest.fixture()
def legacy_world(world):
    from apps.syllabus.models import SyllabusVersion

    SyllabusVersion.objects.filter(syllabus=world["source"]).update(plan_hours={})
    world["source"].refresh_from_db()
    return world


def _card(client, world, key):
    url = reverse("accounts:syllabus_reuse_options")
    options = client.get(url, {"offering": str(world["offerings"][key].pk)}).json()
    [row] = [row for row in options["siblings"] if row["id"] == str(world["source"].pk)]
    return row


def test_legacy_source_uses_its_journal_hours_in_dialog_prompt_and_post(legacy_world):
    world = legacy_world
    client = _client(world)
    assert _card(client, world, "o6")["can_share"] is False
    assert _peers(world, "o6")["reuse"] == []
    assert _post_share(client, world, "o6").status_code == 409
    # Saat eynidir — üç yol da razıdır.
    assert _card(client, world, "o2")["can_share"] is True
    assert [row["id"] for row in _peers(world, "o2")["reuse"]] == [str(world["source"].pk)]
    assert _post_share(client, world, "o2").status_code == 200
