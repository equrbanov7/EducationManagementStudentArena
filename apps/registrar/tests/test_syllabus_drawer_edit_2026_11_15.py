"""«Sillabusa bax» panelindən «Sillabusu redaktə et» + «redaktə edə bilmir» blokları (sahib 2026-11-15).

Sahib: «Bir çox müəllim sillabusu redaktə edə bilmir deyir. Sillabusa baxılan yerdən — sağdakı paneldən —
«Sillabusu redaktə et» olsun, basanda müəllim redaktəyə keçə bilsin.»

Yoxlananlar (hamısı MÜƏLLİM kimi, superuser yox — HTTP ilə):

* panelin JSON-u ``edit`` hədəfini yalnız redaktə hüququ olana verir (müəllif / açılışın cari müəllimi);
  tələbə, kafedra müdiri (``syllabus.edit`` yoxdur), jurnal pay sahibi — yox;
* qaralama / düzəliş / baxışdakı versiya → redaktor həmin versiyada (``open``); təsdiqlənmiş → ``new_version``
  (siyahının əməli), təsdiqlənmiş nüsxə TOXUNULMUR; avtomatik təsdiq rejimində təsdiqlənmiş versiya birbaşa;
* təhvil verilmiş jurnalın YENİ müəllimi başqasının yaratdığı sillabusda yeni versiya açıb bölmə yaza bilir;
* kafedra müdirinin geri qaytardığı versiyanı müəllif düzəldir;
* redaktorun «normal» rejimi bölmə yazısının qapısı ilə eynidir: müəllif olmayan qaralamanı redaktə rejimində
  görmür (əvvəl görürdü, hər autosave «yalnız müəllif» ilə rədd olunurdu);
* kilidli versiyanın bannerində «Yeni versiya yarat» düyməsi (əvvəl yalnız mətn var idi — dalan).
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.registrar.models import JournalShare
from apps.registrar.tests import test_journal_syllabus_bridge as bridge
from apps.syllabus import services as syllabus_services
from apps.syllabus.constants import SectionKey, SyllabusStatus
from apps.syllabus.models import SyllabusVersion
from core.rls import bypass_rls

User = get_user_model()


@override_settings(ACADEMIC_SELFWORK_ENABLED=True)
class SyllabusDrawerEditTest(TestCase):
    # Körpü testinin fixture-u (org, kafedra, açılış, müəllim, müdir, tələbə) — test metodları İRS ALINMIR
    # (sinif modul adlar fəzasına idxal edilmir, yoxsa pytest onun testlərini burada da toplayardı).
    setUp = bridge.JournalSyllabusBridgeTest.setUp
    _member = bridge.JournalSyllabusBridgeTest._member
    _client = bridge.JournalSyllabusBridgeTest._client
    _actor = bridge.JournalSyllabusBridgeTest._actor
    _draft = bridge.JournalSyllabusBridgeTest._draft
    _fill = bridge.JournalSyllabusBridgeTest._fill
    _approved = bridge.JournalSyllabusBridgeTest._approved
    _json_url = bridge.JournalSyllabusBridgeTest._json_url

    # ── köməkçilər ───────────────────────────────────────────────────────
    def _edit(self, user):
        resp = self._client(user).get(self._json_url())
        self.assertEqual(resp.status_code, 200)
        return resp.json()["edit"]

    def _action(self, user, payload):
        return self._client(user).post(
            reverse("accounts:syllabus_action"), data=json.dumps(payload), content_type="application/json"
        )

    def _save(self, user, version, section=SectionKey.LIT.value, data=None):
        version.refresh_from_db()
        row = version.sections.get(section_id=section)
        body = {"section": section, "data": data or {"primary": ["Yeni kitab, 2026"], "additional": ["Əlavə, 2025"]}}
        body["revision"] = row.revision
        return self._client(user).post(
            reverse("accounts:syllabus_section_save", kwargs={"version_id": str(version.pk)}),
            data=json.dumps(body),
            content_type="application/json",
        )

    def _editor(self, user, version):
        resp = self._client(user).get(
            reverse("accounts:profile"), {"section": "syllabus-editor", "version": str(version.pk)}
        )
        self.assertEqual(resp.status_code, 200)
        return resp.context["syllabus_editor_section"], resp.content.decode("utf-8")

    def _revision(self):
        _syllabus, version, actor = self._draft()
        version = syllabus_services.submit(version=self._fill(version, actor), actor=actor)
        chair_actor = self._actor(self.chair)
        version = syllabus_services.start_review(version=version, actor=chair_actor)
        return syllabus_services.request_revision(version=version, actor=chair_actor, reason="Ədəbiyyatı yeniləyin")

    # ── 1. Panelin düyməsi: kimə və hara ────────────────────────────────
    def test_drawer_markup_carries_the_edit_button_with_urls_in_data_attributes(self):
        self._approved()
        resp = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        html = resp.content.decode("utf-8")
        self.assertIn("data-sylv-edit-row hidden", html)  # JS `edit` gələnə qədər gizli
        self.assertIn('data-action-url="%s"' % reverse("accounts:syllabus_action"), html)
        self.assertIn('data-editor-url="%s?section=syllabus-editor"' % reverse("accounts:profile"), html)
        self.assertIn("Sillabusu redaktə et", html)

    def test_draft_opens_the_editor_on_that_draft(self):
        _syllabus, version, _actor = self._draft()
        edit = self._edit(self.teacher)
        self.assertEqual(edit["mode"], "open")
        self.assertEqual(edit["version"], str(version.pk))

    def test_approved_goes_through_new_version_and_never_overwrites_the_approved_copy(self):
        syllabus, approved, _actor = self._approved()
        before = dict(approved.sections.get(section_id=SectionKey.LIT.value).data)
        edit = self._edit(self.teacher)
        self.assertEqual(edit, {"mode": "new_version", "version": "", "syllabus": str(syllabus.pk)})

        resp = self._action(self.teacher, {"action": "new_version", "syllabus": edit["syllabus"], "kind": "minor"})
        self.assertEqual(resp.status_code, 200, resp.content)
        draft = SyllabusVersion.objects.get(pk=resp.json()["version"])
        self.assertEqual(draft.status, SyllabusStatus.DRAFT.value)

        section, _html = self._editor(self.teacher, draft)
        self.assertEqual(section["view_state"], "normal")
        self.assertEqual(self._save(self.teacher, draft).status_code, 200)

        approved.refresh_from_db()
        self.assertEqual(approved.status, SyllabusStatus.APPROVED.value)
        self.assertEqual(approved.sections.get(section_id=SectionKey.LIT.value).data, before)
        # İkinci açılışda panel artıq açıq qaralamaya aparır (ikinci yeni versiya yaranmır).
        self.assertEqual(
            self._edit(self.teacher), {"mode": "open", "version": str(draft.pk), "syllabus": str(syllabus.pk)}
        )

    @override_settings(SYLLABUS_APPROVAL_REQUIRED=False)
    def test_auto_approval_mode_edits_the_approved_version_directly(self):
        _syllabus, version, actor = self._draft()
        version = syllabus_services.submit(version=self._fill(version, actor), actor=actor)
        self.assertEqual(version.status, SyllabusStatus.APPROVED.value)
        edit = self._edit(self.teacher)
        self.assertEqual((edit["mode"], edit["version"]), ("open", str(version.pk)))

    def test_pending_version_opens_the_editor_with_the_withdraw_hint(self):
        _syllabus, version, actor = self._draft()
        version = syllabus_services.submit(version=self._fill(version, actor), actor=actor)
        edit = self._edit(self.teacher)
        self.assertEqual((edit["mode"], edit["version"]), ("open", str(version.pk)))
        section, html = self._editor(self.teacher, version)
        self.assertTrue(section["readonly"])
        self.assertFalse(section["can_new_version"])
        self.assertIn("təqdimatı geri çağırın", html)

    def test_no_button_for_student_chair_or_journal_share_holder(self):
        self._approved()
        self.assertEqual(self._client(self.student).get(self._json_url()).json()["edit"], None)
        # Kafedra müdirində `syllabus.edit` QƏSDƏN yoxdur — panel ya açılmır (``journal.view`` yox), ya düyməsizdir.
        chair = self._client(self.chair).get(self._json_url())
        self.assertTrue(chair.status_code == 404 or chair.json()["edit"] is None)
        # Bölünmüş jurnalın pay sahibi (sahib deyil) jurnalı redaktə edir, sillabusun müəllifi deyil.
        seminarist = User.objects.create_user("sde_seminar", "sde_seminar@qku.edu.az", "pw")
        with bypass_rls():
            self._member(seminarist, "teacher", bridge.TEACHER_PERMS)
            JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=seminarist, kinds=["seminar"]
            )
        resp = self._client(seminarist).get(self._json_url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["mode"], "staff")
        self.assertIsNone(resp.json()["edit"])

    # ── 2. «Redaktə edə bilmir» halları ─────────────────────────────────
    def test_handed_over_journal_new_teacher_edits_the_previous_teachers_syllabus(self):
        """Fənn ikinci müəllimə təhvil verilib: dosyenin müəllifi köhnə müəllimdir, açılışın CARİ müəllimi yenisi."""
        syllabus, approved, _actor = self._approved()
        successor = User.objects.create_user("sde_successor", "sde_successor@qku.edu.az", "pw")
        with bypass_rls():
            self._member(successor, "teacher", bridge.TEACHER_PERMS)
            self.offering.instructor = successor
            self.offering.save(update_fields=["instructor"])
        self.assertNotEqual(syllabus.author_id, successor.pk)

        edit = self._edit(successor)
        self.assertEqual(edit["mode"], "new_version")
        resp = self._action(successor, {"action": "new_version", "syllabus": edit["syllabus"], "kind": "minor"})
        self.assertEqual(resp.status_code, 200, resp.content)
        draft = SyllabusVersion.objects.get(pk=resp.json()["version"])
        section, _html = self._editor(successor, draft)
        self.assertEqual(section["view_state"], "normal")
        self.assertEqual(self._save(successor, draft).status_code, 200)
        submit = self._action(successor, {"action": "submit", "version": str(draft.pk)})
        self.assertEqual(submit.status_code, 200, submit.content)

    def test_chair_returned_revision_is_editable_by_the_author(self):
        version = self._revision()
        edit = self._edit(self.teacher)
        self.assertEqual((edit["mode"], edit["version"]), ("open", str(version.pk)))
        section, _html = self._editor(self.teacher, version)
        self.assertEqual(section["view_state"], "normal")
        self.assertEqual(self._save(self.teacher, version).status_code, 200)
        resp = self._action(self.teacher, {"action": "submit", "version": str(version.pk)})
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_non_author_does_not_get_an_editor_whose_saves_are_refused(self):
        """Əvvəl: qaralama müəllif olmayana «normal» açılırdı, hər autosave 403 «yalnız müəllif» alırdı."""
        _syllabus, version, _actor = self._draft()
        colleague = User.objects.create_user("sde_colleague", "sde_colleague@qku.edu.az", "pw")
        with bypass_rls():
            self._member(colleague, "teacher", bridge.TEACHER_PERMS)
        section, _html = self._editor(colleague, version)
        self.assertEqual(section["view_state"], "readonly")
        self.assertEqual(self._save(colleague, version).status_code, 403)

    # ── 3. Redaktorun kilid banneri ─────────────────────────────────────
    def test_locked_approved_editor_offers_new_version_only_to_the_editor(self):
        _syllabus, approved, _actor = self._approved()
        section, html = self._editor(self.teacher, approved)
        self.assertTrue(section["readonly"])
        self.assertTrue(section["can_new_version"])
        self.assertIn("data-syl-new-version", html)
        self.assertIn("syllabus_new_version.js", html)

        colleague = User.objects.create_user("sde_peer", "sde_peer@qku.edu.az", "pw")
        with bypass_rls():
            self._member(colleague, "teacher", bridge.TEACHER_PERMS)
        section, html = self._editor(colleague, approved)
        self.assertFalse(section["can_new_version"])
        self.assertNotIn("data-syl-new-version", html)
