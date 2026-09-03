"""Qəbul (ATİS) metadatası — ``StudentAcademicRecord``-un qəbul qatı.

Dizayn handoff Mərhələ 3 (ekran 08 «Tələbə qəbulu», ekran 09 «Tələbə reyestri»).

NİYƏ AYRI MODUL? ``models/academic.py`` 593/600 sətirdir — modul ölçüsü qapısına
(``scripts/check_module_size.py``) dayanıb. Sahələr burada abstrakt bazada
TƏRİF olunur, ``academic.py`` isə yalnız bazanı miras alır.

Nə üçün bu sahələr ``UserProfile``-da deyil, akademik QEYDDƏDİR?
---------------------------------------------------------------
Qəbul balı, imtahan növü, təhsil forması və maliyyələşmə mənbəyi ŞƏXSİN deyil,
onun KONKRET İXTİSASA QƏBULUNUN atributlarıdır. Eyni şəxs ikinci ali təhsilə
başqa balla və başqa formada qəbul oluna bilər (``StudentAcademicRecord``
unikallığı ``(organization, student, program)``-dır) — profildə saxlansaydı,
ikinci qəbul birincini əzərdi.

Ekran 09-un «Forma» və «Təhsil haqqı» sütunları məhz buradan oxunur;
``Program.education_form`` isə İXTİSASIN default formasıdır (ekran 03) —
tələbənin forması ondan FƏRQLƏNƏ bilər (əyanidən qiyabiyə köçürmə, hərəkət №3).
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

from .catalog_meta import EducationForm


class FundingType(models.TextChoices):
    """Maliyyələşmə mənbəyi — ekran 08/09 «Təhsil haqqı» sütunu."""

    STATE = "state", pgettext_lazy("registrar.funding_type", "Dövlət sifarişi")
    PAID = "paid", pgettext_lazy("registrar.funding_type", "Ödənişli")


class AdmissionRecordFields(models.Model):
    """Akademik qeydin qəbul (ATİS) atributları — abstrakt, öz cədvəli yoxdur."""

    #: ATİS (Dövlət İmtahan Mərkəzi) sətir identifikatoru — idxalın idempotentlik
    #: açarı DEYİL (o, FİN-dir); yalnız mənbəyə istinad üçün saxlanılır.
    #: `db_default` (Django 5+) — Django-nun adi `default=` arqumenti YALNIZ
    #: ORM-dən (`Model.save()`) keçən yazılara tətbiq olunur; `AddField`
    #: miqrasiyası mövcud sətirləri doldurmaq üçün MÜVƏQQƏTİ DB defaultu
    #: qoyur, sonra onu SİLİR (Django-nun standart davranışı). Nəticədə xam
    #: SQL `INSERT` (test/legacy-repair/ATİS idxal skripti bu sütunları
    #: buraxsa) `NOT NULL` pozuntusu ilə uğursuz olur — `0068` miqrasiyası
    #: bunu server-side DEFAULT əlavə edərək bağlayır (bax audit
    #: `apps/accounts/tests/test_account_archive_postgres.py`).
    atis_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_default="",
        db_index=True,
        help_text="ATİS qəbul siyahısındakı sətir nömrəsi/identifikatoru.",
    )
    admission_score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Qəbul balı (ATİS).",
    )
    admission_exam_type = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_default="",
        help_text="İmtahan növü/qrupu (məs. «I qrup», «Blok», «Magistratura»).",
    )
    education_form = models.CharField(
        max_length=16,
        choices=EducationForm.choices,
        default=EducationForm.FULL_TIME,
        db_default=EducationForm.FULL_TIME,
        db_index=True,
        help_text="Tələbənin təhsil forması (ixtisasın default formasından fərqlənə bilər).",
    )
    funding_type = models.CharField(
        max_length=16,
        choices=FundingType.choices,
        default=FundingType.PAID,
        db_default=FundingType.PAID,
        db_index=True,
        help_text="Maliyyələşmə mənbəyi (dövlət sifarişi / ödənişli).",
    )

    class Meta:
        abstract = True


__all__ = ["AdmissionRecordFields", "FundingType"]
