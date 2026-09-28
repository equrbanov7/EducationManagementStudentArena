"""Audit 2026-09-28 — sillabus iş axınının bütövlüyü (SYL-1, SYL-2, SYL-3, SYL-4, SYL-6, SYL-7).

* SYL-1 — dörd göz: qərar səlahiyyəti olan müəllif (fənni tədris edən kafedra
  müdiri) ÖZ sillabusunu təsdiqləyə / qaytara / rədd edə bilmir; qərar növbəti
  pilləyə (açarı olan dekan, org-wide aktor) keçir, düymələr müəllifdən gizlənir.
* SYL-2 — yeni versiya təsdiqlənmiş nüsxədən budaqlanır, müqayisə bazası da odur.
* SYL-3 — autosave/plan saatı yazısı statusu KİLİDLİ sətirdə yoxlayır.
* SYL-4 — uğursuz göndərmə heç bir iz qoymur (qaldırma, audit sətri yoxdur).
* SYL-6 — ikiqat «yeni versiya» 500 vermir.
* SYL-7 — müəllif olmayanın redaktor GET-i yazmır; tamamlanma təşkilat çəkiləri ilə.
"""

from __future__ import annotations

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, RequestFactory
from django.urls import reverse

import pytest

from apps.organizations.models import OrgUnit
from apps.syllabus import services
from apps.syllabus.constants import SectionKey, SyllabusStatus
from apps.syllabus.models import ChangeKind, SyllabusSection, SyllabusVersion
from apps.syllabus.state_machine import Transition, TransitionDenied, check
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)
from core.constants import OrgUnitType, RoleScopeType

User = get_user_model()

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    org = make_org("syl-audit28")
    faculty = OrgUnit.objects.create(
        organization=org, name="Fakültə", slug=f"{org.slug}-faculty", unit_type=OrgUnitType.FACULTY
    )
    stack = make_academic_stack(org, code="AUD128")
    chair = stack["chair"]
    chair.parent = faculty
    chair.save()
    chair.refresh_from_db()

    teacher = User.objects.create_user("a28_teacher", "a28_teacher@x.test", "pw")
    other_teacher = User.objects.create_user("a28_other", "a28_other@x.test", "pw")
    chair_head = User.objects.create_user("a28_chair", "a28_chair@x.test", "pw")
    dean = User.objects.create_user("a28_dean", "a28_dean@x.test", "pw")
    rim = User.objects.create_user("a28_rim", "a28_rim@x.test", "pw")

    activate_member(org, teacher, "teacher", permissions=TEACHER_PERMS)
    activate_member(org, other_teacher, "teacher", permissions=TEACHER_PERMS)
    # Kafedra müdiri həm də müəllimdir (fənni özü tədris edir).
    activate_member(
        org,
        chair_head,
        "chair_head",
        permissions=CHAIR_PERMS + TEACHER_PERMS,
        scope_unit=chair,
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    # Qərar açarı olan fakültə səviyyəli aktor (növbəti pillə).
    activate_member(
        org, dean, "dean", permissions=CHAIR_PERMS, scope_unit=faculty, level=80, scope_type=RoleScopeType.UNIT
    )
    activate_member(org, rim, "ikt_rehber", permissions=["syllabus.*"], level=88)
    return {
        "org": org,
        "stack": stack,
        "teacher": teacher,
        "other_teacher": other_teacher,
        "chair_head": chair_head,
        "dean": dean,
        "rim": rim,
    }


def _actor(user, org):
    return services.resolve_actor(user, org)


def _fill(version, actor, *, skip=()):
    for section_id, data in complete_section_data().items():
        if section_id in {SectionKey.PREV.value, SectionKey.SEND.value, *skip}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=actor)


