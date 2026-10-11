"""URL auditi WP9a (2026-10-10) — silinmiş ölü marşrutlar bir daha qeydiyyatdan keçməsin.

Hər qrup üçün bir reqressiya: adı ``reverse()`` ilə tapılmır (``NoReverseMatch``), yolu
``resolve()`` ilə həll olunmur (``Resolver404``). Əvəz edən canlı marşrutlar isə qalır.
Mənbə: audit ``wp7_report.md`` §3 (A1–A4, A8–A10, A13–A16).
"""

from django.test import TestCase
from django.urls import NoReverseMatch, Resolver404, resolve, reverse

_PIN = "ABC123"
_UUID = "8b4f2c1e-4a8e-4f5e-9c3d-2a1b0c9d8e7f"


class DeadRoutesGoneTest(TestCase):
    def assert_names_gone(self, names, **kwargs):
        for name in names:
            with self.subTest(name=name):
                with self.assertRaises(NoReverseMatch):
                    reverse(name, kwargs=kwargs or None)

    def assert_paths_gone(self, paths):
        for path in paths:
            with self.subTest(path=path):
                with self.assertRaises(Resolver404):
                    resolve(path)

    def test_a1_blog_legacy_aliases_gone(self):
        self.assert_paths_gone(
            [
                "/blog/",
                "/blog/about/",
                "/blog/technology/",
                "/blog/subscribe/",
                "/blog/posts/create/",
                "/blog/posts/some-slug/",
                "/blog/post/1/edit/",
                "/blog/post/1/review/",
                "/blog/post/1/delete/",
                "/blog/category/some-slug/",
                "/blog/questions/",
            ]
        )

    def test_a2_blog_questions_pages_gone(self):
        self.assert_names_gone(["create_question", "my_questions", "questions_i_can_see"])
        self.assert_paths_gone(["/questions/", "/questions/my/", "/questions/create/"])

    # A3 `exmas/` QALIR (imtahan zalı yazı səhvi, 2026-07-06) — test_final_exam_center_page yoxlayır.

    def test_a4_live_exam_duplicates_gone(self):
        self.assert_names_gone(
            [
                "liveExam:host_lobby",
                "liveExam:host_start_game",
                "liveExam:host_next_question",
                "liveExam:host_finish",
                "live_exam_api_v1:state_json",
            ],
            pin=_PIN,
        )
        self.assert_paths_gone(
            [
                f"/live/host/{_PIN}/",
                f"/live/host/{_PIN}/start/",
                f"/live/host/{_PIN}/next/",
                f"/live/host/{_PIN}/finish/",
                f"/api/v1/live/{_PIN}/state/",
            ]
        )
        # Canlı əvəzlər qalır.
        for name in ("start_game", "next_question", "finish_game", "state_json", "host_presentation"):
            with self.subTest(alive=name):
                self.assertTrue(reverse(f"liveExam:{name}", kwargs={"pin": _PIN}))

    def test_a8_course_list_pages_gone(self):
        self.assert_names_gone(["courses:my_courses", "courses:student_courses"])
        self.assert_paths_gone(["/courses/my-courses/", "/courses/my-enrolled/"])

    def test_a9_assignment_roster_endpoints_gone(self):
        self.assert_names_gone(["assignments:search_students"])
        self.assert_names_gone(["assignments:remove_student_from_assignment"], pk=1)
        self.assert_paths_gone(["/assignments/search-students/", "/assignments/1/remove-student/"])
        self.assertTrue(reverse("assignments:search_groups"))
        self.assertTrue(reverse("assignments:students_by_groups"))

    def test_a10_lab_publish_and_answers_gone(self):
        self.assert_names_gone(["labs:publish_lab", "labs:submission_answers"], pk=1)
        self.assert_paths_gone(["/labs/1/publish/", "/labs/submissions/1/answers/"])

    def test_a13_workload_chairs_gone(self):
        self.assert_names_gone(["workload:chairs"])
        self.assert_paths_gone(["/ders-yuku/kafedralar/"])

    def test_a14_announcement_short_link_gone(self):
        self.assert_names_gone(["announcements:detail"], announcement_id=_UUID)
        self.assert_paths_gone([f"/elanlar/{_UUID}/"])

    def test_a15_notification_standalone_pages_gone(self):
        self.assert_names_gone(["notifications:notification_list", "notifications:unread_count"])
        self.assert_names_gone(["notifications:notification_detail", "notifications:notification_mark_unread"], pk=1)
        self.assert_paths_gone(
            ["/notifications/", "/notifications/1/", "/notifications/1/unread/", "/notifications/unread-count/"]
        )
        # Kabinet bölməsinin işlətdiyi əməliyyat ucları qalır.
        self.assertTrue(reverse("notifications:notification_mark_read", kwargs={"pk": 1}))
        self.assertTrue(reverse("notifications:notification_mark_all_read"))
        self.assertTrue(reverse("notifications:notification_delete", kwargs={"pk": 1}))
        self.assertTrue(reverse("notifications:notification_bulk_delete"))

    def test_a16_monitoring_overview_gone(self):
        self.assert_names_gone(["monitoring:overview"])
        self.assert_paths_gone(["/api/superadmin/monitoring/overview/"])
        self.assertTrue(reverse("monitoring:summary"))
