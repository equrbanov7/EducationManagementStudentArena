"""``restore_intensive_results_20261112`` — köhnə intensiv jurnalında keçilmiş fənnin rəsmi nəticəsi (MR-000288)."""

import datetime as dt
import json
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import intensive_results_restore_2026_11_12 as restore
from apps.registrar.management.commands.restore_intensive_results_20261112 import failure_code
from apps.registrar.models import (
    AssessmentComponent,
    ComponentScore,
    CourseOffering,
    Enrollment,
    FinalGrade,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType
from core.rls import bypass_rls

User = get_user_model()
D = Decimal


class _IntensiveBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_superuser("ir_actor", "ir@example.test", "x")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="IR Univ",
                slug="ir-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.actor,
                status="active",
                is_active=True,
            )
            chair = OrgUnit.objects.create(organization=cls.org, name="Tərcümə", slug="ir-chair", unit_type="chair")
            cls.autumn = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                academic_year="2025/2026",
                period_type=AcademicPeriodType.SEMESTER,
                start_date=dt.date(2025, 9, 15),
                end_date=dt.date(2026, 1, 31),
            )
            cls.spring = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Yaz",
                academic_year="2025/2026",
                period_type=AcademicPeriodType.SEMESTER,
                start_date=dt.date(2026, 2, 1),
                end_date=dt.date(2026, 6, 30),
            )
            cls.subject = Subject.objects.create(
                organization=cls.org, code="QKU-567", name="İqtisadi tərcümə", chair_unit=chair
            )
            cls.regular = CourseOffering.objects.create(organization=cls.org, subject=cls.subject, period=cls.autumn)
            cls.intensive = CourseOffering.objects.create(organization=cls.org, subject=cls.subject, period=cls.spring)
            AssessmentComponent.objects.create(
                organization=cls.org,
                offering=cls.intensive,
                name=restore.ARCHIVE_NAME,
                kind="generic",
                max_score=50,
                order=0,
            )
            for i in (1, 2, 3):
                AssessmentComponent.objects.create(
                    organization=cls.org,
                    offering=cls.intensive,
                    name=f"Kollokvium {i}",
                    kind="kollokvium",
                    max_score=10,
                    order=i,
                )
            role = cls.org.roles.get(name="student")
            cls.users = {}
            for sid in (523, 994, 700):
                user = User.objects.create_user(f"ir{sid}", f"ir{sid}@example.test", "x", first_name="T")
                Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
                cls.users[sid] = user
            # Əvvəlki cəhd (Payız): 30 + 8 = 38 F.
            first = Enrollment.objects.create(organization=cls.org, student=cls.users[523], offering=cls.regular)
            FinalGrade.objects.create(organization=cls.org, enrollment=first, exam_score=D(8))
            # İntensivə artıq köçmüş bacı tələbə.
            Enrollment.objects.create(organization=cls.org, student=cls.users[994], offering=cls.intensive)

    def _plan(self, items):
        path = Path(tempfile.mkdtemp()) / "plan.json"
        plan = {
            "format": restore.FORMAT,
            "periods": [{"id": 12, "name": "2025/2026 Yaz", "type": "spring"}],
            "subjects": [{"id": 567, "name": "İqtisadi tərcümə"}],
            "items": items,
        }
        path.write_text(json.dumps(plan, ensure_ascii=False))
        return str(path)

    def _item(self, sid=523, **extra):
        item = {
            "journals": ["KgJkD1aLxB"],
            "semestr": 12,
            "lesson_id": 567,
            "student": sid,
            "siblings": [994, 510],
            "entry": "48",
            "exam": "34",
            "resit": None,
            "total": "82",
            "attendance_fail": False,
            "export": 49714,
            "k": {"k1": "9", "k2": "9", "k3": "10"},
        }
        item.update(extra)
        return item

    def _ledger(self, entity_type, keys=None):
        if entity_type == "student":
            found = {str(sid): str(user.pk) for sid, user in self.users.items()}
        else:
            found = {}
        if keys is not None:
            wanted = {str(key) for key in keys}
            return {key: value for key, value in found.items() if key in wanted}
        return found

    def _call(self, items=None, *, apply=False, undo="", student="", **extra):
        out = StringIO()
        options = {"org": self.org.slug, "actor": self.actor.username, "apply": apply, "stdout": out, **extra}
        if undo:
            options.update(undo=True, batch=undo)
        else:
            options["file"] = self._plan(items or [self._item()])
        if student:
            options["student"] = student
        with mock.patch.object(restore.Ledger, "_rows", lambda _self, kind, keys=None: self._ledger(kind, keys)):
            call_command("restore_intensive_results_20261112", **options)
        counts = {}
        for line in out.getvalue().splitlines():
            for part in line.split()[1:]:
                key, _sep, value = part.partition("=")
                counts[key] = value
        return counts

    def _new_enrollment(self):
        with bypass_rls():
            return Enrollment.objects.filter(offering=self.intensive, student=self.users[523]).first()


