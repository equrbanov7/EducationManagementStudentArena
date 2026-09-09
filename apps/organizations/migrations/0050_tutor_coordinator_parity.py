"""Tyutor = proqram koordinatoru — eyni icazə dəsti (sahib qərarı, 2026-09-09).

SAHİBİN QƏRARI: «Cədvəl idarəetməsi hissəsi proqram koordinatoru və tyutorda
olacaq — onlar 2-si eyni rol özəlliklərinə malik olmalıdır; elə deyilsə əl et
onu». Əvvəl tyutorda yalnız 5 baxış açarı vardı (`member.view`, `course.view`,
`exam.view`, `people.view_students`, `analytics.view_unit`) və `schedule.manage`
YOX idi, ona görə «Cədvəl idarəetməsi» bölməsi ona ümumiyyətlə açılmırdı.

Seed xəritəsi (``default_roles_university._COORDINATOR_PERMISSIONS``) YENİ
tenant üçün yeniləndi; bu migrasiya MÖVCUD tenantların ``tutor`` roluna həmin
açarları idempotent ƏKİR (0047 ilə eyni üsul):

* rol YARADILMIR — yalnız mövcud sətirlərə açar əlavə olunur;
* `*` (wildcard) olan rol toxunulmur;
* artıq mövcud açar (və ya `prefix.*` forması) təkrarlanmır;
* `level` / `scope_type` / `display_name` DƏYİŞMİR — tyutor 40-da qalır.

Geri dönüş yalnız BU migrasiyanın əkdiyi əlavə açarları çıxarır; tyutorun
tarixi baxış açarları (``_BASE_KEYS``) toxunulmur.
"""

from django.db import migrations

_ROLE = "tutor"
_WILDCARD = "*"

#: Tyutorun 2026-09-09-a qədərki tarixi dəsti — geri dönüşdə SAXLANILIR.
_BASE_KEYS = ("member.view", "course.view", "exam.view", "people.view_students", "analytics.view_unit")

#: Koordinatordan gələn ƏLAVƏ açarlar (seed siyahısı ilə eyni sıra).
_ADDED_KEYS = (
    "people.manage_academic",
    "group.manage",
    "unit.view",
    "journal.roster",
    "schedule.view",
    "schedule.manage",
)


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE).iterator():
        permissions = list(role.permissions or [])
        if _WILDCARD in permissions:
            continue
        changed = False
        for key in _ADDED_KEYS:
            prefix_wildcard = "%s.*" % key.split(".", 1)[0]
            if key in permissions or prefix_wildcard in permissions:
                continue
            permissions.append(key)
            changed = True
        if changed:
            role.permissions = permissions
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE).iterator():
        current = list(role.permissions or [])
        if _WILDCARD in current:
            continue
        kept = [key for key in current if key not in _ADDED_KEYS or key in _BASE_KEYS]
        if kept != current:
            role.permissions = kept
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0049_ikt_rehber_level_95")]

    operations = [migrations.RunPython(forward, backward)]
