"""«Fənləri birləşdir» — HTTP qapısı (403/404), önizləmə → təsdiq, axtarış, dublikat qrupları, kataloq düyməsi."""

from __future__ import annotations

from django.urls import reverse

from apps.audit.models import AuditLog
from apps.registrar.models import CourseOffering, Subject
from core.rls import bypass_rls

from .subject_merge_fixture import REASON, SubjectMergeBase

URLS = ("subject_merge_lookup", "subject_merge_groups", "subject_merge_preview", "subject_merge_apply")


class MergeViewsTest(SubjectMergeBase):
    def _call(self, user, name, data=None):
        client = self.client_for(user)
        url = reverse(f"registrar:{name}")
        if name in ("subject_merge_lookup", "subject_merge_groups"):
            return client.get(url, data or {})
        return client.post(url, data or {})

    def test_missing_permission_is_403_and_unit_scope_is_404(self):
        for name in URLS:
            with self.subTest(name=name):
                self.assertEqual(self._call(self.viewer, name).status_code, 403)
                self.assertEqual(self._call(self.dean, name).status_code, 404)

    def test_preview_then_apply_with_digest(self):
        offering = self.offering(self.source, self.group1)
        data = {"target": str(self.target.pk), "sources": [str(self.source.pk)]}
        response = self._call(self.office, "subject_merge_preview", data)
        self.assertEqual(response.status_code, 200, response.content)
        preview = response.json()["preview"]
        self.assertTrue(preview["can_apply"])

        bad = self._call(self.office, "subject_merge_apply", {**data, "reason": REASON, "digest": "0" * 64})
        self.assertEqual(bad.status_code, 409)
        self.assertEqual(bad.json()["error"], "drift")

        short = self._call(self.office, "subject_merge_apply", {**data, "reason": "qısa", "digest": preview["digest"]})
        self.assertEqual(short.status_code, 400)

        response = self._call(
            self.office, "subject_merge_apply", {**data, "reason": REASON, "digest": preview["digest"]}
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertIn("QA-SM-S → QA-SM-T", body["message"])
        with bypass_rls():
            self.assertEqual(CourseOffering.objects.get(pk=offering.pk).subject_id, self.target.pk)
        self.assertTrue(Subject.objects.get(pk=self.source.pk).is_archived)
        entry = AuditLog.objects.get(pk=body["audit_id"])
        self.assertEqual(entry.user_id, self.office.pk)

    def test_conflict_preview_lists_blocking_items(self):
        self.offering(self.source, self.group1)
        self.offering(self.target, self.group1)
        data = {"target": str(self.target.pk), "sources": [str(self.source.pk)]}
        preview = self._call(self.office, "subject_merge_preview", data).json()["preview"]
        self.assertFalse(preview["can_apply"])
        response = self._call(
            self.office, "subject_merge_apply", {**data, "reason": REASON, "digest": preview["digest"]}
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "conflicts")

    def test_lookup_and_duplicate_groups(self):
        self.offering(self.source, self.group1)
        lookup = self._call(self.office, "subject_merge_lookup", {"q": "QA-SM", "limit": 10}).json()
        self.assertEqual({item["id"] for item in lookup["results"]}, {str(self.target.pk), str(self.source.pk)})
        groups = self._call(self.office, "subject_merge_groups").json()["groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["target"], str(self.source.pk))  # ən çox açılışı olan saxlanılması təklif olunur
        self.assertEqual({item["id"] for item in groups[0]["subjects"]}, {str(self.target.pk), str(self.source.pk)})
        self.assertEqual({item["ects"] for item in groups[0]["subjects"]}, {5})

    def test_wrong_method(self):
        client = self.client_for(self.office)
        self.assertEqual(client.get(reverse("registrar:subject_merge_preview")).status_code, 405)


class CatalogButtonTest(SubjectMergeBase):
    def _section(self, user):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "subject-catalog"})
        return self.client_for(user).get(url)

    def test_button_only_for_org_wide_manager(self):
        response = self._section(self.office)
        self.assertEqual(response.status_code, 200)
        html = (
            response.json().get("html", "")
            if response["Content-Type"].startswith("application/json")
            else response.content.decode()
        )
        self.assertIn("data-sm-open", html)
        self.assertIn("tofSubjectMergeDialog", html)
        self.assertIn("subject_merge.js", html)
        self.assertIn(reverse("registrar:subject_merge_preview"), html)
        # «VoIP» / «Vo İP» — kataloqun dublikat açarı birləşmə qrupları ilə eynidir → sətirdə «Birləşdir»
        self.assertIn(f'data-sm-subject="{self.source.pk}"', html)
        dean = self._section(self.dean)
        dean_html = (
            dean.json().get("html", "")
            if dean["Content-Type"].startswith("application/json")
            else dean.content.decode()
        )
        self.assertNotIn("data-sm-open", dean_html)
