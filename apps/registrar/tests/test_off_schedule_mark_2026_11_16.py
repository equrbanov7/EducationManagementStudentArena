"""«Cədvəldən kənar» işarəsi cədvələ uyğun olmayan dərslərə bərpa olunur (sahib 2026-11-16).

Sahib: «dərsdən kənar yazısını dərs cədvəlinə uyğun olmayanda bərpa et; sistemdən yandırıb-söndürmək olsun».

* ``mark_off_schedule_lessons_20261116``: dry-run → apply (paket id + audit + tarixçə) → idempotent → undo;
* cədvələ uyğun dərs, passiv dərs, slotsuz jurnal, artıq işarəli dərs toxunulmur;
* 14.11 təmizləməsinin hələ geri qaytarılmamış dərsi ötürülür (öz səbəbini ``offsched-…`` undo-su verir);
* undo yalnız səbəbi HƏLƏ avtomatik mətn olan dərsi təmizləyir;
* prod-data-ops qeydiyyatı.
"""

from __future__ import annotations

import pathlib
import re
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.audit.models import AuditLog
from apps.registrar import off_schedule_disable_2026_11_14 as cleanup
from apps.registrar import off_schedule_flags
from apps.registrar import off_schedule_mark_2026_11_16 as mark
from apps.registrar.models import Lesson
from apps.registrar.tests.test_journal_lesson_prefill_2026_10_10 import LessonPrefillBase, _t
from core.rls import bypass_rls

User = get_user_model()
WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "off_schedule_mark: "


def _counts(text: str) -> dict:
    counts = {}
    for line in text.splitlines():
        if line.startswith(PREFIX) and "org=" in line:
            counts.update(pair.split("=", 1) for pair in line[len(PREFIX) :].split())
    return counts


