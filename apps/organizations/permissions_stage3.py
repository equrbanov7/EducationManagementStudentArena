"""Tələbə qəbulu və reyestri icazələri (dizayn Mərhələ 3, ekran 08–09).

NİYƏ AYRI MODUL? ``permissions_stage2.py`` ilə eyni səbəb: ``permissions.py``
modul ölçüsü büdcəsinə (SOFT_CAP=600) yaxındır. Burada YALNIZ DATA var;
birləşdirmə ``permissions.py``-ın sonunda bir sətirlə olur, yəni kataloq hələ
də TƏK dəstdir (``test_permissions.py`` kataloq ↔ etiket uyğunluğunu yoxlayır).

⚠️ PREFİKS QAYDASI: `student.*` YENİ ailədir və LEGACY siyahısında yoxdur
(`grading.`, `courses.`, `exams.`, `members.`, `structure.`).

QƏSDƏN `people.*`-dan AYRIDIR:

* `people.*` KATALOQ səthidir — «kim var, hansı qrupdadır» (dekan, kafedra
  müdiri, koordinator da daşıyır, struktur scope-una tabedir);
* `student.*` isə TƏLƏBƏ XİDMƏTLƏRİ MƏRKƏZİNİN əməliyyat səthidir — rəsmi
  reyestr (əmr izi + ixrac), əmr-əsaslı hərəkət və qəbulda qrup təyinatı.

Eyni prefiksdə olsaydılar, kataloqa baxış icazəsi verilən hər rol avtomatik
XARİC ETMƏ əmri yaza bilərdi (əsasnamə 5.5 — səlahiyyət ayrılığı).
"""

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

#: ``PERMISSION_CATEGORIES``-ə əlavə olunan yeni kateqoriya.
STAGE3_PERMISSION_CATEGORIES = {
    "student": [
        "student.registry_view",
        "student.movement",
        "student.assign_group",
    ],
}

STAGE3_CATEGORY_LABELS = {
    "student": "Tələbə qəbulu və reyestri",
}

STAGE3_PERMISSION_LABELS = {
    "student.registry_view": pgettext_lazy(_PERM_CTX, "Tələbə reyestrinə baxış (hərəkət tarixçəsi və ixrac)"),
    "student.movement": pgettext_lazy(_PERM_CTX, "Tələbə hərəkəti əmri yazmaq (köçürmə, məzuniyyət, bərpa, xaric)"),
    "student.assign_group": pgettext_lazy(_PERM_CTX, "Qəbulda tələbəni qrupa təyin etmək və qrup yaratmaq"),
}


def merge_stage3(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """Kataloqu YERİNDƏ genişləndirir (idempotent — təkrar çağırış təsirsizdir)."""
    for name, keys in STAGE3_PERMISSION_CATEGORIES.items():
        bucket = categories.setdefault(name, [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    category_labels.update(STAGE3_CATEGORY_LABELS)
    permission_labels.update(STAGE3_PERMISSION_LABELS)


__all__ = [
    "STAGE3_CATEGORY_LABELS",
    "STAGE3_PERMISSION_CATEGORIES",
    "STAGE3_PERMISSION_LABELS",
    "merge_stage3",
]
