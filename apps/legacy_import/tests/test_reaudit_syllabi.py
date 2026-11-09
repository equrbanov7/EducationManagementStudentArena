"""Real PostgreSQL proof for reviewed publication and bounded repair receipts."""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest

from apps.legacy_import.services.reaudit_syllabi import RestoreError, contracts, run, state
from apps.registrar.models import Curriculum, CurriculumSubject
from apps.syllabus.public import (
    content_fingerprints,
    publish_reviewed_draft,
    resolve_actor,
    reviewed_completion_report,
    section_data_map,
    services,
)
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(monkeypatch):
    user = get_user_model()
    owner = user.objects.create_superuser("reviewed-owner", "owner@example.test", "pw")
    org = make_org("reviewed", owner=owner)
    profile = owner.profile
    profile.organization = org
    profile.access_state = "active"
    profile.save()
    teacher = user.objects.create_user("reviewed-teacher", password="pw")
    activate_member(
        org, teacher, "teacher", permissions=["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
    )
    stack = make_academic_stack(org)
    offering = make_offering(org, stack, teacher)
    curriculum = Curriculum.objects.create(
        organization=org, program=stack["program"], admission_year=2025, status="approved"
    )
    CurriculumSubject.objects.create(
        organization=org,
        curriculum=curriculum,
        subject=stack["subject"],
        semester_number=1,
        lecture_hours=30,
        seminar_hours=16,
        lab_hours=14,
    )
    scope = {"organization_id": str(org.pk), "period_id": str(stack["period"].pk), "offering_ids": [str(offering.pk)]}
    monkeypatch.setattr(contracts, "SCOPE", scope)
    monkeypatch.setattr(state, "SCOPE", scope)
    actor = resolve_actor(teacher, org)
    syllabus, version = services.create_draft(
        organization=org,
        subject=stack["subject"],
        period=stack["period"],
        actor=actor,
        offering=offering,
        program=stack["program"],
        chair_unit=stack["chair"],
        plan_hours=PLAN_HOURS,
    )
    return org, owner, teacher, offering, syllabus, version


def fill(version, teacher, org):
    for key, data in complete_section_data().items():
        if key not in {"prev", "send", "self"}:
            services.save_section(version=version, section_id=key, data=data, actor=resolve_actor(teacher, org))
    version.refresh_from_db()


def test_reviewed_publication_is_real_operator_and_preserves_teacher(world, django_capture_on_commit_callbacks):
    org, owner, teacher, offering, syllabus, version = world
    fill(version, teacher, org)
    original = section_data_map(version)
    hook = Mock()
    with (
        patch("apps.syllabus.services.approval_hooks._HOOKS", [hook]),
        django_capture_on_commit_callbacks(execute=True),
    ):
        approved = publish_reviewed_draft(
            version=version,
            actor=resolve_actor(owner, org),
            expected_body_sha256=content_fingerprints(original)["canonical_body_sha256"],
            reason="Reviewed authority",
        )
    assert approved.status == "approved"
    assert approved.submitted_by_id == approved.approved_by_id == owner.pk
    assert approved.approval_source == "human"
    assert approved.syllabus.author_id == teacher.pk
    assert section_data_map(approved) == original
    assert set(approved.reviews.values_list("actor_id", flat=True)) == {owner.pk}
    hook.assert_not_called()


def test_preview_and_incomplete_publication_make_no_writes(world):
    org, owner, teacher, offering, syllabus, version = world
    before = section_data_map(version)
    with CaptureQueriesContext(connection) as queries:
        report = reviewed_completion_report(version=version, sections=complete_section_data(), plan_hours=PLAN_HOURS)
        assert report.is_complete
        with pytest.raises(TransitionDenied, match="transition.incomplete"):
            publish_reviewed_draft(
                version=version,
                actor=resolve_actor(owner, org),
                expected_body_sha256=content_fingerprints(before)["canonical_body_sha256"],
                reason="Reviewed authority",
            )
    assert not [q for q in queries if q["sql"].lstrip().upper().startswith(("UPDATE ", "INSERT ", "DELETE "))]
    assert section_data_map(version) == before


def test_repair_readonly_apply_idempotence_and_guarded_undo(world):
    org, owner, teacher, offering, syllabus, version = world
    fill(version, teacher, org)
    with CaptureQueriesContext(connection) as queries:
        preview = run(org, owner)
    assert not [q for q in queries if q["sql"].lstrip().upper().startswith(("UPDATE ", "INSERT ", "DELETE "))]
    assert preview["counts"] == {"publish": 1}
    applied = run(org, owner, apply=True, expected_baseline=preview["baseline"])
    assert applied["status"] == "applied"
    assert run(org, owner)["status"] == "already_present"
    before_undo = run(org, owner, undo=applied["receipt"])
    undone = run(org, owner, undo=applied["receipt"], apply=True, expected_baseline=before_undo["baseline"])
    assert undone["status"] == "undone"
    version.refresh_from_db()
    assert version.status == "draft"
    assert version.reviews.count() == 2  # history survives undo
    assert run(org, owner, undo=applied["receipt"])["status"] == "already_undone"


def test_stale_body_blocks_apply_before_mutation(world):
    org, owner, teacher, offering, syllabus, version = world
    fill(version, teacher, org)
    preview = run(org, owner)
    section = version.sections.get(section_id="info")
    section.data["office_hours"] = "New teacher-authored text"
    section.save()
    with pytest.raises(RestoreError, match="fresh_baseline_required"):
        run(org, owner, apply=True, expected_baseline=preview["baseline"])
    version.refresh_from_db()
    assert version.status == "draft"
    assert version.reviews.count() == 0


def legacy_packet(world):
    from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationRun
    from apps.legacy_import.services.syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS

    org, owner, teacher, offering, syllabus, version = world
    migration = LegacyMigrationRun.objects.create(
        organization=org,
        source_system="myedu_mariadb",
        snapshot_sha256="0" * 64,
        snapshot_size_bytes=1,
        schema_version="1",
        transform_version="1",
        mode="cutover",
    )
    from django.utils import timezone

    LegacyMigrationRun.objects.filter(pk=migration.pk).update(status="running", started_at=timezone.now())
    for entity, key, label, target in [
        ("worker", 85, "auth.user", teacher.pk),
        ("lesson_subject", 22, "registrar.subject", offering.subject_id),
        ("group_unit", 33, "organizations.orgunit", offering.group_id),
    ]:
        LegacyEntityMap.objects.create(
            organization=org,
            created_run=migration,
            source_system="myedu_mariadb",
            entity_type=entity,
            legacy_pk=str(key),
            source_row_hash="1" * 64,
            transform_version="1",
            target_model_label=label,
            target_pk=str(target),
            state="migrated",
        )
    source = dict(id=1, teacher_id=85, lesson_id=22, uniqid="unique", ders_saati=60, language="az", active=1)
    source["sections"] = {table: [[1, "Original source content"]] for table in SYLLABUS_SECTION_CONTRACTS}
    source["week"] = [
        dict(
            id=i + 1,
            uniqid="unique",
            movzu=f"Source topic {i+1}",
            muh_saat="2",
            sem_saat="2" if i < 8 else "0",
            praktiki_saat="0",
            lab_saat="2" if i < 7 else "0",
            qeyd="",
        )
        for i in range(15)
    ]
    journal = dict(id=7, teacher_id=85, lesson_id=22, sillabus_id=1, semestr=14, fake=0, sonra_sil=0, group_ids=[33])
    return {
        "sources": {"1": {"data": source, "sha256": contracts.digest(source)}},
        "bindings": {str(offering.pk): {"source_id": 1, "journal": journal}},
        "sha256": "2" * 64,
    }


def test_exact_legacy_restores_blank_draft_without_forged_human_approval(world):
    org, owner, teacher, offering, syllabus, version = world
    packet = legacy_packet(world)
    preview = run(org, owner, packet=packet)
    assert preview["counts"] == {"restore": 1}, preview
    applied = run(org, owner, packet=packet, apply=True, expected_baseline=preview["baseline"])
    syllabus.refresh_from_db()
    restored = syllabus.approved_version
    assert restored.approval_source == "migration"
    assert restored.approved_by_id is None
    assert restored.completion_percent < 100
    assert restored.sections.get(section_id="week").data["rows"][0]["topic"] == "Source topic 1"
    version.refresh_from_db()
    assert version.status == "archived"
    undo = run(org, owner, undo=applied["receipt"])
    run(org, owner, undo=applied["receipt"], apply=True, expected_baseline=undo["baseline"])
    version.refresh_from_db()
    assert version.status == "draft"
    restored.refresh_from_db()
    assert restored.status == "archived"


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("language", "legacy_source_language_mismatch"),
        ("subject", "exact_legacy_target_route_unproven"),
        ("journal", "legacy_source_journal_identity_mismatch"),
        ("topic", "source_topics_or_contact_hours_mismatch"),
    ],
)
def test_bad_legacy_routes_are_held_without_writes(world, mutation, code):
    org, owner, teacher, offering, syllabus, version = world
    packet = legacy_packet(world)
    source = packet["sources"]["1"]["data"]
    if mutation == "language":
        source["language"] = "ru"
    elif mutation == "subject":
        source["lesson_id"] = packet["bindings"][str(offering.pk)]["journal"]["lesson_id"] = 99
    elif mutation == "journal":
        packet["bindings"][str(offering.pk)]["journal"]["fake"] = 1
    else:
        source["week"][0]["movzu"] = ""
    packet["sources"]["1"]["sha256"] = contracts.digest(source)
    preview = run(org, owner, packet=packet)
    assert preview["counts"] == {}
    assert preview["held"] == [{"offering_id": str(offering.pk), "code": code}]
    version.refresh_from_db()
    assert version.status == "draft"


