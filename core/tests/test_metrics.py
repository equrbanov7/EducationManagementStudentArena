"""Tests for core.metrics path normalisation (Faza 4, audit 2026-07-02)."""

from django.test import SimpleTestCase

from core.metrics import _normalise_path


class NormalisePathTests(SimpleTestCase):
    def test_numeric_uuid_pin_rules_unchanged(self):
        self.assertEqual(_normalise_path("/courses/42/detail/"), "/courses/<id>/detail/")
        self.assertEqual(
            _normalise_path("/media/download/some/file.pdf"),
            "/media/download/<path>",
        )
        self.assertEqual(
            _normalise_path("/api/v1/live/ABCD1234EF/state/"),
            "/api/v1/live/<pin>/state/",
        )

    def test_exam_slug_paths_collapse(self):
        self.assertEqual(
            _normalise_path("/exams/riyaziyyat-yekun-2026/attempt/15/"),
            "/exams/<slug>/attempt/<id>/",
        )
        self.assertEqual(
            _normalise_path("/exams/fizika-quiz/start/"),
            "/exams/<slug>/start/",
        )
        self.assertEqual(
            _normalise_path("/exams/kimya-1/attempt/7/result/"),
            "/exams/<slug>/attempt/<id>/result/",
        )
        self.assertEqual(
            _normalise_path("/exams/tarix-imtahani/statistics/"),
            "/exams/<slug>/statistics/",
        )

    def test_exam_static_subpages_preserved(self):
        for static in (
            "assigned",
            "available",
            "code-check",
            "create",
            "groups",
            "my-history",
            "pending-work",
            "question-bank",
        ):
            path = f"/exams/{static}/"
            self.assertEqual(_normalise_path(path), path)

    def test_blog_slugs_collapse(self):
        self.assertEqual(
            _normalise_path("/articles/yeni-il-teqvimi/"),
            "/articles/<slug>/",
        )
        self.assertEqual(
            _normalise_path("/categories/proqramlasdirma/"),
            "/categories/<slug>/",
        )

    def test_organization_slugs_collapse_and_statics_preserved(self):
        self.assertEqual(
            _normalise_path("/organizations/baki-univer/structure/"),
            "/organizations/<slug>/structure/",
        )
        self.assertEqual(
            _normalise_path("/organizations/switch/adnsu/"),
            "/organizations/switch/<slug>/",
        )
        self.assertEqual(_normalise_path("/organizations/select/"), "/organizations/select/")

    def test_idempotent(self):
        once = _normalise_path("/exams/mekteb-testi/attempt/3/")
        self.assertEqual(_normalise_path(once), once)
