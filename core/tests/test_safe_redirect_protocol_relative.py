"""core.helpers._safe_same_origin_redirect_path — protokol-nisbi yol (2026-09-29, LX-SEC LXS-14)."""

from django.test import RequestFactory, SimpleTestCase

from core.helpers import _safe_same_origin_redirect_path


class ProtocolRelativeRedirectTest(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/", HTTP_HOST="testserver")

    def test_same_host_url_with_double_slash_path_is_rejected(self):
        for candidate in ("http://testserver//evil.com/x", "http://testserver/\\evil.com", "//evil.com", "/\\evil.com"):
            with self.subTest(candidate=candidate):
                self.assertEqual(_safe_same_origin_redirect_path(self.request, candidate), "")

    def test_normal_internal_paths_still_work(self):
        self.assertEqual(_safe_same_origin_redirect_path(self.request, "/exams/?page=2#top"), "/exams/?page=2#top")
        self.assertEqual(_safe_same_origin_redirect_path(self.request, "http://testserver/a/b/"), "/a/b/")
        self.assertEqual(_safe_same_origin_redirect_path(self.request, ""), "")
