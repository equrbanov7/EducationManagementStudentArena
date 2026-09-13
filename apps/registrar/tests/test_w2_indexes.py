"""W2 2026-09-14 — perf auditi 2026-09-13 §6 (Q3) + data auditi §6.2: indeks miqrasiyaları.

* `registrar_lesson_org_date_idx (organization_id, date) INCLUDE (offering_id, hours)`
  miqrasiyadan sonra mövcuddur (registrar 0076, CONCURRENTLY).
* 9 dublikat indeks cütünün artıq üzvü silinib, qalan üzvü (FK / unikal indeks)
  yerindədir — accounts 0023, appeals 0004, courses 0002, exams 0067, registrar 0076.
* `pg_index` üzrə auditorun dublikat sorğusu (`08_schema.sql` §8.3) boş qaytarır.
* `makemigrations --check` — model `Meta` ilə miqrasiya vəziyyəti üst-üstə düşür.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase

import pytest

# (cədvəl, silinən dublikat, saxlanılan indeks)
DUPLICATE_PAIRS = (
    ("accounts_userprofile", "accounts_us_role_e16858_idx", "accounts_userprofile_role_f557a06b"),
    (
        "accounts_userprofile",
        "accounts_us_request_9a72ac_idx",
        "accounts_userprofile_requested_organization_id_14043874",
    ),
    ("appeals_scoreadjustment", "score_adj_attempt_idx", "appeals_scoreadjustment_attempt_id_d1d212f5"),
    ("courses_course", "courses_cou_slug_2e551f_idx", "courses_course_slug_key"),
    ("courses_coursegroup", "courses_cou_course__225864_idx", "courses_coursegroup_course_id_f11bd514"),
    ("courses_coursegroup", "courses_cou_instruc_f2ed74_idx", "courses_coursegroup_instructor_id_241d6cee"),
    ("courses_coursetopic", "courses_cou_course__0e20e3_idx", "courses_coursetopic_course_id_order_47c9c1f8_uniq"),
    ("exams_examstudentpin", "exam_student_pin_idx", "uniq_exam_student_pin"),
    ("registrar_resitrecord", "registrar_resitrecord_enrollment_id_ba0fb850", "uniq_resit_per_enrollment"),
)

DUPLICATE_SQL = """
SELECT indrelid::regclass::text AS tbl, array_agg(indexrelid::regclass::text ORDER BY indexrelid::regclass::text)
FROM pg_index
WHERE indrelid IN (SELECT oid FROM pg_class WHERE relnamespace = 'public'::regnamespace)
GROUP BY indrelid, indkey, indclass, indpred, indexprs
HAVING count(*) > 1
ORDER BY 1
"""


def _indexes_of(table: str) -> dict[str, str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' AND tablename = %s", [table]
        )
        return dict(cursor.fetchall())


@pytest.mark.postgres
class LessonOrgDateIndexTest(TestCase):
    def test_lesson_org_date_covering_index_exists(self):
        indexes = _indexes_of("registrar_lesson")
        self.assertIn("registrar_lesson_org_date_idx", indexes)
        definition = indexes["registrar_lesson_org_date_idx"]
        self.assertIn("(organization_id, date)", definition)
        self.assertIn("INCLUDE (offering_id, hours)", definition)
        # Mövcud kompozit indeks qalır (açılış üzrə jurnal sorğuları).
        self.assertTrue(
            any("(organization_id, offering_id, date)" in d for d in indexes.values()),
            "mövcud (organization_id, offering_id, date) indeksi itib",
        )


@pytest.mark.postgres
class DuplicateIndexesRemovedTest(TestCase):
    def test_duplicate_member_dropped_and_survivor_kept(self):
        for table, dropped, kept in DUPLICATE_PAIRS:
            with self.subTest(table=table, dropped=dropped):
                indexes = _indexes_of(table)
                self.assertNotIn(dropped, indexes, f"{table}: {dropped} hələ də var")
                self.assertIn(kept, indexes, f"{table}: {kept} itib")

    def test_no_duplicate_key_indexes_remain(self):
        with connection.cursor() as cursor:
            cursor.execute(DUPLICATE_SQL)
            rows = cursor.fetchall()
        self.assertEqual(rows, [], f"dublikat indeks cütləri qalıb: {rows}")


class MigrationsInSyncTest(TestCase):
    def test_makemigrations_check_is_clean(self):
        out = StringIO()
        call_command("makemigrations", "--check", "--dry-run", stdout=out, verbosity=1)
        self.assertIn("No changes detected", out.getvalue())
