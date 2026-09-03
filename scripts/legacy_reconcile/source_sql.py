"""Mənbə (MariaDB / MyEdu) tərəfin OXU sorğuları.

5 milyondan çox xana var, ona görə heç bir sorğu XAM sətirləri yaddaşa çəkmir:
qruplaşdırma bazada aparılır.  İki istisna var:

* ``sample_cells_sql`` — 20 tələbə ilə məhdudlaşır (``student_id`` indeksi);
* ``cell_election_keys_sql`` — importer-in ``CellElection`` prefiltrini
  mənbənin eyni açar axını ilə yenidən qurur;
* ``deduped_cell_keys_sql`` — dedup edilmiş xana AÇARLARINI qaytarır (~5 M sətir)
  və ``SourceReader.iter_query`` ilə AXIDILIR, siyahıya yığılmır.
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
         AND (BINARY s.p IN ('ie','qb') OR (s.p REGEXP '^[0-9]+$' AND CAST(s.p AS UNSIGNED) <= 10)))
     OR (s.domain = 'components' AND s.p REGEXP '^[0-9]+$' AND CAST(s.p AS UNSIGNED) <= 10)
     OR (s.domain = 'finals'     AND s.p REGEXP '^[0-9]+$' AND CAST(s.p AS UNSIGNED) <= 100)
    )"""

_OUTCOME = """CASE
        WHEN s.domain = 'marks' THEN
            CASE WHEN s.p = '' THEN 'empty'
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


def cell_election_keys_sql() -> str:
    """J4/J5/J6 ``CellElection.observe`` üçün xam domen açarları.

    Importer exact-dublikatlardan əlavə eyni bit-bucket-ə düşən açarları da
    ikinci keçidin sonuna saxlayır. Bu sıra hədəf toqquşmasının qalibini dəyişə
    bildiyi üçün yalnız SQL ``COUNT(*)``-u kifayət deyil: eyni açarlar Python-da
    importer-in öz ``CellElection`` sinfinə axıdılır. Yazıla bilməyən sətirlər
    də QƏSDƏN daxildir — importer seçkini ``distill``-dən əvvəl aparır.
    """

    time_text = """CASE WHEN time IS NULL OR TIME_TO_SEC(time) < 0 OR TIME_TO_SEC(time) >= 86400
                         THEN '' ELSE TIME_FORMAT(time, '%H:%i') END"""
    return f"""
SELECT source_table, pk, journal_uniqid, student_id, mid, dn, tm, domain
  FROM (
        SELECT 0 AS source_order, '{POINT_TABLE}' AS source_table, id AS pk,
               COALESCE(journal_uniqid, '') AS journal_uniqid,
               COALESCE(student_id, 0) AS student_id,
               COALESCE(month_id, '') AS mid,
               COALESCE(day_number, '') AS dn,
               {time_text} AS tm,
               {_DOMAIN.format(col='month_id')} AS domain
          FROM {POINT_TABLE}
        UNION ALL
        SELECT 1, '{ARCHIVE_TABLE}', id,
               COALESCE(journal_uniqid, ''), COALESCE(student_id, 0),
               COALESCE(month_id, ''), COALESCE(day_number, ''),
               {time_text}, {_DOMAIN.format(col='month_id')}
          FROM {ARCHIVE_TABLE}
         WHERE added_date IS NOT NULL AND DATE(added_date) < '{ARCHIVE_CUTOFF}'
       ) s
 WHERE domain <> 'unknown_code'
 ORDER BY source_order, pk;
"""


def deduped_cell_keys_sql() -> str:
    """J-V4 QALİB xanaları — importer-in faktiki qərar sırasında.

    J4/J5/J6 canlı cədvəl və arxiv üçün AYRI ``CellElection`` qurur.  Seçki
    domen sətrinin yazıla bilib-bilmədiyinə baxmazdan ƏVVƏL aparılır; buna görə
    daha yüksək rütbəli boş/oxunmayan sətir yazıla bilən aşağı rütbəli sətri
    həqiqətən uda bilər.  Bu sorğu həmin iki invariantı SQL-də güzgüləyir:

    * ``source_order`` seçkini canlı/arxiv üzrə ayırır;
    * ``ROW_NUMBER`` qalibi bütün domen sətirlərindən seçir, ``_WRITABLE`` isə
      yalnız bundan SONRA tətbiq olunur.

    Importer PK axınında unikal açarları dərhal emal edir, seçki tələb edən
    dublikat açarların qalibini isə cədvəlin sonunda emal edir.  Son ``ORDER BY``
    bunu da saxlayır: canlı → arxiv, unikal → seçilmiş dublikat, PK.

    Son iki texniki sütun replay-in yaddaş qapağı üçündür: mənbə cədvəli/PK-sı
    konflikt sübutunun dəqiq identity-sidir; ``local_target_repeat`` isə tək
    legacy yazılışın iki fərqli J-V4 açarının eyni normallaşmış hədəf açarına
    düşdüyünü bildirir.  Beləcə yalnız real namizəd hədəf açarları yadda saxlanır.

    ⚠️ Nəticə ~5 milyon sətirdir — ``SourceReader.iter_query`` ilə AXIDILMALIDIR,
    ``query()`` ilə yaddaşa çəkilməməlidir.
    """

    return f"""
