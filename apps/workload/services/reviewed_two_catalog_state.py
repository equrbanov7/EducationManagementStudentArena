"""Locked fresh two-case state; full graph retained, no timetable/content projection."""

from django.db.models import Q

from apps.registrar.public import schedule_conflicts, schedule_lock
from apps.syllabus.public import approved_version_for, content_fingerprints, syllabus_for_offering

from . import reviewed_two_catalog_schema as schema
from . import reviewed_two_catalog_spec as spec
from .group_projection import project_group_settings
from .offering_sync import eligible_instructor_ids
from .reviewed_leyla_catalog_graph import bounded, digest, graph, model, normal, protected, require
from .scoped_snapshot import data as snapshots


def actor_scope(org, actor, *, contract=spec):
    require(
        str(org.pk) == contract.ORG and actor.is_active and actor.is_superuser, "two_catalog_tenant_superadmin_required"
    )
    tenant = (
        model("organizations.Organization")
        .objects.select_for_update()
        .only("id", "owner_id")
        .filter(pk=org.pk, is_active=True, status="active")
        .first()
    )
    require(tenant is not None, "two_catalog_active_tenant_required")
    require(
        model("auth.User").objects.select_for_update().filter(pk=actor.pk, is_active=True, is_superuser=True).exists(),
        "two_catalog_tenant_superadmin_required",
    )
    memberships = bounded(model("organizations.Membership").objects.filter(organization=org, user_id=actor.pk), cap=20)
    profiles = normal(
        list(
            model("accounts.UserProfile")
            .objects.select_for_update()
            .filter(user_id=actor.pk)
            .values("organization_id", "is_deleted", "deleted_at", "blocked_at", "access_state")
        )
    )
    require(
        str(tenant.owner_id) == str(actor.pk)
        or any(m["is_active"] for m in memberships)
        or any(p["organization_id"] == contract.ORG for p in profiles),
        "two_catalog_actor_tenant_required",
    )
    require(
        all(
            not p["is_deleted"]
            and p["deleted_at"] is None
            and p["blocked_at"] is None
            and p["access_state"] == "active"
            for p in profiles
        ),
        "two_catalog_actor_profile_inactive",
    )


def _identity(org, pin, contract=spec):
    Offering = model("registrar.CourseOffering")
    objects = list(
        Offering._base_manager.select_for_update().filter(pk__in=pin["offerings"], organization=org).order_by("pk")
    )
    require({str(o.pk) for o in objects} == set(pin["offerings"]), "two_catalog_fixed_courses_missing")
    for obj in objects:
        require(
            str(obj.organization_id) == contract.ORG
            and not obj.is_intensive
            and all(normal(getattr(obj, k)) == v for k, v in pin["offerings"][str(obj.pk)].items()),
            "two_catalog_course_identity_changed",
        )
        require(
            Offering._base_manager.filter(
                organization=org, subject_id=obj.subject_id, period_id=obj.period_id, group_id=obj.group_id
            ).count()
            == 1,
            "two_catalog_ambiguous_course",
        )
    group = model("organizations.OrgUnit").objects.select_for_update().get(pk=pin["group"]["id"], organization=org)
    canonical_ids = list(
        model("organizations.OrgUnit").objects.filter(organization=org).values_list("pk", flat=True)[:5001]
    )
    require(len(canonical_ids) <= 5000, "two_catalog_group_budget")
    require(
        all(normal(getattr(group, k)) == v for k, v in pin["group"].items() if k != "settings")
        and project_group_settings(group.settings, canonical_group_ids=canonical_ids)
        == project_group_settings(pin["group"]["settings"], canonical_group_ids=canonical_ids),
        "two_catalog_group_identity_changed",
    )
    for sid, expected in pin["subjects"].items():
        subject = model("registrar.Subject").objects.select_for_update().get(pk=sid, organization=org)
        require(
            subject.is_active and all(normal(getattr(subject, k)) == v for k, v in expected.items()),
            "two_catalog_subject_identity_changed",
        )
    teacher = pin["teacher"]
    require(
        model("auth.User").objects.select_for_update().filter(pk=teacher, is_active=True).exists()
        and model("accounts.UserProfile")
        .objects.select_for_update()
        .filter(
            user_id=teacher,
            organization=org,
            is_deleted=False,
            deleted_at__isnull=True,
            blocked_at__isnull=True,
            access_state="active",
        )
        .exists()
        and teacher in eligible_instructor_ids(org.pk, {teacher}),
        "two_catalog_teacher_permission_changed",
    )
    return objects


