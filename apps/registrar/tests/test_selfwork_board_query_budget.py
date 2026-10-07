"""Sərbəst iş lövhəsinin yazısı (``journal_selfwork_action``) — sorğu büdcəsi + xana-xana parite (2026-10-07).

Lövhə HƏR redaktə oluna bilən xananı geri göndərir (mövzu × tələbə). Əvvəl hər
xana ``set_selfwork_mark`` ilə ayrıca yazılırdı: sxem (jurnal kilidi), mövzu,
qeydiyyat (FOR UPDATE), işarə (FOR UPDATE) SELECT-ləri + dəyişəndə INSERT/UPDATE,
tələbə SELECT-i və ayrıca audit sətri. Ölçü (5 mövzu):

=====================  ==============  ===============
POST                   10 tələbə (50)  40 tələbə (200)
=====================  ==============  ===============
dəyişməyən lövhə       311 → 18        1211 → 18
ilk işarələr           436 → 22        1711 → 22
=====================  ==============  ===============

İndi ``set_selfwork_marks``: açılış kilidi → qeydiyyatlar → işarələr TƏK sorğularla,
toplu INSERT/UPDATE, TƏK aqreqat audit sətri (jurnal xanaları kimi). Xana qaydası
dəyişməyib — aşağıdakı parite testi eyni xana ardıcıllığını köhnə xana-xana yolla
(``set_selfwork_mark``) və paketlə tətbiq edib nəticəni, işarələri və audit
dəyişikliklərini müqayisə edir.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, journal_extras
from apps.registrar import selfwork_points as rules
from apps.registrar import services
from apps.registrar.models import (
    Curriculum,
    CurriculumSubject,
    Program,
    SelfWorkMark,
    SelfWorkTopic,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

#: Ölçülmüş 22 + 3 ehtiyat. Əsas qıfıl «50 xana == 200 xana»dır.
BOARD_POST_BUDGET = 25


class SelfworkBoardQueryBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.owner = User.objects.create_user("swb_owner", "swb_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SWB Univ",
                slug="swb-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.specialty = OrgUnit.objects.create(
                organization=cls.org, name="CS", slug="swb-cs", unit_type=OrgUnitType.SPECIALTY
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="SWB semestr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=today - datetime.timedelta(days=60),
                end_date=today + datetime.timedelta(days=60),
                is_current=True,
            )
            cls.program = Program.objects.create(organization=cls.org, code="SWB", name="SWB", absence_limit_percent=25)
            cls.teacher = User.objects.create_user("swb_teacher", "swb_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.small = cls._offering("small", 10, 2026)
            cls.large = cls._offering("large", 40, 2025)
            cls.parity_a = cls._offering("pa", 4, 2024)
            cls.parity_b = cls._offering("pb", 4, 2023)
            for case in (cls.small, cls.large):
                case["topics"] = [
                    journal_extras.add_selfwork_topic(offering=case["offering"], title=f"Mövzu {i}") for i in range(5)
                ]
            for case in (cls.parity_a, cls.parity_b):
                case["topics"] = cls._parity_topics(case["offering"])
            AuditLog.objects.exists()

    @classmethod
    def _offering(cls, label, students, admission_year):
        group = OrgUnit.objects.create(
            organization=cls.org,
            name=f"SWB-{label}",
            slug=f"swb-{label}",
            unit_type=OrgUnitType.GROUP,
            parent=cls.specialty,
        )
        curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=admission_year)
        subject = Subject.objects.create(organization=cls.org, code=f"SWB{label.upper()}", name=f"Fənn {label}")
        CurriculumSubject.objects.create(
            organization=cls.org, curriculum=curriculum, subject=subject, semester_number=1
        )
        role = cls.org.roles.get(name="student")
        for index in range(students):
            student = User.objects.create_user(
                f"swb_{label}_{index:02d}", f"swb_{label}_{index:02d}@qku.edu.az", "pw", first_name=f"S{index}"
            )
            Membership.objects.create(user=student, organization=cls.org, role=role, is_primary=True, is_active=True)
            record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=student,
                program=cls.program,
                curriculum=curriculum,
                group=group,
                admission_year=admission_year,
            )
            services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
        offering = subject.offerings.get()
        offering.instructor = cls.teacher
        offering.save(update_fields=["instructor"])
        gradebook.ensure_assessment_scheme(offering=offering)
        return {"offering": offering, "enrollments": list(offering.enrollments.order_by("student__username"))}

    @classmethod
    def _parity_topics(cls, offering):
        checklist = [
            SelfWorkTopic.objects.create(organization=cls.org, offering=offering, title=f"Çeklist {i}", order=i + 1)
            for i in range(2)
        ]
        points = SelfWorkTopic.objects.create(
            organization=cls.org, offering=offering, title="Bal mövzusu", order=3, max_points=5
        )
        return [*checklist, points]

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    # ── büdcə ───────────────────────────────────────────────────────────────
    def _post(self, case, value_for):
        data = {"action": "marks"}
        for t_index, topic in enumerate(case["topics"]):
            for e_index, enrollment in enumerate(case["enrollments"]):
                data[f"sw__{topic.id}__{enrollment.id}"] = value_for(t_index, e_index)
        url = reverse("registrar:journal_selfwork_action", args=[case["offering"].id])
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        return len(ctx.captured_queries)

    def test_board_post_query_count_is_constant_in_cell_count(self):
        self.client.get(reverse("registrar:journal_detail", args=[self.small["offering"].id]), {"jt": "serbest"})
        phases = (
            ("dəyişməyən lövhə", lambda t, e: "0"),
            ("ilk işarələr", lambda t, e: "1" if (t + e) % 2 else "0"),
            ("eyni lövhə təkrar", lambda t, e: "1" if (t + e) % 2 else "0"),
            ("bir neçə dəyişiklik", lambda t, e: "1" if (t + e) % 2 or e < 3 else "0"),
        )
        for phase, value_for in phases:
            small = self._post(self.small, value_for)
            large = self._post(self.large, value_for)
            print(f"\n[selfwork board] {phase}: 50 xana={small} q; 200 xana={large} q")
            self.assertEqual(small, large, phase)
            self.assertLessEqual(large, BOARD_POST_BUDGET, phase)
        with bypass_rls():
            done = set(
                SelfWorkMark.objects.filter(topic__offering=self.large["offering"], done=True).values_list(
                    "topic_id", "enrollment_id"
                )
            )
        expected = {
            (topic.id, enrollment.id)
            for t, topic in enumerate(self.large["topics"])
            for e, enrollment in enumerate(self.large["enrollments"])
            if (t + e) % 2 or e < 3
        }
        self.assertEqual(done, expected)

    # ── xana-xana parite ────────────────────────────────────────────────────
    def _seed_parity(self, case):
        """Eyni başlanğıc: təzə jurnal işarəsi, fənn qovluğu balı, 2 saatdan köhnə bal."""
        (c0, c1, pts), (e0, e1, e2, e3) = case["topics"], case["enrollments"]
        now = timezone.now()
        common = {"organization": self.org, "graded_at": now, "entered_by": self.teacher}
        SelfWorkMark.objects.create(topic=c0, enrollment=e0, done=True, source=rules.SOURCE_JOURNAL, **common)
        SelfWorkMark.objects.create(
            topic=pts, enrollment=e1, done=True, points=Decimal("3"), source=rules.SOURCE_SUBJECT_FOLDER, **common
        )
        old = SelfWorkMark.objects.create(
            topic=pts, enrollment=e2, done=True, points=Decimal("4"), source=rules.SOURCE_JOURNAL, **common
        )
        SelfWorkMark.objects.filter(pk=old.pk).update(
            updated_at=now - gradebook.mark_edit_window() - datetime.timedelta(minutes=1)
        )
        return (c0, c1, pts), (e0, e1, e2, e3)

    def _parity_cells(self, topics, enrollments):
        (c0, c1, pts), (e0, e1, e2, e3) = topics, enrollments

        def cell(topic, enrollment, raw, *, points_field=False):
            data = {"topic_id": str(topic.id), "enrollment_id": str(enrollment.id)}
            if points_field:
                data.update(done=bool(raw.strip()), points=raw.strip())
            else:
                data.update(done=raw == "1")
            return data

        return [
            cell(c0, e0, "0"),  # təzə işarə geri alınır (pəncərə içində)
            cell(c0, e1, "1"),  # yeni işarə
            cell(c1, e1, "0"),  # yoxdur → no-op
            cell(pts, e1, "5", points_field=True),  # fənn qovluğu balı → rədd
            cell(pts, e2, "2", points_field=True),  # 2 saatdan köhnə → rədd
            cell(pts, e3, "4", points_field=True),  # yeni bal
            cell(pts, e0, "9", points_field=True),  # tavandan böyük → rədd
            cell(pts, e0, "abc", points_field=True),  # etibarsız → rədd
            cell(c1, e3, "1"),
            cell(c1, e3, "0"),  # paket daxilində təkrar hədəf: yarat → geri al
            {"topic_id": "pozuq", "enrollment_id": str(e0.id), "done": True},  # pozuq id → rədd
            {"topic_id": str(c0.id), "enrollment_id": "00000000-0000-0000-0000-000000000000", "done": True},
        ]

    @staticmethod
    def _state(case):
        return sorted(
            (str(m.topic.title), m.enrollment.student.username[-2:], m.done, m.points, m.source, m.entered_by_id)
            for m in SelfWorkMark.objects.filter(topic__offering=case["offering"]).select_related(
                "topic", "enrollment__student"
            )
        )

    @staticmethod
    def _audit_changes(offering, since):
        rows = AuditLog.objects.filter(resource_id=str(offering.pk)).exclude(pk__in=since).order_by("created_at")
        return [
            {key: change[key] for key in ("item", "old", "new")} | {"student": change["student"][:2]}
            for row in rows
            for change in (row.changes or [])
        ]

    def test_batch_matches_cell_by_cell_writer(self):
        with bypass_rls():
            topics_a, enrollments_a = self._seed_parity(self.parity_a)
            topics_b, enrollments_b = self._seed_parity(self.parity_b)
            before = set(AuditLog.objects.values_list("pk", flat=True))
            results_a = [
                journal_extras.set_selfwork_mark(
                    offering=self.parity_a["offering"],
                    topic_id=cell["topic_id"],
                    enrollment_id=cell["enrollment_id"],
                    done=cell["done"],
                    by_user=self.teacher,
                    **({"points": cell["points"]} if "points" in cell else {}),
                )
                for cell in self._parity_cells(topics_a, enrollments_a)
            ]
            accepted, rejected = journal_extras.set_selfwork_marks(
                offering=self.parity_b["offering"],
                cells=self._parity_cells(topics_b, enrollments_b),
                by_user=self.teacher,
            )
            self.assertEqual((accepted, rejected), (results_a.count(True), results_a.count(False)))
            self.assertEqual((accepted, rejected), (6, 6))
            self.assertEqual(self._state(self.parity_a), self._state(self.parity_b))
            changes_a = self._audit_changes(self.parity_a["offering"], before)
            changes_b = self._audit_changes(self.parity_b["offering"], before)
            self.assertEqual(changes_a, changes_b)
            self.assertEqual(len(changes_b), 5)
            # Paket TƏK aqreqat audit sətri yazır (xana-xana yol hər dəyişikliyə bir sətir yazırdı).
            self.assertEqual(
                AuditLog.objects.filter(resource_id=str(self.parity_b["offering"].pk)).exclude(pk__in=before).count(), 1
            )

    def test_locked_journal_rejects_every_cell(self):
        from unittest import mock

        case = self.parity_b
        cells = self._parity_cells(case["topics"], case["enrollments"])
        with bypass_rls(), mock.patch("apps.registrar.selfwork_marks.journal_is_locked", return_value=True):
            result = journal_extras.set_selfwork_marks(offering=case["offering"], cells=cells, by_user=self.teacher)
        self.assertEqual(result, (0, len(cells)))
        with bypass_rls():
            self.assertFalse(SelfWorkMark.objects.filter(topic__offering=case["offering"]).exists())
