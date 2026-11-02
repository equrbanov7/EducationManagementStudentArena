"""Locked full reverse graph; only the exact target subject is mutable."""

from django.db.models import Q

from apps.registrar.public import eligible_instructor_user_ids, schedule_lock
from apps.syllabus.public import content_fingerprints

from . import reviewed_jale_subject_spec as spec
from .reviewed_ilahe_subject_state import actor_scope as _validated_actor_scope
from .reviewed_leyla_catalog_graph import RepairError, bounded, digest, graph, model, require


def actor_scope(org, actor):
    try:
        _validated_actor_scope(org, actor)
    except RepairError:
        raise RepairError("jale_actor_scope_refused") from None


def _bridge(org):
    rows = bounded(
        model("legacy_import.LegacyEntityMap")._base_manager.filter(
            organization=org, source_system="myedu_mariadb", entity_type="worker", legacy_pk="949"
        ),
        cap=2,
    )
    require(len(rows) == 1, "jale_worker_bridge_missing")
    row = rows[0]
    require(
        row["target_model_label"] == "auth.user"
        and row["target_pk"] == str(spec.TEACHER)
        and row["state"] == "migrated"
        and row["source_row_hash"] == spec.WORKER_HASH,
        "jale_worker_bridge_changed",
    )
    return {"count": 1, "sha256": digest(rows)}


def _source_body(org):
    source = model("syllabus.Syllabus")._base_manager.select_for_update().get(pk=spec.SOURCE_SYLLABUS, organization=org)
    require(
        str(source.subject_id) == spec.NEW_SUBJECT
        and str(source.period_id) == spec.PERIOD
        and str(source.offering_id) in set(spec.OFFERINGS) - {spec.TARGET}
        and source.author_id is None
        and source.is_active
        and str(source.current_version_id) == spec.SOURCE_VERSION == str(source.approved_version_id),
        "jale_readonly_source_anchor_changed",
    )
    version = (
        model("syllabus.SyllabusVersion")._base_manager.select_for_update().get(pk=spec.SOURCE_VERSION, syllabus=source)
    )
    require(version.status == "approved", "jale_readonly_source_approval_changed")
    sections = bounded(model("syllabus.SyllabusSection")._base_manager.filter(version=version), cap=20)
    body = content_fingerprints({row["section_id"]: row["data"] for row in sections})
    require(body["canonical_body_sha256"] == spec.SOURCE_BODY_SHA, "jale_readonly_source_body_changed")
    require(body["topic_summary"]["nonempty_topic_count"] == 120, "jale_own_source_topics_changed")
    # This is a read-only anchor for already imported own7456. Never copy/link/approve it.
    return {"source_proof": digest(spec.SOURCE), "body_sha256": spec.SOURCE_BODY_SHA}


def _protected(rows):
    result = {}
    for label, values in rows.items():
        values = [dict(row) for row in values]
        if label == "registrar.CourseOffering":
            for row in values:
                if row["id"] == spec.TARGET:
                    row.pop("subject_id")
        result[label] = {"count": len(values), "sha256": digest(values)}
    return result


def _handovers(org):
    """Require the four already completed canonical handovers, never infer a merge."""
    rows = bounded(
        model("registrar.TeachingHandover")._base_manager.filter(organization=org, offering_id__in=spec.OFFERINGS),
        cap=5,
    )
    require(
        len(rows) == 4
        and {row["offering_id"] for row in rows} == set(spec.OFFERINGS)
        and all(
            row["from_instructor_id"] is None
            and row["to_instructor_id"] == spec.CURRENT_OWNER
            and row["performed_by_id"] == spec.HANDOVER_ACTOR
            and row["reverted_at"] is None
            and row["reverted_by_id"] is None
            and row["deactivated_share_ids"] == []
            for row in rows
        ),
        "jale_exact_handover_chain_changed",
    )
    return {"count": 4, "sha256": digest(rows)}


