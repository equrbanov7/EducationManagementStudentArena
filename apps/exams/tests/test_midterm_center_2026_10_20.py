"""Midterm imtahan mərkəzi axını — `/exams/midterm/` (sahib 2026-10-20).

Sahib: «Midterm də Final imtahanı kimidir — orada da URL /midterm olsun. Final imtahanındakı proses,
məsuliyyət və ciddilik nədirsə eynisi. Orada da istifadəçi adı və PIN götürüb imtahana daxil ola bilir.»

* ``MidtermCenterFlowTests`` — `/exams/midterm/` başlığı, istifadəçi adı + kabinet PIN-i → qaydalar → gözləmə
  otağı → nəzarətçi startı → cəhd; cihaz bağlantısı; final ↔ midterm PIN-i səhv ünvanda qəbul olunmur; kabinet /
  ``start_exam`` yolu bağlıdır; final dəyişməyib; sınaq işləyir; mərkəz (monitor, hesabat, PIN axtarışı) midterm-i
  ayrıca etiketlə göstərir; 5 dəqiqəlik nəticə baxışı.
* ``MidtermCenterTransitionTests`` — açar yandırılmazdan əvvəl kabinetdən başlamış midterm cəhdi normal bitir.
* ``MidtermCenterKeyOffTests`` — açar söndürüləndə hər şey əvvəlki kimidir.
* ``MidtermCenterRuntimeKeyTests`` — «Sistem tənzimləmələri» açarı.
"""

from __future__ import annotations

import io
import runpy
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib import messages as django_messages
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import ExamAttempt, ExamRoom, ExamRoomComputer, FinalAttemptDevice, FinalExamTicket
from apps.exams.services.center_exams import (
    active_center_kinds,
    attempt_in_center,
    is_center_exam,
    legacy_open_attempt,
    midterm_via_center,
)
from apps.exams.services.final_center import room_monitor_snapshot, start_room
from apps.exams.services.final_center.device_binding import device_binding_applies
from apps.exams.services.result_release import secure_answer_key_hidden
from apps.exams.tests.option_token_utils import option_value
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import (
    LOCMEM_CACHE,
    PASSWORD,
    User,
    _make_people,
    _student_client,
)
from apps.exams.tests.test_exam_center_policy import _assign_user_to_org
from apps.exams.tests.test_examaccess_2026_10_13 import _make_official, _set_student_pin

MIDTERM_PIN = "51627384"
FINAL_PIN = "73829164"
PC1_IP = "10.2.2.1"
PC2_IP = "10.2.2.2"
CENTER_ON = {"EXAM_MIDTERM_VIA_CENTER": True}
CENTER_OFF = {"EXAM_MIDTERM_VIA_CENTER": False}


