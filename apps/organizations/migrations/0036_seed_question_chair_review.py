"""Mövcud tenantlara `question.chair_review` açarını əkir.

SAHİBİN TƏLƏBİ (2026-09): müəllimin imtahan sual dəsti (final və ya aralıq)
İmtahan Mərkəzinə BİRBAŞA getmir — əvvəlcə KAFEDRA MÜDİRİ təsdiqləyir.

Açar iki adlı rola verilir (``default_roles_university.py`` ilə eyni nəticə —
yeni tenant onsuz da düzgün seed olunur):

* ``chair_head`` — ƏSAS təsdiqçi (yalnız öz kafedrası; əhatə
  ``Membership.scope_unit`` ilə fail-closed yoxlanılır);
* ``dean`` — YALNIZ FALLBACK: kafedra müdiri təyin edilməyibsə göndəriş
  dekanlığa yönləndirilir (``QuestionSubmission.routed_to_dean``).  Kafedra
  müdiri olan göndərişə dekan qərar VERƏ BİLMİR.

⚠️ `*` və ya `question.*` daşıyan rola TOXUNULMUR (rektor/prorektor/RİM onsuz
da əhatələnir).  İdempotentdir; geri dönüş yalnız bu iki roldan açarı çıxarır.
"""

from django.db import migrations

_PERMISSION = "question.chair_review"
_TARGET_ROLES = ("chair_head", "dean")
_WILDCARDS = ("*", "question.*")


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=_TARGET_ROLES).iterator():
        permissions = list(role.permissions or [])
        if _PERMISSION in permissions or any(card in permissions for card in _WILDCARDS):
            continue
        permissions.append(_PERMISSION)
        role.permissions = permissions
        role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=_TARGET_ROLES).iterator():
        permissions = list(role.permissions or [])
        remaining = [perm for perm in permissions if perm != _PERMISSION]
        if len(remaining) == len(permissions):
            continue
        role.permissions = remaining
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0035_dean_syllabus_review_only")]

    operations = [migrations.RunPython(forward, backward)]