def test_human_partial_content_is_preserved_and_not_replaced_by_legacy(world):
    org, owner, teacher, offering, syllabus, version = world
    packet = legacy_packet(world)
    section = version.sections.get(section_id="desc")
    section.data = {"description": "Teacher authored short paragraph", "goal": ""}
    section.save()
    preview = run(org, owner, packet=packet)
    assert preview["counts"] == {}
    assert preview["held"][0]["code"] == "human_draft_requires_missing_academic_content"
    section.refresh_from_db()
    assert section.data == {"description": "Teacher authored short paragraph", "goal": ""}


def test_apply_failure_rolls_back_publication_and_receipt(world):
    org, owner, teacher, offering, syllabus, version = world
    fill(version, teacher, org)
    preview = run(org, owner)
    with patch(
        "apps.legacy_import.services.reaudit_syllabi.execute._postconditions",
        side_effect=RestoreError("test_postcondition"),
    ):
        with pytest.raises(RestoreError, match="test_postcondition"):
            run(org, owner, apply=True, expected_baseline=preview["baseline"])
    version.refresh_from_db()
    assert version.status == "draft"
    assert version.reviews.count() == 0
    assert run(org, owner)["status"] == "dry_run"


def test_later_teacher_change_blocks_undo(world):
    org, owner, teacher, offering, syllabus, version = world
    fill(version, teacher, org)
    preview = run(org, owner)
    applied = run(org, owner, apply=True, expected_baseline=preview["baseline"])
    section = version.sections.get(section_id="info")
    section.data["office_hours"] = "Later evidence"
    section.save()
    with pytest.raises(RestoreError, match="undo_live_graph_changed"):
        run(org, owner, undo=applied["receipt"])


