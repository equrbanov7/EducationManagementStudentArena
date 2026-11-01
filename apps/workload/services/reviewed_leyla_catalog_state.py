"""Fresh exact identities and complete protected references for the two reviewed rows."""

from types import SimpleNamespace

from django.db.models import Q

from apps.syllabus.public import approved_version_for, content_fingerprints, syllabus_for_offering

from . import reviewed_leyla_catalog_schedule as schedule_state
from . import reviewed_leyla_catalog_spec as spec
from .group_projection import project_group_settings
from .offering_rules import per_group_hours
from .offering_sync import eligible_instructor_ids
from .reviewed_leyla_catalog_graph import bounded, digest, graph, model, normal, protected, require


def actor_scope(org, actor):
    tenant = (
        model("organizations.Organization")
        .objects.select_for_update()
        .filter(pk=org.pk, is_active=True, status="active")
        .first()
    )
    require(tenant is not None, "leyla_active_tenant_superadmin_required")
    require(
        str(org.pk) == spec.ORG and org.is_active and org.status == "active" and actor.is_active and actor.is_superuser,
        "leyla_active_tenant_superadmin_required",
    )
    User = model("auth.User")
    locked = User.objects.select_for_update().filter(pk=actor.pk, is_active=True, is_superuser=True).first()
    require(locked is not None, "leyla_active_tenant_superadmin_required")
    require(
        User.objects.filter(
            Q(profile__organization_id=org.pk)
            | Q(memberships__organization_id=org.pk, memberships__is_active=True)
            | Q(owned_organizations__pk=org.pk),
            pk=actor.pk,
            is_active=True,
            is_superuser=True,
        ).exists(),
        "leyla_actor_tenant_required",
    )
    profiles = model("accounts.UserProfile").objects.filter(user=actor)
    require(
        not profiles.exclude(
            is_deleted=False, deleted_at__isnull=True, blocked_at__isnull=True, access_state="active"
        ).exists(),
        "leyla_actor_profile_inactive",
    )


def _identities(org):
    Offering = model("registrar.CourseOffering")
    objects = list(Offering._base_manager.select_for_update().filter(pk__in=spec.OFFERINGS).order_by("pk"))
    require({str(o.pk) for o in objects} == set(spec.OFFERINGS), "leyla_fixed_offerings_missing")
    for obj in objects:
        pin = spec.OFFERINGS[str(obj.pk)]
        require(
            str(obj.organization_id) == spec.ORG
            and not obj.is_intensive
            and all(str(getattr(obj, k)) == str(v) for k, v in pin.items()),
            "leyla_offering_identity_changed",
        )
        rivals = Offering._base_manager.filter(
            organization=org, subject_id=obj.subject_id, period_id=obj.period_id, group_id=obj.group_id
        )
        require(set(map(str, rivals.values_list("pk", flat=True))) == {str(obj.pk)}, "leyla_canonical_course_ambiguous")
    tenant_ids = list(
        model("organizations.OrgUnit")
        .objects.filter(organization=org)
        .order_by("pk")
        .values_list("pk", flat=True)[:5001]
    )
    require(len(tenant_ids) <= 5000, "leyla_group_budget")
    for gid, pin in spec.GROUPS.items():
        group = model("organizations.OrgUnit").objects.select_for_update().filter(pk=gid, organization=org).first()
        require(
            group is not None
            and all(normal(getattr(group, k)) == v for k, v in pin.items() if k != "settings")
            and project_group_settings(group.settings, canonical_group_ids=tenant_ids)
            == project_group_settings(pin["settings"], canonical_group_ids=tenant_ids),
            "leyla_group_identity_changed",
        )
    for sid, pin in spec.SUBJECTS.items():
        subject = model("registrar.Subject").objects.select_for_update().filter(pk=sid, organization=org).first()
        require(
            subject is not None and subject.is_active and all(getattr(subject, k) == v for k, v in pin.items()),
            "leyla_subject_identity_changed",
        )
    require(
        model("auth.User").objects.select_for_update().filter(pk=spec.TEACHER, is_active=True).first() is not None,
        "leyla_teacher_profile_inactive",
    )
    profile = (
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
    )
    require(profile.first() is not None, "leyla_teacher_profile_inactive")
    memberships = bounded(
        model("organizations.Membership").objects.filter(organization=org, user_id=spec.TEACHER), cap=20
    )
    bounded(model("organizations.Role").objects.filter(pk__in=[m["role_id"] for m in memberships]), cap=20)
    require(
        spec.TEACHER in eligible_instructor_ids(org.pk, {spec.TEACHER}), "leyla_existing_teacher_permission_required"
    )
    return objects


def _bridge(org):
    query = Q(pk__in=[])
    for pin in spec.BRIDGE:
        query |= Q(entity_type=pin["entity_type"], legacy_pk=pin["legacy_pk"])
    rows = bounded(
        model("legacy_import.LegacyEntityMap").objects.filter(query, organization=org, source_system="myedu_mariadb"),
        cap=20,
    )
    fields = tuple(spec.BRIDGE[0])
    actual = [{k: r[k] for k in fields} for r in rows]
    require(
        digest(sorted(actual, key=lambda r: (r["entity_type"], r["legacy_pk"])))
        == digest(sorted(spec.BRIDGE, key=lambda r: (r["entity_type"], r["legacy_pk"]))),
        "leyla_typed_source_bridge_changed",
    )
    return rows