class _CenterFixture:
    @classmethod
    def _build(cls, prefix):
        cls.org, cls.teacher, cls.student = _make_people(prefix)
        cls.center = User.objects.create_user(f"{prefix}_center", f"{prefix}_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.midterm = _make_official(cls.org, cls.teacher, f"{prefix.upper()} Midterm", kind="midterm")
        cls.final = _make_official(cls.org, cls.teacher, f"{prefix.upper()} Final")
        for exam in (cls.midterm, cls.final):
            exam.is_public = False
            exam.save(update_fields=["is_public"])
            exam.allowed_users.add(cls.student)
        cls.room = ExamRoom.objects.create(organization=cls.org, name=f"Zal {prefix}", code=f"Z{prefix}", capacity=10)
        cls.pc1 = ExamRoomComputer.objects.create(
            organization=cls.org, room=cls.room, label="PC-1", seat_number=1, mac_address="AA:BB:CC:20:10:01",
            ip_address=PC1_IP,
        )  # fmt: skip
        cls.pc2 = ExamRoomComputer.objects.create(
            organization=cls.org, room=cls.room, label="PC-2", seat_number=2, mac_address="AA:BB:CC:20:10:02",
            ip_address=PC2_IP,
        )  # fmt: skip

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        _set_student_pin(self.midterm, self.student, MIDTERM_PIN)
        _set_student_pin(self.final, self.student, FINAL_PIN)

    # ── köməkçilər ──────────────────────────────────────────────────────────
    def _login(self, url_name, pin, ip=PC1_IP, client=None):
        client = client or Client()
        response = client.post(reverse(url_name), {"username": self.student.username, "pin": pin}, REMOTE_ADDR=ip)
        return client, response

    def _enter_waiting(self, client, url_name="exams:midterm_exam_entry", ip=PC1_IP):
        confirm = client.post(
            reverse(url_name), {"action": "confirm", "accept_rules": "1", "language": ""}, REMOTE_ADDR=ip
        )
        self.assertEqual(confirm.status_code, 302, getattr(confirm, "content", b"")[:300])
        return confirm

    def _start_midterm_in_hall(self):
        client, response = self._login("exams:midterm_exam_entry", MIDTERM_PIN)
        self.assertEqual(response.status_code, 302, getattr(response, "content", b"")[:300])
        self._enter_waiting(client)
        ticket = FinalExamTicket.objects.get(exam=self.midterm, student=self.student)
        start_room(ticket.session, self.center)
        begin = client.post(reverse("exams:final_exam_begin", args=[ticket.pk]), REMOTE_ADDR=PC1_IP)
        self.assertEqual(begin.status_code, 200, begin.content[:300])
        ticket.refresh_from_db()
        take_url = reverse("exams:take_exam", kwargs={"slug": self.midterm.slug, "attempt_id": ticket.attempt_id})
        return client, ticket, ticket.attempt, take_url

    def _finish(self, client, attempt, take_url, ip=PC1_IP):
        question = attempt.answers.order_by("question__order").first().question
        return client.post(
            take_url,
            {
                "submit_action": "finish",
                f"q_{question.id}": option_value(attempt, question.options.get(label="A")),
                "marked_question_ids": "[]",
            },
            REMOTE_ADDR=ip,
        )

    def _cabinet_client(self):
        return _student_client(self.student.username, self.org)


@override_settings(CACHES=LOCMEM_CACHE, **CENTER_ON)
class MidtermCenterFlowTests(_CenterFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build("mc1020")

    def test_single_source_of_truth_includes_midterm_when_key_on(self):
        self.assertTrue(midterm_via_center())
        self.assertEqual(active_center_kinds(), frozenset({"final", "midterm"}))
        self.assertTrue(is_center_exam(self.midterm))
        self.assertTrue(is_center_exam(self.final))

    def test_midterm_entry_page_renders_with_midterm_heading(self):
        response = Client().get(reverse("exams:midterm_exam_entry"), REMOTE_ADDR=PC1_IP)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(reverse("exams:midterm_exam_entry"), "/exams/midterm/")
        self.assertContains(response, "Midterm imtahan girişi")
        self.assertNotContains(response, "Final imtahan girişi")
        self.assertContains(response, 'action="/exams/midterm/"')
        final_page = Client().get(reverse("exams:final_exam_entry"), REMOTE_ADDR=PC1_IP)
        self.assertContains(final_page, "Final imtahan girişi")

    def test_username_and_cabinet_pin_lead_to_rules_waiting_room_supervisor_start_and_attempt(self):
        client, response = self._login("exams:midterm_exam_entry", MIDTERM_PIN)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/exams/midterm/")

        modal = client.get(reverse("exams:midterm_exam_entry"), REMOTE_ADDR=PC1_IP)
        self.assertEqual(modal.status_code, 200)
        self.assertTrue(modal.context["show_gate_modal"])
        self.assertContains(modal, "Midterm imtahanı")
        self.assertContains(modal, "İmtahan qaydaları")

        ticket = FinalExamTicket.objects.get(exam=self.midterm, student=self.student)
        self.assertIsNotNone(ticket.session_id, "zal oturumu avtomatik açılmalıdır")
        self.assertEqual(ticket.session.room_id, self.room.pk)

        confirm = self._enter_waiting(client)
        self.assertEqual(confirm["Location"], reverse("exams:final_exam_waiting", args=[ticket.pk]))
        waiting = client.get(confirm["Location"], REMOTE_ADDR=PC1_IP)
        self.assertEqual(waiting.status_code, 200)
        self.assertContains(waiting, 'data-entry-url="/exams/midterm/"')

        # Nəzarətçi startından ƏVVƏL cəhd yaranmır.
        early = client.post(reverse("exams:final_exam_begin", args=[ticket.pk]), REMOTE_ADDR=PC1_IP)
        self.assertEqual(early.status_code, 409)
        self.assertFalse(ExamAttempt.objects.filter(user=self.student, exam=self.midterm).exists())

        start_room(ticket.session, self.center)
        begin = client.post(reverse("exams:final_exam_begin", args=[ticket.pk]), REMOTE_ADDR=PC1_IP)
        self.assertEqual(begin.status_code, 200, begin.content[:300])
        attempt = ExamAttempt.objects.get(user=self.student, exam=self.midterm)
        self.assertEqual(attempt.room_id, self.room.pk)
        take = client.get(begin.json()["redirect_url"], REMOTE_ADDR=PC1_IP)
        self.assertEqual(take.status_code, 200)
        self.assertContains(take, 'data-center-exam="1"')

    def test_device_binding_applies_to_midterm(self):
        client, _ticket, attempt, take_url = self._start_midterm_in_hall()
        self.assertTrue(device_binding_applies(attempt))
        self.assertEqual(client.get(take_url, REMOTE_ADDR=PC1_IP).status_code, 200)
        self.assertTrue(FinalAttemptDevice.objects.filter(attempt=attempt).exists())

        # Başqa brauzer (adi login, giriş sessiyası yoxdur) cəhdi aça bilmir.
        other = self._cabinet_client()
        self.assertEqual(other.get(take_url, REMOTE_ADDR=PC2_IP).status_code, 403)

    def test_final_pin_is_refused_on_midterm_entry_and_vice_versa(self):
        anon, response = self._login("exams:midterm_exam_entry", FINAL_PIN)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/exams/final/ ünvanından daxil olun")
        self.assertNotIn("_auth_user_id", anon.session)

        anon, response = self._login("exams:final_exam_entry", MIDTERM_PIN)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/exams/midterm/ ünvanından daxil olun")
        self.assertNotIn("_auth_user_id", anon.session)
        self.assertFalse(FinalExamTicket.objects.filter(student=self.student).exists())

    def test_final_flow_is_unaffected(self):
        client, response = self._login("exams:final_exam_entry", FINAL_PIN)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/exams/final/")
        modal = client.get(reverse("exams:final_exam_entry"), REMOTE_ADDR=PC1_IP)
        self.assertContains(modal, "Final imtahanı")
        # Final bileti ilə midterm səhifəsinə gələn öz giriş səhifəsinə qaytarılır.
        bounce = client.get(reverse("exams:midterm_exam_entry"), REMOTE_ADDR=PC1_IP)
        self.assertEqual(bounce.status_code, 302)
        self.assertEqual(bounce["Location"], "/exams/final/")

    def test_cabinet_code_path_and_start_exam_are_blocked_for_students(self):
        cabinet = self._cabinet_client()
        response = cabinet.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": self.midterm.slug, "access_code": MIDTERM_PIN},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            REMOTE_ADDR=PC1_IP,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("/exams/midterm/", response.json()["error"])

        start = cabinet.post(reverse("exams:start_exam", kwargs={"slug": self.midterm.slug}), REMOTE_ADDR=PC1_IP)
        self.assertEqual(start.status_code, 302)
        texts = [str(message) for message in django_messages.get_messages(start.wsgi_request)]
        self.assertTrue(any("/exams/midterm/" in text for text in texts), texts)
        self.assertFalse(ExamAttempt.objects.filter(user=self.student, exam=self.midterm).exists())

    def test_cabinet_card_shows_center_notice_instead_of_start(self):
        from apps.accounts.views._dashboard_helpers.assigned_tasks import _collect_assigned_tasks

        cabinet = self._cabinet_client()
        request = cabinet.get(reverse("accounts:profile"), {"section": "assigned-exams"}).wsgi_request
        items, _counts, _filter = _collect_assigned_tasks(request, filter_type="exams")
        midterm_row = next(row for row in items if row.get("exam_slug") == self.midterm.slug)
        self.assertTrue(midterm_row["is_final"])
        self.assertFalse(midterm_row["exam_requires_code"])
        self.assertEqual(midterm_row["final_entry_url"], "/exams/midterm/")
        self.assertIn("/exams/midterm/", midterm_row["center_notice"])

    def test_teacher_trial_run_still_works(self):
        teacher = _student_client(self.teacher.username, self.org)
        url = reverse("exams:start_exam", kwargs={"slug": self.midterm.slug}) + "?trial=1"
        response = teacher.post(url, {"trial": "1"}, REMOTE_ADDR=PC1_IP)
        self.assertEqual(response.status_code, 302, getattr(response, "content", b"")[:300])
        trial = ExamAttempt.objects.get(user=self.teacher, exam=self.midterm)
        self.assertTrue(trial.is_trial)
        self.assertFalse(device_binding_applies(trial))
        self.assertFalse(attempt_in_center(trial))

    def test_exam_center_lists_midterm_with_kind_label(self):
        hall, ticket, attempt, take_url = self._start_midterm_in_hall()
        self.assertEqual(hall.get(take_url, REMOTE_ADDR=PC1_IP).status_code, 200)  # cihaz bağlanır
        snapshot = room_monitor_snapshot(self.room)
        row = next(row for row in snapshot["students"] if row["student_id"] == self.student.pk)
        self.assertEqual(row["exam_title"], self.midterm.title)
        self.assertEqual(row["exam_kind_label"], "Midterm")

        center = Client()
        center.force_login(self.center)
        session = center.session
        session["active_organization"] = self.org.slug
        session.save()
        reports = center.get(reverse("exams:exam_center_reports"), {"tab": "tickets", "kind": "midterm"})
        self.assertEqual(reports.status_code, 200)
        self.assertEqual([t.pk for t in reports.context["page_obj"]], [ticket.pk])
        finals_only = center.get(reverse("exams:exam_center_reports"), {"tab": "tickets", "kind": "final"})
        self.assertEqual(list(finals_only.context["page_obj"]), [])
        sessions_tab = center.get(reverse("exams:exam_center_reports"), {"tab": "sessions", "kind": "midterm"})
        self.assertEqual([s.pk for s in sessions_tab.context["page_obj"]], [ticket.session_id])

        pins = center.get(reverse("exams:exam_center_student_pins", args=[self.student.pk]))
        self.assertEqual(pins.status_code, 200)
        midterm_items = [item for item in pins.json()["tickets"] if item["exam_title"] == self.midterm.title]
        self.assertEqual(midterm_items[0]["exam_kind_label"], "Midterm")
        self.assertTrue(midterm_items[0]["device_change_url"], "midterm cəhdinin cihazı mərkəzdən dəyişilə bilər")

    def test_center_midterm_result_has_five_minute_review_then_logout(self):
        client, _ticket, attempt, take_url = self._start_midterm_in_hall()
        self.assertEqual(client.get(take_url, REMOTE_ADDR=PC1_IP).status_code, 200)
        finish = self._finish(client, attempt, take_url)
        self.assertEqual(finish.status_code, 302)
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_finished)
        self.assertTrue(attempt_in_center(attempt))
        self.assertFalse(secure_answer_key_hidden(attempt, is_profile_results=False))
        self.assertTrue(secure_answer_key_hidden(attempt, is_profile_results=True))

        result = client.get(finish["Location"], REMOTE_ADDR=PC1_IP)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.context["is_final_exam_result"])
        self.assertEqual(result.context["back_url"], "/exams/midterm/")

        ExamAttempt.objects.filter(pk=attempt.pk).update(finished_at=timezone.now() - timedelta(minutes=6))
        expired = client.get(finish["Location"], REMOTE_ADDR=PC1_IP)
        self.assertEqual(expired.status_code, 302)
        self.assertEqual(expired["Location"], "/exams/midterm/")
        self.assertNotIn("_auth_user_id", client.session)

    def test_prod_probe_prints_midterm_readiness_counts_only(self):
        self.midterm.start_datetime = timezone.now() + timedelta(days=3)
        self.midterm.end_datetime = timezone.now() + timedelta(days=3, hours=2)
        self.midterm.save(update_fields=["start_datetime", "end_datetime"])
        script = Path(settings.BASE_DIR) / "scripts" / "prod_ops" / "exam_activity_probe.py"
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            runpy.run_path(str(script))
        output = buffer.getvalue()
        lines = dict(line.split(": ", 1) for line in output.strip().splitlines())
        self.assertEqual(lines["midterm_active_start_next_14d"], "1")
        self.assertEqual(lines["midterm_next_14d_with_center_tickets"], "0")
        self.assertEqual(lines["midterm_next_14d_students_with_pin"], "1")
        self.assertEqual(lines["exam_hall_registered_computers"], "2")
        self.assertNotIn(self.student.username, output)
        self.assertNotIn(self.midterm.title, output)


