"""Təkrar istifadə YAZILARI: bağla, kopyala və uyğunlaşdır, toplu, sinxron, ayır, DB invariantları."""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, connection, transaction

import pytest

from apps.audit.models import AuditLog
from apps.syllabus import services
from apps.syllabus.constants import SectionKey, SyllabusStatus
from apps.syllabus.models import (
    ApprovalSource,
    ChangeKind,
    Syllabus,
    SyllabusReview,
    SyllabusVersion,
)
from apps.syllabus.services import reuse_rules as rules
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.factories import PLAN_HOURS
from apps.syllabus.tests.reuse_fixtures import (
    OTHER_HOURS,
    actor,
    approve_version,
    approved_syllabus,
    build_world,
    draft_for,
    fill,
    target,
)

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    return build_world("syl-reuse-link")


def _sections(version) -> dict:
    return {row.section_id: row.data for row in version.sections.all()}


def _audit_rows(version):
    content_type = ContentType.objects.get_for_model(SyllabusVersion)
    return list(AuditLog.objects.filter(content_type=content_type, object_id=str(version.pk)).order_by("created_at"))


# ── Bağla ────────────────────────────────────────────────────────────────────


def test_link_to_approved_source_approves_without_inventing_an_approver(world):
    source, source_version = approved_syllabus(world, "o1")
    syllabus, version = services.reuse.link(source=source, target=target(world, "o2"), actor=actor(world))

    version.refresh_from_db()
    syllabus.refresh_from_db()
    assert syllabus.offering_id == world["offerings"]["o2"].pk
    assert syllabus.reused_from_id == source.pk
    assert syllabus.approved_version_id == syllabus.current_version_id == version.pk
    assert version.status == SyllabusStatus.APPROVED
    assert version.approval_source == ApprovalSource.REUSE
    assert version.approved_by_id is None  # saxta insan təsdiqi YOXDUR
    assert version.source_version_id == source_version.pk
    assert version.change_kind == ChangeKind.REUSED
    assert version.locked_at is not None and version.approved_at is not None
    assert version.completion_percent == 100
    assert _sections(version) == _sections(source_version)  # eyni məzmun
    # Kafedra qərarı UYDURULMUR: hədəf versiyada «təsdiqləndi» qərar qeydi yoxdur.
    assert not SyllabusReview.objects.filter(version=version).exists()
    transitions = [row.changes.get("transition") for row in _audit_rows(version) if row.changes]
    assert "reuse" in transitions
    origin = services.reuse_origin(version)
    assert origin["group"] == world["groups"]["g1"].name
    assert origin["approved_by"] == world["head"]


def test_students_resolve_the_linked_approved_copy(world):
    source, source_version = approved_syllabus(world, "o1")
    services.reuse.link(source=source, target=target(world, "o2"), actor=actor(world))
    offering = world["offerings"]["o2"]
    resolved = services.syllabus_for_offering_obj(offering)
    shown = services.approved_version_for(resolved)
    assert shown.approval_source == ApprovalSource.REUSE
    assert _sections(shown) == _sections(source_version)
    from apps.syllabus.public import build_document

    document = build_document(resolved, shown)
    assert document["approved_by"] == ""
    assert world["groups"]["g1"].name in document["approval_note"]


def test_link_onto_existing_draft_keeps_the_replaced_text_in_the_audit(world):
    source, source_version = approved_syllabus(world, "o1")
    draft, draft_version = draft_for(world, "o2")
    services.save_section(
        version=draft_version,
        section_id=SectionKey.DESC.value,
        data={"description": "Köhnə qaralama mətni", "goal": ""},
        actor=actor(world),
    )
    draft = Syllabus.objects.get(pk=draft.pk)
    _syllabus, version = services.reuse.link(
        source=source, target=target(world, "o2", syllabus=draft), actor=actor(world)
    )
    assert version.pk == draft_version.pk  # eyni versiya state maşını ilə DRAFT → APPROVED keçdi
    assert _sections(version) == _sections(source_version)
    reuse_row = [row for row in _audit_rows(version) if (row.changes or {}).get("transition") == "reuse"][0]
    assert reuse_row.old_values["sections"]["desc"]["description"] == "Köhnə qaralama mətni"


