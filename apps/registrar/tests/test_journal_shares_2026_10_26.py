"""Bölünmüş jurnal (sahib 2026-10-26) — əhatə qaydaları, giriş, POST qapıları, siyahılar, ``apply_journal_shares``.

Sahib: «Fənn 2 müəllim arasında bölünübsə mühazirəçi mühazirəni, seminarçı yalnız öz ballarını görsün»; səviyyə
jurnalında «müəllim jurnalını açanda yalnız öz tələbələrini görsün … müəllimin jurnalı itməsin».
"""

from __future__ import annotations

import io
import json
import os
import re
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import Membership
from apps.registrar import dashboard_data, exam_journal_link, gradebook, journal_shares, services
from apps.registrar.models import (
    CourseOffering,
    Enrollment,
    JournalHygieneDecision,
    JournalShare,
    JournalShareSource,
    Lesson,
    LessonKind,
    LessonMark,
    StudentAcademicRecord,
)
from apps.registrar.tests.test_journal_rules import _setup_offering
from core.rls import bypass_rls

User = get_user_model()
COUNTS_RE = re.compile(r"^journal_shares: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")


def _add_student(cls, name):
    student = User.objects.create_user(name, f"{name}@qku.edu.az", "pw")
    Membership.objects.create(
        user=student, organization=cls.org, role=cls.org.roles.get(name="student"), is_primary=True, is_active=True
    )
    record = StudentAcademicRecord.objects.create(
        organization=cls.org,
        student=student,
        program=cls.program,
        curriculum=cls.curriculum,
        group=cls.group,
        admission_year=2026,
    )
    services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
    return Enrollment.objects.get(student=student, offering=cls.offering)


def _add_teacher(cls, name):
    teacher = User.objects.create_user(name, f"{name}@qku.edu.az", "pw")
    Membership.objects.create(
        user=teacher, organization=cls.org, role=cls.org.roles.get(name="teacher"), is_primary=True, is_active=True
    )
    return teacher


class _ShareBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jsh")
            cls.e1 = cls.enrollment
            cls.e2 = _add_student(cls, "jsh_student2")
            cls.seminarist = _add_teacher(cls, "jsh_seminar")
            cls.stranger = _add_teacher(cls, "jsh_stranger")
            today = timezone.localdate()
            cls.lecture = gradebook.create_lesson(
                allow_past=True, offering=cls.offering, date=today, kind=LessonKind.LECTURE, start_time="08:30"
            )
            cls.seminar = gradebook.create_lesson(
                allow_past=True, offering=cls.offering, date=today, kind=LessonKind.SEMINAR, start_time="10:10"
            )

    def _share(self, teacher, kinds=(), enrollments=(), source=JournalShareSource.LEGACY, batch=""):
        with bypass_rls():
            share = JournalShare.objects.create(
                organization=self.org,
                offering=self.offering,
                teacher=teacher,
                kinds=list(kinds),
                source=source,
                batch=batch,
            )
            share.enrollments.set(list(enrollments))
        return share

    def _scope(self, user):
        with bypass_rls():
            offering = CourseOffering.objects.select_related("organization").get(pk=self.offering.pk)
            return journal_shares.journal_scope(user, offering)

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _url(self):
        return reverse("registrar:journal_detail", args=[self.offering.id])