@override_settings(CACHES=LOCMEM_CACHE)
class MidtermCenterTransitionTests(_CenterFixture, TestCase):
    """Açar yandırılmazdan ƏVVƏL kabinetdən başlamış midterm cəhdi imtahanın ortasında kəsilmir."""

    @classmethod
    def setUpTestData(cls):
        cls._build("mt1020")

    def _cabinet_attempt(self):
        with self.settings(**CENTER_OFF):
            cabinet = self._cabinet_client()
            response = cabinet.post(
                reverse("exams:exam_code_check"),
                {"exam_slug": self.midterm.slug, "access_code": MIDTERM_PIN},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                REMOTE_ADDR=PC1_IP,
            )
            self.assertEqual(response.status_code, 200, response.content[:300])
            attempt = ExamAttempt.objects.get(user=self.student, exam=self.midterm)
            take_url = reverse("exams:take_exam", kwargs={"slug": self.midterm.slug, "attempt_id": attempt.pk})
            self.assertEqual(cabinet.get(take_url, REMOTE_ADDR=PC1_IP).status_code, 200)
        return cabinet, attempt, take_url

    def test_in_progress_cabinet_attempt_continues_and_finishes_after_key_turns_on(self):
        cabinet, attempt, take_url = self._cabinet_attempt()

        with self.settings(**CENTER_ON):
            self.assertEqual(legacy_open_attempt(self.midterm, self.student), attempt)
            # Kabinetdən (kod yolu) davam — yeni cəhd yaranmır, eyni cəhdə yönləndirir.
            resume = cabinet.post(
                reverse("exams:exam_code_check"),
                {"exam_slug": self.midterm.slug, "access_code": MIDTERM_PIN},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                REMOTE_ADDR=PC1_IP,
            )
            self.assertEqual(resume.status_code, 200, resume.content[:300])
            self.assertIn(f"/attempt/{attempt.pk}/", resume.json()["redirect_url"])
            self.assertEqual(cabinet.get(take_url, REMOTE_ADDR=PC1_IP).status_code, 200)
            # Cabinet card keeps the old (resumable) flow for this student.
            self.assertEqual(
                cabinet.get(reverse("exams:start_exam", kwargs={"slug": self.midterm.slug}), REMOTE_ADDR=PC1_IP)[
                    "Location"
                ],
                take_url,
            )

            finish = self._finish(cabinet, attempt, take_url)
            self.assertEqual(finish.status_code, 302)
            attempt.refresh_from_db()
            self.assertTrue(attempt.is_finished)
            self.assertEqual(ExamAttempt.objects.filter(user=self.student, exam=self.midterm).count(), 1)
            # Köhnə cəhd mərkəz nəticəsi deyil — çıxış/5 dəqiqə qaydası ona tətbiq olunmur.
            self.assertFalse(attempt_in_center(attempt))
            self.assertTrue(secure_answer_key_hidden(attempt, is_profile_results=False))
            result = cabinet.get(finish["Location"], REMOTE_ADDR=PC1_IP)
            self.assertEqual(result.status_code, 200)
            self.assertFalse(result.context["is_final_exam_result"])
            self.assertIn("_auth_user_id", cabinet.session)

            # Bitəndən sonra yeni kabinet cəhdi artıq mümkün deyil.
            self.assertIsNone(legacy_open_attempt(self.midterm, self.student))

    def test_legacy_attempt_is_bound_to_its_current_device_when_key_turns_on(self):
        cabinet, attempt, take_url = self._cabinet_attempt()
        self.assertFalse(FinalAttemptDevice.objects.filter(attempt=attempt).exists())
        with self.settings(**CENTER_ON):
            self.assertEqual(cabinet.get(take_url, REMOTE_ADDR=PC1_IP).status_code, 200)
            self.assertTrue(FinalAttemptDevice.objects.filter(attempt=attempt).exists())
            other = self._cabinet_client()
            blocked = other.get(take_url, REMOTE_ADDR=PC2_IP)
            self.assertEqual(blocked.status_code, 403)
            self.assertContains(blocked, "midterm imtahanı başqa cihazda", status_code=403)