def test_operator_cannot_impersonate_teacher_or_publish_own_draft(world):
    org, owner, teacher, offering, syllabus, version = world
    fill(version, teacher, org)
    sha = content_fingerprints(section_data_map(version))["canonical_body_sha256"]
    with pytest.raises(TransitionDenied, match="reviewed_operator_required"):
        publish_reviewed_draft(
            version=version, actor=resolve_actor(teacher, org), expected_body_sha256=sha, reason="test"
        )
    teacher.is_superuser = teacher.is_staff = True
    teacher.save()
    with pytest.raises(TransitionDenied):
        publish_reviewed_draft(
            version=version, actor=resolve_actor(teacher, org), expected_body_sha256=sha, reason="test"
        )
    version.refresh_from_db()
    assert version.status == "draft"


def test_own_base_requires_same_body_for_every_reviewed_candidate(world):
    from copy import deepcopy

    org, owner, teacher, offering, syllabus, version = world
    packet = legacy_packet(world)
    packet["bindings"][str(offering.pk)] = {"source_id": 1, "journal": None, "candidate_ids": [1, 2]}
    other = deepcopy(packet["sources"]["1"]["data"])
    other["id"] = 2
    packet["sources"]["2"] = {"data": other, "sha256": contracts.digest(other)}
    assert run(org, owner, packet=packet)["counts"] == {"restore": 1}
    other["week"][0]["movzu"] = "Different source version"
    packet["sources"]["2"]["sha256"] = contracts.digest(other)
    preview = run(org, owner, packet=packet)
    assert preview["counts"] == {}
    assert preview["held"][0]["code"] == "legacy_own_base_ambiguous_bodies"


