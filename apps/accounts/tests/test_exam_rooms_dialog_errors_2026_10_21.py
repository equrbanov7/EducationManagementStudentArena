"""«İmtahan zalları» dialoqları — xəta dialoqda qalır (sahib 2026-10-21).

Şikayət: «Kompüter əlavə edərkən səhv edəndə səhvi göstərmir, yazdığım tabdan atır — deyirsə yer var,
modalda göstərsin, bütöv atır.» Əvvəl xəta da redirect idi (fraqmentsiz): dialoq bağlanır, yazılanlar
itir, zalın çekmecəsi açılmırdı.

Müqavilə:
* AJAX (``X-Requested-With``) → JSON ``{ok, message, errors: {sahə: mesaj}}``; xəta 400, uğur 200;
  xidmət xətaları SAHƏYƏ bağlanır (yer → ``seat_number``, MAC → ``mac_address``, IP → ``ip_address``);
* adi POST → redirect qalır, xətada vəziyyət sessiyada saxlanır və bölmə onu ``#sar-form-state`` JSON
  blokunda BİR DƏFƏ qaytarır (dialoq yenidən açılır, yazılanlar bərpa olunur).
"""

import json

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.views.profile._sections.exam_rooms import FORM_STATE_SESSION_KEY
from apps.exams.domain.final_center import ExamRoomComputer
from apps.exams.models import ExamRoom
from apps.exams.services.final_center import RoomAdminError, add_computer, update_computer
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()
PASSWORD = "StrongPass123!"
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("xrd_owner", "xrd_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="XRD University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.room = ExamRoom.objects.create(organization=cls.org, name="Zal X", code="ZX", capacity=20)
        cls.other_room = ExamRoom.objects.create(organization=cls.org, name="Zal Y", code="ZY", capacity=20)
        cls.superadmin = User.objects.create_superuser("xrd_admin", "xrd_admin@test.az", PASSWORD)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.superadmin)
        self.url = reverse("accounts:superadmin_exam_rooms")
        self.pc1 = add_computer(
            room=self.room, label="PC-01", mac="AA:BB:CC:DD:EE:01", ip_address="10.0.0.11", seat_number=1
        )

    def _computer(self, **overrides):
        data = {
            "action": "add_computer",
            "organization_id": str(self.org.pk),
            "room_id": str(self.room.pk),
            "label": "PC-02",
            "seat_number": "2",
            "mac_address": "AA:BB:CC:DD:EE:02",
            "ip_address": "10.0.0.12",
            "notes": "pəncərə yanı",
            "next": reverse("accounts:profile") + "?section=superadmin-exam-rooms",
        }
        data.update(overrides)
        return data


