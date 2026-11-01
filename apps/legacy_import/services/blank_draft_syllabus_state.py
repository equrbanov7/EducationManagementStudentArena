"""Full fingerprints and exact empty-draft pins; no current content is rewritten."""

from types import SimpleNamespace

from django.db.models import Q
from django.utils import timezone

from apps.syllabus.public import content_fingerprints, section_data_map
from apps.workload.public import journal_academic_fingerprint, queryset_database_fingerprint

from . import blank_draft_syllabus_spec as spec
from . import exact_syllabus_recovery as core

RestoreError = core.RestoreError


def query(label, org, **filters):
    return core.model(label).objects.filter(organization=org, **filters)


def locked(queryset):
    rows = list(queryset.select_for_update(of=("self",)).order_by("pk")[:10001])
    if len(rows) > 10000:
        raise RestoreError("fixed_state_budget_exceeded")
    return rows


def actor_scope(org, actor):
    current_actor = core.model("auth.User").objects.select_for_update().get(pk=actor.pk)
    profile = (
        core.model("accounts.UserProfile")
        .objects.select_for_update()
        .filter(user=actor, access_state="active", is_deleted=False, blocked_at__isnull=True, deleted_at__isnull=True)
        .first()
    )
    affiliated = profile and (
        profile.organization_id == org.pk
        or org.owner_id == actor.pk
        or query("organizations.Membership", org, user=actor, is_active=True).exists()
    )
    if (
        str(org.pk) != spec.ORG
        or not org.is_active
        or org.status != "active"
        or not current_actor.is_active
        or not current_actor.is_superuser
        or not affiliated
    ):
        raise RestoreError("active_fixed_tenant_superadmin_required")


def scope(org, actor, row):
    actor_scope(org, actor)
    cfg = SimpleNamespace(
        organization=spec.ORG,
        offering=row["offering_id"],
        period=row["period_id"],
        allowed_owners=(row["author_id"],),
        subject_code=row["subject_code"],
        require_current_period=True,
        subject_id=row["subject_id"],
        group_id=row["group_id"],
        author=row["author_id"],
    )
    locked(core.model("auth.User").objects.filter(pk=row["author_id"]))
    locked(core.model("accounts.UserProfile").objects.filter(user_id=row["author_id"]))
    members = locked(query("organizations.Membership", org, user_id__in={actor.pk, row["author_id"]}))
    locked(query("organizations.Role", org, pk__in=[m.role_id for m in members]))
    offering = core.scope(org, actor, cfg)
    locked(query("registrar.Subject", org, pk=offering.subject_id))
    locked(query("organizations.AcademicPeriod", org, pk=offering.period_id))
    period = offering.period
    if (
        not period.is_active
        or period.locked_at is not None
        or period.academic_year != "2026/2027"
        or not (period.start_date <= timezone.localdate() <= period.end_date)
        or offering.lesson_hours != row["hours"]
    ):
        raise RestoreError("current_period_or_contact_hours_changed")
    group = query("organizations.OrgUnit", org, pk=row["group_id"]).select_for_update().get()
    if (
        not group.is_active
        or group.unit_type != "group"
        or any((group.settings or {}).get(k) != row[k] for k in ("sector", "degree_level", "education_form"))
    ):
        raise RestoreError("source_group_sector_degree_changed")
    if (
        not core.model("accounts.UserProfile")
        .objects.filter(
            user_id=row["author_id"],
            organization=org,
            access_state="active",
            is_deleted=False,
            blocked_at__isnull=True,
            deleted_at__isnull=True,
        )
        .exists()
    ):
        raise RestoreError("source_author_inactive_or_deleted")
    for entity, source_id, label, target in (
        ("worker", row["source_author"], "auth.user", str(row["author_id"])),
        ("lesson_subject", row["source_subject"], "registrar.subject", row["subject_id"]),
    ):
        links = locked(
            query(
                "legacy_import.LegacyEntityMap",
                org,
                source_system="myedu_mariadb",
                entity_type=entity,
                legacy_pk=str(source_id),
                state="migrated",
                target_model_label=label,
            )
        )
        if not links or {x.target_pk for x in links} != {target}:
            raise RestoreError("exact_source_identity_mapping_changed")
    plan = (
        query(
            "workload.TeachingTaskRow",
            org,
            pk=row["row_id"],
            task_id=row["task_id"],
            subject_id=row["subject_id"],
            period_id=row["period_id"],
        )
        .select_for_update()
        .select_related("task")
        .get()
    )
    if (
        any(getattr(plan, k) != v for k, v in row["row_fields"].items())
        or plan.task.academic_year != "2026/2027"
        or plan.task.status not in ("approved", "distributed", "amended")
        or sorted(map(str, plan.groups.values_list("pk", flat=True))) != row["row_group_ids"]
    ):
        raise RestoreError("official_source_workload_changed")
    locked(core.model("workload.TeachingTaskRow").groups.through.objects.filter(teachingtaskrow_id=plan.pk))
    assignments = locked(query("workload.TeacherAssignment", org, row=plan))
    if any(a.groups_note.strip() for a in assignments):
        raise RestoreError("source_partial_group_geometry_unreviewed")
    if (
        sorted(
            [
                {k: str(a.pk) if k == "id" else str(a.row_id) if k == "row_id" else getattr(a, k) for k in p}
                for a in assignments
                for p in [row["assignments"][0]]
            ],
            key=lambda x: x["id"],
        )
        != row["assignments"]
    ):
        raise RestoreError("source_assignment_geometry_changed")
    for label in ("Lesson", "Enrollment", "AssessmentScheme", "AssessmentComponent", "ScheduleSlot", "SelfWorkTopic"):
        locked(query("registrar." + label, org, offering=offering))
    for label in (
        "LessonMark",
        "SelfWorkMark",
        "ComponentScore",
        "CriterionScore",
        "CourseWork",
        "FinalGrade",
        "ResitRecord",
    ):
        filters = {"lesson__offering": offering} if label == "LessonMark" else {"enrollment__offering": offering}
        locked(query("registrar." + label, org, **filters))
    return offering, group, plan


