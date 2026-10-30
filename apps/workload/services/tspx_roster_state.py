"""Live identity/family guards and full academic preservation for the fixed roster."""

from django.db.models import Q

from apps.registrar.public import validate_active_student_member

from .repair_fingerprints import academic_database_fingerprint, academic_queries
from .sbio235_state import RepairError, digest, model, records
from .tspx_roster_plan import ORG, PARENT, PERIOD, TARGETS

GROUP_IDS = (PARENT, *TARGETS.values())


def offerings(plan):
    enrolled = model("registrar.Enrollment").objects.filter(organization_id=ORG, student_id__in=plan.user_ids)
    return (
        model("registrar.CourseOffering")
        .objects.filter(organization_id=ORG)
        .filter(Q(group_id__in=GROUP_IDS, period_id=PERIOD) | Q(pk__in=enrolled.values("offering_id")))
    )


def capture(plan, *, lock=False):
    journals = list(offerings(plan).order_by("pk"))
    if lock:
        for qs in academic_queries(organization_id=ORG, offerings=journals).values():
            list(qs.select_for_update().order_by("pk").values_list("pk", flat=True))
    source_ids = [str(p["legacy_student_id"]) for p in plan.people]
    rows = model("workload.TeachingTaskRow").objects.filter(organization_id=ORG, groups__pk__in=GROUP_IDS)
    rows = model("workload.TeachingTaskRow").objects.filter(pk__in=rows.values("pk"))
    queries = {
        "groups": model("organizations.OrgUnit").objects.filter(organization_id=ORG, pk__in=GROUP_IDS),
        "period": model("organizations.AcademicPeriod").objects.filter(organization_id=ORG, pk=PERIOD),
        "records": model("registrar.StudentAcademicRecord")
        .objects.filter(organization_id=ORG)
        .filter(Q(pk__in=plan.record_ids) | Q(group_id__in=GROUP_IDS)),
        "memberships": model("organizations.Membership").objects.filter(organization_id=ORG, user_id__in=plan.user_ids),
        "roles": model("organizations.Role").objects.filter(organization_id=ORG),
        "maps": model("legacy_import.LegacyEntityMap").objects.filter(
            organization_id=ORG,
            source_system="myedu_mariadb",
            entity_type__in=("student", "student_record"),
            legacy_pk__in=source_ids,
        ),
        "workload": rows,
        "assignments": model("workload.TeacherAssignment").objects.filter(row_id__in=rows.values("pk")),
        "enrollments": model("registrar.Enrollment").objects.filter(organization_id=ORG, student_id__in=plan.user_ids),
        "offerings": model("registrar.CourseOffering").objects.filter(pk__in=[o.pk for o in journals]),
    }
    result = {name: records(qs, lock=lock) for name, qs in queries.items()}
    user_query = model("auth.User").objects.filter(pk__in=plan.user_ids)
    profile_query = model("accounts.UserProfile").objects.filter(organization_id=ORG, user_id__in=plan.user_ids)
    if lock:
        user_query, profile_query = user_query.select_for_update(), profile_query.select_for_update()
    result["users"] = list(user_query.order_by("pk").values("id", "username", "first_name", "last_name", "is_active"))
    result["profiles"] = list(profile_query.order_by("pk").values("user_id", "patronymic"))
    result["academic"] = academic_database_fingerprint(
        organization_id=ORG, offerings=journals, exclude=("enrollment", "offering")
    )
    return result


