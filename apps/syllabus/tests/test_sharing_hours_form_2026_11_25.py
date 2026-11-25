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
