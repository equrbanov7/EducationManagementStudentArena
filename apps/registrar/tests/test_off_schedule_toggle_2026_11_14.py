"""«Cədvəldən kənar» işarəsi söndürülə bilir + hamıdan təmizlənir (sahib 2026-11-14, MR-356).

Sahib: «cədvəldən kənar yazısını yığışdır, kimə düşübsə də sil. və onu söndürmək olsun — settings-də söndürüb
yandırmaq»; «dərs cədvəlindəki tarixə görə problem olmasın, heç nəyə məcbur etməsin».

* ``journal.off_schedule_flag`` söndürülü (defolt): cədvələ uyğun olmayan dərs SƏBƏBSİZ açılır, göndərilən səbəb
  yazılmır, köhnəlmiş slot bağı dərsi rədd etmir, modalda səbəb sahəsi yoxdur, grid / «Keçilmiş dərslər» / CSV-də
  işarə yoxdur. Saat həddi qalır.
* Yandırılıbsa köhnə davranış (bax ``test_journal_activation`` / ``test_journal_lesson_prefill_2026_10_10``).
* ``clear_off_schedule_flags_20261114``: dry-run → apply (paket id + audit) → idempotent → undo.
"""

from __future__ import annotations

import re
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import RuntimeSetting
from apps.accounts.services import runtime_settings_admin
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, Role
from apps.registrar import journal_activation
from apps.registrar import lessons_log as lessons_log_service
from apps.registrar import off_schedule_disable_2026_11_14 as cleanup
from apps.registrar.models import Lesson, LessonKind
from apps.registrar.tests.test_journal_lesson_prefill_2026_10_10 import LessonPrefillBase, _t
from core import academic_rules, runtime_settings
from core.constants import OrganizationType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()
REASON = "Kompensasiya dərsi"


class OffScheduleFlagOffTest(LessonPrefillBase):
    """Defolt: işarə söndürülüdür."""

    def test_default_is_off(self):
        self.assertFalse(academic_rules.off_schedule_flag_enabled())
        self.assertFalse(academic_rules.snapshot()["off_schedule_flag"])

    def test_off_slot_lesson_needs_no_reason(self):
        with bypass_rls():
            reason, error = journal_activation.check_manual_lesson(
                self._fresh(), date=self.today.isoformat(), start_time=_t("13:35"), hours=2, raw_reason=""
            )
        self.assertEqual((reason, error), ("", ""))

    def test_hours_cap_still_applies(self):
        with mock.patch.object(journal_activation, "hours_cap_error", return_value="hədd keçilir"):
            with bypass_rls():
                result = journal_activation.check_manual_lesson(
                    self._fresh(), date=self.today.isoformat(), start_time=_t("13:35"), hours=2, raw_reason=""
                )
        self.assertEqual(result, ("", "hədd keçilir"))

    def test_off_slot_lesson_opens_and_posted_reason_is_ignored(self):
        resp = self._add(slot_id="", lesson_kind=LessonKind.LECTURE, lesson_time="13:35|15:05")
        self.assertNotContains(resp, "cədvəldən kənar dərs üçün səbəbi yazın")
        self._add(
            slot_id="",
            lesson_kind=LessonKind.SEMINAR,
            lesson_time="15:15|16:45",
            off_schedule_reason=REASON,
        )
        lessons = self._lessons()
        self.assertEqual([lesson.start_time for lesson in lessons], [_t("13:35"), _t("15:15")])
        self.assertEqual({lesson.off_schedule_reason for lesson in lessons}, {""})

    def test_stale_slot_binding_does_not_refuse_the_lesson(self):
        # Başqa həftə gününün slotu + müəllimin seçdiyi tarix / saat — bağ atılır, dərs əl ilə açılır.
        self._add(slot_id=str(self.other_day.pk), lesson_kind=LessonKind.LECTURE, lesson_time="08:30|10:00")
        (lesson,) = self._lessons()
        self.assertEqual((lesson.date, lesson.start_time, lesson.off_schedule_reason), (self.today, _t("08:30"), ""))

    def test_journal_shows_no_reason_box_and_no_badge(self):
        self._lesson(start_time=_t("13:35"), end_time=_t("15:05"), off_schedule_reason=REASON)
        resp = self._journal(jt="grid")
        self.assertContains(resp, 'data-offsched-flag="0"')
        self.assertNotContains(resp, "data-jd-offsched ")
        self.assertNotContains(resp, 'name="off_schedule_reason"')
        self.assertNotContains(resp, "jd2-th-offsched")
        self.assertNotContains(resp, "is-offsched")
        self.assertNotContains(resp, "cədvəldən kənar:")

    @override_settings(JOURNAL_LESSON_ACTIVATION=True)
    def test_today_strip_lists_no_off_schedule_lessons(self):
        self._lesson(start_time=_t("13:35"), end_time=_t("15:05"))
        resp = self._journal(jt="grid")
        self.assertEqual(resp.context["today_strip"]["extra_lessons"], [])
        self.assertNotContains(resp, "Bu gün cədvəldən kənar açılmış dərs")

    def test_lessons_log_rows_and_csv_drop_the_flag(self):
        lesson = self._lesson(start_time=_t("13:35"), end_time=_t("15:05"), off_schedule_reason=REASON)
        with bypass_rls():
            rows = lessons_log_service.build_rows(Lesson.objects.filter(pk=lesson.pk))
        self.assertEqual((rows[0]["off_schedule"], rows[0]["off_schedule_reason"]), (False, ""))
        csv = lessons_log_service.csv_rows(rows)
        self.assertEqual(len(csv[0]), len(csv[1]))
        self.assertNotIn("Cədvəldən kənar (səbəb)", csv[0])