@override_settings(CACHES=LOCMEM_CACHE, **CENTER_OFF)
class MidtermCenterKeyOffTests(_CenterFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build("mo1020")

    def test_key_off_restores_old_cabinet_flow(self):
        self.assertFalse(is_center_exam(self.midterm))
        self.assertEqual(active_center_kinds(), frozenset({"final"}))
        cabinet = self._cabinet_client()
        response = cabinet.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": self.midterm.slug, "access_code": MIDTERM_PIN},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            REMOTE_ADDR=PC1_IP,
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        attempt = ExamAttempt.objects.get(user=self.student, exam=self.midterm)
        self.assertFalse(device_binding_applies(attempt))
        self.assertFalse(attempt_in_center(attempt))

    def test_midterm_entry_page_is_informational_and_midterm_pin_not_accepted_in_hall(self):
        page = Client().get(reverse("exams:midterm_exam_entry"), REMOTE_ADDR=PC1_IP)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "hazırda imtahan mərkəzi vasitəsilə keçirilmir")
        self.assertNotContains(page, 'name="pin"')

        anon, response = self._login("exams:midterm_exam_entry", MIDTERM_PIN)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", anon.session)

        anon, response = self._login("exams:final_exam_entry", MIDTERM_PIN)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "aktiv final imtahanınız yoxdur")
        self.assertNotIn("_auth_user_id", anon.session)
        self.assertFalse(FinalExamTicket.objects.filter(student=self.student).exists())

    def test_final_still_uses_center(self):
        self.assertTrue(is_center_exam(self.final))
        _client, response = self._login("exams:final_exam_entry", FINAL_PIN)
        self.assertEqual(response.status_code, 302)


