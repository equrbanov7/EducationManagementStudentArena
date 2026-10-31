"""Fixed target identity, existing source/student links and full-field guards."""

import hashlib
import html
import json
import unicodedata
from collections import defaultdict

from django.apps import apps
from django.db import connection

from apps.registrar.public import handover
from apps.workload.public import journal_academic_fingerprint, queryset_database_fingerprint

from .reviewed_content_catalog_bridge import BRIDGES, reviewed_catalog_bridge
from .reviewed_content_contract import ContentError
from .reviewed_content_spec import ORG, TARGETS, YEAR


def model(label):
    return apps.get_model(label)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def normalized(value):
    return unicodedata.normalize("NFKC", html.unescape(str(value))).casefold().strip()


def mappings(entity, legacy_ids, label):
    result = defaultdict(set)
    query = model("legacy_import.LegacyEntityMap").objects.filter(
        organization_id=ORG,
        source_system="myedu_mariadb",
        entity_type=entity,
        legacy_pk__in=list(map(str, legacy_ids)),
        state="migrated",
        target_model_label=label,
    )
    for row in query.values("legacy_pk", "target_pk"):
        result[row["legacy_pk"]].add(row["target_pk"])
    return result


def group_mappings(legacy_ids):
    """Canonical delta identity fallback: exact unique source-derived slug, never a name."""
    result = mappings("group_unit", legacy_ids, "organizations.orgunit")
    wanted = {f"myedu-grp-{gid}": str(gid) for gid in legacy_ids}
    for row in (
        model("organizations.OrgUnit")
        .objects.filter(organization_id=ORG, unit_type="group", slug__in=wanted)
        .values("id", "slug", "settings")
    ):
        source = wanted[row["slug"]]
        embedded = (row["settings"] or {}).get("legacy", {}).get("id")
        if embedded is not None and str(embedded) != source:
            raise ContentError("source_derived_group_slug_metadata_conflict")
        target = str(row["id"])
        if result[source] and result[source] != {target}:
            raise ContentError("source_derived_group_slug_ledger_conflict")
        result[source].add(target)
    return result