def _rows(org):
    result = bounded(model("workload.TeachingTaskRow").objects.filter(organization=org, pk__in=spec.ROWS), cap=2)
    require(len(result) == len(spec.ROWS), "leyla_fixed_rows_missing")
    subjects = []
    for row in result:
        pin = spec.ROWS[row["id"]]
        require(all(str(row[k]) == str(v) for k, v in pin["fields"].items()), "leyla_official_row_fields_changed")
        groups = set(
            map(str, model("workload.TeachingTaskRow").objects.get(pk=row["id"]).groups.values_list("pk", flat=True))
        )
        require(groups == set(pin["groups"]), "leyla_official_row_groups_changed")
        require(row["subject_id"] in (pin["before_subject"], pin["after_subject"]), "leyla_row_subject_changed")
        subjects.append(row["subject_id"] == pin["after_subject"])
    require(len(set(subjects)) == 1, "leyla_partial_relink_state")
    ass = bounded(model("workload.TeacherAssignment")._base_manager.filter(row_id__in=spec.ROWS), cap=10)
    require(all(a["organization_id"] == spec.ORG for a in ass), "leyla_assignment_tenant_changed")
    fields = tuple(spec.ASSIGNMENTS[0])
    require(
        digest([{k: r[k] for k in fields} for r in ass]) == digest(sorted(spec.ASSIGNMENTS, key=lambda r: r["id"])),
        "leyla_exact_allocations_changed",
    )
    rivals_query = Q(pk__in=[])
    for pin in spec.ROWS.values():
        rivals_query |= Q(subject_id=pin["after_subject"], period_id=spec.PERIOD, groups__pk__in=pin["groups"])
    rival_ids = list(
        model("workload.TeachingTaskRow")
        ._base_manager.filter(rivals_query, organization=org)
        .exclude(pk__in=spec.ROWS)
        .order_by("pk")
        .values_list("pk", flat=True)
        .distinct()[:101]
    )
    require(len(rival_ids) <= 100, "leyla_rival_row_budget")
    rivals = bounded(model("workload.TeachingTaskRow")._base_manager.filter(pk__in=rival_ids), cap=100)
    rival_assignments = bounded(model("workload.TeacherAssignment")._base_manager.filter(row_id__in=rival_ids), cap=200)
    require(
        not any(r["total_hours"] > 0 for r in rivals) and not any(a["hours"] > 0 for a in rival_assignments),
        "leyla_existing_canonical_workload_authority",
    )
    for rival in rivals:
        actual = per_group_hours(SimpleNamespace(**rival))
        matching = [pin for pin in spec.ROWS.values() if pin["after_subject"] == rival["subject_id"]]
        expected = per_group_hours(SimpleNamespace(**matching[0]["fields"]))
        require(all(actual[k] <= expected[k] for k in actual), "leyla_canonical_plan_hours_conflict")
    return result, ass, subjects[0], {"rows": rivals, "assignments": rival_assignments}