def _draft(world, author_key="teacher", *, stack=None):
    org = world["org"]
    author = world[author_key]
    stack = stack or world["stack"]
    actor = _actor(author, org)
    offering = make_offering(org, stack, author)
    _syllabus, version = services.create_draft(
        organization=org,
        subject=stack["subject"],
        period=stack["period"],
        actor=actor,
        offering=offering,
        program=stack["program"],
        chair_unit=stack["chair"],
        author=author,
        plan_hours=dict(PLAN_HOURS),
    )
    return version, actor


def _submitted(world, author_key="teacher"):
    version, actor = _draft(world, author_key)
    _fill(version, actor)
    return services.submit(version=version, actor=actor)


def _approved(world):
    version = _submitted(world)
    return services.approve(version=version, actor=_actor(world["chair_head"], world["org"]))


# ── SYL-1 ───────────────────────────────────────────────────────────────────


def test_state_machine_forbids_the_author_on_every_decision():
    for name in (Transition.APPROVE, Transition.REQUEST_REVISION, Transition.REJECT):
        with pytest.raises(TransitionDenied) as denied:
            check(
                name=name,
                status=SyllabusStatus.SUBMITTED.value,
                permissions=["*"],
                reason="Səbəb mətni kifayət qədər uzundur.",
                is_author=True,
            )
        assert denied.value.code == "transition.author_forbidden"


def test_chair_head_who_teaches_cannot_decide_on_own_syllabus(world):
    version = _submitted(world, "chair_head")
    actor = _actor(world["chair_head"], world["org"])

    calls = (
        lambda: services.approve(version=version, actor=actor),
        lambda: services.request_revision(version=version, actor=actor, reason="Qiymətləndirmə natamamdır."),
        lambda: services.reject(version=version, actor=actor, reason="Siyasətə uyğun deyil, rədd."),
    )
    for call in calls:
        with pytest.raises(TransitionDenied) as denied:
            call()
        assert denied.value.code == "transition.author_forbidden"
    version.refresh_from_db()
    assert version.status == SyllabusStatus.SUBMITTED.value
    actions = services.available_actions(version=version, actor=actor)
    assert not {"approve", "request_revision", "reject"} & set(actions)


def test_self_authored_syllabus_is_routed_to_the_dean(world):
    version = _submitted(world, "chair_head")
    dean = _actor(world["dean"], world["org"])

    assert "approve" in services.available_actions(version=version, actor=dean)
    approved = services.approve(version=version, actor=dean)

    assert approved.status == SyllabusStatus.APPROVED.value
    assert approved.approved_by == world["dean"]
    assert approved.submitted_by == world["chair_head"]


def test_org_wide_actor_can_decide_on_the_chair_heads_syllabus(world):
    version = _submitted(world, "chair_head")

    approved = services.approve(version=version, actor=_actor(world["rim"], world["org"]))

    assert approved.status == SyllabusStatus.APPROVED.value


def test_dean_stays_out_of_scope_for_an_ordinary_teachers_syllabus(world):
    version = _submitted(world, "teacher")

    with pytest.raises(TransitionDenied) as denied:
        services.approve(version=version, actor=_actor(world["dean"], world["org"]))
    assert denied.value.code == "transition.out_of_scope"
    # Kafedra müdiri başqasının sillabusunda qərar verir.
    approved = services.approve(version=version, actor=_actor(world["chair_head"], world["org"]))
    assert approved.status == SyllabusStatus.APPROVED.value


def test_self_authored_submit_notifies_the_dean_not_the_author(django_capture_on_commit_callbacks, world):
    from apps.notifications.models import InAppNotification
    from apps.syllabus.services.notifications import SELF_AUTHORED_NOTE

    with mock.patch(
        "apps.organizations.public.dean_memberships_for_unit",
        return_value=[mock.Mock(user=world["dean"])],
    ):
        with django_capture_on_commit_callbacks(execute=True):
            _submitted(world, "chair_head")

    events = InAppNotification.objects.filter(metadata__event="syllabus_submit")
    assert not events.filter(recipient=world["chair_head"]).exists()
    note = events.filter(recipient=world["dean"]).first()
    assert note is not None and str(SELF_AUTHORED_NOTE) in note.message