class MidtermCenterRuntimeKeyTests(TestCase):
    def test_runtime_key_lives_in_exam_group_and_switches_the_flow(self):
        from apps.accounts.runtime_settings_models import RuntimeSetting
        from core import runtime_settings
        from core.runtime_settings_midterm import KEY_MIDTERM_VIA_CENTER

        spec = runtime_settings.SPECS[KEY_MIDTERM_VIA_CENTER]
        self.assertEqual(spec.group, "exam")
        self.assertEqual(spec.kind, "bool")
        self.assertEqual(sum(1 for code, _label in runtime_settings.GROUPS if code == "exam"), 1)

        with override_settings(RUNTIME_SETTINGS_ENABLED=True, **CENTER_ON):
            runtime_settings.invalidate()
            self.assertTrue(midterm_via_center())
            RuntimeSetting.objects.create(key=KEY_MIDTERM_VIA_CENTER, value=False)
            runtime_settings.invalidate()
            self.assertFalse(midterm_via_center())
            self.assertEqual(active_center_kinds(), frozenset({"final"}))
        runtime_settings.invalidate()

    def test_production_settings_default_is_on(self):
        component = Path(settings.BASE_DIR) / "config" / "settings" / "components" / "exam.py"
        self.assertIn(
            'EXAM_MIDTERM_VIA_CENTER = _env_bool_setting("EXAM_MIDTERM_VIA_CENTER", True)',
            component.read_text(encoding="utf-8"),
        )
