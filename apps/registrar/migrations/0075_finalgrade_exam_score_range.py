"""``registrar_finalgrade.exam_score`` üçün diapazon CHECK-i (2026-09-13 məlumat auditi, F1 · P1).

Audit (QA klonu, ``13_followup2.out`` §13.1–13.4): canlı qiymət cədvəlində
**349** sətirdə ``exam_score > 50`` (max 89,00), hamısı ``entry_score_max=50``
sxemində, yəni imtahan tavanı 50-dir. Legacy faktlarla müqayisə göstərdi ki,
miqrasiya sadiqdir — MƏNBƏ məlumatı şkaladan kənardır (bəzi jurnal sətirlərində
«imtahan» sütununa yekun bal yazılıb). ``finals.compute_final_result`` cəmi 100-ə
clamp edir, amma transkriptdə imtahan balı 89 kimi görünür. Yeni daxil etmə
(``finals.set_exam_score``) ``_clamp`` ilə qorunur; DB-də CHECK isə yox idi.

Nə edir
-------
* Model state-inə ``registrar_finalgrade_exam_score_range`` CheckConstraint-i
  əlavə olunur (``makemigrations --check`` təmiz qalır).
* DB-də eyni CHECK **``NOT VALID``** ilə yaradılır: PostgreSQL mövcud sətirləri
  YOXLAMIR (349 legacy sətir miqrasiyanı dayandırmır), amma hər yeni INSERT və
  UPDATE üçün tətbiq edir. Köhnə sətirlər İmtahan Mərkəzinin qərarını gözləyir —
  akademik nəticə burada yenidən yazılmır.

Pozan sətirlərin siyahısı (İmtahan Mərkəzi üçün, yalnız oxu)::

    SELECT fg.id, fg.exam_score, e.student_id, e.offering_id
    FROM registrar_finalgrade fg
    JOIN registrar_enrollment e ON e.id = fg.enrollment_id
    WHERE fg.exam_score < 0 OR fg.exam_score > 50
    ORDER BY fg.exam_score DESC;

Sətirlər düzəldildikdən sonra (ayrıca əməliyyat, miqrasiya deyil)::

    ALTER TABLE registrar_finalgrade VALIDATE CONSTRAINT registrar_finalgrade_exam_score_range;

Orkestrator qərarı: diapazon 0..100-dür (50 deyil) — legacy J-V2 qaydası >50
dəyəri olduğu kimi yazıb ``legacy_journal_exam_score_above_scheme`` ilə
işarələyir; 50-lik CHECK həmin fazanı dayandırardı. Yeni yazı yolu ``_clamp``
ilə 50-də qalır; CHECK yalnız zibil (mənfi / >100) dəyərləri tutur.

Qeyri-PostgreSQL backend-də (yerli SQLite) DB əməliyyatı yoxdur — yalnız
state; geri qaytarıla bilir.
"""

from django.db import migrations, models

CONSTRAINT_NAME = "registrar_finalgrade_exam_score_range"
TABLE = "registrar_finalgrade"

_ADD_NOT_VALID_SQL = f"""
ALTER TABLE {TABLE}
    ADD CONSTRAINT {CONSTRAINT_NAME}
    CHECK (exam_score IS NULL OR (exam_score >= 0 AND exam_score <= 100))
    NOT VALID;
"""

_DROP_SQL = f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME};"


_STATE_CONSTRAINT = models.CheckConstraint(
    condition=models.Q(exam_score__isnull=True) | models.Q(exam_score__gte=0, exam_score__lte=100),
    name=CONSTRAINT_NAME,
)


def _add_not_valid(apps, schema_editor):
    # SQLite ``ALTER TABLE … ADD CONSTRAINT`` dəstəkləmir; test/prod PostgreSQL-dir.
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_ADD_NOT_VALID_SQL)


def _drop(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_DROP_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0074_rls_guest_roster_document"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddConstraint(model_name="finalgrade", constraint=_STATE_CONSTRAINT),
            ],
            database_operations=[
                migrations.RunPython(_add_not_valid, _drop),
            ],
        ),
    ]
