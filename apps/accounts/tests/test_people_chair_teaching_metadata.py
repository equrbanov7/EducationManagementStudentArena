"""Chair directory includes staff/hourly affiliations without moving their primary jobs."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.services import people
from apps.accounts.services.people.detail import _teaching_rows
from apps.accounts.services.people.filters import PeopleFilters
from apps.accounts.services.people.page import teaching_block
from apps.accounts.services.people.teaching_offerings import scoped_owned_offerings
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import CourseOffering, JournalShare, Subject
from core.constants import OrgUnitType, RoleScopeType
from core.rls import bypass_rls

from .people_fixture import PeopleFixture, add_membership, make_role


class ChairTeachingMetadataTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.fx = PeopleFixture()
            cls.lab_role = make_role(
                cls.fx.org,
                "lab_assistant",
                level=30,
                scope_type=RoleScopeType.UNIT,
                permissions=["people.view_teachers", "journal.view"],
            )
            cls.lab = get_user_model().objects.create_user("history_lab")
            add_membership(cls.fx.org, cls.lab, cls.lab_role, unit=cls.fx.kafedra_a1)
            cls.roster = []
            cls.primary_ids = []
            for index in range(18):
                teacher = get_user_model().objects.create_user(
                    f"history_roster_{index}", first_name="HistoryRoster", last_name=f"Teacher{index:02}"
                )
                primary = add_membership(
                    cls.fx.org,
                    teacher,
                    cls.fx.role_teacher,
                    unit=cls.fx.kafedra_a1 if index < 8 else cls.fx.kafedra_b1,
                )
                Membership.objects.filter(pk=primary.pk).update(is_primary=True)
                cls.primary_ids.append(primary.pk)
                if index >= 8:
                    add_membership(cls.fx.org, teacher, cls.fx.role_teacher, unit=cls.fx.kafedra_a1)
                cls.roster.append(teacher)
            # Imported tree: specialty/group is a sibling of chairs under faculty.
            specialty = OrgUnit.objects.create(
                organization=cls.fx.org,
                name="Sibling specialty",
                slug="sibling-specialty",
                unit_type=OrgUnitType.SPECIALTY,
                parent=cls.fx.faculty_a,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.fx.org,
                name="Sibling group",
                slug="sibling-group",
                unit_type=OrgUnitType.GROUP,
                parent=specialty,
            )
            own_subject = Subject.objects.create(
                organization=cls.fx.org, code="HISTORY-META", name="Own chair subject", chair_unit=cls.fx.kafedra_a1
            )
            other_subject = Subject.objects.create(
                organization=cls.fx.org, code="OTHER-META", name="Other chair subject", chair_unit=cls.fx.kafedra_b1
            )
            cls.own = CourseOffering.objects.create(
                organization=cls.fx.org,
                subject=own_subject,
                group=cls.group,
                period=cls.fx.period,
                instructor=cls.roster[8],
                lesson_hours=45,
            )
            cls.other = CourseOffering.objects.create(
                organization=cls.fx.org,
                subject=other_subject,
                group=cls.fx.group_a1,  # Inside chair's old group subtree, but foreign teaching chair.
                period=cls.fx.period,
                instructor=cls.roster[8],
                lesson_hours=75,
            )
            cls.share = JournalShare.objects.create(
                organization=cls.fx.org, offering=cls.own, teacher=cls.roster[9], kinds=["seminar"]
            )

    def actor(self, user=None):
        request = RequestFactory().get("/")
        request.user, request.organization = user or self.lab, self.fx.org
        return people.resolve_actor(request)

    def test_all_eight_staff_and_ten_hourly_affiliations_visible_once_without_workload(self):
        with bypass_rls():
            page = people.build_teachers_page(
                actor=self.actor(), filters=PeopleFilters(query="HistoryRoster", page_size=100)
            )
            self.assertEqual(page["total"], 18)
            self.assertEqual({r["id"] for r in page["results"]}, {str(t.pk) for t in self.roster})
            self.assertNotIn(
                self.fx.teacher_b.pk, people.visible_teachers_qs(self.actor()).values_list("pk", flat=True)
            )

    def test_hourly_primary_other_chair_has_own_subject_metadata_not_foreign_group_subject(self):
        with bypass_rls():
            rows = _teaching_rows(self.roster[8], self.actor())
            self.assertEqual([r["subject_code"] for r in rows], ["HISTORY-META"])
            block = teaching_block(self.roster[8], self.actor(), self.fx.org)
            self.assertEqual(block["totals"], {"offerings": 1, "subjects": 1, "groups": 1, "hours": 45})

    def test_primary_jobs_and_memberships_unchanged_by_reads(self):
        with bypass_rls():
            before = list(
                Membership.objects.filter(user__in=self.roster).values_list("pk", "scope_unit_id", "is_primary")
            )
            for target in (self.roster[0], self.roster[8]):
                list(scoped_owned_offerings(target, self.actor()))
            after = list(
                Membership.objects.filter(user__in=self.roster).values_list("pk", "scope_unit_id", "is_primary")
            )
            self.assertEqual(before, after)
            self.assertTrue(Membership.objects.filter(pk=self.primary_ids[8], scope_unit=self.fx.kafedra_b1).exists())

    def test_foreign_chair_filter_cannot_expand_directory_scope(self):
        with bypass_rls():
            page = people.build_teachers_page(
                actor=self.actor(), filters=PeopleFilters(kafedra=str(self.fx.kafedra_b1.pk), page_size=100)
            )
            self.assertEqual(page["total"], 0)

    def test_empty_scope_and_no_people_permission_fail_closed(self):
        with bypass_rls():
            self.assertFalse(scoped_owned_offerings(self.roster[8], self.actor(self.fx.dean_unscoped)).exists())
            self.assertFalse(scoped_owned_offerings(self.roster[8], self.actor(self.fx.teacher_b)).exists())

    def test_faculty_scope_keeps_original_group_tree_rule(self):
        with bypass_rls():
            self.assertEqual(
                set(scoped_owned_offerings(self.roster[8], self.actor(self.fx.dean_a)).values_list("pk", flat=True)),
                {self.own.pk, self.other.pk},
            )

    def test_hourly_active_share_in_journal_picker_without_changing_owner_or_permissions(self):
        self.client.force_login(self.lab)
        session = self.client.session
        session["active_organization_id"] = str(self.fx.org.pk)
        session.save()
        response = self.client.get(reverse("registrar:journal_list_teachers"), {"q": self.roster[9].username})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["id"] for r in response.json()["results"]], [str(self.roster[9].pk)])
        page = self.client.get(reverse("registrar:journal_list"), {"teacher": self.roster[9].pk, "year": ""})
        # Owner 2026-11-04: the teacher filter mirrors roster[9]'s OWN list — an active share with no
        # positive workload and no recorded lessons is neither current load nor history there.
        self.assertTrue(page.context["journal_teacher_mirrored"])
        self.assertEqual(list(page.context["offerings"]), [])
        page = self.client.get(reverse("registrar:journal_list"), {"group": self.own.group_id, "year": ""})
        self.assertIn(self.own.pk, [o.pk for o in page.context["offerings"]])
        with bypass_rls():
            self.own.refresh_from_db()
            self.assertEqual(self.own.instructor_id, self.roster[8].pk)

    def test_zero_journal_affiliation_has_no_fake_journal_picker_option(self):
        self.client.force_login(self.lab)
        session = self.client.session
        session["active_organization_id"] = str(self.fx.org.pk)
        session.save()
        response = self.client.get(reverse("registrar:journal_list_teachers"), {"q": self.roster[17].username})
        self.assertEqual(response.json()["results"], [])