class IntensiveResultsRestoreTests(_IntensiveBase):
    def test_dry_run_counts_without_writing(self):
        counts = self._call()
        self.assertEqual(counts["mode"], "dry_run")
        self.assertEqual(counts["restored"], "1")
        self.assertEqual(counts["offering_by_siblings"], "1")
        self.assertIsNone(self._new_enrollment())

    def test_apply_writes_official_result_once_and_undo_removes_it(self):
        from apps.registrar import finals

        counts = self._call(apply=True)
        self.assertEqual((counts["restored"], counts["restored_retake"]), ("1", "1"))
        enrollment = self._new_enrollment()
        self.assertIsNotNone(enrollment)
        with bypass_rls():
            result = finals.compute_final_result(enrollment=enrollment, organization=self.org)
            self.assertEqual((result["total"], result["passed"]), (D(82), True))
            self.assertEqual(enrollment.kind, "retake")
            self.assertEqual(
                sorted(
                    ComponentScore.objects.filter(enrollment=enrollment, component__kind="kollokvium").values_list(
                        "score", flat=True
                    )
                ),
                [D(9), D(9), D(10)],
            )
            self.assertTrue(
                AuditLog.objects.filter(resource_type=restore.RESOURCE, resource_id=counts["batch"]).exists()
            )
        again = self._call(apply=True)
        self.assertEqual(again.get("restored", "0"), "0")
        self.assertEqual(again["skip_existing"], "1")
        undone = self._call(apply=True, undo=counts["batch"])
        self.assertEqual(undone["undo_enrollment_deleted"], "1")
        self.assertIsNone(self._new_enrollment())

    def test_failed_official_result_and_already_passed_subject_are_skipped(self):
        counts = self._call([self._item(entry="30", exam="10", total="40")], apply=True)
        self.assertEqual(counts["skip_official_not_passed"], "1")
        self.assertIsNone(self._new_enrollment())
        with bypass_rls():
            first = Enrollment.objects.get(offering=self.regular, student=self.users[523])
            FinalGrade.objects.filter(enrollment=first).update(exam_score=D(40))
            ComponentScore.objects.create(
                organization=self.org,
                component=AssessmentComponent.objects.create(
                    organization=self.org, offering=self.regular, name="Arxiv", kind="generic", max_score=50, order=0
                ),
                enrollment=first,
                score=D(30),
            )
        counts = self._call(apply=True)
        self.assertEqual(counts["skip_already_passed"], "1")

    def test_unresolved_rows_are_counted(self):
        items = [self._item(sid=9999), self._item(sid=700, siblings=[])]
        counts = self._call(items)
        self.assertEqual((counts["skip_student_unresolved"], counts["skip_offering_no_sibling"]), ("1", "1"))

    def test_plan_and_batch_are_validated(self):
        with self.assertRaisesMessage(CommandError, "intensive_results_item_without_total"):
            self._call([self._item(total=None)])
        with self.assertRaisesMessage(CommandError, "intensive_results_batch_invalid"):
            self._call(undo="nope")
        self.assertEqual(failure_code(ValueError("Boom X")), "intensive_results_failed_valueerror_boom_x")


