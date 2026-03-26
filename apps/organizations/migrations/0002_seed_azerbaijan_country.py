from django.db import migrations


def seed_azerbaijan_country(apps, schema_editor):
    Country = apps.get_model("organizations", "Country")

    country = Country.objects.filter(code="AZ").first()
    if country:
        updates = []
        if country.name != "Azerbaijan":
            country.name = "Azerbaijan"
            updates.append("name")
        if not country.is_active:
            country.is_active = True
            updates.append("is_active")
        if updates:
            country.save(update_fields=updates)
        return

    country = Country.objects.filter(name__iexact="Azerbaijan").first()
    if country:
        updates = []
        if country.code != "AZ":
            country.code = "AZ"
            updates.append("code")
        if not country.is_active:
            country.is_active = True
            updates.append("is_active")
        if updates:
            country.save(update_fields=updates)
        return

    Country.objects.create(
        code="AZ",
        name="Azerbaijan",
        is_active=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_azerbaijan_country, migrations.RunPython.noop),
    ]