@override_settings(JOURNAL_OFF_SCHEDULE_FLAG=True)
class OffScheduleFlagOnTest(LessonPrefillBase):
    """Yandırılıbsa köhnə davranış."""

    def test_reason_is_required_and_stored(self):
        resp = self._add(slot_id="", lesson_kind=LessonKind.LECTURE, lesson_time="13:35|15:05")
        self.assertContains(resp, "cədvəldən kənar dərs üçün səbəbi yazın")
        self.assertEqual(self._lessons(), [])
        self._add(slot_id="", lesson_kind=LessonKind.LECTURE, lesson_time="13:35|15:05", off_schedule_reason=REASON)
        (lesson,) = self._lessons()
        self.assertEqual(lesson.off_schedule_reason, REASON)

    def test_journal_has_the_reason_box_and_the_badge(self):
        self._lesson(start_time=_t("13:35"), end_time=_t("15:05"), off_schedule_reason=REASON)
        resp = self._journal(jt="grid")
        self.assertContains(resp, 'data-offsched-flag="1"')
        self.assertContains(resp, 'name="off_schedule_reason"')
        self.assertContains(resp, "jd2-th-offsched")

    def test_stale_slot_binding_is_refused(self):
        resp = self._add(slot_id=str(self.other_day.pk), lesson_kind=LessonKind.LECTURE, lesson_time="08:30|10:00")
        self.assertContains(resp, "tarixində keçirilmir")
        self.assertEqual(self._lessons(), [])


