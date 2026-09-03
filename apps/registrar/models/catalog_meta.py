"""Akademik kataloq metadatası — arxivləmə qatı + ixtisas/fənn sahə fabrikləri.

Dizayn handoff Mərhələ 1 (ekran 03 «İxtisaslar», ekran 04 «Fənn kataloqu»).

NİYƏ AYRI MODUL? ``models/academic.py`` 582/600 sətirdir — modul ölçüsü qapısına
(``scripts/check_module_size.py``) yaxındır. Sahələr burada TƏRİF olunur,
``academic.py`` isə onları bir sətirlə çağırır.

──────────────────────────────────────────────────────────────────────────────
SİLMƏ YOXDUR — ARXİVLƏMƏ VAR (handoff §8 qayda 5)
──────────────────────────────────────────────────────────────────────────────
İxtisas və fənn NƏ silinir, NƏ də deaktiv edilib izsiz qalır: ``is_archived``
bayrağı + **≥20 simvol səbəb** + aktor + timestamp. Səbəb həm sətirdə, həm də
``core.audit.log_action`` yazısında saxlanılır — sətir tarixi qeyd, audit isə
dəyişməz jurnaldır; ikisi bir-birini əvəz etmir.

``is_active`` (mövcud sahə) TOXUNULMUR: o, «cari semestrdə istifadə olunur»
mənasındadır və köçürmə xətti ona söykənir. Arxiv AYRI bayraqdır — arxivlənmiş
yazı ilə bağlı qiymət, jurnal və sillabus TARİXÇƏSİ olduğu kimi qalır.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

#: Arxivləmə səbəbinin minimum uzunluğu (handoff §8 qayda 6 — bütün səbəb
#: tələb edən əməllərdə eynidir). Servis qatı bunu məcbur edir.
ARCHIVE_REASON_MIN_LENGTH = 20


class EducationForm(models.TextChoices):
    """Təhsil forması — ekran 03 «Təhsil forması» sütunu."""

    FULL_TIME = "full_time", pgettext_lazy("registrar.education_form", "Əyani")
    PART_TIME = "part_time", pgettext_lazy("registrar.education_form", "Qiyabi")
    DISTANCE = "distance", pgettext_lazy("registrar.education_form", "Distant")


class SubjectKind(models.TextChoices):
    """Fənn növü — ekran 04 «Fənn blokları» seçicisinin sadə variantı.

    Handoff-dakı çoxsəviyyəli «fənn blokları» (``SubjectBlock``) MODEL tələb edir
    və tədris planı (ekran 05, Mərhələ 2) ilə birlikdə gəlir; Mərhələ 1-də
    kataloqun özündə YALNIZ bu təsnifat saxlanılır.
    """

    CORE = "core", pgettext_lazy("registrar.subject_kind", "İxtisas fənni")
    GENERAL = "general", pgettext_lazy("registrar.subject_kind", "Ümumi fənn")
    ELECTIVE = "elective", pgettext_lazy("registrar.subject_kind", "Seçmə fənn")
    PRACTICE = "practice", pgettext_lazy("registrar.subject_kind", "Təcrübə")


class ArchivableCatalogModel(models.Model):
    """Kataloq yazısının arxiv qatı (abstrakt — öz cədvəli yoxdur)."""

    is_archived = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Arxivlənmiş yazı reyestrdə süzülür; əlaqəli tarixçə saxlanılır.",
    )
    archived_reason = models.TextField(blank=True, help_text="Arxivləmə səbəbi (≥20 simvol).")
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_archived",
    )

    class Meta:
        abstract = True


def education_form_field():
    """``Program.education_form`` — əyani / qiyabi / distant."""
    return models.CharField(
        max_length=16,
        choices=EducationForm.choices,
        default=EducationForm.FULL_TIME,
        db_index=True,
        help_text="Təhsil forması (əyani/qiyabi/distant).",
    )


def subject_kind_field():
    """``Subject.kind`` — kataloq təsnifatı."""
    return models.CharField(
        max_length=16,
        choices=SubjectKind.choices,
        default=SubjectKind.CORE,
        db_index=True,
        help_text="Fənn növü (ixtisas/ümumi/seçmə/təcrübə).",
    )


def owning_chair_field():
    """``Subject.chair_unit`` — fənni APARAN kafedra.

    String-ref FK (``"organizations.OrgUnit"``): ``registrar`` ``organizations``-ı
    STATİK import etməməlidir (``scripts/module_deps.py`` ratchet-i).
    """
    return models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_subjects",
        help_text="Fənni aparan kafedra (OrgUnit: chair/department).",
    )


__all__ = [
    "ARCHIVE_REASON_MIN_LENGTH",
    "ArchivableCatalogModel",
    "EducationForm",
    "SubjectKind",
    "education_form_field",
    "owning_chair_field",
    "subject_kind_field",
]
