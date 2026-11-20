"""Fixed WCU journal coverage evidence: read-only, encrypted, no student names/scores."""

import hashlib
import hmac
import json
import os
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.registrar.public import journal_access_diagnostics
from core.encrypted_export import encrypt_export
from core.rls import apply_rls_request_context

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
YEAR = "2026/2027"
ASOF = date(2026, 11, 20)
KEY = "f21b002d94fdd65fb346e557e6eb85109f60bda3afa8d8c5a2a14e4b9fc922bf"
MISSING_FIELDS = []


def model(label):
    return apps.get_model(label)


def rows(label, fields, *, manager="objects", **filters):
    cls = model(label)
    known = {f.attname for f in cls._meta.concrete_fields}
    chosen = [f for f in fields.split() if f in known]
    MISSING_FIELDS.extend(f"{label}.{f}" for f in fields.split() if f not in known)
    qs = getattr(cls, manager).filter(organization_id=ORG, **filters).order_by("pk")
    result = list(qs.values(*chosen)[:200001])
    if len(result) > 200000:
        raise ValueError("row_limit")
    return result


def collect():
    secret = os.urandom(32)

    def token(value):
        return hmac.new(secret, str(value).encode(), hashlib.sha256).hexdigest()[:32]

    data = {}
    data["periods"] = rows(
        "organizations.AcademicPeriod",
        "id name academic_year start_date end_date is_active is_current locked_at",
        academic_year=YEAR,
    )
    periods = [r["id"] for r in data["periods"] if r["is_active"] and r["start_date"] <= ASOF <= r["end_date"]]
    if not periods:
        raise ValueError("current_period_missing")
    group_objects = list(model("organizations.OrgUnit").objects.filter(organization_id=ORG))
    keys = {
        "course_year",
        "admission_year",
        "education_form",
        "degree_level",
        "sector",
        "language",
        "parent_group",
        "legacy_id",
        "legacy",
        "language_cohort",
        "level",
    }
    data["groups"] = [
        {
            "id": g.pk,
            "name": g.name,
            "parent_id": g.parent_id,
            "path": g.path,
            "unit_type": g.unit_type,
            "is_active": g.is_active,
            "is_service_unit": getattr(g, "is_service_unit", False),
            "settings": {k: v for k, v in (g.settings or {}).items() if k in keys},
        }
        for g in group_objects
    ]
    data["programs"] = rows("registrar.Program", "id name specialty_unit_id degree_level education_form is_active")
    data["curricula"] = rows("registrar.Curriculum", "id program_id admission_year status version is_active name")
    data["plan_rows"] = rows(
        "registrar.CurriculumSubject",
        "id curriculum_id subject_id semester_number is_elective elective_group required_choices "
        "lecture_hours seminar_hours lab_hours credits teaching_chair_id",
    )
    records = rows(
        "registrar.StudentAcademicRecord",
        "id student_id program_id curriculum_id group_id " "admission_year status is_active",
        is_active=True,
        status="enrolled",
    )
    for r in records:
        r["student_token"] = token(r.pop("student_id"))
    data["records"] = records
    data["choices"] = rows(
        "registrar.GroupElectiveChoice", "id group_id period_id elective_group chosen_subject_id", period_id__in=periods
    )
    data["offerings"] = rows(
        "registrar.CourseOffering",
        "id subject_id period_id group_id instructor_id "
        "lesson_hours is_active course_format starts_on ends_on created_at updated_at",
        period_id__in=periods,
    )
    ids = [r["id"] for r in data["offerings"]]
    data["subjects"] = rows("registrar.Subject", "id name code chair_unit_id is_active")
    data["enrollments"] = rows(
        "registrar.Enrollment",
        "id student_id offering_id status kind source_group_id "
        "superseded_by_id lab_group seminar_group created_at updated_at",
        offering_id__in=ids,
    )
    for r in data["enrollments"]:
        r["student_token"] = token(r.pop("student_id"))
    data["slots"] = rows(
        "registrar.ScheduleSlot",
        "id offering_id weekday start_time end_time week_type kind "
        "instructor_id room is_parked parked_at is_deleted deleted_at created_at updated_at",
        manager="all_objects",
        offering_id__in=ids,
    )
    data["lessons"] = rows(
        "registrar.Lesson",
        "id offering_id date kind hours start_time end_time instructor_id "
        "created_by_id created_at updated_at is_passive is_legacy_synthesised lab_group seminar_group",
        offering_id__in=ids,
        date__lte=ASOF,
    )
    lesson_ids = [r["id"] for r in data["lessons"]]
    marks = model("registrar.LessonMark").objects.filter(organization_id=ORG, lesson_id__in=lesson_ids)
    data["lesson_counts"] = list(
        marks.values("lesson_id")
        .annotate(
            count=Count("pk"),
            scores=Count("pk", filter=Q(score__isnull=False)),
            last_created=Max("created_at"),
            last_updated=Max("updated_at"),
        )
        .order_by("lesson_id")
    )
    data["authors"] = list(
        marks.values("lesson__offering_id", "entered_by_id")
        .annotate(count=Count("pk"), last_created=Max("created_at"), last_updated=Max("updated_at"))
        .order_by("lesson__offering_id", "entered_by_id")
    )
    # Coverage by home-group, without exporting student identity or academic scores.
    homes = defaultdict(set)
    for r in records:
        if r["group_id"]:
            homes[r["student_token"]].add(r["group_id"])
    enrs = {r["id"]: r for r in data["enrollments"]}
    grouped = defaultdict(int)
    for lesson_id, enrollment_id in marks.values_list("lesson_id", "enrollment_id").iterator(chunk_size=10000):
        enr = enrs.get(enrollment_id)
        if enr:
            for home in homes.get(enr["student_token"], ()):
                grouped[(lesson_id, home)] += 1
    data["home_group_marks"] = [
        {"lesson_id": key[0], "group_id": key[1], "count": count} for key, count in grouped.items()
    ]
    data["shares"] = rows(
        "registrar.JournalShare", "id offering_id teacher_id kinds is_active created_at updated_at", offering_id__in=ids
    )
    through = model("registrar.JournalShare").enrollments.through
    data["share_enrollments"] = list(
        through.objects.filter(
            journalshare__organization_id=ORG, journalshare_id__in=[r["id"] for r in data["shares"]]
        ).values("journalshare_id", "enrollment_id")
    )
    data["cohorts"] = rows(
        "registrar.LanguageLevelCohort",
        "id group_id offering_id period_id source_offering_id "
        "name family level lecture_hours seminar_hours lab_hours department_id",
        period_id__in=periods,
    )
    data["placements"] = rows(
        "registrar.LanguageLevelPlacement",
        "id cohort_id student_id home_group_id action " "source_enrollment_id target_enrollment_id created_at",
        cohort_id__in=[r["id"] for r in data["cohorts"]],
    )
    for r in data["placements"]:
        r["student_token"] = token(r.pop("student_id"))
    data["tasks"] = rows(
        "workload.TeachingTask", "id chair_id status submitted_at distributed_at academic_year", academic_year=YEAR
    )
    data["work_rows"] = rows(
        "workload.TeachingTaskRow",
        "id task_id subject_id subject_text period_id row_kind "
        "season lecture_plan lecture_total seminar_plan seminar_total lab_plan lab_total "
        "union_count subgroup_count total_hours",
        task_id__in=[r["id"] for r in data["tasks"]],
    )
    row_ids = [r["id"] for r in data["work_rows"]]
    data["row_groups"] = list(
        model("workload.TeachingTaskRow").objects.filter(organization_id=ORG, id__in=row_ids).values("id", "groups__id")
    )
    data["assignments"] = rows(
        "workload.TeacherAssignment",
        "id row_id teacher_id group_id sub_number activity " "hours created_at updated_at",
        row_id__in=row_ids,
    )
    data["handovers"] = rows(
        "registrar.TeachingHandover",
        "id offering_id from_instructor_id to_instructor_id " "created_at reverted_at",
        offering_id__in=ids,
    )
    data["holidays"] = rows("organizations.AcademicHoliday", "id date kind name", date__year=ASOF.year)
    data["roles"] = rows("organizations.Role", "id name permissions is_active")
    data["memberships"] = rows("organizations.Membership", "id user_id role_id scope_unit_id is_active")
    ids_by_off = defaultdict(set)
    for o in data["offerings"]:
        if o["instructor_id"]:
            ids_by_off[o["id"]].add(o["instructor_id"])
    for r in data["shares"]:
        if r["is_active"]:
            ids_by_off[r["offering_id"]].add(r["teacher_id"])
    for r in data["slots"]:
        if r["instructor_id"]:
            ids_by_off[r["offering_id"]].add(r["instructor_id"])
    by_key = defaultdict(set)
    rg = defaultdict(set)
    for r in data["row_groups"]:
        rg[r["id"]].add(r["groups__id"])
    wr = {r["id"]: r for r in data["work_rows"]}
    for a in data["assignments"]:
        r = wr[a["row_id"]]
        if a["teacher_id"] and a["hours"] > 0:
            for g in ([a["group_id"]] if a.get("group_id") else rg[a["row_id"]]):
                by_key[(r["period_id"], r["subject_id"], g)].add(a["teacher_id"])
    for o in data["offerings"]:
        ids_by_off[o["id"]].update(by_key[(o["period_id"], o["subject_id"], o["group_id"])])
    teacher_ids = set().union(*ids_by_off.values())
    teacher_ids.update(r["entered_by_id"] for r in data["authors"] if r["entered_by_id"])
    recipients = {
        r["id"] for r in data["roles"] if r["name"] in {"chair_head", "lab_assistant", "tutor", "program_coordinator"}
    }
    teacher_ids.update(r["user_id"] for r in data["memberships"] if r["role_id"] in recipients)
    data["users"] = list(
        get_user_model()
        .objects.filter(id__in=teacher_ids)
        .values("id", "username", "first_name", "last_name", "is_active", "last_login")
    )
    data["profiles"] = rows("accounts.UserProfile", "user_id access_state blocked_at", user_id__in=teacher_ids)
    data["diagnostics"] = []
    for offering in (
        model("registrar.CourseOffering")
        .objects.filter(organization_id=ORG, pk__in=ids)
        .select_related("organization", "period", "subject", "group", "instructor")
    ):
        data["diagnostics"].extend(journal_access_diagnostics(offering=offering, teacher_ids=ids_by_off[offering.pk]))
    data["application_units"] = rows(
        "applications.ApplicationUnit",
        "id code name is_active handler_role_names resolve_by requires_recipient requires_scope",
    )
    data["application_kinds"] = rows(
        "applications.ApplicationKind",
        "id code label is_active target_unit_id " "allowed_sender_families route_overrides sla_days",
    )
    return data, group_objects, teacher_ids