def test_review_panel_hides_decision_buttons_for_the_author(world):
    version = _submitted(world, "chair_head")
    client = Client()
    client.force_login(world["chair_head"])
    session = client.session
    session["active_organization_id"] = str(world["org"].pk)
    session.save()

    with mock.patch("apps.accounts.views.syllabus.review_api._get_active_organization", return_value=world["org"]):
        response = client.post(
            reverse("accounts:syllabus_review_open", kwargs={"version_id": version.pk}),
            data="{}",
            content_type="application/json",
        )
        decision = client.post(
            reverse("accounts:syllabus_decision", kwargs={"version_id": version.pk}),
            data=json.dumps({"action": "approve"}),
            content_type="application/json",
        )

    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["decisions"] == []
    assert payload["own_note"]
    assert decision.status_code == 403
    assert decision.json()["code"] == "transition.author_forbidden"


# ── SYL-2 ───────────────────────────────────────────────────────────────────


def test_new_version_branches_from_the_approved_one_not_the_rejected_one(world):
    org = world["org"]
    approved = _approved(world)
    syllabus = approved.syllabus
    teacher = _actor(world["teacher"], org)
    chair = _actor(world["chair_head"], org)

    minor = services.create_next_version(syllabus=syllabus, actor=teacher, kind=ChangeKind.MINOR.value)
    week = dict(complete_section_data()[SectionKey.WEEK.value])
    week["rows"] = [dict(row) for row in week["rows"]]
    week["rows"][0]["topic"] = "Tamamilə yeni mövzu"
    services.save_section(version=minor, section_id=SectionKey.WEEK.value, data=week, actor=teacher)
    escalated = services.submit(version=minor, actor=teacher)
    assert escalated.label == "v2.0"
    services.reject(version=escalated, actor=chair, reason="Struktur dəyişikliyi qəbul edilmir.")

    syllabus.refresh_from_db()
    retry = services.create_next_version(syllabus=syllabus, actor=teacher, kind=ChangeKind.MINOR.value)

    assert retry.source_version_id == approved.pk
    assert (retry.major, retry.minor) == (1, 1)
    # Rədd edilmiş v2.0-ın həftə planı yeni qaralamaya KEÇMİR.
    week_row = retry.sections.get(section_id=SectionKey.WEEK.value)
    assert week_row.data["rows"][0]["topic"] != "Tamamilə yeni mövzu"


def test_baseline_is_the_approved_version_even_when_the_source_was_rejected(world):
    org = world["org"]
    approved = _approved(world)
    teacher = _actor(world["teacher"], org)
    chair = _actor(world["chair_head"], org)
    syllabus = approved.syllabus

    first = services.create_next_version(syllabus=syllabus, actor=teacher, kind=ChangeKind.MINOR.value)
    week = dict(complete_section_data()[SectionKey.WEEK.value])
    week["rows"] = [dict(row) for row in week["rows"]]
    week["rows"][0]["topic"] = "Struktur dəyişikliyi"
    services.save_section(version=first, section_id=SectionKey.WEEK.value, data=week, actor=teacher)
    rejected = services.submit(version=first, actor=teacher)
    services.reject(version=rejected, actor=chair, reason="Struktur dəyişikliyi qəbul edilmir.")

    # Köhnə (düzəlişdən əvvəlki) davranışı təqlid: rədd edilmiş versiyadan budaqlanmış minor.
    legacy = services.create_next_version(syllabus=syllabus, actor=teacher, kind=ChangeKind.MINOR.value)
    SyllabusVersion.objects.filter(pk=legacy.pk).update(source_version=rejected)
    SyllabusSection.objects.filter(version=legacy, section_id=SectionKey.WEEK.value).update(data=week)
    legacy.refresh_from_db()

    submitted = services.submit(version=legacy, actor=teacher)

    assert submitted.change_kind == ChangeKind.MAJOR.value
    assert SectionKey.WEEK.value in submitted.escalated_sections


