"""«Hesabı dayandır» dialoqu — hədəfin statusuna görə mətnlər və «Digər» üçün məcburi səbəb (sahib 2026-10-11).

Kilidlənən qaydalar:

* səbəb kataloqu auditoriyaya görədir: tələbəyə aid səbəb (təhsil haqqı …) müəllim dialoqunda, müəllimə aid
  («İşdən ayrılıb / müqavilə bitib») tələbə dialoqunda çıxmır; hədəf naməlumdursa hamısı;
* dialoq mətnləri: tələbə → «Tələbəyə qeyd …», müəllim → «Müəllimə qeyd …», naməlum → «İstifadəçiyə qeyd …»;
  «Digər» üçün ayrıca, etiketli «Səbəbi yazın» sahəsi var;
* «Digər» seçilib, «Səbəbi yazın» boşdursa server 400 qaytarır (qeyd sahəsi onu əvəz etmir); yazılıbsa
  bloklanan şəxs girişdə məhz o mətni görür;
* blok səhifəsi tələbəyə bal/davamiyyət xatırladır, müəllimə neytral mətn göstərir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, SimpleTestCase
from django.urls import reverse

from apps.accounts.services import account_block_reasons as reasons
from apps.organizations.models import Membership, Role
from core.constants import RoleScopeType
from core.rls import bypass_rls

from .test_people_teacher_unit import _Base as PeopleBase
from .test_people_teacher_unit import _request
from .test_student_services_sections import PASSWORD, StudentServicesBase

User = get_user_model()
PARTIAL = "accounts/profile/sections/people/_block_reason_fields.html"


class CatalogAudienceTest(SimpleTestCase):
    def _codes(self, audience):
        return [option["value"] for option in reasons.form_options(audience)["reasons"]]

    def test_reasons_follow_audience(self):
        student, staff, everyone = self._codes("student"), self._codes("staff"), self._codes("")
        self.assertIn("tuition_debt", student)
        self.assertNotIn("employment_ended", student)
        self.assertIn("employment_ended", staff)
        for code in ("tuition_debt", "academic_leave", "exam_violation"):
            self.assertNotIn(code, staff)
        self.assertEqual(set(everyone), set(reasons.REASONS))
        self.assertIn("other", staff)
        self.assertEqual(reasons.REASONS["employment_ended"][1], "hr")

    def test_other_requires_its_own_text(self):
        with self.assertRaises(reasons.BlockReasonError) as caught:
            reasons.normalize_choice("other", "", "2-ci korpus", other_text="")
        self.assertEqual(caught.exception.code, "other_text_required")
        self.assertEqual(reasons.normalize_choice("other", "", "", other_text="Ərizə ilə")[0], "other")
        # Köhnə çağırış (other_text=None) əvvəlki qaydanı saxlayır: izah qeyddən gözlənilir.
        self.assertEqual(reasons.normalize_choice("other", "", "Otaq 5")[2], "Otaq 5")
        text = reasons.audit_text("other", "Otaq 5", "Ərizə ilə")
        self.assertEqual(reasons.display_reason("other", text), "Ərizə ilə")
        self.assertEqual(reasons.display_reason("tuition_debt", "x"), "Təhsil haqqı üzrə borc")

    def test_partial_texts_follow_audience(self):
        def render(audience):
            return render_to_string(
                PARTIAL,
                {
                    "block_id_prefix": "t",
                    "block_options": reasons.form_options(audience),
                    "block_note_max": reasons.MAX_NOTE_LENGTH,
                },
            )

        student, staff, neutral = render("student"), render("staff"), render("")
        self.assertIn("Tələbəyə qeyd", student)
        self.assertIn("Tələbə istifadəçi adı", student)
        self.assertIn("Müəllimə qeyd", staff)
        self.assertIn("Müəllim istifadəçi adı", staff)
        self.assertNotIn("Tələbə", staff)
        self.assertIn("İstifadəçiyə qeyd", neutral)
        for html in (student, staff, neutral):
            self.assertIn('name="reason_other"', html)
            self.assertIn("Səbəbi yazın", html)
            self.assertIn("data-block-other hidden", html)
        self.assertNotIn('value="tuition_debt"', staff)


class StudentOtherReasonTest(StudentServicesBase):
    """Tələbə reyestri/kataloqu: «Digər» + ayrıca səbəb mətni."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name="block_officer_1011",
            defaults={
                "display_name": "Block officer",
                "level": 80,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": ["people.view_students", "people.manage_status", "student.registry_view"],
                "is_active": True,
            },
        )
        cls.officer = User.objects.create_user("ss_block_officer_1011", "ss_bo_1011@qku.edu.az", PASSWORD)
        Membership.objects.create(user=cls.officer, organization=cls.org, role=role, is_primary=True, is_active=True)

    def _officer(self):
        client = Client()
        client.force_login(self.officer)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _block(self, **payload):
        body = {"action": "block", "user_id": str(self.pupil.pk), **payload}
        return self._officer().post(reverse("accounts:people_action"), body)

    def test_other_without_written_reason_is_rejected_even_with_note(self):
        response = self._block(reason_code="other", contact_note="2-ci korpus", reason_other="")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "other_text_required")
        self.pupil.refresh_from_db()
        self.assertTrue(self.pupil.is_active)

    def test_other_reason_is_shown_to_the_blocked_student(self):
        self.pupil.set_password("Pupil-Pass-2026!")
        self.pupil.save(update_fields=["password"])
        response = self._block(reason_code="other", contact_note="Otaq 7", reason_other="Ərizəsi əsasında")
        self.assertEqual(response.status_code, 200, response.content)
        self.pupil.refresh_from_db()
        self.assertEqual(self.pupil.profile.block_reason, "Digər — Ərizəsi əsasında")

        card = self._officer().get(reverse("accounts:student_registry_card", args=[self.record.pk])).json()
        self.assertEqual(card["account"]["reason"], "Ərizəsi əsasında")

        page = Client().post(
            reverse("accounts:student_login"), {"username": self.pupil.username, "password": "Pupil-Pass-2026!"}
        )
        self.assertEqual(page.status_code, 403)
        html = page.content.decode()
        self.assertIn("Ərizəsi əsasında", html)
        self.assertIn("ballarınız", html)


