"""Exact source535 relink state; all academic data remains protected and in place."""

from django.db.models import Q

from apps.registrar.public import schedule_lock
from apps.syllabus.public import approved_version_for, content_fingerprints, syllabus_for_offering

from . import reviewed_ilahe_subject_spec as spec
from .offering_sync import eligible_instructor_ids
from .reviewed_leyla_catalog_graph import bounded, digest, graph, model, protected, require


def actor_scope(org, actor):
    require(str(org.pk) == spec.ORG and actor.is_active and actor.is_superuser, "ilahe_scoped_superadmin_required")
    require(
        model("organizations.Organization")
        .objects.select_for_update()
        .filter(pk=org.pk, is_active=True, status="active")
        .first()
        is not None,
        "ilahe_active_tenant_required",
    )
    User = model("auth.User")
    require(
        User.objects.select_for_update().filter(pk=actor.pk, is_active=True, is_superuser=True).values("id").first()
        is not None,
        "ilahe_scoped_superadmin_required",
    )
    require(
        User.objects.filter(
            Q(profile__organization_id=org.pk)
            | Q(memberships__organization_id=org.pk, memberships__is_active=True)
            | Q(owned_organizations__pk=org.pk),
            pk=actor.pk,
        ).exists(),
        "ilahe_actor_tenant_required",
    )
    require(
        not model("accounts.UserProfile")
        .objects.filter(user=actor)
        .exclude(is_deleted=False, deleted_at__isnull=True, blocked_at__isnull=True, access_state="active")
        .exists(),
        "ilahe_actor_inactive",
    )


def _bridge(org):
    result = []
    for pin in spec.BRIDGE:
        rows = bounded(
            model("legacy_import.LegacyEntityMap")._base_manager.filter(
                organization=org,
                source_system="myedu_mariadb",
                entity_type=pin["entity_type"],
                legacy_pk=pin["legacy_pk"],
            ),
            cap=2,
        )
        require(len(rows) == pin["count"] and digest(rows) == pin["sha256"], "ilahe_source_bridge_changed")
        result.append(
            {
                "entity_type": pin["entity_type"],
                "legacy_pk": pin["legacy_pk"],
                "count": len(rows),
                "sha256": digest(rows),
            }
        )
    return result


def _protected_academic(rows):
    result = {}
    for label, values in rows.items():
        if label == "syllabus.SyllabusShare":
            continue
        values = [dict(row) for row in values]
        if label in {"registrar.CourseOffering", "workload.TeachingTaskRow"}:
            target = spec.TARGET if label == "registrar.CourseOffering" else spec.ROW
            for row in values:
                if row["id"] == target:
                    row.pop("subject_id")
        result[label] = {"count": len(values), "sha256": digest(values)}
    return result


def _syllabi(org, offerings, corrected):
    query = (
        Q(offering_id__in=spec.OFFERINGS)
        | Q(author_id=spec.TEACHER, subject_id__in=(spec.OLD_SUBJECT, spec.NEW_SUBJECT), period_id__in=(spec.PERIOD,))
        | Q(author_id=spec.TEACHER, subject_id__in=(spec.OLD_SUBJECT, spec.NEW_SUBJECT), period_id__isnull=True)
    )
    rows = bounded(model("syllabus.Syllabus")._base_manager.filter(query, organization=org), cap=20)
    require({row["id"] for row in rows} == set(spec.SYLLABI), "ilahe_unreviewed_syllabus_or_human_draft")
    for row in rows:
        pin = spec.SYLLABI[row["id"]]
        require(
            row["author_id"] == spec.TEACHER
            and row["is_active"]
            and row["current_version_id"] == pin["version_id"] == row["approved_version_id"]
            and all(row[field] == pin[field] for field in ("subject_id", "offering_id", "period_id")),
            "ilahe_unreviewed_syllabus_or_human_draft",
        )
    source = model("syllabus.Syllabus")._base_manager.select_for_update().get(pk=spec.SOURCE_SYLLABUS)
    version = approved_version_for(source)
    require(
        version is not None and str(version.pk) == spec.SOURCE_VERSION and version.status == "approved",
        "ilahe_exact_approved_8668_required",
    )
    version = model("syllabus.SyllabusVersion")._base_manager.select_for_update().get(pk=version.pk)
    sections = list(version.sections.select_for_update().order_by("pk"))
    require(
        content_fingerprints({row.section_id: row.data for row in sections})["canonical_body_sha256"]
        == spec.SOURCE_BODY_SHA,
        "ilahe_source_8668_body_changed",
    )
    current = syllabus_for_offering(
        organization=org,
        offering_id=spec.TARGET,
        subject_id=spec.NEW_SUBJECT if corrected else spec.OLD_SUBJECT,
        period_id=spec.PERIOD,
        instructor_id=spec.TEACHER,
    )
    expected = (
        spec.SOURCE_SYLLABUS
        if corrected
        else next(pk for pk, pin in spec.SYLLABI.items() if pin["subject_id"] == spec.OLD_SUBJECT)
    )
    require(current is not None and str(current.pk) == expected, "ilahe_effective_syllabus_changed")
    return rows


