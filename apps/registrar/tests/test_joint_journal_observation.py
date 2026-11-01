"""Selected-teacher projection stays read-only inside every member's actor scope."""

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import Membership
from apps.registrar.models import JournalShare, Lesson, LessonMark
from apps.registrar.page_contexts import journal_list_context
from apps.workload.tests.factories import activate_member, make_structure
from core.constants import RoleScopeType

from . import test_joint_legacy_contact as fixture

User = get_user_model()


@override_settings(REGISTRAR_JOINT_JOURNAL_UI_ENABLED=True)
class JointJournalObservationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixture.LegacyJointContactTests.setUpTestData.__func__(cls)
        cls.admin = User.objects.create_user("joint-observation-admin")
        activate_member(
            cls.org, cls.admin, "joint-auditor", permissions=["course.view", "journal.correct", "journal.view"]
        )
        cls.viewer = User.objects.create_user("joint-observation-department")
        activate_member(
            cls.org,
            cls.viewer,
            "joint-department-viewer",
            permissions=["course.view", "journal.view"],
            scope_type=RoleScopeType.UNIT,
            scope_unit=cls.stack["chair"],
        )

    def context(self, actor, **params):
        request = RequestFactory().get("/jurnal/", {"year": "", "teacher": str(self.teacher.pk), **params})
        request.user, request.organization = actor, self.org
        request.org_memberships = list(
            Membership.objects.filter(user=actor, organization=self.org, is_active=True).select_related("role")
        )
        request.org_permissions = sorted(
            {permission for membership in request.org_memberships for permission in membership.role.permissions}
        )
        return journal_list_context(actor, request)

    def client_for(self, actor):
        client = Client()
        client.force_login(actor)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def url(self):
        return (
            reverse("registrar:joint_journal", args=[self.row.pk, "lecture"]) + f"?teacher={self.teacher.pk}&observe=1"
        )

    def test_admin_selected_teacher_one38_student_joint_with_readonly_real_link(self):
        fixture.LegacyJointContactTests.lessons(self)
        entries = self.context(self.admin)["offerings"]
        self.assertEqual(len(entries), 3)
        (joint,) = [entry for entry in entries if getattr(entry, "joint_selection", None)]
        self.assertEqual(joint.student_count, 38)
        self.assertEqual(joint.joint_observed_teacher, self.teacher)
        self.assertEqual((joint.journal_own_lessons, joint.journal_own_hours), (1, 2))
        self.assertEqual(joint.journal_entry_url, self.url())
        response = self.client_for(self.admin).get(joint.journal_entry_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["joint_read_only"])
        self.assertEqual(len(response.context["rows"]), 38)
        self.assertNotContains(response, 'name="action" value="save_marks"')
        self.assertNotContains(response, 'name="action" value="add_lesson"')
        self.assertTrue(all(not cell["writable"] for row in response.context["rows"] for cell in row["cells"] if cell))
        self.assertEqual(response.wsgi_request.user.pk, self.admin.pk)
        self.assertEqual(response.context["joint_observed_teacher"].pk, self.teacher.pk)

    def test_department_observer_sees_whole_pair_but_post_never_inherits_teacher_rights(self):
        entries = self.context(self.viewer)["offerings"]
        self.assertEqual(len([entry for entry in entries if getattr(entry, "joint_selection", None)]), 1)
        client = self.client_for(self.viewer)
        response = client.get(self.url())
        self.assertEqual(response.status_code, 200)
        before = list(Lesson.objects.values()), list(LessonMark.objects.values())
        response = client.post(self.url(), {"action": "add_lesson", "topic": "Forbidden", "full_edit": "1"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(before, (list(Lesson.objects.values()), list(LessonMark.objects.values())))
        self.assertEqual(client.post(self.url(), {"action": "save_marks"}).status_code, 403)
        self.assertEqual(self.client_for(self.admin).post(self.url(), {"action": "save_marks"}).status_code, 403)

    def test_only_one_filtered_or_authorized_member_cannot_resurrect_hidden_partner(self):
        filtered = self.context(self.admin, group=str(self.offerings[0].group_id))["offerings"]
        self.assertFalse(any(getattr(entry, "joint_selection", None) for entry in filtered))
        self.assertEqual({entry.pk for entry in filtered}, {self.offerings[0].pk})
        outsider = User.objects.create_user("joint-other-department")
        other = make_structure(self.org, code="JOINT-OTHER")
        activate_member(
            self.org,
            outsider,
            "joint-outsider",
            permissions=["course.view", "journal.view"],
            scope_type=RoleScopeType.UNIT,
            scope_unit=other["chair"],
        )
        self.assertFalse(any(getattr(entry, "joint_selection", None) for entry in self.context(outsider)["offerings"]))
        self.assertEqual(self.client_for(outsider).get(self.url()).status_code, 403)

    def test_partial_kind_and_partial_roster_do_not_expand_to_joint_lecture(self):
        activate_member(
            self.org,
            self.viewer,
            "joint-department-viewer",
            permissions=["course.view", "journal.view", "grade.input"],
            scope_type=RoleScopeType.UNIT,
            scope_unit=self.stack["chair"],
        )
        for offering in self.offerings:
            JournalShare.objects.create(
                organization=self.org, offering=offering, teacher=self.viewer, kinds=["seminar"]
            )
        self.assertFalse(
            any(getattr(entry, "joint_selection", None) for entry in self.context(self.viewer)["offerings"])
        )
        self.assertEqual(self.client_for(self.viewer).get(self.url()).status_code, 403)
        JournalShare.objects.filter(teacher=self.viewer).update(kinds=["lecture"])
        share = JournalShare.objects.filter(teacher=self.viewer).first()
        share.enrollments.add(self.enrollments[0])
        self.assertFalse(
            any(getattr(entry, "joint_selection", None) for entry in self.context(self.viewer)["offerings"])
        )
        self.assertEqual(self.client_for(self.viewer).get(self.url()).status_code, 403)

    def test_central_corrector_without_view_permission_keeps_existing_read_authority(self):
        actor = User.objects.create_user("joint-corrector-only")
        activate_member(self.org, actor, "joint-correction-scope", permissions=["course.view", "journal.correct"])
        self.assertEqual(
            len([entry for entry in self.context(actor)["offerings"] if getattr(entry, "joint_selection", None)]), 1
        )
        self.assertEqual(self.client_for(actor).get(self.url()).status_code, 200)
        self.assertEqual(self.client_for(actor).post(self.url(), {"action": "save_marks"}).status_code, 403)

    def test_scoped_roster_observer_uses_same_per_member_canonical_gate(self):
        actor = User.objects.create_user("joint-roster-observer")
        activate_member(
            self.org,
            actor,
            "joint-roster-scope",
            permissions=["course.view", "journal.roster"],
            scope_type=RoleScopeType.UNIT,
            scope_unit=self.stack["chair"],
        )
        self.assertEqual(
            len([entry for entry in self.context(actor)["offerings"] if getattr(entry, "joint_selection", None)]), 1
        )
        self.assertEqual(self.client_for(actor).get(self.url()).status_code, 200)
        self.assertEqual(self.client_for(actor).post(self.url(), {"action": "save_marks"}).status_code, 403)

    def test_missing_or_invalid_selected_teacher_does_not_create_observer_write_route(self):
        self.assertEqual(
            self.client_for(self.viewer)
            .get(self.url().replace(f"teacher={self.teacher.pk}", "teacher=invalid"))
            .status_code,
            403,
        )
        self.assertEqual(
            self.client_for(self.viewer).get(self.url().replace("observe=1", "observe=0")).status_code, 200
        )
        self.assertEqual(
            self.client_for(self.viewer)
            .post(self.url().replace("observe=1", "observe=0"), {"action": "save_marks"})
            .status_code,
            403,
        )
