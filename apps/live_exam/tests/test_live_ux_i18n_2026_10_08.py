"""i18n (2026-10-08): qoşulma / oyun səhifələrində Azərbaycan və ingilis dili qarışmamalıdır.

Səbəblər: (1) PIN girişi, «əvvəlki qoşulma», «ad məşğuldur» mətnləri dil lüğətlərində sərt kodlanmışdı,
sürət-həddi mesajları HƏR dildə Azərbaycanca idi; (2) aparıcının «Dil» ayarı heç yerdə tətbiq olunmurdu.
İndi bütün mətnlər gettext/pgettext-dən gəlir və aparıcı dili sabitləyibsə oyunçu səhifələri həmin dildədir.
"""

from __future__ import annotations

import re

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.live_exam import services
from apps.live_exam.session_settings import update_session_settings

from .lx_be_support import (
    IN_MEMORY_LAYERS,
    add_question,
    make_exam,
    make_host,
    make_players,
    make_session,
    player_client,
    reset_rate_limits,
)

AZ_LETTERS = re.compile(r"[əƏğĞıİşŞçÇöÖüÜ]")
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "lx-i18n"}}


def visible_text(html: str) -> str:
    """Səhifə mətni + JS i18n JSON blokları (onlar da ekranda göstərilir); stil/ikon/inline SVG yox."""
    html = re.sub(r"<(style|svg)\b.*?</\1>", " ", html, flags=re.S)
    html = re.sub(r"<script(?![^>]*application/json)[^>]*>.*?</script>", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS, CACHES=LOCMEM)
class LivePagesLanguageTest(TestCase):
    def setUp(self):
        reset_rate_limits()
        from django.core.cache import cache

        cache.clear()
        self.host, self.org = make_host("lxi18n")
        self.exam = make_exam(self.host, self.org, title="Quiz 101")
        add_question(self.exam, "Q1", [("A", True), ("B", False)])
        self.session = make_session(self.exam, self.host)
        self.player = make_players(self.session, 1, prefix="Ali")[0]

    def _get(self, client, name, lang, **kwargs):
        url = reverse(f"liveExam:{name}", kwargs=kwargs or {"pin": self.session.pin})
        response = client.get(url, HTTP_ACCEPT_LANGUAGE=lang)
        self.assertEqual(response.status_code, 200, (name, response.status_code))
        return response.content.decode()

    def test_session_language_en_makes_player_pages_english(self):
        update_session_settings(self.session, {"language": "en"})
        join = self._get(self.client_class(), "join_page", "az")  # brauzer AZ, aparıcı EN seçib
        self.assertIn('lang="en"', join)
        self.assertNotRegex(visible_text(join), AZ_LETTERS)
        self.assertNotIn("lxj-lang", join)  # dil seçicisi gizlədilir — səhifə onsuz da sabit dildədir
        wait = self._get(player_client(self.session, self.player), "wait_room", "az")
        self.assertNotRegex(visible_text(wait), AZ_LETTERS)
        services.start_game(self.session, question_count=1)
        play = self._get(player_client(self.session, self.player), "player_screen", "az")
        self.assertNotRegex(visible_text(play), AZ_LETTERS)

    def test_session_language_az_makes_player_pages_azerbaijani(self):
        update_session_settings(self.session, {"language": "az"})
        join = self._get(self.client_class(), "join_page", "en")
        self.assertIn('lang="az"', join)
        self.assertIn("Oyuna", join)

    def test_system_language_pages_have_no_hardcoded_azerbaijani(self):
        pin_entry = self.client_class().get(reverse("liveExam:pin_entry"), HTTP_ACCEPT_LANGUAGE="en")
        text = visible_text(pin_entry.content.decode())
        self.assertIn("Join a live exam", text)
        # Dil seçicisi dilləri öz adları ilə göstərir («Azərbaycan dili») — onu çıxırıq.
        self.assertNotRegex(re.sub(r"Azərbaycan[^<\s]*( dili)?", "", text), AZ_LETTERS)

    def test_json_messages_follow_the_language(self):
        update_session_settings(self.session, {"late_join_enabled": False})
        services.start_game(self.session, question_count=1)
        url = reverse("liveExam:join_enter", kwargs={"pin": self.session.pin})
        english = self.client_class().post(
            url, {"nickname": "Late"}, HTTP_ACCEPT_LANGUAGE="en", REMOTE_ADDR="10.50.0.1"
        )
        self.assertEqual(english.status_code, 403)
        self.assertNotRegex(english.json()["message"], AZ_LETTERS)
        update_session_settings(self.session, {"language": "az"})
        azeri = self.client_class().post(url, {"nickname": "Late"}, HTTP_ACCEPT_LANGUAGE="en", REMOTE_ADDR="10.50.0.2")
        self.assertIn("gecikənlərin", azeri.json()["message"])

    def test_join_page_shows_the_block_reason_before_submitting(self):
        update_session_settings(self.session, {"late_join_enabled": False})
        services.start_game(self.session, question_count=1)
        join = self._get(self.client_class(), "join_page", "az")
        self.assertIn('"blockedMessage": "Oyun art', join)
