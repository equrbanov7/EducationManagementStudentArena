"""MR-337/330/355/356 (2026-11-14): səviyyə (dil kohortu) jurnalı PAYLAŞILAN sillabusu görür.

Prod-da Xarici dillər müəlliminin təsdiqlənmiş sillabusu (məs. ``1ad30678``) E-1/E-6 səviyyə jurnallarına
``SyllabusShare`` ilə bağlı idi, amma jurnal «sillabus yazılmayıb» göstərirdi: kohort süzgəci yalnız öz dosyesini və
kohortun mənbə açılışını buraxırdı, paylaşımı kəsirdi.  «İstifadə et» dialoqu isə paylaşım artıq olduğu üçün heç nə
təklif etmirdi — müəllim ilişib qalırdı.  İndi pillə sırası normal jurnaldakı kimidir: öz → paylaşım → kohort mənbəyi.
"""

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.organizations.models import Membership
from apps.registrar import language_cohorts
from apps.registrar.models import CourseOffering, Subject
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

User = get_user_model()

WEEK_ROWS = [{"topic": "Present Simple", "seminar": 2}, {"topic": "Past Simple", "seminar": 2}]


class LevelJournalSharedSyllabusTests(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            from apps.workload.tests.factories import activate_member

            # Kohort mənbə açılışını oxumaq üçün (``language_cohort_assessment.configure``).
            activate_member(
                cls.org,
                cls.coordinator,
                "lc_source_reader",
                permissions=["journal.view"],
                scope_unit=cls.chair,
                scope_type="unit",
            )
            cls.teacher2 = User.objects.create_user("gr_teacher2", "gr_teacher2@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher2,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.history.name = "Xarici dil-1 (Elementary)"
            cls.history.save(update_fields=["name"])
            cls.intermediate = Subject.objects.create(
                organization=cls.org, code="LANG-INT", name="Xarici dil-1 (Intermediate)"
            )

    def _cohort(self, name, **kwargs):
        values = dict(
            organization=self.org,
            actor=self.coordinator,
            department=self.chair,
            period=self.period,
            subject=self.intermediate,
            instructor=self.teacher,
            name=name,
            hours=30,
            lecture_hours=0,
            seminar_hours=30,
            lab_hours=0,
            entry_score_max=50,
            pass_threshold=51,
            min_final_exam_score=17,
            confirm_separate=True,
        )
        values.update(kwargs)
        return language_cohorts.create_cohort(**values)

    def _approved_syllabus(self, offering):
        from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion

        syllabus = Syllabus.objects.create(
            organization=self.org,
            subject=self.intermediate,
            period=self.period,
            offering=offering,
            author=self.teacher,
        )
        version = SyllabusVersion.objects.create(
            organization=self.org, syllabus=syllabus, status="draft", plan_hours={"seminar": 30}
        )
        SyllabusSection.objects.create(
            organization=self.org, version=version, section_id="week", data={"rows": WEEK_ROWS}
        )
        SyllabusVersion.objects.filter(pk=version.pk).update(
            status="approved", approval_source="migration", locked_at=timezone.now()
        )
        Syllabus.objects.filter(pk=syllabus.pk).update(approved_version=version, current_version=version)
        return Syllabus.objects.get(pk=syllabus.pk)

    def _share(self, syllabus, offering):
        from apps.syllabus.models import ShareSource, SyllabusShare

        return SyllabusShare.objects.create(
            organization=self.org,
            syllabus=syllabus,
            offering=offering,
            source=ShareSource.TEACHER,
            created_by=self.teacher,
        )

    def _world(self):
        """E-1 sillabusun sahibidir; E-6 (fərqli saat bölgüsü — kohort mənbə pilləsi onu RƏDD edərdi) paylaşımla."""
        owner = self._cohort("E-1")
        target = self._cohort("E-6", lecture_hours=30, seminar_hours=0)
        syllabus = self._approved_syllabus(owner.offering)
        self._share(syllabus, target.offering)
        return owner, target, syllabus

    @staticmethod
    def _fresh(offering):
        return CourseOffering.objects.select_related("organization").get(pk=offering.pk)

    def test_shared_syllabus_resolves_for_level_journal(self):
        from apps.syllabus.public import offering_syllabus_state, syllabus_for_offering_obj

        owner, target, syllabus = self._world()
        self.assertEqual(syllabus_for_offering_obj(self._fresh(owner.offering)).pk, syllabus.pk)
        found = syllabus_for_offering_obj(self._fresh(target.offering))
        self.assertIsNotNone(found)
        self.assertEqual(found.pk, syllabus.pk)
        self.assertEqual(offering_syllabus_state(found)["state"], "approved")

    def test_journal_notice_topics_and_batch_readers_agree(self):
        from apps.registrar import journal_topics
        from apps.registrar.semester_readiness import approved_syllabus_offering_ids
        from apps.registrar.syllabus_notice import journal_syllabus_notice
        from apps.syllabus.public import approved_week_rows_for_offerings, student_syllabus_map

        _owner, target, syllabus = self._world()
        offering = self._fresh(target.offering)
        notice = journal_syllabus_notice(offering, has_lessons=True)
        self.assertEqual(notice["state"], "approved")
        self.assertFalse(notice["show_banner"])  # «sillabus yazılmayıb» zolağı yoxdur
        self.assertEqual(notice["syllabus_id"], str(syllabus.pk))
        # «MÖVZU — TƏQVİM PLANINDAN»: təsdiqlənmiş planın sətirləri.
        titles = [row["title"] for row in journal_topics.syllabus_week_rows(self._fresh(target.offering))]
        self.assertEqual(titles, ["Present Simple", "Past Simple"])
        self.assertEqual(student_syllabus_map(self.org, [offering]), {offering.pk: syllabus.pk})
        self.assertEqual(
            [row["topic"] for row in approved_week_rows_for_offerings([offering])[offering.pk]],
            [
                "Present Simple",
                "Past Simple",
            ],
        )
        rows = [{"id": offering.pk, "subject_id": offering.subject_id, "instructor_id": offering.instructor_id}]
        self.assertEqual(approved_syllabus_offering_ids(self.org, self.period, rows), {offering.pk})

    def test_own_syllabus_beats_share_and_handover_drops_share(self):
        from apps.syllabus.models import Syllabus
        from apps.syllabus.public import syllabus_for_offering_obj

        _owner, target, _syllabus = self._world()
        own = Syllabus.objects.create(
            organization=self.org,
            subject=self.intermediate,
            period=self.period,
            offering=target.offering,
            author=self.teacher,
        )
        self.assertEqual(syllabus_for_offering_obj(self._fresh(target.offering)).pk, own.pk)
        Syllabus.objects.filter(pk=own.pk).update(is_active=False)
        # Fənn başqa müəllimə keçib — köhnə müəllimin paylaşımı yeni müəllimdə görünmür (paylaşım qayda 4).
        CourseOffering.objects.filter(pk=target.offering_id).update(instructor=self.teacher2)
        self.assertIsNone(syllabus_for_offering_obj(self._fresh(target.offering)))

    def test_cohort_source_tier_still_requires_matching_hours_without_share(self):
        from apps.syllabus.public import syllabus_for_offering_obj

        owner = self._cohort("E-1")
        syllabus = self._approved_syllabus(owner.offering)
        same = self._cohort("E-2", source_offering=owner.offering)
        different = self._cohort("E-3", source_offering=owner.offering, lecture_hours=30, seminar_hours=0)
        self.assertEqual(syllabus_for_offering_obj(self._fresh(same.offering)).pk, syllabus.pk)
        self.assertIsNone(syllabus_for_offering_obj(self._fresh(different.offering)))
        # Müəllim paylaşanda saat fərqi mane deyil — normal jurnaldakı kimi.
        self._share(syllabus, different.offering)
        self.assertEqual(syllabus_for_offering_obj(self._fresh(different.offering)).pk, syllabus.pk)

    def test_reuse_dialog_offers_nothing_once_shared_and_resolved(self):
        from apps.syllabus.public import shared_syllabus_ids
        from apps.syllabus.services import sharing

        _owner, target, syllabus = self._world()
        offering = self._fresh(target.offering)
        self.assertEqual(sharing.target_code(offering, syllabus_id=syllabus.pk), sharing.CODE_ALREADY)
        self.assertEqual(shared_syllabus_ids([offering.pk]), {offering.pk: syllabus.pk})
