"""DB-səviyyəli jurnal toxunulmazlığı (2 saat qaydası).

``registrar_lessonmark`` və ``registrar_componentscore`` sətirləri yazılışdan
(``created_at``) 2 saat keçdikdən sonra UPDATE-ə bağlanır — servis qatındakı
pəncərə qaydasının Postgres zəmanəti (ORM-dən yan keçən kod da dəyişə bilməz).

Qəsdən yalnız UPDATE: DELETE cascade yolu ilə legitim admin axınlarından
(tələbə köçürməsi/xaric → enrollment silinməsi) keçir və trigger onları
sındırardı (bax: aktiv-imtahan trigger dərsi). Saxtalaşdırmanın əsas vektoru
mövcud işarənin dəyişdirilməsidir — o bağlanır; boşaldılmış xana isə görünən
izdir və grade_audit tarixçəsi ayrıca cədvəldə qalır.

Rəsmi düzəliş yolu (Tyutor müraciəti → admin əməliyyatı) üçün sessiya GUC
açarı: ``SET app.journal_unlock = 'on'`` — yalnız nəzarətli admin axını qoyur.
No-op off-Postgres (sqlite testləri pəncərəni servis qatında yoxlayır).
"""

from django.db import migrations

_TABLES = ["registrar_lessonmark", "registrar_componentscore"]

_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION registrar_journal_mark_guard() RETURNS trigger AS $$
BEGIN
    IF current_setting('app.journal_unlock', true) = 'on' THEN
        RETURN NEW;
    END IF;
    IF OLD.created_at < (now() - interval '2 hours') THEN
        RAISE EXCEPTION 'journal mark is frozen (2h window elapsed)'
            USING ERRCODE = 'raise_exception';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def _trigger_sql(table):
    return f"""
DROP TRIGGER IF EXISTS trg_journal_mark_guard ON {table};
CREATE TRIGGER trg_journal_mark_guard
    BEFORE UPDATE ON {table}
    FOR EACH ROW EXECUTE FUNCTION registrar_journal_mark_guard();
"""


def _drop_sql(table):
    return f"DROP TRIGGER IF EXISTS trg_journal_mark_guard ON {table};"


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FUNCTION_SQL)
    for table in _TABLES:
        schema_editor.execute(_trigger_sql(table))


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in _TABLES:
        schema_editor.execute(_drop_sql(table))
    schema_editor.execute("DROP FUNCTION IF EXISTS registrar_journal_mark_guard();")


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0023_rls_journal_tables"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