class ScopeRulesTest(_ShareBase):
    def test_owner_without_share_sees_everything(self):
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])
        scope = self._scope(self.teacher)
        self.assertTrue(scope.full)
        self.assertTrue(scope.can_manage_scores)

    def test_no_shares_is_full_for_everyone(self):
        self.assertTrue(self._scope(self.teacher).full)
        self.assertTrue(self._scope(self.stranger).full)

    def test_owner_with_share_gets_own_plus_unclaimed(self):
        e3 = None
        with bypass_rls():
            e3 = _add_student(self, "jsh_student3")
        self._share(self.teacher, kinds=["lecture"], enrollments=[self.e1])
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])
        scope = self._scope(self.teacher)
        self.assertFalse(scope.full)
        self.assertEqual(scope.kinds, frozenset({"lecture", "lab"}))  # laboratoriyanı heç kim iddia etmir
        self.assertEqual(scope.enrollment_ids, frozenset({str(self.e1.pk), str(e3.pk)}))  # e3 heç kimin deyil
        self.assertTrue(scope.can_manage_scores)

    def test_seminar_holder_sees_only_seminar_and_own_rows(self):
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])
        scope = self._scope(self.seminarist)
        self.assertEqual(scope.kinds, frozenset({"seminar"}))
        self.assertEqual(scope.enrollment_ids, frozenset({str(self.e2.pk)}))
        self.assertFalse(scope.can_manage_scores)
        self.assertTrue(scope.allows_lesson(self.seminar))
        self.assertFalse(scope.allows_lesson(self.lecture))
        with bypass_rls():
            Lesson.objects.filter(pk=self.lecture.pk).update(instructor=self.seminarist)
            self.lecture.refresh_from_db()
        self.assertTrue(scope.allows_lesson(self.lecture))  # öz adına olan dərs həmişə görünür

    def test_level_holder_with_all_kinds_manages_scores_for_own_rows(self):
        self._share(self.seminarist, kinds=[], enrollments=[self.e2])
        scope = self._scope(self.seminarist)
        self.assertIsNone(scope.kinds)
        self.assertEqual(scope.enrollment_ids, frozenset({str(self.e2.pk)}))
        self.assertTrue(scope.can_manage_scores)

    def test_empty_share_is_all(self):
        self._share(self.seminarist)
        self.assertTrue(self._scope(self.seminarist).full)

    def test_superuser_is_full(self):
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])
        admin = User.objects.create_superuser("jsh_root", "jsh_root@qku.edu.az", "pw")
        self.assertTrue(self._scope(admin).full)


class AccessAndGridTest(_ShareBase):
    def test_share_holder_opens_journal_with_own_rows_and_columns(self):
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])
        response = self._client(self.seminarist).get(self._url())
        self.assertEqual(response.status_code, 200)
        journal = response.context["journal"]
        self.assertEqual([row["enrollment"].pk for row in journal["rows"]], [self.e2.pk])
        self.assertEqual([lesson.pk for lesson in journal["lessons"]], [self.seminar.pk])
        self.assertIsNotNone(response.context["journal_share_chip"])
        self.assertEqual([value for value, _label in response.context["lesson_kinds"]], ["seminar"])
        self.assertContains(response, "jd2-share-chip")

    def test_owner_without_share_sees_full_grid(self):
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])
        response = self._client(self.teacher).get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["journal"]["rows"]), 2)
        self.assertEqual(len(response.context["journal"]["lessons"]), 2)
        self.assertIsNone(response.context.get("journal_share_chip"))

    def test_non_holder_gets_404(self):
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])
        self.assertEqual(self._client(self.stranger).get(self._url()).status_code, 404)

    def test_inactive_share_gives_no_access(self):
        share = self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])
        with bypass_rls():
            JournalShare.objects.filter(pk=share.pk).update(is_active=False)
        self.assertEqual(self._client(self.seminarist).get(self._url()).status_code, 404)

    def test_level_holder_does_not_see_other_levels_lessons(self):
        """Səviyyə jurnalı: xanaları yalnız başqa payın tələbələrində olan dərs boş sütun kimi görünmür."""
        self._share(self.teacher, kinds=[], enrollments=[self.e1])
        self._share(self.seminarist, kinds=[], enrollments=[self.e2])
        with bypass_rls():
            # Köçürülmüş dərs adsızdır (``instructor`` boş); pay sahibinin dərsi öz adınadır.
            Lesson.objects.filter(pk=self.lecture.pk).update(instructor=None)
            Lesson.objects.filter(pk=self.seminar.pk).update(instructor=self.seminarist)
            LessonMark.objects.create(organization=self.org, lesson=self.lecture, enrollment=self.e1, status="present")
            LessonMark.objects.create(organization=self.org, lesson=self.seminar, enrollment=self.e2, status="present")
            offering = CourseOffering.objects.get(pk=self.offering.pk)
            own = gradebook.get_offering_journal(
                offering=offering, scope=journal_shares.journal_scope(self.seminarist, offering)
            )
            offering = CourseOffering.objects.get(pk=self.offering.pk)
            owner = gradebook.get_offering_journal(
                offering=offering, scope=journal_shares.journal_scope(self.teacher, offering)
            )
        self.assertEqual([lesson.pk for lesson in own["lessons"]], [self.seminar.pk])
        self.assertEqual([lesson.pk for lesson in owner["lessons"]], [self.lecture.pk])
        self.assertEqual([row["enrollment"].pk for row in owner["rows"]], [self.e1.pk])

    def test_grading_math_is_untouched(self):
        """Göstərilən sətir daralır, giriş balı/qayıb isə bütün dərslər üzrə qalır."""
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])
        with bypass_rls():
            LessonMark.objects.create(organization=self.org, lesson=self.lecture, enrollment=self.e2, status="absent")
            offering = CourseOffering.objects.get(pk=self.offering.pk)
            full = gradebook.get_offering_journal(offering=offering)
            scoped = gradebook.get_offering_journal(
                offering=offering, scope=journal_shares.journal_scope(self.seminarist, offering)
            )
        full_row = next(row for row in full["rows"] if row["enrollment"].pk == self.e2.pk)
        (scoped_row,) = scoped["rows"]
        self.assertEqual(scoped_row["absence_hours"], full_row["absence_hours"])
        self.assertEqual(scoped_row["entry_score"], full_row["entry_score"])
        self.assertEqual(len(scoped_row["cells"]), 1)


