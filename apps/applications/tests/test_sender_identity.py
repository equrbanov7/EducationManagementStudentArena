"""Göndərən etiketi: real mənbə, tenant izolyasiyası və sabit sorğu sayı."""

import json

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import UserProfile
from apps.applications.models import Application
from apps.applications.payloads import row_payload
from apps.applications.services import queries
from apps.applications.services.sender_identity import sender_person
from apps.applications.tests.factories import add_member, kind_of, make_org, make_tree, make_user, make_world, unit_of
from apps.applications.views.endpoints import application_detail
from apps.organizations.models import Membership, Organization, Role
from core.rls import apply_rls_request_context, bypass_rls, reset_rls_context

User = get_user_model()


@override_settings(RLS_TRANSACTION_SCOPED=True)
class SenderIdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.world = make_world("sender-card")
        cls.org = cls.world["organization"]
        cls.sender = cls.world["teacher"]
        cls.sender.first_name, cls.sender.last_name = "Səbinə", "Məmmədova"
        cls.sender.save(update_fields=["first_name", "last_name"])
        profile = cls.sender.profile
        profile.organization, profile.patronymic, profile.staff_position = cls.org, "Natiq", "Ştat vəzifəsi"
        profile.save(update_fields=["organization", "patronymic", "staff_position"])
        membership = Membership.objects.get(organization=cls.org, user=cls.sender, role__name="teacher")
        membership.title = "Baş müəllim"
        membership.save(update_fields=["title"])
        cls.membership = membership
        cls.app = cls.create_application(cls.sender, 1)
        cls.foreign = make_org("sender-foreign")
        cls.foreign_tree = make_tree(cls.foreign, "secret")
        add_member(cls.foreign, cls.sender, "foreign_secret_job", scope_unit=cls.foreign_tree["chair"])
        cls.foreign.memberships.filter(user=cls.sender).update(title="Foreign secret title")

    @classmethod
    def create_application(cls, sender, number):
        return Application.objects.create(
            organization=cls.org,
            number=f"MR-{number:06}",
            kind=kind_of(cls.world, "diger"),
            created_by=sender,
            subject="Dərs yükü haqqında müraciət",
            body="Müraciətin məzmunu burada saxlanılır.",
            sender_family="teacher",
            sender_scope_unit=cls.world["tree"]["chair"],
            current_unit=unit_of(cls.world, "rim"),
        )

    def setUp(self):
        apply_rls_request_context(user_id=self.org.owner_id, org_id=self.org.pk, bypass=False)

    def tearDown(self):
        reset_rls_context()

    def application(self):
        return queries.base_queryset(self.org).get(pk=self.app.pk)

    def test_sender_full_name_username_real_position_and_units(self):
        person = sender_person(self.application())
        self.assertEqual(person["name"], "Səbinə Məmmədova Natiq")
        self.assertEqual(person["username"], self.sender.username)
        self.assertEqual(person["position"], "Baş müəllim")
        self.assertEqual(person["chairs"], [self.world["tree"]["chair"].name])
        self.assertEqual(person["schools"], [self.world["tree"]["faculty"].name])
        self.assertNotIn("Foreign secret", json.dumps(person))
        self.assertFalse({"email", "phone", "permissions", "password", "pin"} & set(person))

    def test_foreign_primary_profile_position_and_patronymic_are_not_exposed(self):
        with bypass_rls():
            UserProfile.objects.filter(user=self.sender).update(
                organization=self.foreign,
                patronymic="Foreign secret father",
                staff_position="Foreign secret position",
            )
        person = sender_person(self.application())
        self.assertEqual(person["name"], "Səbinə Məmmədova")
        self.assertEqual(person["position"], "Baş müəllim")
        self.assertNotIn("Foreign secret", json.dumps(person))

    def test_inactive_role_and_membership_do_not_supply_current_position(self):
        Membership.objects.filter(pk=self.membership.pk).update(is_active=False)
        person = sender_person(self.application())
        self.assertEqual(person["position"], "")
        self.assertEqual(person["roles"], [])
        self.assertEqual(person["units"], [self.world["tree"]["chair"].name])
        Membership.objects.filter(pk=self.membership.pk).update(is_active=True)
        Role.objects.filter(pk=self.membership.role_id).update(is_active=False)
        self.assertEqual(sender_person(self.application())["position"], "")

    def test_missing_profile_and_already_included_patronymic_are_safe(self):
        User.objects.filter(pk=self.sender.pk).update(last_name="Məmmədova Natiq")
        self.assertEqual(sender_person(self.application())["name"], "Səbinə Məmmədova Natiq")
        UserProfile.objects.filter(user=self.sender).delete()
        person = sender_person(self.application())
        self.assertEqual(person["name"], "Səbinə Məmmədova Natiq")
        self.assertEqual(person["position"], "Baş müəllim")

    def test_staff_position_fallback_and_multiple_real_roles(self):
        Membership.objects.filter(pk=self.membership.pk).update(title="")
        add_member(self.org, self.sender, "lab_assistant", scope_unit=self.world["tree"]["chair"])
        person = sender_person(self.application())
        self.assertEqual(person["position"], "Ştat vəzifəsi")
        self.assertEqual(len(person["roles"]), 2)
        self.assertEqual(len(person["chairs"]), 1)

    def test_list_serialization_query_count_is_independent_of_sender_count(self):
        def measure():
            org = Organization.objects.get(pk=self.org.pk)
            viewer = User.objects.get(pk=org.owner_id)
            with CaptureQueriesContext(connection) as queries_seen:
                rows = list(queries.list_applications(organization=org, user=viewer, tab="all", stat="all"))
                payloads = [row_payload(app, viewer_is_handler=True) for app in rows]
            return len(queries_seen), payloads

        baseline, _ = measure()
        for number in range(2, 14):
            sender = make_user(f"extra-sender-{number}")
            add_member(self.org, sender, "teacher", scope_unit=self.world["tree"]["chair"])
            self.create_application(sender, number)
        expanded, payloads = measure()
        self.assertEqual(len(payloads), 13)
        self.assertEqual(expanded, baseline)
        self.assertLessEqual(expanded, 6)

    def test_profile_membership_and_unit_reads_are_already_joined(self):
        app = self.application()
        with self.assertNumQueries(0):
            person = sender_person(app)
        self.assertTrue(person["position"])

    def test_unauthorized_or_foreign_application_does_not_serialize_sender(self):
        request = RequestFactory().get("/")
        request.organization, request.user = self.org, self.world["outsider"]
        response = application_detail(request, self.app.pk)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("requester", json.loads(response.content))
        request.organization, request.user = self.foreign, self.foreign.owner
        response = application_detail(request, self.app.pk)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(self.sender.username, response.content.decode())