@pytest.mark.parametrize(
    ("key", "code"),
    [("o3", rules.CODE_HOURS_DIFFER), ("o4", rules.CODE_CHAIR_DIFFERS)],
)
def test_link_is_refused_when_hours_or_chair_differ(world, key, code):
    source, _version = approved_syllabus(world, "o1")
    with pytest.raises(TransitionDenied) as denied:
        services.reuse.link(source=source, target=target(world, key), actor=actor(world))
    assert denied.value.code == code
    assert not Syllabus.objects.filter(offering=world["offerings"][key]).exists()


def test_unapproved_source_can_only_be_copied(world):
    source, _version = draft_for(world, "o1")
    with pytest.raises(TransitionDenied) as denied:
        services.reuse.link(source=source, target=target(world, "o2"), actor=actor(world))
    assert denied.value.code == rules.CODE_SOURCE_NOT_APPROVED
    syllabus, version = services.reuse.copy_adjust(source=source, target=target(world, "o2"), actor=actor(world))
    assert version.status == SyllabusStatus.DRAFT
    assert syllabus.reused_from_id is None


def test_permission_denials(world):
    source, _version = approved_syllabus(world, "o1")
    foreign, _foreign_version = approved_syllabus(world, "o5", user_key="teacher2")
    # Başqasının açılışına yazmaq olmaz.
    with pytest.raises(TransitionDenied) as denied:
        services.reuse.link(source=source, target=target(world, "o5"), actor=actor(world))
    assert denied.value.code == "transition.author_only"
    # Başqa müəllimin sillabusuna bağlanmaq və onu kopyalamaq olmaz.
    with pytest.raises(TransitionDenied) as denied:
        services.reuse.link(source=foreign, target=target(world, "o2"), actor=actor(world))
    assert denied.value.code == rules.CODE_NOT_OWN
    with pytest.raises(TransitionDenied) as denied:
        services.reuse.copy_adjust(source=foreign, target=target(world, "o2"), actor=actor(world))
    assert denied.value.code == rules.CODE_COPY_OUT_OF_SCOPE
    # `syllabus.edit` açarı olmayan (kafedra müdiri) heç nə yaza bilmir.
    with pytest.raises(TransitionDenied) as denied:
        services.reuse.copy_adjust(source=source, target=target(world, "o2"), actor=actor(world, "head"))
    assert denied.value.code == "transition.permission_denied"


def test_submitted_target_is_never_overwritten(world):
    source, _version = approved_syllabus(world, "o1")
    draft, draft_version = draft_for(world, "o2")
    fill(draft_version, actor(world))
    services.submit(version=draft_version, actor=actor(world))
    draft = Syllabus.objects.get(pk=draft.pk)
    for action in (services.reuse.link, services.reuse.copy_adjust):
        with pytest.raises(TransitionDenied) as denied:
            action(source=source, target=target(world, "o2", syllabus=draft), actor=actor(world))
        assert denied.value.code == rules.CODE_TARGET_LOCKED


# ── Kopyala və uyğunlaşdır ─────────────────────────────────────────────────────


def test_copy_adjusts_the_week_plan_to_the_target_hours(world):
    source, source_version = approved_syllabus(world, "o1")
    syllabus, version = services.reuse.copy_adjust(source=source, target=target(world, "o3"), actor=actor(world))
    version.refresh_from_db()
    assert version.status == SyllabusStatus.DRAFT
    assert version.change_kind == ChangeKind.COPIED
    assert version.source_version_id == source_version.pk
    assert version.plan_hours == OTHER_HOURS
    rows = _sections(version)[SectionKey.WEEK.value]["rows"]
    assert sum(row["lecture"] for row in rows) == 30
    assert sum(row["seminar"] for row in rows) == 30
    assert sum(row["lab"] for row in rows) == 0
    source_topics = [row["topic"] for row in _sections(source_version)[SectionKey.WEEK.value]["rows"]]
    assert [row["topic"] for row in rows][: len(source_topics)] == source_topics
    # Qalan bölmələr eynidir; nəticə adi təsdiq axınına düşür (100% → göndərmək olar).
    assert _sections(version)[SectionKey.LIT.value] == _sections(source_version)[SectionKey.LIT.value]
    assert syllabus.reused_from_id is None
    assert version.completion_percent == 100
    submitted = services.submit(version=version, actor=actor(world))
    assert submitted.status == SyllabusStatus.SUBMITTED


