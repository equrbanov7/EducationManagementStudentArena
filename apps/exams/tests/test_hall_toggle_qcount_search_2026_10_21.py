"""Sahib 2026-10-21 — üç tələb.

1. ``HallComputerToggle*`` — «Sistem tənzimləmələri» → ``exam.hall_computer_check``: yandırılıbsa (defolt)
   qeydli zal kompüteri / MAC (ARP agenti) / IP siyahısı əvvəlki kimi tətbiq olunur; söndürüləndə universitet
   şəbəkəsindəki istənilən kompüterdən giriş olur, amma kənar şəbəkə yenə rədd edilir, PIN və cihaz bağlantısı
   qalır, qeydli kompüterdə gözləmə otağı/zal monitoru işləməyə davam edir.
2. ``QuestionCount*`` — final 50, midterm 30 (``exam.final_question_count`` / ``exam.midterm_question_count``):
   forma ilkin dəyəri, yeni imtahanda server tərəfi, redaktədə əl ilə yazılmış say qorunur.
3. ``LookupSearch*`` — fənn/qrup axtarışı: söz sırası, bitişik/aralı yazı, «/» və «-», az hərfləri, kod.
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt, ExamRoom, ExamRoomComputer, FinalExamTicket
from apps.exams.services import exam_center_gate
from apps.exams.services.lookup_search import lookup_match, split_tokens
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import LOCMEM_CACHE, PASSWORD, User, _make_people
from apps.exams.tests.test_exam_center_policy import _assign_user_to_org
from apps.exams.tests.test_examaccess_2026_10_13 import _make_official, _set_student_pin
from apps.exams.tests.test_question_submission import _Base as _SubjectBase
from apps.exams.tests.test_w4_wizard_units import _login as _unit_login
from apps.exams.tests.test_w4_wizard_units import _UnitFixture
from core.constants import OrgUnitType
from core.rls import bypass_rls
from core.runtime_settings_exam_center import (
    KEY_FINAL_QUESTION_COUNT,
    KEY_HALL_COMPUTER_CHECK,
    KEY_MIDTERM_QUESTION_COUNT,
    category_question_count,
    hall_computer_check,
)

INTERNAL_NETWORK = {
    "EXAM_FINAL_INTERNAL_ONLY": True,
    "INTERNAL_NETWORKS": ["10.0.0.0/8"],
    "NETWORK_ZONE_TRUST_HEADER": False,
    "RUNTIME_SETTINGS_ENABLED": True,
    "FINAL_EXAM_ALLOWED_IPS": [],
    "EXAM_CLIENT_MAC_RESOLUTION": "off",
}
CABINET_PIN = "59213847"
PC1_IP = "10.1.2.1"
UNREGISTERED_IP = "10.1.2.99"
EXTERNAL_IP = "85.132.9.10"


def _set_runtime(key, value):
    from apps.accounts.runtime_settings_models import RuntimeSetting
    from core import runtime_settings

    RuntimeSetting.objects.update_or_create(key=key, defaults={"value": value})
    runtime_settings.invalidate()


def _clear_runtime():
    from core import runtime_settings

    runtime_settings.invalidate()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Zal kompüteri yoxlaması
# ─────────────────────────────────────────────────────────────────────────────


class HallComputerKeyTests(TestCase):
    def test_keys_live_in_existing_exam_group_with_safe_defaults(self):
        from core import runtime_settings

        for key, kind in (
            (KEY_HALL_COMPUTER_CHECK, "bool"),
            (KEY_FINAL_QUESTION_COUNT, "int"),
            (KEY_MIDTERM_QUESTION_COUNT, "int"),
        ):
            self.assertEqual(runtime_settings.SPECS[key].group, "exam")
            self.assertEqual(runtime_settings.SPECS[key].kind, kind)
        self.assertEqual(sum(1 for code, _label in runtime_settings.GROUPS if code == "exam"), 1)
        spec = runtime_settings.SPECS[KEY_MIDTERM_QUESTION_COUNT]
        self.assertEqual((spec.min, spec.max), (1, 200))
        with override_settings(RUNTIME_SETTINGS_ENABLED=True):
            _clear_runtime()
            self.assertTrue(hall_computer_check())  # defolt: mövcud davranış
            self.assertEqual(category_question_count("final"), 50)
            self.assertEqual(category_question_count("midterm"), 30)
            self.assertIsNone(category_question_count("quiz"))
            _set_runtime(KEY_HALL_COMPUTER_CHECK, False)
            _set_runtime(KEY_MIDTERM_QUESTION_COUNT, 25)
            self.assertFalse(hall_computer_check())
            self.assertEqual(category_question_count("midterm"), 25)
        _clear_runtime()


@override_settings(CACHES=LOCMEM_CACHE, **INTERNAL_NETWORK)
class HallComputerToggleEntryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("hall1021")
        cls.center = User.objects.create_user("hall1021_center", "hall1021_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.exam = _make_official(cls.org, cls.teacher, "HALL1021 Final")
        cls.exam.is_public = False
        cls.exam.save(update_fields=["is_public"])
        cls.exam.allowed_users.add(cls.student)
        cls.room = ExamRoom.objects.create(organization=cls.org, name="Zal 1021", code="Z1021", capacity=10)
        cls.pc1 = ExamRoomComputer.objects.create(
            organization=cls.org,
            room=cls.room,
            label="PC-1",
            seat_number=1,
            mac_address="AA:BB:CC:00:21:01",
            ip_address=PC1_IP,
        )

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        _clear_runtime()
        _set_student_pin(self.exam, self.student, CABINET_PIN)

    def tearDown(self):
        _clear_runtime()

    def _login(self, ip, client=None):
        client = client or Client()
        response = client.post(
            reverse("exams:final_exam_entry"), {"username": self.student.username, "pin": CABINET_PIN}, REMOTE_ADDR=ip
        )
        return client, response

    def _attempt(self):
        return ExamAttempt.objects.filter(exam=self.exam, user=self.student).first()

    # ── yandırılıb (defolt) — əvvəlki davranış ───────────────────────────────

    def test_on_unregistered_computer_is_refused_when_hall_computers_exist(self):
        # 2026-10-21 sərt zal rejimi: qeydsiz kompüter giriş formasına çatmır — 403 xəbərdarlıq səhifəsi.
        _client, response = self._login(UNREGISTERED_IP)
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "exams/student/hall_computer_blocked.html")
        self.assertNotContains(response, 'name="pin"', status_code=403)
        self.assertIsNone(self._attempt())
        self.assertFalse(FinalExamTicket.objects.filter(exam=self.exam, student=self.student).exists())

    def test_on_ip_allowlist_still_blocks_the_entry_page(self):
        with override_settings(FINAL_EXAM_ALLOWED_IPS=["10.9.9.9"]):
            response = Client().get(reverse("exams:final_exam_entry"), REMOTE_ADDR=UNREGISTERED_IP)
        self.assertEqual(response.status_code, 403)

    def test_on_mac_mode_refuses_when_the_mac_cannot_be_resolved(self):
        with (
            override_settings(EXAM_CLIENT_MAC_RESOLUTION="arp_agent"),
            mock.patch.object(exam_center_gate, "resolve_client_mac", return_value=None),
        ):
            _client, response = self._login(PC1_IP)
        # 2026-10-21 sərt zal rejimi: MAC oxunmursa kompüter qeydli sayılmır — 403 xəbərdarlıq.
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "exams/student/hall_computer_blocked.html")
        self.assertIsNone(self._attempt())

    def test_on_registered_computer_goes_to_the_waiting_room_flow(self):
        _client, response = self._login(PC1_IP)
        self.assertEqual(response.status_code, 302)
        ticket = FinalExamTicket.objects.get(exam=self.exam, student=self.student)
        self.assertEqual(ticket.session.room_id, self.room.pk)

    # ── söndürülüb — kompüter/MAC/IP tələbi yoxdur ───────────────────────────

    def test_off_unregistered_internal_computer_enters_and_starts(self):
        _set_runtime(KEY_HALL_COMPUTER_CHECK, False)
        client, response = self._login(UNREGISTERED_IP)
        self.assertEqual(response.status_code, 302, response.content[:300])
        attempt = self._attempt()
        self.assertIsNotNone(attempt)
        take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})
        self.assertEqual(response["Location"], take_url)
        self.assertEqual(client.get(take_url, REMOTE_ADDR=UNREGISTERED_IP).status_code, 200)

    def test_off_device_binding_to_the_first_device_stays(self):
        _set_runtime(KEY_HALL_COMPUTER_CHECK, False)
        client, _response = self._login(UNREGISTERED_IP)
        attempt = self._attempt()
        take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})
        self.assertEqual(client.get(take_url, REMOTE_ADDR=UNREGISTERED_IP).status_code, 200)  # ilk cihaz bağlanır
        other, _ = self._login("10.1.2.98")  # başqa brauzer/kompüter, eyni PIN
        page = other.get(take_url, REMOTE_ADDR="10.1.2.98")
        self.assertEqual(page.status_code, 403)
        self.assertTemplateUsed(page, "exams/student/final_device_blocked.html")

    def test_off_external_network_is_still_refused(self):
        _set_runtime(KEY_HALL_COMPUTER_CHECK, False)
        self.assertEqual(Client().get(reverse("exams:final_exam_entry"), REMOTE_ADDR=EXTERNAL_IP).status_code, 403)
        _client, response = self._login(EXTERNAL_IP)
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self._attempt())

    def test_off_wrong_pin_is_still_refused(self):
        _set_runtime(KEY_HALL_COMPUTER_CHECK, False)
        response = Client().post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": "00000000"},
            REMOTE_ADDR=UNREGISTERED_IP,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self._attempt())

    def test_off_ignores_the_ip_allowlist_and_mac_mode(self):
        _set_runtime(KEY_HALL_COMPUTER_CHECK, False)
        with override_settings(FINAL_EXAM_ALLOWED_IPS=["10.9.9.9"], EXAM_CLIENT_MAC_RESOLUTION="arp_agent"):
            with mock.patch.object(exam_center_gate, "resolve_client_mac", return_value=None):
                self.assertEqual(
                    Client().get(reverse("exams:final_exam_entry"), REMOTE_ADDR=UNREGISTERED_IP).status_code, 200
                )
                _client, response = self._login(UNREGISTERED_IP)
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(self._attempt())

    def test_off_registered_computer_keeps_the_waiting_room_and_room_monitor(self):
        _set_runtime(KEY_HALL_COMPUTER_CHECK, False)
        client, response = self._login(PC1_IP)
        self.assertEqual(response.status_code, 302)
        ticket = FinalExamTicket.objects.get(exam=self.exam, student=self.student)
        self.assertEqual(ticket.session.room_id, self.room.pk)
        confirm = client.post(
            reverse("exams:final_exam_entry"),
            {"action": "confirm", "accept_rules": "1", "language": ""},
            REMOTE_ADDR=PC1_IP,
        )
        self.assertEqual(confirm.status_code, 302)
        self.assertEqual(client.get(confirm["Location"], REMOTE_ADDR=PC1_IP).status_code, 200)
        center = Client()
        center.force_login(self.center)
        session = center.session
        session["active_organization"] = self.org.slug
        session.save()
        monitor = center.get(reverse("exams:exam_center_room_monitor", args=[self.room.pk]))
        self.assertEqual(monitor.status_code, 200)

    def test_off_does_not_ask_the_arp_agent_when_no_computer_is_registered(self):
        _set_runtime(KEY_HALL_COMPUTER_CHECK, False)
        with bypass_rls():
            ExamRoomComputer.objects.filter(organization=self.org).update(is_active=False)
        with (
            override_settings(EXAM_CLIENT_MAC_RESOLUTION="arp_agent"),
            mock.patch.object(exam_center_gate, "urlopen", side_effect=AssertionError("ARP agent must not be called")),
        ):
            _client, response = self._login(UNREGISTERED_IP)
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(self._attempt())


class HallGateFunctionTests(TestCase):
    """Qapı funksiyaları birbaşa: söndürüləndə hamısı «icazə», ``resolve_room_computer`` yalnız məlumat."""

    @classmethod
    def setUpTestData(cls):
        cls.org, _teacher, _student = _make_people("hallfn1021")
        cls.room = ExamRoom.objects.create(organization=cls.org, name="Zal F", code="ZF1021", capacity=5)
        cls.pc = ExamRoomComputer.objects.create(
            organization=cls.org, room=cls.room, label="PC", seat_number=1, mac_address="AA:BB:CC:00:21:09",
            ip_address=PC1_IP,
        )  # fmt: skip

    def _request(self, ip):
        from django.test import RequestFactory

        return RequestFactory().get("/exams/final/", REMOTE_ADDR=ip)

    def tearDown(self):
        _clear_runtime()

    @override_settings(RUNTIME_SETTINGS_ENABLED=True, FINAL_EXAM_ALLOWED_IPS=["10.9.9.9"])
    def test_on_and_off(self):
        _clear_runtime()
        request = self._request(UNREGISTERED_IP)
        self.assertFalse(exam_center_gate.final_exam_access_allowed(request))
        self.assertFalse(exam_center_gate.room_ip_access_allowed(request, self.room))
        self.assertFalse(exam_center_gate.org_computer_access_allowed(request, self.org))
        self.assertEqual(exam_center_gate.resolve_room_computer(self._request(PC1_IP), self.org), (self.room, self.pc))

        _set_runtime(KEY_HALL_COMPUTER_CHECK, False)
        self.assertTrue(exam_center_gate.final_exam_access_allowed(request))
        self.assertTrue(exam_center_gate.room_ip_access_allowed(request, self.room))
        self.assertTrue(exam_center_gate.org_computer_access_allowed(request, self.org))
        self.assertEqual(exam_center_gate.resolve_room_computer(request, self.org), (None, None))
        self.assertEqual(exam_center_gate.resolve_room_computer(self._request(PC1_IP), self.org), (self.room, self.pc))


# ─────────────────────────────────────────────────────────────────────────────
# 2. Kateqoriyaya görə sual sayı
# ─────────────────────────────────────────────────────────────────────────────


class QuestionCountFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.registrar.models import Subject

        cls.org, cls.teacher, _student = _make_people("qc1021")
        cls.subject = Subject.objects.create(organization=cls.org, code="QKU-9021", name="Qrafik dizayn")

    def _form(self, data=None, instance=None, initial=None):
        from apps.exams.forms import ExamForm

        kwargs = {"organization": self.org, "user": None}
        if instance is not None:
            kwargs["instance"] = instance
        if initial is not None:
            kwargs["initial"] = initial
        return ExamForm(data, **kwargs) if data is not None else ExamForm(**kwargs)

    def _data(self, category, count, **extra):
        now = timezone.localtime()
        data = {
            "title": "QC exam",
            "exam_type": "test",
            "exam_type_extended": category,
            "subject": str(self.subject.pk),
            "start_datetime": (now + timedelta(days=1)).strftime("%d.%m.%Y %H:%M"),
            "end_datetime": (now + timedelta(days=1, hours=2)).strftime("%d.%m.%Y %H:%M"),
            "total_duration_minutes": "60",
            "random_question_count": "" if count is None else str(count),
            "max_attempts_per_user": "1",
        }
        data.update(extra)
        return data

    def _clean_count(self, form):
        self.assertTrue(form.is_valid(), form.errors.as_json())
        return form.cleaned_data["random_question_count"]

    def test_new_form_initial_and_widget_data(self):
        form = self._form()
        self.assertEqual(form.initial["random_question_count"], 50)
        attrs = form.fields["random_question_count"].widget.attrs
        self.assertEqual(attrs["data-qcount-final"], "50")
        self.assertEqual(attrs["data-qcount-midterm"], "30")
        self.assertEqual(attrs["data-qcount-auto"], "50")
        self.assertIn("Midterm üçün 30 sual (Sistem tənzimləmələri)", attrs["data-qcount-hint-midterm"])
        midterm = self._form(initial={"exam_type_extended": "midterm"})
        self.assertEqual(midterm.initial["random_question_count"], 30)
        self.assertEqual(midterm.question_count_hint, "Midterm üçün 30 sual (Sistem tənzimləmələri)")
        html = str(midterm["random_question_count"])
        self.assertIn('value="30"', html)
        self.assertIn('data-qcount-auto="30"', html)

    def test_new_midterm_left_at_final_default_or_empty_becomes_30(self):
        self.assertEqual(self._clean_count(self._form(self._data("midterm", 50))), 30)
        self.assertEqual(self._clean_count(self._form(self._data("midterm", None))), 30)

    def test_new_final_left_at_midterm_default_or_empty_becomes_50(self):
        self.assertEqual(self._clean_count(self._form(self._data("final", 30))), 50)
        self.assertEqual(self._clean_count(self._form(self._data("final", None))), 50)

    def test_new_custom_count_is_kept(self):
        self.assertEqual(self._clean_count(self._form(self._data("midterm", 25))), 25)
        self.assertEqual(self._clean_count(self._form(self._data("final", 40))), 40)
        self.assertEqual(self._clean_count(self._form(self._data("quiz", 50))), 50)  # sınaq — dəyişmir
        self.assertEqual(self._clean_count(self._form(self._data("quiz", None))), 10)  # əvvəlki boş defolt

    @override_settings(RUNTIME_SETTINGS_ENABLED=True)
    def test_runtime_value_is_used(self):
        _set_runtime(KEY_MIDTERM_QUESTION_COUNT, 35)
        try:
            self.assertEqual(self._clean_count(self._form(self._data("midterm", 50))), 35)
            self.assertEqual(self._form(initial={"exam_type_extended": "midterm"}).initial["random_question_count"], 35)
        finally:
            _clear_runtime()

    def _existing(self, category, count):
        now = timezone.now()
        return Exam.objects.create(
            title="QC existing",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            exam_type_extended=category,
            subject=self.subject,
            random_question_count=count,
            total_duration_minutes=60,
            start_datetime=now + timedelta(days=1),
            end_datetime=now + timedelta(days=1, hours=2),
        )

    def test_edit_keeps_a_deliberate_custom_count(self):
        exam = self._existing("final", 42)
        self.assertEqual(self._clean_count(self._form(self._data("midterm", 42), instance=exam)), 42)
        exam = self._existing("midterm", 50)  # midterm-də əl ilə 50 yazılıb
        self.assertEqual(self._clean_count(self._form(self._data("midterm", 50), instance=exam)), 50)
        self.assertEqual(self._clean_count(self._form(self._data("final", 50), instance=exam)), 50)

    def test_edit_category_switch_moves_an_untouched_auto_count(self):
        exam = self._existing("final", 50)
        self.assertEqual(self._clean_count(self._form(self._data("midterm", 50), instance=exam)), 30)
        self.assertEqual(self._clean_count(self._form(self._data("final", 50), instance=exam)), 50)
        form = self._form(instance=exam)
        self.assertEqual(form.fields["random_question_count"].widget.attrs.get("data-qcount-auto"), "50")
        custom = self._form(instance=self._existing("final", 44))
        self.assertNotIn("data-qcount-auto", custom.fields["random_question_count"].widget.attrs)

    def test_template_renders_the_hint(self):
        from django.template.loader import render_to_string

        html = render_to_string(
            "exams/teacher/partials/_create_exam_modal_form.html",
            {"form": self._form(initial={"exam_type_extended": "midterm"})},
        )
        self.assertIn("data-qcount-hint", html)
        self.assertIn("Midterm üçün 30 sual (Sistem tənzimləmələri)", html)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Fənn / qrup axtarışı
# ─────────────────────────────────────────────────────────────────────────────

GROUP_VARIANTS = (
    "634 Qrafik",
    "634Qrafik",
    "qrafik 634",
    "Qrafik/634",
    "634-qrafik",
    "  634   qrafik  ",
    "QRAFİK 634",
    "qrafık 634",
    "634 qrafikdizayn",
    "dizayn qrafik 634",
)


class LookupMatchTests(SimpleTestCase):
    def test_split_tokens(self):
        self.assertEqual(split_tokens("634Qrafik"), ["634", "Qrafik"])
        self.assertEqual(split_tokens(" qrafik/dizayn-634 "), ["qrafik", "dizayn", "634"])
        self.assertEqual(split_tokens("—"), [])

    def test_group_label_variants(self):
        for query in GROUP_VARIANTS:
            self.assertTrue(lookup_match(query, words=("634 az", "Qrafik dizayn")), query)
        self.assertFalse(lookup_match("635 qrafik", words=("634 az", "Qrafik dizayn")))
        self.assertFalse(lookup_match("634 biznes", words=("634 az", "Qrafik dizayn")))

    def test_subject_variants_across_name_and_code(self):
        words, codes = ("Kompüter şəbəkələri",), ("QKU-1203",)
        for query in ("sebeke", "ŞƏBƏKƏ", "komputer sebeke", "sebeke kompüter", "1203 sebeke", "kompyutersebeke"):
            expected = query != "kompyutersebeke"  # «y» hərf qatlamasına daxil deyil
            self.assertEqual(lookup_match(query, words=words, codes=codes), expected, query)
        self.assertTrue(lookup_match("QKU1203", words=words, codes=codes))
        self.assertTrue(lookup_match("kompütersəbəkələri", words=words, codes=codes))

    def test_short_tokens_still_need_a_word_start(self):
        self.assertTrue(lookup_match("vo", words=("VoIP sistemləri",)))
        self.assertFalse(lookup_match("vo", words=("Devops mühəndisliyi",)))
        self.assertFalse(lookup_match("vo", words=("Bihevorial iqtisadiyyat",)))


class SubjectLookupEndpointTests(_SubjectBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from apps.registrar.models import Subject

        cls.target = Subject.objects.create(organization=cls.org, code="QKU-634", name="Qrafik dizayn əsasları")
        Subject.objects.create(organization=cls.org, code="QKU-700", name="Kompüter şəbəkələri")
        Subject.objects.create(organization=cls.org, code="QKU-701", name="Riyazi analiz")
        Subject.objects.create(organization=cls.org, code="QKU-702", name="Devops mühəndisliyi")

    def _codes(self, q):
        response = self._client_for(self.teacher).get(reverse("exams:subject_search"), {"q": q})
        self.assertEqual(response.status_code, 200)
        return [row["meta"] for row in response.json()["results"]]

    def test_variants_find_the_subject(self):
        for query in (
            "634 Qrafik",
            "qrafik 634",
            "634Qrafik",
            "Qrafik/dizayn",
            "qrafik-dizayn",
            "qrafikdizayn",
            "dizayn qrafik",
            "esaslari qrafik",
            "  qrafik    dizayn ",
            "QRAFİK",
            "QKU634",
            "qku-634",
        ):
            self.assertEqual(self._codes(query), ["QKU-634"], query)

    def test_diacritics_and_word_start(self):
        self.assertEqual(self._codes("ŞƏBƏKƏ"), ["QKU-700"])
        self.assertEqual(self._codes("kompyuter"), [])  # «y» ≠ «ü» — qatlama siyahısı dəyişmir
        self.assertEqual(self._codes("vo"), [])  # «Devops» söz ortasıdır


class UnitLookupEndpointTests(_UnitFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from apps.organizations.models import OrgUnit

        with bypass_rls():
            cls.faculty_q = OrgUnit.objects.create(
                organization=cls.org, name="Qrafik dizayn", slug="hq-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.group_q = OrgUnit.objects.create(
                organization=cls.org, parent=cls.faculty_q, name="634 az", slug="hq-634", unit_type=OrgUnitType.GROUP
            )
            cls.faculty_s = OrgUnit.objects.create(
                organization=cls.org, name="Kompüter şəbəkələri", slug="hq-fac2", unit_type=OrgUnitType.FACULTY
            )
            cls.group_s = OrgUnit.objects.create(
                organization=cls.org, parent=cls.faculty_s, name="702 Ə-1", slug="hq-702", unit_type=OrgUnitType.GROUP
            )

    def _ids(self, q):
        client = _unit_login(self.teacher, self.org)
        response = client.get(reverse("exams:group_search"), {"kind": "units", "q": q})
        self.assertEqual(response.status_code, 200)
        return [row["id"] for row in response.json()["results"]]

    def test_group_variants_with_specialty_name(self):
        for query in GROUP_VARIANTS:
            self.assertEqual(self._ids(query), [str(self.group_q.pk)], query)

    def test_old_compact_rule_and_diacritics_still_work(self):
        self.assertEqual(self._ids("634ing"), [str(self.group.pk)])
        self.assertEqual(self._ids("sebeke 702"), [str(self.group_s.pk)])
        self.assertEqual(self._ids("702 ə1"), [str(self.group_s.pk)])
        self.assertEqual(self._ids("702 e-1"), [str(self.group_s.pk)])
        self.assertCountEqual(self._ids("634"), [str(self.group.pk), str(self.group_q.pk)])