def _authority(org, pin):
    memberships = bounded(
        model("organizations.Membership").objects.filter(organization=org, user_id=pin["teacher"]), cap=20
    )
    roles = bounded(model("organizations.Role").objects.filter(pk__in=[r["role_id"] for r in memberships]), cap=20)
    profile = list(
        model("accounts.UserProfile")
        .objects.select_for_update()
        .filter(user_id=pin["teacher"])
        .values("id", "organization_id", "user_id", "is_deleted", "deleted_at", "blocked_at", "access_state")
    )
    return {"memberships": memberships, "roles": roles, "profile": normal(profile)}


def _bridge(org, pin):
    query = Q(pk__in=[])
    for p in pin["bridge"]:
        query |= Q(entity_type=p["entity_type"], legacy_pk=p["legacy_pk"])
    result = bounded(
        model("legacy_import.LegacyEntityMap").objects.filter(query, organization=org, source_system="myedu_mariadb"),
        cap=20,
    )
    fields = tuple(pin["bridge"][0])
    actual = [{k: r[k] for k in fields} for r in result]
    require(
        digest(sorted(actual, key=lambda r: (r["entity_type"], r["legacy_pk"])))
        == digest(sorted(pin["bridge"], key=lambda r: (r["entity_type"], r["legacy_pk"]))),
        "two_catalog_typed_source_bridge_changed",
    )
    return result


def _rosters(org, objects, pin):
    for obj in objects:
        rows = bounded(
            model("registrar.Enrollment")._base_manager.filter(offering=obj, organization=org, status="enrolled"),
            cap=100,
        )
        users = sorted(r["student_id"] for r in rows)
        require(
            len(users) == len(set(users)) == pin["roster"]["count"]
            and digest(users) == pin["roster"]["sha256"]
            and all(r["superseded_by_id"] is None for r in rows),
            "two_catalog_exact_roster_changed",
        )


def _donor(org, objects, pin):
    course = next(o for o in objects if str(o.pk) == pin["filled"])
    syllabus = syllabus_for_offering(
        organization=org,
        offering_id=course.pk,
        subject_id=course.subject_id,
        period_id=course.period_id,
        instructor_id=course.instructor_id,
    )
    require(syllabus is not None and str(syllabus.pk) == pin["donor"]["id"], "two_catalog_donor_binding_changed")
    syllabus = model("syllabus.Syllabus")._base_manager.select_for_update().get(pk=syllabus.pk)
    require(
        syllabus.organization_id == org.pk
        and syllabus.author_id == pin["teacher"]
        and syllabus.subject_id == course.subject_id
        and syllabus.period_id in (None, course.period_id),
        "two_catalog_donor_identity_changed",
    )
    version = approved_version_for(syllabus)
    require(
        version is not None and str(version.pk) == pin["donor"]["approved_version_id"] and version.status == "approved",
        "two_catalog_approved_own_source_required",
    )
    version = model("syllabus.SyllabusVersion")._base_manager.select_for_update().get(pk=version.pk)
    require(
        version.status == "approved" and version.organization_id == org.pk and version.syllabus_id == syllabus.pk,
        "two_catalog_approved_own_source_required",
    )
    sections = list(version.sections.select_for_update().all())
    require(
        content_fingerprints({s.section_id: s.data for s in sections})["canonical_body_sha256"]
        == pin["donor"]["body_sha256"],
        "two_catalog_approved_source_body_changed",
    )


def _rivals(org, pin, contract=spec):
    rivals = bounded(
        model("workload.TeachingTaskRow")
        .objects.filter(
            organization=org, subject_id=pin["after_subject"], period_id=contract.PERIOD, groups__id=pin["group"]["id"]
        )
        .exclude(pk=pin["row_id"]),
        cap=20,
    )
    assignments = bounded(
        model("workload.TeacherAssignment").objects.filter(organization=org, row_id__in=[r["id"] for r in rivals]),
        cap=40,
    )
    require(
        not any(r["total_hours"] > 0 for r in rivals) and not any(a["hours"] > 0 for a in assignments),
        "two_catalog_existing_canonical_workload_authority",
    )
    return {"rows": rivals, "assignments": assignments}


def _schedule(org, objects, pin, contract=spec):
    # No slot is parked, copied, created or changed. Existing target conflicts hold.
    target = next(o for o in objects if str(o.pk) == pin["filled"])
    slots = list(
        model("registrar.ScheduleSlot")
        .all_objects.select_for_update()
        .filter(organization=org, offering=target, is_parked=False, is_deleted=False)
        .order_by("pk")
    )
    require(len(slots) <= 24, "two_catalog_schedule_budget")
    for slot in slots:
        require(
            not schedule_conflicts.detect(
                organization=org,
                period_id=contract.PERIOD,
                group_id=target.group_id,
                subject_id=target.subject_id,
                offering_id=target.pk,
                instructor_id=pin["teacher"],
                exclude_ids=[slot.pk],
                **{k: getattr(slot, k) for k in ("weekday", "start_time", "end_time", "room", "week_type", "kind")},
            ),
            "two_catalog_target_schedule_conflict",
        )


