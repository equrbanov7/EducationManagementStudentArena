"""Real source-bound current allocation, preserving journal rows byte for byte."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import Membership
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from core.reviewed_graph import digest, graph
from core.rls import bypass_rls

from ..constants import TaskStatus
from ..models import TeacherAssignment, TeachingTaskRow
from ..services import history_restore as service
from ..services.scoping import WorkloadDenied
from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task


class HistoryRestoreTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("history-restore")
            cls.admin = cls.org.owner
            cls.admin.is_superuser = True
            cls.admin.save(update_fields=["is_superuser"])
            cls.stack = make_structure(cls.org, code="HR")
            cls.teacher = get_user_model().objects.create_user("history_restore_teacher")
            cls.other = get_user_model().objects.create_user("history_restore_other")
            for user in (cls.teacher, cls.other):
                activate_member(cls.org, user, "teacher", permissions=TEACHER_PERMS, scope_unit=cls.stack["chair"])
            cls.task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.DISTRIBUTED)
            cls.offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=cls.stack["subject"],
                period=cls.stack["period"],
                group=cls.stack["group"],
                instructor=cls.teacher,
                lesson_hours=75,
            )
            cls.lesson = Lesson.objects.create(
                organization=cls.org,
                offering=cls.offering,
                date=timezone.localdate(),
                kind="lecture",
                hours=2,
                instructor=cls.teacher,
            )
            cls.student = get_user_model().objects.create_user("history_restore_student")
            Membership.objects.create(organization=cls.org, user=cls.student, role=cls.org.roles.get(name="student"))
            cls.enrollment = Enrollment.objects.create(organization=cls.org, offering=cls.offering, student=cls.student)
            LessonMark.objects.create(organization=cls.org, lesson=cls.lesson, enrollment=cls.enrollment, score=8)
            cls.hours = {"lecture": 45, "seminar": 30, "lab": 0}

    def request(self, user=None, *, real=None, mode=None):
        request = RequestFactory().post("/")
        request.user, request.organization = user or self.admin, self.org
        if real is not None:
            request.real_user, request.is_view_as, request.view_as_mode = real, True, mode
        return request

    def restore(self, **kwargs):
        data = {
            "request": self.request(),
            "offering_id": self.offering.pk,
            "chair_id": self.stack["chair"].pk,
            "hours": self.hours,
            "reason": "Mövcud dərsləri olan jurnalın cari yükü bərpa edilir.",
        }
        return service.restore(**{**data, **kwargs})

    def graph(self):
        return digest(graph({"registrar.CourseOffering": [self.offering.pk]}, organization_id=self.org.pk))

    def test_new_row_actual_allocations_current_visibility_and_exact_graph_preserved(self):
        from apps.registrar.teacher_journal_list import own_visible_queryset

        with bypass_rls():
            before = self.graph()
            result = self.restore()
            self.assertEqual(result["status"], "restored")
            self.assertEqual(self.graph(), before)
            self.assertEqual(
                set(
                    TeacherAssignment.objects.filter(row_id=result["row_id"]).values_list(
                        "activity", "hours", "teacher_id"
                    )
                ),
                {("lecture", 45, self.teacher.pk), ("seminar", 30, self.teacher.pk)},
            )
            current = own_visible_queryset(
                CourseOffering.objects.filter(pk=self.offering.pk), self.teacher, self.org
            ).get()
            self.assertTrue(current.journal_is_current_load)
            self.assertTrue(current.journal_current_lecture)
            self.assertTrue(current.journal_current_seminar)
            self.assertFalse(current.journal_current_lab)

    def test_identical_repeat_does_not_double_assign_or_change_graph(self):
        with bypass_rls():
            self.restore()
            row_count = TeachingTaskRow.objects.count()
            assignment_ids = set(TeacherAssignment.objects.values_list("pk", flat=True))
            before = self.graph()
            self.assertEqual(self.restore()["status"], "already_restored")
            self.assertEqual(TeachingTaskRow.objects.count(), row_count)
            self.assertEqual(set(TeacherAssignment.objects.values_list("pk", flat=True)), assignment_ids)
            self.assertEqual(before, self.graph())

    def test_existing_vacant_capacity_is_reused_not_added(self):
        with bypass_rls():
            row = make_row(self.task, self.stack, lecture_total=45, seminar_total=30)
            vacancy = TeacherAssignment.objects.create(organization=self.org, row=row, activity="lecture", hours=45)
            self.restore()
            vacancy.refresh_from_db()
            self.assertEqual(vacancy.teacher_id, self.teacher.pk)
            self.assertEqual(TeachingTaskRow.objects.count(), 1)
            self.assertEqual(TeacherAssignment.objects.count(), 2)

    def test_conflicting_other_teacher_assignment_refuses_without_writes(self):
        with bypass_rls():
            row = make_row(self.task, self.stack, lecture_total=45, seminar_total=30)
            assignment = TeacherAssignment.objects.create(
                organization=self.org, row=row, activity="lecture", hours=45, teacher=self.other
            )
            before = self.graph()
            with self.assertRaisesMessage(WorkloadDenied, "başqa müəllimə"):
                self.restore()
            assignment.refresh_from_db()
            self.assertEqual(assignment.teacher_id, self.other.pk)
            self.assertEqual(before, self.graph())
            self.assertEqual(TeacherAssignment.objects.count(), 1)

    def test_explicit_split_must_equal_existing_contact_and_not_erase_taught_kind(self):
        with bypass_rls():
            for hours in (
                {"lecture": 6, "seminar": 0, "lab": 0},
                {"lecture": 0, "seminar": 75, "lab": 0},
                {"lecture": True, "seminar": 74, "lab": 0},
            ):
                with self.assertRaises(WorkloadDenied):
                    self.restore(hours=hours)
            self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_regular_teacher_cannot_restore_own_load(self):
        with bypass_rls():
            with self.assertRaises(WorkloadDenied):
                self.restore(request=self.request(self.teacher))
            self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_full_view_as_uses_real_authority_readonly_and_limited_do_not(self):
        with bypass_rls():
            for mode in ("readonly", "limited"):
                with self.assertRaises(WorkloadDenied):
                    self.restore(request=self.request(self.teacher, real=self.admin, mode=mode))
            self.assertEqual(
                self.restore(request=self.request(self.teacher, real=self.admin, mode="full"))["status"], "restored"
            )
            self.assertEqual(set(TeacherAssignment.objects.values_list("assigned_by_id", flat=True)), {self.admin.pk})

    def test_other_tenant_offering_and_closed_old_period_refused(self):
        with bypass_rls():
            other_org = make_org("history-restore-foreign")
            with self.assertRaises(WorkloadDenied):
                self.restore(request=self.request(), offering_id=other_org.pk)
            period = self.stack["period"]
            period.is_current = False
            period.save(update_fields=["is_current"])
            with self.assertRaises(WorkloadDenied):
                self.restore()
            self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_anonymous_or_other_authored_history_does_not_supply_current_authority(self):
        with bypass_rls():
            self.lesson.instructor = self.other
            self.lesson.save(update_fields=["instructor"])
            with self.assertRaises(WorkloadDenied):
                self.restore()
            self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_multigroup_patok_row_does_not_expand_restore_to_other_groups(self):
        with bypass_rls():
            row = make_row(self.task, self.stack, lecture_total=45, seminar_total=30)
            other = self.stack["group"].__class__.objects.create(
                organization=self.org,
                name="Other physical group",
                slug="history-restore-other-group",
                unit_type="group",
                parent=self.stack["specialty"],
            )
            row.groups.add(other)
            with self.assertRaisesMessage(WorkloadDenied, "Çoxqruplu"):
                self.restore()
            self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_academic_write_from_unexpected_hook_rolls_back_whole_restore(self):
        original = service.assign_amended

        def corrupted(*args, **kwargs):
            value = original(*args, **kwargs)
            LessonMark.objects.filter(lesson=self.lesson).update(score=9)
            return value

        with bypass_rls():
            before = self.graph()
            with patch.object(service, "assign_amended", side_effect=corrupted), self.assertRaises(WorkloadDenied):
                self.restore()
            self.assertEqual(self.graph(), before)
            self.assertEqual(TeacherAssignment.objects.count(), 0)
            self.assertEqual(TeachingTaskRow.objects.count(), 0)

    def test_form_requires_csrf_and_reason_and_success_redirects_to_existing_journal(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_organization_id"] = str(self.org.pk)
        session.save()
        url = reverse("workload:history_restore", args=[self.offering.pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "csrfmiddlewaretoken")
        response = self.client.post(url, {"chair": self.stack["chair"].pk, **self.hours, "reason": ""})
        self.assertEqual(response.status_code, 200)
        with bypass_rls():
            self.assertEqual(TeacherAssignment.objects.count(), 0)
        response = self.client.post(
            url,
            {
                "chair": self.stack["chair"].pk,
                **self.hours,
                "reason": "Tarixi jurnalın cari yükü təsdiq edilərək bərpa olunur.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("registrar:journal_detail", args=[self.offering.pk]))

    def syllabus_source(self, *, sector="az", other_subject=False):
        from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion

        group = self.stack["group"].__class__.objects.create(
            organization=self.org,
            name="Syllabus source",
            slug="source-" + str(CourseOffering.objects.count()),
            unit_type="group",
            parent=self.stack["specialty"],
            settings={"sector": sector},
        )
        subject = self.stack["subject"]
        if other_subject:
            subject = subject.__class__.objects.create(organization=self.org, code="WRONG", name="Wrong subject")
        course = CourseOffering.objects.create(
            organization=self.org,
            subject=subject,
            period=self.stack["period"],
            group=group,
            instructor=self.teacher,
            lesson_hours=75,
        )
        syllabus = Syllabus.objects.create(
            organization=self.org,
            offering=course,
            subject=subject,
            period=self.stack["period"],
            author=self.teacher,
            chair_unit=self.stack["chair"],
        )
        version = SyllabusVersion.objects.create(
            organization=self.org,
            syllabus=syllabus,
            status="approved",
            locked_at=timezone.now(),
            approval_source="migration",
            plan_hours=self.hours,
            completion_percent=100,
        )
        SyllabusSection.objects.create(
            organization=self.org,
            version=version,
            section_id="week",
            data={"rows": [{"topic": "Genuine source topic", **self.hours}]},
        )
        syllabus.approved_version = version
        syllabus.save(update_fields=["approved_version"])
        self.offering.group.settings = {"sector": "az"}
        self.offering.group.save(update_fields=["settings"])
        return syllabus

    def test_unique_exact_approved_source_bound_without_copying_content_or_marks(self):
        from apps.syllabus.models import SyllabusShare, SyllabusVersion
        from core.reviewed_graph import rows

        with bypass_rls():
            source = self.syllabus_source()
            before = digest(rows(source.approved_version.sections.all()))
            versions = SyllabusVersion.objects.count()
            result = self.restore()
            self.assertEqual(result["syllabus_status"], "approved_bound")
            self.assertEqual(SyllabusShare.objects.get(offering=self.offering).syllabus_id, source.pk)
            self.assertEqual(SyllabusVersion.objects.count(), versions)
            self.assertEqual(digest(rows(source.approved_version.sections.all())), before)
            self.assertEqual(LessonMark.objects.get(lesson=self.lesson).score, 8)
            self.assertEqual(self.restore()["syllabus_status"], "already_approved")

    def test_wrong_subject_and_language_never_bound(self):
        from apps.syllabus.models import SyllabusShare

        with bypass_rls():
            self.syllabus_source(other_subject=True)
            self.syllabus_source(sector="en")
            self.assertEqual(self.restore()["syllabus_status"], "missing")
            self.assertFalse(SyllabusShare.objects.filter(offering=self.offering).exists())

    def test_ambiguous_source_requires_explicit_choice_before_any_load_write(self):
        from apps.syllabus.models import SyllabusShare

        with bypass_rls():
            first = self.syllabus_source()
            self.syllabus_source()
            with self.assertRaisesMessage(WorkloadDenied, "Bir neçə"):
                self.restore()
            self.assertEqual(TeacherAssignment.objects.count(), 0)
            self.restore(syllabus_id=str(first.pk))
            self.assertEqual(SyllabusShare.objects.get(offering=self.offering).syllabus_id, first.pk)

    def test_plan_prefill_uses_exact_approved_plan_not_taught_hours(self):
        with bypass_rls():
            self.assertFalse(any(service.previous_plan(self.offering)[0].values()))
            self.syllabus_source()
            self.assertEqual(service.previous_plan(self.offering)[0], self.hours)

    def test_unit_scope_unknown_chair_denies_plan_post_and_action_but_known_chair_works(self):
        from core.constants import RoleScopeType

        with bypass_rls():
            manager = get_user_model().objects.create_user("history_unit_manager")
            activate_member(
                self.org,
                manager,
                "history_unit_manager",
                scope_unit=self.stack["chair"],
                scope_type=RoleScopeType.UNIT,
                permissions=["workload.manage", "workload.distribute"],
            )
            request = self.request(manager)
            self.assertIsNone(self.stack["subject"].chair_unit_id)
            with self.assertRaises(WorkloadDenied):
                service.plan(request, self.offering.pk)
            with self.assertRaises(WorkloadDenied):
                self.restore(request=request)
            self.assertEqual(TeacherAssignment.objects.count(), 0)
            self.stack["subject"].chair_unit = self.stack["chair"]
            self.stack["subject"].save(update_fields=["chair_unit"])
            self.assertTrue(service.plan(request, self.offering.pk)[2])
            self.assertEqual(self.restore(request=request)["status"], "restored")

    def test_unit_scope_unknown_chair_get_is_not_found(self):
        from core.constants import RoleScopeType

        with bypass_rls():
            manager = get_user_model().objects.create_user("history_unit_get_manager")
            activate_member(
                self.org,
                manager,
                "history_unit_get_manager",
                scope_unit=self.stack["chair"],
                scope_type=RoleScopeType.UNIT,
                permissions=["workload.manage", "workload.distribute"],
            )
        self.client.force_login(manager)
        session = self.client.session
        session["active_organization_id"] = str(self.org.pk)
        session.save()
        url = reverse("workload:history_restore", args=[self.offering.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.post(
                url, {"chair": self.stack["chair"].pk, **self.hours, "reason": "Explicit reason"}
            ).status_code,
            404,
        )

    def test_cross_course_syllabus_context_degree_form_credit_mismatch_and_unknown_fail_closed(self):
        from apps.syllabus.public import approved_restore_sources

        with bypass_rls():
            source = self.syllabus_source()
            target_context = service.syllabus_context(self.offering)
            self.assertEqual(target_context, ("bachelor", "full_time", 6))
            for source_context in (
                ("master", "full_time", 6),
                ("bachelor", "part_time", 6),
                ("bachelor", "full_time", 4),
                None,
            ):

                def context(course, source_context=source_context):
                    return target_context if course.pk == self.offering.pk else source_context

                self.assertEqual(approved_restore_sources(self.offering, context_for=context), [])
            self.assertEqual(approved_restore_sources(self.offering), [])
            self.assertEqual(
                [s.pk for s in approved_restore_sources(self.offering, context_for=service.syllabus_context)],
                [source.pk],
            )

    def test_one_click_exact_row_reuses_previous_plan_and_preserves_graph(self):
        with bypass_rls():
            make_row(self.task, self.stack, lecture_total=45, seminar_total=30)
            self.offering.journal_is_current_load = False
            request = self.request(self.teacher, real=self.admin, mode="full")
            service.attach_actions(request, [self.offering])
            self.assertEqual(self.offering.history_load_restore_plan["lecture"], 45)
            self.assertEqual(self.offering.history_load_restore_plan["seminar"], 30)
            before = self.graph()
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_organization_id"] = str(self.org.pk)
        session.save()
        response = self.client.post(self.offering.history_load_restore_url, self.offering.history_load_restore_plan)
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            self.assertEqual(self.graph(), before)
            self.assertEqual(TeacherAssignment.objects.count(), 2)

    def test_one_click_never_splits_a_patok_or_invents_plan_from_taught_hours(self):
        with bypass_rls():
            self.offering.journal_is_current_load = False
            request = self.request(self.teacher, real=self.admin, mode="full")
            service.attach_actions(request, [self.offering])
            self.assertFalse(hasattr(self.offering, "history_load_restore_plan"))
            row = make_row(self.task, self.stack, lecture_total=45, seminar_total=30)
            other = self.stack["group"].__class__.objects.create(
                organization=self.org,
                name="Second patok group",
                slug="patok-source",
                unit_type="group",
                parent=self.stack["specialty"],
            )
            row.groups.add(other)
            service.attach_actions(request, [self.offering])
            self.assertFalse(hasattr(self.offering, "history_load_restore_plan"))
            self.assertEqual(TeachingTaskRow.objects.count(), 1)

    def test_vacant_patok_row_shows_distribution_link_instead_of_a_failing_restore(self):
        with bypass_rls():
            row = make_row(self.task, self.stack, lecture_total=45, seminar_total=60)
            other = self.stack["group"].__class__.objects.create(
                organization=self.org,
                name="Shared lecture group",
                slug="history-restore-shared-lecture",
                unit_type="group",
                parent=self.stack["specialty"],
            )
            row.groups.add(other)
            self.offering.journal_is_current_load = False
            service.attach_actions(self.request(self.teacher, real=self.admin, mode="full"), [self.offering])
            self.assertIsNone(self.offering.history_load_restore_url)
            shared = self.offering.history_load_restore_shared
            self.assertIn("Shared lecture group", shared["groups"])
            self.assertIn(self.stack["group"].name, shared["groups"])
            self.assertIn("section=workload-distribution", shared["url"])
            self.assertIn("row=" + str(row.pk), shared["url"])
            listed = render_to_string("registrar/partials/_journal_history_restore.html", {"offering": self.offering})
            self.assertIn("jl-restore-note", listed)
            self.assertNotIn("jl-restore-btn", listed)
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_organization_id"] = str(self.org.pk)
        session.save()
        page = self.client.get(reverse("workload:history_restore", args=[self.offering.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "history-restore__shared")
        self.assertContains(page, "row=" + str(row.pk))
        self.assertNotContains(page, "data-restore-submit")
        with bypass_rls():
            self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_single_group_restore_keeps_secondary_list_button(self):
        with bypass_rls():
            make_row(self.task, self.stack, lecture_total=45, seminar_total=30)
            self.offering.journal_is_current_load = False
            service.attach_actions(self.request(self.teacher, real=self.admin, mode="full"), [self.offering])
            self.assertFalse(hasattr(self.offering, "history_load_restore_shared"))
            listed = render_to_string("registrar/partials/_journal_history_restore.html", {"offering": self.offering})
            self.assertIn('class="jl-restore-btn"', listed)
            self.assertNotIn("jl-open-btn", listed)

    def test_actual_full_view_as_middleware_post_restores_and_attributes_real_actor(self):
        with bypass_rls():
            make_row(self.task, self.stack, lecture_total=45, seminar_total=30)
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        started = self.client.post(reverse("accounts:view_as_start"), {"user_id": self.teacher.pk, "org": self.org.pk})
        self.assertEqual(started.status_code, 302)
        self.assertIn("view_as_state", self.client.session)
        url = reverse("workload:history_restore", args=[self.offering.pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        response = self.client.post(
            url,
            {
                "chair": self.stack["chair"].pk,
                **self.hours,
                "reason": "Previous exact workload restored by authorized operator.",
            },
        )
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            self.assertEqual(TeacherAssignment.objects.count(), 2)
            self.assertEqual(set(TeacherAssignment.objects.values_list("assigned_by_id", flat=True)), {self.admin.pk})

    def test_restore_validation_is_visible_and_source_labels_are_not_python_dicts(self):
        with bypass_rls():
            self.syllabus_source()
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_organization_id"] = str(self.org.pk)
        session.save()
        url = reverse("workload:history_restore", args=[self.offering.pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'class="form-control"')
        self.assertContains(page, "Mühazirə: 45")
        self.assertNotContains(page, "&#x27;lecture&#x27;")
        self.assertTrue(page.context["restore_form"].initial["reason"])
        response = self.client.post(url, {"chair": self.stack["chair"].pk, **self.hours, "reason": ""})
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, 'href="#id_reason"')
        with bypass_rls():
            self.assertEqual(TeacherAssignment.objects.count(), 0)

    def zero_placeholder(self):
        row = make_row(self.task, self.stack, lecture_total=0, seminar_total=0)
        row.lecture_plan, row.seminar_plan = 45, 30
        row.union_count = row.subgroup_count = 0
        row.save(update_fields=["lecture_plan", "seminar_plan", "union_count", "subgroup_count"])
        return row

    def test_exact_zero_placeholder_restores_same_row_plan_once_and_preserves_journal(self):
        with bypass_rls():
            row = self.zero_placeholder()
            before = self.graph()
            self.assertEqual(service.previous_plan(self.offering)[0], self.hours)
            self.offering.journal_is_current_load = False
            service.attach_actions(self.request(self.teacher, real=self.admin, mode="full"), [self.offering])
            self.assertEqual(self.offering.history_load_restore_plan["lecture"], 45)
            result = self.restore()
            row.refresh_from_db()
            self.assertEqual(result["row_id"], str(row.pk))
            self.assertEqual(
                (row.lecture_total, row.seminar_total, row.union_count, row.subgroup_count), (45, 30, 1, 1)
            )
            self.assertEqual(TeachingTaskRow.objects.count(), 1)
            self.assertEqual(self.graph(), before)
            self.assertEqual(self.restore()["status"], "already_restored")
            self.assertEqual(TeacherAssignment.objects.count(), 2)

    def test_zero_placeholder_does_not_expand_positive_or_noncontact_capacity(self):
        with bypass_rls():
            row = self.zero_placeholder()
            for field, value in (("lecture_total", 1), ("consult_hours", 1), ("union_count", 1), ("subgroup_count", 2)):
                setattr(row, field, value)
                row.save(update_fields=[field])
                with self.assertRaises(WorkloadDenied):
                    self.restore()
                setattr(row, field, 0)
                row.save(update_fields=[field])
            self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_zero_placeholder_requires_its_own_exact_plan_not_operator_invented_split(self):
        with bypass_rls():
            self.zero_placeholder()
            with self.assertRaises(WorkloadDenied):
                self.restore(hours={"lecture": 30, "seminar": 45, "lab": 0})
            self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_zero_placeholder_capacity_and_academic_graph_roll_back_together(self):
        original = service.assign_amended

        def corrupt(**kwargs):
            result = original(**kwargs)
            LessonMark.objects.filter(lesson=self.lesson).update(score=7)
            return result

        with bypass_rls():
            row = self.zero_placeholder()
            before = self.graph()
            with patch.object(service, "assign_amended", side_effect=corrupt), self.assertRaises(WorkloadDenied):
                self.restore()
            row.refresh_from_db()
            self.assertEqual((row.lecture_total, row.seminar_total, row.union_count, row.subgroup_count), (0, 0, 0, 0))
            self.assertEqual(self.graph(), before)
            self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_zero_placeholder_any_existing_assignment_blocks_even_noncontact_or_vacancy(self):
        from types import SimpleNamespace

        from ..services.history_restore_zero_plan import zero_placeholder_plan

        with bypass_rls():
            row = self.zero_placeholder()
            for activity, teacher in (("exam", self.other.pk), ("consult", None), ("lecture", self.teacher.pk)):
                self.assertIsNone(
                    zero_placeholder_plan(
                        row,
                        course=self.offering,
                        group_ids={self.offering.group_id},
                        assignments=[SimpleNamespace(activity=activity, teacher_id=teacher, hours=1)],
                    )
                )
