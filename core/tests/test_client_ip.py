"""P2-6 reqressiya: `X-Forwarded-For` TƏK yerdə və SAĞDAN oxunur.

2026-09-02 auditi: eyni başlıq beş yerdə müstəqil parse olunurdu.  İki yer
(monitoring) sağdan — düzgün — oxuyurdu, qalanları isə ƏN SOL üzvü götürürdü.
Sol üzvü tamamilə müştəri yazır, yəni `X-Forwarded-For: 1.2.3.4` göndərməklə
per-IP limitlər (login, OTP, contact, sınaq imtahanı) və barmaq izləri
saxtalaşdırıla bilirdi.
"""

from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase, override_settings

from core.utils import get_client_ip


class ClientIpTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, xff=None, remote="10.0.0.9"):
        headers = {"REMOTE_ADDR": remote}
        if xff is not None:
            headers["HTTP_X_FORWARDED_FOR"] = xff
        return self.factory.get("/", **headers)

    def test_no_header_falls_back_to_remote_addr(self):
        self.assertEqual(get_client_ip(self._request()), "10.0.0.9")

    def test_single_member_is_used(self):
        self.assertEqual(get_client_ip(self._request("203.0.113.7")), "203.0.113.7")

    def test_spoofed_left_member_is_ignored(self):
        # Hücumçu soldakı üzvü özü yazır; nginx öz gördüyü peer-i sona qoyur.
        request = self._request("1.2.3.4, 203.0.113.7")
        self.assertEqual(get_client_ip(request), "203.0.113.7")

    def test_many_spoofed_members_are_ignored(self):
        request = self._request("9.9.9.9, 8.8.8.8, 7.7.7.7, 203.0.113.7")
        self.assertEqual(get_client_ip(request), "203.0.113.7")

    @override_settings(TRUSTED_PROXY_HOPS=2)
    def test_two_trusted_hops_skip_the_edge_member(self):
        request = self._request("1.2.3.4, 203.0.113.7, 172.20.0.5")
        self.assertEqual(get_client_ip(request), "203.0.113.7")

    def test_blank_members_are_skipped(self):
        self.assertEqual(get_client_ip(self._request(" , 203.0.113.7 , ")), "203.0.113.7")

    def test_every_call_site_delegates_to_the_shared_helper(self):
        """Modullarda müstəqil XFF parse-i qalmamalıdır."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        offenders = []
        for path in list((root / "apps").rglob("*.py")) + list((root / "core").rglob("*.py")):
            name = path.name
            if "/tests/" in str(path) or "/migrations/" in str(path):
                continue
            if name.startswith("test_") or name in {"tests.py", "factories.py"}:
                continue
            if path == root / "core" / "utils.py":
                continue
            if "HTTP_X_FORWARDED_FOR" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(root)))
        self.assertEqual(offenders, [], f"XFF hələ də müstəqil parse olunur: {offenders}")