WITH cell_stream AS (
    SELECT 0 AS source_order, '{POINT_TABLE}' AS source_table, 0 AS is_archive,
           id AS pk, journal_uniqid, student_id, month_id AS mid,
           COALESCE(day_number, '') AS dn,
           CASE WHEN time IS NULL OR TIME_TO_SEC(time) < 0 OR TIME_TO_SEC(time) >= 86400
                THEN '' ELSE TIME_FORMAT(time, '%H:%i') END AS tm,
           COALESCE(point, '') AS p, COALESCE(update_counter, 0) AS uc,
           COALESCE(CAST(updated_at AS CHAR), '') AS ua,
           {_DOMAIN.format(col='month_id')} AS domain
      FROM {POINT_TABLE}
    UNION ALL
    SELECT 1, '{ARCHIVE_TABLE}', 1, id, journal_uniqid, student_id, month_id,
           COALESCE(day_number, ''),
           CASE WHEN time IS NULL OR TIME_TO_SEC(time) < 0 OR TIME_TO_SEC(time) >= 86400
                THEN '' ELSE TIME_FORMAT(time, '%H:%i') END,
           COALESCE(point, ''), COALESCE(update_counter, 0),
           COALESCE(CAST(updated_at AS CHAR), ''),
           {_DOMAIN.format(col='month_id')}
      FROM {ARCHIVE_TABLE}
     WHERE added_date IS NOT NULL AND DATE(added_date) < '{ARCHIVE_CUTOFF}'
), ranked AS (
    SELECT s.*,
           COUNT(*) OVER (
               PARTITION BY source_order, journal_uniqid, student_id, mid, dn, tm
           ) AS election_count,
           ROW_NUMBER() OVER (
               PARTITION BY source_order, journal_uniqid, student_id, mid, dn, tm
               ORDER BY uc DESC, ua DESC, pk DESC
           ) AS election_rank
      FROM cell_stream s
     WHERE domain <> 'unknown_code'
), elected AS (
    SELECT s.*
      FROM ranked s
     WHERE election_rank = 1 AND {_WRITABLE}
), annotated AS (
    SELECT s.*,
           COUNT(*) OVER (
               PARTITION BY journal_uniqid, student_id, domain,
                            CASE WHEN domain = 'marks' AND
                                           (dn NOT REGEXP '^[0-9]+$' OR
                                            CAST(dn AS UNSIGNED) NOT BETWEEN 1 AND 31)
                                 THEN '00' ELSE mid END,
                            CASE WHEN domain = 'marks' AND dn REGEXP '^[0-9]+$'
                                           AND CAST(dn AS UNSIGNED) BETWEEN 1 AND 31
                                 THEN CAST(dn AS UNSIGNED) ELSE 0 END,
                            CASE WHEN domain = 'marks' THEN tm ELSE '' END
           ) AS local_target_count
      FROM elected s
)
SELECT journal_uniqid, student_id, domain, mid, dn, tm, p,
       source_table, pk, is_archive,
       CASE WHEN local_target_count > 1 THEN 1 ELSE 0 END AS local_target_repeat
  FROM annotated
 ORDER BY source_order, CASE WHEN election_count > 1 THEN 1 ELSE 0 END, pk;
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


def lesson_slot_source_sql() -> str:
    """MƏNBƏDƏKİ dərs slotlarının indeksi — ``(uniqid, ay, gün, "HH:MM")``.

    Nərdivanın «dərs slotu MƏNBƏDƏ yoxdur» pilləsi bu sorğu ilə HƏDƏFDƏN ASILI
    OLMADAN ölçülür.  Sual budur: hədəfdə dərsi tapılmayan xananın həmin dərsi
    MƏNBƏDƏ ümumiyyətlə varmı?

    * **Yoxdursa** — itki köçürmə qüsuru deyil, mənbənin öz boşluğudur; J12
      (``journal_lesson_recovery``) məhz bu sinfi xananın öz ``(ay, gün, saat)``
      açarından bərpa edir, yəni bərpadan sonra pillə SIFIRA enir.
    * **Varsa** — dərs sətri mənbədə olub, hədəfə düşməyib: bu, TAMAM BAŞQA
      səbəbdir (J3-ün orphan/karantin/dublikat qərarları) və hesabatda AÇIQ
      sual kimi qalır.

    Açar J3-ün öz açarının güzgüsüdür: dərs sətri jurnala ``journal_id`` (int
    FK) ilə bağlanır, xana cədvəli isə ``journal_uniqid`` mətnini daşıyır — ona
    görə indeks ``journals`` üzərindən birləşdirilir.  ``journals``-də qarşılığı
    olmayan 28 orphan sətir bu birləşmədə təbii olaraq düşür (onlar heç bir
    xananı izah edə bilməz).

    ⚠️ İL SÜTUNU YOXDUR (J3 sənədinə bax) — həm mənbə slotu, həm də xananın öz
    açarı yalnız ``(ay, gün, saat)``-dır; müqayisə eyni ölçüdədir.
    """

    return """
SELECT DISTINCT j.uniqid, t.month, t.day, t.time
  FROM journals_dates_added_by_teacher t
  JOIN journals j ON j.id = t.journal_id;
"""
