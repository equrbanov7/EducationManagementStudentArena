"""Offline source selection proves typed identity, never a highest-ID guess."""

import json
from copy import deepcopy

import pytest

from apps.legacy_import.services.reaudit_syllabi import contracts, source_plan
from apps.legacy_import.tests import test_reaudit_syllabi as fixtures

world = fixtures.world
legacy_packet = fixtures.legacy_packet

pytestmark = pytest.mark.django_db


def inputs(world, monkeypatch):
    org, owner, teacher, offering, syllabus, version = world
    packet = legacy_packet(world)
    monkeypatch.setattr(source_plan, "SCOPE", contracts.SCOPE)
    source = packet["sources"]["1"]["data"]
    tables = {}
    for label in [
        "registrar.CourseOffering",
        "organizations.OrgUnit",
        "legacy_import.LegacyEntityMap",
        "legacy_import.LegacyEntityMapVersion",
    ]:
        tables[label] = list(contracts.model(label).objects.values())
    snapshot = json.loads(json.dumps({"tables": tables}, default=str))
    header = {
        key: source[key] for key in ("id", "uniqid", "teacher_id", "lesson_id", "ders_saati", "language", "active")
    }
    journal = packet["bindings"][str(offering.pk)]["journal"]
    return snapshot, source, header, journal


def test_exact_journal_packet_has_replayable_private_source_and_safe_summary(world, monkeypatch):
    snapshot, source, header, journal = inputs(world, monkeypatch)
    packet, plan = source_plan.prepare_sources(snapshot, [header], [journal], lambda _h: deepcopy(source))
    oid = str(world[3].pk)
    assert packet["bindings"][oid] == {"source_id": 1, "journal": journal}
    assert packet["sources"]["1"]["sha256"] == contracts.digest(source)
    assert plan["binding_count"] == 1
    assert plan["rows"][0]["live_official_hours_check_pending"]
    assert source["week"][0]["movzu"] not in json.dumps(plan)


def test_own_base_distinct_body_is_held_instead_of_selecting_highest_id(world, monkeypatch):
    snapshot, source, header, _journal = inputs(world, monkeypatch)
    other = deepcopy(source)
    other.update(id=999, uniqid="second")
    for week in other["week"]:
        week["uniqid"] = "second"
    other["week"][0]["movzu"] = "Newer incompatible course body"
    other_header = {key: other[key] for key in header}
    packet, plan = source_plan.prepare_sources(
        snapshot, [header, other_header], [], lambda h: deepcopy(source if h["id"] == 1 else other)
    )
    assert not packet["bindings"]
    assert plan["rows"][0]["code"] == "multiple_distinct_legacy_bodies_require_review"


def test_own_base_identical_body_tie_is_explicit_and_repeatable(world, monkeypatch):
    snapshot, source, header, _journal = inputs(world, monkeypatch)
    other = deepcopy(source)
    other.update(id=999, uniqid="second")
    for week in other["week"]:
        week["uniqid"] = "second"
    other_header = {key: other[key] for key in header}
    packet, plan = source_plan.prepare_sources(
        snapshot, [other_header, header], [], lambda h: deepcopy(source if h["id"] == 1 else other)
    )
    assert packet["bindings"][str(world[3].pk)] == {"source_id": 1, "journal": None, "candidate_ids": [1, 999]}
    assert set(packet["sources"]) == {"1", "999"}


def test_inactive_duplicate_uniqid_still_blocks_ambiguous_source_owner(world, monkeypatch):
    snapshot, source, header, journal = inputs(world, monkeypatch)
    duplicate = header | {"id": 2, "active": 0}
    packet, plan = source_plan.prepare_sources(snapshot, [header, duplicate], [journal], lambda h: deepcopy(source))
    assert not packet["bindings"]
    assert plan["rows"][0]["code"] == "legacy_source_uniqid_ambiguous"


def test_wrong_language_never_becomes_a_source(world, monkeypatch):
    snapshot, source, header, journal = inputs(world, monkeypatch)
    header["language"] = source["language"] = "ru"
    packet, plan = source_plan.prepare_sources(snapshot, [header], [journal], lambda h: deepcopy(source))
    assert not packet["bindings"]
    assert plan["rows"][0]["code"] == "no_exact_legacy_body_candidate"
