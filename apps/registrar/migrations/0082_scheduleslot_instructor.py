"""Cədvəl slotunun REAL müəllimi — ``ScheduleSlot.instructor`` (bölünmüş tədris, 2026-09-25).

Mühazirəni jurnal sahibi (``CourseOffering.instructor``), seminarı/laboratoriyanı isə başqa
müəllim (assistent) aparır. Əvvəl slotda müəllim sahəsi yox idi: B-nin seminarı hər yerdə
A-nın adı ilə görünür, B öz «Dərs cədvəli»ndə onu görmür və B-nin toqquşmaları tutulmurdu.

* ``instructor`` — nullable FK, ``SET_NULL``; NULL = «jurnal sahibi» (effektiv müəllim
  ``offering.instructor``). BÜTÜN mövcud sətirlər NULL qalır → davranış dəyişmir; jurnal
  sahibi dəyişəndə (fənn təhvili) override-sız slotlar yeni sahibi izləyir.
* PostgreSQL qoruyucusu: slotun müəllimi ``Lesson.instructor`` / ``CourseOffering.instructor``
  kimi AKTİV, ``grade.input`` səlahiyyətli üzv olmalıdır (``0041``
  ``registrar_guard_active_member`` funksiyası, eyni trigger adı) — «Dərsi aktivləşdir» slotun
  müəllimini dərsə köçürür, orada da eyni qoruyucu var. Servis qatı eyni qaydanı əvvəlcədən
  yoxlayır (``schedule_slot_teachers``). Qeyri-PostgreSQL backend-də no-op; geri qaytarılır.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_TABLE = "registrar_scheduleslot"
_TRIGGER = "registrar_active_member_instructor_guard"


def _install_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON public.{_TABLE}")
    schema_editor.execute(
        f"CREATE TRIGGER {_TRIGGER} BEFORE INSERT OR UPDATE OF instructor_id, organization_id "
        f"ON public.{_TABLE} FOR EACH ROW EXECUTE FUNCTION "
        "public.registrar_guard_active_member('instructor_id', 'grade.input', 'instructor')"
    )


def _remove_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON public.{_TABLE}")


class Migration(migrations.Migration):
    dependencies = [
        ("registrar", "0081_selfwork_points"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduleslot",
            name="instructor",
            field=models.ForeignKey(
                blank=True,
                help_text="Slotu aparan müəllim (boş = jurnal sahibi).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(_install_guard, _remove_guard),
    ]
