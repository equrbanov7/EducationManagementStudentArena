"""MR27 real modellərlə: source-only əhatə, dry-run, konflikt, kompensasiya."""

import datetime as dt
import hashlib
import io
import json
import tempfile

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import UserProfile
from apps.legacy_import.models import LegacyEntityMap
from apps.legacy_import.services.field_contracts import (
    GROUP_STRUCTURE_FIELDS,
    SPECIALITY_STRUCTURE_FIELDS,
    STUDENT_IDENTITY_FIELDS,
)
from apps.legacy_import.services.mr27_plan import DATES, GROUP, OFFERING, ORG, PARENT, PERIOD, POINTS
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Program, Subject
from core.rls import bypass_rls


def plan():
    speciality = {key: "" for key in SPECIALITY_STRUCTURE_FIELDS.allowed_fields}
    speciality.update(id=103, name="Bioekelogiya", speciality_code="005566", department_id=35)
    group = {key: "" for key in GROUP_STRUCTURE_FIELDS.allowed_fields}
    group.update(
        id=902,
        name="510/6BİEO",
        speciality_id=103,
        department_id=35,
        sector="az",
        eyani_qiyabi="Əyani",
        bak_or_mag="mag",
        start_year=2026,
        curricula_id=168,
        kollec_or_uni="University",
    )
    students = []
    for pk, first, last, father in (
        (10127, "Fatimə", "Əliyeva", "Allahverdi"),
        (10128, "Rəqsanə", "Cəfərli", "Ruslan"),
    ):
        row = {key: "" for key in STUDENT_IDENTITY_FIELDS.allowed_fields}
        row.update(
            id=pk,
            first_name=first,
            last_name=last,
            father_name=father,
            group_id=902,
            speciality_id=0,
            join_date=2026,
            sex=0,
            status=0,
        )
        students.append(row)
    marks = []
    for student, ids in POINTS.items():
        for (date, kind), pk in zip(DATES.items(), ids):
            marks.append(
                dict(
                    source_point_id=pk,
                    legacy_student_id=student,
                    date=date,
                    kind=kind,
                    time="20:10:00",
                    status="absent" if student == 10129 and date == "2026-10-05" else "present",
                    score=9 if student != 10129 and date == "2026-10-08" else None,
                )
            )
    return dict(format="mr27-recovery/1", speciality=speciality, group=group, students=students, marks=marks)


