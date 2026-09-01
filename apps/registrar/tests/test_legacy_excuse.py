"""Köhnə üzrlü-qayıb sənədləri: append-only model + jurnal oxu qatı (sarı + ✎).

İki müqavilə ölçülür:

1. **Sahibin qaydası** — qeyd yazıldıqdan sonra HEÇ NƏ dəyişmir; yeganə istisna
   köhnə serverdən sonradan gətirilən FAYLIN qoşulmasıdır (bir dəfə).
2. **Paralel sistem yoxdur** — sənəd qeydi mövcud düzəliş-tarixçə payload-una
   qatılır və qrid xanası ``JournalCorrection`` kimi müəllim üçün KİLİDLƏNMİR.
"""

import datetime

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction

from apps.registrar import gradebook, legacy_excuse
from apps.registrar.models import (
    AttendanceStatus,
    LegacyExcuseDocument,
    LegacyExcuseMappingStatus,
    LessonKind,
    LessonMark,
)
from apps.registrar.tests.test_corrections_bridge import _BaseJournalSetup
from core.rls import bypass_rls

_SOURCE = {
    "source_system": "myedu_mariadb",
    "source_table": "allowed_qb",
    "source_snapshot_sha256": "a" * 64,
    "source_row_hash": "b" * 64,
    "materialization_digest": "c" * 64,
    "transform_version": "rehearsal-identity-v1",
}


class _ExcuseSetup(_BaseJournalSetup):
    def _excused_lesson(self, day, hours=2):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                allow_past=True,
                offering=self.offering,
                date=datetime.date(2024, 10, day),
                kind=LessonKind.LECTURE,
            )
            lesson.hours = hours
            lesson.save(update_fields=["hours"])
            mark = LessonMark.objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=self.enrollment,
                status=AttendanceStatus.EXCUSED,
            )
        return lesson, mark

    def _document(self, *, source_pk=1, start=(2024, 10, 7), end=(2024, 10, 9), student=None, **overrides):
        values = {
            **_SOURCE,
            "organization": self.org,
            "source_pk": source_pk,
            "student": self.student if student is None else student,
            "mapping_status": LegacyExcuseMappingStatus.LINKED,
            "source_student_ref": "3110",
            "source_owner_ref": "51",
            "source_batch_ref": "05Izfa",
            "starts_on": datetime.date(*start),
            "ends_on": datetime.date(*end),
            "source_window_text": "2024-10-07 08:30:00|2024-10-09 23:59:00",
            "source_recorded_at_text": "2024-10-10 17:10:19",
            "note": "Texnopark",
            "document_name": "1697461819.jpg",
        }
        values.update(overrides)
        with bypass_rls():
            return LegacyExcuseDocument.objects.create(**values)


class LegacyExcuseModelTest(_ExcuseSetup):
    def test_the_record_is_append_only_for_every_field_but_the_document(self):
        document = self._document()

        document.note = "dəyişdirilmiş izah"
        with self.assertRaises(ValidationError):
            document.save(update_fields=["note"])
        with self.assertRaises(ValidationError):
            document.save()
        with self.assertRaises(ValidationError):
            document.delete()
        with bypass_rls():
            with self.assertRaises(ValidationError):
                LegacyExcuseDocument.objects.filter(pk=document.pk).update(note="x")
            with self.assertRaises(ValidationError):
                LegacyExcuseDocument.objects.filter(pk=document.pk).delete()
            assert LegacyExcuseDocument.objects.get(pk=document.pk).note == "Texnopark"

    def test_the_missing_file_can_be_attached_exactly_once(self):
        """Sahib faylları köhnə serverdən gətirəndə qoşula bilir — bir dəfə."""

        document = self._document()
        assert not document.document_available

        with bypass_rls():
            attached = legacy_excuse.attach_document(
                document, SimpleUploadedFile("1697461819.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")
            )
            assert attached is True
            stored = LegacyExcuseDocument.objects.get(pk=document.pk)
            assert stored.document_available
            # İkinci cəhd səssiz keçmir: mövcud fayl ƏVƏZLƏNMİR.
            assert legacy_excuse.attach_document(stored, SimpleUploadedFile("x.pdf", b"%PDF-1.4\n")) is False
            stored.document = ""
            with self.assertRaises(ValidationError):
                stored.save(update_fields=["document"])

    def test_raw_sql_cannot_rewrite_a_stored_record_either(self):
        """Sxem qatı bəsdir deyil: PG trigger-i də xam SQL-i bloklayır."""

        if connection.vendor != "postgresql":
            self.skipTest("append-only trigger yalnız PostgreSQL-dədir")
        document = self._document()
        with bypass_rls():
            for statement in (
                "UPDATE registrar_legacyexcusedocument SET note = 'saxta' WHERE id = %s",
                "DELETE FROM registrar_legacyexcusedocument WHERE id = %s",
            ):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute(statement, [str(document.pk)])
            assert LegacyExcuseDocument.objects.get(pk=document.pk).note == "Texnopark"

    def test_a_linked_record_must_carry_a_student_and_a_window(self):
        with bypass_rls():
            document = LegacyExcuseDocument(
                **_SOURCE,
                organization=self.org,
                source_pk=99,
                mapping_status=LegacyExcuseMappingStatus.LINKED,
            )
            with self.assertRaises(ValidationError):
                document.full_clean()

    def test_an_unresolved_record_may_not_point_at_a_student(self):
        with bypass_rls():
            document = LegacyExcuseDocument(
                **_SOURCE,
                organization=self.org,
                source_pk=98,
                student=self.student,
                mapping_status=LegacyExcuseMappingStatus.STUDENT_UNRESOLVED,
            )
            with self.assertRaises(ValidationError):
                document.full_clean()


