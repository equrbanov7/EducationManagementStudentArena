"""İmtahan nəticəsi → jurnal: doğru qeydiyyat, görünən atlama, xəbərdarlıq, fənn seçicisi (sahib 2026-10-26).

Sahib: «İmtahan yaradarkən fənn seçirəm — tələbənin imtahan nəticəsi kimi sistemə düşəcəkmi? Bu hissə doğru
olsun. Təkrar fənn varsa göstərməsin. Qrupa əlavə olunanda ona aid fənn çıxmasa ya da tələbə onunla bağlı
xəbərdarlıq ala bilərik.»
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.exams.models import Exam
from apps.exams.services import exam_journal_link, journal_sync
from apps.exams.services.subject_picker_hints import normalize_subject_name
from apps.exams.tests.test_exam_center_policy import _assign_user_to_org
from apps.exams.tests.test_exam_journal_link_2026_10_24 import _LinkSetup, _login
from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar import exam_bridge
from apps.registrar import exam_journal_link as registrar_link
from apps.registrar.models import CourseOffering, Enrollment, FinalGrade, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType
from core.rls import bypass_rls
from core.roles import ProfileRole

User = get_user_model()


_AUTUMN = datetime.date(2026, 9, 1)


def _cand(pk, *, offering_id="o1", source_group_id=None, created=1, period_id="p", start=_AUTUMN):
    period = SimpleNamespace(pk=period_id, start_date=start)
    offering = SimpleNamespace(subject_id="s", period_id=period_id, period=period)
    return SimpleNamespace(
        pk=pk,
        student_id=1,
        offering_id=offering_id,
        offering=offering,
        source_group_id=source_group_id,
        created_at=datetime.datetime(2026, 1, created, tzinfo=datetime.timezone.utc),
    )


class PickEnrollmentTests(SimpleTestCase):
    def test_linked_journal_wins_then_own_group_then_newest(self):
        own_old = _cand("a", offering_id="own", created=1)
        guest_new = _cand("b", offering_id="guest", source_group_id="g", created=9)
        own_new = _cand("c", offering_id="own2", created=5)
        with self.assertLogs("apps.registrar.exam_bridge", level="WARNING"):
            self.assertIs(exam_bridge.pick_enrollment([own_old, guest_new, own_new], ["guest"]), guest_new)
        with self.assertLogs("apps.registrar.exam_bridge", level="WARNING"):
            self.assertIs(exam_bridge.pick_enrollment([own_old, guest_new, own_new]), own_new)
        with self.assertLogs("apps.registrar.exam_bridge", level="WARNING"):
            self.assertIs(exam_bridge.pick_enrollment([own_old, guest_new]), own_old)

    def test_single_or_empty(self):
        only = _cand("a")
        self.assertIs(exam_bridge.pick_enrollment([only]), only)
        self.assertIsNone(exam_bridge.pick_enrollment([]))

    def test_choose_never_falls_back_to_a_future_period(self):
        current = SimpleNamespace(pk="cur", start_date=datetime.date(2026, 9, 1))
        future = _cand("f", period_id="fut", start=datetime.date(2027, 2, 1))
        older = _cand("o", period_id="old", start=datetime.date(2025, 9, 1))
        newer = _cand("n", period_id="spr", start=datetime.date(2026, 2, 1))
        self.assertIsNone(exam_bridge.choose_enrollment([future], current))
        self.assertIs(exam_bridge.choose_enrollment([future, older, newer], current), newer)
        in_current = _cand("c", period_id="cur")
        self.assertIs(exam_bridge.choose_enrollment([future, newer, in_current], current), in_current)


class SubjectNameNormalizationTests(SimpleTestCase):
    def test_az_letters_case_spaces_and_hyphens_are_folded(self):
        self.assertEqual(normalize_subject_name("Veb-proqramlaşdırma"), normalize_subject_name("veb proqramlasdirma"))
        self.assertEqual(normalize_subject_name("İnformatika"), normalize_subject_name("INFORMATIKA"))
        self.assertEqual(normalize_subject_name("Ədəbiyyat, Ölkəşünaslıq"), "edebiyyatolkesunasliq")
        self.assertNotEqual(normalize_subject_name("Fizika"), normalize_subject_name("Fizika 2"))


class _FinalSetup(_LinkSetup):
    def _final(self, title="FN"):
        return self._exam(category="final", title=title)

    def _grade(self, enrollment):
        with bypass_rls():
            return FinalGrade.objects.filter(enrollment=enrollment).first()

    def _drop_current_enrollment(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.enrollment.pk).update(status=Enrollment.Status.DROPPED)

    def _period(self, name, start, end, **extra):
        with bypass_rls():
            return AcademicPeriod.objects.create(
                organization=self.org,
                name=name,
                period_type=AcademicPeriodType.SEMESTER,
                academic_year=f"{start.year}/{start.year + 1}",
                start_date=start,
                end_date=end,
                **extra,
            )

    def _enroll_in(self, period=None, group=None, *, source_group=None):
        with bypass_rls():
            offering = CourseOffering.objects.create(
                organization=self.org, subject=self.subject, period=period or self.period, group=group or self.group
            )
            enrollment = Enrollment.objects.create(
                organization=self.org, student=self.student, offering=offering, source_group=source_group
            )
        return offering, enrollment

    def _guest_group(self, name="G-X"):
        with bypass_rls():
            return OrgUnit.objects.create(organization=self.org, name=name, slug=name.lower(), unit_type="group")


class FinalBridgeEnrollmentTests(_FinalSetup):
    def test_future_period_enrollment_is_never_used_past_one_is(self):
        self._drop_current_enrollment()
        future = self._period("Yaz", datetime.date(2027, 2, 1), datetime.date(2027, 6, 30))
        _future_offering, future_enrollment = self._enroll_in(future)
        with bypass_rls():
            self.assertIsNone(
                exam_bridge.resolve_enrollment(student=self.student, subject_id=self.subject.pk, organization=self.org)
            )
        self._finish(*self._final(), correct=3)
        self.assertIsNone(self._grade(future_enrollment))

        past = self._period("Yaz keçmiş", datetime.date(2026, 2, 1), datetime.date(2026, 6, 30))
        _past_offering, past_enrollment = self._enroll_in(past)
        with bypass_rls():
            chosen = exam_bridge.resolve_enrollment(
                student=self.student, subject_id=self.subject.pk, organization=self.org
            )
        self.assertEqual(chosen, past_enrollment)

    def test_current_period_fallback_ignores_future_periods_without_a_current_flag(self):
        with bypass_rls():
            AcademicPeriod.objects.filter(organization=self.org).update(is_current=False)
        self._period("Gələcək", datetime.date(2099, 2, 1), datetime.date(2099, 6, 30))
        with bypass_rls():
            self.assertEqual(exam_bridge._current_period(self.org), self.period)

    def test_final_without_enrollment_is_logged_and_counted(self):
        self._drop_current_enrollment()
        counter = journal_sync.journal_sync_skips_total.labels(reason=journal_sync.SKIP_NO_ENROLLMENT)
        before = counter._value.get()
        with self.assertLogs("apps.exams.services.journal_sync", level="WARNING") as logs:
            self._finish(*self._final(), correct=3)
        self.assertEqual(counter._value.get(), before + 1)
        self.assertTrue(any("no_enrollment" in line for line in logs.output), logs.output)

    def test_final_follows_the_exam_journal_link(self):
        guest = self._guest_group()
        guest_offering, guest_enrollment = self._enroll_in(group=guest, source_group=self.group)
        exam, options = self._final()
        with bypass_rls():
            exam.allowed_units.add(guest)
            exam_journal_link.refresh_links(exam)
            self.assertEqual(list(exam.journal_offerings.all()), [guest_offering])
        self._finish(exam, options, correct=3)
        self.assertEqual(self._grade(guest_enrollment).exam_score, Decimal("50"))
        self.assertIsNone(self._grade(self.enrollment))

    def test_without_link_own_group_wins_over_newer_guest_enrollment(self):
        guest = self._guest_group()
        _guest_offering, guest_enrollment = self._enroll_in(group=guest, source_group=self.group)
        with self.assertLogs("apps.registrar.exam_bridge", level="WARNING"):
            self._finish(*self._final(), correct=3)
        self.assertEqual(self._grade(self.enrollment).exam_score, Decimal("50"))
        self.assertIsNone(self._grade(guest_enrollment))


class CoverageTests(_FinalSetup):
    def _student(self, username, *, group=None):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        with bypass_rls():
            _assign_user_to_org(user, self.org, ProfileRole.STUDENT, "student")
            if group is not None:
                StudentAcademicRecord.objects.create(
                    organization=self.org,
                    student=user,
                    program=self.program,
                    curriculum=self.curriculum,
                    group=group,
                    admission_year=2024,
                )
        return user

    def test_enrollment_coverage_counts_and_query_budget(self):
        lonely = self._student("cv_lonely")
        guest = self._guest_group()
        self._enroll_in(group=guest, source_group=self.group)  # self.student → 2 jurnal
        single = self._student("cv_single")
        with bypass_rls():
            Enrollment.objects.create(organization=self.org, student=single, offering=self.offering)
            with CaptureQueriesContext(connection) as ctx:
                coverage = registrar_link.enrollment_coverage(
                    self.org, self.subject.pk, [self.student.pk, lonely.pk, single.pk]
                )
            self.assertLessEqual(len(ctx.captured_queries), 2)
            with self.assertNumQueries(1):
                registrar_link.enrollment_coverage(self.org, self.subject.pk, [lonely.pk], period=self.period)
        self.assertEqual(coverage, {"ok": 1, "none": [lonely.pk], "multiple": [self.student.pk]})
        self.assertEqual(registrar_link.enrollment_coverage(self.org, None, [lonely.pk])["none"], [])

    def _count(self, **params):
        response = _login(self.center, self.org).get(
            reverse("exams:assigned_student_count"), params, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_confirm_count_reports_students_without_a_journal(self):
        lonely = self._student("cv_lonely", group=self.group)
        data = self._count(units=str(self.group.pk), subject=str(self.subject.pk), category="final")
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["no_journal"], 1)
        self.assertEqual(data["multiple_journals"], 0)
        self.assertEqual(len(data["warnings"]), 1)
        self.assertIn("1", data["warnings"][0])
        # Kateqoriyası jurnala yazılmayan imtahan (quiz) — xəbərdarlıq yoxdur.
        quiz = self._count(units=str(self.group.pk), subject=str(self.subject.pk), category="quiz")
        self.assertEqual((quiz["total"], quiz["warnings"]), (2, []))
        self.assertIsNotNone(lonely)

    def test_confirm_count_includes_journal_roster_students_like_access_policy(self):
        roster_only = self._student("cv_roster", group=self.other_group)
        with bypass_rls():
            Enrollment.objects.create(organization=self.org, student=roster_only, offering=self.offering)
        self.assertEqual(self._count(units=str(self.group.pk))["total"], 1)
        data = self._count(units=str(self.group.pk), subject=str(self.subject.pk), category="midterm")
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["warnings"], [])

    def test_confirm_count_warns_when_groups_have_no_journal_for_the_subject(self):
        self._student("cv_other", group=self.other_group)
        data = self._count(units=str(self.other_group.pk), subject=str(self.subject.pk), category="final")
        self.assertEqual(data["no_journal"], 1)
        self.assertEqual(len(data["warnings"]), 2)

    def _create(self, **extra):
        client = _login(self.center, self.org)
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(
                reverse("exams:create_exam") + "?modal=1",
                self._payload(**extra),
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(response.status_code, 200, response.content[:400])
        return [(message.level_tag, str(message)) for message in get_messages(response.wsgi_request)]

    def test_saving_an_exam_flashes_a_non_blocking_coverage_warning(self):
        self._student("cv_lonely", group=self.group)
        texts = self._create(exam_type_extended="final")
        with bypass_rls():
            self.assertTrue(Exam.objects.filter(title="JS Loop").exists())
        warnings = [text for level, text in texts if level == "warning"]
        self.assertTrue(any("1" in text and "jurnal" in text for text in warnings), texts)

    def test_saving_with_full_coverage_has_no_warning(self):
        texts = self._create()
        with bypass_rls():
            exam = Exam.objects.get(title="JS Loop")
        from apps.exams.services.exam_journal_coverage import exam_coverage_warnings

        with bypass_rls():
            self.assertEqual(exam_coverage_warnings(exam), [])
        self.assertEqual([text for level, text in texts if level == "warning"], [])


class SubjectPickerTests(_FinalSetup):
    def _search(self, user, url_name="exams:subject_search", **params):
        response = _login(user, self.org).get(reverse(url_name), params, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        return {row["id"]: row for row in response.json()["results"]}

    def test_near_duplicate_names_get_a_disambiguating_hint(self):
        with bypass_rls():
            twin = Subject.objects.create(organization=self.org, code="CS101B", name="Proqramlaşdirma")
            Subject.objects.create(organization=self.org, code="ARX1", name="Proqramlaşdırma arxiv", is_archived=True)
            Subject.objects.create(organization=self.org, code="OFF1", name="Proqramlaşdırma köhnə", is_active=False)
        rows = self._search(self.teacher, q="Proq")
        self.assertEqual(set(rows), {str(self.subject.pk), str(twin.pk)})  # arxiv / passiv görünmür
        mine = rows[str(self.subject.pk)]
        self.assertEqual(mine["hint"], f"CS101 · {self.group.name}")
        self.assertEqual(mine["text"], f"Proqramlaşdırma (CS101 · {self.group.name})")
        self.assertIn("CS101B", rows[str(twin.pk)]["hint"])
        self.assertIn("jurnal", rows[str(twin.pk)]["hint"])

    def test_distinct_names_have_no_hint(self):
        rows = self._search(self.teacher, q="Proq")
        self.assertNotIn("hint", rows[str(self.subject.pk)])
        self.assertEqual(rows[str(self.subject.pk)]["meta"], "CS101")

    def test_teacher_subjects_endpoint_hides_archived_but_keeps_selected_ok(self):
        with bypass_rls():
            Subject.objects.filter(pk=self.subject.pk).update(is_archived=True)
        data = _login(self.teacher, self.org).get(
            reverse("exams:journal_teacher_subjects"),
            {"teacher": self.teacher.pk, "selected": str(self.subject.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        payload = data.json()
        self.assertEqual(payload["results"], [])
        self.assertTrue(payload["selected_ok"])


class SyncFinalScoresCommandTests(_FinalSetup):
    def _run(self, *args):
        out = StringIO()
        call_command("sync_final_scores", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_then_apply_replays_a_lost_final_score(self):
        self._drop_current_enrollment()
        exam, options = self._final()
        self._finish(exam, options, correct=3)
        self.assertIsNone(self._grade(self.enrollment))
        with bypass_rls():
            Enrollment.objects.filter(pk=self.enrollment.pk).update(status=Enrollment.Status.ENROLLED)
        out = self._run("--org", self.org.slug, "--exam", exam.slug)
        self.assertIn("DRY-RUN", out)
        self.assertIn("written 1", out)
        self.assertIsNone(self._grade(self.enrollment))
        out = self._run("--org", self.org.slug, "--exam", str(exam.pk), "--apply")
        self.assertIn("YAZILDI", out)
        self.assertEqual(self._grade(self.enrollment).exam_score, Decimal("50"))

    def test_counts_no_enrollment_and_only_official_attempt(self):
        self._drop_current_enrollment()
        exam, options = self._final()
        self._finish(exam, options, correct=1, started_at=timezone.now() - datetime.timedelta(hours=2))
        self._finish(exam, options, correct=3, attempt_number=2)
        out = self._run("--org", self.org.slug, "--apply")
        self.assertIn("rəsmi final cəhdi 1", out)
        self.assertIn("no_enrollment 1", out)

    def test_unknown_exam_is_an_error(self):
        with self.assertRaises(CommandError):
            self._run("--exam", "no-such-exam")