class MR27RecoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.actor = User.objects.create_superuser("mr27_actor", "actor@example.test", "test")
        with bypass_rls():
            cls.org = Organization.objects.create(
                id=ORG,
                name="MR27 QKU",
                slug="qku",
                org_type="university",
                owner=cls.actor,
                status="active",
                is_active=True,
            )
            parent = OrgUnit.objects.create(
                id=PARENT, organization=cls.org, name="Magistratura", slug="masters", unit_type="faculty"
            )
            cls.group = OrgUnit.objects.create(
                id=GROUP,
                organization=cls.org,
                name="510/6BİEO",
                slug="myedu-grp-902",
                unit_type="group",
                parent=parent,
                settings={"legacy": {"id": 902}, "admission_year": 2026},
            )
            period = AcademicPeriod.objects.create(
                id=PERIOD,
                organization=cls.org,
                name="Payız",
                academic_year="2026/2027",
                period_type="semester",
                start_date=dt.date(2026, 9, 1),
                end_date=dt.date(2027, 1, 31),
                is_current=True,
            )
            teacher = User.objects.create_user(id=8415, username="ramiz.qulamov")
            Membership.objects.create(user=teacher, organization=cls.org, role=cls.org.roles.get(name="teacher"))
            cls.existing = User.objects.create_user(
                id=2510, username="ibrahim.omerov", first_name="Ibrahim", last_name="Ömərov"
            )
            UserProfile.objects.filter(user=cls.existing).update(organization=cls.org, patronymic="Azad")
            Membership.objects.create(user=cls.existing, organization=cls.org, role=cls.org.roles.get(name="student"))
            subject = Subject.objects.create(
                organization=cls.org, code="QKU-MR27", name="Xəzər dənizinin bioresursları"
            )
            cls.offering = CourseOffering.objects.create(
                id=OFFERING, organization=cls.org, period=period, group=cls.group, subject=subject, instructor=teacher
            )
            enrollment = Enrollment.objects.create(organization=cls.org, student=cls.existing, offering=cls.offering)
            for date, kind in DATES.items():
                if date == "2026-10-05":
                    continue
                lesson = Lesson.objects.create(
                    organization=cls.org,
                    offering=cls.offering,
                    date=date,
                    kind=kind,
                    start_time=dt.time(20, 10),
                    hours=2,
                )
                LessonMark.objects.create(organization=cls.org, lesson=lesson, enrollment=enrollment, status="present")

    def run_command(self, *, apply=True, data=None, undo="", sha_bad=False, assertion=False):
        out = io.StringIO()
        with tempfile.NamedTemporaryFile(suffix=".json") as f:
            raw = json.dumps(data or plan(), ensure_ascii=False).encode()
            f.write(raw)
            f.flush()
            kwargs = dict(org="qku", actor="mr27_actor", apply=apply, stdout=out, include_teacher_assertion=assertion)
            if undo:
                kwargs["undo"] = undo
            else:
                kwargs.update(file=f.name, sha256="0" * 64 if sha_bad else hashlib.sha256(raw).hexdigest())
            call_command("recover_mr27_journal", **kwargs)
        return out.getvalue()

    @override_settings(RLS_TRANSACTION_SCOPED=True)
    def test_dry_run_rolls_back_then_apply_restores_three_and_repeat_is_empty(self):
        out = self.run_command(apply=False)
        self.assertIn("created_lessonmark=15", out)
        self.assertEqual(Enrollment.objects.filter(offering=self.offering).count(), 1)
        self.assertFalse(LegacyEntityMap.objects.filter(legacy_pk="10127").exists())
        out = self.run_command()
        self.assertIn("created_user=2", out)
        self.assertEqual(Enrollment.objects.filter(offering=self.offering, status="enrolled").count(), 3)
        self.assertEqual(LessonMark.objects.filter(lesson__offering=self.offering).count(), 21)
        self.assertEqual(Lesson.objects.filter(offering=self.offering).count(), 7)
        self.assertFalse(Lesson.objects.filter(offering=self.offering, date="2026-10-22").exists())
        for user in get_user_model().objects.filter(profile__institutional_identifier__in=["10127", "10128"]):
            self.assertFalse(user.has_usable_password())
            self.assertTrue(user.email.endswith("@placeholder.invalid"))
        self.assertEqual(Program.objects.get().degree_level, "master")
        self.assertNotIn("created_", self.run_command())

    def test_conflicting_live_mark_rolls_back_every_new_identity_and_structure(self):
        LessonMark.objects.filter(lesson__offering=self.offering, lesson__date="2026-10-08").update(score=7)
        with self.assertRaisesMessage(Exception, "mark_conflict"):
            self.run_command()
        self.assertFalse(Program.objects.exists())
        self.assertEqual(Enrollment.objects.filter(offering=self.offering).count(), 1)

    def test_source_or_checksum_scope_cannot_expand(self):
        with self.assertRaisesMessage(Exception, "plan_digest_mismatch"):
            self.run_command(sha_bad=True)
        altered = plan()
        altered["marks"][0]["date"] = "2026-10-22"
        with self.assertRaisesMessage(Exception, "mark_source_mismatch"):
            self.run_command(data=altered)
        self.assertEqual(LessonMark.objects.count(), 6)

    def test_undo_retains_ledger_blocks_new_accounts_and_removes_only_additions(self):
        batch = self.run_command().split("batch=")[1].strip()
        self.run_command(undo=batch)
        self.assertEqual(Enrollment.objects.filter(offering=self.offering, status="enrolled").count(), 1)
        self.assertEqual(LessonMark.objects.filter(lesson__offering=self.offering).count(), 6)
        self.assertEqual(Lesson.objects.filter(offering=self.offering).count(), 6)
        self.assertEqual(LegacyEntityMap.objects.filter(entity_type="student").count(), 2)
        self.assertFalse(
            get_user_model()
            .objects.filter(profile__institutional_identifier__in=["10127", "10128"], is_active=True)
            .exists()
        )
        self.assertIn("already_undone=1", self.run_command(undo=batch))

    def test_undo_rejects_later_edit_without_partial_write(self):
        batch = self.run_command().split("batch=")[1].strip()
        LessonMark.objects.filter(lesson__offering=self.offering, lesson__date="2026-10-05", status="absent").update(
            score=4
        )
        with self.assertRaisesMessage(Exception, "undo_row_changed"):
            self.run_command(undo=batch)
        self.assertEqual(Enrollment.objects.filter(offering=self.offering, status="enrolled").count(), 3)
        self.assertEqual(LessonMark.objects.count(), 21)

    def test_wrong_tenant_and_unmapped_identifier_fail_atomically(self):
        other = Organization.objects.create(
            name="Other", slug="other-mr27", org_type="university", owner=self.actor, status="active", is_active=True
        )
        from apps.legacy_import.services.mr27_recovery import Recovery

        with self.assertRaisesMessage(Exception, "actor_or_tenant_scope"):
            Recovery(other, self.actor, plan(), "0" * 64, 1)
        wrong = get_user_model().objects.create_user(username="wrongidentity")
        UserProfile.objects.filter(user=wrong).update(organization=self.org, institutional_identifier="10127")
        with self.assertRaisesMessage(Exception, "student_identity_conflict"):
            self.run_command()
        self.assertFalse(Program.objects.exists())

    def test_undo_rejects_additional_foreign_enrollment(self):
        batch = self.run_command().split("batch=")[1].strip()
        user = get_user_model().objects.get(profile__institutional_identifier="10127")
        subject = Subject.objects.create(organization=self.org, code="OTHER", name="Other subject")
        other = CourseOffering.objects.create(
            organization=self.org, period=self.offering.period, group=self.group, subject=subject
        )
        Enrollment.objects.create(organization=self.org, offering=other, student=user)
        with self.assertRaisesMessage(Exception, "undo_foreign_usage"):
            self.run_command(undo=batch)
        self.assertEqual(LessonMark.objects.filter(lesson__offering=self.offering).count(), 21)

    def test_teacher_assertion_has_separate_evidence_actual_actor_and_undo(self):
        batch = self.run_command(assertion=True).split("batch=")[1].strip()
        lesson = Lesson.objects.get(offering=self.offering, date="2026-10-22")
        self.assertEqual(lesson.kind, "seminar")
        self.assertEqual(lesson.start_time, dt.time(20, 10))
        self.assertEqual(lesson.hours, 2)
        scores = dict(
            LessonMark.objects.filter(lesson=lesson).values_list(
                "enrollment__student__profile__institutional_identifier", "score"
            )
        )
        self.assertEqual(scores["10127"], 10)
        self.assertEqual(scores["10128"], 10)
        self.assertEqual(LessonMark.objects.get(lesson=lesson, enrollment__student=self.existing).score, 9)
        self.assertFalse(LessonMark.objects.filter(lesson=lesson).exclude(entered_by=self.actor).exists())
        self.assertEqual(LessonMark.objects.filter(lesson__offering=self.offering).count(), 24)
        self.assertIn("teacher_marks_already_present=3", self.run_command(assertion=True))
        self.run_command(undo=batch)
        self.assertEqual(LessonMark.objects.filter(lesson__offering=self.offering).count(), 6)
        self.assertFalse(Lesson.objects.filter(offering=self.offering, date="2026-10-22").exists())

    def test_undo_refuses_new_credential_and_forward_auth_group(self):
        batch = self.run_command().split("batch=")[1].strip()
        user = get_user_model().objects.get(profile__institutional_identifier="10127")
        from django.contrib.auth.models import Group

        group = Group.objects.create(name="laterauthgroup")
        user.groups.add(group)
        with self.assertRaisesMessage(Exception, "undo_foreign_usage"):
            self.run_command(undo=batch)
        user.groups.clear()
        user.set_password("new-credential-in-test")
        user.save(update_fields=["password"])
        with self.assertRaisesMessage(Exception, "undo_credential_issued"):
            self.run_command(undo=batch)
        self.assertTrue(get_user_model().objects.get(pk=user.pk).is_active)

    def test_absence_only_repair_has_its_own_audited_undo(self):
        self.run_command()
        enrollment = Enrollment.objects.get(offering=self.offering, student=self.existing)
        Enrollment.objects.filter(pk=enrollment.pk).update(absence_hours=77)
        result = self.run_command()
        self.assertIn("updated_absence_hours=1", result)
        batch = result.split("batch=")[1].strip()
        self.run_command(undo=batch)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.absence_hours, 77)

    def test_foreign_tenant_usage_is_not_hidden_from_undo_guard(self):
        from django.db import connection

        from apps.organizations.models import Membership, Organization
        from core.rls import bypass_rls

        batch = self.run_command().split("batch=")[1].strip()
        user = get_user_model().objects.get(profile__institutional_identifier="10127")
        with bypass_rls():
            other = Organization.objects.create(
                name="Foreign review org",
                slug="foreign-review",
                org_type="university",
                owner=self.actor,
                status="active",
                is_active=True,
            )
            Membership.objects.create(user=user, organization=other, role=other.roles.get(name="student"))
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute(
                "ALTER TABLE organizations_membership ENABLE ROW LEVEL SECURITY; ALTER TABLE organizations_membership FORCE ROW LEVEL SECURITY; DROP POLICY IF EXISTS rls_tenant_isolation ON organizations_membership; CREATE POLICY rls_tenant_isolation ON organizations_membership USING (current_setting('app.bypass_rls',true)='on' OR organization_id::text=current_setting('app.current_org_id',true)) WITH CHECK (current_setting('app.bypass_rls',true)='on' OR organization_id::text=current_setting('app.current_org_id',true))"
            )
            cursor.execute("CREATE ROLE mr27_independent_rls NOLOGIN NOBYPASSRLS")
            cursor.execute("GRANT USAGE ON SCHEMA public TO mr27_independent_rls")
            cursor.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO mr27_independent_rls")
            cursor.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO mr27_independent_rls")
            cursor.execute("SET LOCAL ROLE mr27_independent_rls")
            cursor.execute(
                "SELECT set_config('app.bypass_rls','off',true),set_config('app.current_org_id',%s,true)",
                [str(self.org.pk)],
            )
        try:
            self.assertEqual(Membership.objects.filter(organization=other, user=user).count(), 0)
            with self.assertRaisesMessage(Exception, "undo_foreign_usage"):
                self.run_command(undo=batch)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
