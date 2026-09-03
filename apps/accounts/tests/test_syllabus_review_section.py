"""«Sillabus təsdiqi» bölməsi — render müqaviləsi, əhatə qapısı, qərar səthi.

Nəyi qoruyur
------------
1. **Sol sidebar QALIR.** Ekran profil shell-inin bölməsidir, ayrıca tam səhifə
   deyil (sahibin açıq tələbi).
2. **FAIL-CLOSED əhatə.** Başqa kafedranın versiya id-si ilə nə baxış açılır,
   nə qərar verilir — 404. İcazəsi olub əhatəsi olmayan istifadəçi «əhatə
   təyin edilməyib» boş vəziyyətini görür.
3. **SƏBƏB MƏCBURİDİR.** `revise`/`reject` üçün qısa səbəb 400 ilə dayanır və
   status DƏYİŞMİR.
4. **APPROVED KİLİDLİDİR.** Təsdiqlənmiş versiyaya ikinci qərar 409 verir.
5. **JS bağları.** Şablon ilə xarici JS arasındakı `data-*` körpüsü səssizcə
   sınır — burada kilidlənir.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.syllabus import services
from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.models import SyllabusVersion
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)
from core.constants import RoleScopeType

User = get_user_model()

PASSWORD = "StrongPass123!"
TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]

#: `syllabus_review.js` mühərrikinin bağlandığı köklər.
ENGINE_HOOKS = (
    "data-syllabus-review",
    "data-open-url",
    "data-decision-url",
    "data-syl-tab",
    "data-syl-search",
    'data-syl-filter="status"',
    'data-syl-filter="sort"',
    "data-syl-open=",
    "data-syl-panel",
    "data-syl-modal",
    "data-syl-reason",
    "data-syl-toast",
)

#: `syllabus_review_panel.js` render-inin doldurduğu yuvalar.
PANEL_HOOKS = (
    "data-syl-rv-code",
    "data-syl-rv-name",
    "data-syl-rv-status",
    "data-syl-rv-meta",
    "data-syl-rv-note",
    "data-syl-rv-general",
    'data-syl-rv-pane="sections"',
    "data-syl-rv-diffs",
    "data-syl-rv-timeline",
    "data-syl-rv-foot",
)


def _submit(org, stack, teacher):
    actor = services.resolve_actor(teacher, org)
    offering = make_offering(org, stack, teacher)
    _syllabus, version = services.create_draft(
        organization=org,
        subject=stack["subject"],
        period=stack["period"],
        actor=actor,
        offering=offering,
        program=stack["program"],
        chair_unit=stack["chair"],
        author=teacher,
        plan_hours=dict(PLAN_HOURS),
    )
    for section_id, data in complete_section_data().items():
        if section_id in {"prev", "send"}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=actor)
    return services.submit(version=version, actor=actor)


class SyllabusReviewSectionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("syl-review")
        cls.teacher = User.objects.create_user("rv_teacher", "rv_teacher@x.test", PASSWORD)
        cls.other_teacher = User.objects.create_user("rv_teacher2", "rv_teacher2@x.test", PASSWORD)
        cls.chair = User.objects.create_user("rv_chair", "rv_chair@x.test", PASSWORD)
        cls.naked = User.objects.create_user("rv_naked", "rv_naked@x.test", PASSWORD)

        cls.stack = make_academic_stack(cls.org, code="RVA101")
        cls.other_stack = make_academic_stack(cls.org, code="RVB202")
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)
        activate_member(cls.org, cls.other_teacher, "teacher_b", permissions=TEACHER_PERMS)
        activate_member(
            cls.org,
            cls.chair,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        # ⚠️ İcazə var, struktur əhatəsi yoxdur — README §3.3 `noscope`.
        activate_member(
            cls.org, cls.naked, "chair_no_scope", permissions=CHAIR_PERMS, level=70, scope_type=RoleScopeType.UNIT
        )

        cls.version = _submit(cls.org, cls.stack, cls.teacher)
        cls.foreign_version = _submit(cls.org, cls.other_stack, cls.other_teacher)

    def _client(self, user) -> Client:
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _html(self, user, **params) -> str:
        response = self._client(user).get(reverse("accounts:profile"), {"section": "syllabus-review", **params})
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    def _post(self, user, name, version, payload=None):
        return self._client(user).post(
            reverse(name, kwargs={"version_id": str(version.pk)}),
            data=json.dumps(payload or {}),
            content_type="application/json",
        )

    # ── Profil shell-i ─────────────────────────────────────────────────────

    def test_screen_renders_inside_the_profile_shell_with_the_sidebar(self):
        """Təsdiq ekranı ayrıca tam səhifə DEYİL — sidebar qalır."""
        html = self._html(self.chair)

        self.assertIn('data-profile-section-panel="syllabus-review"', html)
        self.assertIn('data-section="syllabus-review"', html)

    def test_teacher_never_sees_the_review_section(self):
        """`syllabus.edit` qərar səthini AÇMIR — açar ayrıdır."""
        html = self._html(self.teacher)

        self.assertNotIn("data-syllabus-review", html)
        self.assertNotIn('data-section="syllabus-review"', html)

    # ── Əhatə ──────────────────────────────────────────────────────────────

    def test_chair_queue_lists_only_its_own_department(self):
        html = self._html(self.chair)

        self.assertIn(f'data-syl-open="{self.version.pk}"', html)
        self.assertNotIn(f'data-syl-open="{self.foreign_version.pk}"', html)

    def test_actor_without_structure_scope_gets_the_empty_state(self):
        """Əhatəsizlik «bütün universitet» DEYİL."""
        html = self._html(self.naked)

        self.assertIn("Təşkilati əhatə təyin edilməmişdir", html)
        self.assertNotIn(f'data-syl-open="{self.version.pk}"', html)

    def test_opening_a_foreign_version_is_rejected(self):
        response = self._post(self.chair, "accounts:syllabus_review_open", self.foreign_version)

        self.assertEqual(response.status_code, 404)
        self.foreign_version.refresh_from_db()
        self.assertEqual(self.foreign_version.status, SyllabusStatus.SUBMITTED.value)

    def test_deciding_on_a_foreign_version_is_rejected(self):
        response = self._post(
            self.chair,
            "accounts:syllabus_decision",
            self.foreign_version,
            {"action": "approve"},
        )

        self.assertEqual(response.status_code, 404)
        self.foreign_version.refresh_from_db()
        self.assertIsNone(self.foreign_version.approved_at)

    # ── Baxışın açılması ───────────────────────────────────────────────────

    def test_opening_the_panel_moves_submitted_into_review(self):
        version = _submit(self.org, make_academic_stack(self.org, code="RVC303"), self.teacher)
        version.syllabus.chair_unit = self.stack["chair"]
        version.syllabus.save(update_fields=["chair_unit"])

        response = self._post(self.chair, "accounts:syllabus_review_open", version)

        self.assertEqual(response.status_code, 200)
        version.refresh_from_db()
        self.assertEqual(version.status, SyllabusStatus.REVIEW.value)

    def test_panel_payload_carries_sections_diff_and_timeline(self):
        payload = self._post(self.chair, "accounts:syllabus_review_open", self.version).json()

        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["sections"]), 8)
        self.assertIn("rows", payload["diff"])
        self.assertTrue(payload["timeline"])
        # İlk təsdiq namizədidir → müqayisə bazası yoxdur.
        self.assertFalse(payload["has_base"])

    def test_first_candidate_marks_no_section_as_changed(self):
        """Baza yoxdursa «dəyişib» nişanı VERİLMİR — yoxsa bütün kartlar yanardı."""
        payload = self._post(self.chair, "accounts:syllabus_review_open", self.version).json()

        self.assertEqual([row["id"] for row in payload["sections"] if row["changed"]], [])

    # ── Səbəb məcburiliyi ──────────────────────────────────────────────────

    def test_revision_without_a_reason_is_refused_and_status_is_unchanged(self):
        response = self._post(
            self.chair, "accounts:syllabus_decision", self.version, {"action": "revise", "reason": "qısa"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "transition.reason_required")
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, SyllabusStatus.SUBMITTED.value)

    def test_rejection_without_a_reason_is_refused(self):
        response = self._post(self.chair, "accounts:syllabus_decision", self.version, {"action": "reject"})

        self.assertEqual(response.status_code, 400)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, SyllabusStatus.SUBMITTED.value)

    def test_revision_with_a_reason_records_it_on_the_version(self):
        reason = "Həftəlik mövzular tədris planı ilə uyğunlaşdırılmalıdır."
        response = self._post(
            self.chair,
            "accounts:syllabus_decision",
            self.version,
            {"action": "revise", "reason": reason, "sections": {"week": "11-ci həftə boşdur"}},
        )

        self.assertEqual(response.status_code, 200)
        version = SyllabusVersion.objects.get(pk=self.version.pk)
        self.assertEqual(version.status, SyllabusStatus.REVISION.value)
        self.assertEqual(version.decision_reason, reason)
        review = version.reviews.filter(decision="revision").first()
        self.assertEqual(review.section_comments, {"week": "11-ci həftə boşdur"})

    # ── APPROVED kilidi ────────────────────────────────────────────────────

    def test_approved_version_is_locked_against_further_decisions(self):
        version = _submit(self.org, make_academic_stack(self.org, code="RVD404"), self.teacher)
        version.syllabus.chair_unit = self.stack["chair"]
        version.syllabus.save(update_fields=["chair_unit"])

        approved = self._post(self.chair, "accounts:syllabus_decision", version, {"action": "approve"})
        self.assertEqual(approved.status_code, 200)

        again = self._post(
            self.chair,
            "accounts:syllabus_decision",
            version,
            {"action": "revise", "reason": "Təsdiqdən sonra dəyişiklik cəhdi — bloklanmalıdır."},
        )

        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["code"], "version.approved_locked")
        version.refresh_from_db()
        self.assertEqual(version.status, SyllabusStatus.APPROVED.value)
        self.assertIsNotNone(version.locked_at)

    # ── Şablon ↔ JS bağları ────────────────────────────────────────────────

    def test_engine_hooks_are_present(self):
        html = self._html(self.chair)

        for hook in ENGINE_HOOKS:
            with self.subTest(hook=hook):
                self.assertIn(hook, html)

    def test_panel_hooks_are_present(self):
        html = self._html(self.chair)

        for hook in PANEL_HOOKS:
            with self.subTest(hook=hook):
                self.assertIn(hook, html)

    def test_dialog_and_text_payloads_are_embedded_as_json(self):
        """Mətn JS faylında YAZILMIR — `json_script` bloklarından gəlir."""
        html = self._html(self.chair)

        self.assertIn('id="syl-review-dialogs"', html)
        self.assertIn('id="syl-review-texts"', html)
        for key in ("approve", "revise", "reject"):
            self.assertIn(f'"{key}"', html)

    def test_coverage_tab_renders_breakdown_and_policy_card(self):
        html = self._html(self.chair, tab="coverage")

        self.assertIn("syl-table--coverage", html)
        self.assertIn("Təsdiq marşrutu", html)
        # Tətbiq olunmayan mərhələ «aktiv» kimi göstərilmir.
        self.assertIn("tətbiq olunmur", html)

    def test_coverage_tab_shows_the_official_program_code(self):
        """«Əhatə» tabında ixtisasın yanında rəsmi şifr GÖRÜNÜR.

        Bloker idi: tab yalnız ixtisas adını çap edirdi. Burada həm CƏDVƏL
        nişanı (``syl-code``), həm də ondan qidalanan VAHİD FİLTRİ açılışı
        yoxlanılır — ikisi eyni etiket mənbəyindən gəlir, ona görə birinin
        düzəlib o birinin unudulması mümkün olmasın.
        """
        program = self.stack["program"]
        program.name = "Dünya iqtisadiyyatı"
        program.official_code = ""
        # Yalnız KÖHNƏ şifr — cari təsnifatda ləğv olunmuş ixtisas.
        program.legacy_official_code = "050401"
        program.save(update_fields=["name", "official_code", "legacy_official_code"])

        html = self._html(self.chair, tab="coverage")

        self.assertIn('<span class="syl-code">050401</span>', html)
        # Filtr açılışı da şifrli etiketi göstərir.
        self.assertIn("Dünya iqtisadiyyatı · 050401", html)

    def test_no_inline_style_or_script_is_emitted_by_the_section(self):
        """CSP: şablonda inline CSS/JS QADAĞANDIR (yalnız json_script istisnadır)."""
        html = self._html(self.chair)
        section = html.split('data-profile-section-panel="syllabus-review"', 1)[1].split("</section>", 1)[0]

        self.assertNotIn("<style", section)
        self.assertNotIn('<script type="text/javascript"', section)
        self.assertNotIn(" style=", section)
