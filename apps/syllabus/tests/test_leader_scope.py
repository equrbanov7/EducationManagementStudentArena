"""Rəhbərin «Hamısı | Mənim fənlərim» açarı (sahib 2026-10-08).

Geniş əhatəli (kafedra/fakültə/org) rəhbər siyahıda HAMINI görür, amma özü də dərs
deyir — öz sillabuslarına daralmaq üçün açar lazımdır.  Yoxlanılır:

* açar YALNIZ geniş əhatəli + dərs deyən rəhbərə görünür; dərs deməyən rəhbər və
  adi müəllim onu görmür (müəllimin siyahısı dəyişmir);
* «Mənim fənlərim» dəsti, KPI və status sayğacları ``own_q`` üzrədir;
* başqasının sətrində müəllif əməlləri (redaktə, geri çağırma, bağ) yoxdur, öz
  açılışında isə «Sillabus yarat» müəllim kimi işləyir; icazəsiz rəhbərə düymə çıxmır.
"""

from __future__ import annotations

import json

from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import pytest

from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering
from apps.syllabus.tests.factories import activate_member
from apps.syllabus.tests.reuse_fixtures import (
    CHAIR_PERMS,
    TEACHER_PERMS,
    approved_syllabus,
    build_world,
    draft_for,
)
from core.constants import OrgUnitType, RoleScopeType

pytestmark = pytest.mark.django_db


def _offering(world, name, instructor):
    group = OrgUnit.objects.create(
        organization=world["org"],
        name=name,
        slug=f"{world['org'].slug}-{name.lower()}",
        unit_type=OrgUnitType.GROUP,
        parent=world["groups"]["g1"].parent,
    )
    return CourseOffering.objects.create(
        organization=world["org"],
        subject=world["subject"],
        period=world["period"],
        group=group,
        instructor=instructor,
        lesson_hours=60,
    )


@pytest.fixture()
def world():
    data = build_world("syl-leader-scope")
    head = data["head"]
    # Rəhbər həm də müəllimdir: ikinci (müəllim) üzvlüyü + öz açılışları.
    activate_member(
        data["org"],
        head,
        "teacher",
        permissions=TEACHER_PERMS,
        scope_unit=data["chair"],
        scope_type=RoleScopeType.COURSE,
    )
    data["offerings"]["h1"] = _offering(data, "201A", head)
    data["offerings"]["h2"] = _offering(data, "202A", head)
    from django.contrib.auth import get_user_model

    idle = get_user_model().objects.create_user("syl-leader-idle", "syl-leader-idle@x.test", "pw")
    activate_member(
        data["org"],
        idle,
        "chair_head",
        permissions=CHAIR_PERMS,
        scope_unit=data["chair"],
        scope_type=RoleScopeType.UNIT,
    )
    data["idle"] = idle
    approved_syllabus(data, "o1")  # müəllimin təsdiqlənmiş sillabusu
    draft_for(data, "o5", user_key="teacher2")  # ikinci müəllimin qaralaması
    draft_for(data, "h1", user_key="head")  # rəhbərin öz qaralaması
    return data


def _permissions(world, key):
    from apps.syllabus import services

    return list(services.resolve_actor(world[key], world["org"]).permissions)


def _section(world, key, **params):
    from apps.accounts.views.syllabus.section import build_syllabus_list_section

    request = RequestFactory().get("/accounts/profile/", params)
    request.user = world[key]
    request.org_permissions = _permissions(world, key)
    request.organization = world["org"]
    return build_syllabus_list_section(request, organization=world["org"])["syllabus_list_section"]


def _kpi(section, key):
    return next(card["value"] for card in section["kpis"] if card["key"] == key)


def _chip(section, key):
    return next(chip["count"] for chip in section["chips"] if chip["key"] == key)


def test_teaching_leader_sees_the_switch_and_others_do_not(world):
    section = _section(world, "head")
    assert [(chip["key"], chip["active"]) for chip in section["scope_switch"]["chips"]] == [("", True), ("mine", False)]
    assert section["filters"]["scope"] == ""  # default «Hamısı»
    assert _section(world, "idle")["scope_switch"] is None  # dərs deməyən rəhbər
    assert _section(world, "teacher")["scope_switch"] is None  # adi müəllim


