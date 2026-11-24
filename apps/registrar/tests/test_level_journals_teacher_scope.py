"""MR-000593 (2026-11-20): «Mövcud səviyyə jurnalları» — adi müəllim yalnız öz / aktiv payı olan, boş olmayan jurnalı görür."""

from django.contrib.auth import get_user_model

from apps.organizations.models import Membership
from apps.registrar import language_cohort_query
from apps.registrar.journal_access import can_observe_journal
from apps.registrar.models import Enrollment, JournalShare, TeachingHandover
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls


class ExistingLevelJournalsTeacherScopeTests(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            from apps.workload.tests.factories import activate_member

            activate_member(
                cls.org,
                cls.coordinator,
                "lvl_scope_reader",
                permissions=["journal.view"],
                scope_unit=cls.chair,
                scope_type="unit",
            )
            cls.history.name = "Xarici dil-1 (Elementary)"
            cls.history.save(update_fields=["name"])
            cls.colleague = get_user_model().objects.create_user("lvl_colleague", "lvl_colleague@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.colleague,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            for user in (cls.teacher, cls.colleague, cls.coordinator):
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])
            # Köhnə səviyyə jurnalı: əvvəl müəllimin idi, həmkara təhvil verilib, tələbələri artıq başqa jurnaldadır.
            cls.other_offering.instructor = cls.colleague
            cls.other_offering.save(update_fields=["instructor"])
            TeachingHandover.objects.create(
                organization=cls.org,
                offering=cls.other_offering,
                from_instructor=cls.teacher,
                to_instructor=cls.colleague,
                reason="Köhnə bölgü",
            )
            Enrollment.objects.filter(offering=cls.other_offering).update(status=Enrollment.Status.DROPPED)

    def ids(self, user):
        return {row.pk for row in language_cohort_query.existing_level_journals(user, self.org)}

    def test_handover_observer_no_longer_lists_colleagues_empty_level_journal(self):
        # Ön şərt: köhnə yol (təhvil müşahidəçisi) bu jurnalı oxu üçün açır — siyahı ona görə sızırdı.
        self.assertTrue(can_observe_journal(self.teacher, self.other_offering))
        ids = self.ids(self.teacher)
        self.assertIn(self.offering.pk, ids)
        self.assertNotIn(self.other_offering.pk, ids)

    def test_handover_observer_not_listed_even_when_journal_has_students(self):
        Enrollment.objects.filter(offering=self.other_offering).update(status=Enrollment.Status.ENROLLED)
        self.assertNotIn(self.other_offering.pk, self.ids(self.teacher))

    def test_own_empty_level_journal_is_hidden_until_it_has_a_student(self):
        Enrollment.objects.filter(offering=self.offering).update(status=Enrollment.Status.DROPPED)
        self.assertNotIn(self.offering.pk, self.ids(self.teacher))
        Enrollment.objects.filter(offering=self.offering).update(status=Enrollment.Status.ENROLLED)
        self.assertIn(self.offering.pk, self.ids(self.teacher))

    def test_active_share_lists_journal_and_inactive_share_does_not(self):
        Enrollment.objects.filter(offering=self.other_offering).update(status=Enrollment.Status.ENROLLED)
        share = JournalShare.objects.create(
            organization=self.org, offering=self.other_offering, teacher=self.teacher, kinds=["seminar"]
        )
        self.assertIn(self.other_offering.pk, self.ids(self.teacher))
        share.is_active = False
        share.save(update_fields=["is_active"])
        self.assertNotIn(self.other_offering.pk, self.ids(self.teacher))

    def test_active_share_on_empty_journal_is_not_listed(self):
        JournalShare.objects.create(organization=self.org, offering=self.other_offering, teacher=self.teacher)
        self.assertNotIn(self.other_offering.pk, self.ids(self.teacher))

    def test_scoped_staff_view_is_unchanged_and_keeps_empty_journals(self):
        ids = self.ids(self.coordinator)
        self.assertIn(self.offering.pk, ids)
        self.assertIn(self.other_offering.pk, ids)