# ── Toplu ────────────────────────────────────────────────────────────────────


def test_bulk_links_or_copies_per_target_and_is_idempotent(world):
    source, _version = approved_syllabus(world, "o1")
    act = actor(world)
    first = services.reuse.apply_bulk(
        source=source, targets=[target(world, key) for key in ("o2", "o3", "o4", "o5")], actor=act
    )
    by_offering = {row["offering"]: row for row in first}
    offerings = world["offerings"]
    assert by_offering[str(offerings["o2"].pk)]["status"] == "linked"
    assert by_offering[str(offerings["o3"].pk)]["status"] == "copied"
    assert by_offering[str(offerings["o4"].pk)]["status"] == "copied"
    assert by_offering[str(offerings["o5"].pk)]["status"] == "skipped"  # başqasının açılışı
    assert by_offering[str(offerings["o5"].pk)]["code"] == "transition.author_only"
    versions_before = SyllabusVersion.objects.count()

    existing = {row.offering_id: row for row in Syllabus.objects.filter(offering__in=list(offerings.values()))}
    second = services.reuse.apply_bulk(
        source=source,
        targets=[target(world, key, syllabus=existing.get(offerings[key].pk)) for key in ("o2", "o3", "o4")],
        actor=act,
    )
    assert [row["status"] for row in second] == ["already", "exists", "exists"]
    assert SyllabusVersion.objects.count() == versions_before


# ── Sinxron (əl ilə) və ayır ─────────────────────────────────────────────────


def _new_source_approval(world, source):
    act = actor(world)
    draft = services.create_next_version(syllabus=source, actor=act, kind=ChangeKind.MINOR.value)
    services.save_section(
        version=draft,
        section_id=SectionKey.LIT.value,
        data={
            "primary": ["Yeni əsas mənbə — 2026", "Sedgewick, Algorithms, 2011"],
            "additional": ["Knuth, TAOCP, 1997"],
        },
        actor=act,
    )
    draft.refresh_from_db()
    return approve_version(world, draft, act)


def test_new_source_approval_waits_for_an_explicit_apply(world):
    source, _version = approved_syllabus(world, "o1")
    linked, first = services.reuse.link(source=source, target=target(world, "o2"), actor=actor(world))
    new_source = _new_source_approval(world, source)

    linked = Syllabus.objects.select_related("reused_from__approved_version", "approved_version").get(pk=linked.pk)
    assert linked.approved_version_id == first.pk  # avtomatik DƏYİŞMƏDİ
    assert services.reuse_sync.is_behind(linked)
    source = Syllabus.objects.select_related("approved_version").get(pk=source.pk)
    assert services.reuse_sync.linked_summary([source])[source.pk] == {"linked": 1, "behind": 1}

    results = services.reuse_sync.propagate(source=source, actor=actor(world), hours_for=lambda row: PLAN_HOURS)
    assert [row["status"] for row in results] == ["synced"]
    linked.refresh_from_db()
    current = linked.approved_version
    assert current.source_version_id == new_source.pk
    assert current.approval_source == ApprovalSource.REUSE and current.approved_by_id is None
    assert current.label == "v1.1"
    assert _sections(current) == _sections(new_source)
    first.refresh_from_db()
    assert first.status == SyllabusStatus.ARCHIVED
    again = services.reuse_sync.propagate(source=source, actor=actor(world), hours_for=lambda row: PLAN_HOURS)
    assert [row["status"] for row in again] == ["already"]


def test_sync_skips_a_target_whose_hours_changed(world):
    source, _version = approved_syllabus(world, "o1")
    linked, first = services.reuse.link(source=source, target=target(world, "o2"), actor=actor(world))
    _new_source_approval(world, source)
    source = Syllabus.objects.select_related("approved_version").get(pk=source.pk)
    results = services.reuse_sync.propagate(source=source, actor=actor(world), hours_for=lambda row: OTHER_HOURS)
    assert results[0]["status"] == "skipped" and results[0]["code"] == rules.CODE_HOURS_DIFFER
    linked.refresh_from_db()
    assert linked.approved_version_id == first.pk
    with pytest.raises(TransitionDenied) as denied:
        services.reuse_sync.propagate(source=source, actor=actor(world, "teacher2"))
    assert denied.value.code == "transition.out_of_scope"


