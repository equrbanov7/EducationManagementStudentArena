"""«Tədqiqat analitikası» (sahib 2026-11-11): 45 saatlıq fənn — 30 mühazirə + 15 seminar, üç qrup bir patok.

Kart: 803/5 BT (45 mühazirə, Kərimov 45), 803/5 Tİ (30 mühazirə + 15 seminar; Kərimov 30 + seminar 1 s),
803/5T(ing) (45 mühazirə, Kərimov 45); sənəd təsdiqlənib (``distributed``), Tİ sətrində düzəliş açıqdır.
Kafedra müdiri UI-dakı sorğularla (``sətir/``, ``bolgu/``, ``patok/axinlar/``) kartı düzəldə bilməlidir.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import OrgUnit
from apps.workload.constants import AmendmentTarget, Season, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTaskRow, WorkloadAmendment
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_org, make_structure, make_task

User = get_user_model()
CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]
AMEND = {"amend_reason": "correction", "amend_note": "45 saat = 30 mühazirə + 15 seminar"}


class TedqiqatBase(TestCase):
    code = "TA"

    @classmethod
    def setUpTestData(cls):
        cls.org = make_org(f"tedqiqat-{cls.code.lower()}")
        cls.stack = make_structure(cls.org, code=cls.code)
        cls.task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.DISTRIBUTED)
        cls.task.distributed_at = timezone.now() - timezone.timedelta(days=2)
        cls.task.save(update_fields=["distributed_at"])
        cls.head = User.objects.create_user(f"{cls.code.lower()}-head")
        activate_member(
            cls.org,
            cls.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        cls.kerimov = User.objects.create_user(f"{cls.code.lower()}-kerimov", first_name="Elçin", last_name="Kərimov")
        activate_member(cls.org, cls.kerimov, "teacher", permissions=TEACHER_PERMS)
        cls.g_bt, cls.g_ti, cls.g_ing = (cls._group(name) for name in ("803/5 BT", "803/5 Tİ", "803/5T(ing)"))
        cls.row_bt = cls._row(cls.g_bt, lecture=45, seminar=0)
        cls.row_ti = cls._row(cls.g_ti, lecture=30, seminar=15)
        cls.row_ing = cls._row(cls.g_ing, lecture=45, seminar=0)
        cls.bt_lecture = cls._assign(cls.row_bt, "lecture", 45)
        cls.ti_lecture = cls._assign(cls.row_ti, "lecture", 30)
        cls.ti_seminar = cls._assign(cls.row_ti, "seminar", 1)
        cls.ing_lecture = cls._assign(cls.row_ing, "lecture", 45)

    @classmethod
    def _group(cls, name):
        return OrgUnit.objects.create(
            organization=cls.org,
            name=f"{cls.code} {name}",
            slug=f"{cls.code.lower()}-{name.lower().replace(' ', '-').replace('/', '-').replace('(', '').replace(')', '')}",
            unit_type=OrgUnitType.GROUP,
            parent=cls.stack["specialty"],
        )

    @classmethod
    def _row(cls, group, *, lecture, seminar):
        row = TeachingTaskRow.objects.create(
            organization=cls.org,
            task=cls.task,
            season=Season.FALL,
            period=cls.stack["period"],
            subject=cls.stack["subject"],
            specialty=cls.stack["specialty"],
            faculty=cls.stack["faculty"],
            lecture_plan=lecture,
            lecture_total=lecture,
            seminar_plan=seminar,
            seminar_total=seminar,
            union_count=1,
            subgroup_count=1,
            credits="3",
            credits_value=3,
            total_hours=lecture + seminar,
        )
        row.groups.set([group])
        return row

    @classmethod
    def _assign(cls, row, activity, hours):
        return TeacherAssignment.objects.create(
            organization=cls.org, row=row, teacher=cls.kerimov, activity=activity, hours=hours
        )

    def setUp(self):
        self.client.force_login(self.head)

    def _post(self, name, payload):
        return self.client.post(reverse(name), data=json.dumps(payload), content_type="application/json")

    def _row_form(self, row, **changes):
        """«Redaktə» modalının göndərdiyi forma (``EMSWorkloadForms.values``)."""
        row.refresh_from_db()
        data = {
            "task_id": str(self.task.pk),
            "row_id": str(row.pk),
            "subject_id": str(row.subject_id),
            "subject_text": row.subject_label,
            "period_id": str(row.period_id),
            "season": row.season,
            "row_kind": row.row_kind,
            "specialty_id": str(row.specialty_id),
            "group_ids": [str(g.pk) for g in row.groups.all()],
            "education_form": row.education_form,
            "degree_level": row.degree_level,
            "student_count": str(row.student_count),
            "union_count": str(row.union_count),
            "subgroup_count": str(row.subgroup_count),
            "credits": row.credits,
            "credits_value": str(row.credits_value),
        }
        for field in (
            "lecture_plan",
            "lecture_total",
            "seminar_plan",
            "seminar_total",
            "lab_plan",
            "lab_total",
            "consult_hours",
            "exam_hours",
            "thesis_hours",
            "postgrad_hours",
            "practice_research_hours",
            "practice_production_hours",
        ):
            data[field] = str(getattr(row, field) or 0)
        data.update({key: str(value) for key, value in changes.items()})
        return data

    @classmethod
    def _open_ti_amendment(cls):
        """Ekrandakı vəziyyət: Tİ sətrində düzəliş açıqdır («Düzəliş açıqdır»), sənəd ``amended``."""
        WorkloadAmendment.objects.create(
            organization=cls.org,
            task=cls.task,
            target_kind=AmendmentTarget.ROW,
            target_id=cls.row_ti.pk,
            reason="correction",
            note="Tİ seminarı",
            made_by=cls.head,
        )
        cls.task.status = TaskStatus.AMENDED
        cls.task.save(update_fields=["status"])

    def _split_row(self, row, assigned_lecture):
        """«Redaktə»: 45 mühazirə → 30 mühazirə + 15 seminar (UI-nin üç addımı)."""
        data = self._row_form(row, lecture_plan=30, lecture_total=30, seminar_plan=15, seminar_total=15)
        response = self._post("workload:row_save", data)
        if response.status_code == 409 and response.json()["error"] == "workload.amendment_required":
            response = self._post("workload:row_save", {**data, **AMEND})
        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertEqual(body["error"], "workload.total_below_assigned")
        # Mesaj HANSI bölgünün neçəyə enəcəyini deyir.
        self.assertIn("Kərimov", body["message"])
        self.assertIn(f"{assigned_lecture} → 30", body["message"])
        response = self._post("workload:row_save", {**data, **AMEND, "shrink_assignments": "1"})
        self.assertEqual(response.status_code, 200, response.content)
        row.refresh_from_db()
        self.assertEqual(
            (row.lecture_plan, row.lecture_total, row.seminar_plan, row.seminar_total, row.total_hours),
            (30, 30, 15, 15, 45),
        )
        self.assertEqual(
            list(TeacherAssignment.objects.filter(row=row, activity="lecture").values_list("teacher_id", "hours")),
            [(self.kerimov.pk, 30)],
        )


class TedqiqatAnalitikasiFlowTests(TedqiqatBase):
    """Ekrandakı kart → sahibin istədiyi nəticə, yalnız UI sorğuları ilə."""

    code = "TF"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._open_ti_amendment()

    def test_chair_fixes_the_card_end_to_end(self):
        # 1) Tİ seminarı: qələm → 1 s → 15 s (Tİ düzəlişin hədəfidir — səbəb soruşulmur).
        payload = {
            "row_id": str(self.row_ti.pk),
            "assignment_id": str(self.ti_seminar.pk),
            "activity": "seminar",
            "teacher_id": str(self.kerimov.pk),
            "hours": "16",
            "groups_note": "",
            "is_hourly_paid": "",
            "group_id": "",
            "sub_number": "",
        }
        response = self._post("workload:assign", payload)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], "workload.hours_exceeded")
        self.assertIn("ən çox 15 saat", response.json()["message"])
        response = self._post("workload:assign", {**payload, "hours": "15"})
        self.assertEqual(response.status_code, 200, response.content)
        self.ti_seminar.refresh_from_db()
        self.assertEqual(self.ti_seminar.hours, 15)

        # 2) Axınları birləşdirmək — saatlar fərqli (45 / 30 / 45): aydın rədd, heç nə yazılmır.
        streams = [{"row_ids": [str(self.row_bt.pk), str(self.row_ti.pk), str(self.row_ing.pk)]}]
        response = self._post("workload:patok_streams", {"task_id": str(self.task.pk), "streams": streams, **AMEND})
        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertEqual(body["error"], "workload.stream_plan_mismatch")
        self.assertIn("803/5 BT — 45 s", body["message"])
        self.assertIn("803/5 Tİ — 30 s", body["message"])
        self.row_ing.refresh_from_db()
        self.assertEqual((self.row_ing.lecture_total, self.row_ing.patok_lead_id), (45, None))

        # 3) BT və ing sətirləri: 45 mühazirə → 30 + 15 (düzəliş + bölgünün azaldılması razılığı).
        self._split_row(self.row_bt, 45)
        self._split_row(self.row_ing, 45)
        self.assertEqual(
            set(
                WorkloadAmendment.objects.filter(task=self.task, target_kind=AmendmentTarget.ROW).values_list(
                    "target_id", flat=True
                )
            ),
            {self.row_bt.pk, self.row_ti.pk, self.row_ing.pk},
        )

        # 4) Bir patok: üç qrup bir axın, mühazirəçi Kərimov — yükə 30 s BİR dəfə.
        streams[0]["teacher_id"] = str(self.kerimov.pk)
        response = self._post("workload:patok_streams", {"task_id": str(self.task.pk), "streams": streams, **AMEND})
        self.assertEqual(response.status_code, 200, response.content)
        for row in (self.row_bt, self.row_ti, self.row_ing):
            row.refresh_from_db()
        self.assertEqual((self.row_bt.lecture_total, self.row_bt.patok_lead_id), (30, None))
        for partner in (self.row_ti, self.row_ing):
            self.assertEqual(
                (partner.lecture_plan, partner.lecture_total, partner.patok_lead_id), (30, 0, self.row_bt.pk)
            )
        lectures = TeacherAssignment.objects.filter(row__task=self.task, activity="lecture")
        self.assertEqual(
            list(lectures.values_list("row_id", "teacher_id", "hours")), [(self.row_bt.pk, self.kerimov.pk, 30)]
        )

        from apps.workload.services.subject_cards import cards_page

        card = cards_page(self.task, limit=10)["cards"][0]
        self.assertEqual(len(card["lecture"]["streams"]), 1)
        self.assertEqual(card["lecture"]["load_hours"], 30)
        self.assertEqual(card["seminar"]["total"], 45)

        # 5) BT və ing seminarları (15 s) — yeni bölgü; sətirlər artıq düzəlişin hədəfidir, səbəb soruşulmur.
        for row in (self.row_bt, self.row_ing):
            response = self._post(
                "workload:assign",
                {"row_id": str(row.pk), "activity": "seminar", "teacher_id": str(self.kerimov.pk), "hours": "15"},
            )
            self.assertEqual(response.status_code, 200, response.content)

        # 6) Bölgü yenidən təsdiqlənir.
        response = self._post("workload:confirm", {"task_id": str(self.task.pk)})
        self.assertEqual(response.status_code, 200, response.content)


class RowSplitDistributedTests(TedqiqatBase):
    """Təsdiqlənmiş (``distributed``) sənəd, açıq düzəliş yoxdur — sətir bölgüsü düzəliş + razılıqla işləyir."""

    code = "TD"

    def test_lowering_lecture_with_one_assignment_names_it_and_shrinks_on_consent(self):
        self._split_row(self.row_bt, 45)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.AMENDED)

    def test_several_assignments_message_lists_each_and_the_latest_is_cut_first(self):
        from apps.workload.services.assigned_floor import below_assigned_message, shrink_plan

        TeacherAssignment.objects.filter(pk=self.bt_lecture.pk).update(hours=25)
        other = User.objects.create_user(f"{self.code.lower()}-other", first_name="Aysel", last_name="Məmmədova")
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row_bt, teacher=other, activity="lecture", hours=20
        )
        self.assertEqual(shrink_plan(self.row_bt.pk, "lecture", 30), [("Aysel Məmmədova", 20, 5)])
        self.assertEqual(
            shrink_plan(self.row_bt.pk, "lecture", 10), [("Aysel Məmmədova", 20, 0), ("Elçin Kərimov", 25, 10)]
        )
        message = below_assigned_message(self.row_bt.pk, "lecture", assigned=45, total=10)
        self.assertIn("Elçin Kərimov 25 s, Aysel Məmmədova 20 s", message)
        self.assertIn("Aysel Məmmədova 20 s silinəcək", message)
        self.assertIn("Elçin Kərimov 25 → 10 s", message)

    def test_unchanged_existing_stream_with_different_plans_can_still_be_saved(self):
        # Köhnə məlumat: Tİ artıq BT-nin tərəfdaşıdır (plan 30 ≠ 45) — eyni axını yenidən saxlamaq bloklanmır.
        TeacherAssignment.objects.filter(pk=self.ti_lecture.pk).delete()
        TeachingTaskRow.objects.filter(pk=self.row_ti.pk).update(
            lecture_total=0, patok_lead=self.row_bt, total_hours=15
        )
        streams = [{"row_ids": [str(self.row_bt.pk), str(self.row_ti.pk)]}, {"row_ids": [str(self.row_ing.pk)]}]
        response = self._post("workload:patok_streams", {"task_id": str(self.task.pk), "streams": streams, **AMEND})
        self.assertEqual(response.status_code, 200, response.content)
