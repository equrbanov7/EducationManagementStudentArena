"""Cədvəl slotunun REAL müəllimi — ``ScheduleSlot.instructor`` (bölünmüş tədris, 2026-09-25).

Nəyi qoruyur
------------
* köhnə sətirlər (NULL) üçün davranış dəyişmir — effektiv müəllim = jurnal sahibi;
* seminarı aparan assistent (B) onu ÖZ cədvəlində görür, jurnal sahibi (A) görmür;
* B-nin toqquşması tutulur, A isə həmin saatda boşdur; axın qaydası effektiv müəllimlə;
* generatorun dərci override-ı yalnız FƏRQLİ olanda yazır, toqquşmanı effektiv müəllimlə yoxlayır;
* redaktorun «Dərsi aparan müəllim» seçimi SERVERDƏ yoxlanır (ixtiyari müəllim yox);
* «Dərsi aktivləşdir» dərsə slotun müəllimini yazır;
* cədvəl səhifələrinin sorğu sayı override-dan asılı deyil (N+1 yoxdur).

Redaktorun HTTP səthi: ``test_schedule_slot_instructor_editor.py``.
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import deletion
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import schedule, schedule_conflicts, schedule_publish, services
from apps.registrar.models import Lesson, ScheduleSlot, SlotKind, Subject, WeekType
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


def _t(text):
    return datetime.time.fromisoformat(text)


class SlotInstructorBase(TestCase):
    """A = jurnal sahibi, B = seminar assistenti (öz fənni də var), C = kənar müəllim, D = başqa sahib."""

    code = "si"

    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        monday = cls.today - datetime.timedelta(days=cls.today.weekday())
        cls.owner = User.objects.create_user(f"{cls.code}_owner", f"{cls.code}_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name=f"{cls.code.upper()} Univ",
                slug=f"{cls.code}-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug=f"{cls.code}-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.speciality = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="İxtisas",
                slug=f"{cls.code}-spec",
                unit_type=OrgUnitType.SPECIALTY,
            )
            cls.groups = [
                OrgUnit.objects.create(
                    organization=cls.org,
                    parent=cls.speciality,
                    name=name,
                    slug=f"{cls.code}-{name.lower()}",
                    unit_type=OrgUnitType.GROUP,
                )
                for name in ("231A", "231B", "231C", "231D")
            ]
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Cari semestr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=monday - datetime.timedelta(days=14),
                end_date=cls.today + datetime.timedelta(days=90),
                is_current=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="SI101", name="Verilənlər bazası")
            cls.subject_b = Subject.objects.create(organization=cls.org, code="SI202", name="Şəbəkələr")
            cls.teacher_a = cls._teacher("a", "Aytən", "Əliyeva")
            cls.teacher_b = cls._teacher("b", "Bəhruz", "Həsənov")
            cls.teacher_c = cls._teacher("c", "Cavid", "Kərimov")
            cls.teacher_d = cls._teacher("d", "Dilarə", "Məmmədova")
            cls.offering = cls._offering(cls.subject, cls.groups[0], cls.teacher_a)  # A-nın jurnalı
            cls.offering_b = cls._offering(cls.subject_b, cls.groups[1], cls.teacher_b)  # B-nin öz fənni
            cls.offering_c = cls._offering(cls.subject_b, cls.groups[2], cls.teacher_a)  # A-nın başqa qrupu
            cls.offering_d = cls._offering(cls.subject, cls.groups[3], cls.teacher_d)  # eyni fənn, başqa sahib

    @classmethod
    def _teacher(cls, suffix, first, last):
        user = User.objects.create_user(
            f"{cls.code}_t{suffix}", f"{cls.code}_t{suffix}@qku.edu.az", "pw", first_name=first, last_name=last
        )
        Membership.objects.create(
            user=user, organization=cls.org, role=cls.org.roles.get(name="teacher"), is_primary=True, is_active=True
        )
        return user

    @classmethod
    def _offering(cls, subject, group, instructor):
        offering = services.get_or_create_offering(
            organization=cls.org, subject=subject, period=cls.period, group=group
        )
        offering.instructor = instructor
        offering.save(update_fields=["instructor"])
        return offering

    def _slot(self, offering, *, weekday=1, start="10:10", end="11:40", kind=SlotKind.LECTURE, instructor=None, **kw):
        return ScheduleSlot.objects.create(
            organization=self.org,
            offering=offering,
            weekday=weekday,
            start_time=_t(start),
            end_time=_t(end),
            kind=kind,
            instructor=instructor,
            **kw,
        )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client


class DefaultBehaviourTest(SlotInstructorBase):
    code = "sidef"

    def test_field_is_an_optional_set_null_reference(self):
        field = ScheduleSlot._meta.get_field("instructor")
        self.assertTrue(field.null and field.blank)
        self.assertIs(field.remote_field.on_delete, deletion.SET_NULL)

    def test_slot_without_override_is_taught_by_the_journal_owner(self):
        with bypass_rls():
            slot = self._slot(self.offering)
            slot = ScheduleSlot.objects.select_related("offering").get(pk=slot.pk)
            annotated = (
                ScheduleSlot.objects.filter(pk=slot.pk)
                .annotate(teacher=schedule.effective_instructor_expr())
                .values_list("teacher", flat=True)
                .get()
            )
            for_a = schedule.get_teacher_schedule(organization=self.org, teacher=self.teacher_a, period=self.period)
            for_b = schedule.get_teacher_schedule(organization=self.org, teacher=self.teacher_b, period=self.period)
        self.assertIsNone(slot.instructor_id)
        self.assertEqual(schedule.effective_instructor_id(slot), self.teacher_a.pk)
        self.assertEqual(schedule.effective_instructor(slot), self.teacher_a)
        self.assertEqual(annotated, self.teacher_a.pk)
        self.assertEqual([row.pk for row in for_a], [slot.pk])
        self.assertEqual(for_b, [])

    def test_choosing_the_journal_owner_stores_null(self):
        with bypass_rls():
            slot = schedule.create_slot(
                offering=self.offering,
                weekday=2,
                start_time=_t("08:30"),
                end_time=_t("10:00"),
                instructor=self.teacher_a,
            )
        self.assertIsNone(slot.instructor_id)
        self.assertIsNone(schedule.stored_instructor_id(self.offering, str(self.teacher_a.pk)))
        self.assertEqual(schedule.stored_instructor_id(self.offering, self.teacher_b.pk), self.teacher_b.pk)


class TeacherScheduleTest(SlotInstructorBase):
    code = "sisch"

    def test_assistant_sees_the_seminar_and_the_owner_does_not(self):
        with bypass_rls():
            lecture = self._slot(self.offering, weekday=1, start="08:30", end="10:00")
            seminar = self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_b)
            own_b = self._slot(self.offering_b, weekday=3)
            for_a = schedule.get_teacher_schedule(organization=self.org, teacher=self.teacher_a, period=self.period)
            for_b = schedule.get_teacher_schedule(organization=self.org, teacher=self.teacher_b, period=self.period)
            group = schedule.get_group_schedule(organization=self.org, group=self.groups[0], period=self.period)
        self.assertEqual([row.pk for row in for_a], [lecture.pk])
        self.assertEqual([row.pk for row in for_b], [seminar.pk, own_b.pk])
        # Qrupun cədvəli dəyişmir — həm mühazirə, həm seminar orada; etiket effektiv müəllimdir.
        self.assertEqual([row.pk for row in group], [lecture.pk, seminar.pk])
        self.assertEqual([schedule.effective_instructor(row) for row in group], [self.teacher_a, self.teacher_b])

    def test_teacher_schedule_is_one_query_with_labels(self):
        with bypass_rls():
            self._slot(self.offering, weekday=1, start="08:30", end="10:00", instructor=self.teacher_b)
            self._slot(self.offering_b, weekday=3)
            with self.assertNumQueries(1):
                slots = schedule.get_teacher_schedule(organization=self.org, teacher=self.teacher_b, period=self.period)
                labels = [
                    (row.offering.subject.code, row.offering.group.name, schedule.effective_instructor(row).username)
                    for row in slots
                ]
        self.assertEqual(len(labels), 2)

    def test_manage_view_lists_teachers_who_only_have_overrides(self):
        from apps.registrar import schedule_manage

        with bypass_rls():
            self._slot(self.offering, weekday=4, instructor=self.teacher_c)
            offerings = schedule_manage.scoped_offerings(self.owner, self.org, period=self.period)
            rows = schedule_manage.scoped_teacher_rows(offerings)
        ids = [row["id"] for row in rows]
        self.assertIn(str(self.teacher_c.pk), ids)  # öz açılışı yoxdur — yalnız slotu var
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, [row["id"] for row in sorted(rows, key=lambda row: row["name"])])


class ConflictTest(SlotInstructorBase):
    code = "sicf"

    def test_assistant_clash_is_detected_and_the_owner_is_free(self):
        with bypass_rls():
            seminar = self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_b)
            # B-nin öz fənni eyni saatda başqa qrupda → B-nin toqquşması (əvvəl görünmürdü).
            with self.assertRaises(schedule.ScheduleConflict) as caught:
                schedule.create_slot(offering=self.offering_b, weekday=2, start_time=_t("10:10"), end_time=_t("11:40"))
            # A həmin saatda BOŞDUR (əvvəl seminar A-nın adına yazılır və A-nı bloklayırdı).
            free = schedule.create_slot(
                offering=self.offering_c, weekday=2, start_time=_t("10:10"), end_time=_t("11:40")
            )
        self.assertEqual(caught.exception.conflict.pk, seminar.pk)
        self.assertEqual(free.offering_id, self.offering_c.pk)

    def test_new_slot_is_checked_for_its_own_teacher(self):
        with bypass_rls():
            own_b = self._slot(self.offering_b, weekday=4, start="13:35", end="15:05")
            with self.assertRaises(schedule.ScheduleConflict) as caught:
                schedule.create_slot(
                    offering=self.offering,
                    weekday=4,
                    start_time=_t("13:35"),
                    end_time=_t("15:05"),
                    kind=SlotKind.SEMINAR,
                    instructor=self.teacher_b,
                )
            schedule.create_slot(offering=self.offering, weekday=4, start_time=_t("13:35"), end_time=_t("15:05"))
        self.assertEqual(caught.exception.conflict.pk, own_b.pk)

    def test_editor_engine_names_the_effective_teacher(self):
        with bypass_rls():
            self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_b)
            params = {
                "organization": self.org,
                "weekday": 2,
                "start_time": _t("10:10"),
                "end_time": _t("11:40"),
                "week_type": WeekType.ALL,
            }
            for_b = schedule_conflicts.detect(
                **params, group_id=self.groups[1].pk, instructor_id=str(self.teacher_b.pk)
            )
            for_a = schedule_conflicts.detect(**params, group_id=self.groups[2].pk, instructor_id=self.teacher_a.pk)
            free = schedule_conflicts.suggest(
                organization=self.org, group_id=self.groups[1].pk, instructor_id=str(self.teacher_b.pk), limit=100
            )
        self.assertEqual([row["kind"] for row in for_b], [schedule_conflicts.KIND_TEACHER])
        self.assertEqual(for_b[0]["instructor"], "Bəhruz Həsənov")
        self.assertIn("231A", for_b[0]["message"])
        self.assertEqual(for_a, [])
        # Mətn id ("12") ilə də müəllimin məşğul xanası tövsiyə olunmur.
        self.assertNotIn((2, "10:10|11:40"), {(row["weekday"], row["time_slot"]) for row in free})

    def test_joint_lecture_compares_effective_teachers(self):
        with bypass_rls():
            lecture = self._slot(self.offering, weekday=5, start="08:30", end="10:00", room="A-1")
            # Override olmadan 231D-nin mühazirəsini jurnal sahibi D aparır — başqa müəllim, eyni otaq → toqquşma.
            with self.assertRaises(schedule.ScheduleConflict) as caught:
                schedule.create_slot(
                    offering=self.offering_d, weekday=5, start_time=_t("08:30"), end_time=_t("10:00"), room="A-1"
                )
            # Axın mühazirəsini A aparır (jurnal D-dədir) → eyni effektiv müəllim, birgə oturuş, toqquşma deyil.
            stream = schedule.create_slot(
                offering=self.offering_d,
                weekday=5,
                start_time=_t("08:30"),
                end_time=_t("10:00"),
                room="A-1",
                instructor=self.teacher_a,
            )
        self.assertEqual(caught.exception.conflict.pk, lecture.pk)
        self.assertEqual(stream.instructor_id, self.teacher_a.pk)


class PublishTest(SlotInstructorBase):
    code = "sipub"

    def _row(self, offering, teacher, *, weekday=1, start="08:30", end="10:00", kind=SlotKind.LECTURE):
        return {
            "offering_id": str(offering.pk),
            "weekday": weekday,
            "start_time": _t(start),
            "end_time": _t(end),
            "week_type": WeekType.ALL,
            "kind": kind,
            "room": "",
            "teacher_id": teacher,
            "stream": "",
        }

    def _publish(self, rows, offerings=None):
        return schedule_publish.publish_slots(
            actor=self.owner,
            organization=self.org,
            period=self.period,
            offering_ids=[str(o.pk) for o in (offerings or [self.offering])],
            slots=rows,
            source="test:slotinst",
        )

    def test_override_is_written_only_when_the_teacher_differs(self):
        rows = [
            self._row(self.offering, self.teacher_a.pk),
            self._row(self.offering, str(self.teacher_b.pk), weekday=2, kind=SlotKind.SEMINAR),
            self._row(self.offering, None, weekday=3, kind=SlotKind.SEMINAR),
        ]
        with bypass_rls():
            result = self._publish(rows)
            created = {slot.weekday: slot for slot in ScheduleSlot.objects.filter(pk__in=result["slot_ids"])}
            audit = AuditLog.objects.get(resource_type="registrar.ScheduleSlot", resource_id="test:slotinst")
        self.assertEqual(result["created"], 3)
        self.assertIsNone(created[1].instructor_id)  # jurnal sahibi → NULL (sahib dəyişəndə izləsin)
        self.assertEqual(created[2].instructor_id, self.teacher_b.pk)
        self.assertIsNone(created[3].instructor_id)
        self.assertEqual(audit.new_values["instructor_overrides"], 1)

    def test_new_rows_are_checked_for_their_own_teacher(self):
        with bypass_rls():
            # B-nin öz açılışının canlı slotu (dərcdə əvəz olunmur) çərşənbə axşamı 08:30-da.
            self._slot(self.offering_b, weekday=2, start="08:30", end="10:00")
            with self.assertRaises(schedule_publish.PublishError) as caught:
                self._publish([self._row(self.offering, self.teacher_b.pk, weekday=2, kind=SlotKind.SEMINAR)])
            written = ScheduleSlot.objects.filter(offering=self.offering).count()
            # Eyni saatda jurnal sahibi A aparsa toqquşma yoxdur.
            result = self._publish([self._row(self.offering, self.teacher_a.pk, weekday=2)])
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(caught.exception.errors["conflicts"][0]["kind"], schedule_conflicts.KIND_TEACHER)
        self.assertEqual(written, 0)
        self.assertEqual(result["created"], 1)

    def test_live_overrides_occupy_their_teacher(self):
        with bypass_rls():
            # A-nın 231C jurnalının seminarını B aparır (canlı, dərcdə əvəz olunmur).
            self._slot(self.offering_c, weekday=3, kind=SlotKind.SEMINAR, instructor=self.teacher_b)
            with self.assertRaises(schedule_publish.PublishError) as caught:
                self._publish(
                    [self._row(self.offering_b, self.teacher_b.pk, weekday=3, start="10:10", end="11:40")],
                    [self.offering_b],
                )
            # A isə həmin saatda boşdur — onun 231A dərsi dərc olunur.
            result = self._publish([self._row(self.offering, self.teacher_a.pk, weekday=3, start="10:10", end="11:40")])
        self.assertEqual(caught.exception.errors["conflicts"][0]["kind"], schedule_conflicts.KIND_TEACHER)
        self.assertEqual(result["created"], 1)

    def test_teacher_without_an_active_teaching_membership_is_refused(self):
        stranger = User.objects.create_user("sipub_stranger", "sipub_s@qku.edu.az", "pw")
        with bypass_rls():
            with self.assertRaises(schedule_publish.PublishError) as caught:
                self._publish([self._row(self.offering, stranger.pk, weekday=2, kind=SlotKind.SEMINAR)])
            live = ScheduleSlot.objects.filter(offering=self.offering).count()
        self.assertEqual(caught.exception.code, "invalid")
        self.assertEqual(live, 0)


class ActivationTest(SlotInstructorBase):
    code = "siact"

    def _today_seminar(self, teacher):
        return self._slot(self.offering, weekday=self.today.isoweekday(), kind=SlotKind.SEMINAR, instructor=teacher)

    def test_activation_and_strip_use_the_slot_teacher(self):
        with bypass_rls():
            slot = self._today_seminar(self.teacher_b)
        page = self._client(self.teacher_a).get(reverse("registrar:journal_detail", args=[self.offering.pk]))
        response = self._client(self.teacher_a).post(
            reverse("registrar:journal_activate_slot", args=[self.offering.pk, slot.pk])
        )
        with bypass_rls():
            lesson = Lesson.objects.get(offering=self.offering)
        self.assertEqual(page.status_code, 200)
        self.assertEqual([item["teacher"] for item in page.context["today_strip"]["items"]], ["Bəhruz Həsənov"])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(lesson.instructor_id, self.teacher_b.pk)
        self.assertEqual(lesson.kind, SlotKind.SEMINAR)

    def test_slot_without_override_keeps_the_old_rule(self):
        with bypass_rls():
            slot = self._today_seminar(None)
        self._client(self.teacher_a).post(reverse("registrar:journal_activate_slot", args=[self.offering.pk, slot.pk]))
        with bypass_rls():
            lesson = Lesson.objects.get(offering=self.offering)
        self.assertEqual(lesson.instructor_id, self.teacher_a.pk)

    def test_journal_page_queries_do_not_grow_with_an_override(self):
        with bypass_rls():
            slot = self._today_seminar(None)
        client = self._client(self.teacher_a)
        url = reverse("registrar:journal_detail", args=[self.offering.pk])
        client.get(url)  # isinmə: sessiya/icazə keşləri
        with CaptureQueriesContext(connection) as plain:
            client.get(url)
        with bypass_rls():
            ScheduleSlot.objects.filter(pk=slot.pk).update(instructor=self.teacher_b)
        with CaptureQueriesContext(connection) as overridden:
            client.get(url)
        # Slotun müəllimi `offering_slots` sorğusunda LEFT JOIN ilə gəlir — əlavə sorğu yoxdur.
        self.assertLessEqual(len(overridden), len(plain))


@override_settings(UNIVERSITY_MODE=True)
class SchedulePageBudgetTest(SlotInstructorBase):
    """«Dərs cədvəli» səhifəsinin sorğu sayı override-dan asılı deyil (etiketlər LEFT JOIN ilə)."""

    code = "sibud"

    def test_teacher_schedule_page_queries_are_unchanged(self):
        with bypass_rls():
            self._slot(self.offering_b, weekday=3)
            seminars = [self._slot(self.offering, weekday=day, kind=SlotKind.SEMINAR) for day in (1, 2)]
        client = self._client(self.teacher_b)
        url = "%s?section=my-schedule" % reverse("accounts:profile")
        client.get(url)  # isinmə: sessiya/icazə keşləri
        with CaptureQueriesContext(connection) as own_only:
            plain = client.get(url)
        with bypass_rls():
            ScheduleSlot.objects.filter(pk__in=[slot.pk for slot in seminars]).update(instructor=self.teacher_b)
        with CaptureQueriesContext(connection) as overridden:
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(plain, "Verilənlər bazası")
        self.assertContains(response, "Verilənlər bazası")  # A-nın fənninin seminarı indi B-nin cədvəlində
        # «Jurnalı aç» yalnız B-nin öz jurnalına — A-nın jurnalı B üçün açılmır.
        self.assertContains(response, reverse("registrar:journal_detail", args=[self.offering_b.pk]))
        self.assertNotContains(response, reverse("registrar:journal_detail", args=[self.offering.pk]))
        self.assertEqual(len(overridden), len(own_only))
