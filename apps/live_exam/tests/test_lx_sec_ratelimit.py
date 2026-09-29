"""LX-SEC — sinif NAT-ı ilə uyğun limitlər və PIN təxmininə qarşı qapılar (Audit 2026-09-28).

Real sinif: 90–150 tələbə EYNİ universitet NAT İP-sindən, bəziləri Wi-Fi qırıldıqca
yenidən qoşulur. Qayda (LXS-05 / LXS-06):

* İP üzrə yalnız UĞURSUZ PIN axtarışları sayılır (brute force «miss» tələb edir) və
  bu büdcə BÜTÜN PIN həll edən giriş nöqtələri üçün ortaqdır (pin_entry, join
  səhifəsi, join/enter);
* etibarlı imzalı oyunçu token-i olan (artıq qoşulmuş) tələbəni İP büdcəsi heç
  vaxt kəsmir;
* per-klient sərt vedrə yalnız etibarlı ``live_client_id`` cookie-si üçün —
  cookie-siz klientlər İP üzrə ORTAQ «klient» vedrəsinə düşmür;
* pin+İP vedrəsi yalnız YENİ oyunçu cəhdlərini sayır (reconnect sayılmır);
* oyunçu səhifələri / POST-ları mövcud olmayan PIN üçün fərqli cavab vermir;
* reaksiyalar üçün sessiya-səviyyəli fan-out tavanı (LXS-11).
"""

from __future__ import annotations

import random
from collections import Counter

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.live_exam.models import LivePlayer, LiveSession
from apps.live_exam.views.player._shared import _pin_ip_rate
from core.rate_limit import parse_rate

from .lx_sec_support import make_exam, make_org, make_session, make_teacher, player_client, reset_rate_limits

_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_NAT_IP = "10.150.0.1"


def _fake_pin(rng: random.Random, real_pin: str) -> str:
    while True:
        guess = "".join(rng.choice(_ALPHABET) for _ in range(10))
        if guess != real_pin:
            return guess


class _RateBase(TestCase):
    def setUp(self):
        reset_rate_limits()
        from django.contrib.auth import get_user_model

        owner = get_user_model().objects.create_user("lxs_rl_owner", "lxs_rl_owner@example.com", "StrongPass123!")
        self.org = make_org("LXS RateLimit Org", owner)
        self.host = make_teacher("lxs_rl_host", self.org)
        self.exam = make_exam(self.host, self.org, "lxs-ratelimit-exam")
        self.session = make_session(self.exam, self.host, host_settings={"max_participants": 150})
        self.rng = random.Random(2809)
        self.pin_entry = reverse("liveExam:pin_entry")
        self.join_page = reverse("liveExam:join_page", kwargs={"pin": self.session.pin})
        self.join_enter = reverse("liveExam:join_enter", kwargs={"pin": self.session.pin})

    def _join_payload(self, nickname):
        return {"nickname": nickname, "avatar_key": "avatar_1", "accessory_key": "accessory_none"}