def derived(data, group_objects, teacher_ids):
    # Use deployed canonical read-only rules; do not duplicate plan/union semantics.
    from apps.registrar.cohort_plans import PlanIndex, approved_plans, group_cohort_year
    from apps.registrar.joint_journal import selections
    from apps.registrar.journal_edit_windows import earliest_entry_date, late_entry_days
    from apps.registrar.services import group_course_year

    org = model("organizations.Organization").objects.get(pk=ORG)
    plans = approved_plans(org, [r["id"] for r in data["programs"]])
    programs = list(
        model("registrar.Program").objects.filter(organization_id=ORG, is_active=True).select_related("specialty_unit")
    )
    record_programs = defaultdict(set)
    for r in data["records"]:
        record_programs[r["group_id"]].add(r["program_id"])
    data["group_plans"] = []
    for g in group_objects:
        if not g.is_active or g.unit_type != "group":
            continue
        course = group_course_year(g, YEAR)
        for p in programs:
            structural = p.specialty_unit is not None and g.path.startswith(f"{p.specialty_unit.path}/")
            if not structural and p.pk not in record_programs[g.pk]:
                continue
            plan, status, year = PlanIndex(plans.get(p.pk, [])).for_group(g)
            data["group_plans"].append(
                {
                    "group_id": g.pk,
                    "program_id": p.pk,
                    "course_year": course,
                    "admission_year": year or group_cohort_year(g),
                    "plan_id": plan.pk if plan else None,
                    "status": status,
                    "structural_match": structural,
                }
            )
    data["joint_sets"] = []
    for user in get_user_model().objects.filter(pk__in=teacher_ids, is_active=True):
        user.set_active_organization_context(org)
        for item in selections(organization=org, user=user):
            if all(
                o.period.academic_year == YEAR and o.period.start_date <= ASOF <= o.period.end_date
                for o in item.offerings
            ):
                data["joint_sets"].append(
                    {
                        "teacher_id": user.pk,
                        "row_id": item.source_row_id,
                        "kind": item.kind,
                        "offering_ids": list(item.offering_ids),
                    }
                )
    data["entry_policy"] = {"earliest_date": earliest_entry_date(ASOF), "late_days": late_entry_days()}


