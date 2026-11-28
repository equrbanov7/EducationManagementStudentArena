"""Role-tour actions and transition images stay inside the reference account's grants."""

import unittest

from .recorded_permissions import chapter_flags
from .scenes import role_scenes


def chapter(section, *labels):
    return {"section": section, "title": " · ".join(labels)}


class RecordedPermissionsTests(unittest.TestCase):
    def test_room_listing_reports_designation_and_administration_are_distinct(self):
        chapters = [
            chapter("external-rooms", "İmtahan zalları"),
            chapter("external-rooms", "İmtahan zalları", "Hesabatlar"),
            chapter("external-rooms", "İmtahan zalları", "Bütün otaqları göstər"),
            chapter("external-rooms", "İmtahan zalları", "Zal idarəetmə"),
        ]
        self.assertEqual(chapter_flags(chapters[:1]), {"faq_supervise_rooms"})
        self.assertEqual(chapter_flags(chapters[:2]), {"faq_supervise_rooms", "faq_exam_center"})
        self.assertEqual(
            chapter_flags(chapters),
            {"faq_supervise_rooms", "faq_exam_center", "faq_designate_exam_halls", "faq_manage_exam_rooms"},
        )

    def test_read_only_midterm_vs_writing_in_own_journal_and_central_scores(self):
        self.assertEqual(
            chapter_flags([chapter("external-journal", "Elektron jurnal", "Jurnalı aç", "Midterm")]), set()
        )
        self.assertEqual(
            chapter_flags([chapter("external-journal", "Elektron jurnal", "Öz jurnalını aç", "Midterm")]),
            {"faq_write_own_journal"},
        )
        self.assertEqual(
            chapter_flags([chapter("exam-score-entry", "İmtahan balının daxil edilməsi", "MİDTERM")]),
            {"faq_enter_paper_scores"},
        )

    def test_nested_control_and_its_transition_frame_are_excluded_together(self):
        row = {
            "id": "001",
            "key": "groups-registry",
            "href": "?section=groups-registry",
            "label": "Qruplar",
            "ok": True,
            "opened": [
                {"label": "Yeni qrup", "frame": "denied.jpg"},
                {"label": "Qrupun adı", "parent": "Yeni qrup", "frame": "field.jpg"},
                {"label": "KOD ↕", "frame": "order.jpg", "before": "denied.jpg"},
                {"label": "A-001 qrupuna tələbə əlavə et", "frame": "placement.jpg"},
            ],
        }
        excluded = []
        scenes = role_scenes(
            "synthetic", [row], [], example={"sections": ["groups-registry"], "capabilities": []}, excluded=excluded
        )
        self.assertEqual([x["title"] for x in scenes], ["Qruplar", "Qruplar · KOD ↕"])
        self.assertEqual(scenes[-1]["before"], scenes[-1]["after"])
        self.assertEqual(len(excluded), 3)
        self.assertEqual(chapter_flags(scenes), set())

    def test_an_inaccessible_workload_workspace_contributes_no_landing_image(self):
        row = {
            "id": "001",
            "key": "workload-center",
            "label": "Dərs yükü mərkəzi",
            "href": "?section=workload-center",
            "ok": True,
            "opened": [],
        }
        excluded = []
        scenes = role_scenes(
            "synthetic", [row], [], example={"sections": ["workload-center"], "capabilities": []}, excluded=excluded
        )
        self.assertEqual(scenes, [])
        self.assertEqual(len(excluded), 1)
