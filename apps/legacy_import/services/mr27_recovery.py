"""MR27: mənbə ilə bağlı, yalnız bir jurnal üçün atomik və auditli bərpa."""

import datetime as dt
from collections import Counter
from uuid import uuid4

from django.apps import apps
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.public import legacy_accounts
from apps.audit.public import log_action
from apps.registrar.public import enroll_student_in_subject, recompute_absence_hours_many
from core.constants import AuditAction

from .delta.people import student_gender
from .field_contracts import STUDENT_IDENTITY_FIELDS
from .legacy_demographics import legacy_birth_date
from .mr27_ledger import SourceLedger
from .mr27_plan import EXISTING_STUDENT, GROUP, OFFERING, ORG, PARENT, PERIOD, TEACHER, RecoveryError, digest, validate
from .rehearsal_contracts import source_row_hash
from .rehearsal_structure_source import _group, _program_plans, _speciality
from .rehearsal_structure_targets import _program_row_hash

RESOURCE = "legacy_import.mr27_recovery"


def model(name):
    return apps.get_model(name)


def fingerprint(obj):
    # Qorunan hash auditə PII və credential dəyərlərini çıxarmır.
    return digest({f.attname: getattr(obj, f.attname) for f in obj._meta.concrete_fields if f.name != "password"})


def audit(org, actor, batch, manifest, reason="MR-000027 source-backed recovery"):
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=RESOURCE,
        resource_id=batch,
        resource_repr=batch,
        reason=reason,
        new_values=manifest,
    )


