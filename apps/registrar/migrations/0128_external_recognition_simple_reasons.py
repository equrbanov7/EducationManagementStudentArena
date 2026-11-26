"""«Fəndən azad etmə» səbəbləri (sahib 2026-11-27): «Kurs / sertifikat», «Kollec nəticəsi» + xarici fənnin izi
(ölkə, xarici fənn, kredit, qiymət, müddət) yalnız Erasmus+ / mübadilədə məcburi. Mövcud sətirlər dəyişmir
(sxem əməli — append-only trigger-i UPDATE/DELETE-i qoruyur, ALTER-ə toxunmur)."""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0087_foreign_students_office"),
        ("registrar", "0127_group_transfer_removal"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="externalcreditrecognition",
            name="reg_recog_foreign_credit_positive",
        ),
        migrations.RemoveConstraint(
            model_name="externalcreditrecognition",
            name="reg_recog_program",
        ),
        migrations.AlterField(
            model_name="externalcreditrecognition",
            name="country",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AlterField(
            model_name="externalcreditrecognition",
            name="foreign_credit",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AlterField(
            model_name="externalcreditrecognition",
            name="foreign_grade",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AlterField(
            model_name="externalcreditrecognition",
            name="foreign_subject",
            field=models.CharField(blank=True, default="", max_length=300),
        ),
        migrations.AlterField(
            model_name="externalcreditrecognition",
            name="institution",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="externalcreditrecognition",
            name="program",
            field=models.CharField(
                choices=[
                    ("course", "Kurs / sertifikat"),
                    ("college", "Kollec nəticəsi"),
                    ("other_university", "Başqa ali məktəb"),
                    ("erasmus", "Erasmus+"),
                    ("exchange", "Mübadilə proqramı"),
                    ("other", "Digər (adını yazın)"),
                ],
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="externalcreditrecognition",
            name="study_period",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddConstraint(
            model_name="externalcreditrecognition",
            constraint=models.CheckConstraint(
                condition=models.Q(("foreign_credit__isnull", True), ("foreign_credit__gt", 0), _connector="OR"),
                name="reg_recog_foreign_credit_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalcreditrecognition",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("program__in", ["course", "college", "other_university", "erasmus", "exchange", "other"])
                ),
                name="reg_recog_program",
            ),
        ),
    ]