def snapshot(org, *, contract=spec):
    require(len(contract.CASES) in (1, 2), "two_catalog_fixed_scope_required")
    require(schema.fingerprints() == contract.SCHEMA, "two_catalog_unreviewed_relation_schema")
    schedule_lock.lock_schedule(org.pk, contract.PERIOD)
    periods = bounded(model("organizations.AcademicPeriod").objects.filter(pk=contract.PERIOD, organization=org), cap=1)
    require(
        len(periods) == 1
        and periods[0]["academic_year"] == contract.YEAR
        and periods[0]["is_active"]
        and periods[0]["locked_at"] is None,
        "two_catalog_period_locked_or_changed",
    )
    result = {"periods": periods, "cases": []}
    all_offerings, all_rows, syllabus_query = [], [], Q(pk__in=[])
    corrected = []
    for pin in contract.CASES:
        task = bounded(
            model("workload.TeachingTask").objects.filter(pk=pin["row_fields"]["task_id"], organization=org), cap=1
        )
        require(
            len(task) == 1
            and task[0]["academic_year"] == contract.YEAR
            and task[0]["chair_id"] == pin["source"]["chair_id"]
            and task[0]["status"] in ("approved", "distributed", "amended"),
            "two_catalog_released_task_changed",
        )
        require(
            model("organizations.OrgUnit")
            .objects.filter(organization=org, pk=task[0]["chair_id"], is_active=True, unit_type="chair")
            .exists(),
            "two_catalog_official_chair_changed",
        )
        objects = _identity(org, pin, contract)
        all_offerings.extend(objects)
        rows = bounded(model("workload.TeachingTaskRow").objects.filter(pk=pin["row_id"], organization=org), cap=1)
        require(
            len(rows) == 1
            and all(rows[0][k] == v for k, v in pin["row_fields"].items())
            and rows[0]["subject_id"] in (pin["before_subject"], pin["after_subject"]),
            "two_catalog_row_fields_changed",
        )
        groups = set(
            map(
                str, model("workload.TeachingTaskRow").objects.get(pk=pin["row_id"]).groups.values_list("pk", flat=True)
            )
        )
        require(groups == {pin["group"]["id"]}, "two_catalog_row_groups_changed")
        assignments = bounded(
            model("workload.TeacherAssignment").objects.filter(row_id=pin["row_id"], organization=org), cap=4
        )
        require(
            [{k: r[k] for k in pin["assignments"][0]} for r in assignments] == pin["assignments"],
            "two_catalog_exact_allocations_changed",
        )
        _rosters(org, objects, pin)
        _donor(org, objects, pin)
        _schedule(org, objects, pin, contract)
        result["cases"].append(
            {
                "row": rows[0],
                "task": task[0],
                "assignments": assignments,
                "bridge": _bridge(org, pin),
                "authority": _authority(org, pin),
                "rivals": _rivals(org, pin, contract),
            }
        )
        corrected.append(rows[0]["subject_id"] == pin["after_subject"])
        all_rows.append(pin["row_id"])
        syllabus_query |= (
            Q(offering_id__in=pin["offerings"])
            | Q(author_id=pin["teacher"], subject_id__in=pin["subjects"], period_id__in=[contract.PERIOD])
            | Q(author_id=pin["teacher"], subject_id__in=pin["subjects"], period_id__isnull=True)
        )
    require(len(set(corrected)) == 1, "two_catalog_partial_relink_state")
    syllabi = bounded(model("syllabus.Syllabus")._base_manager.filter(syllabus_query, organization=org), cap=40)
    academic = graph(
        contract.ORG,
        {
            "registrar.CourseOffering": {str(o.pk) for o in all_offerings},
            "workload.TeachingTaskRow": set(all_rows),
            "syllabus.Syllabus": {r["id"] for r in syllabi},
        },
    )
    require(
        {r["id"] for r in academic["workload.TeachingTaskRow"]} == set(all_rows),
        "two_catalog_unreviewed_workload_graph",
    )
    for pin in contract.CASES:
        require(
            not any(r["offering_id"] == pin["empty"] for r in academic.get("registrar.Lesson", [])),
            "two_catalog_named_journal_not_empty",
        )
    counts = normal(snapshots.offering_counts([o.pk for o in all_offerings]))
    expected = {oid: value for pin in contract.CASES for oid, value in pin["counts"].items()}
    require({r["offering_id"]: r for r in counts} == expected, "two_catalog_source_content_fingerprint_changed")
    result.update(
        corrected=corrected[0],
        protected=protected(academic),
        schema=digest(contract.SCHEMA),
        source=digest([p["source"] for p in contract.CASES]),
    )
    return result
