"""Xarici dil səviyyə jurnalları üçün ortaq qurğu (``merge_level_journals``, ``build_journal_share_plans``,
``chair_journal_health`` testləri; sahib 2026-10-27).

Kafedra «Kafedra» (``SubgroupFixture``) iki səviyyə fənnini aparır: L = «…-1(intermediate)», L2 = «…-1(pre-intermadiate)»
(kataloqdakı yazı xətası — səviyyə sayılmalıdır). Açılışlar:

* ``lvl_a`` — L, G1, sahibi ``lvl_t`` (köhnə jurnal J-nin müəllimi): ``host`` (G1);
* ``lvl_b`` — L, G2, sahibi ``lvl_z``: ``student`` (J-nin tələbəsi), ``s3`` (Z-nin öz tələbəsi), ``s4`` (köhnə
  sistemdə L2-dədir — yanlış səviyyə), ``s5`` (heç bir siyahıda yoxdur);
* ``lvl_c`` — L2, G2, sahibi ``lvl_z``: ``s4``.

Dərslər: A və B-də 2025-10-07 və 2025-10-14 10:10 (B-də əlavə 2025-10-21 — A-da yoxdur).
"""

from __future__ import annotations

import datetime

from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.rls import bypass_rls

D = datetime.date
TEN_TEN = datetime.time(10, 10)
LEVEL_L = "Xarici dildə kommunikasiya-1(intermediate)"
LEVEL_L2 = "Xarici dildə kommunikasiya-1(pre-intermadiate)"


class LevelFixture(SubgroupFixture):
    PREFIX = "lvl"

    @classmethod
    def build_levels(cls):
        cls.build_world()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])
            teacher_role = cls.org.roles.get(name="teacher")
            cls.t = cls._member("lvl_t", teacher_role)
            cls.z = cls._member("lvl_z", teacher_role)
            subject = Subject.objects.create
            cls.level = subject(organization=cls.org, code="LVLL", name=LEVEL_L, chair_unit=cls.chair)
            cls.level2 = subject(organization=cls.org, code="LVLL2", name=LEVEL_L2, chair_unit=cls.chair)
            offering = CourseOffering.objects.create
            cls.lvl_a = offering(
                organization=cls.org, subject=cls.level, period=cls.period, group=cls.group1, instructor=cls.t
            )
            cls.lvl_b = offering(
                organization=cls.org, subject=cls.level, period=cls.period, group=cls.group2, instructor=cls.z
            )
            cls.lvl_c = offering(
                organization=cls.org, subject=cls.level2, period=cls.period, group=cls.group2, instructor=cls.z
            )
            cls.s3 = cls._student("lvl_s3", cls.group2)
            cls.s4 = cls._student("lvl_s4", cls.group2)
            cls.s5 = cls._student("lvl_s5", cls.group2)
            enroll = cls._enroll
            cls.e_host = enroll(cls.host, cls.lvl_a)
            cls.e_student = enroll(cls.student, cls.lvl_b)
            cls.e_s3 = enroll(cls.s3, cls.lvl_b)
            cls.e_s4 = enroll(cls.s4, cls.lvl_b)
            cls.e_s5 = enroll(cls.s5, cls.lvl_b)
            cls.e_s4_c = enroll(cls.s4, cls.lvl_c)

    @classmethod
    def _enroll(cls, student, offering):
        return Enrollment.objects.create(organization=cls.org, student=student, offering=offering)

    def lesson(self, offering, day, start=TEN_TEN, kind="seminar"):
        return Lesson.objects.create(organization=self.org, offering=offering, date=day, start_time=start, kind=kind)

    def mark(self, lesson, enrollment, status="present", score=None):
        return LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, status=status, score=score
        )


__all__ = ["D", "LEVEL_L", "LEVEL_L2", "LevelFixture", "TEN_TEN"]