class ClassroomNatScenarioTest(_RateBase):
    def test_150_students_behind_one_nat_ip_all_get_in(self):
        """LXS-05: default limitlərlə (150 join / 10 dəq pin+İP, cookie-siz klient = İP) sinif kilidlənirdi."""
        statuses = Counter()
        for index in range(150):
            client = Client(REMOTE_ADDR=_NAT_IP)
            if index % 5 == 0:  # PIN-i əllə yazıb səhv edən tələbə
                typo = client.post(self.pin_entry, {"pin": _fake_pin(self.rng, self.session.pin)})
                statuses[("typo", typo.status_code)] += 1
            qr = client.get(self.pin_entry, {"pin": self.session.pin})
            statuses[("qr", qr.status_code)] += 1
            page = client.get(self.join_page)
            statuses[("page", page.status_code)] += 1
            payload = self._join_payload(f"Tələbə {index}")
            joined = client.post(self.join_enter, payload)
            statuses[("join", joined.status_code)] += 1
            if index % 3 == 0:  # zəif Wi-Fi: səhifəni yeniləyib yenidən «Qoşul»
                for _ in range(2):
                    statuses[("page", client.get(self.join_page).status_code)] += 1
                    statuses[("rejoin", client.post(self.join_enter, payload).status_code)] += 1
                wait = client.get(reverse("liveExam:wait_room", kwargs={"pin": self.session.pin}))
                statuses[("wait", wait.status_code)] += 1

        self.assertEqual(LivePlayer.objects.filter(session=self.session).count(), 150)
        blocked = {key: count for key, count in statuses.items() if key[1] == 429}
        self.assertEqual(blocked, {}, statuses)
        self.assertEqual(statuses[("typo", 404)], 30)
        self.assertEqual(statuses[("qr", 302)], 150)
        self.assertEqual(statuses[("join", 200)], 150)
        self.assertEqual(statuses[("rejoin", 200)], 100)

    def test_pin_bruteforce_from_one_ip_is_stopped(self):
        limit = parse_rate(_pin_ip_rate()).limit
        attacker_ip = "10.66.6.6"
        statuses = []
        for _ in range(limit + 5):
            client = Client(REMOTE_ADDR=attacker_ip)  # hər cəhd təzə cookie qabı ilə
            statuses.append(client.post(self.pin_entry, {"pin": _fake_pin(self.rng, self.session.pin)}).status_code)
        self.assertEqual(Counter(statuses[:limit]), Counter({404: limit}))
        self.assertEqual(set(statuses[limit:]), {429})

        # Büdcə bitib — düzgün PIN də həmin İP-dən HƏLL OLUNMUR (fərqlənən cavab yoxdur).
        self.assertEqual(
            Client(REMOTE_ADDR=attacker_ip).post(self.pin_entry, {"pin": self.session.pin}).status_code, 429
        )
        self.assertEqual(
            Client(REMOTE_ADDR="10.66.6.7").post(self.pin_entry, {"pin": self.session.pin}).status_code, 302
        )


class PinOracleTest(_RateBase):
    @override_settings(LIVE_PIN_IP_RATE_LIMIT="3/10m")
    def test_all_pin_resolving_entry_points_share_one_miss_budget(self):
        """LXS-06: join səhifəsi (GET) və join/enter (POST) əvvəl «miss» saymırdı — limitsiz PIN orakulu."""
        ip = "10.66.0.1"
        ghosts = [_fake_pin(self.rng, self.session.pin) for _ in range(3)]
        self.assertEqual(Client(REMOTE_ADDR=ip).get(reverse("liveExam:join_page", args=[ghosts[0]])).status_code, 404)
        ghost_enter = Client(REMOTE_ADDR=ip).post(
            reverse("liveExam:join_enter", args=[ghosts[1]]), self._join_payload("G")
        )
        self.assertEqual(ghost_enter.status_code, 404)
        self.assertEqual(Client(REMOTE_ADDR=ip).post(self.pin_entry, {"pin": ghosts[2]}).status_code, 404)

        self.assertEqual(Client(REMOTE_ADDR=ip).get(self.join_page).status_code, 429)
        self.assertEqual(Client(REMOTE_ADDR=ip).post(self.join_enter, self._join_payload("Late")).status_code, 429)
        self.assertEqual(Client(REMOTE_ADDR=ip).post(self.pin_entry, {"pin": self.session.pin}).status_code, 429)
        self.assertFalse(LivePlayer.objects.filter(session=self.session).exists())

    def test_player_endpoints_answer_the_same_for_unknown_pins(self):
        """LXS-06: gözləmə otağı / oyun ekranı əvvəl mövcud olmayan PIN-ə 404, mövcuda 302 verirdi."""
        ghost = _fake_pin(self.rng, self.session.pin)
        for route in ("wait_room", "player_screen"):
            with self.subTest(route=route):
                real = Client().get(reverse(f"liveExam:{route}", args=[self.session.pin]))
                fake = Client().get(reverse(f"liveExam:{route}", args=[ghost]))
                self.assertEqual((real.status_code, fake.status_code), (302, 302))
                self.assertEqual(fake.url, reverse("liveExam:join_page", args=[ghost]))
        for route, data in (("wait_room_profile", {"nickname": "X"}), ("wait_room_reaction", {"reaction_key": "clap"})):
            with self.subTest(route=route):
                real = Client().post(reverse(f"liveExam:{route}", args=[self.session.pin]), data)
                fake = Client().post(reverse(f"liveExam:{route}", args=[ghost]), data)
                self.assertEqual((real.status_code, fake.status_code), (403, 403))

    @override_settings(LIVE_PIN_IP_RATE_LIMIT="2/10m")
    def test_rate_limited_pin_entry_does_not_leak_session_theme(self):
        """LXS-06: limit dolanda da POST PIN-i həll edib sessiyanın mövzusunu ``data-live-theme``-də qaytarırdı."""
        LiveSession.objects.filter(pk=self.session.pk).update(host_settings={"theme_key": "winter"})
        ip = "10.66.0.2"
        for _ in range(2):
            Client(REMOTE_ADDR=ip).post(self.pin_entry, {"pin": _fake_pin(self.rng, self.session.pin)})
        limited = Client(REMOTE_ADDR=ip).post(self.pin_entry, {"pin": self.session.pin, "theme": "sweet"})
        self.assertEqual(limited.status_code, 429)
        self.assertNotContains(limited, 'data-live-theme="winter"', status_code=429)


