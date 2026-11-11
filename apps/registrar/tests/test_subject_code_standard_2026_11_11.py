"""Sahib 2026-11-11: «Fənn kodu səhv düşənləri də. Standart olsun bir» — vahid ``QKU-N``.

Standart olmayan HƏR forma (``SAYT-N``, ``QKU-L…``, ``QKU-MR…``, ``QKU-SRC-…``, başında sıfır, kiçik hərf, boşluq)
növbəti boş ``QKU-N``-ə keçir (kartın id-si dəyişmir, köhnə kod audit-də qalır və açar kimi tapılır); QKU dublikatı
olan kart əvvəl birləşdirilməlidir; kataloq formu yeni qeyri-standart kodu rədd edir, boş kodu özü verir.
"""

from __future__ import annotations

from django.test import RequestFactory, TestCase

from apps.registrar import catalog_actions, subject_codes, subject_recode
from apps.registrar.models import Subject
from core.rls import bypass_rls

from .subject_merge_fixture import SubjectMergeBase

BATCH = "dupsubj-20261111-000000-abcd"


class CodeShapeTest(TestCase):
    def test_only_plain_qku_number_is_standard(self):
        shapes = {
            "QKU-1": "standard",
            "QKU-2766": "standard",
            "QKU-053": "other",
            "qku-53": "case",
            "SAYT-0012": "site",
            "QKU-L2670": "other",
            "QKU-MR123-DE3": "other",
            "QKU-SRC-5ABD462502C4": "other",
            " QKU-5": "whitespace",
            "": "blank",
            None: "blank",
        }
        for code, shape in shapes.items():
            self.assertEqual(subject_codes.code_shape(code), shape, code)
            self.assertEqual(subject_codes.is_standard_code(code), shape == "standard", code)


class RecodeAllTest(SubjectMergeBase):
    def setUp(self):
        with bypass_rls():
            self.plain = Subject.objects.create(organization=self.org, code="QKU-300", name="Alfa")
            self.legacy = Subject.objects.create(organization=self.org, code="QKU-L2670", name="Beta")
            self.site = Subject.objects.create(organization=self.org, code="SAYT-0007", name="Qamma")
            self.twin = Subject.objects.create(organization=self.org, code="QKU-MR085", name="alfa")  # QKU dublikatı
            self.zero = Subject.objects.create(organization=self.org, code="QKU-053", name="Zeta")  # başında sıfır
            self.archived = Subject.objects.create(
                organization=self.org, code="SAYT-0001", name="Delta", is_archived=True, is_active=False
            )

    def test_all_scope_recodes_every_non_standard_card_and_keeps_old_code_findable(self):
        with bypass_rls():
            plan = subject_recode.plan(self.org, scope="all")
            new = {item["old"]: item["new"] for item in plan["items"]}
            self.assertEqual(new["SAYT-0007"], "QKU-301")  # SAYT kartları əvvəl, köhnə nömrə sırası ilə
            self.assertRegex(new["QKU-L2670"], r"^QKU-30[2-9]$")
            self.assertTrue(all(subject_codes.is_standard_code(code) for code in new.values()))
            self.assertEqual(len(set(new.values())), len(new))
            self.assertIn("QKU-053", new)  # qeyri-standart kart ÖZÜNÜN «QKU dublikatı» sayılmır
            self.assertEqual(plan["has_qku_duplicate"], ["QKU-MR085"])
            self.assertEqual(plan["counts"]["archived_skipped"], 1)
            subject_recode.apply_recode(self.org, plan["items"], batch=BATCH)
            self.assertEqual(Subject.objects.get(pk=self.legacy.pk).code, new["QKU-L2670"])
            self.assertEqual(subject_recode.old_code_index(self.org)["QKU-L2670"], str(self.legacy.pk))
            subject_recode.undo_recode(self.org, BATCH)
            self.assertEqual(Subject.objects.get(pk=self.legacy.pk).code, "QKU-L2670")
            self.assertNotIn("QKU-L2670", subject_recode.old_code_index(self.org))

    def test_site_scope_is_unchanged(self):
        with bypass_rls():
            plan = subject_recode.plan(self.org)
        self.assertEqual([item["old"] for item in plan["items"]], ["SAYT-0007"])


class CatalogFormGuardTest(SubjectMergeBase):
    def _save(self, **data):
        request = RequestFactory().post("/x/", {"kind": "core", "ects": "5", **data})
        request.user = self.owner
        with bypass_rls():
            return catalog_actions._save_subject(request, self.org)

    def test_new_card_gets_next_code_and_non_standard_code_is_refused(self):
        with bypass_rls():
            Subject.objects.create(organization=self.org, code="QKU-410", name="Mövcud")
        refused = self._save(code="SAYT-0099", name="Yeni fənn")
        self.assertEqual(refused.status_code, 400)
        self.assertIn(b"nonstandard_code", refused.content)
        self.assertIn(b"QKU-411", refused.content)
        created = self._save(code="", name="Yeni fənn")
        self.assertEqual(created.status_code, 200)
        with bypass_rls():
            self.assertEqual(Subject.objects.get(name="Yeni fənn").code, "QKU-411")
        # köhnə kartın DƏYİŞMƏYƏN qeyri-standart kodu saxlanılır; yeni qeyri-standart koda keçid rədd olunur
        kept = self._save(id=str(self.target.pk), code=self.target.code, name="VoIP sistemləri (yeni ad)")
        self.assertEqual(kept.status_code, 200)
        changed = self._save(id=str(self.target.pk), code="ABC-1", name="VoIP sistemləri")
        self.assertEqual(changed.status_code, 400)

    def test_organization_without_the_standard_is_untouched(self):
        saved = self._save(code="MATH101", name="Riyaziyyat")
        self.assertEqual(saved.status_code, 200)
