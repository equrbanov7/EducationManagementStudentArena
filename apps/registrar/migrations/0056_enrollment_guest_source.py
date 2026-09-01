"""«Alt qrupdan əlavə olunub» (guest) provenansı — Enrollment sahələri + DB qoruyucuları.

Yeni MODEL yaradılmır: jurnal sətirləri onsuz da ``offering.enrollments``-dan
qurulur, ona görə başqa qrupdan əlavə olunan tələbə üçün lazım olan yeganə şey
MƏNBƏ işarəsidir (``source_group``) + audit izləri (``added_by``/``added_at``).
Təkrar əlavənin qarşısını mövcud ``uniq_student_offering`` unikal məhdudiyyəti
onsuz da alır.

DB qoruyucuları (Postgres):

* ``registrar_same_org_source_group_guard`` — mövcud ``registrar_guard_same_org_fk``
  funksiyasını təkrar işlədir: mənbə qrup tələbənin təşkilatına aid olmalıdır.
* ``registrar_enrollment_source_group_setonce_guard`` — provenans BİR DƏFƏ yazılır;
  doludursa dəyişdirilə/silinə bilməz (audit izini yenidən yazmaq mümkün olmasın).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_SET_ONCE_SQL = r"""
CREATE OR REPLACE FUNCTION public.registrar_guard_enrollment_source_group()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF OLD.source_group_id IS NOT NULL
       AND NEW.source_group_id IS DISTINCT FROM OLD.source_group_id THEN
        RAISE EXCEPTION 'enrollment guest source group is write-once'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
"""


def _install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_SET_ONCE_SQL)
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS registrar_same_org_source_group_guard ON public.registrar_enrollment"
    )
    schema_editor.execute(
        "CREATE TRIGGER registrar_same_org_source_group_guard "
        "BEFORE INSERT OR UPDATE OF source_group_id, organization_id ON public.registrar_enrollment "
        "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_same_org_fk("
        "'source_group_id', 'organizations_orgunit', 'guest source group')"
    )
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS registrar_enrollment_source_group_setonce_guard ON public.registrar_enrollment"
    )
    schema_editor.execute(
        "CREATE TRIGGER registrar_enrollment_source_group_setonce_guard "
        "BEFORE UPDATE OF source_group_id ON public.registrar_enrollment "
        "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_enrollment_source_group()"
    )


def _remove(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS registrar_enrollment_source_group_setonce_guard ON public.registrar_enrollment"
    )
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS registrar_same_org_source_group_guard ON public.registrar_enrollment"
    )
    schema_editor.execute("DROP FUNCTION IF EXISTS public.registrar_guard_enrollment_source_group()")


class Migration(migrations.Migration):
    dependencies = [
        ("registrar", "0055_program_official_code_alter_program_code"),
        ("organizations", "0013_alter_orgunit_unit_type"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="enrollment",
            name="source_group",
            field=models.ForeignKey(
                blank=True,
                help_text="Doludursa: tələbə BU açılışa başqa (alt) qrupdan əlavə olunub — mənbə qrup.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="guest_enrollments",
                to="organizations.orgunit",
            ),
        ),
        migrations.AddField(
            model_name="enrollment",
            name="added_by",
            field=models.ForeignKey(
                blank=True,
                help_text="Alt qrupdan əlavəni edən aktor (koordinator/dekanlıq).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="guest_enrollments_added",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="enrollment",
            name="added_at",
            field=models.DateTimeField(blank=True, help_text="Alt qrupdan əlavə vaxtı.", null=True),
        ),
        migrations.RunPython(_install, _remove),
    ]
