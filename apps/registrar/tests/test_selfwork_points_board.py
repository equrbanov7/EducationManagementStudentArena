"""Sərbəst iş lövhəsi (BAL strukturu) — render, POST, sənədli düzəliş, tələbə görünüşü.

* köhnə çeklist jurnalı — 1/0 çipi (dəyişməyib);
* təsdiqlənmiş 2 × 5 sillabusu, struktur qurulmayıb — «Strukturu tətbiq et» zolağı;
* qurulmuş struktur — bal seçimi (bootstrap select, «—» + 1…5), «2 × 5 bal (sillabus)» başlığı;
* fənn qovluğu balı — «Fənn qovluğu» nişanı + tooltip, lövhədə OXU-ONLY (POST dəyişmir);
* ``structure_mismatch`` — izahlı xəbərdarlıq zolağı;
* sənədli düzəliş bal qəbul edir (``new_points``) və geri alınır; tarixçədə «4 → 3»;
* tələbə: «Sərbəst iş 1 · 4/5» + mənbə nişanı; «Fənlərim» çipi kanonik balı göstərir.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import RequestFactory
from django.urls import reverse

from apps.registrar import item_corrections, journal_extras, selfwork_structure
from apps.registrar.models import CorrectionReason, SelfWorkCorrection, SelfWorkMark, SelfWorkTopic
from apps.registrar.public_services import selfwork_points as hook
from apps.registrar.tests.selfwork_points_fixture import approve_syllabus
from apps.registrar.tests.test_documented_change_gates import _JournalGateSetup, _pdf
from core.rls import bypass_rls


class SelfWorkPointsBoardTest(_JournalGateSetup):
    def setUp(self):
        super().setUp()
        self.url = reverse("registrar:journal_detail", args=[self.offering.id]) + "?jt=serbest"
        self.action_url = reverse("registrar:journal_selfwork_action", args=[self.offering.id])

    # ── köməkçilər ────────────────────────────────────────────────────────
    def _structure(self, option="2x5"):
        with bypass_rls():
            approve_syllabus(self.offering, self.ikt_teacher, option=option)
            selfwork_structure.ensure_structure(self.offering)
        return list(SelfWorkTopic.objects.filter(offering=self.offering).order_by("slot_index"))

    def _page(self, user=None, url=None):
        resp = self._client(user or self.ikt_teacher).get(url or self.url)
        self.assertEqual(resp.status_code, 200)
        return resp

    def _folder_award(self, slot=1, points="4"):
        with bypass_rls():
            return hook.record_points(
                offering=self.offering,
                enrollment=self.enrollment,
                slot_index=slot,
                slot_title="Qovluq tapşırığı",
                max_points=Decimal("5.0"),
                points=Decimal(points),
                source_ref="subject_folder.submission:00000000-0000-0000-0000-00000000000a",
                by_user=self.ikt_teacher,
            )

    # ── render ─────────────────────────────────────────────────────────────
    def test_legacy_checklist_board_is_unchanged(self):
        with bypass_rls():
            journal_extras.add_selfwork_topic(offering=self.offering, title="Köhnə mövzu")
        resp = self._page()
        self.assertContains(resp, "data-jd-sw-chip")
        self.assertNotContains(resp, "data-jd-swp")
        self.assertContains(resp, "Çeklist: hər mövzu 1 bal")
        self.assertEqual(resp.context["selfwork_board"]["structure"]["state"], selfwork_structure.STATE_NONE)

    def test_pending_structure_offers_apply_button(self):
        with bypass_rls():
            approve_syllabus(self.offering, self.ikt_teacher, option="2x5")
        resp = self._page()
        board = resp.context["selfwork_board"]
        self.assertEqual(board["structure"]["state"], selfwork_structure.STATE_PENDING)
        self.assertEqual([slot["virtual"] for slot in board["slots"]], [True, True])
        self.assertContains(resp, 'value="ensure_structure"')
        self.assertContains(resp, "Strukturu tətbiq et")
        self.assertFalse(SelfWorkTopic.objects.filter(offering=self.offering).exists(), "GET YAZMIR")

    def test_structured_board_renders_points_picker(self):
        topics = self._structure()
        resp = self._page()
        self.assertContains(resp, "2 × 5 bal")
        self.assertContains(resp, f'name="swp__{topics[0].id}__{self.enrollment.id}"')
        self.assertContains(resp, "data-jd-swp")
        self.assertNotContains(resp, "data-jd-sw-chip")
        self.assertContains(resp, 'class="bootstrap-single-select jd2-semselect jd-swp-select"')
        cell = resp.context["selfwork_board"]["rows"][0]["cells"][0]
        self.assertEqual(cell["options"], ["1", "2", "3", "4", "5"])
        self.assertContains(resp, "selfwork_points.css")

    def test_folder_mark_shows_badge_and_is_read_only(self):
        topics = self._structure()
        self.assertTrue(self._folder_award(slot=1, points="4")[0])
        resp = self._page()
        cell = resp.context["selfwork_board"]["rows"][0]["cells"][0]
        self.assertTrue(cell["from_folder"])
        self.assertContains(resp, "jd-swp-folder")
        self.assertContains(resp, "Fənn qovluğundan yazılıb")
        self.assertNotContains(resp, f'name="swp__{topics[0].id}__{self.enrollment.id}"')
        self.assertContains(resp, f'name="swp__{topics[1].id}__{self.enrollment.id}"')
        # Qovluq balı olan slotun silmə düyməsi yoxdur.
        self.assertNotContains(resp, f'value="{topics[0].id}"')

    def test_mismatch_banner_explains_the_problem(self):
        with bypass_rls():
            topic = journal_extras.add_selfwork_topic(offering=self.offering, title="Köhnə")
            journal_extras.set_selfwork_mark(
                offering=self.offering, topic_id=topic.id, enrollment_id=self.enrollment.id, done=True
            )
            approve_syllabus(self.offering, self.ikt_teacher, option="2x5")
        resp = self._page()
        self.assertEqual(resp.context["selfwork_board"]["structure"]["state"], selfwork_structure.STATE_MISMATCH)
        self.assertContains(resp, "jd-swp-banner--warn")
        self.assertContains(resp, "avtomatik çevrilmir")
        self.assertContains(resp, "data-jd-sw-chip", msg_prefix="köhnə çeklist işləməyə davam edir")

    # ── POST ───────────────────────────────────────────────────────────────
    def test_apply_structure_action(self):
        with bypass_rls():
            approve_syllabus(self.offering, self.ikt_teacher, option="1x10")
        resp = self._client(self.ikt_teacher).post(self.action_url, {"action": "ensure_structure"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            list(SelfWorkTopic.objects.filter(offering=self.offering).values_list("slot_index", "max_points")),
            [(1, 10)],
        )

    def test_points_post_writes_changes_and_refuses_invalid(self):
        topics = self._structure()
        client = self._client(self.ikt_teacher)
        key = f"swp__{topics[0].id}__{self.enrollment.id}"
        client.post(self.action_url, {key: "4"})
        mark = SelfWorkMark.objects.get(topic=topics[0], enrollment=self.enrollment)
        self.assertEqual((mark.done, mark.points, mark.source), (True, Decimal("4.0"), "journal"))
        client.post(self.action_url, {key: "6"})  # tavandan yuxarı
        mark.refresh_from_db()
        self.assertEqual(mark.points, Decimal("4.0"))
        client.post(self.action_url, {key: ""})  # 2 saat içində «—» → bal silinir (0 yazılmır)
        mark.refresh_from_db()
        self.assertEqual((mark.done, mark.points), (False, None))
        client.post(self.action_url, {key: "3"})
        self._freeze(SelfWorkMark.objects.filter(pk=mark.pk), field="updated_at")
        client.post(self.action_url, {key: "5"})  # pəncərə bitib → yalnız sənədli düzəliş
        mark.refresh_from_db()
        self.assertEqual(mark.points, Decimal("3.0"))

    def test_folder_points_cannot_be_changed_or_deleted_from_the_board(self):
        topics = self._structure()
        self.assertTrue(self._folder_award(slot=1, points="4")[0])
        client = self._client(self.ikt_teacher)
        client.post(self.action_url, {f"swp__{topics[0].id}__{self.enrollment.id}": "1"})
        resp = client.post(self.action_url, {"action": "delete_topic", "topic_id": str(topics[0].id)})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(SelfWorkTopic.objects.filter(pk=topics[0].pk).exists())
        self.assertEqual(SelfWorkMark.objects.get(topic=topics[0], enrollment=self.enrollment).points, Decimal("4.0"))

    # ── sənədli düzəliş (bal) ──────────────────────────────────────────────
    def test_documented_points_correction_and_revert(self):
        topics = self._structure()
        self.assertTrue(self._folder_award(slot=1, points="4")[0])
        client = self._client(self.ikt_teacher)
        resp = client.post(
            reverse("registrar:correction_apply", args=[self.offering.id]),
            {
                "target": "selfwork",
                "topic_id": str(topics[0].id),
                "enrollment_id": str(self.enrollment.id),
                "new_done": "1",
                "new_points": "3",
                "reason": CorrectionReason.TECHNICAL,
                "note": "Plagiat hissəsi çıxıldı — protokol əsasında.",
                "document": _pdf(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        mark = SelfWorkMark.objects.get(topic=topics[0], enrollment=self.enrollment)
        correction = SelfWorkCorrection.objects.get(topic=topics[0], enrollment=self.enrollment)
        self.assertEqual((mark.points, mark.source), (Decimal("3.0"), "subject_folder"))
        self.assertEqual((correction.old_points, correction.new_points), (Decimal("4.0"), Decimal("3.0")))
        history = item_corrections.selfwork_corrections_map(self.offering)[f"{topics[0].id}:{self.enrollment.id}"]
        self.assertEqual((history[0]["old"], history[0]["new"]), ("4", "3"))
        # Düzəliş rejimində xana bal modalını açır.
        page = self._page(url=reverse("registrar:journal_detail", args=[self.offering.id]) + "?jt=serbest&correct=1")
        self.assertContains(page, 'data-sw-points-mode="1"')
        self.assertContains(page, "data-corr-swp-points")
        resp = client.post(
            reverse("registrar:correction_delete", args=[self.offering.id]),
            {
                "type": "selfwork",
                "topic_id": str(topics[0].id),
                "enrollment_id": str(self.enrollment.id),
                "correction_id": str(correction.id),
            },
        )
        self.assertEqual(resp.status_code, 302)
        mark.refresh_from_db()
        self.assertEqual((mark.done, mark.points), (True, Decimal("4.0")), "geri alma köhnə bala qaytarır")

    def test_checklist_correction_contract_is_unchanged(self):
        with bypass_rls():
            topic = journal_extras.add_selfwork_topic(offering=self.offering, title="Çeklist")
            correction = item_corrections.apply_selfwork_correction(
                offering=self.offering,
                topic=topic,
                enrollment=self.enrollment,
                new_done=True,
                reason=CorrectionReason.TECHNICAL,
                note="Təhvil kağız jurnalda var idi.",
                document=_pdf(),
                by_user=self.ikt_teacher,
            )
        self.assertEqual((correction.old_done, correction.new_done), (False, True))
        self.assertEqual((correction.old_points, correction.new_points), (None, None))
        entry = item_corrections.selfwork_corrections_map(self.offering)[f"{topic.id}:{self.enrollment.id}"][0]
        self.assertEqual((entry["old"], entry["new"]), ("0", "1"))

    # ── tələbə görünüşü ────────────────────────────────────────────────────
    def test_student_sees_points_per_slot(self):
        from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
        from apps.registrar.public import build_student_journal_context

        self._structure()
        self.assertTrue(self._folder_award(slot=1, points="4")[0])
        with bypass_rls():
            program = Program.objects.create(organization=self.org, code="DG-P", name="Proqram")
            curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2024)
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=program,
                curriculum=curriculum,
                group=self.group,
                admission_year=2024,
            )
        request = RequestFactory().get("/", {"subject": str(self.enrollment.id)})
        request.user = self.student
        with bypass_rls():
            ctx = build_student_journal_context(request, organization=self.org)
        detail = ctx["journal_student_section"]["detail"]
        cells = detail["selfwork_row"]["cells"]
        self.assertEqual(
            [(c["points_value"], c["max_points"], c["from_folder"]) for c in cells][:2],
            [
                ("4", 5, True),
                ("", 5, False),
            ],
        )
        self.assertEqual(detail["parts"]["selfwork"], Decimal("4"))
        self.assertEqual(detail["entry_score"], Decimal("4"))
