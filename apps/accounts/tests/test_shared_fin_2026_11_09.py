"""Eyni FİN — bir adamın tələbə və işçi hesabı (sahib 2026-11-09, ``apps/accounts/shared_fin.py``).

Kilidlənən qaydalar:

* işçi hesabı məcburi FİN xanasına eyni adlı TƏLƏBƏ hesabının FİN-ini yazanda heç nə yazılmır, «hər iki hesab
  mənimdir?» təsdiqi (``link_offer``) göstərilir; audit yalnız sahə adını saxlayır;
* təsdiq gələndə FİN hər iki hesabda qalır, bağ işçi profilindədir (``fin_shared_with`` = tələbə), qapı bir daha
  dayandırmır;
* eyni ailədən (tələbə ↔ tələbə) və ya fərqli adlı hesab üçün əvvəlki «başqa hesabda qeydə alınıb» imtinası qalır;
* RİM FİN redaktəsi bağlı cütü toqquşma saymır; iki ƏSAS hesabda eyni FİN DB səviyyəsində qadağandır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts import shared_fin
from apps.accounts.models import UserProfile
from apps.accounts.services.profile_completion import AUDIT_REASON_CONFLICT
from apps.accounts.services.rim.policy import RimAccessError
from apps.accounts.services.rim.profile_edit import _assert_fin_available
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "shared-fin"}}
FIN = "5ARZU01"


@override_settings(PROFILE_COMPLETION_ENABLED=True, CACHES=LOCMEM)
class SharedFinTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sf_owner", "sf_owner@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name="SF Univ", slug="sf-univ", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active"
        )
        cls.roles = {}
        for name, level in (("student", 10), ("tutor", 40)):
            cls.roles[name], _ = Role.objects.update_or_create(
                organization=cls.org,
                name=name,
                defaults={
                    "display_name": name,
                    "level": level,
                    "scope_type": RoleScopeType.ORGANIZATION,
                    "permissions": [],
                    "is_active": True,
                },
            )
        cls.student = cls._member("arzu.humbatova", "student", first="Arzu", last="Hümbətova", fin=FIN)
        cls.staff = cls._member("arzu.humbatova.t", "tutor", first="Arzu", last="Humbatova", fin=None)
        cls.other_student = cls._member("arzu.humbatova2", "student", first="Arzu", last="Hümbətova", fin=None)
        cls.stranger = cls._member("leyla.q", "tutor", first="Leyla", last="Quliyeva", fin=None)

    @classmethod
    def _member(cls, username, role, *, first, last, fin):
        user = User.objects.create_user(username, f"{username.replace('.', '_')}@gmail.com", "pw")
        user.first_name, user.last_name = first, last
        user.save(update_fields=["first_name", "last_name"])
        profile = user.profile
        profile.fin = fin
        profile.phone = "+994501112233"
        profile.organization = cls.org
        profile.save(update_fields=["fin", "phone", "organization", "updated_at"])
        Membership.objects.create(
            user=user, organization=cls.org, role=cls.roles[role], is_primary=True, is_active=True
        )
        return user

    def setUp(self):
        self.url = reverse("accounts:complete_profile")

    def test_staff_typing_student_fin_gets_link_offer_without_writing(self):
        self.client.force_login(self.staff)
        response = self.client.post(self.url, {"fin": FIN.lower()})
        self.assertEqual(response.status_code, 200)
        offer = response.context["link_offer"]
        self.assertEqual(offer["holder_name"], "Arzu Hümbətova")
        self.assertIn("tələbə hesabınız", offer["holder_label"])
        self.assertEqual(dict(offer["values"])["fin"], FIN.lower())
        self.assertFalse(response.context["has_errors"])
        self.assertContains(response, 'name="confirm_shared_fin" value="1"')
        self.staff.profile.refresh_from_db()
        self.assertIsNone(self.staff.profile.fin)
        row = AuditLog.objects.get(reason=AUDIT_REASON_CONFLICT, object_id=str(self.staff.pk))
        self.assertEqual((row.changes["fields"], row.changes["outcome"]), (["fin"], "link_offer"))
        self.assertNotIn(FIN, str(row.changes))

    def test_confirm_links_accounts_and_gate_stops_asking(self):
        self.client.force_login(self.staff)
        response = self.client.post(self.url, {"fin": FIN, shared_fin.CONFIRM_FIELD: "1"}, follow=False)
        self.assertEqual(response.status_code, 302)
        staff_profile = UserProfile.objects.get(user=self.staff)
        student_profile = UserProfile.objects.get(user=self.student)
        self.assertEqual((staff_profile.fin, student_profile.fin), (FIN, FIN))
        self.assertEqual(staff_profile.fin_shared_with_id, self.student.pk)
        self.assertIsNotNone(staff_profile.fin_shared_confirmed_at)
        self.assertTrue(staff_profile.fin_self_reported)
        self.assertIsNone(student_profile.fin_shared_with_id)
        self.assertIsNotNone(staff_profile.profile_completed_at)
        self.assertEqual(AuditLog.objects.filter(reason=shared_fin.AUDIT_REASON_LINKED).count(), 2)
        # Bir daha soruşulmur: qapı keçir.
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(shared_fin.linked_user(self.student), self.staff)
        self.assertEqual(shared_fin.linked_student_user(staff_profile.user), self.student)

    def test_student_typing_staff_fin_links_with_link_on_staff_profile(self):
        # Əks istiqamət: FİN əvvəlcə işçi hesabındadır — bağ yenə işçi profilinə qoyulur, tələbə əsas qalır.
        UserProfile.objects.filter(user=self.student).update(fin=None)
        UserProfile.objects.filter(user=self.staff).update(fin=FIN)
        self.client.force_login(self.student)
        response = self.client.post(self.url, {"fin": FIN})
        self.assertEqual(response.status_code, 200)
        self.assertIn("işçi hesabınız", response.context["link_offer"]["holder_label"])
        self.client.post(self.url, {"fin": FIN, shared_fin.CONFIRM_FIELD: "1"})
        staff_profile = UserProfile.objects.get(user=self.staff)
        student_profile = UserProfile.objects.get(user=self.student)
        self.assertEqual((staff_profile.fin, student_profile.fin), (FIN, FIN))
        self.assertEqual(staff_profile.fin_shared_with_id, self.student.pk)
        self.assertIsNone(student_profile.fin_shared_with_id)

    def test_same_family_or_different_name_is_still_a_conflict(self):
        self.client.force_login(self.other_student)  # tələbə ↔ tələbə, eyni ad
        response = self.client.post(self.url, {"fin": FIN})
        self.assertIsNone(response.context["link_offer"])
        self.assertIn("başqa hesabda", response.context["fields"][0]["error"])
        self.client.force_login(self.stranger)  # heyət, fərqli ad
        response = self.client.post(self.url, {"fin": FIN, shared_fin.CONFIRM_FIELD: "1"})
        self.assertIsNone(response.context["link_offer"])
        self.assertIn("başqa hesabda", response.context["fields"][0]["error"])
        self.assertIsNone(UserProfile.objects.get(user=self.stranger).fin)

    def test_rim_fin_edit_accepts_linked_pair_and_db_rejects_second_primary(self):
        shared_fin.link_accounts(self.staff, self.student, fin=FIN)
        _assert_fin_available(FIN, UserProfile.objects.get(user=self.staff))  # bağlı cüt — toqquşma deyil
        _assert_fin_available(FIN, UserProfile.objects.get(user=self.student))
        with self.assertRaises(RimAccessError):
            _assert_fin_available(FIN, UserProfile.objects.get(user=self.stranger))
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserProfile.objects.filter(user=self.stranger).update(fin=FIN)  # ikinci ƏSAS hesab — qadağandır
        self.assertIsNone(shared_fin.link_offer(FIN, self.stranger))
