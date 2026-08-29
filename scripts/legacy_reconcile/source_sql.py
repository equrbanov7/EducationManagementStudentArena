"""Mənbə (MariaDB / MyEdu) tərəfin OXU sorğuları — hamısı aqreqatdır.

5 milyondan çox xana var, ona görə heç bir sorğu bütün sətirləri yaddaşa
çəkmir: qruplaşdırma bazada aparılır, Python-a yalnız yekunlar gəlir.  Yeganə
istisna «nümunə-yoxlama» sorğularıdır — onlar 20 tələbə ilə məhdudlaşır və
``student_id`` indeksindən istifadə edir.
"""

from __future__ import annotations

from .analysis import ARCHIVE_CUTOFF

POINT_TABLE = "journals_dates_points"
ARCHIVE_TABLE = "journals_dates_points_archive"

# Hesabatın §1-də sətir-sətir mühasibatı aparılan mənbə cədvəlləri.
ACCOUNTED_TABLES = (
    "departments",
    "speciality",
    "curricula",
    "curricula_plan",
    "lessons",
    "groups",
    "students",
    "workers",
    "journals",
    "journals_dates_added_by_teacher",
    POINT_TABLE,
    ARCHIVE_TABLE,
    "yekun",
    "imthngrscxsblr",
    "balvereqi_logs",
)

# ``month_id`` → domen.  ``apps/legacy_import/.../points_source.py`` güzgüsü.
_DOMAIN = """CASE
        WHEN {col} REGEXP '^(0[1-9]|1[0-2])$' THEN 'marks'
        WHEN {col} IN ('k1','k2','k3','si') THEN 'components'
        WHEN {col} IN ('im','im2') THEN 'finals'
        ELSE 'unknown_code' END"""

# Yazıla bilən xana qapısı.  ``BINARY`` qəsdəndir: legacy kollasiya hərfə
# həssas deyil, Python müqayisəsi isə həssasdır — güzgü dəqiq olmalıdır.
_WRITABLE = """(
        (s.domain = 'marks'
         AND s.dn REGEXP '^[0-9]+$' AND CAST(s.dn AS UNSIGNED) BETWEEN 1 AND 31
         AND (BINARY s.p IN ('ie','qb') OR (s.p REGEXP '^[0-9]+$' AND CAST(s.p AS UNSIGNED) <= 10)))
     OR (s.domain = 'components' AND s.p REGEXP '^[0-9]+$' AND CAST(s.p AS UNSIGNED) <= 10)
     OR (s.domain = 'finals'     AND s.p REGEXP '^[0-9]+$' AND CAST(s.p AS UNSIGNED) <= 100)
    )"""

_OUTCOME = """CASE
        WHEN s.domain = 'marks' THEN
            CASE WHEN s.dn NOT REGEXP '^[0-9]+$' OR CAST(s.dn AS UNSIGNED) NOT BETWEEN 1 AND 31 THEN 'unreadable'
                 WHEN s.p = '' THEN 'empty'
                 WHEN BINARY s.p IN ('ie','qb') THEN 'writable'
                 WHEN s.p REGEXP '^[0-9]+$' AND CAST(s.p AS UNSIGNED) <= 10 THEN 'writable'
                 ELSE 'unreadable' END
        WHEN s.domain = 'components' THEN
            CASE WHEN s.p = '' THEN 'empty'
                 WHEN s.p REGEXP '^[0-9]+$' AND CAST(s.p AS UNSIGNED) <= 10 THEN 'writable'
                 ELSE 'unreadable' END
        WHEN s.domain = 'finals' THEN
            CASE WHEN s.p = '' THEN 'empty'
                 WHEN s.p REGEXP '^[0-9]+$' AND CAST(s.p AS UNSIGNED) <= 100 THEN 'writable'
                 ELSE 'unreadable' END
        ELSE 'out_of_scope' END"""


def _cell_stream(*, columns: str = "", archive_filtered: bool) -> str:
    """Canlı + arxiv xanalarının vahid axını (təsnifat sütunları ilə).

    ``archive_filtered=True`` olduqda arxivdən yalnız J-V7 kəsimindən ƏVVƏLKİ
    sətirlər gəlir; ``False`` olduqda örtüşən sətirlər də axına düşür və
    ``eligible`` sütunu ilə ayrılır.
    """

    prefix = f"{columns}, " if columns else ""
    eligible = f"CASE WHEN added_date IS NOT NULL AND DATE(added_date) < '{ARCHIVE_CUTOFF}' THEN 1 ELSE 0 END"
    archive_where = (
        f"WHERE added_date IS NOT NULL AND DATE(added_date) < '{ARCHIVE_CUTOFF}'" if archive_filtered else ""
    )
    return f"""
    SELECT 'live' AS src, 1 AS eligible, {prefix}
           {_DOMAIN.format(col='month_id')} AS domain,
           COALESCE(day_number, '') AS dn,
           COALESCE(point, '') AS p
      FROM {POINT_TABLE}
    UNION ALL
    SELECT 'archive', {eligible}, {prefix}
           {_DOMAIN.format(col='month_id')},
           COALESCE(day_number, ''),
           COALESCE(point, '')
      FROM {ARCHIVE_TABLE}
      {archive_where}
    """


