"""RİM rəhbərinin səviyyəsi 88 → 95 (sahib qərarı, 2026-09-09).

SƏBƏB: «RİM rəhbərinin səviyyə limitini superadminden bir aşağı et — 95 də ola
bilər, səlahiyyəti olsun deyə hər şeyə». Seed xəritəsi
(``default_roles_university``) və ``core.roles.ProfileRole.LEVELS`` yeni tenant
üçün yeniləndi; bu migrasiya MÖVCUD tenantların ``ikt_rehber`` rol sətrini eyni
səviyyəyə gətirir (0047 ilə eyni idempotent üsul).

PRAKTİK NƏTİCƏ: ``organizations.scoping.ORG_WIDE_MIN_LEVEL`` 90-dır, ona görə 95
ilə RİM ümumi scope resolverindən də ORG-WIDE əhatə alır (əvvəl 88 ilə yalnız
permission-spesifik resolverdən alırdı). İcazə açarları DƏYİŞMİR.

Geri dönüş səviyyəni 88-ə qaytarır.
"""

from django.db import migrations

_ROLE = "ikt_rehber"
_NEW_LEVEL = 95
_OLD_LEVEL = 88


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    Role.objects.filter(name=_ROLE, level__lt=_NEW_LEVEL).update(level=_NEW_LEVEL)


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    Role.objects.filter(name=_ROLE, level=_NEW_LEVEL).update(level=_OLD_LEVEL)


class Migration(migrations.Migration):
    dependencies = [("organizations", "0048_lab_assistant_lessons_unit")]

    operations = [migrations.RunPython(forward, backward)]
