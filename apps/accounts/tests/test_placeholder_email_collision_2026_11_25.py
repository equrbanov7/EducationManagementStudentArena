"""Yer-tutucu e-poçt toqquşması — 2026-11-25 (QA klon).

RİM «Yeni yarat» → Müəllim, FİN-siz və e-poçtsuz → 500 «Əməliyyat alınmadı»:
``ad.soyad`` istifadəçi adı boş idi, amma ``intake.ad.soyad@placeholder.invalid``
adı sonradan dəyişdirilmiş köhnə hesabda qalmışdı → ``accounts_auth_email_canon_uniq``.

Müqavilə:

* bütün yer-tutucu qurucuları (RİM forması, toplu tələbə / müəllim əlavəsi, siyahı /
  yük faylı / köhnə sistem yaradıcıları) ``identity.claim_placeholder_email`` işlədir —
  bazada (kanonik formada) və faylda tutulmuşsa ``<ad>.2@…``, ``<ad>.3@…``;
* mövcud xəbərdarlıqlar qalır;
* qalıq ``IntegrityError`` (yarış) RİM-də 500 yox, ``email`` sahə xətasıdır.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.accounts.identity import claim_placeholder_email
from apps.accounts.models import UserProfile
from apps.accounts.services.rim import create as rim_create
from core.rls import bypass_rls

from .test_rim_account_create import RimCreateBase
from .test_student_intake import student_row
from .test_teacher_intake import _csv, _IntakeBase

User = get_user_model()

DOMAIN = "placeholder.invalid"


class ClaimPlaceholderEmailTest(RimCreateBase):
    def test_free_base_is_returned_as_is(self):
        self.assertEqual(claim_placeholder_email("intake.Free.Name"), "intake.free.name@" + DOMAIN)

    def test_taken_in_db_gets_a_numeric_suffix_case_insensitively(self):
        User.objects.create_user("old.holder", "Intake.Taken.Name@Placeholder.Invalid", "pw")
        User.objects.create_user("old.holder2", "intake.taken.name.2@" + DOMAIN, "pw")
        self.assertEqual(claim_placeholder_email("intake.taken.name"), "intake.taken.name.3@" + DOMAIN)

    def test_taken_set_is_respected_and_updated(self):
        taken = {"intake.abc@" + DOMAIN}
        first = claim_placeholder_email("intake.ABC", taken)
        second = claim_placeholder_email("intake.ABC", taken)
        self.assertEqual([first, second], ["intake.abc.2@" + DOMAIN, "intake.abc.3@" + DOMAIN])
        self.assertIn(second, taken)


class RimCreatePlaceholderCollisionTest(RimCreateBase):
    """Bug-ın özü: köhnə hesab ``intake.rena.demoyeva@…``-ni saxlayır, adı isə başqadır."""

    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.holder = User.objects.create_user("rena.renamed", "intake.rena.demoyeva@" + DOMAIN, "pw")

    def test_teacher_without_fin_and_email_gets_a_unique_placeholder(self):
        result = self.create(
            self.rim, "teacher", fin="", birth_date="", email="", first_name="Rəna", last_name="Demoyeva"
        )
        created = User.objects.get(pk=result["user_id"])
        self.assertEqual(created.username, "rena.demoyeva")
        self.assertEqual(created.email, "intake.rena.demoyeva.2@" + DOMAIN)
        self.assertNotEqual(created.pk, self.holder.pk)
        self.assertTrue(any("placeholder" in text for text in result["warnings"]))
        self.holder.refresh_from_db()
        self.assertEqual(self.holder.email, "intake.rena.demoyeva@" + DOMAIN)

    def test_duplicate_real_email_falls_back_to_a_unique_placeholder(self):
        result = self.create(
            self.rim,
            "teacher",
            fin="",
            birth_date="",
            email=self.teacher.email,
            first_name="Rəna",
            last_name="Demoyeva",
        )
        self.assertEqual(result["email"], "intake.rena.demoyeva.2@" + DOMAIN)

    def test_residual_email_integrity_error_is_a_field_error(self):
        error = IntegrityError('duplicate key value violates unique constraint "accounts_auth_email_canon_uniq"')
        with mock.patch.object(rim_create.intake_create, "create_account", side_effect=error):
            with self.assertRaises(rim_create.RimCreateError) as caught:
                self.create(self.rim, "teacher", fin="", birth_date="", first_name="Rəna", last_name="Demoyeva")
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(caught.exception.reason_code, "email_taken")
        self.assertIn("email", caught.exception.fields)
        # Savepoint geri qaytarıldı — tranzaksiya işləkdir.
        self.assertTrue(User.objects.filter(pk=self.holder.pk).exists())

    def test_other_integrity_errors_still_propagate(self):
        with mock.patch.object(
            rim_create.intake_create, "create_account", side_effect=IntegrityError("some_other_constraint")
        ):
            with self.assertRaises(IntegrityError):
                self.create(self.rim, "teacher", fin="", birth_date="", first_name="Rəna", last_name="Demoyeva")


class StudentIntakePlaceholderCollisionTest(RimCreateBase):
    """Toplu tələbə əlavəsi (FİN açarlı): FİN-i dəyişmiş köhnə hesab ``intake.<fin>@…``-ni saxlayır."""

    def test_apply_uses_a_unique_placeholder(self):
        with bypass_rls():
            User.objects.create_user("old.student", "intake.5ppppp5@" + DOMAIN, "pw")
        response = self.apply(self.rim, [student_row("5PPPPP5", "Rəna", "Demoyeva")])
        payload = response.json()
        self.assertEqual(payload["summary"]["created"], 1, payload)
        with bypass_rls():
            profile = UserProfile.objects.select_related("user").get(fin="5PPPPP5")
        self.assertEqual(profile.user.email, "intake.5ppppp5.2@" + DOMAIN)


class TeacherIntakePlaceholderCollisionTest(_IntakeBase):
    """Toplu müəllim əlavəsi (FİN açarlı) — eyni toqquşma."""

    def test_apply_uses_a_unique_placeholder(self):
        with bypass_rls():
            User.objects.create_user("old.teacher", "intake.abc1299@" + DOMAIN, "pw")
        row = ["ABC1299", "Rəna", "Demoyeva", "", "12.03.1985", "qadın", "", "", "T-299", "", self.chair.name]
        row += ["", "", "", ""]
        response = self._post("teaching_office_head", "accounts:teacher_intake_apply", _csv([row]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["summary"]["created"], 1, response.content)
        with bypass_rls():
            profile = UserProfile.objects.select_related("user").get(fin="ABC1299")
        self.assertEqual(profile.user.email, "intake.abc1299.2@" + DOMAIN)
