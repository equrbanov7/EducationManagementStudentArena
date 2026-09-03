"""`final_score.entry` — kağız imtahan balının əl ilə daxil edilməsi icazəsi.

SAHİBİN QƏRARI (2026-08): yazılı və praktiki imtahan kağız üzərində (yaxud kodda)
keçir — sistemdən getmir. Balları sonradan İMTAHAN MƏRKƏZİ sistemə köçürür:
qrup seçir, formada bir-bir yazır, istəsə imtahan vərəqinin şəklini/PDF-ini və
mətn qeydini əlavə edir. Həmin səth yeni açarla qapılıdır: ``final_score.entry``.

Mövcud tenantlarda:

1. ``*`` daşıyan rollar (rektor / sahib) onsuz da hər şeyi əhatə edir — toxunulmur;
2. ``exam.*`` daşıyan rollar (imtahan mərkəzi, imtahan mərkəzi rəhbəri/işçisi,
   RİM = ``ikt_rehber``, prorektor) da wildcard ilə əhatə olunur — toxunulmur;
3. yalnız DAR imtahan dəsti daşıyan mərkəz rollarına (köhnə tenantlarda
   ``exam.*`` əvəzinə açar-açar yazılmış ola bilər) açar AÇIQ əlavə olunur.

Beləliklə default sahib: imtahan mərkəzi rolları + RİM + rektor. Digər rola
(dekan, kafedra müdiri…) lazım olsa permission-editordan verilir.

İdempotentdir. Geri dönüş: açar yalnız açıq yazılmış yerlərdən çıxarılır.
"""

from django.db import migrations

_PERMISSION = "final_score.entry"

#: Açarın verildiyi rollar — SAHİBİN QƏRARI (2026-08-28): «Daralt, ancaq imtahan
#: mərkəzi imtahan final balını yaza bilsin; müəllim və digərləri yaza bilməsin.»
#: Ona görə siyahı YALNIZ imtahan mərkəzinin qərar verən rollarıdır.
#: `exam_center_staff` (nəzarətçi/monitor) DAXİL DEYİL — bal qərarı vermir.
#: `ikt_rehber` (RİM) DAXİL DEYİL — texniki idarəçidir; lazım olsa permission-
#: editordan AÇIQ verir (audit izi ilə). Rektor `*` ilə onsuz da əhatə olunur.
_EXPLICIT_ROLE_NAMES = (
    "exam_center",
    "exam_center_head",
)


def _covered(permissions) -> bool:
    """Rol bu açarı onsuz da əhatə edirmi.

    DİQQƏT: ``exam.*`` BURADA SAYILMIR — açar qəsdən ``final_score.`` prefiksindədir
    ki, imtahan wildcard-ı onu əhatə etməsin (sahibin daraltma qərarı).
    """
    return "*" in permissions or _PERMISSION in permissions


_LEGACY_PERMISSION = "exam.score_entry"


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    # Yenidən adlandırma təmizliyi: köhnə açar heç bir roldа qalmasın.
    for role in Role.objects.all().iterator():
        permissions = list(role.permissions or [])
        remaining = [perm for perm in permissions if perm != _LEGACY_PERMISSION]
        if len(remaining) != len(permissions):
            role.permissions = remaining
            role.save(update_fields=["permissions"])
    for role in Role.objects.filter(name__in=_EXPLICIT_ROLE_NAMES).iterator():
        permissions = list(role.permissions or [])
        if _covered(permissions):
            continue
        permissions.append(_PERMISSION)
        role.permissions = permissions
        role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        permissions = list(role.permissions or [])
        remaining = [perm for perm in permissions if perm != _PERMISSION]
        if len(remaining) != len(permissions):
            role.permissions = remaining
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0030_journal_close_permission")]

    operations = [migrations.RunPython(forward, backward)]
