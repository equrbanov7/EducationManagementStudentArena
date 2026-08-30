"""Sillabus dosyesi və versiyaları.

``Syllabus`` — bir fənnin bir semestrdəki sillabus DOSYESİ (dəyişməz lövbər).
``SyllabusVersion`` — həmin dosyenin nömrələnmiş, statuslu versiyası; state
maşınının (README §4) daşıyıcısı məhz budur.

Çoxkirayəçilik: hər cədvəldə birbaşa ``organization`` FK var və RLS/FORCE RLS
migrasiya ilə qoşulur (mövcud ``registrar_examscoreentry`` nümunəsi).

Modul sərhədi: burada ``apps.*`` importu YOXDUR — registrar/organizations
modellərinə yalnız STRING FK ilə istinad olunur (module_deps qrafında əlavə
kənar yaratmır).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy

from core.models import ActiveManager, TimeStampedModel, UUIDModel

from ..constants import OPEN_STATUSES, REASON_REQUIRED_STATUSES, SyllabusStatus

_CTX = "syllabus.model"


class ChangeKind(models.TextChoices):
    """Versiyanın necə yarandığı."""

    INITIAL = "initial", pgettext_lazy(_CTX, "İlk versiya")
    MINOR = "minor", pgettext_lazy(_CTX, "Kiçik dəyişiklik (cari semestr)")
    MAJOR = "major", pgettext_lazy(_CTX, "Böyük dəyişiklik (növbəti semestr)")
    COPIED = "copied", pgettext_lazy(_CTX, "Keçən ildən köçürülüb")
    IMPORTED = "imported", pgettext_lazy(_CTX, "Köhnə sistemdən köçürülüb")


class ApprovalSource(models.TextChoices):
    """Təsdiqin MƏNBƏYİ — insan qərarı ilə köçürmə damğasını ayırır.

    ⚠️ Sahibin qərarı (2026-08): köçürülən köhnə sillabuslar «TƏSDİQLƏNMİŞ»
    statusla gəlir, amma SAXTA insan təsdiqi UYDURULMUR. Belə qeydlərdə
    ``approved_by`` NULL qalır və mənbə ``migration`` damğalanır; UI təsdiqləyəni
    «sistem/köçürmə» kimi göstərir.
    """

    HUMAN = "human", pgettext_lazy(_CTX, "İnsan qərarı")
    MIGRATION = "migration", pgettext_lazy(_CTX, "Sistem / köçürmə")


class Syllabus(UUIDModel, TimeStampedModel):
    """Bir fənnin bir semestrdəki sillabus dosyesi.

    ÜÇ identifikasiya forması var (üç qismən UNIQUE məhdudiyyət):

    1. ``offering`` dolu — konkret açılış (qrup + müəllim). Normal axın.
    2. ``offering`` boş, ``period`` dolu — semestr səviyyəli dosye.
    3. HƏR İKİSİ boş — «baza sillabus»: köhnə sistemdən köçürülmüş, semestri
       BİLİNMƏYƏN qeyd (bax ``docs/migration/SILLABUS_KOCURME_SPEC.md``).
       Semestr uydurmaq əvəzinə dosye fənn + müəllim cütü ilə lövbərlənir;
       müəllim ondan «Keçən ildən köçür» ilə semestrli qaralama yaradır.
    """

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="syllabi")
    subject = models.ForeignKey("registrar.Subject", on_delete=models.PROTECT, related_name="syllabi")
    period = models.ForeignKey(
        "organizations.AcademicPeriod",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="syllabi",
        help_text="Semestr. Köçürülmüş «baza sillabus»da BOŞDUR — uydurma tarix yazılmır.",
    )
    offering = models.ForeignKey(
        "registrar.CourseOffering",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="syllabi",
        help_text="Fənn açılışı (qrup + müəllim). Köçürülmüş tarixi qeydlərdə boş ola bilər.",
    )
    program = models.ForeignKey(
        "registrar.Program",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="syllabi",
        help_text="İxtisas — siyahıda fənn adının altında göstərilir.",
    )
    chair_unit = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="syllabi",
        help_text="Təsdiq edən kafedra (OrgUnit). Kafedra müdirinin scope filtri bu sahəyə söykənir.",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="authored_syllabi",
        help_text="Sillabusu yazan müəllim.",
    )
    current_version = models.ForeignKey(
        "syllabus.SyllabusVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Üzərində işlənən / ən son versiya (siyahıda göstərilən).",
    )
    approved_version = models.ForeignKey(
        "syllabus.SyllabusVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Hazırda QÜVVƏDƏ olan təsdiqlənmiş versiya — tələbənin gördüyü.",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sillabus")
        verbose_name_plural = pgettext_lazy(_CTX, "sillabuslar")
        ordering = ["subject__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "offering"],
                condition=Q(offering__isnull=False),
                name="uniq_syllabus_per_offering",
            ),
            models.UniqueConstraint(
                fields=["organization", "subject", "period"],
                condition=Q(offering__isnull=True, period__isnull=False),
                name="uniq_syllabus_per_subject_period",
            ),
            # «Baza sillabus» (köçürmə): semestrsiz, fənn + müəllim cütü ilə tək.
            models.UniqueConstraint(
                fields=["organization", "subject", "author"],
                condition=Q(offering__isnull=True, period__isnull=True),
                name="uniq_syllabus_base_per_subject_author",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "period"]),
            models.Index(fields=["organization", "chair_unit"]),
            models.Index(fields=["organization", "author"]),
        ]

    def __str__(self):
        return f"{self.subject_id} @ {self.period_id}"


class SyllabusVersion(UUIDModel, TimeStampedModel):
    """Sillabusun nömrələnmiş versiyası — state maşınının daşıyıcısı.

    Nömrələmə ``major.minor``: kiçik dəyişiklik ``minor``-u artırır (cari
    semestrə tətbiq olunur), böyük dəyişiklik ``major``-u artırıb ``minor``-u
    sıfırlayır (növbəti semestrdən).

    DB səviyyəsində qorunan invariantlar (CheckConstraint):
      * ``REVISION``/``REJECTED`` üçün ``decision_reason`` BOŞ OLA BİLMƏZ;
      * ``APPROVED`` versiyanın ``locked_at``-i mütləq doludur (kilid);
      * insan qərarı ilə təsdiqlənmiş versiyanın ``approved_by``-ı doludur —
        köçürmə mənbəyi (``migration``) isə NULL təsdiqləyənə İCAZƏ verir.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="syllabus_versions"
    )
    syllabus = models.ForeignKey(Syllabus, on_delete=models.CASCADE, related_name="versions")
    major = models.PositiveSmallIntegerField(default=1)
    minor = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=16,
        choices=SyllabusStatus.choices,
        default=SyllabusStatus.DRAFT,
        db_index=True,
    )
    change_kind = models.CharField(max_length=16, choices=ChangeKind.choices, default=ChangeKind.INITIAL)
    applies_to_period = models.ForeignKey(
        "organizations.AcademicPeriod",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="syllabus_versions",
        help_text="Versiyanın tətbiq olunduğu semestr (böyük versiya növbəti semestrə göstərir).",
    )
    source_version = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="derived_versions",
        help_text="Bu versiyanın köçürüldüyü mənbə versiya (diff üçün baza).",
    )
    plan_hours = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tədris planından gələn auditoriya saatı bölgüsü: {'lecture': .., 'seminar': .., 'lab': ..}.",
    )
    completion_percent = models.PositiveSmallIntegerField(
        default=0,
        help_text="Biznes qaydalarına uyğun bölmələrin faizi — servis qatı hesablayır (input sayı DEYİL).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    review_started_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Versiyanı baxışa götürmüş kafedra müdiri.",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(
        blank=True,
        help_text="Düzəliş/rədd səbəbi — bu iki status üçün MƏCBURİDİR (DB check).",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_syllabus_versions",
        help_text="Təsdiqləyən şəxs. Köçürülmüş qeydlərdə NULL — saxta insan təsdiqi yazılmır.",
    )
    approval_source = models.CharField(
        max_length=16,
        choices=ApprovalSource.choices,
        default=ApprovalSource.HUMAN,
        help_text="Təsdiqin mənbəyi: insan qərarı və ya köçürmə damğası.",
    )
    locked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Versiyanın redaktəyə bağlandığı an (təsdiqə göndərmə və ya təsdiq).",
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sillabus versiyası")
        verbose_name_plural = pgettext_lazy(_CTX, "sillabus versiyaları")
        ordering = ["-major", "-minor"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "syllabus", "major", "minor"],
                name="uniq_syllabus_version_number",
            ),
            # Bir dosyedə eyni anda YALNIZ BİR açıq (qərarsız) versiya ola bilər.
            models.UniqueConstraint(
                fields=["syllabus"],
                condition=Q(status__in=sorted(OPEN_STATUSES)),
                name="uniq_syllabus_open_version",
            ),
            # Qüvvədə olan təsdiqlənmiş versiya da YALNIZ BİRDİR (köhnəsi arxivlənir).
            models.UniqueConstraint(
                fields=["syllabus"],
                condition=Q(status=SyllabusStatus.APPROVED),
                name="uniq_syllabus_approved_version",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=sorted(REASON_REQUIRED_STATUSES)) | ~Q(decision_reason=""),
                name="syllabus_version_reason_required",
            ),
            models.CheckConstraint(
                condition=~Q(status=SyllabusStatus.APPROVED) | Q(locked_at__isnull=False),
                name="syllabus_version_approved_is_locked",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status=SyllabusStatus.APPROVED)
                    | ~Q(approval_source=ApprovalSource.HUMAN)
                    | Q(approved_by__isnull=False)
                ),
                name="syllabus_version_human_approval_has_approver",
            ),
            models.CheckConstraint(condition=Q(major__gte=1), name="syllabus_version_major_positive"),
            models.CheckConstraint(
                condition=Q(completion_percent__lte=100),
                name="syllabus_version_completion_percent_range",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["syllabus", "-major", "-minor"]),
            models.Index(fields=["organization", "submitted_at"]),
        ]

    def __str__(self):
        return f"{self.label} · {self.status}"

    @property
    def label(self) -> str:
        """«v2.0» formalı versiya etiketi."""
        return f"v{self.major}.{self.minor}"

    @property
    def is_locked(self) -> bool:
        """Redaktəyə bağlıdırmı (APPROVED daxil bütün qeyri-qaralama statuslar)."""
        from ..constants import EDITABLE_STATUSES

        return self.status not in EDITABLE_STATUSES

    @property
    def is_approved_lock(self) -> bool:
        """Təsdiqlənmiş = əbədi kilid; yalnız yeni versiya yaradıla bilər."""
        return self.status == SyllabusStatus.APPROVED
