"""QA-1 F17: daxil olmuş istifadəçinin gördüyü səhifələr (jurnal, kabinet) ``noindex`` — ictimai yol kimi görünsə də."""

from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase

from core.context_processors import seo_context


def _robots(path, *, authenticated):
    request = RequestFactory().get(path)
    request.user = SimpleNamespace(is_authenticated=authenticated)
    return seo_context(request)["seo"]["robots"]


class PrivatePagesAreNotIndexedTest(SimpleTestCase):
    def test_journal_path_is_noindex_even_when_anonymous(self):
        self.assertEqual(_robots("/jurnal/123/", authenticated=False), "noindex, nofollow")

    def test_signed_in_user_gets_noindex_on_any_page(self):
        self.assertEqual(_robots("/some-public-looking/page/", authenticated=True), "noindex, nofollow")

    def test_anonymous_public_page_stays_indexable(self):
        self.assertEqual(_robots("/", authenticated=False), "index, follow")
