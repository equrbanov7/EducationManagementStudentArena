"""Rəy 2026-10-21 (R06): ən son planın tətbiqi YALNIZ açıq təsdiqlə — önizləmə + server qapısı + audit.

Əvvəl qrupun qəbul ili üçün təsdiqlənmiş plan yoxdursa (və ya qəbul ili bilinmirsə) «Semestr açılışı» ən son
planı SƏSSİZ tətbiq edir, açılışları yaradır və yalnız sonra xəbərdarlıq qaytarırdı. İndi:

* ``generate_offerings(dry_run=True)`` — heç nə yazmadan hansı qrupun hansı plana düşdüyünü verir;
* əməlin ilk göndərişi (``fallback_reviewed`` yoxdur) fallback qrup varsa 409 + siyahı qaytarır, HEÇ NƏ yazmır;
* ``fallback_reviewed=1`` ilə yalnız ``confirm_fallback`` siyahısındakı qruplar ən son plandan açılır, qalanları
  atlanır və adı ilə bildirilir; kohort planı olan qruplar həmişə açılır; əməl idempotent qalır;
* audit sətri təsdiqlənən (qrup → plan) və atlanan qrupları daşıyır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

import pytest

from apps.audit.models import AuditLog
from apps.registrar import semester_open
from apps.registrar.models import CourseOffering
from apps.registrar.tests.test_cohort_plans_2026_10_19 import world  # noqa: F401 — pytest fixture
from apps.syllabus.tests.factories import activate_member

User = get_user_model()

pytestmark = pytest.mark.django_db

SEMESTER_KEYS = ["semester.view", "semester.open", "semester.lock", "semester.unlock"]


@pytest.fixture()
def office(world):  # noqa: F811
    user = User.objects.create_user("r06_office", "r06_office@x.test", "pw")
    activate_member(world["org"], user, "teaching_office_head", permissions=SEMESTER_KEYS, level=80)
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = world["org"].slug
    session.save()
    return client


def _post(client, world, **extra):  # noqa: F811
    data = {
        "action": "generate",
        "period": str(world["period"].pk),
        "semester_number": "3",
        "programs": [str(world["program"].pk)],
        **extra,
    }
    return client.post(reverse("registrar:semester_action"), data)


def _groups_with_offerings(world):  # noqa: F811
    return set(
        CourseOffering.objects.filter(organization=world["org"], period=world["period"]).values_list(
            "group__name", flat=True
        )
    )


def _audit(world):  # noqa: F811
    return (
        AuditLog.objects.filter(organization=world["org"], reason="semester: offerings generated from approved plans")
        .order_by("-created_at")
        .first()
    )


def test_dry_run_previews_fallbacks_without_writing(world):  # noqa: F811
    preview = semester_open.generate_offerings(
        organization=world["org"],
        period=world["period"],
        programs=[world["program"]],
        semester_number=3,
        dry_run=True,
    )
    assert _groups_with_offerings(world) == set()
    assert preview["created"] == 0 and preview["enrolled"] == 0
    rows = {item["group"]: item for item in preview["cohort_fallbacks"]}
    assert set(rows) == {"CH-231", "CH-X"}
    assert rows["CH-231"]["admission_year"] == 2023 and rows["CH-X"]["admission_year"] == 0
    for item in rows.values():
        assert item["plan_id"] == str(world["plan26"].pk) and item["plan_year"] == 2026
        assert item["plan_label"] and item["reason_label"]


def test_service_skips_unconfirmed_fallback_groups_and_stays_idempotent(world):  # noqa: F811
    params = {
        "organization": world["org"],
        "period": world["period"],
        "programs": [world["program"]],
        "semester_number": 3,
    }
    result = semester_open.generate_offerings(**params, confirmed_fallbacks={str(world["g23"].pk)})
    assert _groups_with_offerings(world) == {"CH-251", "CH-231"}
    assert [item["group"] for item in result["cohort_fallbacks"]] == ["CH-231"]
    assert [item["group"] for item in result["cohort_fallback_skipped"]] == ["CH-X"]
    assert any("CH-X" in message and "atlandı" in message for message in result["warnings"])

    again = semester_open.generate_offerings(**params, confirmed_fallbacks={str(world["g23"].pk), str(world["gx"].pk)})
    assert _groups_with_offerings(world) == {"CH-251", "CH-231", "CH-X"}
    assert again["created"] == 2 and again["existing"] == result["created"]
    assert again["cohort_fallback_skipped"] == []


def test_first_post_returns_preview_and_writes_nothing(world, office):  # noqa: F811
    response = _post(office, world)
    assert response.status_code == 409, response.content
    payload = response.json()
    assert payload["error"] == "fallback_confirmation_required"
    assert {item["group"] for item in payload["fallbacks"]} == {"CH-231", "CH-X"}
    assert all(item["plan_year"] == 2026 for item in payload["fallbacks"])
    assert _groups_with_offerings(world) == set()
    assert _audit(world) is None


def test_reviewed_post_without_confirmation_skips_fallback_groups(world, office):  # noqa: F811
    response = _post(office, world, fallback_reviewed="1")
    assert response.status_code == 200, response.content
    payload = response.json()
    assert _groups_with_offerings(world) == {"CH-251"}  # kohort planı olan qrup açılır
    assert {item["group"] for item in payload["cohort_fallback_skipped"]} == {"CH-231", "CH-X"}
    assert any("atlandı" in message for message in payload["warnings"])
    audit = _audit(world)
    assert audit.new_values["cohort_fallback_confirmed"] == []
    assert {item["group"] for item in audit.new_values["cohort_fallback_skipped"]} == {"CH-231", "CH-X"}


def test_confirmed_post_opens_fallback_groups_and_audits_the_plan(world, office):  # noqa: F811
    response = _post(office, world, fallback_reviewed="1", confirm_fallback=[str(world["g23"].pk), str(world["gx"].pk)])
    assert response.status_code == 200, response.content
    assert _groups_with_offerings(world) == {"CH-251", "CH-231", "CH-X"}
    audit = _audit(world)
    confirmed = {item["group"]: item for item in audit.new_values["cohort_fallback_confirmed"]}
    assert set(confirmed) == {"CH-231", "CH-X"}
    assert confirmed["CH-231"]["plan_id"] == str(world["plan26"].pk)
    assert confirmed["CH-231"]["plan_year"] == 2026 and confirmed["CH-231"]["admission_year"] == 2023
    assert audit.new_values["cohort_fallback_skipped"] == []
    assert set(audit.new_values["cohort_fallback_groups"]) == {"CH-231", "CH-X"}


def test_no_fallback_groups_means_no_confirmation_step(world, office):  # noqa: F811
    from apps.organizations.models import OrgUnit

    OrgUnit.objects.filter(pk__in=[world["g23"].pk, world["gx"].pk]).update(is_active=False)
    response = _post(office, world)
    assert response.status_code == 200, response.content
    assert _groups_with_offerings(world) == {"CH-251"}
    assert response.json()["cohort_fallback_skipped"] == []
