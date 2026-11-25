"""«Ana qrupu alt qruplara böl» ana jurnalı TƏK jurnal saxlayır (sahib 2026-11-07/08: «ana qrup alt qrupların cəmidir»).

* bölmədən sonra ana jurnalın siyahısı dəyişmir (tələbələr ``enrolled``, provenans = alt qrup), alt qrup üçün AKTİV
  təkrar jurnal qalmır (DB qapısının tələb etdiyi varis açılışı müəllimsiz və passivdir), hər alt qrup ana jurnalda
  seminar alt qrupudur (``SeminarGroup`` + ``seminar_group``); rəsmi köçürmənin auditi və tarixçəsi qalır;
* əl ilə qoyulmuş seminar yeri dəyişdirilmir.

Geri qayıdış / qardaş alt qrup / köhnə forma zəncirləri (hər köçürmə ayrıca tranzaksiya):
``apps/registrar/tests/test_subgroup_parent_journal_transfer_2026_11_25.py``.
"""

from apps.audit.models import AuditLog
from apps.organizations.models import OrgUnit
from apps.registrar.gradebook import get_offering_journal
from apps.registrar.models import CourseOffering, Enrollment, SeminarGroup, StudentAcademicRecord

from .test_groups_registry_split import _SplitBase

SUB1, SUB2 = "QA-DS2 KE-24-1", "QA-DS2 KE-24-2"


class SplitKeepsParentJournalTest(_SplitBase):
    def setUp(self):
        super().setUp()
        self.offering_b = CourseOffering.objects.create(
            organization=self.org, subject=self.subject_b, period=self.period, group=self.group
        )
        for record in self.students:
            for offering in (self.offering, self.offering_b):
                Enrollment.objects.create(organization=self.org, offering=offering, student=record.student)

    def _row(self, record, offering=None):
        return Enrollment.objects.get(offering=offering or self.offering, student=record.student)

    def _do_split(self):
        a, b, _c = self.students
        response = self._split("teaching_office_head", self._payload([a], [b]))
        self.assertEqual(response.status_code, 200, response.content)
        return OrgUnit.objects.get(organization=self.org, name=SUB1), OrgUnit.objects.get(
            organization=self.org, name=SUB2
        )

    def _number(self, offering, unit):
        return SeminarGroup.objects.get(offering=offering, unit=unit).number

    def test_split_keeps_parent_roster_and_places_seminar_subgroups(self):
        a, b, c = self.students
        active_before = CourseOffering.objects.filter(organization=self.org, is_active=True).count()
        sub1, sub2 = self._do_split()

        # Ana jurnal: 3 tələbə qalır, heç bir sətir tarixçəyə keçmir, alt qrup üçün aktiv təkrar jurnal yoxdur.
        for offering in (self.offering, self.offering_b):
            rows = Enrollment.objects.filter(offering=offering)
            self.assertEqual(rows.filter(status=Enrollment.Status.ENROLLED).count(), 3)
            self.assertFalse(rows.exclude(status=Enrollment.Status.ENROLLED).exists())
        self.assertEqual(CourseOffering.objects.filter(organization=self.org, is_active=True).count(), active_before)
        shells = CourseOffering.objects.filter(group__in=[sub1, sub2])
        self.assertFalse(shells.filter(is_active=True).exists())
        self.assertFalse(shells.exclude(instructor=None).exists())
        self.assertFalse(Enrollment.objects.filter(offering__in=shells, status=Enrollment.Status.ENROLLED).exists())
        # Varis sətirləri tarixçədir və ana sətrə bağlıdır (köçürmənin tərsi ilə eyni forma).
        for successor in Enrollment.objects.filter(offering__in=shells):
            self.assertEqual(successor.status, Enrollment.Status.DROPPED)
            self.assertEqual(successor.superseded_by.offering.group_id, self.group.pk)
        self.assertEqual(len(get_offering_journal(offering=self.offering)["rows"]), 3)

        # Reyestr dəyişib (rəsmi köçürmə), ana jurnalda isə hər alt qrup seminar alt qrupudur.
        self.assertEqual(StudentAcademicRecord.objects.get(pk=a.pk).group_id, sub1.pk)
        self.assertEqual(StudentAcademicRecord.objects.get(pk=b.pk).group_id, sub2.pk)
        for offering in (self.offering, self.offering_b):
            groups = {row.unit_id: row for row in SeminarGroup.objects.filter(offering=offering)}
            self.assertEqual(set(groups), {sub1.pk, sub2.pk})
            self.assertEqual(groups[sub1.pk].name, SUB1)
            self.assertNotEqual(groups[sub1.pk].number, groups[sub2.pk].number)
            self.assertEqual(self._row(a, offering).seminar_group, groups[sub1.pk].number)
            self.assertEqual(self._row(b, offering).seminar_group, groups[sub2.pk].number)
            self.assertIsNone(self._row(c, offering).seminar_group)
        # Provenans: köçürülən sətrin mənbə qrupu alt qrupdur, qalan tələbənin sətri adi qalır.
        self.assertEqual(self._row(a).source_group_id, sub1.pk)
        self.assertEqual(self._row(b).source_group_id, sub2.pk)
        self.assertIsNone(self._row(c).source_group_id)

        parent_rows = {str(self._row(a).pk), str(self._row(a, self.offering_b).pk)}
        transfer_audit = AuditLog.objects.get(resource_type="registrar.group_transfer", resource_id=str(a.pk))
        self.assertEqual(set(transfer_audit.changes["moved_enrollment_ids"]), parent_rows)
        audit = AuditLog.objects.get(resource_type="registrar.subgroup_parent_journal", resource_id=str(a.pk))
        self.assertEqual(set(audit.changes["kept_in_parent_enrollment_ids"]), parent_rows)
        self.assertEqual(set(audit.changes["seminar_placed_enrollment_ids"]), parent_rows)

    def test_manual_seminar_place_is_not_overwritten(self):
        a, _b, _c = self.students
        Enrollment.objects.filter(offering=self.offering, student=a.student).update(seminar_group=7)
        sub1, _sub2 = self._do_split()
        self.assertEqual(self._row(a).seminar_group, 7)
        self.assertFalse(SeminarGroup.objects.filter(offering=self.offering, unit=sub1).exists())
        self.assertEqual(self._row(a, self.offering_b).seminar_group, self._number(self.offering_b, sub1))