class TeacherBlockTextsTest(PeopleBase):
    def test_teacher_section_uses_staff_catalog(self):
        from apps.accounts.services import people
        from apps.accounts.views.people.section import build_people_section

        request = _request(self.fx.dean_a, self.fx.org)
        request.session = {}
        with bypass_rls():
            actor = people.resolve_actor(request)
            self.assertTrue(actor.can_manage_status)
            section = build_people_section(request, "teachers")["people_section"]
        codes = [option["value"] for option in section["block_options"]["reasons"]]
        self.assertEqual(section["block_options"]["audience"], "staff")
        self.assertIn("employment_ended", codes)
        self.assertNotIn("tuition_debt", codes)

    def test_blocked_teacher_sees_neutral_page_with_hr_contact(self):
        self._login(self.fx.dean_a)
        response = self._post(
            {"action": "block", "user_id": self.fx.teacher_a.pk, "reason_code": "employment_ended", "contact_code": ""}
        )
        self.assertEqual(response.status_code, 200, response.content)
        teacher = User.objects.get(pk=self.fx.teacher_a.pk)
        self.assertEqual(
            (teacher.profile.block_reason_code, teacher.profile.block_contact_code), ("employment_ended", "hr")
        )

        page = Client().post(reverse("accounts:staff_login"), {"username": teacher.username, "password": "pw"})
        self.assertEqual(page.status_code, 403)
        html = page.content.decode()
        self.assertIn("İşdən ayrılıb / müqavilə bitib", html)
        self.assertIn("Kadrlar şöbəsi", html)
        self.assertIn("Hesabınızdakı məlumatlar silinməyib", html)
        self.assertNotIn("ballarınız", html)