class LegacyExcuseReadLayerTest(_ExcuseSetup):
    def test_an_excused_cell_inside_the_window_gets_the_document_entry(self):
        _lesson, mark = self._excused_lesson(8)
        self._document()

        with bypass_rls():
            excuse_map = legacy_excuse.excuse_map_for_offering(self.offering)

        entry = excuse_map[str(mark.id)][0]
        assert entry["kind"] == "legacy_excuse"
        assert entry["note"] == "Texnopark"
        assert entry["document"] == "1697461819.jpg"
        assert entry["document_available"] is False
        # Sınıq link VERİLMİR — fayl hədəfdə yoxdur.
        assert "document_url" not in entry
        assert entry["period"] == "07.10.2024 – 09.10.2024"
        # Bu bir DƏYİŞİKLİK deyil: köhnə → yeni sətri yoxdur.
        assert "old" not in entry and "new" not in entry

    def test_a_cell_outside_the_window_and_a_plain_absence_stay_untouched(self):
        _outside, outside_mark = self._excused_lesson(20)
        _absent_lesson, absent_mark = self._absent_lesson(8)
        self._document()

        with bypass_rls():
            excuse_map = legacy_excuse.excuse_map_for_offering(self.offering)

        assert str(outside_mark.id) not in excuse_map
        assert str(absent_mark.id) not in excuse_map

    def test_an_unresolved_document_never_reaches_the_journal(self):
        _lesson, mark = self._excused_lesson(8)
        self._document(
            student=None,
            mapping_status=LegacyExcuseMappingStatus.STUDENT_UNRESOLVED,
            starts_on=None,
            ends_on=None,
        )

        with bypass_rls():
            assert legacy_excuse.excuse_map_for_offering(self.offering) == {}

    def test_the_grid_is_flagged_without_locking_the_cell_for_the_teacher(self):
        _lesson, mark = self._excused_lesson(8)
        self._document()

        with bypass_rls():
            journal = gradebook.get_offering_journal(offering=self.offering, newest_first=True)
            corrections_map = {}
            legacy_excuse.attach_to_offering_journal(self.offering, journal, corrections_map)

        cell = next(c for row in journal["rows"] for c in row["cells"] if c["mark"] and c["mark"].id == mark.id)
        assert cell["legacy_excuse"] is True
        # ``corrected`` rəsmi (sənədli) düzəliş + müəllim kilidi deməkdir —
        # köhnə sənəd onu QALDIRMIR.
        assert cell["corrected"] is False
        assert str(mark.id) in corrections_map

    def test_the_student_view_never_exposes_the_attached_file_url(self):
        _lesson, mark = self._excused_lesson(8)
        document = self._document()
        with bypass_rls():
            legacy_excuse.attach_document(
                document, SimpleUploadedFile("1697461819.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")
            )
            student_map = legacy_excuse.excuse_map_for_enrollment(self.enrollment)
            teacher_map = legacy_excuse.excuse_map_for_offering(self.offering)

        assert "document_url" not in student_map[str(mark.id)][0]
        assert student_map[str(mark.id)][0]["document_available"] is True
        assert "document_url" in teacher_map[str(mark.id)][0]

    def test_merging_keeps_existing_correction_history_first(self):
        _lesson, mark = self._excused_lesson(8)
        self._document()
        corrections_map = {str(mark.id): [{"kind": "grade"}]}

        with bypass_rls():
            merged = legacy_excuse.merge_into(corrections_map, legacy_excuse.excuse_map_for_offering(self.offering))

        assert [entry["kind"] for entry in merged[str(mark.id)]] == ["grade", "legacy_excuse"]
