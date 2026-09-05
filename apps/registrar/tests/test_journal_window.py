"""Dərs pəncərəsi — QA 2026-09-05 P1-8 reqressiya qapısı.

Pəncərə YALNIZ sütunları kəsir: qayıb saatı, giriş balı və buraxılış qərarı
həmişə BÜTÜN dərslər üzrə hesablanmalıdır.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.registrar.journal_window import resolve_window, window_meta


class ResolveWindowTest(SimpleTestCase):
    def test_no_limit_shows_everything(self):
        self.assertEqual(resolve_window(226, limit=None, offset=0), (226, 0))
        self.assertEqual(resolve_window(226, limit=0, offset=40), (226, 0))

    def test_offset_is_clamped_into_range(self):
        self.assertEqual(resolve_window(30, limit=20, offset=100), (20, 10))
        self.assertEqual(resolve_window(30, limit=20, offset=-5), (20, 0))

    def test_window_slice(self):
        self.assertEqual(resolve_window(226, limit=20, offset=20), (20, 20))


class WindowMetaTest(SimpleTestCase):
    def test_label_range_reads_ascending_when_newest_first(self):
        meta = window_meta(total=32, shown=20, size=20, offset=0, newest_first=True)
        self.assertEqual((meta["first_seq"], meta["last_seq"]), (13, 32))
        self.assertTrue(meta["enabled"])
        self.assertFalse(meta["has_prev"])
        self.assertTrue(meta["has_next"])

    def test_chronological_order_labels(self):
        meta = window_meta(total=32, shown=20, size=20, offset=0, newest_first=False)
        self.assertEqual((meta["first_seq"], meta["last_seq"]), (1, 20))

    def test_disabled_when_everything_fits(self):
        meta = window_meta(total=8, shown=8, size=20, offset=0, newest_first=True)
        self.assertFalse(meta["enabled"])
        self.assertFalse(meta["has_next"])