class IntensiveArchiveOfferingTests(_IntensiveBase):
    """``--create-missing-offerings``: uyğun açılış yoxdursa köhnə jurnal ailəsinin bağlı intensiv arxiv açılışı."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.teacher = User.objects.create_user("ir_teacher", "ir_teacher@example.test", "x")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.missing = Subject.objects.create(
                organization=cls.org, code="QKU-777", name="Ardıcıl tərcümə və qeydgötürmə texnikası"
            )

    def _plan(self, items):
        path = super()._plan(items)
        data = json.loads(Path(path).read_text())
        data["subjects"].append({"id": 777, "name": "Ardıcıl tərcümə və qeydgötürmə texnikası"})
        Path(path).write_text(json.dumps(data, ensure_ascii=False))
        return path

    def _ledger(self, entity_type, keys=None):
        if entity_type == "worker":
            return {"23": str(self.teacher.pk)}
        return super()._ledger(entity_type, keys)

    def _missing_item(self, sid=700, **extra):
        item = self._item(sid=sid, journals=["CnbUmerDlP"], lesson_id=777, siblings=[], teacher=23)
        item.update(extra)
        return item

    def _create(self, items, **kwargs):
        return self._call(items, create_missing_offerings=True, **kwargs)

    def _archive(self):
        with bypass_rls():
            return CourseOffering.objects.filter(subject=self.missing).first()

    def test_without_flag_row_is_skipped(self):
        counts = self._call([self._missing_item()], apply=True)
        self.assertEqual(counts["skip_offering_no_sibling"], "1")
        self.assertIsNone(self._archive())

    def test_creates_closed_intensive_archive_and_undo_removes_it(self):
        from apps.registrar import finals
        from apps.registrar.models import AssessmentScheme

        items = [self._missing_item(), self._missing_item(sid=994, total="70", exam="22")]
        counts = self._create(items, apply=True)
        self.assertEqual(counts["offerings_created"], "1")
        self.assertEqual(counts["offering_by_archive_new"], "1")
        self.assertEqual(counts["offering_by_archive_existing"], "1")
        self.assertEqual(counts["restored"], "2")
        offering = self._archive()
        with bypass_rls():
            self.assertEqual(
                (offering.course_format, offering.group_id, offering.instructor_id, offering.period_id),
                ("intensive", None, self.teacher.pk, self.spring.pk),
            )
            self.assertEqual((offering.starts_on, offering.ends_on), (self.spring.start_date, self.spring.end_date))
            scheme = AssessmentScheme.objects.get(offering=offering)
            self.assertEqual((scheme.approval_status, scheme.is_published), ("approved", True))
            rows = Enrollment.objects.filter(offering=offering)
            self.assertEqual(rows.count(), 2)
            mine = rows.select_related("offering", "student").get(student=self.users[700])
            result = finals.compute_final_result(enrollment=mine, organization=self.org)
            self.assertEqual((result["total"], result["passed"]), (D(82), True))
        again = self._create([self._missing_item()], apply=True)
        self.assertEqual((again.get("offerings_created", "0"), again["skip_existing"]), ("0", "1"))
        undone = self._call(apply=True, undo=counts["batch"])
        self.assertEqual((undone["undo_enrollment_deleted"], undone["undo_offering_deleted"]), ("2", "1"))
        self.assertIsNone(self._archive())

    def test_dry_run_and_failed_row_leave_no_archive(self):
        counts = self._create([self._missing_item()])
        self.assertEqual((counts["mode"], counts["offerings_created"]), ("dry_run", "1"))
        self.assertIsNone(self._archive())
        counts = self._create([self._missing_item(entry="30", exam="10", total="40")], apply=True)
        self.assertEqual(counts["skip_official_not_passed"], "1")
        self.assertEqual(counts.get("offerings_created", "0"), "0")
        self.assertIsNone(self._archive())

    def test_current_period_and_ambiguous_rows_are_never_created(self):
        with bypass_rls():
            AcademicPeriod.objects.filter(pk=self.spring.pk).update(is_current=True)
        counts = self._create([self._missing_item()], apply=True)
        self.assertEqual(counts["skip_offering_period_not_past"], "1")
        self.assertIsNone(self._archive())
        with bypass_rls():
            AcademicPeriod.objects.filter(pk=self.spring.pk).update(is_current=False)
            twin = CourseOffering.objects.create(
                organization=self.org,
                subject=self.subject,
                period=self.spring,
                group=OrgUnit.objects.create(organization=self.org, name="G", slug="ir-g", unit_type="group"),
            )
            Enrollment.objects.create(organization=self.org, student=self.users[994], offering=twin)
        counts = self._create([self._item(siblings=[994])], apply=True)
        self.assertEqual(counts["skip_offering_ambiguous"], "1")
        self.assertEqual(counts.get("offerings_created", "0"), "0")
