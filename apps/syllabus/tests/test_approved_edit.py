"""Avtomatik rejimdə təsdiqlənmiş məzmun redaktəsi: status, audit, author və konflikt."""

from django.test import override_settings

import pytest

from apps.accounts.views.syllabus.rows import build_row
from apps.audit.models import AuditLog
from apps.syllabus import services
from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.models import ApprovalSource
from apps.syllabus.services.drafts import SectionConflict
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.test_workflow import _fill
from apps.syllabus.tests.test_workflow import draft as _draft_fixture
from apps.syllabus.tests.test_workflow import world as _world_fixture

draft = _draft_fixture
world = _world_fixture

pytestmark = pytest.mark.django_db
AUTO = override_settings(SYLLABUS_APPROVAL_REQUIRED=False)


def approved(draft):
    syllabus, version, actor = draft
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    return syllabus, version, actor


@AUTO
def test_edit_preserves_published_version_and_records_content(draft):
    syllabus, version, actor = approved(draft)
    row = version.sections.get(section_id="info")
    before = row.data
    services.save_section(
        version=version,
        section_id="info",
        data={"office_hours": "Bazar ertəsi 12:00"},
        actor=actor,
        expected_revision=row.revision,
    )
    version.refresh_from_db()
    syllabus.refresh_from_db()
    row.refresh_from_db()
    assert version.status == SyllabusStatus.APPROVED
    assert version.approval_source == ApprovalSource.AUTO
    assert version.approved_by_id is None
    assert syllabus.approved_version_id == version.pk
    assert not version.is_locked
    assert row.data["teacher"] == before["teacher"]
    audit = AuditLog.objects.get(resource_type="syllabus.approved_edit")
    assert audit.old_values["data"] == before
    assert audit.new_values["data"] == row.data


@AUTO
def test_stale_revision_never_overwrites_approved_data(draft):
    _, version, actor = approved(draft)
    row = version.sections.get(section_id="info")
    with pytest.raises(SectionConflict):
        services.save_section(
            version=version,
            section_id="info",
            data={"office_hours": "X"},
            actor=actor,
            expected_revision=row.revision - 1,
        )
    assert not AuditLog.objects.filter(resource_type="syllabus.approved_edit").exists()


@AUTO
def test_enabling_manual_approval_restores_lock(draft):
    _, version, actor = approved(draft)
    with override_settings(SYLLABUS_APPROVAL_REQUIRED=True):
        assert version.is_locked
        with pytest.raises(TransitionDenied, match="version.locked"):
            services.save_section(version=version, section_id="info", data={}, actor=actor)


@AUTO
def test_other_teacher_cannot_edit(draft, world):
    _, version, _ = approved(draft)
    actor = services.resolve_actor(world["outsider"], world["org"])
    with pytest.raises(TransitionDenied):
        services.save_section(version=version, section_id="info", data={}, actor=actor)


@AUTO
def test_author_gets_edit_action_without_new_draft(draft):
    syllabus, version, actor = approved(draft)
    syllabus.refresh_from_db()
    row = build_row(syllabus, viewer={"user_id": actor.user.pk, "can_edit": True})
    keys = {action["key"] for action in row["actions"]}
    assert "edit" in keys and "new_version" not in keys
    assert row["status_key"] == SyllabusStatus.APPROVED