def test_wrong_subject_owned_dossier_needs_exact_source_before_rebind(world):
    from apps.registrar.models import Subject

    org, owner, teacher, offering, syllabus, version = world
    packet = legacy_packet(world)
    wrong = Subject.objects.create(organization=org, code="WRONG", name="Unrelated subject")
    type(syllabus).objects.filter(pk=syllabus.pk).update(subject=wrong)
    preview = run(org, owner, packet=packet)
    assert preview["counts"] == {"restore": 1}, preview
    assert preview["actions"][0]["rebind_subject"] is True
    applied = run(org, owner, packet=packet, apply=True, expected_baseline=preview["baseline"])
    syllabus.refresh_from_db()
    assert syllabus.subject_id == offering.subject_id
    assert applied["postconditions"][0]["approved_syllabus_unlocked"]


def test_missing_dossier_restore_and_undo_preserve_archived_new_history(world):
    org, owner, teacher, offering, syllabus, version = world
    packet = legacy_packet(world)
    syllabus.delete()
    preview = run(org, owner, packet=packet)
    assert preview["counts"] == {"restore": 1}, preview
    applied = run(org, owner, packet=packet, apply=True, expected_baseline=preview["baseline"])
    undo = run(org, owner, undo=applied["receipt"])
    run(org, owner, undo=applied["receipt"], apply=True, expected_baseline=undo["baseline"])
    new = type(syllabus).objects.get(offering=offering)
    assert not new.is_active
    assert new.versions.get().status == "archived"


def test_same_author_approved_donor_carry_is_receipted_and_undoable(world):
    from apps.organizations.models import OrgUnit
    from apps.syllabus.public import import_migrated_version

    org, owner, teacher, offering, syllabus, version = world
    syllabus.delete()
    group = OrgUnit.objects.create(organization=org, name="Other group", slug="other-group", unit_type="group")
    donor_offering = type(offering).objects.create(
        organization=org,
        subject=offering.subject,
        period=offering.period,
        instructor=teacher,
        group=group,
        lesson_hours=60,
    )
    donor, approved = import_migrated_version(
        organization=org,
        subject=offering.subject,
        offering=donor_offering,
        period=offering.period,
        author=teacher,
        plan_hours=PLAN_HOURS,
        section_data=complete_section_data(),
        approved_at=None,
    )
    preview = run(org, owner)
    assert preview["counts"] == {"carry": 1}, preview
    applied = run(org, owner, apply=True, expected_baseline=preview["baseline"])
    assert state.resolved(offering).pk == donor.pk
    undo = run(org, owner, undo=applied["receipt"])
    run(org, owner, undo=applied["receipt"], apply=True, expected_baseline=undo["baseline"])
    assert state.resolved(offering) is None
    approved.refresh_from_db()
    assert approved.status == "approved"


def test_cross_tenant_and_unlisted_offering_cannot_be_repaired(world):
    from uuid import uuid4

    org, owner, teacher, offering, syllabus, version = world
    with pytest.raises(RestoreError, match="fixed_audit_offering_scope_required"):
        run(org, owner, offering_ids=[uuid4()])
    other = make_org("other-org", owner=owner)
    with pytest.raises(RestoreError, match="active_fixed_tenant_operator_required"):
        run(other, owner)