def snapshot(org):
    schedule_lock.lock_schedule(org.pk, spec.PERIOD)
    courses = bounded(
        model("registrar.CourseOffering")._base_manager.filter(organization=org, pk__in=spec.OFFERINGS), cap=4
    )
    require({row["id"] for row in courses} == set(spec.OFFERINGS), "jale_course_scope_changed")
    target = next(row for row in courses if row["id"] == spec.TARGET)
    require(target["subject_id"] in {spec.OLD_SUBJECT, spec.NEW_SUBJECT}, "jale_subject_changed")
    corrected = target["subject_id"] == spec.NEW_SUBJECT
    for row in courses:
        subject = spec.OLD_SUBJECT if row["id"] == spec.TARGET and not corrected else spec.NEW_SUBJECT
        require(
            row["subject_id"] == subject
            and row["group_id"] == spec.OFFERINGS[row["id"]]
            and row["period_id"] == spec.PERIOD
            and row["instructor_id"] == spec.CURRENT_OWNER
            and row["lesson_hours"] == 150
            and row["is_active"],
            "jale_fixed_course_identity_changed",
        )
    require(
        spec.CURRENT_OWNER in eligible_instructor_user_ids(organization=org),
        "jale_current_owner_not_eligible",
    )
    handovers = _handovers(org)
    require(
        not model("registrar.CourseOffering")
        ._base_manager.filter(organization=org, subject_id=spec.NEW_SUBJECT, group_id=spec.GROUP, period_id=spec.PERIOD)
        .exclude(pk=spec.TARGET)
        .exists(),
        "jale_new_subject_collision",
    )
    period = bounded(
        model("organizations.AcademicPeriod")._base_manager.filter(organization=org, pk=spec.PERIOD), cap=1
    )
    require(len(period) == 1 and period[0]["is_active"] and period[0]["locked_at"] is None, "jale_period_locked")
    subjects = bounded(
        model("registrar.Subject")._base_manager.filter(organization=org, pk__in=(spec.OLD_SUBJECT, spec.NEW_SUBJECT)),
        cap=2,
    )
    require(len(subjects) == 2 and all(row["is_active"] for row in subjects), "jale_subject_inactive")
    require(
        not model("syllabus.Syllabus")._base_manager.filter(organization=org, offering_id=spec.TARGET).exists()
        and not model("syllabus.SyllabusShare")
        ._base_manager.filter(organization=org, offering_id=spec.TARGET)
        .exists(),
        "jale_target_content_requires_separate_review",
    )
    shares = bounded(
        model("registrar.JournalShare")._base_manager.filter(organization=org, offering_id__in=spec.OFFERINGS), cap=10
    )
    require(
        len(shares) == 4
        and {row["offering_id"] for row in shares} == set(spec.OFFERINGS)
        and all(row["teacher_id"] == spec.TEACHER and row["is_active"] and row["kinds"] == [] for row in shares),
        "jale_exact_journal_shares_changed",
    )
    users = bounded(model("auth.User")._base_manager.filter(pk__in=(spec.TEACHER, spec.SEPARATE_ACCOUNT)), cap=2)
    # Receipt hashes include the two accounts but never log passwords or contacts.
    user_hashes = {str(row["id"]): digest(row) for row in users}
    require(len(users) == 2 and all(row["is_active"] for row in users), "jale_separate_accounts_changed")
    profiles = bounded(
        model("accounts.UserProfile")._base_manager.filter(user_id__in=(spec.TEACHER, spec.SEPARATE_ACCOUNT)), cap=2
    )
    require(len(profiles) == 2, "jale_separate_accounts_changed")
    memberships = bounded(
        model("organizations.Membership")._base_manager.filter(user_id__in=(spec.TEACHER, spec.SEPARATE_ACCOUNT)),
        cap=30,
    )
    account_state = {"users": user_hashes, "profiles": digest(profiles), "memberships": digest(memberships)}
    protected_graph = graph(spec.ORG, {"registrar.CourseOffering": set(spec.OFFERINGS)})
    for label, count in spec.FULL_COUNTS.items():
        require(len(protected_graph.get(label, [])) == count, "jale_protected_counts_changed")
    root_graph = graph(spec.ORG, {"registrar.CourseOffering": {spec.TARGET}})
    for label, count in spec.COUNTS.items():
        require(len(root_graph.get(label, [])) == count, "jale_protected_counts_changed")
    enrs = root_graph["registrar.Enrollment"]
    lessons = root_graph["registrar.Lesson"]
    soft = {
        "registrar.JournalCorrection": bounded(
            model("registrar.JournalCorrection")
            ._base_manager.filter(organization=org)
            .filter(
                Q(enrollment_ref__in=[row["id"] for row in enrs]) | Q(lesson_ref__in=[row["id"] for row in lessons])
            ),
            cap=500,
        ),
        "registrar.LessonCorrection": bounded(
            model("registrar.LessonCorrection")
            ._base_manager.filter(organization=org)
            .filter(Q(lesson_id__in=[row["id"] for row in lessons]) | Q(lesson_id__isnull=True)),
            cap=500,
        ),
    }
    return {
        "corrected": corrected,
        "period": period,
        "subjects": subjects,
        "accounts": account_state,
        "bridge": _bridge(org),
        "source": _source_body(org),
        "current_owner_handovers": handovers,
        "academic": _protected(protected_graph),
        "soft_history": {label: {"count": len(rows), "sha256": digest(rows)} for label, rows in soft.items()},
    }