def test_mine_scope_filters_rows_kpis_and_status_counts(world):
    everything = _section(world, "head")
    mine = _section(world, "head", scope="mine")
    assert mine["filters"]["scope"] == "mine"
    assert [(chip["key"], chip["active"]) for chip in mine["scope_switch"]["chips"]] == [("", False), ("mine", True)]
    # Hamısı: 3 sillabus (müəllim, ikinci müəllim, rəhbər) + rəhbərin sillabussuz açılışı (h2).
    assert _kpi(everything, "total") == 4
    assert (_chip(everything, "approved"), _chip(everything, "draft")) == (1, 2)
    # Mənim fənlərim: yalnız rəhbərin qaralaması + sillabussuz açılışı.
    assert _kpi(mine, "total") == 2
    assert (_chip(mine, "approved"), _chip(mine, "draft")) == (0, 1)
    assert _kpi(mine, "missing") == 1
    groups = {(row["kind"], row["code"]) for row in mine["rows"]}
    assert len(mine["rows"]) == 2 and groups == {("missing", "RSE101"), ("syllabus", "RSE101")}
    syllabus_row = next(row for row in mine["rows"] if row["kind"] == "syllabus")
    assert [action["key"] for action in syllabus_row["actions"]][0] in {"reuse", "resume"}


def test_plain_teacher_list_is_unchanged_by_the_scope_param(world):
    plain = _section(world, "teacher")
    forced = _section(world, "teacher", scope="mine")
    assert forced["filters"]["scope"] == ""
    assert [row["id"] for row in forced["rows"]] == [row["id"] for row in plain["rows"]]
    assert forced["kpis"] == plain["kpis"]


def test_leader_rows_only_offer_actions_the_leader_may_run(world):
    rows = {row["id"]: row for row in _section(world, "head")["rows"]}
    from apps.syllabus.models import Syllabus

    foreign_draft = Syllabus.objects.get(offering=world["offerings"]["o5"])
    own_draft = Syllabus.objects.get(offering=world["offerings"]["h1"])
    foreign_keys = [action["key"] for action in rows[str(foreign_draft.pk)]["actions"]]
    assert "resume" not in foreign_keys and "view" in foreign_keys
    own_keys = [action["key"] for action in rows[str(own_draft.pk)]["actions"]]
    assert "resume" in own_keys
    missing = rows[str(world["offerings"]["h2"].pk)]
    assert [action["key"] for action in missing["actions"]] == ["reuse", "create"]


def test_leader_creates_own_syllabus_like_a_teacher_but_not_for_others(world):
    client = Client()
    client.force_login(world["head"])
    session = client.session
    session["active_organization"] = world["org"].slug
    session.save()
    url = reverse("accounts:syllabus_action")

    def create(key):
        return client.post(
            url,
            data=json.dumps({"action": "create", "offering": str(world["offerings"][key].pk)}),
            content_type="application/json",
        )

    assert create("h2").status_code == 200
    assert create("o2").status_code == 404  # başqasının açılışı


def test_leader_without_edit_permission_gets_no_create_buttons(world):
    from django.contrib.auth import get_user_model

    viewer = get_user_model().objects.create_user("syl-leader-view", "syl-leader-view@x.test", "pw")
    activate_member(
        world["org"],
        viewer,
        "dean_like",
        permissions=["syllabus.view", "syllabus.review", "grade.input"],
        scope_unit=world["chair"],
        scope_type=RoleScopeType.UNIT,
    )
    world["viewer"] = viewer
    offering = _offering(world, "301A", viewer)
    section = _section(world, "viewer")
    assert section["scope_switch"] is not None
    missing = next(row for row in section["rows"] if row["id"] == str(offering.pk))
    assert missing["actions"] == []
    assert all("new_version" not in [a["key"] for a in row["actions"]] for row in section["rows"])


def test_switch_costs_a_bounded_number_of_queries(world):
    _section(world, "head")  # isinmə
    with CaptureQueriesContext(connection) as small:
        _section(world, "head")
    from apps.syllabus import services

    for index in range(4):
        offering = _offering(world, f"40{index}A", world["teacher2"])
        services.create_draft(
            organization=world["org"],
            subject=world["subject"],
            period=world["period"],
            actor=services.resolve_actor(world["teacher2"], world["org"]),
            offering=offering,
            chair_unit=offering.group.parent,
            author=world["teacher2"],
        )
    with CaptureQueriesContext(connection) as large:
        _section(world, "head")
    assert len(large.captured_queries) == len(small.captured_queries)


def test_reuse_is_not_offered_to_a_leader_from_someone_elses_syllabus(world):
    """Rəhbər başqa müəllimin sillabusunu GÖRÜR, amma ona bağlana bilmir — təklif çıxmamalıdır."""
    idle = world["idle"]
    activate_member(
        world["org"],
        idle,
        "teacher",
        permissions=TEACHER_PERMS,
        scope_unit=world["chair"],
        scope_type=RoleScopeType.COURSE,
    )
    offering = _offering(world, "501A", idle)
    section = _section(world, "idle")
    assert section["scope_switch"] is not None  # indi dərs deyir
    missing = next(row for row in section["rows"] if row["id"] == str(offering.pk))
    keys = [action["key"] for action in missing["actions"]]
    assert "reuse" not in keys and keys[0] == "create"
