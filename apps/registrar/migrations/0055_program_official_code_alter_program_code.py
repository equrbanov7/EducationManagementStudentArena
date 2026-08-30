"""Program.official_code — rəsmi dövlət ixtisas kodu (istifadəçiyə göstərilən).

``Program.code`` DAXİLİ identifikator olaraq qalır və ``uniq_program_code_per_org``
məhdudiyyəti TOXUNULMAZDIR — köçürmə xətti (``apps.legacy_import``) həmin kodun
tenant-unikallığına söykənir. Yeni sahə isə QƏSDƏN unikal deyil: bir rəsmi kod
bir neçə proqrama aid ola bilər (060209 → dörd magistr psixologiya proqramı).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0054_legacy_grade_attempts_and_artifacts"),
    ]

    operations = [
        migrations.AddField(
            model_name="program",
            name="official_code",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Rəsmi dövlət ixtisas kodu (məs. 060209) — istifadəçiyə göstərilən koddur. Unikal DEYİL: bir kod bir neçə proqrama (magistr istiqamətləri, AZ/EN bölmələri, əyani/qiyabi formalar) aid ola bilər.",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="program",
            name="code",
            field=models.CharField(
                help_text="Daxili sabit identifikator (tenant daxilində unikal) — istifadəçiyə göstərilmir.",
                max_length=32,
            ),
        ),
    ]
