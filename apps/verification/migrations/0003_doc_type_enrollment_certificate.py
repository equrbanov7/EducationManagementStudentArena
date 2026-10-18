"""Yeni sənəd növü — «Təhsil aldığı yer haqqında arayış» (sahib 2026-10-19). Yalnız ``choices``: sxem dəyişmir."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("verification", "0002_seed_document_seal_permission"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documentseal",
            name="doc_type",
            field=models.CharField(
                choices=[
                    ("transcript", "Akademik transkript"),
                    ("enrollment_certificate", "Təhsil aldığı yer haqqında arayış"),
                ],
                max_length=32,
            ),
        ),
    ]
