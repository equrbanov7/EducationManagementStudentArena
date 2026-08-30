"""Servis qatı — uçdan-uca axın, kilid və əhatə testləri."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.utils import IntegrityError

import pytest

from apps.syllabus import services
from apps.syllabus.constants import SectionKey, SyllabusStatus
from apps.syllabus.models import ApprovalSource, ChangeKind, SyllabusVersion
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)
from core.constants import RoleScopeType

User = get_user_model()

# `grade.input` — PG `registrar_guard_active_member` trigger-i CourseOffering
# müəllimindən məhz bu icazəni tələb edir (registrar 0041).
TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    org = make_org("syl-org")
    teacher = User.objects.create_user("syl_teacher", "syl_teacher@x.test", "pw")
    chair = User.objects.create_user("syl_chair", "syl_chair@x.test", "pw")
    outsider = User.objects.create_user("syl_outsider", "syl_outsider@x.test", "pw")
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
    other_chair_unit = make_academic_stack(org, code="OTH202")["chair"]
    activate_member(
        org,
        outsider,
        "chair_head_other",
        permissions=CHAIR_PERMS,
        scope_unit=other_chair_unit,
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    offering = make_offering(org, stack, teacher)
    return {
        "org": org,
        "teacher": teacher,
        "chair": chair,
        "outsider": outsider,
        "stack": stack,
        "offering": offering,
    }


def _actor(user, org):
    return services.resolve_actor(user, org)


def _fill(version, actor):
    for section_id, data in complete_section_data().items():
        if section_id in {SectionKey.PREV.value, SectionKey.SEND.value}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=actor)
    version.refresh_from_db()
    return version


@pytest.fixture()
def draft(world):
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
    return syllabus, version, actor


def test_create_draft_makes_ten_sections_and_zero_completion(draft):
    _syllabus, version, _actor_obj = draft
    assert version.sections.count() == 10
    assert version.status == SyllabusStatus.DRAFT
    assert version.label == "v1.0"
    assert version.completion_percent < 100


def test_autosave_recomputes_completion_to_100(draft):
    _syllabus, version, actor = draft
    _fill(version, actor)
    assert version.completion_percent == 100
    assert version.sections.filter(section_id=SectionKey.WEEK.value, is_complete=True).exists()


def test_incomplete_draft_cannot_be_submitted(draft):
    _syllabus, version, actor = draft
    with pytest.raises(TransitionDenied) as excinfo:
        services.submit(version=version, actor=actor)
    assert excinfo.value.code == "transition.incomplete"


def test_full_happy_path_submit_review_approve(draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    assert version.status == SyllabusStatus.SUBMITTED
    assert version.locked_at is not None

    chair_actor = _actor(world["chair"], world["org"])
    version = services.start_review(version=version, actor=chair_actor)
    assert version.status == SyllabusStatus.REVIEW
    assert version.reviewer_id == world["chair"].pk

    version = services.approve(version=version, actor=chair_actor, comment="Uyğundur")
    assert version.status == SyllabusStatus.APPROVED
    assert version.approval_source == ApprovalSource.HUMAN
    assert version.approved_by_id == world["chair"].pk
    version.syllabus.refresh_from_db()
    assert version.syllabus.approved_version_id == version.pk


def test_approved_version_sections_cannot_be_edited(draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    version = services.approve(version=version, actor=chair_actor)
    with pytest.raises(TransitionDenied) as excinfo:
        services.save_section(version=version, section_id=SectionKey.DESC.value, data={"description": "x"}, actor=actor)
    assert excinfo.value.code == "version.locked"


def test_revision_requires_a_reason(draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    with pytest.raises(TransitionDenied) as excinfo:
        services.request_revision(version=version, actor=chair_actor, reason="")
    assert excinfo.value.code == "transition.reason_required"

    version = services.request_revision(version=version, actor=chair_actor, reason="Ədəbiyyat siyahısı yenilənməlidir.")
    assert version.status == SyllabusStatus.REVISION
    assert version.decision_reason


def test_revision_reopens_editing_and_can_be_resubmitted(draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    version = services.request_revision(version=version, actor=chair_actor, reason="Düzəliş lazımdır")
    version = services.resume_editing(version=version, actor=actor)
    assert version.status == SyllabusStatus.DRAFT
    version = services.submit(version=version, actor=actor)
    assert version.status == SyllabusStatus.SUBMITTED


def test_withdraw_requires_reason_and_returns_to_draft(draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    with pytest.raises(TransitionDenied):
        services.withdraw(version=version, actor=actor, reason="")
    version = services.withdraw(version=version, actor=actor, reason="Səhv fayl əlavə etmişəm")
    assert version.status == SyllabusStatus.DRAFT
    assert version.submitted_at is None


def test_chair_outside_own_department_cannot_approve(draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    outsider_actor = _actor(world["outsider"], world["org"])
    with pytest.raises(TransitionDenied) as excinfo:
        services.approve(version=version, actor=outsider_actor)
    assert excinfo.value.code == "transition.out_of_scope"


def test_syllabus_without_chair_unit_is_fail_closed(world, draft):
    _syllabus, version, actor = draft
    version.syllabus.chair_unit = None
    version.syllabus.save(update_fields=["chair_unit"])
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    with pytest.raises(TransitionDenied) as excinfo:
        services.approve(version=version, actor=chair_actor)
    assert excinfo.value.code == "transition.out_of_scope"


def test_new_minor_version_archives_the_previous_approved_one(draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    first = services.approve(version=version, actor=chair_actor)

    second = services.create_next_version(syllabus=first.syllabus, actor=actor, kind=ChangeKind.MINOR.value)
    assert second.label == "v1.1"
    assert second.status == SyllabusStatus.DRAFT
    # Köhnə versiya yeni versiya TƏSDİQLƏNƏNƏ QƏDƏR qüvvədədir.
    first.refresh_from_db()
    assert first.status == SyllabusStatus.APPROVED

    services.recompute_completion(second)
    second.refresh_from_db()
    second = services.submit(version=second, actor=actor)
    second = services.approve(version=second, actor=chair_actor)
    first.refresh_from_db()
    assert first.status == SyllabusStatus.ARCHIVED
    assert first.archived_at is not None


def test_major_version_increments_major_and_resets_minor(draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    approved = services.approve(version=version, actor=chair_actor)
    nxt = services.create_next_version(syllabus=approved.syllabus, actor=actor, kind=ChangeKind.MAJOR.value)
    assert (nxt.major, nxt.minor) == (2, 0)
    assert nxt.source_version_id == approved.pk


def test_only_one_open_version_per_syllabus(draft, world):
    _syllabus, version, actor = draft
    with pytest.raises(TransitionDenied) as excinfo:
        services.create_next_version(syllabus=version.syllabus, actor=actor, kind=ChangeKind.MINOR.value)
    assert excinfo.value.code == "version.open_version_exists"


def test_autosave_conflict_is_detected(draft):
    _syllabus, version, actor = draft
    row, _report = services.save_section(
        version=version, section_id=SectionKey.DESC.value, data={"description": "a", "goal": "b"}, actor=actor
    )
    with pytest.raises(services.SectionConflict):
        services.save_section(
            version=version,
            section_id=SectionKey.DESC.value,
            data={"description": "c", "goal": "d"},
            actor=actor,
            expected_revision=row.revision - 1,
        )


def test_disallowed_selfwork_option_is_refused_at_the_service_boundary(draft):
    _syllabus, version, actor = draft
    with pytest.raises(TransitionDenied) as excinfo:
        services.save_section(
            version=version,
            section_id=SectionKey.SELF.value,
            data={"option": "3x5", "topics": []},
            actor=actor,
        )
    assert excinfo.value.code == "self.option_not_allowed"


def test_migrated_syllabus_is_approved_without_a_fake_human_approver(world):
    from django.utils import timezone

    syllabus, version = services.import_migrated_version(
        organization=world["org"],
        subject=world["stack"]["subject"],
        period=world["stack"]["period"],
        approved_at=timezone.now(),
        chair_unit=world["stack"]["chair"],
        plan_hours=PLAN_HOURS,
        section_data=complete_section_data(),
        note="Köhnə sistemdən köçürülüb",
    )
    assert version.status == SyllabusStatus.APPROVED
    assert version.approval_source == ApprovalSource.MIGRATION
    assert version.approved_by_id is None
    assert version.locked_at is not None
    assert version.change_kind == ChangeKind.IMPORTED
    assert syllabus.approved_version_id == version.pk


def test_migrated_base_syllabus_needs_no_semester(world):
    """Köhnə bazada semestr yoxdur — uydurmaq əvəzinə «baza sillabus» yaranır."""
    from django.utils import timezone

    stamp = timezone.now()
    syllabus, archived = services.import_migrated_version(
        organization=world["org"],
        subject=world["stack"]["subject"],
        approved_at=stamp,
        author=world["teacher"],
        chair_unit=world["stack"]["chair"],
        major=1,
        minor=0,
        status=SyllabusStatus.ARCHIVED,
    )
    _syllabus2, current = services.import_migrated_version(
        organization=world["org"],
        subject=world["stack"]["subject"],
        approved_at=stamp,
        author=world["teacher"],
        chair_unit=world["stack"]["chair"],
        major=1,
        minor=1,
        status=SyllabusStatus.APPROVED,
    )
    assert syllabus.period_id is None
    assert _syllabus2.pk == syllabus.pk
    assert archived.status == SyllabusStatus.ARCHIVED
    assert current.status == SyllabusStatus.APPROVED
    assert current.approved_by_id is None
    syllabus.refresh_from_db()
    assert syllabus.approved_version_id == current.pk


def test_migration_import_refuses_open_statuses(world):
    from django.utils import timezone

    with pytest.raises(TransitionDenied) as excinfo:
        services.import_migrated_version(
            organization=world["org"],
            subject=world["stack"]["subject"],
            approved_at=timezone.now(),
            status=SyllabusStatus.DRAFT,
        )
    assert excinfo.value.code == "import.status_not_allowed"


def test_db_refuses_a_revision_without_a_reason(draft):
    _syllabus, version, _actor_obj = draft
    with pytest.raises(IntegrityError):
        SyllabusVersion.objects.filter(pk=version.pk).update(status=SyllabusStatus.REVISION, decision_reason="")


def test_review_queue_is_scoped_to_the_own_department(draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    services.submit(version=version, actor=actor)
    own = services.review_queue(organization=world["org"], actor=_actor(world["chair"], world["org"]))
    other = services.review_queue(organization=world["org"], actor=_actor(world["outsider"], world["org"]))
    assert own.count() == 1
    assert other.count() == 0


def test_teacher_without_review_permission_sees_an_empty_queue(draft, world):
    queue = services.review_queue(organization=world["org"], actor=_actor(world["teacher"], world["org"]))
    assert queue.count() == 0


def test_list_is_scoped_and_counts_statuses(draft, world):
    _syllabus, version, actor = draft
    rows = services.list_syllabi(organization=world["org"], actor=actor)
    assert rows.count() == 1
    counts = services.status_counts(rows)
    assert counts[SyllabusStatus.DRAFT.value] == 1
    assert counts["total"] == 1
    outsider_rows = services.list_syllabi(organization=world["org"], actor=_actor(world["outsider"], world["org"]))
    assert outsider_rows.count() == 0


def test_version_diff_marks_changed_sections(draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    approved = services.approve(version=version, actor=chair_actor)
    nxt = services.create_next_version(syllabus=approved.syllabus, actor=actor, kind=ChangeKind.MINOR.value)
    services.save_section(
        version=nxt,
        section_id=SectionKey.METHOD.value,
        data={"methods": ["Mühazirə", "Case study təhlili", "Fərdi məsləhət"], "note": ""},
        actor=actor,
    )
    diff = services.version_diff(approved, nxt)
    assert diff[SectionKey.METHOD.value]["changed"] is True
    assert diff[SectionKey.DESC.value]["changed"] is False


def test_every_transition_is_written_to_the_existing_audit_log(draft, world):
    from django.contrib.contenttypes.models import ContentType

    from apps.audit.models import AuditLog

    _syllabus, version, actor = draft
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    content_type = ContentType.objects.get_for_model(SyllabusVersion)
    entries = AuditLog.objects.filter(content_type=content_type, object_id=str(version.pk))
    assert entries.filter(changes__transition="submit").exists()


def test_timeline_merges_versions_and_decisions(draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    services.request_revision(version=version, actor=chair_actor, reason="Saatlar uyğun deyil")
    events = services.version_timeline(version.syllabus)
    kinds = {event["kind"] for event in events}
    assert kinds == {"version", "review"}
    assert any(event.get("decision") == "revision" for event in events)