def table_counts_sql() -> str:
    """Hər mühasibatlaşdırılan mənbə cədvəlinin xam sətir sayı."""

    parts = [f"SELECT '{table}' AS t, COUNT(*) AS n FROM `{table}`" for table in ACCOUNTED_TABLES]
    return "\n UNION ALL ".join(parts) + ";"


def cell_classification_sql() -> str:
    """``(mənbə cədvəli, arxiv-uyğunluğu, domen, nəticə) → say``."""

    return f"""
SELECT src, eligible, domain, outcome, COUNT(*) AS n FROM (
    SELECT s.src, s.eligible, s.domain, {_OUTCOME} AS outcome
      FROM ({_cell_stream(archive_filtered=False)}) s
) t
GROUP BY src, eligible, domain, outcome
ORDER BY src, eligible, domain, outcome;
"""


def cell_by_enrollment_sql() -> str:
    """``(jurnal uniqid, tələbə, domen) → dedup edilmiş yazıla bilən xana sayı``.

    J-V4 dedup açarı: jurnal + ay + gün + tələbə + saat.  Daxili ``GROUP BY``
    məhz o açarla aparılır — yəni «qalib» xanalar sayılır, uduzanlar yox.
    """

    columns = "journal_uniqid, student_id, month_id AS mid, COALESCE(TIME_FORMAT(time, '%H:%i'), '') AS tm"
    return f"""
SELECT c.journal_uniqid, c.student_id, c.domain, COUNT(*) AS n FROM (
    SELECT s.journal_uniqid, s.student_id, s.domain, s.mid, s.dn, s.tm
      FROM ({_cell_stream(columns=columns, archive_filtered=True)}) s
     WHERE {_WRITABLE}
     GROUP BY s.journal_uniqid, s.student_id, s.domain, s.mid, s.dn, s.tm
) c
GROUP BY c.journal_uniqid, c.student_id, c.domain;
"""


def raw_writable_sql() -> str:
    """Dedup ETMƏDƏN yazıla bilən xana sayı (dublikat pilləsini ölçmək üçün)."""

    return f"""
SELECT s.domain, COUNT(*) AS n
  FROM ({_cell_stream(archive_filtered=True)}) s
 WHERE {_WRITABLE}
 GROUP BY s.domain;
"""


def value_distribution_sql() -> str:
    """Xana dəyərlərinin forma paylanması: ``ie`` / ``qb`` / rəqəm / digər."""

    return f"""
SELECT src, domain, shape, COUNT(*) AS n FROM (
    SELECT s.src, s.domain,
           CASE WHEN s.p = '' THEN 'boş'
                WHEN BINARY s.p = 'ie' THEN 'ie (davamiyyət: iştirak edib)'
                WHEN BINARY s.p = 'qb' THEN 'qb (davamiyyət: qayıb)'
                WHEN s.p REGEXP '^[0-9]+$' THEN 'rəqəm (bal)'
                ELSE 'digər (oxunmayan)' END AS shape
      FROM ({_cell_stream(archive_filtered=False)}) s
     WHERE s.eligible = 1
) t
GROUP BY src, domain, shape
ORDER BY src, domain, n DESC;
"""


YEKUN_JOINED_SQL = """
SELECT y.student_id, COALESCE(j.uniqid, ''), COALESCE(y.girish, -1),
       COALESCE(y.imtahanda, -1), COALESCE(y.yekun, -1)
  FROM yekun y
  LEFT JOIN journals j ON j.id = y.journal_id;
"""

