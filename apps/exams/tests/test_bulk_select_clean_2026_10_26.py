"""Toplu sual önizləməsi — «Yalnız təmiz sualları seç» + «Təmiz: N / M» (sahib 2026-10-26).

«Təmiz» qaydası serverdədir (``meta.is_clean``): xəta/xəbərdarlıq yoxdur, problem
kateqoriyası (dublikat, struktur, balans, düstur, naməlum şəkil) yoxdur; digər «info»
qeydləri sualı natəmiz etmir. Kart ``data-q-clean`` daşıyır, JS yalnız onu oxuyur.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, QuestionBank
from apps.exams.services.bulk_confidence import refresh_question_meta
from apps.exams.services.bulk_workbench import analyze_mcq_bulk
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

_FIVE = ["A) Alma", "B) Armud", "C) Gilas", "D) Heyva", "E) Nar"]


def _question(number, stem, options, answer="Cavab: A"):
    return "\n".join([f"{number}. {stem}", *options, answer])


# 1 — təmiz (5 variant, cavab işarəli) · 2 — 4 variant (sarı xəbərdarlıq) · 3 — D yoxdur (xəta)
# · 4 — təmiz · 5 — 1-in dublikatı DEYİL (fərqli mətn), təmiz
_RAW = "\n\n".join(
    [
        _question(1, "Birinci təmiz sual?", _FIVE),
        _question(2, "Dörd variantlı sual?", _FIVE[:4]),
        _question(3, "Variantı çatışmayan sual?", _FIVE[:3]),
        _question(4, "İkinci təmiz sual?", _FIVE),
        _question(5, "Üçüncü təmiz sual?", _FIVE),
    ]
)
_CLEAN = {1, 4, 5}


def _base_question(**extra):
    question = {
        "text": "Sual mətni?",
        "options": {"A": "Alma", "B": "Armud", "C": "Gilas", "D": "Heyva", "E": "Nar"},
        "correct": ["A"],
        "warnings": [],
    }
    question.update(extra)
    return question


def _warn(w_type, severity="warning"):
    return {"type": w_type, "severity": severity, "msg": w_type}


class IsCleanMetaTests(SimpleTestCase):
    def assert_clean(self, question, expected):
        meta = refresh_question_meta(question)
        self.assertIs(meta["is_clean"], expected, question.get("warnings"))
        self.assertEqual("is-clean" in meta["flags"].split(), expected)

    def test_no_warnings_is_clean(self):
        self.assert_clean(_base_question(), True)

    def test_plain_info_note_keeps_question_clean(self):
        self.assert_clean(_base_question(warnings=[_warn("some_note", "info")]), True)

    def test_duplicates_are_not_clean(self):
        for w_type in ("duplicate_in_import", "already_in_exam"):
            with self.subTest(w_type=w_type):
                self.assert_clean(_base_question(warnings=[_warn(w_type, "error")]), False)

    def test_structure_problems_are_not_clean(self):
        for w_type, severity in (
            ("missing_option", "error"),
            ("option_count_too_low", "error"),
            ("option_count_recommend_5", "warning"),
            ("empty_option_text", "error"),
            ("correct_missing", "error"),
            ("correct_defaulted", "warning"),
        ):
            with self.subTest(w_type=w_type):
                self.assert_clean(_base_question(warnings=[_warn(w_type, severity)]), False)

    def test_balance_notes_are_not_clean_even_at_info_level(self):
        for w_type in ("correct_too_long", "correct_too_short"):
            with self.subTest(w_type=w_type):
                self.assert_clean(_base_question(warnings=[_warn(w_type, "info")]), False)

    def test_formula_issues_are_not_clean(self):
        for w_type in ("formula_too_long", "formula_denied", "formula_fallback"):
            with self.subTest(w_type=w_type):
                self.assert_clean(_base_question(warnings=[_warn(w_type)]), False)
        self.assert_clean(_base_question(formula_fallback=True), False)

    def test_unknown_image_ref_is_not_clean(self):
        self.assert_clean(_base_question(warnings=[_warn("image_ref_unknown")]), False)

    def test_any_warning_or_error_severity_is_not_clean(self):
        for severity in ("warning", "error"):
            with self.subTest(severity=severity):
                self.assert_clean(_base_question(warnings=[_warn("import_source", severity)]), False)

    def test_analysis_counts_clean_questions(self):
        analysis = analyze_mcq_bulk(_RAW)
        flags = [question["meta"]["is_clean"] for question in analysis["parsed"]]
        self.assertEqual(flags, [index in _CLEAN for index in range(1, 6)])
        self.assertEqual(analysis["category_counts"]["clean"], len(_CLEAN))

    def test_duplicate_pair_in_import_is_not_clean(self):
        raw = _question(1, "Eyni sual?", _FIVE) + "\n\n" + _question(2, "Eyni sual?", _FIVE)
        analysis = analyze_mcq_bulk(raw)
        self.assertEqual([q["meta"]["is_clean"] for q in analysis["parsed"]], [False, False])
        self.assertEqual(analysis["category_counts"]["clean"], 0)


class SelectCleanViewTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="select-clean-teacher", email="select-clean@example.com", password="StrongPass123!"
        )
        self.organization = Organization.objects.create(
            name="Select Clean Org",
            slug="select-clean-org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        profile = self.teacher.profile
        profile.organization = self.organization
        profile.organization_type = self.organization.org_type
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
        Membership.objects.update_or_create(
            user=self.teacher,
            organization=self.organization,
            defaults={"role": self.organization.roles.get(name="teacher"), "is_primary": True, "is_active": True},
        )
        self.exam = Exam.objects.create(
            title="Select Clean Exam",
            author=self.teacher,
            organization=self.organization,
            exam_type="test",
            is_active=True,
        )
        self.bank = QuestionBank.objects.create(
            name="Select Clean Bank",
            created_by=self.teacher,
            organization=self.organization,
            default_question_type="test",
        )
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.organization.slug
        session.save()

    def _exam_url(self):
        return reverse("exams:test_question_bank", args=[self.exam.slug])

    def _bank_url(self):
        return reverse("exams:question_bank_bulk_add", args=[self.bank.pk])

    def _assert_preview_controls(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-wb-select-clean", count=1)
        self.assertContains(response, "Yalnız təmiz sualları seç")
        self.assertContains(response, "Təmiz: 3 / 5")
        self.assertContains(response, "exams/js/workbench_select_clean.js")
        for index in range(1, 6):
            flag = "1" if index in _CLEAN else "0"
            self.assertContains(response, f'id="qcard-{index}" data-q-index="{index}"')
            self.assertRegex(
                response.content.decode(),
                rf'id="qcard-{index}"[^>]*data-q-clean="{flag}"',
            )

    def test_exam_preview_renders_select_clean_control_and_count(self):
        response = self.client.post(self._exam_url(), {"action": "preview", "raw_text": _RAW, "language": "az"})
        self._assert_preview_controls(response)

    def test_bank_preview_renders_select_clean_control_and_count(self):
        response = self.client.post(
            self._bank_url(), {"action": "preview", "raw_text": _RAW, "q_format": "test", "language": "az"}
        )
        self._assert_preview_controls(response)

    def test_button_disabled_when_nothing_is_clean(self):
        raw = _question(1, "Dörd variantlı?", _FIVE[:4])
        response = self.client.post(self._exam_url(), {"action": "preview", "raw_text": raw, "language": "az"})
        self.assertContains(response, "Təmiz: 0 / 1")
        self.assertRegex(response.content.decode(), r"data-wb-select-clean\s+title=\"[^\"]*\"\s+disabled")

    def test_docx_binding_warning_refreshes_is_clean(self):
        """Bağlama (DOCX) sonradan xəbərdarlıq əlavə edirsə kart natəmiz olur, sayğac yenilənir."""

        def bind(token, parsed, **scope):
            parsed[0]["warnings"].append(_warn("image_ref_unknown"))
            return parsed

        with patch("apps.exams.views.teacher.question_bank._views_misc.bind_import_manifest", side_effect=bind):
            response = self.client.post(
                self._exam_url(),
                {"action": "preview", "raw_text": _RAW, "language": "az", "math_token": "b" * 32},
            )
        self.assertContains(response, "Təmiz: 2 / 5")
        self.assertRegex(response.content.decode(), r'id="qcard-1"[^>]*data-q-clean="0"')

    def test_exam_save_with_clean_indices_imports_only_clean(self):
        with patch("apps.exams.services.difficulty.schedule_ai_question_difficulty_warmup"):
            response = self.client.post(
                self._exam_url(),
                {
                    "action": "save",
                    "raw_text": _RAW,
                    "selected_indices": ",".join(str(i) for i in sorted(_CLEAN)),
                    "points_payload": "{}",
                    "random_question_count": "0",
                    "default_points": "1",
                    "language": "az",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            sorted(self.exam.questions.values_list("text", flat=True)),
            sorted(["Birinci təmiz sual?", "İkinci təmiz sual?", "Üçüncü təmiz sual?"]),
        )

    def test_bank_save_with_clean_indices_imports_only_clean(self):
        response = self.client.post(
            self._bank_url(),
            {
                "action": "save",
                "raw_text": _RAW,
                "selected_indices": ",".join(str(i) for i in sorted(_CLEAN)),
                "points_payload": "{}",
                "q_format": "test",
                "language": "az",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            sorted(self.bank.library_questions.values_list("text", flat=True)),
            sorted(["Birinci təmiz sual?", "İkinci təmiz sual?", "Üçüncü təmiz sual?"]),
        )
