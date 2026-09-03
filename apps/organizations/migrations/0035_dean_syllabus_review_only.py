"""Dekan sillabus QƏRARINI itirir — təsdiq YALNIZ kafedra müdirinindir.

SAHİBİN QƏRARI (2026-09-03). Auditin R-2 tapıntısından sonra aydın oldu ki,
kafedra müdiri sillabusu praktikada heç görmürdü və de-fakto təsdiqçi dekan
idi (fakültə scope-u bütün kafedraları örtür).  Universitetin əsl qaydası
isə əksinədir: sillabusun akademik məzmununa cavabdeh şəxs KAFEDRA
MÜDİRİDİR.

Bu miqrasiya MÖVCUD tenantlarda `dean` adlı rolun sillabus QƏRAR açarlarını
çıxarır (`default_roles_university.py` ilə eyni nəticə — yeni tenant onsuz da
düzgün seed olunur):

    çıxarılır:  syllabus.approve · syllabus.revise · syllabus.reject
    QALIR:      syllabus.view    · syllabus.review

Yəni dekan növbəni AÇIR, oxuyur və şərh yazır — qərar düyməsi yoxdur.
Override yalnız org-wide rollardadır (`*` daşıyan rektor/prorektor və
`syllabus.*` daşıyan RİM); onların hər əməli audit olunur.

⚠️ `*` və ya `syllabus.*` daşıyan rola TOXUNULMUR — wildcard-ı sətir-sətir
sökmək rolun bütün mənasını dəyişərdi; siyahıda konkret açar varsa yalnız o
silinir.

İdempotentdir (ikinci icrada dəyişəcək sətir qalmır).
Geri dönüş: eyni üç açar `dean` rollarına qaytarılır.
"""

from django.db import migrations

#: Dekandan çıxarılan qərar açarları.
_DECISION_PERMISSIONS = ("syllabus.approve", "syllabus.revise", "syllabus.reject")

#: Yalnız bu adlı rol hədəflənir (tenant öz adlı xüsusi rolunu qurubsa
#: toxunulmur — icazə redaktorunda verilmiş açarı miqrasiya geri almır).
_TARGET_ROLE = "dean"


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_TARGET_ROLE).iterator():
        permissions = list(role.permissions or [])
        remaining = [perm for perm in permissions if perm not in _DECISION_PERMISSIONS]
        if len(remaining) == len(permissions):
            continue
        role.permissions = remaining
        role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_TARGET_ROLE).iterator():
        permissions = list(role.permissions or [])
        if "*" in permissions or "syllabus.*" in permissions:
            continue
        added = False
        for permission in _DECISION_PERMISSIONS:
            if permission not in permissions:
                permissions.append(permission)
                added = True
        if added:
            role.permissions = permissions
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0034_seed_user_import_permission")]

    operations = [migrations.RunPython(forward, backward)]
