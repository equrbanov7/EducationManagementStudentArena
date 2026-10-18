"""Alt qrup / kredit paketinin müstəqil yoxlamasından sonrakı düzəlişlər (2026-10-18).

* jurnal modalı («Alt qrupdan tələbə əlavə et», ``journal.roster``) kredit həddi + tutumdan yan keçmir və
  tarixçəyə ``place`` / ``undo`` sətri yazır;
* kredit artırmayan birləşmə (öz jurnalından azad + bura) həddi aşan tələbədə də bloklanmır;
* köhnə ``place`` sətrinin geri götürülməsi sonrakı yerləşdirməni silmir (``superseded``);
* fəndən azad edilmiş tələbə həmin fənnə alt qrupdan yerləşdirilmir (``subject_exempt``);
* açarsız aktorun yüklədiyi fayl oxunmadan imtina olunur.
"""

from __future__ import annotations

from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.organizations.models import Role
from apps.registrar import credit_load, guest_roster, subgroup_documents, subject_exempt
from apps.registrar.models import Enrollment, SubgroupPlacementEvent
from apps.registrar.public import SubgroupPlacementError, place_in_subgroup, undo_subgroup_placement
from apps.registrar.tests.subgroup_base import SubgroupFixture, pdf
from core.constants import RoleScopeType
from core.rls import bypass_rls

REASON = "Dekanlığın təqdimatı əsasında alt qrupa yerləşdirmə"


class _Base(SubgroupFixture, TestCase):
    PREFIX = "sgr"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            roster_role = Role.objects.create(
                organization=cls.org,
                name="sgr_roster",
                display_name="Siyahı (test)",
                level=75,
                scope_type=RoleScopeType.ORGANIZATION,
                permissions=["journal.roster", "unit.view"],
            )
            cls.coordinator = cls._member("sgr_coord", roster_role)

    def place(self, offering=None, **kwargs):
        with bypass_rls():
            return place_in_subgroup(
                student=self.student,
                offering=offering or self.physics_g1,
                document=pdf(),
                actor=kwargs.pop("actor", self.dean),
                reason=REASON,
                **kwargs,
            )

    def modal_add(self, offering=None, **extra):
        offering = offering or self.physics_g1
        payload = {"document": pdf(), "group": str(self.group2.id), "student": str(self.student.id), "reason": "modal"}
        payload.update(extra)
        return self.client_for(self.coordinator).post(
            reverse("registrar:journal_guest_add", args=[offering.id]), payload
        )


class JournalModalGateTest(_Base):
    def test_modal_obeys_credit_limit(self):
        with mock.patch.object(credit_load, "limits", return_value={"base": 10, "with_subgroup": 12}):
            response = self.modal_add()
        self.assertEqual(response.status_code, 409, response.content)
        self.assertFalse(response.json()["ok"])
        with bypass_rls():
            self.assertFalse(
                Enrollment.objects.filter(
                    student=self.student, offering=self.physics_g1, status=Enrollment.Status.ENROLLED
                ).exists()
            )
            self.assertEqual(SubgroupPlacementEvent.objects.count(), 0)

    def test_modal_add_and_remove_write_history(self):
        response = self.modal_add()
        self.assertEqual(response.status_code, 200, response.content)
        enrollment_id = response.json()["enrollment_id"]
        with bypass_rls():
            place = SubgroupPlacementEvent.objects.get(enrollment_id=enrollment_id)
        self.assertEqual(place.kind, "place")
        self.assertEqual(place.details.get("via"), "journal_modal")
        self.assertEqual((place.credits_before, place.credits_after), (10, 16))
        self.assertIsNotNone(place.document_id)

        removed = self.client_for(self.coordinator).post(
            reverse("registrar:journal_guest_remove", args=[self.physics_g1.id]), {"enrollment": enrollment_id}
        )
        self.assertEqual(removed.status_code, 200, removed.content)
        with bypass_rls():
            undo = SubgroupPlacementEvent.objects.get(undoes=place)
        self.assertEqual(undo.kind, "undo")
        self.assertEqual(undo.credits_after, 10)


class MergeNeverBlockedTest(_Base):
    def test_net_zero_merge_passes_even_over_limit(self):
        # Öz planı 10 kredit, hədd 5 — birləşmə krediti dəyişmir, ona görə bloklanmır.
        self.slot(self.own_history, weekday=4)
        with mock.patch.object(credit_load, "limits", return_value={"base": 5, "with_subgroup": 5}):
            result = self.place(self.history_g1, release_source=True)
        self.assertTrue(result["released"])

    def test_adding_credits_over_limit_is_still_refused(self):
        with mock.patch.object(credit_load, "limits", return_value={"base": 5, "with_subgroup": 5}):
            with self.assertRaises(SubgroupPlacementError) as caught:
                self.place()
        self.assertEqual(caught.exception.code, "credit_limit")


class UndoSupersededTest(_Base):
    def test_old_event_cannot_drop_a_newer_placement(self):
        first = self.place()
        with bypass_rls():
            # Servislə (tarixçəsiz) çıxarılıb yenidən yerləşdirilib — eyni qeydiyyat sətri yenidən aktivdir.
            guest_roster.remove_guest_student(
                offering=self.physics_g1, enrollment=first["enrollment"], by_user=self.dean, reason="test"
            )
        second = self.place()
        self.assertEqual(second["enrollment"].pk, first["enrollment"].pk)
        with bypass_rls():
            with self.assertRaises(SubgroupPlacementError) as caught:
                undo_subgroup_placement(
                    event_id=first["event"].pk, actor=self.dean, reason=REASON, organization=self.org
                )
            self.assertEqual(caught.exception.code, "superseded")
            self.assertEqual(Enrollment.objects.get(pk=second["enrollment"].pk).status, Enrollment.Status.ENROLLED)

    def test_database_allows_a_single_undo_per_placement(self):
        placed = self.place()
        with bypass_rls():
            undo_subgroup_placement(event_id=placed["event"].pk, actor=self.dean, reason=REASON, organization=self.org)
            undo = SubgroupPlacementEvent.objects.get(undoes=placed["event"])
            with self.assertRaises(IntegrityError), transaction.atomic():
                SubgroupPlacementEvent.objects.create(
                    organization=self.org,
                    kind="undo",
                    enrollment=undo.enrollment,
                    student=self.student,
                    offering=self.physics_g1,
                    undoes=placed["event"],
                    reason=REASON,
                    actor=self.dean,
                )


class SubjectExemptTest(_Base):
    def test_exempt_subject_cannot_be_placed(self):
        with bypass_rls():
            own_physics = self.physics_g1.__class__.objects.create(
                organization=self.org,
                subject=self.physics,
                period=self.period,
                group=self.group2,
                instructor=self.teacher,
            )
            enrollment = Enrollment.objects.create(organization=self.org, student=self.student, offering=own_physics)
            subject_exempt.exempt_student(
                offering=own_physics, enrollment_id=enrollment.pk, actor=self.coordinator, reason="Azad"
            )
        with self.assertRaises(SubgroupPlacementError) as caught:
            self.place()
        self.assertEqual(caught.exception.code, "subject_exempt")


class KeyCheckedBeforeUploadTest(_Base):
    def test_actor_without_key_is_refused_before_file_is_read(self):
        with mock.patch.object(subgroup_documents, "validate") as validate:
            with self.assertRaises(SubgroupPlacementError) as caught:
                self.place(actor=self.plain)
        self.assertEqual(caught.exception.code, "forbidden")
        validate.assert_not_called()
