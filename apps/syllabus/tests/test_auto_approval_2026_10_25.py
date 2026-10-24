"""Sillabus avtomatik təsdiqi (sahib 2026-10-25): «Sillabus təsdiqi tələb olunur» açarı + toplu əmr.

Açar SÖNÜLÜ → göndərmə dərhal ``APPROVED`` (``approval_source=auto``, ``approved_by`` boş), kafedra
növbəsi boş, «təsdiqə göndərildi» bildirişi YOX, müəllimə «təsdiqləndi» bildirişi VAR.
Açar YANIQ → köhnə kafedra axını dəyişmir.  Test dəstinin defoltu ``SYLLABUS_APPROVAL_REQUIRED=True``-dur
(``config.settings.test``); prod defoltu SÖNÜLÜdür — onu ``test_prod_default_is_auto_approve`` yoxlayır.
"""

from __future__ import annotations

import re
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

import pytest

from apps.accounts.models import RuntimeSetting
from apps.notifications.models import InAppNotification
from apps.syllabus import services
from apps.syllabus.constants import SectionKey, SyllabusStatus
from apps.syllabus.document import reuse_approval_note
from apps.syllabus.models import ApprovalSource, SyllabusReview, SyllabusVersion
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)
from core import runtime_settings as rs
from core import runtime_settings_extensions
from core import runtime_settings_syllabus as rss
from core.constants import RoleScopeType

User = get_user_model()

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]
WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"

pytestmark = pytest.mark.django_db

AUTO = override_settings(SYLLABUS_APPROVAL_REQUIRED=False)


@pytest.fixture()
def world():
    org = make_org("syl-auto-org")
    teacher = User.objects.create_user("syl_auto_teacher", "syl_auto_teacher@x.test", "pw")
    chair = User.objects.create_user("syl_auto_chair", "syl_auto_chair@x.test", "pw")
    stack = make_academic_stack(org)
    activate_member(org, teacher, "teacher", permissions=TEACHER_PERMS)
    activate_member(
        org,
        chair,
        "chair_head",
        permissions=CHAIR_PERMS,
        scope_unit=stack["chair"],
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    offering = make_offering(org, stack, teacher)
    return {"org": org, "teacher": teacher, "chair": chair, "stack": stack, "offering": offering}


def _actor(user, org):
    return services.resolve_actor(user, org)


def _new_draft(world):
    actor = _actor(world["teacher"], world["org"])
    syllabus, version = services.create_draft(
        organization=world["org"],
        subject=world["stack"]["subject"],
        period=world["stack"]["period"],
        actor=actor,
        offering=world["offering"],
        program=world["stack"]["program"],
        chair_unit=world["stack"]["chair"],
        plan_hours=PLAN_HOURS,
    )
    for section_id, data in complete_section_data().items():
        if section_id in {SectionKey.PREV.value, SectionKey.SEND.value}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=actor)
    version.refresh_from_db()
    return syllabus, version, actor


@pytest.fixture()
def draft(world):
    return _new_draft(world)


def _queue(world):
    return services.review_queue(organization=world["org"], actor=_actor(world["chair"], world["org"]))


def _run(*args):
    out = StringIO()
    call_command("syllabus_auto_approve_pending", *args, stdout=out)
    return out.getvalue()


# ── açar spesifikasiyası ────────────────────────────────────────────────────────────────────────────────────────


def test_spec_registered_with_label_help_and_group():
    spec = rs.SPECS[rss.KEY_APPROVAL_REQUIRED]
    assert spec.kind == "bool"
    assert spec.group == "syllabus"
    assert str(spec.label) and str(spec.help)
    assert "syllabus" in [code for code, _label in rs.GROUPS]
    assert "core.runtime_settings_syllabus" in runtime_settings_extensions._MODULES


def test_prod_default_is_auto_approve(settings):
    del settings.SYLLABUS_APPROVAL_REQUIRED  # test.py yalnız kafedra axınını saxlamaq üçün True qoyur
    assert rs.SPECS[rss.KEY_APPROVAL_REQUIRED].default() is False
    assert rss.approval_required() is False


