"""Eyni PK-li approved mənbə düzəlişi: bağlı nüsxə köhnəlir, tarixçə saxlanır."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from django.test import override_settings
from django.utils import timezone

import pytest

from apps.syllabus import services
from apps.syllabus.constants import SectionKey, SyllabusStatus
from apps.syllabus.models import Syllabus
from apps.syllabus.services.reuse_sync import _snapshot_is_behind
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.factories import PLAN_HOURS
from apps.syllabus.tests.reuse_fixtures import actor, approved_syllabus, build_world, target


def _sections(version):
    return {row.section_id: row.data for row in version.sections.all()}


@pytest.mark.django_db
def test_in_place_edit_is_behind_and_resync_keeps_previous_snapshot():
    world = build_world("reuse-inplace-source")
    source, base = approved_syllabus(world)
    linked, previous = services.reuse.link(source=source, target=target(world, "o2"), actor=actor(world))
    previous_content = _sections(previous)
    assert not services.reuse_sync.is_behind(linked)

    with override_settings(SYLLABUS_APPROVAL_REQUIRED=False):
        services.save_section(
            version=base,
            section_id=SectionKey.INFO.value,
            data={"office_hours": "Yeni məsləhət saatı — 2026"},
            actor=actor(world),
        )
    base.refresh_from_db()
    source = Syllabus.objects.select_related("approved_version").get(pk=source.pk)
    linked = Syllabus.objects.select_related("reused_from__approved_version", "approved_version").get(pk=linked.pk)
    assert base.status == SyllabusStatus.APPROVED
    assert source.approved_version_id == base.pk
    assert linked.approved_version_id == previous.pk
    assert _sections(previous) == previous_content
    assert services.reuse_sync.is_behind(linked)
    assert services.reuse_sync.linked_summary([source])[source.pk] == {"linked": 1, "behind": 1}

    # Bağlı nüsxənin müəllifi birbaşa redaktə edə bilməz; mövcud sinxron yolu işləyir.
    with override_settings(SYLLABUS_APPROVAL_REQUIRED=False), pytest.raises(TransitionDenied):
        services.save_section(version=previous, section_id=SectionKey.INFO.value, data={}, actor=actor(world))
    result = services.reuse_sync.propagate(source=source, actor=actor(world), hours_for=lambda _: PLAN_HOURS)
    assert [row["status"] for row in result] == ["synced"]
    linked.refresh_from_db()
    previous.refresh_from_db()
    current = linked.approved_version
    assert current.pk != previous.pk
    assert current.source_version_id == base.pk
    assert current.status == SyllabusStatus.APPROVED
    assert previous.status == SyllabusStatus.ARCHIVED
    assert _sections(previous) == previous_content
    assert _sections(current) == _sections(base)
    assert not services.reuse_sync.is_behind(linked)
    assert services.reuse_sync.linked_summary([source])[source.pk] == {"linked": 1, "behind": 0}
    again = services.reuse_sync.propagate(source=source, actor=actor(world), hours_for=lambda _: PLAN_HOURS)
    assert [row["status"] for row in again] == ["already"]


@pytest.mark.parametrize("source_time_missing,copy_time_missing", [(True, False), (False, True), (True, True)])
def test_missing_historical_timestamps_never_assert_current(source_time_missing, copy_time_missing):
    stamp = timezone.now()
    base = SimpleNamespace(pk=uuid4(), approved_at=None if source_time_missing else stamp)
    assert _snapshot_is_behind(base, base.pk, None if copy_time_missing else stamp)


def test_timestamp_boundary_and_missing_source_are_unambiguous():
    stamp = timezone.now()
    base = SimpleNamespace(pk=uuid4(), approved_at=stamp)
    assert not _snapshot_is_behind(base, base.pk, stamp)
    assert not _snapshot_is_behind(base, base.pk, stamp + timedelta(seconds=1))
    assert _snapshot_is_behind(base, base.pk, stamp - timedelta(seconds=1))
    assert _snapshot_is_behind(base, uuid4(), stamp + timedelta(seconds=1))
    assert not _snapshot_is_behind(None, None, None)
