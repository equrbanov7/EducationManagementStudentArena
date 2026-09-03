"""Köhnə sistemdən gələn ÜZRLÜ QAYIB sənədinin dəyişdirilməz mənbə qeydi.

Niyə ayrıca model (``JournalCorrection`` DEYİL)
----------------------------------------------
``JournalCorrection`` bir xananın DƏYİŞDİRİLMƏSİDİR: köhnə dəyər → yeni dəyər,
səbəb + qeyd + PDF, düzəldənin adı.  Köçürmədə isə heç nə dəyişmir — xana artıq
``excused`` (üq) yazılıb, çünki J4 (``journal_marks``) qayıbı məhz bu
``allowed_qb`` pəncərələri ilə üzürlü sayır (``rehearsal_journal_points_source
.is_excused``).  Çatışmayan yeganə şey SÜBUTdur: kim göndərib, nə vaxt, hansı
tarix aralığı üçün, hansı izahla və hansı sənədlə.  ``JournalCorrection`` sətri
uydurmaq "old_status == new_status" olan saxta düzəliş yazmaq olardı — həm
audit tarixçəsini, həm müəllim kilidini yalan məlumatla doldurardı.

Ona görə bu model ``LegacyGradeFact`` ilə eyni ailədəndir: xam mənbə faktının
append-only snapshot-u.  UI isə YENİ bir mexanizm qurmur — mövcud SARI xana +
✎ tarixçə modalını (``registrar/partials/_correction_history_modal.html``)
təkrar işlədir; oxu qatı ``apps/registrar/legacy_excuse.py``-dədir.

Sənədin ÖZÜ hələ bizdə yoxdur
-----------------------------
Canlı mənbədə 2,964 sətrin hamısında fayl ADI var (``1697461819.jpg`` — vaxt
möhürü), faylların özü isə köhnə serverdə qalıb.  Ona görə ``document`` sahəsi
BOŞ köçürülür və UI sınıq yükləmə linki vermir, «sənəd köhnə sistemdədir»
deyir.  Sahib faylları serverdən gətirəndə ``attach_document`` ilə sonradan
qoşulur — bu modelin YEGANƏ icazəli mutasiyasıdır (bax ``save``).
Addım-addım prosedur: ``docs/migration/UZRLU_QAYIB_SENEDLERI.md``.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel
from core.upload_security import FileUploadValidator

SHA256_RE = r"\A[0-9a-f]{64}\Z"
TOKEN_RE = r"\A[a-z0-9][a-z0-9._-]{0,63}\Z"
sha256_validator = RegexValidator(SHA256_RE, "SHA-256 lowercase hex formatında olmalıdır.")
token_validator = RegexValidator(TOKEN_RE, "Dəyər təhlükəsiz token formatında olmalıdır.")

#: Canlı ``allowed_qb.file`` uzantı bölgüsü: jpg 928 · pdf 674 · docx 574 ·
#: jpeg 486 · png 295 · jfif 7.  Sonradan qoşulan fayl da məhz bu dəstdən ola
#: bilər — başqa uzantı yüklənməsi fail-closed rədd olunur.
LEGACY_EXCUSE_EXTENSIONS = frozenset({".pdf", ".jpg", ".jpeg", ".jfif", ".png", ".docx"})
_MAX_DOCUMENT_MB = 25

#: ``desc`` canlıda ən uzunu 109 simvoldur; tavan gen saxlanır ki, kəsim
#: ``legacy_excuse_note_truncated`` ilə hesabata düşsün, sükutla itməsin.
NOTE_MAX_LENGTH = 2000
DOCUMENT_NAME_MAX_LENGTH = 64


def legacy_excuse_document_path(instance, filename: str) -> str:
    """Qorunan media altında org-scoped saxlama yolu (sonradan qoşulan fayl)."""

    return f"legacy_excuse_documents/{instance.organization_id}/{filename}"


class LegacyExcuseMappingStatus(models.TextChoices):
    """Mənbə sətrinin hədəfə bağlanma vəziyyəti."""

    LINKED = "linked", pgettext_lazy("registrar.legacy_excuse_mapping", "Bağlanıb")
    STUDENT_UNRESOLVED = (
        "student_unresolved",
        pgettext_lazy("registrar.legacy_excuse_mapping", "Tələbə tapılmadı"),
    )
    WINDOW_INVALID = (
        "window_invalid",
        pgettext_lazy("registrar.legacy_excuse_mapping", "Yararsız tarix aralığı"),
    )


class _AppendOnlyQuerySet(models.QuerySet):
    """Toplu mutasiya HEÇ VAXT — sətir səviyyəsində belə yalnız fayl qoşulur."""

    def update(self, **kwargs):
        raise ValidationError("Legacy excuse evidence is immutable.")

    def delete(self):
        raise ValidationError("Legacy excuse evidence cannot be deleted.")


class _AppendOnlyManager(models.Manager.from_queryset(_AppendOnlyQuerySet)):
    pass


class LegacyExcuseDocument(UUIDModel, TimeStampedModel):
    """Bir ``allowed_qb`` sətri: tələbə + tarix aralığı + izah + sənəd adı.

    Yazıldıqdan sonra YEGANƏ dəyişə bilən sahə ``document``-dir və o da yalnız
    BOŞDAN DOLUYA gedə bilər (bax ``save``).  Beləliklə sahibin qaydası —
    «köhnə datanı dəyişmirik» — sxem səviyyəsində qorunur, faylın sonradan
    qoşulması isə bloklanmır.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="legacy_excuse_documents"
    )
    # Tələbə tapılmasa da sətir SAXLANIR (data itmir) — ``mapping_status``
    # ``student_unresolved`` olur.  Canlı mənbədə 8 belə sətir var.
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="legacy_excuse_documents",
    )

    source_system = models.CharField(max_length=64, validators=[token_validator])
    source_table = models.CharField(max_length=64, validators=[token_validator])
    source_pk = models.PositiveBigIntegerField()
    source_snapshot_sha256 = models.CharField(max_length=64, validators=[sha256_validator])
    source_row_hash = models.CharField(max_length=64, validators=[sha256_validator])
    materialization_digest = models.CharField(max_length=64, validators=[sha256_validator])
    transform_version = models.CharField(max_length=64, validators=[token_validator])

    mapping_status = models.CharField(max_length=24, choices=LegacyExcuseMappingStatus.choices)
    source_student_ref = models.CharField(max_length=64, blank=True, default="")
    # Sənədi sistemə yükləyən köhnə işçinin id-si (canlıda 4 nəfər).
    source_owner_ref = models.CharField(max_length=64, blank=True, default="")
    # ``uniq``: BİR sənəd paketinin açarıdır — eyni akt bir neçə tələbəyə aiddirsə
    # sətirlər eyni ``uniq`` və eyni ``file`` daşıyır (canlı: 2,964 sətir → 977
    # paket, 773 fayl).  Jurnal ``uniqid``-i DEYİL.
    source_batch_ref = models.CharField(max_length=32, blank=True, default="")

    # Üzürlü sayılan aralıq — J-V3 qaydasının işlətdiyi məhz bu iki tarixdir.
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    # Mənbənin xam (saat daxil) mətni; parse nəticəsi ilə yanaşı itkisiz qalır.
    source_window_text = models.CharField(max_length=64, blank=True, default="")
    source_recorded_at_text = models.CharField(max_length=32, blank=True, default="")

    note = models.TextField(blank=True, default="", help_text="Köhnə sistemdəki izah (``desc``).")
    #: Köhnə serverdəki faylın adı — vaxt möhürü + uzantı (``1697461819.jpg``).
    document_name = models.CharField(max_length=DOCUMENT_NAME_MAX_LENGTH, blank=True, default="")
    document = models.FileField(
        upload_to=legacy_excuse_document_path,
        blank=True,
        default="",
        validators=[
            FileUploadValidator(allowed_extensions=set(LEGACY_EXCUSE_EXTENSIONS), max_size_mb=_MAX_DOCUMENT_MB)
        ],
        help_text="Boşdur: sənəd köhnə sistemdədir, sonradan qoşula bilər.",
    )

    objects = _AppendOnlyManager()

    class Meta:
        ordering = ["source_table", "source_pk"]
        verbose_name = pgettext_lazy("registrar.model.legacy_excuse.meta", "üzrlü qayıb sənədi")
        verbose_name_plural = pgettext_lazy("registrar.model.legacy_excuse.meta", "üzrlü qayıb sənədləri")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "source_system", "source_table", "source_pk"],
                name="registrar_legacy_excuse_source_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(starts_on__isnull=True, ends_on__isnull=True)
                | models.Q(starts_on__isnull=False, ends_on__isnull=False, ends_on__gte=models.F("starts_on")),
                name="registrar_legacy_excuse_window_ordered",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "student"], name="reg_legacy_excuse_org_std"),
            models.Index(fields=["organization", "starts_on"], name="reg_legacy_excuse_org_start"),
        ]

    def clean(self):
        super().clean()
        linked = self.mapping_status == LegacyExcuseMappingStatus.LINKED
        if linked and (not self.student_id or self.starts_on is None or self.ends_on is None):
            raise ValidationError({"student": "Bağlanmış üzrlü qayıb sənədində tələbə və tarix aralığı olmalıdır."})
        if self.mapping_status == LegacyExcuseMappingStatus.STUDENT_UNRESOLVED and self.student_id:
            raise ValidationError({"student": "Həll olunmamış qeyd tələbəyə bağlana bilməz."})

    def save(self, *args, **kwargs):
        """Append-only + BİR istisna: boş ``document`` sonradan doldurula bilər.

        Fayl bir dəfə qoşulduqdan sonra dəyişdirilə/silinə bilməz; qalan bütün
        sahələr yazıldığı andan dəyişməzdir.
        """

        if self._state.adding:
            return super().save(*args, **kwargs)
        update_fields = kwargs.get("update_fields")
        if update_fields is None or set(update_fields) - {"document", "updated_at"}:
            raise ValidationError("Legacy excuse evidence is immutable.")
        if not self.document:
            raise ValidationError("An attached legacy excuse document cannot be cleared.")
        stored = type(self)._base_manager.filter(pk=self.pk).values_list("document", flat=True).first()
        if stored:
            raise ValidationError("An attached legacy excuse document cannot be replaced.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Legacy excuse evidence cannot be deleted.")

    @property
    def document_available(self) -> bool:
        """Faylın özü hədəfdədirmi (yoxsa yalnız adı köçürülüb)?"""

        return bool(self.document)

    def __str__(self):
        return f"legacy-excuse<{self.source_table}:{self.source_pk}>"


__all__ = [
    "DOCUMENT_NAME_MAX_LENGTH",
    "LEGACY_EXCUSE_EXTENSIONS",
    "NOTE_MAX_LENGTH",
    "LegacyExcuseDocument",
    "LegacyExcuseMappingStatus",
    "legacy_excuse_document_path",
]
