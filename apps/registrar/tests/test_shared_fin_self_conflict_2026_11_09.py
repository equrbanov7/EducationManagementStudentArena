"""Eyni FİN-li bağlı hesab — ayrıca işçi hesabı bağlı tələbə hesabının qrupuna / jurnalına toxuna bilmir
(sahib 2026-11-09, ``apps/accounts/shared_fin.py`` + ``organizations.self_conflict.linked_student_of``).

Ssenari: tələbə (632/6 İ) üçün ayrıca tyutor hesabı açılır və FİN təsdiqi ilə bağlanır. Tyutor hesabının heyət
əhatəsindən öz qrupu çıxır, qrup yoldaşı / öz jurnalı toqquşma sayılır, DB trigger-i bal yazısını kəsir.
"""

from __future__ import annotations

import datetime

from django.db import IntegrityError, connection, transaction

from apps.accounts.models import UserProfile
from apps.organizations.public import get_permission_scope, is_self_conflict, own_scope
from apps.registrar.models import Enrollment, Lesson, LessonKind, LessonMark
from apps.registrar.tests.test_self_conflict_2026_11_08 import User, _SelfConflictBase
from core.rls import bypass_rls

FIN = "5LINK01"


class LinkedAccountSelfConflictTest(_SelfConflictBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.linked_staff = User.objects.create_user("sc_linked_staff", "sc_linked@qku.edu.az", "pw")
            cls._member(cls.linked_staff, "tutor", cls.faculty)
            UserProfile.objects.filter(user=cls.mate).update(fin=FIN)
            UserProfile.objects.filter(user=cls.linked_staff).update(fin=FIN, fin_shared_with=cls.mate)

    def test_linked_staff_own_scope_is_the_students_scope(self):
        staff = self._fresh(self.linked_staff)
        with bypass_rls():
            scope = own_scope(staff, self.org)
        self.assertEqual(scope.user_ids, {str(self.linked_staff.pk)})
        self.assertIn(str(self.mate.pk), scope.student_ids)
        self.assertIn(str(self.sub_mate.pk), scope.student_ids)
        self.assertEqual(scope.group_ids, {str(self.own_group.pk), str(self.sub_group.pk)})
        self.assertIn(str(self.own_offering.pk), scope.offering_ids)
        self.assertNotIn(str(self.other_offering.pk), scope.offering_ids)
        with bypass_rls():
            self.assertTrue(is_self_conflict(staff, self.org, group_id=self.own_group.pk))
            self.assertTrue(is_self_conflict(staff, self.org, student_id=self.mate.pk))
            self.assertFalse(is_self_conflict(staff, self.org, group_id=self.other_group.pk))
            unit_scope = get_permission_scope(staff, self.org, "unit.view")
        self.assertIn(str(self.own_group.pk), {str(pk) for pk in unit_scope.excluded_unit_ids})

    def test_plain_tutor_without_link_is_unchanged(self):
        with bypass_rls():
            self.assertFalse(own_scope(self._fresh(self.plain_tutor), self.org))

    def test_db_trigger_blocks_linked_staff_marks_on_students_journal(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL trigger")
        with bypass_rls():
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.own_offering,
                date=datetime.date(2026, 9, 17),
                kind=LessonKind.SEMINAR,
            )
            enrollment = Enrollment.objects.get(offering=self.own_offering, student=self.mate)
            with self.assertRaises(IntegrityError), transaction.atomic():
                LessonMark.objects.create(
                    organization=self.org, lesson=lesson, enrollment=enrollment, entered_by=self.linked_staff
                )
            LessonMark.objects.create(
                organization=self.org, lesson=lesson, enrollment=enrollment, entered_by=self.plain_tutor
            )
