"""Dərs yükü modulunun sabitləri — status, fəaliyyət, forma və icazə açarları.

Bu modul HEÇ NƏ import etmir (django.db xaric) — modellər, servislər, view-lar
və testlər eyni kataloqu buradan alır. Spesifikasiya: ``docs/workload/DERS_YUKU_SPEC.md``.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

_CTX = "workload"

# ── İcazə açarları (kataloq: apps/organizations/permissions.py) ──────────────
PERM_VIEW = "workload.view"
PERM_MANAGE = "workload.manage"
PERM_SUBMIT = "workload.submit"
PERM_REVIEW = "workload.review"
PERM_APPROVE = "workload.approve"
PERM_DISTRIBUTE = "workload.distribute"
PERM_REPORT = "workload.report"
PERM_OBJECT = "workload.object"


class TaskStatus(models.TextChoices):
    """Tapşırıq sənədinin statusu (spec §4.1).

    ⚠️ SİYAHI TAM SAXLANILIR: F1 (tədris şöbəsi) və F2 (dekanlıq) statusları
    (``submitted``/``returned``/``pending_final_approval``/``approved``) bu
    fazada İSTİFADƏ OLUNMUR, amma kataloqda var ki, sonrakı fazalar sahə
    miqrasiyası tələb etməsin.
    """

    DRAFT = "draft", pgettext_lazy(_CTX, "Qaralama")
    SUBMITTED = "submitted", pgettext_lazy(_CTX, "Dekanlığa göndərilib")
    RETURNED = "returned", pgettext_lazy(_CTX, "Qaytarılıb")
    PENDING_FINAL_APPROVAL = "pending_final_approval", pgettext_lazy(_CTX, "Yekun təsdiq gözləyir")
    APPROVED = "approved", pgettext_lazy(_CTX, "Təsdiqlənib")
    DISTRIBUTING = "distributing", pgettext_lazy(_CTX, "Bölüşdürülür")
    DISTRIBUTED = "distributed", pgettext_lazy(_CTX, "Bölüşdürülüb")
    AMENDED = "amended", pgettext_lazy(_CTX, "Düzəliş edilib")
    CANCELLED = "cancelled", pgettext_lazy(_CTX, "Ləğv edilib")


#: Sətirlərin redaktə oluna bildiyi statuslar.
#: ``returned`` F1-də əlavə olundu: dekan qaytaranda tədris şöbəsi məhz həmin
#: sətirləri düzəldib yenidən göndərir (spec §4.1).
#: ``amended`` QA 2026-09-05 (P3-22) əlavə olundu: `services.amendments.open_amendment`
#: sətir hədəfi üçün tapşırığı `amended`-ə keçirir və mesajı "düzəliş axını
#: istifadə edilməlidir" deyir — amma bu status əvvəllər EDITABLE deyildi, ona
#: görə amendment açandan sonra sətri REDAKTƏ ETMƏK MÜMKÜN DEYİLDİ (`amendment.
#: new_values` sənədləşdirilir, TƏTBİQ olunmurdu). `confirm_distribution` artıq
#: `amended`-i qəbul edir (yenidən `distributed`-ə bağlamaq üçün) — simmetriya
#: bura ilə tamamlanır.
EDITABLE_STATUSES = frozenset({TaskStatus.DRAFT, TaskStatus.RETURNED, TaskStatus.DISTRIBUTING, TaskStatus.AMENDED})
#: Bölgü (təyinat) əməliyyatlarına açıq statuslar.
#: ``approved`` F2 zəncirinin çıxışıdır — dekanlıq təsdiqindən sonra kafedra
#: müdiri bölgüyə başlayır; ``draft`` yalnız HEÇ VAXT göndərilməmiş sənəd üçün
#: keçərlidir (``services.workflow.ensure_distribution_stage`` yoxlayır).
ASSIGNABLE_STATUSES = frozenset({TaskStatus.DRAFT, TaskStatus.APPROVED, TaskStatus.DISTRIBUTING, TaskStatus.AMENDED})
#: Təsdiqdən sonrakı statuslar — dəyişiklik yalnız amendment axını ilə.
LOCKED_STATUSES = frozenset({TaskStatus.DISTRIBUTED, TaskStatus.CANCELLED})


class Season(models.TextChoices):
    FALL = "fall", pgettext_lazy(_CTX, "Payız")
    SPRING = "spring", pgettext_lazy(_CTX, "Yaz")
    SUMMER = "summer", pgettext_lazy(_CTX, "Yay")


class RowKind(models.TextChoices):
    TEACHING = "teaching", pgettext_lazy(_CTX, "Dərs")
    PRACTICE = "practice", pgettext_lazy(_CTX, "Təcrübə")
    THESIS = "thesis", pgettext_lazy(_CTX, "Buraxılış/dissertasiya işi")
    POSTGRAD = "postgrad", pgettext_lazy(_CTX, "Dissertant/doktorant")
    OTHER = "other", pgettext_lazy(_CTX, "Digər")


class EducationForm(models.TextChoices):
    """Təhsil forması — sistemdə ilk dəfə burada modellənir (spec §9.1)."""

    EYANI = "eyani", pgettext_lazy(_CTX, "Əyani")
    QIYABI = "qiyabi", pgettext_lazy(_CTX, "Qiyabi")
    INTENSIV = "intensiv", pgettext_lazy(_CTX, "İntensiv")
    DISTANT = "distant", pgettext_lazy(_CTX, "Distant")


class DegreeLevel(models.TextChoices):
    """``registrar.DegreeLevel`` dəyərlərinin GÜZGÜSÜ (modul sərhədi: import yox)."""

    BACHELOR = "bachelor", pgettext_lazy(_CTX, "Bakalavr")
    MASTER = "master", pgettext_lazy(_CTX, "Magistr")
    PHD = "phd", pgettext_lazy(_CTX, "Doktorantura")


class Activity(models.TextChoices):
    """Bölgü fəaliyyət növü (spec §5.5)."""

    LECTURE = "lecture", pgettext_lazy(_CTX, "Mühazirə")
    SEMINAR = "seminar", pgettext_lazy(_CTX, "Seminar/təcrübi")
    LAB = "lab", pgettext_lazy(_CTX, "Laboratoriya")
    CONSULT = "consult", pgettext_lazy(_CTX, "Məsləhət")
    EXAM = "exam", pgettext_lazy(_CTX, "İmtahan")
    THESIS = "thesis", pgettext_lazy(_CTX, "Buraxılış işinə rəhbərlik")
    POSTGRAD = "postgrad", pgettext_lazy(_CTX, "Dissertant rəhbərliyi")
    PRACTICE_RESEARCH = "practice_research", pgettext_lazy(_CTX, "Elmi-tədqiqat təcrübəsi")
    PRACTICE_PRODUCTION = "practice_production", pgettext_lazy(_CTX, "İstehsalat təcrübəsi")


#: Fəaliyyət → sətirdəki SAAT TAVANI sahəsi. Balans yoxlaması (servis + DB
#: trigger) bu xəritə ilə işləyir; yeni fəaliyyət əlavə edəndə hər iki yer
#: (bura + ``0002_rls_workload`` trigger-i) yenilənməlidir.
ACTIVITY_TOTAL_FIELD: dict[str, str] = {
    Activity.LECTURE: "lecture_total",
    Activity.SEMINAR: "seminar_total",
    Activity.LAB: "lab_total",
    Activity.CONSULT: "consult_hours",
    Activity.EXAM: "exam_hours",
    Activity.THESIS: "thesis_hours",
    Activity.POSTGRAD: "postgrad_hours",
    Activity.PRACTICE_RESEARCH: "practice_research_hours",
    Activity.PRACTICE_PRODUCTION: "practice_production_hours",
}

#: Auditoriya (kontakt) fəaliyyətləri — bölgünün 100% tamamlanması bunlarla ölçülür.
TEACHING_ACTIVITIES = (Activity.LECTURE, Activity.SEMINAR, Activity.LAB)

#: ``CourseOffering.lesson_hours`` üçün kontakt saatı sahələri (spec §7.1).
CONTACT_TOTAL_FIELDS = ("lecture_total", "seminar_total", "lab_total")

#: Sətrin CƏMİ saatını təşkil edən bütün sahələr (``total_hours`` yoxlaması).
TOTAL_HOUR_FIELDS = (
    "lecture_total",
    "seminar_total",
    "lab_total",
    "consult_hours",
    "exam_hours",
    "thesis_hours",
    "postgrad_hours",
    "practice_research_hours",
    "practice_production_hours",
)


class RowReviewStatus(models.TextChoices):
    PENDING = "pending", pgettext_lazy(_CTX, "Gözləyir")
    REVIEWED = "reviewed", pgettext_lazy(_CTX, "Baxılıb")
    FLAGGED = "flagged", pgettext_lazy(_CTX, "İradlı")
    RETURNED = "returned", pgettext_lazy(_CTX, "Qaytarılıb")


class SliceStatus(models.TextChoices):
    """Fakültə təsdiq diliminin vəziyyəti (spec §5.3, ekran 15)."""

    PENDING = "pending", pgettext_lazy(_CTX, "Göndərilib")
    APPROVED = "approved", pgettext_lazy(_CTX, "Təsdiqlənib")
    RETURNED = "returned", pgettext_lazy(_CTX, "Qaytarılıb")


class ObjectionReason(models.TextChoices):
    """Müəllim etirazının 4 səbəbi — dizayn ekran 16 (`REASONS`, hərfi copy)."""

    HOURS = "hours", pgettext_lazy(_CTX, "Saat sayı düz deyil")
    STUDENTS = "students", pgettext_lazy(_CTX, "Qrup/tələbə sayı səhvdir")
    SUBJECT = "subject", pgettext_lazy(_CTX, "Fənn ixtisasım deyil")
    NORM = "norm", pgettext_lazy(_CTX, "Norma həddindən artıqdır")


class ObjectionStatus(models.TextChoices):
    OPEN = "open", pgettext_lazy(_CTX, "Baxılır")
    ACCEPTED = "accepted", pgettext_lazy(_CTX, "Qəbul edildi")
    REJECTED = "rejected", pgettext_lazy(_CTX, "Rədd edildi")


#: Səbəb tələb edən əməllərin minimum uzunluğu (handoff §8 qayda 6).
REASON_MIN_LENGTH = 20

#: Dekanın ikinci təsdiqi — dərs yükü üçün AÇIQDIR (plan §2/15, açıq qərar §10.2).
#: Sillabusda isə söndürülüdür; ona görə bayraq ailə-ailə saxlanılır.
DEAN_SECOND_APPROVAL_ENABLED = True


class TeacherPosition(models.TextChoices):
    PROFESSOR = "professor", pgettext_lazy(_CTX, "Professor")
    DOSENT = "dosent", pgettext_lazy(_CTX, "Dosent")
    BAS_MUELLIM = "bas_muellim", pgettext_lazy(_CTX, "Baş müəllim")
    MUELLIM = "muellim", pgettext_lazy(_CTX, "Müəllim")
    ASSISTENT = "assistent", pgettext_lazy(_CTX, "Assistent")


class AmendmentTarget(models.TextChoices):
    ROW = "row", pgettext_lazy(_CTX, "Tapşırıq sətri")
    ASSIGNMENT = "assignment", pgettext_lazy(_CTX, "Bölgü sətri")


class AmendmentReason(models.TextChoices):
    CORRECTION = "correction", pgettext_lazy(_CTX, "Texniki səhvin düzəlişi")
    STAFF_CHANGE = "staff_change", pgettext_lazy(_CTX, "Kadr dəyişikliyi")
    STUDENT_COUNT = "student_count", pgettext_lazy(_CTX, "Tələbə sayının dəyişməsi")
    OFFICIAL = "official", pgettext_lazy(_CTX, "Rəsmi sərəncam/əmr")
    OTHER = "other", pgettext_lazy(_CTX, "Digər")


#: Müəllim rolları — kafedra bölgüsündə namizəd hovuzu (spec §5.5).
TEACHER_ROLE_NAMES = ("teacher", "assistant", "lab_assistant")

#: NK №215: bir ştat üzrə illik norma (org-konfiqurasiyalı default).
DEFAULT_ANNUAL_NORM_HOURS = 500
#: KQ-12/2024: könüllü saathesabı tavanı.
DEFAULT_HOURLY_PAID_CAP = 250
#: NK №348 / spec §7: 1 kredit = 30 saat ümumi tədris yükü.
HOURS_PER_CREDIT = 30

#: Fəsil ↔ semestr nömrəsinin paritetı (tədris planından idxal üçün).
SEASON_BY_SEMESTER_PARITY = {1: Season.FALL, 0: Season.SPRING}

__all__ = [
    "ACTIVITY_TOTAL_FIELD",
    "ASSIGNABLE_STATUSES",
    "CONTACT_TOTAL_FIELDS",
    "DEAN_SECOND_APPROVAL_ENABLED",
    "DEFAULT_ANNUAL_NORM_HOURS",
    "DEFAULT_HOURLY_PAID_CAP",
    "EDITABLE_STATUSES",
    "HOURS_PER_CREDIT",
    "LOCKED_STATUSES",
    "PERM_APPROVE",
    "PERM_DISTRIBUTE",
    "PERM_MANAGE",
    "PERM_OBJECT",
    "PERM_REPORT",
    "PERM_REVIEW",
    "PERM_SUBMIT",
    "PERM_VIEW",
    "REASON_MIN_LENGTH",
    "SEASON_BY_SEMESTER_PARITY",
    "TEACHER_ROLE_NAMES",
    "TEACHING_ACTIVITIES",
    "TOTAL_HOUR_FIELDS",
    "Activity",
    "AmendmentReason",
    "AmendmentTarget",
    "DegreeLevel",
    "EducationForm",
    "ObjectionReason",
    "ObjectionStatus",
    "RowKind",
    "RowReviewStatus",
    "Season",
    "SliceStatus",
    "TaskStatus",
    "TeacherPosition",
]