def snapshot(org):
    schedule_lock.lock_schedule(org.pk, spec.PERIOD)
    offering_objects = list(
        model("registrar.CourseOffering")
        ._base_manager.select_for_update()
        .filter(organization=org, pk__in=spec.OFFERINGS)
        .order_by("pk")
    )
    require({str(obj.pk) for obj in offering_objects} == set(spec.OFFERINGS), "ilahe_fixed_courses_missing")
    course = next(obj for obj in offering_objects if str(obj.pk) == spec.TARGET)
    require(str(course.subject_id) in {spec.OLD_SUBJECT, spec.NEW_SUBJECT}, "ilahe_subject_changed")
    corrected = str(course.subject_id) == spec.NEW_SUBJECT
    for obj in offering_objects:
        pin = dict(spec.OFFERINGS[str(obj.pk)])
        if str(obj.pk) == spec.TARGET:
            pin["subject_id"] = spec.NEW_SUBJECT if corrected else spec.OLD_SUBJECT
        require(
            all(str(getattr(obj, field)) == str(value) for field, value in pin.items()), "ilahe_course_identity_changed"
        )
    cohorts = bounded(
        model("registrar.CourseOffering")._base_manager.filter(
            organization=org, subject_id__in=(spec.OLD_SUBJECT, spec.NEW_SUBJECT), period_id=spec.PERIOD
        ),
        cap=50,
    )
    require({row["id"] for row in cohorts} == set(spec.OFFERINGS), "ilahe_new_course_cohort_conflict")
    require(
        spec.TEACHER in eligible_instructor_ids(org.pk, {spec.TEACHER}), "ilahe_existing_teacher_permission_required"
    )
    require(
        model("accounts.UserProfile")
        .objects.select_for_update()
        .filter(
            organization=org,
            user_id=spec.TEACHER,
            user__is_active=True,
            is_deleted=False,
            deleted_at__isnull=True,
            blocked_at__isnull=True,
            access_state="active",
        )
        .first()
        is not None,
        "ilahe_teacher_inactive",
    )
    rows = bounded(
        model("workload.TeachingTaskRow")._base_manager.filter(
            organization=org, subject_id__in=(spec.OLD_SUBJECT, spec.NEW_SUBJECT), period_id=spec.PERIOD
        ),
        cap=30,
    )
    require({row["id"] for row in rows} == set(spec.ROWS), "ilahe_new_workload_authority_conflict")
    for row in rows:
        expected = dict(spec.ROWS[row["id"]])
        if row["id"] == spec.ROW:
            expected["subject_id"] = spec.NEW_SUBJECT if corrected else spec.OLD_SUBJECT
        require(
            all(str(row[field]) == str(value) for field, value in expected.items()), "ilahe_workload_identity_changed"
        )
    require(
        all(
            row["subject_id"] == (spec.NEW_SUBJECT if corrected else spec.OLD_SUBJECT)
            for row in rows
            if row["id"] == spec.ROW
        ),
        "ilahe_partial_subject_state",
    )
    tasks = bounded(model("workload.TeachingTask")._base_manager.filter(organization=org, pk=spec.TASK), cap=1)
    require(
        len(tasks) == 1
        and tasks[0]["chair_id"] == spec.CHAIR
        and tasks[0]["academic_year"] == "2026/2027"
        and tasks[0]["status"] in {"approved", "distributed", "amended"},
        "ilahe_released_task_changed",
    )
    periods = bounded(
        model("organizations.AcademicPeriod")._base_manager.filter(organization=org, pk=spec.PERIOD), cap=1
    )
    require(
        len(periods) == 1 and periods[0]["is_active"] and periods[0]["locked_at"] is None,
        "ilahe_period_locked_or_inactive",
    )
    for subject in (spec.OLD_SUBJECT, spec.NEW_SUBJECT):
        require(
            model("registrar.Subject")
            .objects.select_for_update()
            .filter(organization=org, pk=subject, is_active=True)
            .first()
            is not None,
            "ilahe_subject_inactive",
        )
    syllabi = _syllabi(org, offering_objects, corrected)
    academic = graph(
        spec.ORG,
        {
            "registrar.CourseOffering": set(spec.OFFERINGS),
            "workload.TeachingTaskRow": set(spec.ROWS),
            "syllabus.Syllabus": set(spec.SYLLABI),
        },
    )
    require(
        set(academic) - {"syllabus.SyllabusShare"} == set(spec.GRAPH_PINS), "ilahe_new_reverse_relation_requires_review"
    )
    for label, pin in spec.GRAPH_PINS.items():
        values = academic[label]
        require(len(values) == pin["count"], "ilahe_protected_row_count_changed")
        if not corrected or label not in {"registrar.CourseOffering", "workload.TeachingTaskRow"}:
            require(digest(values) == pin["sha256"], "ilahe_pinned_protected_content_changed")
    shares = academic.get("syllabus.SyllabusShare", [])
    require(
        len(shares) == int(corrected)
        and all(
            row["offering_id"] == spec.TARGET
            and row["syllabus_id"] == spec.SOURCE_SYLLABUS
            and row["source"] == "legacy"
            for row in shares
        ),
        "ilahe_unreviewed_syllabus_share",
    )
    enrollments = academic["registrar.Enrollment"]
    require(
        all(row["status"] == "enrolled" and row["superseded_by_id"] is None for row in enrollments),
        "ilahe_roster_history_changed",
    )
    primary_students = {row["student_id"] for row in enrollments if row["offering_id"] == spec.TARGET}
    require(
        not any(row["student_id"] in primary_students and row["offering_id"] != spec.TARGET for row in enrollments),
        "ilahe_new_subject_student_collision",
    )
    lesson_ids = {row["id"] for row in academic["registrar.Lesson"]}
    enrollment_ids = {row["id"] for row in enrollments}
    stable = {
        "registrar.JournalCorrection": bounded(
            model("registrar.JournalCorrection")
            ._base_manager.filter(organization=org)
            .filter(Q(enrollment_ref__in=enrollment_ids) | Q(lesson_ref__in=lesson_ids)),
            cap=200,
        ),
        "registrar.LessonCorrection": bounded(
            model("registrar.LessonCorrection")
            ._base_manager.filter(organization=org)
            .filter(Q(lesson_id__in=lesson_ids) | Q(lesson_id__isnull=True)),
            cap=200,
        ),
        "registrar.LegacyExcuseDocument": bounded(
            model("registrar.LegacyExcuseDocument")
            ._base_manager.filter(organization=org)
            .filter(Q(student_id__in={row["student_id"] for row in enrollments}) | Q(student_id__isnull=True)),
            cap=200,
        ),
    }
    amendments = bounded(
        model("workload.WorkloadAmendment").objects.filter(organization=org, task_id=spec.TASK, target_id=spec.ROW),
        cap=100,
    )
    return {
        "corrected": corrected,
        "tasks": tasks,
        "periods": periods,
        "rows": rows,
        "source": digest(spec.SOURCE),
        "bridge": _bridge(org),
        "academic": _protected_academic(academic),
        "shares": shares,
        "stable_history": protected(
            graph(spec.ORG, {label: {row["id"] for row in values} for label, values in stable.items()})
        ),
        "amendments": amendments,
        "approved_body": spec.SOURCE_BODY_SHA,
        "syllabus_ids": sorted(row["id"] for row in syllabi),
    }
