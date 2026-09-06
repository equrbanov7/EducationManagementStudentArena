"""Koordinator vizası qapısı — dekan `approve_slice` (QA 2026-09-05 P2-36).

Sahib qərarı: dilim təsdiqindən əvvəl koordinatoru olan ixtisasın sətirləri
baxılmalıdır (`workload.visa_required`, default AÇIQ — bax
`apps/workload/policy.py`). İradlı (`flagged`) sətir isə siyasətdən ASILI
OLMADAN həmişə bağlıdır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import Organization
from core.constants import RoleScopeType

from ..constants import RowReviewStatus, TaskStatus
from ..models import TaskFacultySlice, TeachingTaskRow
from ..services import WorkloadDenied, approve_slice, resolve_actor, review_all, submit_task
from .factories import activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

OFFICE_PERMS = ["workload.view", "workload.manage", "workload.submit"]
COORD_PERMS = ["workload.view", "workload.review"]
DEAN_PERMS = ["workload.view", "workload.approve"]


class VisaGateBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("wvisa")
        cls.stack = make_structure(cls.org, code="WV")
        cls.office = User.objects.create_user("wvisa.office", "wvisa.office@x.test", "pw")
        cls.dean = User.objects.create_user("wvisa.dean", "wvisa.dean@x.test", "pw")
        activate_member(cls.org, cls.office, "teaching_office_head", permissions=OFFICE_PERMS, level=85)
        # Rol adı QƏSDƏN "dean" DEYİL: `workflow.COORDINATOR_ROLES` özü "dean"
        # adını daşıyan üzvləri də əhatə sayır (dekan öz sətrinə viza verə
        # bilər) — `NoCoordinatorCoverageTest`-in "heç bir baxa bilən yoxdur"
        # ssenarisini yoxlaması üçün dekanın rolu bu kataloqdan kənarda olmalıdır.
        activate_member(
            cls.org,
            cls.dean,
            "faculty_dean",
            permissions=DEAN_PERMS,
            scope_unit=cls.stack["faculty"],
            scope_type=RoleScopeType.UNIT,
            level=70,
        )

    def actor(self, user):
        return resolve_actor(user, self.org)

    def submitted_slice(self):
        """Bir sətirli tapşırığı göndərir və onun fakültə dilimini qaytarır."""
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        make_row(task, self.stack)
        submit_task(task=task, actor=self.actor(self.office))
        task.refresh_from_db()
        return task, TaskFacultySlice.objects.get(task=task)


class CoordinatorCoveredTest(VisaGateBase):
    """Ixtisasın koordinatoru VAR — viza qapısı işə düşür."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.coordinator = User.objects.create_user("wvisa.coord", "wvisa.coord@x.test", "pw")
        activate_member(
            cls.org,
            cls.coordinator,
            "program_coordinator",
            permissions=COORD_PERMS,
            scope_unit=cls.stack["specialty"],
            scope_type=RoleScopeType.UNIT,
            level=45,
        )

    def test_pending_row_blocks_the_deans_approval(self):
        """1) Sətir hələ `pending`-dir — dekan `visa_missing` ilə bağlanır."""
        task, slice_obj = self.submitted_slice()
        with self.assertRaises(WorkloadDenied) as ctx:
            approve_slice(slice_obj=slice_obj, actor=self.actor(self.dean))
        self.assertEqual(ctx.exception.code, "workload.visa_missing")
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.SUBMITTED)

    def test_review_all_unblocks_the_approval(self):
        """2) Koordinator `review_all` edəndən sonra dekan sərbəst təsdiqləyir."""
        task, slice_obj = self.submitted_slice()
        review_all(actor=self.actor(self.coordinator))
        result = approve_slice(slice_obj=slice_obj, actor=self.actor(self.dean))
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.APPROVED)
        self.assertEqual(result["slice_status"], "approved")

    def test_flagged_row_blocks_even_with_visa_policy_off(self):
        """3) İrad qapısı siyasətdən ASILI DEYİL — `visa_required=False` olsa belə bağlıdır."""
        task, slice_obj = self.submitted_slice()
        organization = Organization.objects.get(pk=self.org.pk)
        organization.settings = {"workload": {"visa_required": False}}
        organization.save(update_fields=["settings"])

        row = TeachingTaskRow.objects.get(task=task)
        row.review_status = RowReviewStatus.FLAGGED
        row.save(update_fields=["review_status"])

        with self.assertRaises(WorkloadDenied) as ctx:
            approve_slice(slice_obj=slice_obj, actor=self.actor(self.dean))
        self.assertEqual(ctx.exception.code, "workload.rows_flagged")


class NoCoordinatorCoverageTest(VisaGateBase):
    """4) Ixtisasın koordinatoru YOXDUR — əhatə qaydası dekanı kilidləmir.

    Baxa bilən adam olmayan ixtisas üçün viza tələb etmək dilimi əbədi
    kilidləyər (heç kim heç vaxt baxa bilməz) — ona görə əhatəsiz ixtisas
    təsdiqi bloklamır.
    """

    def test_dean_can_approve_without_any_coordinator(self):
        task, slice_obj = self.submitted_slice()
        result = approve_slice(slice_obj=slice_obj, actor=self.actor(self.dean))
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.APPROVED)
        self.assertEqual(result["slice_status"], "approved")
