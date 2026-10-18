"""«Fənləri birləşdir» — FK inventarı qoruyucusu (2026-10-19).

``registrar.Subject``-ə YENİ FK/M2M əlaqəsi əlavə olunanda bu test DÜŞÜR: əlaqəni
``apps/registrar/subject_merge_inventory.RELATIONS``-a strategiya ilə (``repoint`` / ``m2m`` /
``keep``) yazın, unikallıq qaydası varsa ``subject_merge_conflicts``-ə toqquşma yoxlaması əlavə
edin və ``subject_merge_fixture.build_full_source``-a nümunə sətir qoşun.
"""

from django.test import SimpleTestCase

from apps.registrar.subject_merge_inventory import (
    KEEP,
    M2M,
    RELATIONS,
    REPOINT,
    discovered_relations,
    stale_relations,
    unhandled_relations,
)


class SubjectRelationInventoryTest(SimpleTestCase):
    def test_every_subject_relation_is_handled_by_the_merge(self):
        self.assertEqual(
            unhandled_relations(),
            set(),
            "registrar.Subject-ə yeni FK/M2M əlavə olunub, amma fənn birləşdirməsi onu tanımır — "
            "subject_merge_inventory.RELATIONS-a əlavə edin.",
        )

    def test_inventory_has_no_stale_entries(self):
        self.assertEqual(stale_relations(), set())

    def test_hidden_relations_are_discovered(self):
        """``related_name="+"`` əlaqələri (``_meta.related_objects``-də görünmür) də tapılır."""
        found = discovered_relations()
        self.assertIn("registrar.ExamChanceGrant.subject", found)
        self.assertIn("surveys.SurveyResponse.subject", found)
        self.assertIn("exams.StudentGroup.subjects", found)

    def test_strategies_are_known_and_unique(self):
        keys = [item.key for item in RELATIONS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(item.strategy in (REPOINT, M2M, KEEP) for item in RELATIONS))
        self.assertEqual([item.key for item in RELATIONS if item.strategy == M2M], ["exams.StudentGroup.subjects"])