def main():
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise ValueError("fresh_postgresql_transaction_required")
    started = timezone.now()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
        apply_rls_request_context(user_id=None, org_id=ORG, bypass=False, local=True)
        actor = (
            get_user_model()
            .objects.filter(username=os.environ["COVERAGE_ACTOR"], is_active=True, is_superuser=True)
            .first()
        )
        if actor is None:
            raise ValueError("active_superuser_required")
        apply_rls_request_context(user_id=actor.pk, org_id=ORG, bypass=False, local=True)
        data, groups, teachers = collect()
        derived(data, groups, teachers)
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_read_only")
            if cursor.fetchone()[0] != "on":
                raise ValueError("readonly_required")
    payload = {
        "format": "wcu-journal-coverage/1",
        "organization_id": ORG,
        "academic_year": YEAR,
        "asof": ASOF,
        "cutoff": ASOF - timedelta(days=1),
        "started_at": started,
        "captured_at": timezone.now(),
        "missing_schema_fields": MISSING_FIELDS,
        "data": data,
    }
    path = Path(os.environ["COVERAGE_OUTPUT"])
    envelope = encrypt_export(payload, Path(os.environ["COVERAGE_PUBLIC_KEY"]).read_bytes(), fingerprint=KEY)
    raw = json.dumps(envelope, sort_keys=True).encode()
    if len(raw) > 128 * 1024 * 1024:
        raise ValueError("ciphertext_limit")
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
        out.write(raw)
    print(f"coverage_capture_sha256={hashlib.sha256(raw).hexdigest()} tables={len(data)}")


if __name__ == "__main__":
    main()
