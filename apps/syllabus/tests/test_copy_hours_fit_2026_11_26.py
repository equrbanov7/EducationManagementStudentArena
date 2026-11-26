"""«Kopyala və uyğunlaşdır» — saat fərqi səssiz tətbiq olunmur (sahib 2026-11-26).

Mənbənin dərs saatı jurnalın saatından fərqlidirsə (və ya köhnə sistemdən gələn mənbənin saatı bilinmirsə):

* dialoq kartı «Mənbə: … saat (N həftə) · Bu jurnal: … saat (M sətir)» və «Dərs saatları fərqlidir» göstərir,
  kopyalananda nə olacağını («N sətir kəsiləcək» / «N boş sətir əlavə olunacaq») əvvəlcədən deyir və təsdiq istəyir;
* SERVER qaralamaya hədəfin plan saatını yazır, cədvəli hədəfin sətir sayına gətirir (sondan kəsir / boş əlavə edir);
* saat EYNİDİRSƏ köhnə davranış dəyişmir; paylaşım saat fərqində yenə rədd olunur (PR #473).
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.test import Client
from django.urls import reverse

import pytest

from apps.audit.models import AuditLog
from apps.syllabus import services
from apps.syllabus.constants import LESSON_HOUR_KINDS, SectionKey
from apps.syllabus.models import Syllabus, SyllabusVersion
from apps.syllabus.services import copy_fit
from apps.syllabus.services.reuse_rules import CODE_HOURS_DIFFER
from apps.syllabus.tests.factories import PLAN_HOURS
from apps.syllabus.tests.reuse_fixtures import OTHER_HOURS, actor, approved_syllabus, build_world, target
from apps.syllabus.week_plan import fit_week_rows

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    return build_world("syl-copy-fit")


def _client(world):
    client = Client()
    client.force_login(world["teacher"])
    session = client.session
    session["active_organization"] = world["org"].slug
    session.save()
    return client


def _post(client, payload):
    return client.post(
        reverse("accounts:syllabus_reuse_action"),
        data=json.dumps({key: str(value) for key, value in payload.items()}),
        content_type="application/json",
    )


def _card(client, world, offering_key, source):
    options = client.get(
        reverse("accounts:syllabus_reuse_options"), {"offering": str(world["offerings"][offering_key].pk)}
    ).json()
    return next(row for row in options["siblings"] if row["id"] == str(source.pk))


def _week(version) -> list:
    return version.sections.get(section_id=SectionKey.WEEK.value).data["rows"]


def _sums(rows) -> dict:
    return {kind: sum(int(row.get(kind) or 0) for row in rows) for kind in LESSON_HOUR_KINDS}


def _rows(count, *, lecture=2):
    return [
        {"topic": f"Mövzu {index + 1}", "outcome": "", "lecture": lecture, "seminar": 0, "lab": 0}
        for index in range(count)
    ]


# ── Qayda (week_plan.fit_week_rows) ────────────────────────────────────────────


def test_fit_cuts_extra_rows_from_the_end():
    rows, info = fit_week_rows(_rows(15), {"lecture": 20})
    assert info == {"before": 15, "after": 10, "cut": 5, "added": 0}
    assert [row["topic"] for row in rows] == [f"Mövzu {index + 1}" for index in range(10)]
    assert _sums(rows)["lecture"] == 20


def test_fit_adds_empty_rows_and_redistributes_hours():
    rows, info = fit_week_rows(_rows(5), {"lecture": 25})
    assert info == {"before": 5, "after": 13, "cut": 0, "added": 8}
    assert [row["topic"] for row in rows[5:]] == [""] * 8
    assert _sums(rows) == {"lecture": 25, "seminar": 0, "lab": 0}


def test_fit_without_target_hours_changes_nothing():
    rows, info = fit_week_rows(_rows(4), {})
    assert len(rows) == 4 and info["cut"] == info["added"] == 0


def test_copy_plan_states():
    assert copy_fit.copy_state({"lecture": 30}, {"lecture": 30}) == copy_fit.SAME
    assert copy_fit.copy_state({"lecture": 30}, {"lecture": 20}) == copy_fit.DIFFER
    assert copy_fit.copy_state({}, {"lecture": 20}) == copy_fit.SOURCE_UNKNOWN
    assert copy_fit.copy_state({"lecture": 30}, {}) == copy_fit.TARGET_UNKNOWN
    plan = copy_fit.copy_plan(source_hours_value={"lecture": 45}, target_hours={"lecture": 25}, row_count=15)
    assert (plan["fit"], plan["target_rows"], plan["cut"], plan["added"]) == (True, 13, 2, 0)
    same = copy_fit.copy_plan(source_hours_value={"lecture": 30}, target_hours={"lecture": 30}, row_count=17)
    assert (same["fit"], same["cut"], same["added"]) == (False, 0, 0)


# ── Yazı yolu (copy_adjust) ────────────────────────────────────────────────────


def test_copy_with_fewer_target_hours_cuts_rows_and_takes_target_hours(world):
    source, source_version = approved_syllabus(world, "o1")
    hours = {"lecture": 20}
    _syllabus, version = services.reuse.copy_adjust(
        source=source, target=target(world, "o3", hours=hours), actor=actor(world)
    )
    version.refresh_from_db()
    rows = _week(version)
    assert version.plan_hours == hours
    assert len(rows) == 10  # ceil(20 / 2) — 16 sətirdən 6-sı sondan kəsildi
    assert _sums(rows) == {"lecture": 20, "seminar": 0, "lab": 0}
    assert [row["topic"] for row in rows] == [row["topic"] for row in _week(source_version)][:10]
    audit = next(
        row
        for row in AuditLog.objects.filter(resource_type="syllabus.version", resource_id=str(version.pk))
        if (row.changes or {}).get("week_fit")
    )
    assert audit.changes["week_fit"] == {"state": "differ", "before": 16, "after": 10, "cut": 6, "added": 0}


def test_copy_with_more_target_hours_adds_empty_rows(world):
    source, _version = approved_syllabus(world, "o1")
    hours = {"lecture": 40, "seminar": 10}
    _syllabus, version = services.reuse.copy_adjust(
        source=source, target=target(world, "o3", hours=hours), actor=actor(world)
    )
    rows = _week(version)
    assert len(rows) == 20
    assert all(not row["topic"] for row in rows[16:])  # 4 boş sətir
    assert _sums(rows) == {"lecture": 40, "seminar": 10, "lab": 0}


def test_copy_from_a_source_with_unknown_hours_is_fitted_to_the_target(world):
    source, source_version = approved_syllabus(world, "o1")
    SyllabusVersion.objects.filter(pk=source_version.pk).update(plan_hours={})  # köhnə sistemdən — saat yoxdur
    source = Syllabus.objects.select_related("approved_version", "current_version").get(pk=source.pk)
    _syllabus, version = services.reuse.copy_adjust(source=source, target=target(world, "o3"), actor=actor(world))
    version.refresh_from_db()
    rows = _week(version)
    assert version.plan_hours == OTHER_HOURS
    assert len(rows) == 15
    assert _sums(rows) == {"lecture": 30, "seminar": 30, "lab": 0}


def test_copy_with_same_hours_keeps_the_old_behaviour(world):
    source, source_version = approved_syllabus(world, "o1")
    _syllabus, version = services.reuse.copy_adjust(source=source, target=target(world, "o2"), actor=actor(world))
    version.refresh_from_db()
    assert version.plan_hours == PLAN_HOURS
    assert _week(version) == _week(source_version)  # 16 sətir (sonuncu boş) — heç nə kəsilmir


# ── HTTP: dialoq + POST ────────────────────────────────────────────────────────


def test_dialog_warns_and_previews_the_cut_and_the_post_applies_it(world):
    source, _version = approved_syllabus(world, "o1")
    client = _client(world)
    fit = _card(client, world, "o3", source)["copy_fit"]
    assert fit["state"] == "differ" and fit["confirm"] is True
    assert fit["warning"] == "Dərs saatları fərqlidir"
    assert fit["line"] == "Mənbə: 60 saat (16 həftə) · Bu jurnal: 60 saat (15 sətir)"
    assert "sondan 1 sətir kəsiləcək" in fit["action"]
    assert fit["confirm_label"] == "Bəli, uyğunlaşdırıb kopyala"

    # Server müştəriyə etibar etmir: təsdiq bayrağı olmadan da eyni uyğunlaşma.
    response = _post(client, {"action": "copy", "source": source.pk, "offering": world["offerings"]["o3"].pk})
    assert response.status_code == 200, response.content
    version = SyllabusVersion.objects.get(pk=response.json()["version"])
    assert version.plan_hours == OTHER_HOURS and len(_week(version)) == 15


def test_dialog_for_a_legacy_source_without_hours(world):
    source, source_version = approved_syllabus(world, "o1")
    SyllabusVersion.objects.filter(pk=source_version.pk).update(plan_hours={})
    Syllabus.objects.filter(pk=source.pk).update(offering=None)  # köhnə sistemdən — jurnalı da yoxdur
    fit = _card(_client(world), world, "o3", source)["copy_fit"]
    assert fit["state"] == "source_unknown" and fit["confirm"] is True
    assert fit["warning"] == "Mənbənin dərs saatı məlum deyil"
    assert fit["line"] == "Mənbə: saat məlum deyil (16 həftə) · Bu jurnal: 60 saat (15 sətir)"


def test_dialog_more_rows_needed_says_how_many_empty_rows_are_added(world):
    from apps.syllabus.models import SyllabusSection

    source, source_version = approved_syllabus(world, "o1")
    week = SyllabusSection.objects.get(version=source_version, section_id=SectionKey.WEEK.value)
    SyllabusSection.objects.filter(pk=week.pk).update(data={**week.data, "rows": week.data["rows"][:5]})
    fit = _card(_client(world), world, "o3", source)["copy_fit"]
    assert fit["line"] == "Mənbə: 60 saat (5 həftə) · Bu jurnal: 60 saat (15 sətir)"
    assert (fit["cut"], fit["added"]) == (0, 10)
    assert "10 boş sətir əlavə olunacaq" in fit["action"]


def test_dialog_same_hours_has_no_warning(world):
    source, _version = approved_syllabus(world, "o1")
    fit = _card(_client(world), world, "o2", source)["copy_fit"]
    assert (fit["state"], fit["confirm"], fit["warning"], fit["cut"], fit["added"]) == ("same", False, "", 0, 0)


def test_share_is_still_refused_when_hours_differ(world):
    source, _version = approved_syllabus(world, "o1")
    response = _post(_client(world), {"action": "share", "source": source.pk, "offering": world["offerings"]["o3"].pk})
    assert response.status_code == 409
    assert response.json()["code"] == CODE_HOURS_DIFFER


def test_week_row_counts_is_one_query(world, django_assert_num_queries):
    _source, version = approved_syllabus(world, "o1")
    with django_assert_num_queries(1):
        assert copy_fit.week_row_counts([version]) == {version.pk: 16}


def test_shipped_js_asks_before_copying():
    base = Path(settings.BASE_DIR) / "apps/accounts/static/accounts/js/profile"
    reuse = (base / "syllabus_reuse.js").read_text(encoding="utf-8")
    fit_js = (base / "syllabus_reuse_fit.js").read_text(encoding="utf-8")
    assert "fit.needsConfirm(state.modal, source)" in reuse
    assert "window.EMSSyllabusReuseFit = {" in fit_js
    template = (
        Path(settings.BASE_DIR) / "apps/accounts/templates/accounts/profile/sections/syllabus/_reuse_dialog.html"
    ).read_text(encoding="utf-8")
    assert "data-syl-reuse-fit" in template and "data-syl-reuse-copy-label" in template