class PostGuardTest(_ShareBase):
    def setUp(self):
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])

    def _autosave(self, lesson, enrollment, status="present", user=None):
        return self._client(user or self.seminarist).post(
            self._url(),
            {"action": "save_marks", "autosave": "1", f"att__{lesson.id}__{enrollment.id}": status},
        )

    def _marks(self):
        with bypass_rls():
            return set(LessonMark.objects.values_list("lesson_id", "enrollment_id"))

    def test_holder_writes_own_seminar_cell(self):
        response = self._autosave(self.seminar, self.e2)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["written"], 1)
        self.assertEqual(self._marks(), {(self.seminar.pk, self.e2.pk)})

    def test_holder_cannot_write_lecture_cell(self):
        response = self._autosave(self.lecture, self.e2)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "share_scope")
        self.assertEqual(self._marks(), set())

    def test_holder_cannot_write_other_students_cell(self):
        self.assertEqual(self._autosave(self.seminar, self.e1).status_code, 403)
        self.assertEqual(self._marks(), set())

    def test_owner_still_writes_everything(self):
        self.assertEqual(self._autosave(self.lecture, self.e1, user=self.teacher).status_code, 200)
        self.assertEqual(self._autosave(self.seminar, self.e2, user=self.teacher).status_code, 200)

    def _add_lesson(self, kind, instructor=""):
        return self._client(self.seminarist).post(
            self._url(),
            {
                "action": "add_lesson",
                "lesson_date": timezone.localdate().isoformat(),
                "lesson_kind": kind,
                "lesson_hours": "2",
                "lesson_time": "13:35|15:05",
                "lesson_instructor": instructor,
            },
        )

    def test_add_lesson_outside_kinds_is_refused(self):
        self.assertEqual(self._add_lesson("lecture").status_code, 403)
        with bypass_rls():
            self.assertEqual(Lesson.objects.filter(offering=self.offering).count(), 2)

    def test_add_lesson_is_written_in_holders_name(self):
        response = self._add_lesson("seminar", instructor=str(self.teacher.pk))
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            lesson = Lesson.objects.get(offering=self.offering, start_time="13:35")
        self.assertEqual((lesson.kind, lesson.instructor_id), (LessonKind.SEMINAR, self.seminarist.pk))

    def test_scores_actions_refused_without_score_management(self):
        response = self._client(self.seminarist).post(
            self._url(), {"action": "save_component_scores", f"cscore__x__{self.e2.id}": "5"}
        )
        self.assertEqual(response.status_code, 403)

    def test_midterm_save_refused_for_seminar_only_holder(self):
        url = reverse("registrar:journal_kollokvium_save", args=[self.offering.id])
        response = self._client(self.seminarist).post(url, {f"kscore__x__{self.e2.id}": "5", "autosave": "1"})
        self.assertEqual(response.status_code, 403)

    def test_lesson_action_on_foreign_kind_is_refused(self):
        url = reverse("registrar:journal_lesson_action", args=[self.offering.id, self.lecture.id])
        response = self._client(self.seminarist).post(url, {"action": "delete_lesson"})
        self.assertEqual(response.status_code, 403)
        with bypass_rls():
            self.assertTrue(Lesson.objects.filter(pk=self.lecture.pk).exists())