def test_stored_value_drives_read_point(settings):
    settings.RUNTIME_SETTINGS_ENABLED = True
    try:
        rs.invalidate()
        assert rss.approval_required() is True  # test defoltu
        RuntimeSetting.objects.create(key=rss.KEY_APPROVAL_REQUIRED, value=False)
        rs.invalidate()
        assert rss.approval_required() is False
        RuntimeSetting.objects.filter(key=rss.KEY_APPROVAL_REQUIRED).update(value=True)
        rs.invalidate()
        assert rss.approval_required() is True
    finally:
        rs.invalidate()


# ── submit: açar sönülü ─────────────────────────────────────────────────────────────────────────────────────────


@AUTO
def test_submit_with_switch_off_is_approved_immediately(django_capture_on_commit_callbacks, draft, world):
    syllabus, version, actor = draft
    with django_capture_on_commit_callbacks(execute=True):
        version = services.submit(version=version, actor=actor)

    assert version.status == SyllabusStatus.APPROVED
    assert version.approval_source == ApprovalSource.AUTO
    assert version.approved_by_id is None
    assert version.approved_at is not None and version.locked_at is not None
    syllabus.refresh_from_db()
    assert syllabus.approved_version_id == version.pk
    assert syllabus.current_version_id == version.pk

    decisions = list(
        SyllabusReview.objects.filter(version=version).order_by("created_at").values_list("decision", flat=True)
    )
    assert decisions == ["submitted", "approved"]
    approved_row = SyllabusReview.objects.get(version=version, decision="approved")
    assert approved_row.actor_id is None
    assert approved_row.reason == "Avtomatik təsdiq (sistem tənzimləməsi)"
    assert "avtomatik" in reuse_approval_note(version)


@AUTO
def test_switch_off_leaves_chair_queue_empty_and_sends_no_pending_notice(
    django_capture_on_commit_callbacks, draft, world
):
    _syllabus, version, actor = draft
    with django_capture_on_commit_callbacks(execute=True):
        services.submit(version=version, actor=actor)

    assert _queue(world).count() == 0
    chair_notes = InAppNotification.objects.filter(recipient=world["chair"])
    assert not chair_notes.filter(metadata__event="syllabus_submit").exists()
    teacher_notes = InAppNotification.objects.filter(recipient=world["teacher"], metadata__event="syllabus_approve")
    assert teacher_notes.count() == 1


@AUTO
def test_auto_approval_is_audited(draft):
    from apps.audit.models import AuditLog

    _syllabus, version, actor = draft
    first = services.submit(version=version, actor=actor)
    assert first.status == SyllabusStatus.APPROVED
    logs = AuditLog.objects.filter(resource_type="syllabus.version", resource_id=str(first.pk))
    assert logs.filter(reason="Avtomatik təsdiq (sistem tənzimləməsi)").exists()


# ── submit: açar yanıq (köhnə davranış) ─────────────────────────────────────────────────────────────────────────


def test_submit_with_switch_on_stays_pending(django_capture_on_commit_callbacks, draft, world):
    _syllabus, version, actor = draft
    with django_capture_on_commit_callbacks(execute=True):
        version = services.submit(version=version, actor=actor)

    assert version.status == SyllabusStatus.SUBMITTED
    assert version.approved_at is None
    assert _queue(world).count() == 1
    assert InAppNotification.objects.filter(recipient=world["chair"], metadata__event="syllabus_submit").count() == 1


# ── toplu əmr ───────────────────────────────────────────────────────────────────────────────────────────────────


def _pending_version(world, status):
    """Verilən statusda versiya yaradır (test defoltu açar YANIQ olduğu üçün göndərmə SUBMITTED qalır)."""
    _syllabus, version, actor = _new_draft(world)
    version = services.submit(version=version, actor=actor)
    assert version.status == SyllabusStatus.SUBMITTED
    chair = _actor(world["chair"], world["org"])
    if status == SyllabusStatus.REVIEW:
        version = services.start_review(version=version, actor=chair)
    elif status == SyllabusStatus.REVISION:
        version = services.request_revision(version=version, actor=chair, reason="Düzəliş lazımdır")
    elif status == SyllabusStatus.REJECTED:
        version = services.reject(version=version, actor=chair, reason="Uyğun deyil")
    assert version.status == status
    return version


