"""`transcript.issue` — kim transkript / arayış verə bilər (sahib 2026-10-19).

Matris: org-wide açar daşıyanlar (Tədris şöbəsinin müdiri, Tələbə xidmətləri, RİM rəhbəri) və köhnə
``course.edit`` yolu (sahib, prorektor) istənilən tələbəyə; dekan / dekan müavini YALNIZ öz fakültəsinə
(kənarı 404); açarsız rollar (Tədris şöbəsi əməkdaşı, müəllim, tələbə) 404. View-as rejimində 403.
"""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.permissions import get_permission_label
from apps.registrar import document_access, pdf_views
from apps.verification.models import DocType, DocumentSeal
from core.rls import bypass_rls

from .world_documents import TEMPLATE_ISSUERS, build_documents_world, get_transcript, post_arayis


class TemplateGrantTest(TestCase):
    def test_key_is_in_the_catalog_with_a_label(self):
        self.assertTrue(get_permission_label("transcript.issue"))

    def test_template_roles_carry_the_key(self):
        roles = {role["name"]: role.get("permissions", []) for role in UNIVERSITY_ROLES}
        for name in TEMPLATE_ISSUERS:
            permissions = roles[name]
            self.assertTrue("transcript.issue" in permissions or "*" in permissions, name)
        for name in ("teacher", "student", "teaching_office_staff", "chair_head", "hr"):
            if name in roles:
                self.assertNotIn("transcript.issue", roles[name], name)

    def test_migration_grants_existing_tenants(self):
        from importlib import import_module

        from django.apps import apps as global_apps
        from django.db import connection

        migration = import_module("apps.verification.migrations.0004_seed_transcript_issue_permission")
        world = build_documents_world("qkumg")
        with bypass_rls():
            role = world["org"].roles.get(name="dean")
            role.permissions = [key for key in role.permissions if key != "transcript.issue"]
            role.save(update_fields=["permissions"])

            class _Editor:
                def __init__(self):
                    self.connection = connection

                def execute(self, sql):
                    with connection.cursor() as cursor:
                        cursor.execute(sql)

            migration.forward(global_apps, _Editor())
            migration.forward(global_apps, _Editor())  # idempotent
            role.refresh_from_db()
        self.assertEqual(role.permissions.count("transcript.issue"), 1)


class TranscriptIssueMatrixTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_documents_world("qkutm")

    def _status(self, user, record=None):
        return get_transcript(self.w, self.w[user] if isinstance(user, str) else user, record=record).status_code

    def test_org_wide_issuers_get_any_student(self):
        for name in ("owner", "to_head", "txm", "rim", "vrector"):
            with self.subTest(role=name):
                self.assertEqual(self._status(name), 200)
                self.assertEqual(self._status(name, self.w["record2"]), 200)

    def test_dean_and_vice_dean_only_their_faculty(self):
        for name in ("dean", "vdean"):
            with self.subTest(role=name):
                self.assertEqual(self._status(name), 200)
                self.assertEqual(self._status(name, self.w["record2"]), 404)

    def test_roles_without_the_key_get_404(self):
        for name in ("office", "teacher", "student", "s2", "unit_staff"):
            with self.subTest(role=name):
                self.assertEqual(self._status(name), 404)

    def test_new_path_records_the_real_issuer(self):
        self.assertEqual(self._status("txm"), 200)
        with bypass_rls():
            seal = DocumentSeal.objects.filter(doc_type=DocType.TRANSCRIPT, subject_user=self.w["student"]).first()
        self.assertEqual(seal.issued_by_id, self.w["txm"].pk)

    def test_scope_helper_matches_the_view(self):
        org = self.w["org"]
        self.assertTrue(document_access.can_issue(self.w["dean"], org))
        self.assertFalse(document_access.can_issue(self.w["teacher"], org))
        self.assertFalse(document_access.can_issue(AnonymousUser(), org))
        ids = set(document_access.issuable_records(self.w["dean"], org).values_list("pk", flat=True))
        self.assertEqual(ids, {self.w["record"].pk})


class DocumentViewAsTest(TestCase):
    """View-as: buraxılış möhür YAZIR — transkript (GET) və arayış (POST) 403, möhür yaranmır."""

    @classmethod
    def setUpTestData(cls):
        cls.w = build_documents_world("qkuva")

    def _request(self, method, *, ajax=True):
        factory = RequestFactory()
        headers = {"HTTP_ACCEPT": "application/pdf, application/json"} if ajax else {"HTTP_ACCEPT": "text/html"}
        request = factory.get("/", **headers) if method == "get" else factory.post("/", {"place": ""}, **headers)
        request.user = self.w["txm"]
        request.real_user = self.w["owner"]
        request.is_view_as = True
        request.organization = self.w["org"]
        request._dont_enforce_csrf_checks = True
        return request

    def test_transcript_and_certificate_are_blocked(self):
        response = pdf_views.student_transcript_pdf(self._request("get"), pk=self.w["record"].pk)
        self.assertEqual(response.status_code, 403)
        response = pdf_views.student_enrollment_certificate_pdf(self._request("post"), pk=self.w["record"].pk)
        self.assertEqual(response.status_code, 403)
        with bypass_rls():
            self.assertFalse(DocumentSeal.objects.filter(subject_user=self.w["student"]).exists())

    def test_view_as_flag_and_normal_mode(self):
        self.assertTrue(document_access.blocked_by_view_as(self._request("get")))
        self.assertEqual(post_arayis(self.w, self.w["txm"]).status_code, 200)  # adi rejimdə işləyir

    def test_plain_links_get_the_html_403_page_not_json(self):
        """Adi link (yeni tab) xam JSON görməməlidir — PermissionDenied → layihənin 403 səhifəsi."""
        from unittest import mock

        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            pdf_views.student_transcript_pdf(self._request("get", ajax=False), pk=self.w["record"].pk)
        with self.assertRaises(PermissionDenied):
            pdf_views.student_enrollment_certificate_pdf(self._request("post", ajax=False), pk=self.w["record"].pk)
        with mock.patch("apps.registrar.public.STUDENT_TRANSCRIPT_SELF_SERVICE", True):
            request = self._request("get", ajax=False)
            request.user = self.w["student"]
            with self.assertRaises(PermissionDenied):
                pdf_views.my_transcript_pdf(request)
        with bypass_rls():
            self.assertFalse(DocumentSeal.objects.filter(subject_user=self.w["student"]).exists())

    def test_handler403_renders_html(self):
        from core.views import handler403

        response = handler403(self._request("get", ajax=False))
        self.assertEqual(response.status_code, 403)
        self.assertIn("text/html", response["Content-Type"])
