"""QA 2026-10-17 F-05: kafedra müdiri və tyutorda «Cədvəl idarəetməsi» 0 qrup göstərirdi.

Qruplar kafedranın deyil, fakültənin altındadır, ona görə kafedra kökünün qrup alt-ağacı boş idi.
İndi kafedra kökü ÖZ KAFEDRASININ fənlərinin açılışlarını əhatə edir — yalnız AÇILIŞ səviyyəsində
(redaktorun oxu görünüşü + hüceyrə əməlləri, ``widened=True``); qrup səviyyəli yazılar (növbə siyasəti,
generator, dərc) dar əhatədə qalır. Tyutor rəhbəri (``OrgUnit.head``) olduğu qrupların cədvəlini qurur.
Başqa kafedranın fənni və başqa qrup əhatədən kənardadır; «Xanaya dərs qoy» yad fənn üçün açılış
YARATMAZDAN / müəllim bağlamazdan əvvəl 403 verir (review 2026-10-17).
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import schedule_editor, schedule_editor_actions, schedule_grid, schedule_manage, services
from apps.registrar.models import CourseOffering, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class ChairAndTutorScheduleScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("scs_owner", "scs_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SCS Univ",
                slug="scs-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )

            def unit(name, unit_type, parent=None):
                return OrgUnit.objects.create(
                    organization=cls.org, parent=parent, name=name, slug=f"scs-{name.lower()}", unit_type=unit_type
                )

            faculty = unit("Fak", OrgUnitType.FACULTY)
            cls.chair = unit("KafA", OrgUnitType.CHAIR, faculty)
            other_chair = unit("KafB", OrgUnitType.CHAIR, faculty)
            specialty = unit("Ixt", OrgUnitType.SPECIALTY, faculty)
            cls.group = unit("G1", OrgUnitType.GROUP, specialty)
            cls.other_group = unit("G2", OrgUnitType.GROUP, specialty)
            cls.period = period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2025/2026 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date=datetime.date.today() - datetime.timedelta(days=10),
                end_date=datetime.date.today() + datetime.timedelta(days=100),
                is_current=True,
            )
            own_subject = Subject.objects.create(organization=cls.org, code="A1", name="Öz fənn", chair_unit=cls.chair)
            cls.foreign_subject = foreign_subject = Subject.objects.create(
                organization=cls.org, code="B1", name="Yad fənn", chair_unit=other_chair
            )

            def offering(subject, group):
                return services.get_or_create_offering(
                    organization=cls.org, subject=subject, period=period, group=group
                )

            cls.own_offering = offering(own_subject, cls.group)
            cls.foreign_offering = offering(foreign_subject, cls.group)
            cls.other_group_foreign = offering(foreign_subject, cls.other_group)

            cls.unused_foreign = Subject.objects.create(
                organization=cls.org, code="B2", name="Yad fənn 2", chair_unit=other_chair
            )
            cls.teacher = User.objects.create_user("scs_teacher", "scs_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.chair_head = User.objects.create_user("scs_chair", "scs_chair@qku.edu.az", "pw")
            cls.tutor = User.objects.create_user("scs_tutor", "scs_tutor@qku.edu.az", "pw")
            for user, role in ((cls.chair_head, "chair_head"), (cls.tutor, "tutor")):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    scope_unit=cls.chair if role == "chair_head" else other_chair,
                    is_primary=True,
                    is_active=True,
                )
            # Tyutor yad kafedraya təyin olunub, amma G2-nin rəhbəridir (qrup reyestrindəki «Tyutor»).
            cls.other_group.head = cls.tutor
            cls.other_group.save(update_fields=["head"])

    def _group_ids(self, user, widened=True):
        with bypass_rls():
            groups = schedule_manage.scoped_groups(user, self.org, widened=widened)
            return set(groups.values_list("pk", flat=True))

    def test_chair_head_sees_groups_with_own_chair_offerings(self):
        self.assertEqual(self._group_ids(self.chair_head), {self.group.pk})

    def test_group_level_scope_stays_strict(self):
        # Növbə siyasəti / generator / dərc dar əhatəni işlədir: kafedra fənni qrupu açmır.
        self.assertEqual(self._group_ids(self.chair_head, widened=False), set())
        self.assertEqual(self._group_ids(self.tutor, widened=False), {self.other_group.pk})
        with bypass_rls():
            strict = schedule_manage.scoped_offerings(self.chair_head, self.org, period=self.period)
            self.assertFalse(strict.exists())

    def _save(self, subject, **extra):
        key = schedule_grid.lesson_periods(self.org)[0]["key"]
        data = {"weekday": "1", "time_slot": key, "subject_id": str(subject.pk), **extra}
        return schedule_editor_actions.save_cell(
            actor=self.chair_head, organization=self.org, group=self.group, period=self.period, data=data
        )

    def test_save_cell_rejects_foreign_chair_subject_before_any_write(self):
        with bypass_rls():
            before = list(
                CourseOffering.objects.filter(organization=self.org).values_list("pk", "instructor_id", "is_active")
            )
            for subject in (self.foreign_subject, self.unused_foreign):
                with self.assertRaises(schedule_editor.CellError) as caught:
                    self._save(subject, instructor_id=str(self.teacher.pk))
                self.assertEqual(caught.exception.status, 403)
            after = list(
                CourseOffering.objects.filter(organization=self.org).values_list("pk", "instructor_id", "is_active")
            )
        self.assertEqual(sorted(before), sorted(after))
        self.assertFalse(CourseOffering.objects.filter(subject=self.unused_foreign).exists())

    def test_group_subject_helper_matches_offering_rule(self):
        with bypass_rls():
            for subject, expected in ((self.own_offering.subject, True), (self.foreign_subject, False)):
                self.assertEqual(
                    schedule_manage.can_manage_group_subject(self.chair_head, self.org, self.group, subject), expected
                )
            self.assertTrue(
                schedule_manage.can_manage_group_subject(
                    self.tutor, self.org, self.other_group, self.own_offering.subject
                )
            )

    def test_chair_head_manages_only_own_chair_subjects(self):
        with bypass_rls():
            self.assertTrue(schedule_manage.can_manage_offering(self.chair_head, self.org, self.own_offering))
            self.assertFalse(schedule_manage.can_manage_offering(self.chair_head, self.org, self.foreign_offering))
            offerings = set(
                schedule_manage.scoped_offerings(self.chair_head, self.org, group=self.group, widened=True).values_list(
                    "pk", flat=True
                )
            )
        self.assertEqual(offerings, {self.own_offering.pk})

    def test_tutor_sees_own_chair_subjects_and_headed_group(self):
        # KafB fənni hər iki qrupda var; G2 həm də tyutorun öz qrupudur.
        self.assertEqual(self._group_ids(self.tutor), {self.group.pk, self.other_group.pk})
        with bypass_rls():
            self.assertTrue(schedule_manage.can_manage_offering(self.tutor, self.org, self.other_group_foreign))
            self.assertFalse(schedule_manage.can_manage_offering(self.tutor, self.org, self.own_offering))

    def test_headed_group_alone_is_enough_for_tutor(self):
        with bypass_rls():
            Subject.objects.filter(chair_unit__name="KafB").update(chair_unit=None)
        self.assertEqual(self._group_ids(self.tutor), {self.other_group.pk})

    def test_actor_without_schedule_key_gets_nothing(self):
        teacher = User.objects.create_user("scs_plain", "scs_plain@qku.edu.az", "pw")
        with bypass_rls():
            Membership.objects.create(
                user=teacher,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            self.group.head = teacher
            self.group.save(update_fields=["head"])
        self.assertEqual(self._group_ids(teacher), set())
