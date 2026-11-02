"""A second chair's released workload permits scoped reading, not broad access."""

from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.services import people
from apps.organizations.models import Membership
from apps.registrar.models import CourseOffering, Subject
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from core.rls import bypass_rls

from .people_fixture import PeopleFixture


class TeachingChairDirectoryTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.fx = PeopleFixture()
            cls.fx.period.is_current = True
            cls.fx.period.save(update_fields=["is_current"])
            cls.task = TeachingTask.objects.create(
                organization=cls.fx.org,
                chair=cls.fx.kafedra_a1,
                academic_year=cls.fx.period.academic_year,
                status="approved",
            )
            cls.row = TeachingTaskRow.objects.create(
                organization=cls.fx.org,
                task=cls.task,
                period=cls.fx.period,
                subject=cls.fx.offering_a.subject,
                lecture_plan=30,
                lecture_total=30,
            )
            cls.row.groups.add(cls.fx.offering_a.group)
            TeacherAssignment.objects.create(
                organization=cls.fx.org,
                row=cls.row,
                teacher=cls.fx.teacher_b,
                activity="lecture",
                hours=30,
            )
            cls.fx.offering_a.instructor = cls.fx.teacher_b
            cls.fx.offering_a.save(update_fields=["instructor"])
            subject = Subject.objects.create(
                organization=cls.fx.org, code="OTHER-CHAIR", name="Unrelated", chair_unit=cls.fx.kafedra_b1
            )
            cls.other = CourseOffering.objects.create(
                organization=cls.fx.org,
                subject=subject,
                period=cls.fx.period,
                group=cls.fx.offering_a.group,
                instructor=cls.fx.teacher_b,
            )
            # Journal-view permission is a scoped role capability, not a role-name exception.
            role = cls.fx.role_chair
            role.permissions = [*role.permissions, "journal.view"]
            role.save(update_fields=["permissions"])

    def _actor(self):
        request = RequestFactory().get("/")
        request.user, request.organization = self.fx.chair_a1, self.fx.org
        return people.resolve_actor(request)

    def test_primary_other_chair_teacher_visible_without_membership_or_scope_grant(self):
        with bypass_rls():
            before = list(Membership.objects.filter(user=self.fx.teacher_b).values_list("pk", "scope_unit_id"))
            ids = set(people.visible_teachers_qs(self._actor()).values_list("pk", flat=True))
            self.assertIn(self.fx.teacher_b.pk, ids)
            self.assertEqual(
                before, list(Membership.objects.filter(user=self.fx.teacher_b).values_list("pk", "scope_unit_id"))
            )

    def test_draft_and_cancelled_workload_do_not_expand_directory(self):
        with bypass_rls():
            for status in ("draft", "cancelled"):
                TeachingTask.objects.filter(pk=self.task.pk).update(status=status)
                self.assertNotIn(
                    self.fx.teacher_b.pk, people.visible_teachers_qs(self._actor()).values_list("pk", flat=True)
                )

    def test_journal_picker_and_selected_teacher_remain_own_chair_only(self):
        self.client.force_login(self.fx.chair_a1)
        session = self.client.session
        session["active_organization_id"] = str(self.fx.org.pk)
        session.save()
        with bypass_rls():
            response = self.client.get(reverse("registrar:journal_list_teachers"), {"q": self.fx.teacher_b.username})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([r["id"] for r in response.json()["results"]], [str(self.fx.teacher_b.pk)])
            page = self.client.get(reverse("registrar:journal_list"), {"teacher": self.fx.teacher_b.pk})
            self.assertEqual(page.status_code, 200)
            self.assertEqual({o.pk for o in page.context["offerings"]}, {self.fx.offering_a.pk})
            denied = self.client.get(reverse("registrar:journal_detail", args=[self.other.pk]))
            self.assertEqual(denied.status_code, 404)