# ── SYL-3 ───────────────────────────────────────────────────────────────────


def test_stale_autosave_cannot_write_into_a_submitted_version(world):
    version, actor = _draft(world)
    _fill(version, actor)
    stale = SyllabusVersion.objects.select_related("syllabus").get(pk=version.pk)
    services.submit(version=version, actor=actor)
    before = SyllabusSection.objects.get(version=version, section_id=SectionKey.DESC.value).data

    with pytest.raises(TransitionDenied) as denied:
        services.save_section(
            version=stale, section_id=SectionKey.DESC.value, data={"description": "", "goal": ""}, actor=actor
        )

    assert denied.value.code == "version.locked"
    assert SyllabusSection.objects.get(version=version, section_id=SectionKey.DESC.value).data == before
    version.refresh_from_db()
    assert version.completion_percent == 100


def test_stale_plan_hours_and_seed_do_not_touch_a_submitted_version(world):
    version, actor = _draft(world)
    _fill(version, actor)
    stale = SyllabusVersion.objects.get(pk=version.pk)
    services.submit(version=version, actor=actor)
    week_before = SyllabusSection.objects.get(version=version, section_id=SectionKey.WEEK.value).revision

    services.set_plan_hours(stale, {"lecture": 60})
    seeded = services.seed_week_hours(stale, {"lecture": 60})

    version.refresh_from_db()
    assert version.plan_hours == PLAN_HOURS
    assert seeded is False
    assert SyllabusSection.objects.get(version=version, section_id=SectionKey.WEEK.value).revision == week_before


# ── SYL-4 ───────────────────────────────────────────────────────────────────


def _audit_rows(version, user):
    from django.apps import apps as django_apps

    audit_log = django_apps.get_model("audit", "AuditLog")
    return audit_log.objects.filter(resource_id=str(version.pk), user=user)


def _structural_minor(world):
    org = world["org"]
    approved = _approved(world)
    teacher = _actor(world["teacher"], org)
    minor = services.create_next_version(syllabus=approved.syllabus, actor=teacher, kind=ChangeKind.MINOR.value)
    week = dict(complete_section_data()[SectionKey.WEEK.value])
    week["rows"] = [dict(row) for row in week["rows"]]
    week["rows"][0]["topic"] = "Struktur dəyişikliyi"
    services.save_section(version=minor, section_id=SectionKey.WEEK.value, data=week, actor=teacher)
    return minor


def test_non_author_submit_leaves_no_side_effects(world):
    minor = _structural_minor(world)
    outsider = _actor(world["other_teacher"], world["org"])

    with pytest.raises(TransitionDenied) as denied:
        services.submit(version=minor, actor=outsider)

    assert denied.value.code == "transition.out_of_scope"
    minor.refresh_from_db()
    assert (minor.label, minor.change_kind, minor.status) == ("v1.1", ChangeKind.MINOR.value, SyllabusStatus.DRAFT)
    assert not _audit_rows(minor, world["other_teacher"]).exists()


def test_non_author_submit_via_http_is_refused_without_side_effects(world):
    minor = _structural_minor(world)
    client = Client()
    client.force_login(world["other_teacher"])

    with mock.patch("apps.accounts.views.syllabus.api._get_active_organization", return_value=world["org"]):
        response = client.post(
            reverse("accounts:syllabus_action"),
            data=json.dumps({"action": "submit", "version": str(minor.pk)}),
            content_type="application/json",
        )

    assert response.status_code in {404, 409}
    assert response.json()["ok"] is False
    minor.refresh_from_db()
    assert (minor.label, minor.status) == ("v1.1", SyllabusStatus.DRAFT)
    assert not _audit_rows(minor, world["other_teacher"]).exists()