class WorkflowTest(SimpleTestCase):
    def test_workflow_runs_the_command_and_keeps_its_summary(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - mark_off_schedule_lessons_20261116\n", text)
        self.assertIn("            mark_off_schedule_lessons_20261116)\n", text)
        self.assertIn('[ "$COMMAND" = "mark_off_schedule_lessons_20261116" ]', text)
        self.assertIn("|off_schedule_mark|", text)
        self.assertIn("^offmark-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$", text)

    def test_batch_id_format(self):
        self.assertRegex(mark.new_batch_id(), r"^offmark-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")


class MarkOffScheduleCommandTest(LessonPrefillBase):
    """Fikstur: ``offering`` cədvəllidir (bu gün 10:10 seminar, 12:00 lab; 13:35 yad jurnalın slotu, 15:15 parklı),
    ``plain`` cədvəlsizdir."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = User.objects.create_superuser("osm_admin", "osm_admin@qku.edu.az", "pw")

    def _run(self, *extra):
        out = StringIO()
        call_command(
            "mark_off_schedule_lessons_20261116", "--org=lp-univ", f"--actor={self.admin.username}", *extra, stdout=out
        )
        return out.getvalue()

    def _reasons(self):
        with bypass_rls():
            return dict(Lesson.objects.values_list("pk", "off_schedule_reason"))

    def test_helper_is_the_inverse_of_stale_lessons(self):
        on = self._lesson(start_time=_t("10:10"))
        off = self._lesson(start_time=_t("13:35"))
        with bypass_rls():
            offering = self._fresh()
            self.assertEqual(off_schedule_flags.unflagged_off_schedule(offering, [on, off]), [off])
            self.assertEqual(off_schedule_flags.unflagged_off_schedule(self._fresh(self.plain), [on, off]), [])

    def test_dry_run_apply_idempotent_and_undo(self):
        on_slot = self._lesson(start_time=_t("10:10"), end_time=_t("11:40"))
        off_slot = self._lesson(start_time=_t("13:35"), end_time=_t("15:05"))  # yad jurnalın saatı
        parked = self._lesson(days_ago=7, start_time=_t("15:15"))  # parklı slot sayılmır
        no_time = self._lesson(days_ago=7)
        passive = self._lesson(start_time=_t("16:50"), is_passive=True)
        flagged = self._lesson(start_time=_t("08:00"), off_schedule_reason="Əvəzetmə")
        no_slots = self._lesson(self.plain, start_time=_t("08:30"))
        before = self._reasons()

        dry = self._run()
        self.assertIn("mode=dry_run step=mark batch=offmark-", dry)
        counts = _counts(dry)
        self.assertEqual(counts["offerings"], "1")
        self.assertEqual(counts["lessons"], "4")
        self.assertEqual(counts["on_schedule"], "1")
        self.assertEqual(counts["off_schedule"], "3")
        self.assertEqual(counts["off_no_time"], "1")
        self.assertEqual(counts["marked"], "3")
        self.assertEqual(counts["passive_skipped"], "1")
        self.assertEqual(counts["no_slots_offerings"], "1")
        self.assertEqual(counts["no_slots_lessons"], "1")
        self.assertEqual(self._reasons(), before)

        applied = self._run("--apply")
        batch = re.search(r"batch=(offmark-\S+)", applied).group(1)
        self.assertEqual(_counts(applied)["marked"], "3")
        reasons = self._reasons()
        for lesson in (off_slot, parked, no_time):
            self.assertEqual(reasons[lesson.pk], mark.AUTO_REASON)
        for lesson in (on_slot, passive, no_slots):
            self.assertEqual(reasons[lesson.pk], "")
        self.assertEqual(reasons[flagged.pk], "Əvəzetmə")
        with bypass_rls():
            entry = AuditLog.objects.get(resource_type=mark.MARKED, new_values__batch=batch)
            self.assertEqual(entry.resource_id, str(self.offering.pk))
            self.assertEqual(set(entry.new_values["lessons"]), {str(off_slot.pk), str(parked.pk), str(no_time.pk)})
            history = AuditLog.objects.get(
                resource_id=str(self.offering.pk), new_values__reason=f"off_schedule_marked:{mark.SOURCE}"
            )
            self.assertIn(mark.AUTO_REASON, history.changes[0]["new"])

        again = _counts(self._run("--apply"))
        self.assertEqual((again["marked"], again["off_schedule"], again["on_schedule"]), ("0", "0", "1"))

        # Müəllim bir dərsin səbəbini öz mətninə dəyişib — undo ona toxunmur.
        with bypass_rls():
            Lesson.objects.filter(pk=parked.pk).update(off_schedule_reason="Kompensasiya dərsi")
        undo_dry = self._run("--undo", f"--batch={batch}")
        self.assertIn("undo_entries=1 undo_cleared=2 undo_changed=1", undo_dry)
        self.assertEqual(self._reasons()[off_slot.pk], mark.AUTO_REASON)
        self._run("--undo", f"--batch={batch}", "--apply")
        reasons = self._reasons()
        self.assertEqual((reasons[off_slot.pk], reasons[no_time.pk]), ("", ""))
        self.assertEqual(reasons[parked.pk], "Kompensasiya dərsi")
        self.assertEqual(reasons[flagged.pk], "Əvəzetmə")
        self.assertIn("undo_cleared=0 undo_changed=3", self._run("--undo", f"--batch={batch}", "--apply"))

    def test_lessons_awaiting_the_offsched_undo_are_left_for_it(self):
        cleared = self._lesson(start_time=_t("13:35"), off_schedule_reason="Kompensasiya dərsi")
        call_command(
            "clear_off_schedule_flags_20261114",
            "--org=lp-univ",
            f"--actor={self.admin.username}",
            "--apply",
            stdout=StringIO(),
        )
        self.assertEqual(self._reasons()[cleared.pk], "")

        counts = _counts(self._run("--apply"))
        self.assertEqual((counts["awaiting_offsched_undo"], counts["marked"]), ("1", "0"))
        self.assertEqual(self._reasons()[cleared.pk], "")

        with bypass_rls():
            batch = AuditLog.objects.get(resource_type=cleanup.CLEARED).new_values["batch"]
        call_command(
            "clear_off_schedule_flags_20261114",
            "--org=lp-univ",
            f"--actor={self.admin.username}",
            "--undo",
            f"--batch={batch}",
            "--apply",
            stdout=StringIO(),
        )
        self.assertEqual(self._reasons()[cleared.pk], "Kompensasiya dərsi")
        counts = _counts(self._run("--apply"))
        self.assertEqual((counts["awaiting_offsched_undo"], counts["marked"]), ("0", "0"))

    def test_bad_arguments_are_refused(self):
        with self.assertRaisesMessage(CommandError, "off_schedule_mark_batch_invalid"):
            self._run("--undo", "--batch=offsched-20261114-101010-abcd")
        with self.assertRaisesMessage(CommandError, "off_schedule_mark_batch_needs_undo"):
            self._run("--batch=offmark-20261116-101010-abcd")
        with self.assertRaisesMessage(CommandError, "off_schedule_mark_organization_unknown"):
            call_command("mark_off_schedule_lessons_20261116", "--org=yox", f"--actor={self.admin.username}")
        with self.assertRaisesMessage(CommandError, "actor_must_be_active_superuser"):
            call_command("mark_off_schedule_lessons_20261116", "--org=lp-univ", "--actor=lp_teacher")


def test_summary_keys_pass_the_workflow_filter():
    """prod-data-ops ``[a-z_]+=`` açarı tələb edir — rəqəmli açar bütün xülasə sətrini gizlədirdi (2026-11-16)."""
    import re as _re

    from apps.registrar.management.commands import mark_off_schedule_lessons_20261116 as command

    assert all(_re.fullmatch(r"[a-z_]+", key) for key in command._COUNT_KEYS)
