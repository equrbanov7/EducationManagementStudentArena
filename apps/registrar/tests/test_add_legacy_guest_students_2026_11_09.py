"""``add_legacy_guest_students_20261109`` — köhnə jurnalda iştirakı olan tələbə alt qrupdan jurnala (sahib 2026-11-09)."""

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.registrar.models import Enrollment
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

User = get_user_model()


class AddLegacyGuestStudentsCommandTests(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.actor = User.objects.create_superuser("lg_actor", "lg_actor@qku.edu.az", "pw")

    def _plan(self, items):
        path = Path(tempfile.mkdtemp()) / "plan.json"
        path.write_text(json.dumps({"format": "legacy-guests/1", "items": items}, ensure_ascii=False))
        return str(path)

    def _call(self, items, *, apply=False):
        out = StringIO()
        call_command(
            "add_legacy_guest_students_20261109",
            org=self.org.slug,
            actor=self.actor.username,
            file=self._plan(items),
            apply=apply,
            stdout=out,
        )
        counts = {}
        for line in out.getvalue().splitlines():
            for part in line.split()[1:]:
                key, _sep, value = part.partition("=")
                counts[key] = value
        return counts

    def _items(self):
        return [
            {
                "offering": str(self.offering.pk),
                "name": f"{self.guest.last_name} {self.guest.first_name}".strip() or "gr_guest",
                "reason": "Köhnə jurnal 4uHKOTrG3i",
            },
            {"offering": str(self.offering.pk), "fin": "ZZZ9999", "name": "Yoxdur Belə"},
            {"offering": "00000000-0000-0000-0000-000000000000", "name": "Kimsə Biri"},
        ]

    def test_dry_run_counts_without_writing(self):
        self._drop_own_history(self.guest)
        self.guest.first_name, self.guest.last_name = "Qonaq", "Tələbə"
        self.guest.save(update_fields=["first_name", "last_name"])
        counts = self._call(self._items())
        self.assertEqual(counts["mode"], "dry_run")
        self.assertEqual(counts["added"], "1")
        self.assertEqual(counts["skip_student_unresolved"], "1")
        self.assertEqual(counts["skip_offering_unknown"], "1")
        with bypass_rls():
            self.assertFalse(
                Enrollment.objects.filter(offering=self.offering, student=self.guest, status="enrolled").exists()
            )

    def test_apply_adds_once_and_refuses_active_own_journal(self):
        self._drop_own_history(self.guest)
        self.guest.first_name, self.guest.last_name = "Qonaq", "Tələbə"
        self.guest.save(update_fields=["first_name", "last_name"])
        # far_student öz Tarix jurnalında aktivdir → birləşmə edilmir, atlanır.
        self.far_student.first_name, self.far_student.last_name = "Uzaq", "Tələbə"
        self.far_student.save(update_fields=["first_name", "last_name"])
        items = self._items() + [{"offering": str(self.offering.pk), "name": "Tələbə Uzaq"}]
        counts = self._call(items, apply=True)
        self.assertEqual(counts["mode"], "apply")
        self.assertEqual(counts["added"], "1")
        self.assertEqual(counts["added_group"], "1")
        self.assertEqual(counts["skip_other_journal_active"], "1")
        with bypass_rls():
            enrollment = Enrollment.objects.get(offering=self.offering, student=self.guest)
            self.assertEqual((enrollment.status, enrollment.source_group_id), ("enrolled", self.group2.pk))
        again = self._call(items, apply=True)
        self.assertEqual(again.get("added", "0"), "0")
        self.assertEqual(again["skip_already_enrolled"], "1")

    def _level_cohort(self):
        """Səviyyə qrupu: Tarix fənni «Xarici dil-1 (Elementary)» olur (qonağın aktiv jurnalı eyni ailədə), yeni
        «Intermediate» fənni ilə səviyyə qrupu yaradılır."""
        from apps.registrar import language_cohorts
        from apps.registrar.models import Subject

        with bypass_rls():
            self.history.name = "Xarici dil-1 (Elementary)"
            self.history.save(update_fields=["name"])
            intermediate = Subject.objects.create(
                organization=self.org, code="LANG-INT", name="Xarici dil-1 (Intermediate)"
            )
            for user in (self.host, self.guest, self.teacher):
                user.profile.organization = self.org
                user.profile.save(update_fields=["organization"])
            return language_cohorts.create_cohort(
                organization=self.org,
                actor=self.coordinator,
                department=self.chair,
                period=self.period,
                subject=intermediate,
                instructor=self.teacher,
                name="Evening English",
                hours=30,
                lecture_hours=0,
                seminar_hours=30,
                lab_hours=0,
                entry_score_max=50,
                pass_threshold=51,
                min_final_exam_score=17,
            )

    def test_level_cohort_adds_only_without_active_level_journal(self):
        cohort = self._level_cohort()
        self.guest.first_name, self.guest.last_name = "Qonaq", "Tələbə"
        self.guest.save(update_fields=["first_name", "last_name"])
        items = [{"offering": str(cohort.offering_id), "name": "Tələbə Qonaq", "reason": "Köhnə jurnal 8v2jO5Imte"}]
        # Qonağın eyni dil ailəsində aktiv jurnalı var (Elementary) → köçürmə inzibati qərardır, yazılmır.
        counts = self._call(items, apply=True)
        self.assertEqual(counts["skip_level_move_needed"], "1")
        self.assertNotIn("added", counts)
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(offering=cohort.offering, student=self.guest).exists())
        # Aktiv səviyyə jurnalı yoxdursa → səviyyə idarəetməsi ilə təmiz əlavə.
        self._drop_own_history(self.guest)
        counts = self._call(items, apply=True)
        self.assertEqual((counts["added"], counts["added_level_cohort"]), ("1", "1"))
        with bypass_rls():
            enrollment = Enrollment.objects.get(offering=cohort.offering, student=self.guest)
            self.assertEqual((enrollment.status, enrollment.source_group_id), ("enrolled", self.group2.pk))
        again = self._call(items, apply=True)
        self.assertEqual(again.get("added", "0"), "0")
        self.assertEqual(again["skip_already_enrolled"], "1")

    def test_refusal_messages_map_to_fixed_codes(self):
        from apps.registrar.management.commands.add_legacy_guest_students_20261109 import refusal_code

        self.assertEqual(refusal_code("Bu tələbə artıq jurnaldadır."), "skip_already_enrolled")
        self.assertEqual(
            refusal_code("Bu tələbənin burada rəsmi köçürmə tarixçəsi var — inzibati yoxlama tələb olunur."),
            "skip_transfer_history",
        )
        self.assertEqual(refusal_code("Əvvəlki əlavənin mənbə qrupu fərqlidir."), "skip_source_group_differs")
        self.assertEqual(refusal_code("Bu semestr bağlıdır — keçmiş dövrün jurnalına …"), "skip_roster_closed")
        self.assertEqual(refusal_code("Tələbənin aktiv akademik qeydi (qrupu) yoxdur."), "skip_no_active_record")
        self.assertEqual(refusal_code("nəsə başqa"), "skip_refused")

    def test_bad_plan_is_refused(self):
        path = Path(tempfile.mkdtemp()) / "plan.json"
        path.write_text(json.dumps({"format": "other/1", "items": []}))
        with self.assertRaises(CommandError):
            call_command(
                "add_legacy_guest_students_20261109", org=self.org.slug, actor=self.actor.username, file=str(path)
            )
