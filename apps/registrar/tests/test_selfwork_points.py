"""Sərbəst iş BAL modeli — kanonik qayda, sillabus strukturları, DB qoruyucuları.

Kilidlənən müqavilələr:

* effektiv bal: ``points`` → yoxdursa ``done × max_points`` → 0; cəm ≤ 10;
* SQL aqreqatları (``selfwork_totals*``, ``selfwork_total_for``) ↔ Python güzgüsü
  (``effective_points`` / ``selfwork_slots`` / lövhə) — qarışıq data üzərində EYNİ;
* 1 × 10 / 2 × 5 / 10 × 1 strukturları: ``ensure_structure`` N mövzu × P bal qurur,
  idempotentdir; köhnə mövzular yalnız rəqəm dəyişmədən uyğunlaşdırılır, əks halda
  ``structure_mismatch`` (heç nə yazılmır);
* «+ mövzu» strukturdan artıq slot aça bilmir;
* PostgreSQL qoruyucuları: bal ≤ mövzu tavanı, qiymətli mövzunun tavanı dəyişmir,
  bal = təhvil, slot unikaldır; RLS cədvəlləri dəyişməyib.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.registrar import gradebook, journal_extras, selfwork_points, selfwork_structure
from apps.registrar.models import ComponentKind, SelfWorkMark, SelfWorkTopic
from apps.registrar.models.selfwork import SELFWORK_TOTAL_POINTS
from apps.registrar.tests.selfwork_points_fixture import SelfWorkLegacyFixture, approve_syllabus
from core.rls import bypass_rls


def _mark(topic, enrollment, *, done=True, points=None, source="journal"):
    return SelfWorkMark.objects.create(
        organization=topic.organization, topic=topic, enrollment=enrollment, done=done, points=points, source=source
    )


class RulesTest(TestCase):
    """Skalyar qayda — DB-siz."""

    def test_effective_points_decision_table(self):
        topic = SelfWorkTopic(max_points=5)
        self.assertEqual(selfwork_points.effective_points(None, topic), Decimal("0"))
        self.assertEqual(selfwork_points.effective_points(SelfWorkMark(done=False), topic), Decimal("0"))
        self.assertEqual(selfwork_points.effective_points(SelfWorkMark(done=True), topic), Decimal("5"))
        self.assertEqual(
            selfwork_points.effective_points(SelfWorkMark(done=True, points=Decimal("4.5")), topic), Decimal("4.5")
        )
        checklist = SelfWorkTopic(max_points=1)
        self.assertEqual(str(selfwork_points.effective_points(SelfWorkMark(done=True), checklist)), "1")

    def test_cap_and_representation(self):
        self.assertEqual(selfwork_points.cap_total(Decimal("11")), Decimal("10"))
        self.assertEqual(str(selfwork_points.cap_total(Decimal("7.0"))), "7")  # köhnə Decimal(int) təmsili
        self.assertEqual(str(selfwork_points.cap_total(None)), "0")
        self.assertEqual(selfwork_points.display(Decimal("4.50")), "4.5")
        self.assertEqual(selfwork_points.display(None), "—")

    def test_parse_points_rejects_extra_precision(self):
        self.assertEqual(selfwork_points.parse_points("4,5"), Decimal("4.5"))
        self.assertIsNone(selfwork_points.parse_points(""))
        for raw in ("4.25", "abc", "NaN", "Infinity"):
            with self.assertRaises(ValueError, msg=raw):
                selfwork_points.parse_points(raw)

    def test_total_constant_matches_syllabus_policy(self):
        from apps.syllabus import public as syllabus_public

        self.assertEqual(SELFWORK_TOTAL_POINTS, syllabus_public.SELFWORK_TOTAL_SCORE)
        for option, config in syllabus_public.SELFWORK_OPTIONS.items():
            self.assertEqual(config["count"] * config["per_score"], SELFWORK_TOTAL_POINTS, option)


class SqlPythonMirrorTest(SelfWorkLegacyFixture, TestCase):
    """Qarışıq data (çeklist + bal + fənn qovluğu) — bütün sayma yolları EYNİ cəmi verir."""

    def _mixed(self):
        offering, enrollments = self._fresh_offering(code="SWM201", option="2x5")
        with bypass_rls():
            selfwork_structure.ensure_structure(offering)
            slot1, slot2 = SelfWorkTopic.objects.filter(offering=offering).order_by("slot_index")
            _mark(slot1, enrollments["swp_s0"], points=Decimal("4.5"), source="subject_folder")
            _mark(slot2, enrollments["swp_s0"])  # bal yoxdur, təhvil → max (5)
            _mark(slot1, enrollments["swp_s1"], points=Decimal("3"))
            _mark(slot2, enrollments["swp_s1"], done=False)
            _mark(slot1, enrollments["swp_s2"], done=False)
        return offering, enrollments

    def test_every_counting_path_agrees(self):
        offering, enrollments = self._mixed()
        expected = {"swp_s0": Decimal("9.5"), "swp_s1": Decimal("3"), "swp_s2": Decimal("0"), "swp_s3": Decimal("0")}
        with bypass_rls():
            ids = [e.id for e in enrollments.values()]
            flat = selfwork_points.selfwork_totals(ids)
            by_offering = selfwork_points.selfwork_totals_by_offering(ids, [offering.id])
            _slots, slot_totals = selfwork_points.selfwork_slots(list(enrollments.values()), [offering.id])
            board = {r["student"].username: r for r in journal_extras.get_selfwork_board(offering)["rows"]}
            for username, enrollment in enrollments.items():
                want = expected[username]
                self.assertEqual(selfwork_points.selfwork_total_for(enrollment), want, username)
                self.assertEqual(flat.get(enrollment.id, Decimal("0")), want, username)
                self.assertEqual(by_offering.get((enrollment.id, offering.id), Decimal("0")), want, username)
                self.assertEqual(slot_totals.get((enrollment.id, offering.id), Decimal("0")), want, username)
                self.assertEqual(board[username]["checklist_total"], want, username)
                python_sum = sum(
                    (selfwork_points.effective_points(m) for m in SelfWorkMark.objects.filter(enrollment=enrollment)),
                    Decimal("0"),
                )
                self.assertEqual(python_sum, want, username)
            # Yazılış açarsız qalır (analitika güzgüsünün «işarəsi yoxdursa açar yoxdur» davranışı).
            self.assertNotIn(enrollments["swp_s2"].id, flat)

    def test_entry_score_includes_points_single_and_batch(self):
        from apps.registrar import finals_batch

        offering, enrollments = self._mixed()
        with bypass_rls():
            batch = finals_batch.entry_batch(list(enrollments.values()))
            for username, enrollment in enrollments.items():
                single = gradebook.entry_score_for(enrollment, 50)
                batched = gradebook.entry_score_for(enrollment, 50, **batch.entry_kwargs(enrollment))
                self.assertEqual(single, batched, username)
            # 9.5 → giriş balı tam ədəd (yarım-yuxarı): 10.
            self.assertEqual(gradebook.entry_score_for(enrollments["swp_s0"], 50), Decimal("10"))

    def test_total_is_capped_at_ten(self):
        offering, enrollments = self._fresh_offering(code="SWM202", option=None)
        with bypass_rls():
            journal_extras.ensure_selfwork_component(offering)
            topics = [
                SelfWorkTopic.objects.create(organization=self.org, offering=offering, title=f"T{i}", order=i)
                for i in range(1, 13)
            ]
            for topic in topics:  # 12 təhvil (10-luq tavan yan keçilib — köhnə yarış datası)
                _mark(topic, enrollments["swp_s0"])
            self.assertEqual(selfwork_points.selfwork_total_for(enrollments["swp_s0"]), Decimal("10"))
            self.assertEqual(gradebook.entry_score_for(enrollments["swp_s0"], 50), Decimal("10"))


class StructureTest(SelfWorkLegacyFixture, TestCase):
    def _topics(self, offering):
        return list(SelfWorkTopic.objects.filter(offering=offering).order_by("slot_index", "order"))

    def test_each_syllabus_option_builds_its_slots_once(self):
        for code, option, count, per in (("SWS1", "1x10", 1, 10), ("SWS2", "2x5", 2, 5), ("SWS3", "10x1", 10, 1)):
            offering, _enrollments = self._fresh_offering(code=code, option=option)
            with bypass_rls():
                plan = selfwork_structure.ensure_structure(offering)
                self.assertTrue(plan.applied, option)
                topics = self._topics(offering)
                self.assertEqual([t.slot_index for t in topics], list(range(1, count + 1)), option)
                self.assertEqual({t.max_points for t in topics}, {per}, option)
                self.assertEqual(topics[0].title, "Sərbəst iş 1")
                again = selfwork_structure.ensure_structure(offering)
                self.assertFalse(again.applied, option)
                self.assertEqual(again.state, selfwork_structure.STATE_OK)
                self.assertEqual(len(self._topics(offering)), count, "idempotent")
                # entry_score_for yalnız SELF_WORK komponenti varsa sayır — struktur onu da yaradır.
                self.assertTrue(offering.assessment_components.filter(kind=ComponentKind.SELF_WORK).exists())

    def test_no_syllabus_keeps_legacy_checklist_mode(self):
        offering, _enrollments = self._fresh_offering(code="SWS4", option=None)
        with bypass_rls():
            plan = selfwork_structure.ensure_structure(offering)
        self.assertEqual(plan.state, selfwork_structure.STATE_NONE)
        self.assertFalse(SelfWorkTopic.objects.filter(offering=offering).exists())

    def test_legacy_topics_adopted_by_10x1_without_changing_numbers(self):
        with bypass_rls():
            before = {u: gradebook.entry_score_for(e, 50) for u, e in self.e1.items()}
            approve_syllabus(self.o1, self.teacher, option="10x1")
            plan = selfwork_structure.ensure_structure(self.o1)
            topics = self._topics(self.o1)
            after = {u: gradebook.entry_score_for(e, 50) for u, e in self.e1.items()}
        self.assertTrue(plan.applied)
        self.assertEqual([t.slot_index for t in topics], list(range(1, 11)))
        self.assertEqual({t.max_points for t in topics}, {1})
        self.assertEqual([t.title for t in topics][:2], ["Mövzu 1", "Mövzu 2"], "köhnə adlar qalır")
        self.assertEqual(after, before, "10 × 1 uyğunlaşdırması heç bir tələbənin balını dəyişmir")

    def test_graded_legacy_topics_are_not_converted_to_2x5(self):
        with bypass_rls():
            approve_syllabus(self.o1, self.teacher, option="2x5")
            plan = selfwork_structure.ensure_structure(self.o1)
            topics = self._topics(self.o1)
            message = selfwork_structure.mismatch_message(plan)
        self.assertEqual(plan.state, selfwork_structure.STATE_MISMATCH)
        self.assertEqual(plan.reason, selfwork_structure.REASON_TOO_MANY)
        self.assertTrue(all(t.slot_index is None and t.max_points == 1 for t in topics), "heç nə yazılmayıb")
        self.assertIn("2 × 5", message)

    def test_ungraded_legacy_topics_are_adopted_but_graded_ones_are_not(self):
        offering, enrollments = self._fresh_offering(code="SWS5", option=None)
        with bypass_rls():
            journal_extras.add_selfwork_topic(offering=offering, title="Birinci")
            second = journal_extras.add_selfwork_topic(offering=offering, title="İkinci")
            approve_syllabus(offering, self.teacher, option="2x5")
            plan = selfwork_structure.load_plan(offering, syllabus=selfwork_structure.SYLLABUS_ALWAYS)
            self.assertEqual(plan.state, selfwork_structure.STATE_PENDING)
            # Bir təhvil yazılan kimi çevirmə RƏQƏMİ dəyişərdi → uyğunsuzluq.
            journal_extras.set_selfwork_mark(
                offering=offering, topic_id=second.id, enrollment_id=enrollments["swp_s0"].id, done=True
            )
            plan = selfwork_structure.ensure_structure(offering)
            self.assertEqual(plan.state, selfwork_structure.STATE_MISMATCH)
            self.assertEqual(plan.reason, selfwork_structure.REASON_LEGACY_GRADED)
            journal_extras.set_selfwork_mark(
                offering=offering, topic_id=second.id, enrollment_id=enrollments["swp_s0"].id, done=False
            )
            plan = selfwork_structure.ensure_structure(offering)
            topics = self._topics(offering)
        self.assertTrue(plan.applied)
        self.assertEqual([(t.title, t.slot_index, t.max_points) for t in topics], [("Birinci", 1, 5), ("İkinci", 2, 5)])

    def test_add_topic_respects_structure_and_deleted_slot_is_restored(self):
        offering, _enrollments = self._fresh_offering(code="SWS6", option="2x5")
        with bypass_rls():
            self.assertIsNone(journal_extras.add_selfwork_topic(offering=offering, title="Üçüncü"))
            topics = self._topics(offering)
            self.assertEqual(len(topics), 2, "2 × 5-də N-dən artıq mövzu yoxdur (əvvəl struktur quruldu)")
            self.assertTrue(journal_extras.delete_selfwork_topic(topic=topics[1]))
            # Natamam struktur: lövhə sillabusu oxuyur və slotu «tətbiq et» kimi göstərir.
            board = journal_extras.get_selfwork_board(offering)
            self.assertEqual(board["structure"]["state"], selfwork_structure.STATE_PENDING)
            self.assertEqual([slot["virtual"] for slot in board["slots"]], [False, True])
            self.assertFalse(board["can_add_topic"])
            self.assertTrue(selfwork_structure.ensure_structure(offering).applied)
        self.assertEqual([(t.slot_index, t.max_points) for t in self._topics(offering)], [(1, 5), (2, 5)])

    def test_legacy_add_topic_cap_is_unchanged(self):
        offering, _enrollments = self._fresh_offering(code="SWS7", option=None)
        with bypass_rls():
            for i in range(10):
                self.assertIsNotNone(journal_extras.add_selfwork_topic(offering=offering, title=f"M{i}"))
            self.assertIsNone(journal_extras.add_selfwork_topic(offering=offering, title="11-ci"))


class DatabaseGuardTest(SelfWorkLegacyFixture, TestCase):
    """CHECK + PostgreSQL trigger qoruyucuları (servisi yan keçən yazılar da)."""

    def setUp(self):
        self.offering, self.enrollments = self._fresh_offering(code="SWG1", option="2x5")
        with bypass_rls():
            selfwork_structure.ensure_structure(self.offering)
        self.slot1 = SelfWorkTopic.objects.get(offering=self.offering, slot_index=1)

    def _violates(self, func):
        with bypass_rls(), self.assertRaises(IntegrityError), transaction.atomic():
            func()

    def test_points_above_topic_maximum_are_rejected(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL trigger")
        self._violates(lambda: _mark(self.slot1, self.enrollments["swp_s0"], points=Decimal("6")))

    def test_points_require_done_and_positive_range(self):
        self._violates(lambda: _mark(self.slot1, self.enrollments["swp_s0"], done=False, points=Decimal("2")))
        self._violates(lambda: _mark(self.slot1, self.enrollments["swp_s1"], points=Decimal("0")))

    def test_graded_topic_maximum_cannot_change(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL trigger")
        with bypass_rls():
            _mark(self.slot1, self.enrollments["swp_s0"], points=Decimal("3"))
        self._violates(lambda: SelfWorkTopic.objects.filter(pk=self.slot1.pk).update(max_points=10))

    def test_slot_is_unique_per_offering(self):
        self._violates(
            lambda: SelfWorkTopic.objects.create(
                organization=self.org, offering=self.offering, title="dublikat", slot_index=1, max_points=5
            )
        )

    def test_rls_is_still_forced_on_selfwork_tables(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL RLS")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN "
                "('registrar_selfworktopic', 'registrar_selfworkmark', 'registrar_selfworkcorrection')"
            )
            rows = {name: (enabled, forced) for name, enabled, forced in cursor.fetchall()}
            cursor.execute(
                "SELECT tablename FROM pg_policies WHERE policyname = 'rls_tenant_isolation' "
                "AND tablename IN ('registrar_selfworktopic', 'registrar_selfworkmark')"
            )
            policies = {row[0] for row in cursor.fetchall()}
        self.assertEqual(rows["registrar_selfworktopic"], (True, True))
        self.assertEqual(rows["registrar_selfworkmark"], (True, True))
        self.assertEqual(policies, {"registrar_selfworktopic", "registrar_selfworkmark"})
