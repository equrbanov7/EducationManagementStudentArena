"""«Xanaya dərs qoy» — «Korpus → Otaq» seçiciləri (sahib 2026-10-17: «korpusa uyğun otaqları düz seç»).

Nəyi qoruyur
------------
* dialoq kataloqu (``schedule_rooms.dialog_rooms``): hər otaq korpusu + tutumu + «33 · 40 nəfər» mətni ilə,
  korpuslar siyahısı, qrupun korpusu defolt (xəritə adı reyestr yazılışına çevrilir), insan sırası;
* ``plan(building=…)``: otaqlar SEÇİLMİŞ korpusa görə sıralanır (başqa korpus «same_campus=False»),
  ``campus`` isə qrupun öz korpusu qalır; boş / naməlum korpus → qrupun korpusu;
* HTTP: bölmə render-ində otaq sahəsi stilli seçicidir (datalist YOX), variantlar korpus + tutumla;
  ``action=plan`` ``room_building``-i qəbul edir.
"""

from __future__ import annotations

from django.urls import reverse

from apps.registrar import campus, schedule_rooms
from apps.registrar.tests.test_schedule_suggest_2026_10_17 import _SuggestBase
from core.rls import bypass_rls


class DialogRoomCatalogTest(_SuggestBase):
    code = "sdr"

    def test_catalog_has_building_capacity_and_group_default(self):
        with bypass_rls():
            self._room("10", 40, "Korpus A")
            self._room("9", 0, "Korpus A")
            catalog = schedule_rooms.dialog_rooms(self.org, self.groups[0])
        rows = {(row["label"], row["building"]): row for row in catalog["rooms"]}
        self.assertEqual(rows[("Uyğun", "Korpus B")]["capacity"], 30)
        self.assertEqual(rows[("Uyğun", "Korpus B")]["text"], "Uyğun · 30 nəfər")
        self.assertEqual(rows[("9", "Korpus A")]["text"], "9", "tutum məlum deyil — yalnız ad")
        self.assertEqual(catalog["buildings"], ["Korpus A", "Korpus B"])
        self.assertEqual(catalog["default_building"], "Korpus B")
        korpus_a = [row["label"] for row in catalog["rooms"] if row["building"] == "Korpus A"]
        self.assertEqual(korpus_a[:2], ["9", "10"], "otaq nömrələri insan sırası ilə")

    def test_map_name_is_matched_to_the_registry_spelling(self):
        self.assertEqual(campus.match_building(["Korpus B", "Korpus A"], "korpus  b"), "Korpus B")
        self.assertEqual(campus.match_building(["Korpus B"], "Korpus C"), "")
        with bypass_rls():
            self.assertEqual(schedule_rooms.dialog_rooms(self.org)["default_building"], "", "qrup yoxdur")

    def test_plan_ranks_rooms_by_the_selected_korpus(self):
        rooms = self._plan(weekday=1, time_slot="10:10|11:40", building="Korpus A")
        self.assertEqual(rooms["campus"], "Korpus B", "qrupun korpusu dəyişmir")
        self.assertEqual(rooms["campus_selected"], "Korpus A")
        rows = rooms["rooms"]["rows"]
        self.assertEqual(rows[0]["label"], "Uzaq")
        self.assertTrue(rows[0]["same_campus"])
        uygun = next(row for row in rows if row["label"] == "Uyğun")
        self.assertFalse(uygun["same_campus"], "seçilmiş korpusa nəzərən başqa korpus")
        default = self._plan(weekday=1, time_slot="10:10|11:40", building="Yox korpus")
        self.assertEqual(default["campus_selected"], "Korpus B", "naməlum korpus → qrupun korpusu")


class DialogRoomHttpTest(_SuggestBase):
    code = "sdrh"

    def test_section_renders_korpus_and_room_selects_with_capacity(self):
        url = "%s?section=schedule-manage&sm_group=%s" % (reverse("accounts:profile"), self.groups[0].pk)
        response = self._client(self.coordinator).get(url)
        self.assertEqual(response.status_code, 200)
        section = response.context["schedule_manage_section"]
        uygun = next(row for row in section["rooms"] if row["label"] == "Uyğun")
        self.assertEqual((uygun["building"], uygun["capacity"]), ("Korpus B", 30))
        self.assertEqual(section["room_buildings"], ["Korpus A", "Korpus B"])
        self.assertEqual(section["room_default_building"], "Korpus B")
        body = response.content.decode()
        self.assertIn("data-sedit-room-building", body)
        self.assertIn('data-default-building="Korpus B"', body)
        self.assertIn('data-building="Korpus B" data-text="Uyğun · 30 nəfər"', body)
        self.assertNotIn("<datalist", body, "native datalist yoxdur")
        self.assertIn("schedule_editor_room.js", body)

    def test_plan_action_accepts_the_selected_korpus(self):
        payload = {**self._payload(), "action": "plan", "mode": "both", "weekday": "1"}
        payload.update({"time_slot": "10:10|11:40", "slot_kind": "seminar", "room_building": "Korpus A"})
        response = self._act(self.coordinator, payload)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["campus_selected"], "Korpus A")
        self.assertEqual(data["rooms"]["rows"][0]["building"], "Korpus A")
