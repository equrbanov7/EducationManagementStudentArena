"""Migrated PostgreSQL guards for mixed-home-group language level teaching."""

from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.urls import reverse

from apps.registrar import gradebook
from apps.registrar import language_cohort_placement as placement
from apps.registrar import language_cohort_query, language_cohorts
from apps.registrar.models import (
    CourseOffering,
    Enrollment,
    LanguageLevelCohort,
    LanguageLevelPlacement,
    Lesson,
    LessonMark,
    StudentAcademicRecord,
    Subject,
)
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls


class LanguageCohortTests(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            from apps.workload.tests.factories import activate_member

            activate_member(
                cls.org,
                cls.coordinator,
                "lc_source_reader",
                permissions=["journal.view"],
                scope_unit=cls.chair,
                scope_type="unit",
            )
            cls.history.name = "Xarici dil-1 (Elementary)"
            cls.history.save(update_fields=["name"])
            cls.intermediate = Subject.objects.create(
                organization=cls.org, code="LANG-INT", name="Xarici dil-1 (Intermediate)"
            )
            for user in (cls.host, cls.guest, cls.far_student, cls.teacher):
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])

    def create(self, **kwargs):
        values = dict(
            organization=self.org,
            actor=self.coordinator,
            department=self.chair,
            period=self.period,
            subject=self.intermediate,
            instructor=self.teacher,
            name="Evening English",
            hours=30,
            lecture_hours=0,
            seminar_hours=30,
            lab_hours=0,
            entry_score_max=50,
            pass_threshold=51,
            min_final_exam_score=17,
        )
        values.update(kwargs)
        return language_cohorts.create_cohort(**values)

    def record(self, student=None):
        return StudentAcademicRecord.objects.get(organization=self.org, student=student or self.host)

    def move(self, cohort, student=None, **kwargs):
        record = self.record(student)
        sources = language_cohorts.eligible_family_enrollments(cohort=cohort, student_id=record.student_id)
        values = dict(
            cohort=cohort,
            record_id=record.pk,
            actor=self.coordinator,
            reason="Dekanlıq səviyyə qərarı",
            source_enrollment_id=sources[0].pk if len(sources) == 1 else None,
        )
        values.update(kwargs)
        return placement.place_student(**values)

    def test_staff_creates_distinct_teaching_group_and_teacher_sees_it(self):
        cohort = self.create()
        self.assertEqual(cohort.group.parent_id, self.chair.pk)
        self.assertTrue(cohort.group.settings["language_level_cohort"])
        self.assertEqual(cohort.level, "intermediate")
        self.assertEqual(cohort.offering.instructor_id, self.teacher.pk)
        self.assertTrue(language_cohorts.can_manage(self.teacher, cohort))
        self.assertEqual(self.record().group_id, self.group1.pk)
        self.assertFalse(StudentAcademicRecord.objects.filter(group=cohort.group).exists())
        response = self._client(self.teacher).get(reverse("registrar:language_cohort_detail", args=[cohort.pk]))
        self.assertEqual(response.status_code, 200)

    def test_teacher_and_out_of_scope_staff_cannot_create(self):
        for actor in (self.teacher, self.outsider):
            with self.assertRaises(PermissionDenied):
                self.create(actor=actor)
        self.assertEqual(LanguageLevelCohort.objects.count(), 0)

    def test_plain_subject_or_invalid_hours_rejected(self):
        for changes in ({"subject": self.math}, {"hours": 0}, {"hours": 301}, {"name": "x"}):
            with self.assertRaises(ValidationError):
                self.create(**changes)
        self.assertEqual(LanguageLevelCohort.objects.count(), 0)

    def test_existing_same_level_journal_requires_explicit_separate_confirmation(self):
        with self.assertRaises(ValidationError):
            self.create(subject=self.history)
        cohort = self.create(subject=self.history, confirm_separate=True)
        self.assertNotEqual(cohort.offering_id, self.offering.pk)
        self.assertTrue(CourseOffering.objects.filter(pk=self.offering.pk).exists())

    def test_add_and_remove_preserve_home_group_and_mark_ids_without_supersession(self):
        cohort = self.create()
        source = Enrollment.objects.get(student=self.host, offering=self.offering)
        lesson = Lesson.objects.create(
            organization=self.org, offering=self.offering, kind="seminar", date=self.period.start_date, hours=2
        )
        mark = LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=source, status="present", score=8
        )
        target = self.move(cohort)
        source.refresh_from_db()
        mark.refresh_from_db()
        self.assertEqual(source.status, "dropped")
        self.assertIsNone(source.superseded_by_id)
        self.assertEqual(mark.enrollment_id, source.pk)
        self.assertEqual(mark.score, 8)
        self.assertFalse(LessonMark.objects.filter(enrollment=target).exists())
        self.assertEqual(self.record().group_id, self.group1.pk)
        self.assertEqual(target.source_group_id, self.group1.pk)
        event = cohort.placements.get()
        self.assertEqual(
            (event.action, event.source_enrollment_id, event.target_enrollment_id), ("move", source.pk, target.pk)
        )
        own_lesson = Lesson.objects.create(
            organization=self.org, offering=cohort.offering, kind="seminar", date=self.period.start_date, hours=2
        )
        own_mark = LessonMark.objects.create(
            organization=self.org, lesson=own_lesson, enrollment=target, status="absent"
        )
        placement.remove_student(
            cohort=cohort, enrollment_id=target.pk, actor=self.teacher, reason="Səviyyə qrupundan çıxarılır"
        )
        target.refresh_from_db()
        self.assertEqual(target.status, "dropped")
        self.assertTrue(LessonMark.objects.filter(pk=own_mark.pk).exists())
        self.assertEqual(cohort.placements.count(), 2)

    def test_move_between_level_subjects_keeps_old_and_new_marks_and_reuses_enrollment(self):
        first = self.create()
        enrollment = self.move(first)
        second = self.create(name="Elementary second", subject=self.history, confirm_separate=True)
        next_enrollment = self.move(second)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, "dropped")
        self.assertIsNone(enrollment.superseded_by_id)
        self.assertNotEqual(enrollment.offering.subject_id, next_enrollment.offering.subject_id)
        restored = self.move(first)
        self.assertEqual(restored.pk, enrollment.pk)
        self.assertEqual(self.record().group_id, self.group1.pk)

    def test_source_confirmation_tamper_and_duplicate_submit_do_not_write(self):
        cohort = self.create()
        with self.assertRaises(ValidationError):
            self.move(cohort, source_enrollment_id=None)
        self.assertFalse(cohort.placements.exists())
        target = self.move(cohort)
        with self.assertRaises(ValidationError):
            self.move(cohort)
        self.assertEqual(Enrollment.objects.filter(offering=cohort.offering, student=self.host).count(), 1)
        target.refresh_from_db()
        self.assertEqual(target.status, "enrolled")
        self.assertEqual(cohort.placements.count(), 1)

    def test_teacher_can_move_own_authorized_student_but_not_other_home_group_directory(self):
        cohort = self.create()
        allowed = list(language_cohort_query.candidate_records(cohort=cohort, actor=self.teacher))
        self.assertIn(self.host.pk, {r.student_id for r in allowed})
        self.assertNotIn(self.far_student.pk, {r.student_id for r in allowed})
        self.move(cohort, actor=self.teacher)
        with self.assertRaises(PermissionDenied):
            self.move(cohort, student=self.far_student, actor=self.teacher)

    def test_wrong_profile_state_missing_father_irrelevant_to_exact_student_ids(self):
        cohort = self.create()
        self.host.profile.access_state = "archived"
        self.host.profile.save(update_fields=["access_state"])
        with self.assertRaises(ValidationError):
            self.move(cohort)
        self.assertFalse(cohort.placements.exists())

    def test_audit_failure_rolls_back_all_enrollment_and_history_changes(self):
        cohort = self.create()
        with patch("apps.registrar.language_cohort_placement.log_action", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                self.move(cohort)
        self.assertFalse(cohort.placements.exists())
        self.assertFalse(Enrollment.objects.filter(offering=cohort.offering).exists())
        self.assertEqual(Enrollment.objects.get(student=self.host, offering=self.offering).status, "enrolled")

    def test_get_is_read_only_and_other_tenant_or_out_of_scope_has_no_access(self):
        cohort = self.create()
        client = self._client(self.coordinator)
        url = reverse("registrar:language_cohort_detail", args=[cohort.pk])
        before = (Enrollment.objects.count(), LanguageLevelPlacement.objects.count())
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(before, (Enrollment.objects.count(), LanguageLevelPlacement.objects.count()))
        self.assertEqual(self._client(self.outsider).get(url).status_code, 404)
        self.assertEqual(self._client(self.host).get(url).status_code, 404)

    def test_immutable_evidence_and_cohort_identity_have_database_guards(self):
        cohort = self.create()
        self.move(cohort)
        event = cohort.placements.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            LanguageLevelPlacement.objects.filter(pk=event.pk).update(reason="tampered evidence")
        with self.assertRaises(IntegrityError), transaction.atomic():
            LanguageLevelCohort.objects.filter(pk=cohort.pk).update(level="elementary")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN ('registrar_languagelevelcohort','registrar_languagelevelplacement')"
            )
            self.assertEqual(len(rows := cursor.fetchall()), 2)
            self.assertTrue(all(row[1] and row[2] for row in rows))

    def test_new_journal_rows_keep_academic_home_group(self):
        cohort = self.create()
        target = self.move(cohort)
        journal = gradebook.get_offering_journal(offering=cohort.offering)
        row = next(row for row in journal["rows"] if row["enrollment"].pk == target.pk)
        self.assertEqual(row["home_group"].pk, self.group1.pk)
        self.assertNotEqual(row["home_group"].pk, cohort.group_id)

    def test_existing_level_registry_keeps_original_canonical_id(self):
        existing = language_cohort_query.existing_level_journals(self.teacher, self.org)
        self.assertIn(self.offering.pk, {row.pk for row in existing})
        self.assertEqual(LanguageLevelCohort.objects.count(), 0)

    def test_cohort_cannot_be_selected_as_academic_home_by_service_or_raw_sql(self):
        from apps.registrar.integrity import validate_student_record_target

        cohort = self.create()
        record = self.record()
        with self.assertRaises(ValidationError):
            validate_student_record_target(
                organization=self.org,
                student=self.host,
                program=record.program,
                curriculum=record.curriculum,
                group=cohort.group,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentAcademicRecord.objects.filter(pk=record.pk).update(group=cohort.group)
        record.refresh_from_db()
        self.assertEqual(record.group_id, self.group1.pk)

    def test_original_history_surface_is_permission_checked_and_get_never_writes(self):
        cohort = self.create()
        source = Enrollment.objects.get(student=self.host, offering=self.offering)
        lesson = Lesson.objects.create(
            organization=self.org, offering=self.offering, kind="seminar", date=self.period.start_date, hours=2
        )
        mark = LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=source, status="present", score=9
        )
        self.move(cohort)
        event = cohort.placements.get()
        url = reverse("registrar:language_cohort_history", args=[cohort.pk, event.pk])
        client = self._client(self.teacher)

        def read_only(execute, sql, params, many, context):
            if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) and '"django_session"' not in sql:
                self.fail("History GET attempted a write")
            return execute(sql, params, many, context)

        with connection.execute_wrapper(read_only):
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "9")
        content = response.content.decode().split('<main class="lc-page">', 1)[1].split("</main>", 1)[0]
        self.assertNotIn("<form", content)
        self.assertEqual(self._client(self.outsider).get(url).status_code, 404)
        self.assertEqual(self._client(self.host).get(url).status_code, 404)
        mark.refresh_from_db()
        self.assertEqual(mark.score, 9)

    def test_locked_target_or_source_and_past_period_refuse_all_changes(self):
        cohort = self.create()
        with patch("apps.registrar.guest_roster.roster_block_reason", return_value="Locked"):
            with self.assertRaises(ValidationError):
                self.move(cohort)
        with patch("apps.registrar.guest_merge.release_block_reason", return_value="Final grade"):
            with self.assertRaises(ValidationError):
                self.move(cohort)
        self.period.is_current = False
        self.period.save(update_fields=["is_current"])
        with self.assertRaises(ValidationError):
            self.move(cohort)
        self.assertFalse(cohort.placements.exists())
        self.assertFalse(Enrollment.objects.filter(offering=cohort.offering).exists())

    def test_foreign_cohort_reference_and_actor_cannot_mutate(self):
        cohort = self.create()
        with self.assertRaises(PermissionDenied):
            self.move(cohort, actor=self.outsider)
        self.assertFalse(cohort.placements.exists())
        url = reverse("registrar:language_cohort_detail", args=[cohort.pk])
        self.assertEqual(
            self._client(self.outsider)
            .post(url, {"action": "remove", "enrollment": self.host.pk, "reason": "Trying outside scope"})
            .status_code,
            404,
        )

    def test_create_audit_failure_rolls_back_group_and_offering(self):
        from django.apps import apps

        groups = apps.get_model("organizations", "OrgUnit").objects.count()
        offerings = CourseOffering.objects.count()
        with patch("apps.registrar.language_cohorts.log_action", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                self.create()
        self.assertEqual(apps.get_model("organizations", "OrgUnit").objects.count(), groups)
        self.assertEqual(CourseOffering.objects.count(), offerings)
        self.assertFalse(LanguageLevelCohort.objects.exists())

    def test_level_selector_redirects_only_to_authorized_cohort(self):
        cohort = self.create()
        index = reverse("registrar:language_cohorts")
        response = self._client(self.teacher).get(index, {"cohort": str(cohort.pk)})
        self.assertRedirects(response, reverse("registrar:language_cohort_detail", args=[cohort.pk]))
        self.assertEqual(self._client(self.outsider).get(index, {"cohort": str(cohort.pk)}).status_code, 404)

    def test_cross_tenant_request_and_foreign_subject_are_rejected(self):
        from django.test import Client

        from apps.workload.tests.factories import make_org

        foreign = make_org("language-foreign")
        subject = Subject.objects.create(organization=foreign, code="LANG-FOREIGN", name="Xarici dil-1 (Intermediate)")
        with self.assertRaises(ValidationError):
            self.create(subject=subject)
        cohort = self.create()
        client = Client()
        client.force_login(foreign.owner)
        session = client.session
        session["active_organization"] = foreign.slug
        session.save()
        url = reverse("registrar:language_cohort_detail", args=[cohort.pk])
        response = client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, cohort.name, status_code=404)

    def test_instructor_reassignment_removes_old_teacher_management(self):
        from django.contrib.auth import get_user_model

        from apps.workload.tests.factories import TEACHER_PERMS, activate_member

        cohort = self.create()
        new_teacher = get_user_model().objects.create_user("cohort-new-teacher")
        activate_member(self.org, new_teacher, "new_teacher", permissions=TEACHER_PERMS)
        CourseOffering.objects.filter(pk=cohort.offering_id).update(instructor=new_teacher)
        cohort.refresh_from_db()
        self.assertFalse(language_cohorts.can_manage(self.teacher, cohort))
        self.assertTrue(language_cohorts.can_manage(new_teacher, cohort))

    def test_two_active_sources_are_never_arbitrarily_selected(self):
        cohort = self.create()
        Enrollment.objects.create(organization=self.org, student=self.host, offering=self.other_offering)
        with self.assertRaises(ValidationError):
            self.move(cohort)
        self.assertFalse(cohort.placements.exists())
        self.assertFalse(Enrollment.objects.filter(offering=cohort.offering).exists())

    def test_form_post_creates_cohort_and_source_confirmation_is_csrf_protected(self):
        client = self._client(self.coordinator)
        response = client.post(
            reverse("registrar:language_cohorts"),
            {
                "name": "Morning English",
                "department": str(self.chair.pk),
                "period": str(self.period.pk),
                "subject": str(self.intermediate.pk),
                "instructor": str(self.teacher.pk),
                "lecture_hours": "0",
                "seminar_hours": "30",
                "lab_hours": "0",
                "entry_score_max": "50",
                "pass_threshold": "51",
                "min_final_exam_score": "17",
            },
        )
        cohort = LanguageLevelCohort.objects.get(name="Morning English")
        self.assertRedirects(response, reverse("registrar:language_cohort_detail", args=[cohort.pk]))
        from django.test import Client

        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.coordinator)
        session = protected.session
        session["active_organization"] = self.org.slug
        session.save()
        self.assertEqual(
            protected.post(
                reverse("registrar:language_cohort_detail", args=[cohort.pk]),
                {
                    "action": "place",
                    "record": str(self.record().pk),
                    "reason": "Placement without CSRF token",
                },
            ).status_code,
            403,
        )
        self.assertFalse(cohort.placements.exists())

    def test_teacher_end_to_end_list_journal_lesson_and_mark_use_explicit_contact_kind(self):
        import datetime
        from types import SimpleNamespace

        from django.utils import timezone

        from apps.registrar.journal_list_scope import journal_list_base

        today = timezone.localdate()
        self.period.start_date = today - datetime.timedelta(days=30)
        self.period.end_date = today + datetime.timedelta(days=90)
        self.period.academic_year = "2026/2027"
        self.period.save(update_fields=["start_date", "end_date", "academic_year"])
        cohort = self.create()
        target = self.move(cohort)
        visible, _ = journal_list_base(self.teacher, SimpleNamespace(organization=self.org))
        self.assertTrue(visible.filter(pk=cohort.offering_id, journal_current_seminar=True).exists())
        self.assertFalse(visible.filter(pk=cohort.offering_id, journal_current_lecture=True).exists())
        client = self._client(self.teacher)
        url = reverse("registrar:journal_detail", args=[cohort.offering_id])
        self.assertEqual(client.get(url).status_code, 200)
        response = client.post(
            url,
            {
                "action": "add_lesson",
                "lesson_date": today.isoformat(),
                "lesson_kind": "seminar",
                "lesson_hours": "2",
                "lesson_time": "08:30|10:00",
                "topic": "Level-specific practice",
                "off_schedule_reason": "Səviyyə qrupu üçün ilk dərs",
            },
        )
        self.assertEqual(response.status_code, 302)
        lesson = Lesson.objects.get(offering=cohort.offering)
        self.assertEqual(lesson.kind, "seminar")
        response = client.post(
            url,
            {
                "action": "save_marks",
                f"att__{lesson.pk}__{target.pk}": "present",
                f"score__{lesson.pk}__{target.pk}": "8",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LessonMark.objects.get(enrollment=target, lesson=lesson).score, 8)
        with self.assertRaises(gradebook.LessonRuleError):
            gradebook.create_lesson(
                offering=cohort.offering, date=today, kind="lecture", hours=2, created_by=self.teacher
            )
        with self.assertRaises(gradebook.LessonRuleError):
            gradebook.create_lesson(
                offering=cohort.offering, date=today, kind="seminar", hours=31, created_by=self.teacher
            )

    def test_explicit_scheme_or_exact_level_source_required_and_no_scores_copied(self):
        from apps.registrar.models import AssessmentComponent, AssessmentScheme

        default = self.create(
            name="Authoritative level defaults", entry_score_max=None, pass_threshold=None, min_final_exam_score=None
        )
        self.assertEqual(default.offering.assessment_scheme.entry_score_max, 30)
        first = self.create(
            name="Configured same-level source",
            entry_score_max=60,
            pass_threshold=65,
            min_final_exam_score=20,
            confirm_separate=True,
        )
        AssessmentComponent.objects.create(
            organization=self.org, offering=first.offering, name="Speaking", max_score=12
        )
        second = self.create(
            name="Second exact-level cohort",
            source_offering=first.offering,
            confirm_separate=True,
            entry_score_max=None,
            pass_threshold=None,
            min_final_exam_score=None,
        )
        scheme = AssessmentScheme.objects.get(offering=second.offering)
        self.assertEqual((scheme.entry_score_max, scheme.pass_threshold, scheme.min_final_exam_score), (30, 65, 20))
        self.assertFalse(scheme.is_published)
        self.assertEqual(AssessmentComponent.objects.get(offering=second.offering).max_score, 10)
        with self.assertRaises(ValidationError):
            self.create(name="Wrong-level config", source_offering=self.offering, confirm_separate=True)

    def test_contact_kinds_and_grading_config_are_not_silently_inferred(self):
        with self.assertRaises(ValidationError):
            self.create(lecture_hours=None, seminar_hours=None, lab_hours=None)
        with self.assertRaises(ValidationError):
            self.create(hours=50)
        self.assertFalse(LanguageLevelCohort.objects.exists())

    def test_generic_or_wrong_author_syllabus_does_not_attach_to_new_cohort(self):
        from apps.syllabus.models import Syllabus
        from apps.syllabus.public import syllabus_for_offering_obj

        cohort = self.create()
        Syllabus.objects.create(
            organization=self.org,
            subject=self.intermediate,
            period=self.period,
            author=self.coordinator,
        )
        self.assertIsNone(syllabus_for_offering_obj(cohort.offering))
        own = Syllabus.objects.create(
            organization=self.org,
            subject=self.intermediate,
            period=self.period,
            offering=cohort.offering,
            author=self.teacher,
        )
        self.assertEqual(syllabus_for_offering_obj(cohort.offering).pk, own.pk)

    def test_generic_guest_mutations_cannot_bypass_level_placement_history(self):
        from apps.registrar import guest_roster

        cohort = self.create()
        with self.assertRaises(ValidationError):
            guest_roster.add_guest_student(offering=cohort.offering, student=self.host, by_user=self.coordinator)
        target = self.move(cohort)
        with self.assertRaises(ValidationError):
            guest_roster.remove_guest_student(offering=cohort.offering, enrollment=target, by_user=self.coordinator)
        target.refresh_from_db()
        self.assertEqual(target.status, "enrolled")
        self.assertEqual(cohort.placements.count(), 1)

    def test_only_exact_approved_source_syllabus_with_matching_contact_hours_is_reused(self):
        from django.utils import timezone

        from apps.syllabus.models import Syllabus, SyllabusVersion
        from apps.syllabus.public import syllabus_for_offering_obj

        first = self.create()
        syllabus = Syllabus.objects.create(
            organization=self.org,
            subject=self.intermediate,
            period=self.period,
            offering=first.offering,
            author=self.teacher,
        )
        version = SyllabusVersion.objects.create(
            organization=self.org,
            syllabus=syllabus,
            status="approved",
            approval_source="migration",
            locked_at=timezone.now(),
            plan_hours={"seminar": 30},
        )
        syllabus.approved_version = version
        syllabus.save(update_fields=["approved_version"])
        second = self.create(name="Same-level exact plan", source_offering=first.offering, confirm_separate=True)
        self.assertEqual(syllabus_for_offering_obj(second.offering).pk, syllabus.pk)
        different = self.create(
            name="Different contact kinds",
            source_offering=first.offering,
            confirm_separate=True,
            lecture_hours=30,
            seminar_hours=0,
            lab_hours=0,
        )
        self.assertIsNone(syllabus_for_offering_obj(different.offering))

    def test_preintermediate_catalog_variants_have_one_display_level_without_subject_merge(self):
        from apps.registrar.language_levels import level_of

        self.assertEqual(level_of("X (PreIntermediate)"), "pre-intermediate")
        self.assertEqual(level_of("X (Pre-Intermediate)"), "pre-intermediate")
        self.assertEqual(level_of("X (UpperIntermediate)"), "upper-intermediate")

    def test_database_rls_hides_other_tenant_cohorts_and_placement_events(self):
        cohort = self.create()
        self.move(cohort)
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolcreaterole OR rolsuper FROM pg_roles WHERE rolname=current_user")
            if not cursor.fetchone()[0]:
                self.skipTest("PostgreSQL role creation privilege required for a non-bypass RLS probe")
            cursor.execute("CREATE ROLE language_cohort_rls_probe NOLOGIN")
            cursor.execute("GRANT USAGE ON SCHEMA public TO language_cohort_rls_probe")
            cursor.execute(
                "GRANT SELECT ON registrar_languagelevelcohort,registrar_languagelevelplacement TO language_cohort_rls_probe"
            )
            cursor.execute("SET LOCAL ROLE language_cohort_rls_probe")
            try:
                cursor.execute("SELECT set_config('app.bypass_rls','off',true)")
                cursor.execute("SELECT set_config('app.current_org_id','00000000-0000-0000-0000-000000000001',true)")
                cursor.execute("SELECT count(*) FROM registrar_languagelevelcohort")
                self.assertEqual(cursor.fetchone()[0], 0)
                cursor.execute("SELECT count(*) FROM registrar_languagelevelplacement")
                self.assertEqual(cursor.fetchone()[0], 0)
                cursor.execute("SELECT set_config('app.current_org_id',%s,true)", [str(self.org.pk)])
                cursor.execute("SELECT count(*) FROM registrar_languagelevelcohort")
                self.assertEqual(cursor.fetchone()[0], 1)
                cursor.execute("SELECT count(*) FROM registrar_languagelevelplacement")
                self.assertEqual(cursor.fetchone()[0], 1)
            finally:
                cursor.execute("RESET ROLE")

    def test_lost_teaching_permission_does_not_expose_owned_legacy_registry_rows(self):
        from apps.organizations.models import Membership

        Membership.objects.filter(organization=self.org, user=self.teacher).update(is_active=False)
        self.assertEqual(language_cohort_query.existing_level_journals(self.teacher, self.org), [])

    def test_subject_exemption_cannot_be_bypassed_by_a_level_placement(self):
        cohort = self.create()
        with patch("apps.registrar.subject_exempt.is_exempt_from_subject", return_value=True):
            with self.assertRaises(ValidationError):
                self.move(cohort)
        self.assertFalse(cohort.placements.exists())
        self.assertFalse(Enrollment.objects.filter(offering=cohort.offering).exists())

    def test_teacher_readds_own_removed_student_using_explicit_placement_history(self):
        cohort = self.create()
        target = self.move(cohort)
        placement.remove_student(
            cohort=cohort, enrollment_id=target.pk, actor=self.teacher, reason="Qrup siyahısı yenilənir"
        )
        candidates = language_cohort_query.candidate_records(cohort=cohort, actor=self.teacher)
        self.assertIn(self.host.pk, {row.student_id for row in candidates})
        restored = self.move(cohort, actor=self.teacher)
        self.assertEqual(restored.pk, target.pk)
        self.assertEqual(cohort.placements.count(), 3)

    def test_creation_form_labels_follow_request_language(self):
        from django.utils.translation import override

        from apps.registrar.language_cohort_views import CohortForm

        with override("en"):
            form = CohortForm(actor=self.coordinator, organization=self.org)
            self.assertEqual(str(form.fields["name"].label), "Group name")
            self.assertEqual(str(form.fields["lecture_hours"].label), "Lecture hours")

    def test_source_scheme_lookup_and_direct_clone_cannot_cross_actor_chair_scope(self):
        from apps.registrar.language_cohort_views import CohortForm
        from apps.registrar.models import AssessmentScheme

        foreign_source = CourseOffering.objects.create(
            organization=self.org,
            subject=self.intermediate,
            period=self.period,
            group=self.far_group,
            instructor=self.teacher,
        )
        AssessmentScheme.objects.create(organization=self.org, offering=foreign_source)
        form = CohortForm(actor=self.coordinator, organization=self.org)
        self.assertFalse(form.fields["source_offering"].queryset.filter(pk=foreign_source.pk).exists())
        before = LanguageLevelCohort.objects.count()
        with self.assertRaises(PermissionDenied):
            self.create(source_offering=foreign_source, confirm_separate=True)
        self.assertEqual(LanguageLevelCohort.objects.count(), before)