class ClearOffScheduleCommandTest(LessonPrefillBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = User.objects.create_superuser("osd_admin", "osd_admin@qku.edu.az", "pw")

    def _run(self, *extra):
        out = StringIO()
        call_command(
            "clear_off_schedule_flags_20261114", "--org=lp-univ", f"--actor={self.admin.username}", *extra, stdout=out
        )
        return out.getvalue()

    def _reasons(self):
        with bypass_rls():
            return dict(Lesson.objects.values_list("pk", "off_schedule_reason"))

    def test_dry_run_apply_idempotent_and_undo(self):
        flagged = self._lesson(start_time=_t("13:35"), end_time=_t("15:05"), off_schedule_reason=REASON)
        other = self._lesson(self.plain, days_ago=1, start_time=_t("08:30"), off_schedule_reason="Əvəzetmə")
        clean = self._lesson(days_ago=2, start_time=_t("10:10"))
        before = self._reasons()

        dry = self._run()
        self.assertIn("mode=dry_run step=clear", dry)
        self.assertIn("org=lp-univ offerings=2 flagged=2 cleared=2 race_skipped=0", dry)
        self.assertEqual(self._reasons(), before)

        applied = self._run("--apply")
        batch = re.search(r"batch=(offsched-\S+)", applied).group(1)
        self.assertIn("cleared=2", applied)
        self.assertEqual(set(self._reasons().values()), {""})
        with bypass_rls():
            entries = AuditLog.objects.filter(resource_type=cleanup.CLEARED, new_values__batch=batch)
            self.assertEqual(entries.count(), 2)
            saved = {}
            for entry in entries:
                saved.update(entry.new_values["lessons"])
            self.assertEqual(saved, {str(flagged.pk): REASON, str(other.pk): "Əvəzetmə"})
            history = AuditLog.objects.filter(
                resource_id=str(self.offering.pk),
                new_values__reason=f"off_schedule_reevaluated:{cleanup.SOURCE}",
            ).get()
            self.assertIn(REASON, history.changes[0]["old"])

        self.assertIn("offerings=0 flagged=0 cleared=0", self._run("--apply"))

        undo_dry = self._run("--undo", f"--batch={batch}")
        self.assertIn("undo_restored=2", undo_dry)
        self.assertEqual(set(self._reasons().values()), {""})
        self._run("--undo", f"--batch={batch}", "--apply")
        self.assertEqual(self._reasons(), before)
        self.assertEqual(self._reasons()[clean.pk], "")
        self.assertIn("undo_restored=0 undo_already=2", self._run("--undo", f"--batch={batch}", "--apply"))

    def test_bad_arguments_are_refused(self):
        with self.assertRaisesMessage(CommandError, "off_schedule_batch_invalid"):
            self._run("--undo", "--batch=nope")
        with self.assertRaisesMessage(CommandError, "off_schedule_batch_needs_undo"):
            self._run("--batch=offsched-20261114-101010-abcd")
        with self.assertRaisesMessage(CommandError, "off_schedule_organization_unknown"):
            call_command("clear_off_schedule_flags_20261114", "--org=yox", f"--actor={self.admin.username}")
        with self.assertRaisesMessage(CommandError, "actor_must_be_active_superuser"):
            call_command("clear_off_schedule_flags_20261114", "--org=lp-univ", "--actor=lp_teacher")


def test_batch_id_format():
    assert re.match(r"^offsched-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$", cleanup.new_batch_id())


LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "off-schedule"}}


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class OffScheduleSettingPageTest(TestCase):
    """RİM «Sistem tənzimləmələri» → «Elektron jurnal» qrupunda açar; yandırma / söndürmə dərhal oxunur."""

    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("osp_owner", "osp_owner@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name="OSP Univ", slug="osp-univ", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name="ikt_rehber",
            defaults={
                "display_name": "ikt_rehber",
                "level": 95,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": ["semester.view"],
                "is_active": True,
            },
        )
        cls.rim = User.objects.create_user("osp_rim", "osp_rim@qku.edu.az", "pw")
        Membership.objects.create(user=cls.rim, organization=cls.org, role=role, is_primary=True, is_active=True)

    def setUp(self):
        RuntimeSetting.objects.all().delete()
        runtime_settings.invalidate()

    def tearDown(self):
        runtime_settings.invalidate()

    def test_switch_on_and_off(self):
        self.assertFalse(academic_rules.off_schedule_flag_enabled())
        runtime_settings_admin.save_values(actor=self.rim, data={"journal.off_schedule_flag": "1"})
        self.assertTrue(academic_rules.off_schedule_flag_enabled())
        runtime_settings_admin.save_values(actor=self.rim, data={"journal.off_schedule_flag": "0"})
        self.assertFalse(academic_rules.off_schedule_flag_enabled())

    def test_page_renders_the_switch_in_the_journal_group(self):
        client = Client()
        client.force_login(self.rim)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "system-settings"})
        html = client.get(url, {"ss_group": "journal"}).json()["html"]
        self.assertIn('id="ss-journal.off_schedule_flag"', html)
        self.assertIn("Cədvəldən kənar", html)