def test_unlink_keeps_the_approved_copy_and_opens_an_independent_draft(world):
    source, _version = approved_syllabus(world, "o1")
    linked, approved = services.reuse.link(source=source, target=target(world, "o2"), actor=actor(world))
    with pytest.raises(TransitionDenied) as denied:
        services.create_next_version(syllabus=linked, actor=actor(world), kind=ChangeKind.MINOR.value)
    assert denied.value.code == rules.CODE_LINKED_UNLINK_FIRST
    with pytest.raises(TransitionDenied) as denied:
        services.reuse_sync.unlink(target_syllabus=linked, actor=actor(world, "teacher2"))
    assert denied.value.code == "transition.author_only"

    draft = services.reuse_sync.unlink(target_syllabus=linked, actor=actor(world))
    linked.refresh_from_db()
    approved.refresh_from_db()
    assert linked.reused_from_id is None
    assert approved.status == SyllabusStatus.APPROVED  # tələbə üçün qüvvədə qalır
    assert linked.approved_version_id == approved.pk
    assert draft.status == SyllabusStatus.DRAFT and draft.label == "v1.1"
    assert _sections(draft)[SectionKey.LIT.value] == _sections(approved)[SectionKey.LIT.value]
    with pytest.raises(TransitionDenied) as denied:
        services.reuse_sync.unlink(target_syllabus=linked, actor=actor(world))
    assert denied.value.code == rules.CODE_NOT_LINKED


# ── DB invariantları ─────────────────────────────────────────────────────────


def test_a_syllabus_cannot_be_reused_from_itself(world):
    syllabus, _version = draft_for(world, "o1")
    with pytest.raises(IntegrityError), transaction.atomic():
        Syllabus.objects.filter(pk=syllabus.pk).update(reused_from=syllabus)


def test_source_must_share_organization_and_subject(world):
    from apps.registrar.models import Subject

    syllabus, _version = draft_for(world, "o1")
    other_subject = Subject.objects.create(organization=world["org"], code="RSE999", name="Başqa fənn")
    stranger = Syllabus.objects.create(
        organization=world["org"], subject=other_subject, period=world["period"], author=world["teacher"]
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS syllabus_reuse_same_org_subject IMMEDIATE")
        Syllabus.objects.filter(pk=syllabus.pk).update(reused_from=stranger)


# ── Köhnə dosyenin kafedrası (ixtisasa bağlı) ────────────────────────────────


def _as_legacy(source, unit):
    """Köçürülmüş dosyeni təqlid edir: ``chair_unit`` kafedraya yox, ixtisasa işarə edir."""
    Syllabus.objects.filter(pk=source.pk).update(chair_unit=unit)
    return Syllabus.objects.select_related("chair_unit", "author", "approved_version").get(pk=source.pk)


def test_link_uses_the_effective_chair_of_a_legacy_source(world):
    source, _version = approved_syllabus(world, "o1")
    source = _as_legacy(source, world["groups"]["g1"].parent)
    act = actor(world)
    # Təsdiq marşrutu (ensure_chair_unit) ilə eyni: ixtisas → müəllifin kafedra üzvlüyü.
    assert rules.effective_chair_unit_id(source) == world["chair"].pk
    assert rules.link_code(source, actor=act, target_hours=PLAN_HOURS, target_chair_unit_id=world["chair"].pk) == ""

    syllabus, version = services.reuse.link(source=source, target=target(world, "o2"), actor=act)
    assert version.status == SyllabusStatus.APPROVED and version.approval_source == ApprovalSource.REUSE
    assert syllabus.chair_unit_id == world["chair"].pk
    source.refresh_from_db()
    assert source.chair_unit_id == world["chair"].pk  # yazı yolunda self-heal (ensure_chair_unit)


def test_a_legacy_source_under_another_chair_is_still_refused(world):
    source, _version = approved_syllabus(world, "o1")
    source = _as_legacy(source, world["groups"]["g4"].parent)  # ixtisas C — BAŞQA kafedranın altında
    assert rules.effective_chair_unit_id(source) == world["other_chair"].pk
    with pytest.raises(TransitionDenied) as denied:
        services.reuse.link(source=source, target=target(world, "o2"), actor=actor(world))
    assert denied.value.code == rules.CODE_CHAIR_DIFFERS