def _academic(org, offerings):
    Lesson = model("registrar.Lesson")
    require(not Lesson._base_manager.filter(offering_id__in=spec.EMPTY).exists(), "leyla_named_journal_no_longer_empty")
    marks = bounded(
        model("registrar.LessonMark")._base_manager.filter(lesson__offering_id__in=spec.FILLED), cap=spec.MARK_COUNT
    )
    require(len(marks) == spec.MARK_COUNT, "leyla_canonical_cell_count_changed")
    require(
        digest([{k: r[k] for k in spec.MARK_FIELDS} for r in marks]) == spec.MARK_SHA256,
        "leyla_canonical_cells_changed",
    )
    enrollment = model("registrar.Enrollment")
    for gid, pin in spec.ROSTERS.items():
        for offering in (o for o in offerings if str(o.group_id) == gid):
            rows = bounded(
                enrollment._base_manager.filter(offering=offering, organization=org, status="enrolled"), cap=100
            )
            users = sorted(r["student_id"] for r in rows)
            require(
                len(users) == pin["count"]
                and digest(users) == pin["sha256"]
                and all(r["superseded_by_id"] is None for r in rows),
                "leyla_active_roster_changed",
            )
    syllabus_ids = set()
    for pin in spec.SYLLABI:
        obj = next(o for o in offerings if str(o.pk) == pin["offering_id"])
        syl = syllabus_for_offering(
            organization=org,
            offering_id=obj.pk,
            subject_id=obj.subject_id,
            period_id=obj.period_id,
            instructor_id=obj.instructor_id,
        )
        if syl:
            syl = model("syllabus.Syllabus")._base_manager.select_for_update().get(pk=syl.pk)
        version = approved_version_for(syl) if syl else None
        if version:
            version = model("syllabus.SyllabusVersion")._base_manager.select_for_update().get(pk=version.pk)
        require(
            syl is not None
            and str(syl.pk) == pin["syllabus_id"]
            and syl.organization_id == org.pk
            and syl.author_id == spec.TEACHER
            and syl.subject_id == obj.subject_id
            and syl.period_id in (None, obj.period_id)
            and version is not None
            and str(version.pk) == pin["version_id"],
            "leyla_approved_syllabus_binding_changed",
        )
        require(
            content_fingerprints({s.section_id: s.data for s in version.sections.select_for_update().all()})[
                "canonical_body_sha256"
            ]
            == pin["canonical_body_sha256"],
            "leyla_approved_syllabus_body_changed",
        )
        syllabus_ids.add(str(syl.pk))
    scope = Q(offering_id__in=spec.OFFERINGS) | Q(
        author_id=spec.TEACHER, subject_id__in=spec.SUBJECTS, period_id=spec.PERIOD
    )
    syllabi = bounded(model("syllabus.Syllabus")._base_manager.filter(scope, organization=org), cap=40)
    named_subjects = {r["before_subject"] for r in spec.ROWS.values()}
    require(
        not any(r["subject_id"] in named_subjects for r in syllabi), "leyla_named_syllabus_requires_explicit_review"
    )
    syllabus_ids.update(r["id"] for r in syllabi)
    roots = {
        "registrar.CourseOffering": set(spec.OFFERINGS),
        "workload.TeachingTaskRow": set(spec.ROWS),
        "syllabus.Syllabus": syllabus_ids,
    }
    result = graph(spec.ORG, roots)
    # Recheck after parent/child locks: an insertion before traversal must not bypass the pinned cells.
    final_marks = bounded(
        model("registrar.LessonMark")._base_manager.filter(lesson__offering_id__in=spec.FILLED), cap=spec.MARK_COUNT
    )
    require(
        digest([{k: r[k] for k in spec.MARK_FIELDS} for r in final_marks]) == spec.MARK_SHA256,
        "leyla_canonical_cells_changed",
    )
    named_enrollments = {r["id"] for r in result.get("registrar.Enrollment", []) if r["offering_id"] in spec.EMPTY}
    allowed = {
        "registrar.Enrollment",
        "registrar.AssessmentScheme",
        "registrar.AssessmentComponent",
        "registrar.ScheduleSlot",
    }
    for label, values in result.items():
        cls = model(label)
        offering_fields = [
            f.attname
            for f in cls._meta.concrete_fields
            if f.is_relation and f.related_model == model("registrar.CourseOffering")
        ]
        if label not in allowed:
            require(
                not any(any(r.get(f) in spec.EMPTY for f in offering_fields) for r in values),
                "leyla_named_reference_requires_review",
            )
        require(
            not any(r.get("enrollment_id") in named_enrollments for r in values),
            "leyla_named_enrollment_content_requires_review",
        )
    return result


def snapshot(org):
    schedule_state.lock_scope(org)  # Match the canonical scheduler lock order before any course/slot locks.
    tasks = bounded(model("workload.TeachingTask").objects.filter(organization=org, pk=spec.TASK), cap=1)
    require(
        len(tasks) == 1
        and tasks[0]["academic_year"] == spec.YEAR
        and tasks[0]["chair_id"] == spec.CHAIR
        and tasks[0]["status"] in ("approved", "distributed", "amended"),
        "leyla_released_task_changed",
    )
    require(
        model("organizations.OrgUnit")
        .objects.select_for_update()
        .filter(pk=spec.CHAIR, organization=org, is_active=True, unit_type="chair")
        .first()
        is not None,
        "leyla_official_chair_changed",
    )
    periods = bounded(model("organizations.AcademicPeriod").objects.filter(pk=spec.PERIOD, organization=org), cap=1)
    require(
        len(periods) == 1 and periods[0]["academic_year"] == spec.YEAR and periods[0]["is_active"],
        "leyla_period_identity_changed",
    )
    offerings = _identities(org)
    bridge = _bridge(org)
    rows, assignments, corrected, rivals = _rows(org)
    academic = _academic(org, offerings)
    amendments = bounded(
        model("workload.WorkloadAmendment").objects.filter(
            organization=org, task_id=spec.TASK, target_kind="row", target_id__in=spec.ROWS
        ),
        cap=100,
    )
    academic.pop("registrar.ScheduleSlot", None)  # Checked separately with exact parking/copy/undo invariants.
    return {
        "schedule": schedule_state.capture(org),
        "groups": bounded(model("organizations.OrgUnit").objects.filter(pk__in=spec.GROUPS), cap=3),
        "subjects": bounded(model("registrar.Subject").objects.filter(pk__in=spec.SUBJECTS), cap=4),
        "rows": rows,
        "canonical_other_rows": rivals,
        "periods": periods,
        "assignments": assignments,
        "tasks": tasks,
        "amendments": amendments,
        "protected": protected(academic),
        "bridge": bridge,
        "corrected": corrected,
        "source_sha256": digest(spec.SOURCE),
        "selection_sha256": digest(spec.ROWS),
    }