class CurrentState:
    def __init__(self, data, *, actor, lock=False):
        if connection.vendor != "postgresql" or not actor.is_active or not actor.is_superuser:
            raise ContentError("active_superadmin_and_postgresql_required")
        self.data = data
        self.selected = {pk: TARGETS[pk] for pk in data["selected_target_ids"]}
        journals = {row["uniqid"]: row for row in data["journals"]}
        workers = {row["id"]: row for row in data["workers"]}
        self.group_maps = group_mappings({gid for row in journals.values() for gid in row["groups_id"]})
        subjects = mappings(
            "lesson_subject", {s["legacy_subject_id"] for s in self.selected.values()}, "registrar.subject"
        )
        old_workers = mappings("worker", {s["legacy_teacher_id"] for s in self.selected.values()}, "auth.user")
        source_students = {row["id"] for row in data["students"]}
        self.student_maps = mappings("student", source_students, "auth.user")
        from .reviewed_content_student_bridge import reviewed_student_bridge

        reviewed_student_bridge(data, self.student_maps, lock=lock)
        teacher_ids = {s["teacher_id"] for s in self.selected.values()}
        teachers = {
            row["id"]: row
            for row in model("auth.User")
            .objects.filter(pk__in=teacher_ids)
            .values("id", "first_name", "last_name", "is_active")
        }
        teacher_profiles = {
            row["user_id"]: row
            for row in model("accounts.UserProfile")
            .objects.filter(organization_id=ORG, user_id__in=teacher_ids)
            .values("user_id", "patronymic")
        }
        offerings = (
            model("registrar.CourseOffering")
            .objects.filter(organization_id=ORG, pk__in=self.selected)
            .select_related("period", "subject", "group")
        )
        if lock:
            offerings = offerings.select_for_update(of=("self",))
        self.selected_offerings = {str(row.pk): row for row in offerings}
        if set(self.selected_offerings) != set(self.selected):
            raise ContentError("reviewed_current_journal_missing")
        self.closed = set(map(str, handover.closed_offering_ids([o.pk for o in self.selected_offerings.values()])))
        eligible = handover.eligible_target_ids(model("organizations.Organization").objects.get(pk=ORG))
        self.families = defaultdict(set)
        for pk, spec in self.selected.items():
            offering = self.selected_offerings[pk]
            period = offering.period
            if (str(offering.subject_id), str(offering.period_id), str(offering.group_id), offering.instructor_id) != (
                spec["subject_id"],
                spec["period_id"],
                spec["group_id"],
                spec["teacher_id"],
            ):
                raise ContentError("reviewed_current_course_identity_changed")
            if (
                not offering.is_active
                or not period.is_active
                or period.academic_year != YEAR
                or period.start_date.year != 2026
                or period.start_date.month != 9
            ):
                raise ContentError("reviewed_current_period_or_activity_changed")
            subject_maps = subjects[str(spec["legacy_subject_id"])]
            subject_matches = subject_maps == {spec["subject_id"]}
            if pk in BRIDGES or not subject_matches:
                subject_matches = reviewed_catalog_bridge(offering, spec, subject_maps)
            if self.group_maps[str(spec["legacy_group_id"])] != {spec["group_id"]} or not subject_matches:
                raise ContentError("source_subject_or_group_identity_bridge_changed")
            source = workers[spec["legacy_teacher_id"]]
            user, profile = teachers.get(spec["teacher_id"]), teacher_profiles.get(spec["teacher_id"])
            if user is None or profile is None or not user["is_active"] or spec["teacher_id"] not in eligible:
                raise ContentError("source_teacher_current_authority_invalid")
            if tuple(map(normalized, (source["first_name"], source["last_name"], source["father_name"]))) != tuple(
                map(normalized, (user["first_name"], user["last_name"], profile["patronymic"]))
            ):
                raise ContentError("source_teacher_full_identity_changed")
            if old_workers[str(spec["legacy_teacher_id"])] and old_workers[str(spec["legacy_teacher_id"])] != {
                str(spec["teacher_id"])
            }:
                raise ContentError("source_worker_ledger_conflict")
            journal = journals[spec["journal_uniqid"]]
            family_groups = set().union(*(self.group_maps[str(g)] for g in journal["groups_id"]))
            family = model("registrar.CourseOffering").objects.filter(
                organization_id=ORG,
                subject_id=spec["subject_id"],
                period_id=spec["period_id"],
                group_id__in=family_groups,
            )
            self.families[spec["journal_uniqid"]].update(str(v) for v in family.values_list("pk", flat=True))
        self.read_ids = set().union(*self.families.values())
        self.offerings = list(
            model("registrar.CourseOffering").objects.filter(organization_id=ORG, pk__in=self.read_ids)
        )
        lessons = model("registrar.Lesson").objects.filter(organization_id=ORG, offering_id__in=self.read_ids)
        enrollments = model("registrar.Enrollment").objects.filter(organization_id=ORG, offering_id__in=self.read_ids)
        if lock:
            lessons, enrollments = lessons.select_for_update(), enrollments.select_for_update()
        self.lessons = defaultdict(list)
        for row in lessons:
            self.lessons[(str(row.offering_id), row.date, row.start_time)].append(row)
        self.enrollments = list(enrollments)
        self.by_user = defaultdict(list)
        for row in self.enrollments:
            self.by_user[row.student_id].append(row)
        user_ids = {int(uid) for values in self.student_maps.values() for uid in values if uid.isdigit()}
        self.tenant_students = set(
            model("accounts.UserProfile")
            .objects.filter(organization_id=ORG, user_id__in=user_ids)
            .values_list("user_id", flat=True)
        )
        self.active_groups = defaultdict(set)
        for row in (
            model("registrar.StudentAcademicRecord")
            .objects.filter(organization_id=ORG, student_id__in=user_ids, is_active=True, status="enrolled")
            .values("student_id", "group_id")
        ):
            self.active_groups[row["student_id"]].add(str(row["group_id"]))
        self.group_of_offering = {str(row.pk): str(row.group_id) for row in self.offerings}
        self.marks = defaultdict(list)
        marks = model("registrar.LessonMark").objects.filter(organization_id=ORG, lesson__offering_id__in=self.read_ids)
        if lock:
            marks = marks.select_for_update(of=("self",))
        for row in marks.select_related("lesson", "enrollment"):
            key = (str(row.lesson.offering_id), row.lesson.date, row.lesson.start_time, row.enrollment.student_id)
            self.marks[key].append(row)

    def fingerprint(self):
        teacher_ids = {s["teacher_id"] for s in self.selected.values()}
        relevant_users = teacher_ids | {int(pk) for ids in self.student_maps.values() for pk in ids}
        result = {
            "academic": journal_academic_fingerprint(organization_id=ORG, offerings=self.offerings),
            "groups": queryset_database_fingerprint(
                model("organizations.OrgUnit").objects.filter(
                    organization_id=ORG, pk__in=self.group_of_offering.values()
                )
            ),
            "periods": queryset_database_fingerprint(
                model("organizations.AcademicPeriod").objects.filter(
                    organization_id=ORG, pk__in={s["period_id"] for s in self.selected.values()}
                )
            ),
            "source_identity_maps": {
                "groups": {key: sorted(value) for key, value in self.group_maps.items()},
                "students": {key: sorted(value) for key, value in self.student_maps.items()},
            },
            "teachers": list(
                model("auth.User")
                .objects.filter(pk__in=teacher_ids)
                .order_by("pk")
                .values("id", "first_name", "last_name", "is_active")
            ),
        }
        for label in ("organizations.Membership", "accounts.UserProfile", "registrar.StudentAcademicRecord"):
            result[label] = queryset_database_fingerprint(
                model(label).objects.filter(
                    organization_id=ORG,
                    **{
                        (
                            "student_id__in" if label == "registrar.StudentAcademicRecord" else "user_id__in"
                        ): relevant_users
                    },
                )
            )
        return result


def protected(state, *, created_lessons=(), created_marks=(), touched=()):
    """Every old lesson/cell stays identical; only exact derived absence caches may change."""
    result = {
        "academic": journal_academic_fingerprint(
            organization_id=ORG, offerings=state.offerings, exclude=("lesson", "mark", "enrollment")
        )
    }
    for label, excluded in (
        ("registrar.Lesson", created_lessons),
        ("registrar.LessonMark", created_marks),
        ("registrar.Enrollment", touched),
    ):
        result[label] = queryset_database_fingerprint(
            model(label).objects.filter(organization_id=ORG).exclude(pk__in=excluded)
        )
    for label in (
        "organizations.Membership",
        "organizations.Role",
        "accounts.UserProfile",
        "registrar.StudentAcademicRecord",
    ):
        result[label] = queryset_database_fingerprint(model(label).objects.filter(organization_id=ORG))
    if touched:
        fields = [f.name for f in model("registrar.Enrollment")._meta.concrete_fields if f.name != "absence_hours"]
        result["touched_enrollment_identity"] = queryset_database_fingerprint(
            model("registrar.Enrollment").objects.filter(organization_id=ORG, pk__in=touched).values(*fields)
        )
    return result