class Recovery:
    def __init__(self, org, actor, data, sha, size, *, teacher_assertion=False):
        validate(data)
        if str(org.pk) != ORG or not actor.is_active or not actor.is_superuser:
            raise RecoveryError("actor_or_tenant_scope")
        self.org, self.actor, self.data = org, actor, data
        self.sha, self.size = sha, size
        self.teacher_assertion = teacher_assertion
        self.counts = Counter()
        self.created = []
        self.enrollment_before = []
        self.source_marks = []
        self.batch = f"mr27-{timezone.now():%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"

    def remember(self, obj, mode="retain"):
        self.created.append((obj, mode))
        self.counts[f"created_{obj._meta.model_name}"] += 1
        return obj

    def scope(self):
        self.offering = (
            model("registrar.CourseOffering")
            .objects.select_for_update(of=("self",))
            .select_related("period", "group", "subject")
            .get(pk=OFFERING, organization=self.org)
        )
        o = self.offering
        if (
            str(o.period_id) != PERIOD
            or str(o.group_id) != GROUP
            or o.instructor_id != TEACHER
            or not o.is_active
            or not o.period.is_current
        ):
            raise RecoveryError("offering_scope_changed")
        group = model("organizations.OrgUnit").objects.select_for_update().get(pk=GROUP, organization=self.org)
        legacy = (group.settings or {}).get("legacy", {})
        if legacy.get("id") != 902 or str(group.parent_id) != PARENT:
            raise RecoveryError("group_scope_changed")
        self.group = group
        existing = (
            model("registrar.Enrollment")
            .objects.select_for_update()
            .filter(offering=o, student_id=EXISTING_STUDENT, organization=self.org, status="enrolled")
            .first()
        )
        if existing is None:
            raise RecoveryError("existing_student_enrollment_missing")
        self.enrollments = {10129: existing}
        profile = model("accounts.UserProfile").objects.get(user_id=EXISTING_STUDENT, organization=self.org)
        user = get_user_model().objects.get(pk=EXISTING_STUDENT)
        if user.username != "ibrahim.omerov" or profile.patronymic.casefold() != "azad":
            raise RecoveryError("existing_student_identity_changed")
        previous_undo = (
            model("audit.AuditLog")
            .objects.filter(organization=self.org, resource_type=RESOURCE, reason="MR-000027 compensating undo")
            .exists()
        )
        if previous_undo:
            raise RecoveryError("previous_undo_requires_review")

    def structure(self):
        source = _speciality(103, self.data["speciality"])
        group_source = _group(902, self.data["group"])
        plan = _program_plans([source], [group_source])[0]
        self.ledger = SourceLedger(self.org, self.actor, self.sha, self.size)
        Unit = model("organizations.OrgUnit")
        mapped = self.ledger.mapped("speciality_unit", 103)
        if mapped:
            specialty = Unit.objects.get(pk=mapped, organization=self.org, unit_type="specialty", name=source.name)
        else:
            if Unit.objects.filter(organization=self.org, unit_type="specialty", name__iexact=source.name).exists():
                raise RecoveryError("unmapped_specialty_collision")
            specialty = self.remember(
                Unit.objects.create(
                    organization=self.org,
                    unit_type="specialty",
                    name=source.name,
                    code=source.code,
                    slug="myedu-speciality-103",
                    parent_id=PARENT,
                    settings={"legacy": {"id": 103, "table": "speciality", "source_system": "myedu_mariadb"}},
                    is_active=True,
                )
            )
        self.ledger.bind("speciality_unit", 103, specialty, source.source_row_hash)
        Program = model("registrar.Program")
        mapped = self.ledger.mapped("speciality_program", "103:master")
        if mapped:
            program = Program.objects.get(
                pk=mapped, organization=self.org, specialty_unit=specialty, degree_level="master", name=plan.name
            )
        else:
            if Program.objects.filter(organization=self.org, code=plan.code).exists():
                raise RecoveryError("unmapped_program_collision")
            program = self.remember(
                Program.objects.create(
                    organization=self.org,
                    specialty_unit=specialty,
                    code=plan.code,
                    name=plan.name,
                    degree_level=plan.degree_level,
                    education_form="full_time",
                    ects_total=plan.ects_total,
                    is_active=True,
                )
            )
        if not program.is_active or not specialty.is_active:
            raise RecoveryError("inactive_structure")
        self.ledger.bind("speciality_program", "103:master", program, _program_row_hash(plan, source.source_row_hash))
        self.program = program

    def students(self):
        Profile = model("accounts.UserProfile")
        Record = model("registrar.StudentAcademicRecord")
        Curriculum = model("registrar.Curriculum")
        for row in sorted(self.data["students"], key=lambda r: r["id"]):
            key = str(row["id"])
            mapped = self.ledger.mapped("student", key)
            profiles = list(Profile.objects.select_for_update().filter(institutional_identifier=key))
            if len(profiles) > 1 or (profiles and str(profiles[0].organization_id) != ORG):
                raise RecoveryError("student_identifier_collision")
            if mapped and (not profiles or str(profiles[0].user_id) != mapped):
                raise RecoveryError("student_mapping_collision")
            if profiles:
                user = profiles[0].user
                if (
                    (user.first_name, user.last_name, profiles[0].patronymic)
                    != (row["first_name"], row["last_name"], row["father_name"])
                    or not user.is_active
                    or profiles[0].access_state != "active"
                ):
                    raise RecoveryError("student_identity_conflict")
                if not Record.objects.filter(
                    organization=self.org,
                    student=user,
                    group=self.group,
                    program=self.program,
                    is_active=True,
                    status="enrolled",
                ).exists():
                    raise RecoveryError("student_record_conflict")
            else:
                # Adaş hesabı mənimsəmir; tam ad/ata adı artıq mövcuddursa təxmin etmir.
                if Profile.objects.filter(
                    organization=self.org,
                    user__first_name__iexact=row["first_name"],
                    user__last_name__iexact=row["last_name"],
                    patronymic__iexact=row["father_name"],
                ).exists():
                    raise RecoveryError("unmapped_exact_identity_collision")
                curriculum_exists = Curriculum.objects.filter(
                    organization=self.org, program=self.program, admission_year=2026
                ).exists()
                user = legacy_accounts.create_legacy_student(
                    organization=self.org,
                    actor=self.actor,
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    patronymic=row["father_name"],
                    fin=(row.get("fincode") or None),
                    gender=student_gender(row),
                    birth_date=legacy_birth_date(row.get("birthday") or None),
                    legacy_code=key,
                    group=self.group,
                    program=self.program,
                    admission_year=2026,
                    education_form="full_time",
                    tag=self.batch,
                )
                self.remember(user)
                self.remember(user.profile)
                membership = model("organizations.Membership").objects.get(
                    user=user, organization=self.org, is_active=True
                )
                self.remember(membership)
                record = Record.objects.get(organization=self.org, student=user, program=self.program)
                self.remember(record)
                if not curriculum_exists:
                    self.remember(record.curriculum)
            self.ledger.bind(
                "student",
                key,
                user,
                source_row_hash(contract=STUDENT_IDENTITY_FIELDS, legacy_pk=row["id"], projected_row=row),
            )
            record = Record.objects.get(
                organization=self.org, student=user, program=self.program, group=self.group, is_active=True
            )
            enrollment, created = enroll_student_in_subject(
                record=record, subject=self.offering.subject, period=self.offering.period, kind="mandatory"
            )
            if enrollment is None or enrollment.offering_id != self.offering.pk or enrollment.status != "enrolled":
                raise RecoveryError("enrollment_conflict")
            if created:
                self.remember(enrollment)
            self.enrollments[row["id"]] = enrollment

    def marks(self):
        Lesson, Mark = model("registrar.Lesson"), model("registrar.LessonMark")
        lessons = {}
        for row in self.data["marks"]:
            date = dt.date.fromisoformat(row["date"])
            key = row["date"]
            if key not in lessons:
                found = list(
                    Lesson.objects.select_for_update().filter(organization=self.org, offering=self.offering, date=date)
                )
                if len(found) > 1 or (
                    found and (found[0].kind != row["kind"] or found[0].start_time != dt.time(20, 10))
                ):
                    raise RecoveryError("lesson_conflict")
                if found:
                    lesson = found[0]
                elif key == "2026-10-05":
                    # Legacy mənbədə dərsi keçirən müəllif metadata-sı yoxdur: cari sahibi yazmırıq.
                    lesson = self.remember(
                        Lesson.objects.create(
                            organization=self.org,
                            offering=self.offering,
                            date=date,
                            kind=row["kind"],
                            start_time=dt.time(20, 10),
                            hours=2,
                            is_legacy_synthesised=True,
                        ),
                        "delete",
                    )
                else:
                    raise RecoveryError("unexpected_missing_lesson")
                lessons[key] = lesson
            enrollment = self.enrollments[row["legacy_student_id"]]
            mark = (
                Mark.objects.select_for_update()
                .filter(organization=self.org, lesson=lessons[key], enrollment=enrollment)
                .first()
            )
            if mark:
                if mark.status != row["status"] or mark.score != row["score"]:
                    raise RecoveryError("mark_conflict")
                self.counts["marks_already_present"] += 1
            else:
                mark = self.remember(
                    Mark.objects.create(
                        organization=self.org,
                        lesson=lessons[key],
                        enrollment=enrollment,
                        status=row["status"],
                        score=row["score"],
                        entered_by=None,
                    ),
                    "delete",
                )
            self.source_marks.append(
                {
                    "source_point_id": row["source_point_id"],
                    "source_hash": digest(row),
                    "target_mark": str(mark.pk),
                    "target_lesson": str(lessons[key].pk),
                    "target_enrollment": str(enrollment.pk),
                }
            )
        before = {e.pk: e.absence_hours for e in self.enrollments.values()}
        after = recompute_absence_hours_many(self.enrollments.values())
        self.counts["updated_absence_hours"] += sum(old != after[pk] for pk, old in before.items())
        self.enrollment_before.extend(
            {"id": str(pk), "absence_hours": old, "after": after[pk]} for pk, old in before.items() if old != after[pk]
        )

    def teacher_marks(self):
        """Mənbə dump-dan ayrı müəllim balları; məlum olmayan saat uydurulmur."""
        Lesson, Mark = model("registrar.Lesson"), model("registrar.LessonMark")
        found = list(
            Lesson.objects.select_for_update().filter(organization=self.org, offering=self.offering, date="2026-10-22")
        )
        if len(found) > 1 or (found and found[0].kind != "seminar"):
            raise RecoveryError("teacher_lesson_conflict")
        if found:
            lesson = found[0]
        else:
            lesson = self.remember(
                Lesson.objects.create(
                    organization=self.org,
                    offering=self.offering,
                    date="2026-10-22",
                    kind="seminar",
                    start_time=None,
                    hours=2,
                    created_by=self.actor,
                    instructor_id=TEACHER,
                    off_schedule_reason="MR-000027: 22.10 balları müəllimin 28.10 12:14 cavabından; saat məlum deyil. 2 akademik saat sistemin standart qaydasıdır, mənbə vaxt sübutu deyil.",
                ),
                "delete",
            )
        self.teacher_lesson_evidence = {
            "start_time": lesson.start_time.isoformat() if lesson.start_time else None,
            "time_evidence": "existing lesson time retained" if found else "unknown; no time inferred",
            "hours": lesson.hours,
            "hours_policy": (
                "existing lesson hours retained"
                if found
                else "canonical default 2 academic hours; not source-proven duration"
            ),
        }
        for legacy, score in ((10127, 10), (10128, 10), (10129, 9)):
            enrollment = self.enrollments[legacy]
            mark = (
                Mark.objects.select_for_update()
                .filter(organization=self.org, lesson=lesson, enrollment=enrollment)
                .first()
            )
            if mark:
                if mark.status != "present" or mark.score != score:
                    raise RecoveryError("teacher_mark_conflict")
                self.counts["teacher_marks_already_present"] += 1
            else:
                self.remember(
                    Mark.objects.create(
                        organization=self.org,
                        lesson=lesson,
                        enrollment=enrollment,
                        status="present",
                        score=score,
                        entered_by=self.actor,
                    ),
                    "delete",
                )

    def execute(self):
        self.scope()
        self.structure()
        self.students()
        self.marks()
        if self.teacher_assertion:
            self.teacher_marks()
        self.ledger.finish()
        for obj, _mode in self.created:
            obj.refresh_from_db()
        manifest = {
            "sha256": self.sha,
            "teacher_assertion": (
                {
                    "date": "2026-10-22",
                    "scores": {"10127": 10, "10128": 10, "10129": 9},
                    "grade_evidence": "MR27 teacher reply 2026-10-28 12:14",
                    **self.teacher_lesson_evidence,
                    "kind_policy": "numeric scores: seminar; this offering source lists lecture/seminar, no lab",
                    "entered_by": "actual administrative actor",
                }
                if self.teacher_assertion
                else None
            ),
            "run": str(self.ledger.run.pk),
            "created": [
                {"model": obj._meta.label_lower, "id": str(obj.pk), "mode": mode, "fingerprint": fingerprint(obj)}
                for obj, mode in self.created
            ],
            "absence_before": self.enrollment_before,
            "source_points": [r["source_point_id"] for r in self.data["marks"]],
            "source_marks": self.source_marks,
            "identity_resolution": {
                str(legacy): {"user": e.student_id, "enrollment": str(e.pk)} for legacy, e in self.enrollments.items()
            },
            "counts": dict(self.counts),
        }
        if self.created or self.enrollment_before:
            audit(self.org, self.actor, self.batch, manifest)
        return dict(self.counts), self.batch