def capture(org, actor, row, *, source_version_id=None, undone=False):
    offering, group, plan = scope(org, actor, row)
    syllabus = (
        query(
            "syllabus.Syllabus",
            org,
            pk=row["syllabus_id"],
            offering=offering,
            author_id=row["author_id"],
            subject_id=row["subject_id"],
            period_id=row["period_id"],
        )
        .select_for_update()
        .get()
    )
    if (
        query("syllabus.Syllabus", org, offering=offering).count() != 1
        or syllabus.reused_from_id is not None
        or not syllabus.is_active
    ):
        raise RestoreError("current_dossier_scope_changed")
    metadata = {f.attname: getattr(syllabus, f.attname) for f in syllabus._meta.concrete_fields}
    metadata["approved_version_id"] = None
    if core.digest(metadata) != row["syllabus_sha256"]:
        raise RestoreError("current_dossier_metadata_changed")
    versions = locked(query("syllabus.SyllabusVersion", org, syllabus=syllabus))
    expected = {row["draft_id"]} | ({str(source_version_id)} if source_version_id else set())
    if {str(v.pk) for v in versions} != expected:
        raise RestoreError("current_versions_changed")
    draft = next(v for v in versions if str(v.pk) == row["draft_id"])
    if (
        draft.status != "draft"
        or draft.approval_source != "human"
        or core.metadata_digest(draft) != row["draft_sha256"]
    ):
        raise RestoreError("human_draft_changed")
    sections = locked(query("syllabus.SyllabusSection", org, version=draft))
    section_pins = {r["id"]: r for r in row["section_pins"]}
    if {str(s.pk) for s in sections} != set(section_pins) or any(
        core.metadata_digest(s) != section_pins[str(s.pk)]["record_sha256"] for s in sections
    ):
        raise RestoreError("human_draft_sections_changed")
    actual_nonblank = sorted(
        s["section_id"]
        for s in content_fingerprints(section_data_map(draft))["sections"]
        if s["nonblank_string_present"]
    )
    if actual_nonblank != row["expected_nonblank_sections"]:
        raise RestoreError("human_draft_sections_changed")
    if query("syllabus.SyllabusReview", org, version__syllabus=syllabus).exists():
        raise RestoreError("current_review_history_changed")
    if (
        query("syllabus.SyllabusShare", org).filter(Q(syllabus=syllabus) | Q(offering=offering)).exists()
        or query("syllabus.Syllabus", org, reused_from=syllabus).exists()
        or query("syllabus.SyllabusVersion", org, source_version__syllabus=syllabus).exists()
    ):
        raise RestoreError("current_share_or_reuse_changed")
    if query("registrar.LanguageLevelCohort", org).filter(Q(offering=offering) | Q(source_offering=offering)).exists():
        raise RestoreError("unexpected_cohort_context")
    approved_id = None if undone or source_version_id is None else source_version_id
    if str(syllabus.approved_version_id or "") != str(approved_id or "") or syllabus.current_version_id != draft.pk:
        raise RestoreError("current_pointers_changed")
    if source_version_id:
        source = next(v for v in versions if str(v.pk) == str(source_version_id))
        if source.status != ("archived" if undone else "approved") or source.approval_source != "migration":
            raise RestoreError("restored_source_status_changed")
    protected = journal_academic_fingerprint(
        organization_id=org.pk, offerings=[offering], exclude=("syllabus", "version", "section", "review")
    )
    for label, qs in (
        ("group", query("organizations.OrgUnit", org, pk=group.pk)),
        ("subject", query("registrar.Subject", org, pk=offering.subject_id)),
        ("period", query("organizations.AcademicPeriod", org, pk=offering.period_id)),
        ("row", query("workload.TeachingTaskRow", org, pk=plan.pk)),
        ("task", query("workload.TeachingTask", org, pk=plan.task_id)),
        ("assignments", query("workload.TeacherAssignment", org, row=plan)),
        ("author_profile", core.model("accounts.UserProfile").objects.filter(user_id=row["author_id"])),
        ("author_memberships", query("organizations.Membership", org, user_id=row["author_id"])),
    ):
        protected[label] = queryset_database_fingerprint(qs)
    return (
        {
            "protected": protected,
            "syllabus": core.metadata_digest(syllabus),
            "versions": {str(v.pk): core.metadata_digest(v) for v in versions},
            "sections": {
                str(v.pk): queryset_database_fingerprint(query("syllabus.SyllabusSection", org, version=v))
                for v in versions
            },
        },
        syllabus,
        draft,
    )