def validate(plan, organization):
    groups = {
        str(g.pk): g
        for g in model("organizations.OrgUnit").objects.filter(
            organization=organization, pk__in=GROUP_IDS, is_active=True, unit_type="group"
        )
    }
    if len(groups) != 3:
        raise RepairError("tspx_active_family_missing")
    parent = groups[PARENT]
    for legacy, gid in TARGETS.items():
        child = groups[gid]
        if (
            str((child.settings or {}).get("parent_group")) != PARENT
            or child.parent_id != parent.parent_id
            or "".join(child.name.lower().split()) != f"135tspx-{1 if legacy == 927 else 2}"
            or any(
                (child.settings or {}).get(k) != (parent.settings or {}).get(k)
                for k in ("sector", "education_form", "degree_level")
            )
        ):
            raise RepairError("tspx_registered_parent_or_sector_changed")
    period = model("organizations.AcademicPeriod").objects.get(pk=PERIOD, organization=organization)
    if not period.is_current or not period.is_active or period.academic_year != "2026/2027":
        raise RepairError("tspx_active_current_period_required")
    active = model("registrar.StudentAcademicRecord").objects.filter(
        organization=organization, group_id__in=GROUP_IDS, status="enrolled"
    )
    if set(active.values_list("student_id", flat=True)) != plan.user_ids or active.count() != 50:
        raise RepairError("tspx_live_family_student_set_changed")
    people = {}
    for item in plan.people:
        record = (
            model("registrar.StudentAcademicRecord")
            .objects.select_related("student")
            .get(pk=item["expected_record_id"], organization=organization, student_id=item["target_user_id"])
        )
        profile = model("accounts.UserProfile").objects.get(organization=organization, user=record.student)

        def clean(value):
            return " ".join(str(value or "").split()).casefold()

        actual = (record.student.first_name, record.student.last_name, profile.patronymic)
        wanted = tuple(item["source_identity"][key] for key in ("first_name", "last_name", "patronymic"))
        target = item.get("target_group_id", PARENT)
        if (
            not record.student.is_active
            or record.status != "enrolled"
            or str(record.group_id) not in {PARENT, target}
            or record.admission_year != item["keep_admission_year"]
            or str(record.program_id) != item["keep_program_id"]
            or str(record.curriculum_id) != item["keep_curriculum_id"]
            or tuple(map(clean, actual)) != tuple(map(clean, wanted))
        ):
            raise RepairError("tspx_live_student_identity_or_record_changed")
        validate_active_student_member(organization=organization, user=record.student)
        for kind, label, pk in (
            ("student", "auth.user", record.student_id),
            ("student_record", "registrar.studentacademicrecord", record.pk),
        ):
            maps = model("legacy_import.LegacyEntityMap").objects.filter(
                organization=organization,
                source_system=item["source_system"],
                entity_type=kind,
                legacy_pk=str(item["legacy_student_id"]),
                state="migrated",
                target_model_label=label,
                target_pk=str(pk),
            )
            if kind == "student":
                maps = maps.filter(source_row_hash=item["ledger_source_row_hash"])
            if maps.count() != 1:
                raise RepairError("tspx_current_immutable_mapping_mismatch")
        people[str(record.pk)] = record
    return groups, period, people


def _same(old, new, excluded=()):
    return {k: v for k, v in old.items() if k not in excluded} == {k: v for k, v in new.items() if k not in excluded}


def preserved(before, after, moved, changed_enrollments=()):
    old_offerings = model("registrar.CourseOffering").objects.filter(
        organization_id=ORG, pk__in=[o["id"] for o in before["offerings"]]
    )
    if before["academic"] != academic_database_fingerprint(
        organization_id=ORG, offerings=list(old_offerings), exclude=("enrollment", "offering")
    ):
        raise RepairError("tspx_existing_academic_content_changed")
    for key in ("groups", "period", "users", "profiles", "maps", "memberships", "roles", "workload", "assignments"):
        if before[key] != after[key]:
            raise RepairError("tspx_identity_access_or_workload_changed")
    old = {r["id"]: r for r in before["records"]}
    new = {r["id"]: r for r in after["records"]}
    if old.keys() != new.keys():
        raise RepairError("tspx_record_created_or_removed")
    for pk, row in old.items():
        allowed = ("group_id", "updated_at") if pk in moved else ()
        if not _same(row, new[pk], allowed):
            raise RepairError("tspx_unrelated_student_record_changed")
    new_enrollments = {e["id"]: e for e in after["enrollments"]}
    for row in before["enrollments"]:
        excluded = ("status", "superseded_by_id", "updated_at") if row["id"] in changed_enrollments else ()
        if row["id"] not in new_enrollments or not _same(row, new_enrollments[row["id"]], excluded):
            raise RepairError("tspx_enrollment_identity_or_content_changed")
    new_offerings = {o["id"]: o for o in after["offerings"]}
    for old_offer in before["offerings"]:
        current = new_offerings.get(old_offer["id"])
        if current is None or not _same(
            old_offer, current, ("instructor_id", "lesson_hours", "course_id", "updated_at")
        ):
            raise RepairError("tspx_existing_journal_identity_changed")
        for key in ("instructor_id", "lesson_hours", "course_id"):
            if old_offer[key] != current[key] and (
                old_offer[key]
                or old_offer["group_id"] not in TARGETS.values()
                or not any(
                    o["group_id"] == PARENT
                    and o["subject_id"] == old_offer["subject_id"]
                    and o["period_id"] == old_offer["period_id"]
                    and o[key] == current[key]
                    for o in before["offerings"]
                )
            ):
                raise RepairError("tspx_existing_teaching_configuration_changed")


def baseline(snapshot):
    return digest(snapshot)