class ListsTest(_ShareBase):
    def test_journal_list_includes_share_offering_with_scoped_count(self):
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])
        response = self._client(self.seminarist).get(reverse("registrar:journal_list"), {"year": ""})
        self.assertEqual(response.status_code, 200)
        (offering,) = list(response.context["offerings"])
        self.assertEqual(offering.pk, self.offering.pk)
        self.assertEqual(offering.student_count, 1)

    def test_stranger_list_is_empty(self):
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])
        response = self._client(self.stranger).get(reverse("registrar:journal_list"), {"year": ""})
        self.assertEqual(list(response.context["offerings"]), [])

    def test_dashboard_and_exam_wizard_include_share_offering(self):
        self._share(self.seminarist, kinds=[], enrollments=[self.e2])
        with bypass_rls():
            data = dashboard_data.teacher_offerings(organization=self.org, teacher=self.seminarist, period=self.period)
            wizard = set(exam_journal_link.teacher_offerings(self.org, self.seminarist, period=self.period))
        self.assertEqual([(row["offering_id"], row["students"]) for row in data["rows"]], [(self.offering.pk, 1)])
        self.assertEqual(wizard, {self.offering})


class ApplyJournalSharesCommandTest(_ShareBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.admin = User.objects.create_superuser("jsh_admin", "jsh_admin@qku.edu.az", "pw")
            cls.e3 = _add_student(cls, "jsh_student3")
            cls.e4 = _add_student(cls, "jsh_student4")
            LessonMark.objects.create(organization=cls.org, lesson=cls.lecture, enrollment=cls.e4, status="present")

    def _file(self, shares, drops=()):
        payload = {
            "format": "journal-shares/1",
            "period": str(self.period.pk),
            "shares": shares,
            "drop_enrollments": [str(pk) for pk in drops],
        }
        handle, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
        self.addCleanup(os.unlink, path)
        return path

    def _run(self, *args):
        out = io.StringIO()
        call_command("apply_journal_shares", "--org", self.org.slug, "--actor", self.admin.username, *args, stdout=out)
        lines = out.getvalue().splitlines()
        for line in lines:
            self.assertRegex(line, COUNTS_RE)  # stdout-a YALNIZ saylar
        counts = {}
        for line in lines:
            for pair in line.split(" ")[1:]:
                key, value = pair.split("=")
                counts[key] = value
        return counts

    def _shares_payload(self):
        return [
            {
                "offering": str(self.offering.pk),
                "teacher": self.seminarist.pk,
                "kinds": ["seminar"],
                "enrollments": [str(self.e2.pk), "00000000-0000-0000-0000-000000000000"],
                "journals": ["x"],
                "is_owner": False,
            },
            {
                "offering": str(self.offering.pk),
                "teacher": self.teacher.pk,
                "kinds": ["lecture", "seminar"],
                "enrollments": [str(e.pk) for e in (self.e1, self.e2, self.e3, self.e4)],
                "journals": ["y"],
                "is_owner": True,
            },
            {
                "offering": str(self.offering.pk),
                "teacher": 987654321,
                "kinds": [],
                "enrollments": [],
                "is_owner": False,
            },
        ]

    def test_dry_run_counts_and_writes_nothing(self):
        counts = self._run("--file", self._file(self._shares_payload(), drops=[self.e3.pk, self.e4.pk]))
        self.assertEqual(counts["mode"], "dry_run")
        self.assertEqual(counts["shares_created"], "2")
        self.assertEqual(counts["teacher_missing"], "1")
        # Sıfır uuid + əvvəlcə çıxarılan e3 (çıxarışlar paylardan ƏVVƏL tətbiq olunur).
        self.assertEqual(counts["enrollments_invalid"], "2")
        self.assertEqual(counts["drops_applied"], "1")
        self.assertEqual(counts["drop_kept_has_data"], "1")
        with bypass_rls():
            self.assertFalse(JournalShare.objects.exists())
            self.assertEqual(Enrollment.objects.get(pk=self.e3.pk).status, Enrollment.Status.ENROLLED)

    def test_apply_is_idempotent_and_undo_deactivates(self):
        path = self._file(self._shares_payload(), drops=[self.e3.pk, self.e4.pk])
        counts = self._run("--file", path, "--apply")
        self.assertEqual((counts["shares_created"], counts["drops_applied"]), ("2", "1"))
        batch = counts["batch"]
        with bypass_rls():
            seminar = JournalShare.objects.get(teacher=self.seminarist)
            owner = JournalShare.objects.get(teacher=self.teacher)
            self.assertEqual(seminar.kinds, ["seminar"])
            self.assertEqual(set(seminar.enrollments.values_list("pk", flat=True)), {self.e2.pk})
            self.assertEqual(owner.kinds, [])  # dərslərdəki bütün növləri örtür → hamısı
            self.assertEqual(list(owner.enrollments.all()), [])  # bütün aktiv tələbələr → hamısı
            self.assertEqual(Enrollment.objects.get(pk=self.e3.pk).status, Enrollment.Status.DROPPED)
            self.assertEqual(Enrollment.objects.get(pk=self.e4.pk).status, Enrollment.Status.ENROLLED)
            decision = JournalHygieneDecision.objects.get(enrollment=self.e3)
            self.assertEqual((decision.category, decision.reason_code), ("empty_subject", "language_level"))
        again = self._run("--file", path, "--apply")
        self.assertEqual((again["shares_created"], again["shares_unchanged"]), ("0", "2"))
        self.assertEqual(again["drops_applied"], "0")
        undo = self._run("--undo", batch, "--apply")
        self.assertEqual(undo["shares_deactivated"], "2")
        with bypass_rls():
            self.assertFalse(JournalShare.objects.filter(is_active=True).exists())

    def test_manual_share_is_never_overwritten(self):
        self._share(self.seminarist, kinds=["lecture"], source=JournalShareSource.MANUAL)
        counts = self._run("--file", self._file(self._shares_payload()[:1]), "--apply")
        self.assertEqual((counts["manual_kept"], counts["shares_created"]), ("1", "0"))
        with bypass_rls():
            self.assertEqual(JournalShare.objects.get(teacher=self.seminarist).kinds, ["lecture"])

    def test_inactive_teacher_is_skipped(self):
        with bypass_rls():
            Membership.objects.filter(user=self.seminarist).update(is_active=False)
        counts = self._run("--file", self._file(self._shares_payload()[:1]), "--apply")
        self.assertEqual((counts["teacher_inactive"], counts["shares_created"]), ("1", "0"))

    def test_bad_inputs_fail_closed(self):
        with self.assertRaises(CommandError):
            self._run("--undo", "not-a-batch")
        handle, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(handle, "w") as stream:
            stream.write('{"format": "other"}')
        self.addCleanup(os.unlink, path)
        with self.assertRaises(CommandError):
            self._run("--file", path)


class ProdDataOpsWhitelistTest(SimpleTestCase):
    def test_command_is_whitelisted_with_counts_only_log(self):
        text = (Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("          - apply_journal_shares\n", text)
        self.assertIn("            apply_journal_shares)\n", text)
        self.assertIn("^journal-shares-[0-9a-z-]+$", text)
        self.assertIn("shares.json.enc", text)
        self.assertIn("/tmp/journal_shares_${GITHUB_RUN_ID}.json", text)
        self.assertIn("^journal_shares: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$", text)
        self.assertIn("^shares-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$", text)
