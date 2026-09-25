"""Sərbəst iş BAL modeli (2026-09-25): sillabus strukturu 1×10 / 2×5 / 10×1.

* ``SelfWorkTopic.max_points`` (1…10, default 1) + ``slot_index`` (sillabus slotu);
* ``SelfWorkMark.points`` (0 < bal ≤ 10, yalnız ``done``), ``source`` (jurnal /
  fənn qovluğu), ``source_ref``, ``graded_at``;
* ``SelfWorkCorrection.old_points`` / ``new_points`` (bal düzəlişi).

KÖHNƏ DATA DƏYİŞMİR: mövcud mövzular ``max_points=1``, işarələr ``points=NULL``
alır — effektiv bal (``points`` → yoxdursa ``done`` × ``max_points``) əvvəlki
«təhvil sayı» ilə EYNİDİR (bax ``apps/registrar/tests/test_selfwork_points_parity.py``).
Yeni NOT NULL sütunlar ``db_default`` daşıyır (xam INSERT-lər üçün, 0068 naxışı).

PostgreSQL qoruyucuları (RLS dəyişmir — cədvəllər eynidir):
* bal mövzunun ``max_points``-undan böyük ola bilməz;
* qiymətli (təhvil/bal) işarəsi olan mövzunun ``max_points``-u DƏYİŞDİRİLƏ
  BİLMƏZ — köhnə çeklist mövzusunu «səssizcə» 5 ballığa çevirmək rəqəmləri
  dəyişərdi (servis bunu ``structure_mismatch`` kimi göstərir).
"""

from django.db import migrations, models

_GUARD_SQL = r"""
CREATE OR REPLACE FUNCTION public.registrar_guard_selfwork_mark_points()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    topic_max integer;
BEGIN
    IF NEW.points IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT max_points INTO topic_max FROM public.registrar_selfworktopic WHERE id = NEW.topic_id;
    IF topic_max IS NULL OR NEW.points > topic_max THEN
        RAISE EXCEPTION 'self-work points exceed the topic maximum'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_selfwork_topic_max_points()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF NEW.max_points IS DISTINCT FROM OLD.max_points AND EXISTS (
        SELECT 1
          FROM public.registrar_selfworkmark mark
         WHERE mark.topic_id = NEW.id
           AND (mark.done OR mark.points IS NOT NULL)
    ) THEN
        RAISE EXCEPTION 'self-work topic with graded marks cannot change its maximum'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.registrar_guard_selfwork_mark_points() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_selfwork_topic_max_points() FROM PUBLIC;

DROP TRIGGER IF EXISTS registrar_selfwork_mark_points_guard ON public.registrar_selfworkmark;
CREATE TRIGGER registrar_selfwork_mark_points_guard
    BEFORE INSERT OR UPDATE OF points, topic_id ON public.registrar_selfworkmark
    FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_selfwork_mark_points();

DROP TRIGGER IF EXISTS registrar_selfwork_topic_max_points_guard ON public.registrar_selfworktopic;
CREATE TRIGGER registrar_selfwork_topic_max_points_guard
    BEFORE UPDATE OF max_points ON public.registrar_selfworktopic
    FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_selfwork_topic_max_points();
"""

_DROP_SQL = r"""
DROP TRIGGER IF EXISTS registrar_selfwork_mark_points_guard ON public.registrar_selfworkmark;
DROP TRIGGER IF EXISTS registrar_selfwork_topic_max_points_guard ON public.registrar_selfworktopic;
DROP FUNCTION IF EXISTS public.registrar_guard_selfwork_mark_points();
DROP FUNCTION IF EXISTS public.registrar_guard_selfwork_topic_max_points();
"""


def _install_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_GUARD_SQL)


def _drop_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_DROP_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0080_lesson_off_schedule_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="selfworkcorrection",
            name="new_points",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True),
        ),
        migrations.AddField(
            model_name="selfworkcorrection",
            name="old_points",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True),
        ),
        migrations.AddField(
            model_name="selfworkmark",
            name="graded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="selfworkmark",
            name="points",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                help_text="Real bal (0 < bal ≤ mövzunun max balı); boşdursa işarə çeklistdir.",
                max_digits=4,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="selfworkmark",
            name="source",
            field=models.CharField(
                choices=[("journal", "Jurnal"), ("subject_folder", "Fənn qovluğu")],
                db_default="journal",
                default="journal",
                help_text="Balın mənbəyi — fənn qovluğundan gələn bal jurnalda yalnız sənədli düzəlişlə dəyişir.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="selfworkmark",
            name="source_ref",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                help_text="Mənbə istinadı (məs. «subject_folder.submission:<uuid>») — idempotentlik + audit.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="selfworktopic",
            name="max_points",
            field=models.PositiveSmallIntegerField(
                db_default=1,
                default=1,
                help_text="Mövzunun maksimum balı: 1 (çeklist / 10 × 1), 5 (2 × 5), 10 (1 × 10).",
            ),
        ),
        migrations.AddField(
            model_name="selfworktopic",
            name="slot_index",
            field=models.PositiveSmallIntegerField(
                blank=True, help_text="Sillabusun sərbəst iş slotu (1…N); köhnə çeklist mövzusunda boşdur.", null=True
            ),
        ),
        migrations.AddConstraint(
            model_name="selfworkcorrection",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("old_points__isnull", True),
                        models.Q(("old_points__gt", 0), ("old_points__lte", 10)),
                        _connector="OR",
                    ),
                    models.Q(
                        ("new_points__isnull", True),
                        models.Q(("new_points__gt", 0), ("new_points__lte", 10)),
                        _connector="OR",
                    ),
                ),
                name="selfwork_correction_points_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="selfworkmark",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("points__isnull", True), models.Q(("points__gt", 0), ("points__lte", 10)), _connector="OR"
                ),
                name="selfwork_mark_points_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="selfworkmark",
            constraint=models.CheckConstraint(
                condition=models.Q(("points__isnull", True), ("done", True), _connector="OR"),
                name="selfwork_mark_points_imply_done",
            ),
        ),
        migrations.AddConstraint(
            model_name="selfworkmark",
            constraint=models.CheckConstraint(
                condition=models.Q(("source__in", ["journal", "subject_folder"])), name="selfwork_mark_source_valid"
            ),
        ),
        migrations.AddConstraint(
            model_name="selfworktopic",
            constraint=models.CheckConstraint(
                condition=models.Q(("max_points__gte", 1), ("max_points__lte", 10)),
                name="selfwork_topic_max_points_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="selfworktopic",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("slot_index__isnull", True),
                    models.Q(("slot_index__gte", 1), ("slot_index__lte", 10)),
                    _connector="OR",
                ),
                name="selfwork_topic_slot_index_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="selfworktopic",
            constraint=models.UniqueConstraint(
                condition=models.Q(("slot_index__isnull", False)),
                fields=("offering", "slot_index"),
                name="uniq_selfwork_topic_offering_slot",
            ),
        ),
        migrations.RunPython(_install_guards, _drop_guards),
    ]
