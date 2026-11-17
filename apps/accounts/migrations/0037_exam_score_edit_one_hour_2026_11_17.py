"""Sahib 2026-11-17: «1 saat balları redaktə etmək müddəti».

«İmtahan balının daxil edilməsi» ekranında daxil edən təsdiqdən sonra balı sənədsiz dəyişə bildiyi müddət
(``exam.score_edit_minutes``) 15 dəqiqədən 60 dəqiqəyə qalxır. Kodun defoltu da 60-dır
(``core.runtime_settings_exam_scores``); «Sistem tənzimləmələri»ndə açar SAXLANIBSA (sətir varsa) o sətir də 60
olur ki, defolt dəyişikliyi səssizcə üstələnməsin. Sətir yoxdursa yaradılmır (defolt işləyir). Geri miqrasiya
yalnız 60 olan sətri əvvəlki 15-ə qaytarır.
"""

from django.db import migrations

KEY = "exam.score_edit_minutes"
NEW_MINUTES = 60
OLD_MINUTES = 15


def raise_window(apps, schema_editor):
    RuntimeSetting = apps.get_model("accounts", "RuntimeSetting")
    RuntimeSetting.objects.filter(key=KEY).update(value=NEW_MINUTES)


def restore_window(apps, schema_editor):
    RuntimeSetting = apps.get_model("accounts", "RuntimeSetting")
    RuntimeSetting.objects.filter(key=KEY, value=NEW_MINUTES).update(value=OLD_MINUTES)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0036_shared_fin_linked_accounts_2026_11_09"),
    ]

    operations = [
        migrations.RunPython(raise_window, restore_window),
    ]