def _another_world(world, code):
    """Eyni təşkilatda və kafedrada başqa fənn/açılış — hər dosyedə yalnız bir açıq versiya ola bilər."""
    stack = make_academic_stack(world["org"], code=code)
    teacher = User.objects.create_user(f"t_{code.lower()}", f"t_{code.lower()}@x.test", "pw")
    activate_member(world["org"], teacher, "teacher", permissions=TEACHER_PERMS)
    chair = User.objects.create_user(f"c_{code.lower()}", f"c_{code.lower()}@x.test", "pw")
    activate_member(
        world["org"],
        chair,
        "chair_head",
        permissions=CHAIR_PERMS,
        scope_unit=stack["chair"],
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    return {
        "org": world["org"],
        "teacher": teacher,
        "chair": chair,
        "stack": stack,
        "offering": make_offering(world["org"], stack, teacher),
    }


@pytest.fixture()
def mixed(world):
    submitted = _pending_version(world, SyllabusStatus.SUBMITTED)
    review = _pending_version(_another_world(world, "AAA101"), SyllabusStatus.REVIEW)
    revision = _pending_version(_another_world(world, "BBB202"), SyllabusStatus.REVISION)
    rejected = _pending_version(_another_world(world, "CCC303"), SyllabusStatus.REJECTED)
    return submitted, review, revision, rejected


def test_command_dry_run_counts_only_pending_and_writes_nothing(mixed):
    submitted, review, revision, rejected = mixed
    with override_settings(SYLLABUS_APPROVAL_REQUIRED=False):
        out = _run()
    assert "pending=2 submitted=1 review=1 revision_untouched=1 rejected_untouched=1" in out
    assert "dry_run=1 would_approve=2" in out
    for version, status in (
        (submitted, "submitted"),
        (review, "review"),
        (revision, "revision"),
        (rejected, "rejected"),
    ):
        version.refresh_from_db()
        assert version.status == status


@AUTO
def test_command_apply_approves_pending_only_and_is_idempotent(mixed):
    submitted, review, revision, rejected = mixed
    out = _run("--apply")
    assert "applied=1 approved=2 failed=0" in out
    for version in (submitted, review):
        version.refresh_from_db()
        assert version.status == SyllabusStatus.APPROVED
        assert version.approval_source == ApprovalSource.AUTO
        assert version.approved_by_id is None
        version.syllabus.refresh_from_db()
        assert version.syllabus.approved_version_id == version.pk
    revision.refresh_from_db()
    rejected.refresh_from_db()
    assert revision.status == SyllabusStatus.REVISION
    assert rejected.status == SyllabusStatus.REJECTED

    again = _run("--apply")
    assert "pending=0" in again and "approved=0 failed=0" in again
    assert SyllabusVersion.objects.filter(status__in=["submitted", "review"]).count() == 0


def test_command_apply_refused_while_approval_required(mixed):
    with pytest.raises(CommandError, match="approval_required"):
        _run("--apply")
    assert SyllabusVersion.objects.filter(status="submitted").count() == 1


@AUTO
def test_command_org_filter(mixed):
    out = _run("--org", "no-such-org", "--apply")
    assert "pending=0" in out
    assert SyllabusVersion.objects.filter(status__in=["submitted", "review"]).count() == 2


@AUTO
def test_command_output_has_only_counts(mixed):
    out = _run("--apply")
    for line in out.strip().splitlines():
        assert re.fullmatch(r"syllabus_auto_approve: [a-z_]+=\d+( [a-z_]+=\d+)*", line), line


# ── workflow ağ siyahısı ────────────────────────────────────────────────────────────────────────────────────────


def test_workflow_whitelists_command():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "          - syllabus_auto_approve_pending\n" in text
    assert "            syllabus_auto_approve_pending)\n" in text
