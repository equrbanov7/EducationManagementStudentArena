"""Fənnin başqa müəllimə TƏHVİLİ — dəyişməz təhvil qeydi (audit + geri qaytarma).

SAHİBİN TƏLƏBİ (2026-08): «tarix fənnini Elvin keçir, Elvin işdən çıxdı, o fənni
Əliyə assign edə bilim, jurnal artıq Əlinin olsun, o görsün.»

NƏ KÖÇÜR VƏ NƏ KÖÇMÜR
---------------------
Köçən YEGANƏ şey ``CourseOffering.instructor``-dur. Jurnal sahibliyi bu sahədən
oxunur (:mod:`apps.registrar.journal_access`), ona görə sahəni dəyişmək jurnalı
bütövlükdə yeni müəllimə verir — əlavə köçürməyə ehtiyac yoxdur.

**Köhnə data TOXUNULMUR** (sahibin qırmızı xətti):

* ``LessonMark`` / ``ComponentScore`` / ``FinalGrade`` — bal və davamiyyət
  olduğu kimi qalır; sətirlərin ``created_by``/audit izləri yenidən yazılmır.
* ``Lesson.instructor`` — həmin dərsi FAKTİKİ keçən adamın qeydidir; keçmiş
  dərsin müəllimini dəyişmək tarixi saxtalaşdırmaq olardı. Boş (NULL) dərslər
  jurnalda açılışın CARİ müəllimini göstərir — yəni gələcək dərslər avtomatik
  yeni müəllimin adına düşür, keçmişlər isə yerində qalır.
* ``Syllabus`` — sillabus MÜƏLLİFƏ bağlıdır (``apps.syllabus``), açılışa yox;
  təhvil onun sahibliyini DƏYİŞMİR (bax :mod:`apps.registrar.handover` şərhi).

NİYƏ AYRICA MODEL (audit sətri kifayət etmir)
---------------------------------------------
``AuditLog`` axtarış/hesabat üçündür, DAVRANIŞ üçün deyil. Bu qeyd üç şeyi
daşıyır: (1) geri qaytarma üçün lazım olan «kimdən» dəyəri, (2) köhnə müəllimin
YALNIZ-OXU jurnal görünüşünün əsası, (3) UI-da təhvil tarixçəsi. Bunları audit
JSON-undan oxumaq kövrək olardı.

⚠️ Ad SNAPSHOT-ları (``from_instructor_name`` / ``to_instructor_name``) qəsdən
saxlanılır: hesab sonradan silinsə (SET_NULL) təhvil tarixçəsi «— → —» olmasın.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..reference_identity import ReferenceIdentityValidationMixin


class TeachingHandover(ReferenceIdentityValidationMixin, UUIDModel, TimeStampedModel):
    """Bir dərs açılışının bir müəllimdən digərinə təhvil verilməsi (bir hadisə).

    Zəncir sərbəstdir: A → B → C üç sətir yaradır. Geri qaytarma (``revert``)
    YENİ sətir yaratmır — mövcud sətri «geri qaytarılmış» kimi işarələyir və
    açılışın müəllimini ``from_instructor``-a qaytarır. Beləliklə tarixçə
    şişmir və «bu təhvil qüvvədədirmi» sualının tək cavabı olur.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="teaching_handovers"
    )
    offering = models.ForeignKey(
        "registrar.CourseOffering",
        on_delete=models.CASCADE,
        related_name="handovers",
        help_text="Təhvil verilən dərs açılışı (fənn × semestr × qrup).",
    )
    from_instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="handovers_given",
        help_text="Təhvildən ƏVVƏLKİ müəllim (boş ola bilər — açılış müəllimsiz idi).",
    )
    to_instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="handovers_received",
        help_text="Təhvildən SONRAKI müəllim.",
    )
    from_instructor_name = models.CharField(max_length=255, blank=True)
    to_instructor_name = models.CharField(max_length=255, blank=True)

    reason = models.TextField(help_text="Təhvilin səbəbi — MƏCBURİDİR (audit sualının cavabı).")
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="teaching_handovers_performed",
        help_text="Təhvili aparan aktor (RİM / dekan / kafedra müdiri).",
    )

    # ── Geri qaytarma (səhv təyinatın düzəlişi) ──────────────────────────────
    reverted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reverted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="teaching_handovers_reverted",
    )
    revert_reason = models.TextField(blank=True)

    #: Yeni müəllimə bildiriş göndərildimi (təkrar göndərməmək üçün).
    notified = models.BooleanField(default=False)

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.handover.meta", "fənn təhvili qeydi")
        verbose_name_plural = pgettext_lazy("registrar.model.handover.meta", "fənn təhvili qeydləri")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "offering", "-created_at"]),
            models.Index(fields=["organization", "from_instructor"]),
            models.Index(fields=["organization", "to_instructor"]),
        ]

    def __str__(self):
        return f"{self.offering_id}: {self.from_instructor_name or '—'} → {self.to_instructor_name or '—'}"

    @property
    def is_reverted(self) -> bool:
        return self.reverted_at is not None


__all__ = ["TeachingHandover"]
