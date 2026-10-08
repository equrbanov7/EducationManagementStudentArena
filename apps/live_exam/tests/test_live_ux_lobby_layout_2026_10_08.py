"""L1 / L4 / L5 (2026-10-08): proyektor düzülüşü — sürüşən konteynerlər və say.

* L1 — «Aşağıdakı adlar görünmür, çevirmək də olmur»: lobbi siyahısı ``overflow: hidden`` idi.
  İndi ``hx-scroll`` sürüşən konteyneri, avtomatik sütunlu çip şəbəkəsi və sıxlıq pillələri; ümumi
  say serverdən HƏQİQİ saydır (siyahı 200-də kəsilsə də).
* Statik testlər düzülüşün sürüşən konteyner siniflərini işlətdiyini qoruyur (gələcək redizaynda
  təsadüfən yenə ``overflow: hidden`` qayıtmasın).
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.live_exam import services
from apps.live_exam.models import LivePlayer
from apps.live_exam.transport import build_lobby_state_payload

from .lx_be_support import IN_MEMORY_LAYERS, add_question, host_client, make_exam, make_host, make_players, make_session

APP = Path(__file__).resolve().parents[1]
CSS = APP / "static" / "css"
JS = APP / "static" / "js" / "host_lobby"
TEMPLATES = APP / "templates" / "liveExam"


def css_block(text: str, selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", text)
    return match.group(1) if match else ""


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS)
class LobbyRosterCountTest(TestCase):
    def setUp(self):
        self.host, self.org = make_host("lxroster2")
        self.exam = make_exam(self.host, self.org)
        add_question(self.exam, "Q1", [("a", True), ("b", False)])
        self.session = make_session(self.exam, self.host)
        self.client = host_client(self.host, self.org)

    def test_count_is_the_real_total_even_when_the_list_is_capped(self):
        make_players(self.session, 205)
        payload = build_lobby_state_payload(self.session)
        self.assertEqual(len(payload["players"]), 200)
        self.assertEqual(payload["count"], 205)
        state = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin})).json()
        self.assertEqual((state["total_players"], state["roster_count"]), (205, 205))

    def test_count_for_a_real_classroom_and_after_removal(self):
        players = make_players(self.session, 22)
        self.assertEqual(build_lobby_state_payload(self.session)["count"], 22)
        services.start_game(self.session, question_count=1)
        services.remove_player(self.session, players[0].id)
        self.session.refresh_from_db()
        payload = build_lobby_state_payload(self.session)
        self.assertEqual(payload["count"], 21)
        self.assertEqual(LivePlayer.all_objects.filter(session=self.session).count(), 22)
        state = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin})).json()
        self.assertEqual(state["roster_count"], 21)
        self.assertEqual(len(state["players"]), 21)  # aparıcının «İştirakçılar» siyahısı oyun gedərkən


class ProjectorLayoutStaticTest(SimpleTestCase):
    """Düzülüş sürüşən konteyner siniflərini işlədir (L1 lobbi, L6 çekməcə, L4 plitələr)."""

    def test_shared_scroll_container_class(self):
        controls = (CSS / "host_lobby" / "_controls.css").read_text(encoding="utf-8")
        block = css_block(controls, ".hx-scroll")
        self.assertIn("overflow-y: auto", block)
        self.assertIn("overscroll-behavior: contain", block)
        head = (TEMPLATES / "partials" / "_host_head_assets.html").read_text(encoding="utf-8")
        self.assertIn("css/host_lobby/_controls.css", head)

    def test_lobby_roster_is_a_scrollable_responsive_grid(self):
        lobby_js = (JS / "lobby.js").read_text(encoding="utf-8")
        self.assertIn('class="hx-cloud hx-scroll"', lobby_js)
        for level in ('"l"', '"m"', '"s"', '"xs"', '"xxs"'):
            self.assertIn(level, lobby_js)  # avtomatik kiçilmə pillələri
        self.assertIn("is-scrollable", lobby_js)
        css = (CSS / "host_lobby" / "_part2.css").read_text(encoding="utf-8")
        cloud = css_block(css, ".hx-cloud")
        self.assertNotIn("overflow: hidden", cloud)  # əvvəlki xəta: adlar kəsilirdi, sürüşmürdü
        self.assertIn("repeat(auto-fit", cloud)
        self.assertIn('.hx-cloud[data-density="xxs"]', css)
        constants = (JS / "constants.js").read_text(encoding="utf-8")
        self.assertRegex(constants, r"LOBBY_MAX_BUBBLES = (2\d\d|\d{4,})")

    def test_players_drawer_list_scrolls(self):
        drawer = (TEMPLATES / "partials" / "_host_players_drawer.html").read_text(encoding="utf-8")
        self.assertIn("hx-scroll", drawer)
        self.assertIn("data-players-list", drawer)
