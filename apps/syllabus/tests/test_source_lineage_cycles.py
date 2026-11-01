"""PG regressions: mutable draft copies must never manufacture cyclic provenance."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.db import close_old_connections, transaction
from django.test import override_settings

import pytest

from apps.syllabus import services
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.syllabus.services import source_lineage
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.reuse_fixtures import actor, build_world, draft_for
from core.rls import bypass_rls

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(params=[False, True])
def world(request):
    with override_settings(RLS_TRANSACTION_SCOPED=request.param), bypass_rls():
        data = build_world("source-lineage")
        data["a"], data["av"] = draft_for(data, "o1")
        data["b"], data["bv"] = draft_for(data, "o2")
        yield data


def copy(world, source, destination):
    with transaction.atomic(), bypass_rls():
        source = Syllabus.objects.get(pk=world[source].pk)
        destination = Syllabus.objects.get(pk=world[destination].pk)
        return services.reuse.copy_adjust(
            source=source,
            target=services.reuse.ReuseTarget(syllabus=destination),
            actor=actor(world),
        )


def snapshot(world):
    return (
        list(Syllabus.objects.filter(organization=world["org"]).order_by("pk").values()),
        list(SyllabusVersion.objects.filter(organization=world["org"]).order_by("pk").values()),
        list(SyllabusSection.objects.filter(organization=world["org"]).order_by("pk").values()),
    )


def test_reverse_in_place_copy_refused_before_sections_and_keeps_both_drafts(world):
    copy(world, "a", "b")
    before = snapshot(world)
    with pytest.raises(TransitionDenied) as exc:
        copy(world, "b", "a")
    assert exc.value.code == source_lineage.INVALID
    assert snapshot(world) == before
    world["bv"].refresh_from_db()
    assert world["bv"].source_version_id == world["av"].pk
    assert world["av"].source_version_id is None


def test_existing_cycle_is_not_repaired_or_copied_into_a_third_draft(world):
    SyllabusVersion.objects.filter(pk=world["av"].pk).update(source_version=world["bv"])
    SyllabusVersion.objects.filter(pk=world["bv"].pk).update(source_version=world["av"])
    world["c"], world["cv"] = draft_for(world, "o3")
    before = snapshot(world)
    with pytest.raises(TransitionDenied) as exc:
        copy(world, "a", "c")
    assert exc.value.code == source_lineage.INVALID
    assert snapshot(world) == before


def test_self_and_foreign_ancestry_are_refused_even_with_bypass(world):
    with transaction.atomic(), pytest.raises(TransitionDenied):
        source_lineage.validate_source(organization_id=world["org"].pk, target_id=world["av"].pk, source=world["av"])
    foreign = build_world("source-lineage-other")
    _, base = draft_for(foreign, "o1")
    SyllabusVersion.objects.filter(pk=world["av"].pk).update(source_version=base)
    before = snapshot(world)
    with pytest.raises(TransitionDenied):
        copy(world, "a", "b")
    assert snapshot(world) == before


def test_stale_cached_source_pointer_does_not_bypass_fresh_chain(world):
    cached = Syllabus.objects.select_related("current_version").get(pk=world["a"].pk)
    SyllabusVersion.objects.filter(pk=world["av"].pk).update(source_version=world["bv"])
    before = snapshot(world)
    with transaction.atomic(), pytest.raises(TransitionDenied):
        services.reuse.copy_adjust(
            source=cached, target=services.reuse.ReuseTarget(syllabus=world["b"]), actor=actor(world)
        )
    assert snapshot(world) == before


def test_concurrent_reverse_copy_is_busy_then_rejected_by_committed_ancestry(world):
    def second():
        close_old_connections()
        try:
            with transaction.atomic(), bypass_rls(), pytest.raises(TransitionDenied) as exc:
                source_lineage.lock_lineage(world["org"].pk)
            return exc.value.code
        finally:
            close_old_connections()

    with transaction.atomic():
        copy(world, "a", "b")
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(second).result(timeout=10) == source_lineage.BUSY
    with pytest.raises(TransitionDenied) as exc:
        copy(world, "b", "a")
    assert exc.value.code == source_lineage.INVALID


def test_no_body_write_precedes_guard_in_approval_reuse(world):
    source, base = world["a"], world["av"]
    base.source_version = world["bv"]
    base.save(update_fields=["source_version"])
    before = snapshot(world)
    with transaction.atomic(), patch.object(services.reuse, "check"), pytest.raises(TransitionDenied):
        services.reuse._approve_as_reuse(
            world["bv"],
            syllabus=world["b"],
            source=source,
            base=base,
            actor=actor(world),
            plan_hours=base.plan_hours,
        )
    assert snapshot(world) == before


def test_legacy_copy_from_previous_cycle_rolls_back_new_document_and_sections(world):
    SyllabusVersion.objects.filter(pk=world["av"].pk).update(source_version=world["av"])
    before = snapshot(world)
    with pytest.raises(TransitionDenied) as exc:
        services.copy_from_previous(source_syllabus=world["a"], target_period=world["period"], actor=actor(world))
    assert exc.value.code == source_lineage.INVALID
    assert snapshot(world) == before


def test_copy_into_existing_new_minor_cycle_rolls_back_new_version(world):
    from apps.syllabus.services.copy_into import copy_into_existing

    SyllabusVersion.objects.filter(pk=world["bv"].pk).update(status="rejected", decision_reason="Fixture rejection")
    SyllabusVersion.objects.filter(pk=world["av"].pk).update(source_version=world["av"])
    before = snapshot(world)
    with pytest.raises(TransitionDenied) as exc:
        copy_into_existing(world["b"], base=world["av"], actor=actor(world))
    assert exc.value.code == source_lineage.INVALID
    assert snapshot(world) == before