def test_incomplete_author_submit_is_not_escalated(world):
    minor = _structural_minor(world)
    teacher = _actor(world["teacher"], world["org"])
    services.save_section(
        version=minor, section_id=SectionKey.DESC.value, data={"description": "", "goal": ""}, actor=teacher
    )

    with pytest.raises(TransitionDenied) as denied:
        services.submit(version=minor, actor=teacher)

    assert denied.value.code == "transition.incomplete"
    minor.refresh_from_db()
    assert (minor.label, minor.change_kind) == ("v1.1", ChangeKind.MINOR.value)


# ── SYL-6 ───────────────────────────────────────────────────────────────────


def test_double_click_new_version_returns_the_open_version_instead_of_500(world):
    approved = _approved(world)
    syllabus = approved.syllabus
    teacher = _actor(world["teacher"], world["org"])
    opened = services.create_next_version(syllabus=syllabus, actor=teacher, kind=ChangeKind.MINOR.value)
    client = Client()
    client.force_login(world["teacher"])

    with (
        mock.patch("apps.accounts.views.syllabus.api._get_active_organization", return_value=world["org"]),
        mock.patch("apps.accounts.views.syllabus.api.services.create_next_version", side_effect=IntegrityError("dup")),
    ):
        response = client.post(
            reverse("accounts:syllabus_action"),
            data=json.dumps({"action": "new_version", "syllabus": str(syllabus.pk)}),
            content_type="application/json",
        )

    assert response.status_code == 200, response.content
    assert response.json()["version"] == str(opened.pk)


def test_second_new_version_is_a_clean_domain_refusal(world):
    approved = _approved(world)
    teacher = _actor(world["teacher"], world["org"])
    services.create_next_version(syllabus=approved.syllabus, actor=teacher, kind=ChangeKind.MINOR.value)

    with pytest.raises(TransitionDenied) as denied:
        services.create_next_version(syllabus=approved.syllabus, actor=teacher, kind=ChangeKind.MINOR.value)
    assert denied.value.code == "version.open_version_exists"


# ── SYL-7 ───────────────────────────────────────────────────────────────────


def _editor(user, org, version):
    from apps.accounts.views.syllabus.editor import build_syllabus_editor_section

    request = RequestFactory().get("/profile/", {"section": "syllabus-editor"})
    request.user = user
    return build_syllabus_editor_section(request, organization=org, version=version)["syllabus_editor_section"]


def test_editor_get_by_a_non_author_does_not_write(world):
    version, _actor_ = _draft(world)
    row = SyllabusSection.objects.get(version=version, section_id=SectionKey.WEEK.value)
    revision_before, data_before = row.revision, row.data

    _editor(world["chair_head"], world["org"], SyllabusVersion.objects.get(pk=version.pk))

    row.refresh_from_db()
    assert (row.revision, row.data) == (revision_before, data_before)


def test_editor_get_by_the_author_still_seeds_the_week_plan(world):
    version, _actor_ = _draft(world)
    row = SyllabusSection.objects.get(version=version, section_id=SectionKey.WEEK.value)
    revision_before = row.revision

    _editor(world["teacher"], world["org"], SyllabusVersion.objects.get(pk=version.pk))

    row.refresh_from_db()
    assert row.revision == revision_before + 1


def test_editor_completion_uses_the_organization_weights(world):
    from apps.syllabus import public
    from apps.syllabus.policy import assessment_weights

    org = world["org"]
    org.settings = {"syllabus": {"assessment": {"midterm": 25}}}
    org.save(update_fields=["settings"])
    version, _actor_ = _draft(world)
    seen = []
    real = public.completion_rules.evaluate

    def spy(section_data, plan_hours=None, assessment=None):
        seen.append(assessment)
        return real(section_data, plan_hours, assessment)

    request = RequestFactory().get("/profile/")
    request.user = world["teacher"]
    with mock.patch.object(public.completion_rules, "evaluate", side_effect=spy):
        public.build_syllabus_editor_context(request, organization=org, version=version)

    assert seen and seen[0] == assessment_weights(org)