class SharedIpFairnessTest(_RateBase):
    @override_settings(LIVE_PIN_IP_RATE_LIMIT="2/10m")
    def test_signed_player_is_never_locked_out_by_ip_misses(self):
        _player, returning = player_client(self.session, "Back", "lxs-rl-back", REMOTE_ADDR=_NAT_IP)
        for _ in range(3):  # eyni NAT-da kimsə PIN təxmin edir
            Client(REMOTE_ADDR=_NAT_IP).post(self.pin_entry, {"pin": _fake_pin(self.rng, self.session.pin)})
        self.assertEqual(returning.get(self.join_page).status_code, 200)
        self.assertEqual(returning.post(self.join_enter, self._join_payload("Back")).status_code, 200)
        # Qalıq kompromis: yeni tələbə büdcə bərpa olunana qədər gözləyir.
        self.assertEqual(Client(REMOTE_ADDR=_NAT_IP).get(self.join_page).status_code, 429)

    @override_settings(LIVE_EXAM_JOIN_RATE_LIMIT="2/5m")
    def test_cookieless_clients_do_not_share_a_client_bucket(self):
        """LXS-05: cookie-siz klientin «klient» açarı İP idi — bütün NAT bir vedrəni bölüşürdü."""
        statuses = [
            Client(REMOTE_ADDR=_NAT_IP).post(self.pin_entry, {"pin": _fake_pin(self.rng, self.session.pin)}).status_code
            for _ in range(5)
        ]
        self.assertEqual(statuses, [404] * 5)

    @override_settings(LIVE_EXAM_JOIN_RATE_LIMIT="2/5m")
    def test_per_client_bucket_still_stops_one_device(self):
        client = Client(REMOTE_ADDR=_NAT_IP)
        client.get(self.pin_entry)  # etibarlı ``live_client_id`` alır
        statuses = [
            client.post(self.pin_entry, {"pin": _fake_pin(self.rng, self.session.pin)}).status_code for _ in range(3)
        ]
        self.assertEqual(statuses, [404, 404, 429])

    @override_settings(LIVE_EXAM_JOIN_IP_RATE_LIMIT="3/10m")
    def test_reconnects_do_not_consume_the_new_player_budget(self):
        clients = []
        for index in range(3):
            client = Client(REMOTE_ADDR=_NAT_IP)
            self.assertEqual(client.post(self.join_enter, self._join_payload(f"P{index}")).status_code, 200)
            clients.append((client, f"P{index}"))
        for client, nickname in clients:
            for _ in range(2):
                self.assertEqual(client.post(self.join_enter, self._join_payload(nickname)).status_code, 200)
        newcomer = Client(REMOTE_ADDR=_NAT_IP).post(self.join_enter, self._join_payload("Flood"))
        self.assertEqual(newcomer.status_code, 429)
        self.assertEqual(LivePlayer.objects.filter(session=self.session).count(), 3)


class ReactionFanOutTest(_RateBase):
    @override_settings(LIVE_REACTION_SESSION_RATE_LIMIT="3/10s")
    def test_session_wide_reaction_cap(self):
        """LXS-11: hər oyunçu 3/10s — atılan oyunçularla fan-out (reaksiya × soket) sərhədsiz idi."""
        url = reverse("liveExam:wait_room_reaction", kwargs={"pin": self.session.pin})
        statuses = []
        for index in range(5):
            _player, client = player_client(self.session, f"R{index}", f"lxs-react-{index}")
            response = client.post(url, {"reaction_key": "clap"})
            statuses.append(response.status_code)
        self.assertEqual(statuses, [200, 200, 200, 429, 429])