class AjaxContractTests(_Base):
    def _post(self, data):
        return self.client.post(self.url, data, **AJAX)

    def test_duplicate_seat_is_a_seat_field_error_and_nothing_is_saved(self):
        response = self._post(self._computer(seat_number="1"))
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(set(body["errors"]), {"seat_number"})
        self.assertIn("1", body["errors"]["seat_number"])
        self.assertEqual(body["message"], body["errors"]["seat_number"])
        self.assertFalse(ExamRoomComputer.objects.filter(label="PC-02").exists())
        # AJAX xətası sessiyaya «köhnə tost» və ya dialoq vəziyyəti YAZMIR.
        self.assertEqual(list(get_messages(response.wsgi_request)), [])
        self.assertNotIn(FORM_STATE_SESSION_KEY, self.client.session)

    def test_duplicate_mac_in_same_room_and_other_room_map_to_mac_field(self):
        same = self._post(self._computer(mac_address="aa-bb-cc-dd-ee-01"))
        self.assertEqual(same.status_code, 400)
        self.assertEqual(set(same.json()["errors"]), {"mac_address"})

        add_computer(room=self.other_room, label="Y-01", mac="AA:BB:CC:DD:EE:77")
        other = self._post(self._computer(mac_address="AA:BB:CC:DD:EE:77"))
        self.assertEqual(other.status_code, 400)
        self.assertIn("Zal Y", other.json()["errors"]["mac_address"])

    def test_bad_mac_format(self):
        response = self._post(self._computer(mac_address="AA:BB:CC:DD:EE:GZ"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("AA:BB:CC:DD:EE:GZ", response.json()["errors"]["mac_address"])

    def test_duplicate_ip_in_org_maps_to_ip_field(self):
        add_computer(room=self.other_room, label="Y-02", mac="AA:BB:CC:DD:EE:78", ip_address="10.0.0.50")
        response = self._post(self._computer(ip_address="10.0.0.50"))
        self.assertEqual(response.status_code, 400)
        errors = response.json()["errors"]
        self.assertEqual(set(errors), {"ip_address"})
        self.assertIn("Zal Y", errors["ip_address"])

    def test_every_bad_field_is_reported_at_once(self):
        response = self._post(self._computer(label="", seat_number="abc", mac_address="zz", ip_address="10.0.0"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"label", "seat_number", "mac_address", "ip_address"})

    def test_success_returns_ok_message_and_highlight(self):
        response = self._post(self._computer())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        computer = ExamRoomComputer.objects.get(label="PC-02")
        self.assertTrue(body["ok"])
        self.assertTrue(body["message"])
        self.assertEqual(body["hl_comp"], computer.pk)
        self.assertEqual(body["room_id"], self.room.pk)
        self.assertEqual(list(get_messages(response.wsgi_request)), [])

    def test_update_computer_seat_clash(self):
        pc2 = add_computer(room=self.room, label="PC-02", mac="AA:BB:CC:DD:EE:02", seat_number=2)
        response = self._post(
            self._computer(action="update_computer", computer_id=str(pc2.pk), seat_number="1", is_active="1")
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"seat_number"})
        pc2.refresh_from_db()
        self.assertEqual(pc2.seat_number, 2)

    def test_room_form_errors_are_per_field(self):
        response = self._post(
            {
                "action": "create_room",
                "organization_id": str(self.org.pk),
                "name": "",
                "code": "zx",
                "capacity": "0",
                "computer_count": "0",
            }
        )
        self.assertEqual(response.status_code, 400)
        errors = response.json()["errors"]
        self.assertIn("name", errors)
        self.assertIn("code", errors)

    def test_bulk_all_failed_is_an_error_with_line_list(self):
        response = self._post(
            {
                "action": "bulk_add_computers",
                "organization_id": str(self.org.pk),
                "room_id": str(self.room.pk),
                "bulk_text": "PC-09, not-a-mac\nPC-10",
            }
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("bulk_text", body["errors"])
        self.assertEqual(len(body["error_list"]), 2)

    def test_bulk_empty_text_is_a_field_error(self):
        response = self._post(
            {
                "action": "bulk_add_computers",
                "organization_id": str(self.org.pk),
                "room_id": str(self.room.pk),
                "bulk_text": "# yalnız şərh",
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"bulk_text"})

    def test_bulk_partial_success_keeps_only_failed_lines(self):
        response = self._post(
            {
                "action": "bulk_add_computers",
                "organization_id": str(self.org.pk),
                "room_id": str(self.room.pk),
                "bulk_text": "PC-20, AA:BB:CC:DD:EE:20, 20\nPC-21, AA:BB:CC:DD:EE:21, 1",
            }
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["keep_open"])
        self.assertEqual(body["remaining_text"], "PC-21, AA:BB:CC:DD:EE:21, 1")
        self.assertIn("bulk_text", body["errors"])
        self.assertTrue(ExamRoomComputer.objects.filter(label="PC-20").exists())
        self.assertFalse(ExamRoomComputer.objects.filter(label="PC-21").exists())

    def test_grant_unknown_user_maps_to_username(self):
        response = self._post(
            {"action": "grant_room_manager", "organization_id": str(self.org.pk), "username": "yoxdur-belə"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"username"})

    def test_drawer_action_error_goes_to_summary(self):
        response = self._post({"action": "nonsense", "organization_id": str(self.org.pk)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"__all__"})

    def test_delete_room_success_reports_removed_room(self):
        room = ExamRoom.objects.create(organization=self.org, name="Silinən", code="SIL")
        response = self._post({"action": "delete_room", "organization_id": str(self.org.pk), "room_id": str(room.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["removed_room"], room.pk)

    def test_non_manager_gets_json_403(self):
        plain = User.objects.create_user("xrd_plain", "xrd_plain@test.az", PASSWORD)
        client = Client()
        client.force_login(plain)
        response = client.post(self.url, self._computer(), **AJAX)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])


class NonAjaxFallbackTests(_Base):
    def test_error_redirects_back_to_the_room_drawer_and_keeps_dialog_state(self):
        response = self.client.post(self.url, self._computer(seat_number="1"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"#sar-room-{self.room.pk}", response["Location"])
        state = self.client.session[FORM_STATE_SESSION_KEY]
        self.assertEqual(state["dialog"], "sarComputerDialog")
        self.assertEqual(state["action"], "add_computer")
        self.assertEqual(state["room_id"], str(self.room.pk))
        self.assertEqual(state["values"]["label"], "PC-02")
        self.assertEqual(state["values"]["notes"], "pəncərə yanı")
        self.assertNotIn("csrfmiddlewaretoken", state["values"])
        self.assertNotIn("next", state["values"])
        self.assertEqual(set(state["errors"]), {"seat_number"})

        page = self.client.get(self.url, {"room_org": str(self.org.pk)})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'id="sar-form-state"')
        # `json_script` qeyri-ASCII-ni \uXXXX ilə yazır (və `</script>`-i qaçırır).
        self.assertContains(page, json.dumps("pəncərə yanı")[1:-1])
        # Bir dəfəlik: növbəti render dialoqu yenidən açmır.
        self.assertNotIn(FORM_STATE_SESSION_KEY, self.client.session)
        again = self.client.get(self.url, {"room_org": str(self.org.pk)})
        self.assertNotContains(again, 'id="sar-form-state"')

    def test_success_still_redirects_with_highlight(self):
        response = self.client.post(self.url, self._computer())
        self.assertEqual(response.status_code, 302)
        computer = ExamRoomComputer.objects.get(label="PC-02")
        self.assertIn(f"hl_comp={computer.pk}", response["Location"])
        self.assertNotIn(FORM_STATE_SESSION_KEY, self.client.session)

    def test_bulk_partial_success_reopens_dialog_with_failed_lines(self):
        response = self.client.post(
            self.url,
            {
                "action": "bulk_add_computers",
                "organization_id": str(self.org.pk),
                "room_id": str(self.room.pk),
                "bulk_text": "PC-30, AA:BB:CC:DD:EE:30\nPC-31, bad",
            },
        )
        self.assertEqual(response.status_code, 302)
        state = self.client.session[FORM_STATE_SESSION_KEY]
        self.assertEqual(state["dialog"], "sarBulkDialog")
        self.assertEqual(state["values"]["bulk_text"], "PC-31, bad")

    def test_section_renders_ajax_contract_hooks(self):
        page = self.client.get(self.url, {"room_org": str(self.org.pk)})
        self.assertContains(page, "data-sar-fragment-url=")
        self.assertContains(page, 'data-sar-region="list"')
        self.assertContains(page, 'data-sar-ajax="1"')
        self.assertContains(page, "accounts/js/superadmin_exam_rooms_ajax.js")


class ServiceFieldMappingTests(_Base):
    def test_errors_carry_field_names(self):
        cases = {
            "seat_number": {"seat_number": 1},
            "mac_address": {"mac": "AA:BB:CC:DD:EE:01"},
            "ip_address": {"ip_address": "10.0.0.11"},
            "label": {"label": "pc-01"},
        }
        for field, override in cases.items():
            kwargs = {"label": "PC-50", "mac": "AA:BB:CC:DD:EE:50", "seat_number": 50, "ip_address": ""}
            kwargs.update(override)
            with self.subTest(field=field):
                with self.assertRaises(RoomAdminError) as ctx:
                    add_computer(room=self.room, **kwargs)
                self.assertEqual(set(ctx.exception.errors), {field})
                self.assertEqual(str(ctx.exception), ctx.exception.errors[field])

    def test_update_keeps_own_ip_and_seat(self):
        update_computer(
            computer=self.pc1, label="PC-01", mac="AA:BB:CC:DD:EE:01", seat_number=1, ip_address="10.0.0.11"
        )
        self.pc1.refresh_from_db()
        self.assertEqual(self.pc1.ip_address, "10.0.0.11")

    def test_plain_message_still_works(self):
        exc = RoomAdminError("mətn")
        self.assertEqual(str(exc), "mətn")
        self.assertEqual(exc.errors, {})
        self.assertEqual(RoomAdminError("x", field="ip_address").errors, {"ip_address": "x"})