QUALITY_SQL = """
SELECT 'students_no_name', COUNT(*) FROM students
 WHERE TRIM(COALESCE(first_name, '')) = '' OR TRIM(COALESCE(last_name, '')) = ''
UNION ALL SELECT 'students_no_group', COUNT(*) FROM students WHERE COALESCE(group_id, 0) = 0
UNION ALL SELECT 'students_orphan_group', COUNT(*) FROM students s
   WHERE COALESCE(s.group_id, 0) <> 0 AND NOT EXISTS (SELECT 1 FROM `groups` g WHERE g.id = s.group_id)
UNION ALL SELECT 'students_dup_fincode', COUNT(*) FROM (
     SELECT fincode FROM students WHERE TRIM(COALESCE(fincode, '')) <> ''
      GROUP BY fincode HAVING COUNT(*) > 1) d
UNION ALL SELECT 'students_dup_name', COUNT(*) FROM (
     SELECT first_name, last_name, father_name FROM students
      GROUP BY first_name, last_name, father_name HAVING COUNT(*) > 1) n
UNION ALL SELECT 'workers_no_name', COUNT(*) FROM workers
   WHERE TRIM(COALESCE(first_name, '')) = '' OR TRIM(COALESCE(last_name, '')) = ''
UNION ALL SELECT 'journals_no_teacher', COUNT(*) FROM journals WHERE COALESCE(teacher_id, 0) = 0
UNION ALL SELECT 'journals_orphan_teacher', COUNT(*) FROM journals j
   WHERE COALESCE(j.teacher_id, 0) <> 0 AND NOT EXISTS (SELECT 1 FROM workers w WHERE w.id = j.teacher_id)
UNION ALL SELECT 'journals_orphan_lesson', COUNT(*) FROM journals j
   WHERE COALESCE(j.lesson_id, 0) <> 0 AND NOT EXISTS (SELECT 1 FROM lessons l WHERE l.id = j.lesson_id)
UNION ALL SELECT 'journals_dup_uniqid', COUNT(*) FROM (
     SELECT uniqid FROM journals GROUP BY uniqid HAVING COUNT(*) > 1) u
UNION ALL SELECT 'groups_orphan_speciality', COUNT(*) FROM `groups` g
   WHERE COALESCE(g.speciality_id, 0) <> 0
     AND NOT EXISTS (SELECT 1 FROM speciality sp WHERE sp.id = g.speciality_id)
UNION ALL SELECT 'yekun_orphan_journal', COUNT(*) FROM yekun y
   WHERE NOT EXISTS (SELECT 1 FROM journals j WHERE j.id = y.journal_id)
UNION ALL SELECT 'yekun_orphan_student', COUNT(*) FROM yekun y
   WHERE NOT EXISTS (SELECT 1 FROM students s WHERE s.id = y.student_id);
"""

STUDENT_POOL_SQL = """
SELECT s.id, CONCAT_WS(' ', COALESCE(s.last_name, ''), COALESCE(s.first_name, '')),
       COALESCE(g.name, ''), COALESCE(sp.name, gsp.name, '')
  FROM students s
  LEFT JOIN `groups` g ON g.id = s.group_id
  LEFT JOIN speciality sp ON sp.id = s.speciality_id
  LEFT JOIN speciality gsp ON gsp.id = g.speciality_id;
"""


def sample_cells_sql(student_ids) -> str:
    """Seçilmiş tələbələrin XAM xanaları — J-V4 dedup Python-da aparılır.

    Nümunə kiçikdir (20 tələbə), ona görə burada aqreqat yox, xam sətir çəkilir:
    dedup «qalib» qaydası (``update_counter`` → ``updated_at`` → ``id``) SQL-də
    yox, saf funksiyada tətbiq olunur ki, testlə örtülsün.
    """

    ids = ",".join(str(int(value)) for value in student_ids)
    cutoff = f"WHERE added_date IS NOT NULL AND DATE(added_date) < '{ARCHIVE_CUTOFF}'"
    columns = """journal_uniqid, student_id, month_id, COALESCE(day_number, '') AS dn,
           COALESCE(TIME_FORMAT(time, '%H:%i'), '') AS tm, COALESCE(point, '') AS p,
           COALESCE(update_counter, 0) AS uc, COALESCE(CAST(updated_at AS CHAR), '') AS ua, id"""
    return f"""
SELECT * FROM (
    SELECT {columns} FROM {POINT_TABLE} WHERE student_id IN ({ids})
    UNION ALL
    SELECT {columns} FROM {ARCHIVE_TABLE} {cutoff} AND student_id IN ({ids})
) c;
"""


def sample_yekun_sql(student_ids) -> str:
    """Seçilmiş tələbələrin ``yekun`` sətirləri (fənn adı ilə)."""

    ids = ",".join(str(int(value)) for value in student_ids)
    return f"""
SELECT y.student_id, COALESCE(j.uniqid, ''), COALESCE(l.name, ''),
       COALESCE(y.girish, -1), COALESCE(y.imtahanda, -1), COALESCE(y.yekun, -1)
  FROM yekun y
  LEFT JOIN journals j ON j.id = y.journal_id
  LEFT JOIN lessons l ON l.id = y.lesson_id
 WHERE y.student_id IN ({ids});
"""


def journal_subject_sql() -> str:
    """``uniqid → fənn adı`` (nümunə cədvəlində sütun başlığı üçün)."""

    return """
SELECT j.uniqid, COALESCE(l.name, CONCAT('#', j.lesson_id))
  FROM journals j LEFT JOIN lessons l ON l.id = j.lesson_id;
"""
