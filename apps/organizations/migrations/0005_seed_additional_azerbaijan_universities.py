from django.db import migrations


def seed_additional_azerbaijan_universities(apps, schema_editor):
    Country = apps.get_model("organizations", "Country")
    Institution = apps.get_model("organizations", "Institution")

    az, _ = Country.objects.get_or_create(code="AZ", defaults={"name": "Azerbaijan", "is_active": True})

    universities = [
        ("Baku State University", "UNI-BSU"),
        ("ADA University", "UNI-ADA"),
        ("Azerbaijan State University of Economics (UNEC)", "UNI-UNEC"),
        ("Azerbaijan Technical University", "UNI-AZTU"),
        ("Azerbaijan University of Architecture and Construction", "UNI-AUAC"),
        ("Khazar University", "UNI-KHAZAR"),
        ("Azerbaijan Medical University", "UNI-AMU"),
        ("Azerbaijan State Oil and Industry University", "UNI-ASOIU"),
        ("Baku Engineering University", "UNI-BEU"),
        ("Western Caspian University", "UNI-WCU"),
    ]

    for name, code in universities:
        Institution.objects.get_or_create(
            country=az,
            institution_type="university",
            name=name,
            defaults={"code": code, "is_active": True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0004_country_institution"),
    ]

    operations = [
        migrations.RunPython(seed_additional_azerbaijan_universities, migrations.RunPython.noop),
    ]
