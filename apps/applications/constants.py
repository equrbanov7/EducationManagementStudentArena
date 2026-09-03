"""Müraciətlər modulunun sabitləri — statuslar, hadisə növləri, icazə açarları.

DİQQƏT — nə BURADA, nə DB-dədir:

* **Burada** = məhsulun dəyişməz qaydaları: status maşınının açarları, hadisə
  növləri, göndərən ailələri, icazə açarları, nişan palitraları.
* **DB-də** (``ApplicationUnit`` / ``ApplicationKind``) = HƏR TƏŞKİLATIN özünə
  görə qura biləcəyi kataloq: hansı şöbələr var, hansı rol onları idarə edir,
  hansı müraciət növü hara gedir, neçə iş günü müddət. Universitetlərin
  strukturu eyni deyil — mərkəzi şöbələr bu kod bazasında OrgUnit deyil, ROLDUR
  (bax ``SCOUT_APPLICATIONS_INTEGRATION.md`` §6c), ona görə marşrut rol adları
  ilə konfiqurasiya olunur, sərt kodlaşdırılmır.

``DEFAULT_UNIT_SEED`` / ``DEFAULT_KIND_SEED`` yalnız İLK doldurma üçün nümunə
dəstidir (``services.catalog.seed_catalog``); sonra tenant onu redaktə edə bilər.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

from core.constants import OrgUnitType

_CTX = "applications"

# ── İcazə açarları ──────────────────────────────────────────────────────────
PERM_CREATE = "application.create"
PERM_HANDLE = "application.handle"
PERM_MANAGE = "application.manage"


class SenderFamily(models.TextChoices):
    """Göndərənin ailəsi — hansı növləri yarada biləcəyini müəyyən edir."""

    STUDENT = "student", pgettext_lazy(_CTX, "Tələbə")
    TEACHER = "teacher", pgettext_lazy(_CTX, "Müəllim")
    STAFF = "staff", pgettext_lazy(_CTX, "Əməkdaş")


SENDER_FAMILIES = tuple(choice.value for choice in SenderFamily)


class ApplicationStatus(models.TextChoices):
    """Müraciətin vəziyyəti (dizayn §3.3-ün genişləndirilmiş dəsti)."""

    SUBMITTED = "submitted", pgettext_lazy(_CTX, "Yeni")
    IN_REVIEW = "in_review", pgettext_lazy(_CTX, "Baxılır")
    ASSIGNED = "assigned", pgettext_lazy(_CTX, "Təyin edilib")
    FORWARDED = "forwarded", pgettext_lazy(_CTX, "Yönləndirilib")
    WAITING_INFO = "waiting_info", pgettext_lazy(_CTX, "Məlumat gözlənilir")
    RETURNED = "returned", pgettext_lazy(_CTX, "Düzəliş üçün qaytarılıb")
    RESOLVED = "resolved", pgettext_lazy(_CTX, "Həll olunub")
    REJECTED = "rejected", pgettext_lazy(_CTX, "Rədd edilib")
    CLOSED = "closed", pgettext_lazy(_CTX, "Bağlanıb")
    CANCELLED = "cancelled", pgettext_lazy(_CTX, "Ləğv edilib")


#: Bağlı (terminal) statuslar — «açıq» bunların əksidir.
CLOSED_STATUSES = frozenset(
    {
        ApplicationStatus.RESOLVED.value,
        ApplicationStatus.REJECTED.value,
        ApplicationStatus.CLOSED.value,
        ApplicationStatus.CANCELLED.value,
    }
)
OPEN_STATUSES = frozenset(status.value for status in ApplicationStatus) - CLOSED_STATUSES

#: Emalçının qərar verə biləcəyi mənbə statusları (dizayn §3.4).
HANDLER_ACTION_SOURCES = frozenset(
    {
        ApplicationStatus.IN_REVIEW.value,
        ApplicationStatus.ASSIGNED.value,
        ApplicationStatus.FORWARDED.value,
        ApplicationStatus.WAITING_INFO.value,
    }
)


class EventKind(models.TextChoices):
    """Zaman xəttinin bir sətri — append-only."""

    SUBMITTED = "submitted", pgettext_lazy(_CTX, "Göndərildi")
    SEEN = "seen", pgettext_lazy(_CTX, "Baxışa götürüldü")
    COMMENT = "comment", pgettext_lazy(_CTX, "Qeyd")
    ASSIGNED = "assigned", pgettext_lazy(_CTX, "Məsul şəxsə təyin edildi")
    INFO_REQUESTED = "info_requested", pgettext_lazy(_CTX, "Əlavə məlumat istənildi")
    INFO_PROVIDED = "info_provided", pgettext_lazy(_CTX, "Əlavə məlumat verildi")
    FORWARDED = "forwarded", pgettext_lazy(_CTX, "Başqa şöbəyə yönləndirildi")
    RETURNED = "returned", pgettext_lazy(_CTX, "Düzəliş üçün qaytarıldı")
    RESUBMITTED = "resubmitted", pgettext_lazy(_CTX, "Düzəlişdən sonra yenidən göndərildi")
    RESOLVED = "resolved", pgettext_lazy(_CTX, "Həll olundu")
    REJECTED = "rejected", pgettext_lazy(_CTX, "Rədd edildi")
    CLOSED = "closed", pgettext_lazy(_CTX, "Bağlandı")
    CANCELLED = "cancelled", pgettext_lazy(_CTX, "Ləğv edildi")


class ResolveBy(models.TextChoices):
    """Şöbənin AİDİYYƏTİ necə hesablanır (göndərənin hansı əcdadına bağlanır)."""

    ORGANIZATION = "organization", pgettext_lazy(_CTX, "Bütün təşkilat (mərkəzi şöbə)")
    FACULTY = "faculty", pgettext_lazy(_CTX, "Göndərənin fakültəsi")
    CHAIR = "chair", pgettext_lazy(_CTX, "Göndərənin kafedrası")
    SPECIALTY = "specialty", pgettext_lazy(_CTX, "Göndərənin ixtisası")


#: ``ResolveBy`` → ``OrgUnitType`` (əcdad axtarışı üçün).
RESOLVE_BY_UNIT_TYPE = {
    ResolveBy.FACULTY.value: OrgUnitType.FACULTY,
    ResolveBy.CHAIR.value: OrgUnitType.CHAIR,
    ResolveBy.SPECIALTY.value: OrgUnitType.SPECIALTY,
}

#: Kafedra iki tiplə modelləşdirilə bilər (seed-lərdə ``department`` da işlənir).
RESOLVE_BY_FALLBACK_UNIT_TYPES = {
    ResolveBy.CHAIR.value: (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT),
    ResolveBy.FACULTY.value: (OrgUnitType.FACULTY,),
    ResolveBy.SPECIALTY.value: (OrgUnitType.SPECIALTY,),
}

#: Nişan palitraları (dizayn §3.2 «badge bg / fg» sütunu) — UI onları belə oxuyur.
BADGE_PALETTES = {
    "primary": {"bg": "#dbeafe", "fg": "#1e40af"},
    "warning": {"bg": "#fef3c7", "fg": "#92400e"},
    "danger": {"bg": "#fee2e2", "fg": "#b91c1c"},
    "neutral": {"bg": "#f1f5f9", "fg": "#334155"},
    "success": {"bg": "#dcfce7", "fg": "#15803d"},
}

#: Status pilləsinin rəngləri (dizayn §3.3) — UI-ya hazır ötürülür.
STATUS_PALETTE = {
    ApplicationStatus.SUBMITTED.value: "primary",
    ApplicationStatus.IN_REVIEW.value: "warning",
    ApplicationStatus.ASSIGNED.value: "primary",
    ApplicationStatus.FORWARDED.value: "neutral",
    ApplicationStatus.WAITING_INFO.value: "warning",
    ApplicationStatus.RETURNED.value: "warning",
    ApplicationStatus.RESOLVED.value: "success",
    ApplicationStatus.REJECTED.value: "danger",
    ApplicationStatus.CLOSED.value: "neutral",
    ApplicationStatus.CANCELLED.value: "neutral",
}

# ── Yükləmə qaydaları ───────────────────────────────────────────────────────
ALLOWED_ATTACHMENT_EXTENSIONS = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".docx"})
MAX_ATTACHMENT_MB = 10
MAX_ATTACHMENTS_PER_ACTION = 5

# ── Server-side uzunluq qaydaları (dizayn §8.4) ─────────────────────────────
MIN_SUBJECT_LENGTH = 5
MIN_BODY_LENGTH = 20
MIN_NOTE_LENGTH = 10

#: «Həll olundu» statusunda cavabsız qalan müraciət neçə iş günündən sonra
#: avtomatik bağlanır (dizayn §3.4 «tələbə təsdiqləyir və ya avtomatik»).
AUTO_CLOSE_WORKING_DAYS = 5

#: Siyahı səhifələməsi.
PAGE_SIZE = 30

# ── Kataloq seed-i ──────────────────────────────────────────────────────────
#: (code, name, note, handler_role_names, resolve_by, default_sla_days)
#:
#: ⚠️ ``handler_role_names`` KONFİQURASİYADIR: bu kod bazasında «Tələbə
#: Xidmətləri Mərkəzi», «Maliyyə Şöbəsi» və «Kadrlar şöbəsi» üçün ayrıca rol
#: YOXDUR, ona görə default olaraq ``hr`` (kadr/qeydiyyat funksiyası) verilir.
#: Tenant öz rolunu yaradanda kataloqdan dəyişir — miqrasiya təkrar yazmır.
DEFAULT_UNIT_SEED = (
    {
        "code": "telebe",
        "name": "Tələbə Xidmətləri Mərkəzi",
        "note": "sənəd, arayış, transkript, qeydiyyat",
        # 2026-09 (handoff Mərhələ 3): şöbənin ÖZ rolu yarandı —
        # `student_services` (bax `organizations/default_roles_student_services.py`).
        # `hr` FALLBACK kimi SAXLANILIR: mövcud tenantlarda əməkdaşlar hələ
        # kadr rolu ilə işləyir, siyahıdan çıxarılsa növbə birdən sahibsiz qalardı.
        "handler_role_names": ["student_services", "hr"],
        "resolve_by": ResolveBy.ORGANIZATION.value,
        "default_sla_days": 3,
    },
    {
        "code": "tedris",
        "name": "Tədris Şöbəsi",
        "note": "plan, cədvəl, fənn, semestr açılışı",
        "handler_role_names": ["vice_rector"],
        "resolve_by": ResolveBy.ORGANIZATION.value,
        "default_sla_days": 5,
    },
    {
        "code": "dekan",
        "name": "Dekanlıq",
        "note": "tələbə hərəkəti, akademik məsələlər",
        "handler_role_names": ["dean"],
        "resolve_by": ResolveBy.FACULTY.value,
        "default_sla_days": 5,
    },
    {
        "code": "kafedra",
        "name": "Kafedra müdirliyi",
        "note": "müəllim, fənn tədrisi, sillabus",
        "handler_role_names": ["chair_head"],
        "resolve_by": ResolveBy.CHAIR.value,
        "default_sla_days": 5,
    },
    {
        "code": "koordinator",
        "name": "Proqram koordinatoru",
        "note": "ixtisas, qrup, fərdi tədris planı",
        "handler_role_names": ["program_coordinator"],
        "resolve_by": ResolveBy.SPECIALTY.value,
        "default_sla_days": 3,
    },
    {
        "code": "maliyye",
        "name": "Maliyyə Şöbəsi",
        "note": "təhsil haqqı, ödəniş, güzəşt",
        "handler_role_names": ["hr"],
        "resolve_by": ResolveBy.ORGANIZATION.value,
        "default_sla_days": 5,
    },
    {
        "code": "kadrlar",
        "name": "Kadrlar şöbəsi",
        "note": "əmək müqaviləsi, məzuniyyət, kadr sənədi",
        "handler_role_names": ["hr"],
        "resolve_by": ResolveBy.ORGANIZATION.value,
        "default_sla_days": 5,
    },
    {
        "code": "rim",
        "name": "RİM (Rəqəmsal İnkişaf Mərkəzi)",
        "note": "sistem girişi, texniki nasazlıq",
        "handler_role_names": ["ikt_rehber"],
        "resolve_by": ResolveBy.ORGANIZATION.value,
        "default_sla_days": 2,
    },
    {
        "code": "imtahan",
        "name": "İmtahan Mərkəzi",
        "note": "imtahan təşkili, PIN, nəticə",
        "handler_role_names": ["exam_center", "exam_center_head"],
        "resolve_by": ResolveBy.ORGANIZATION.value,
        "default_sla_days": 3,
    },
)

#: Rəsmi apellyasiya AYRI moduldadır (``apps.appeals``) — «Qiymətə etiraz»
#: müraciəti onu ƏVƏZ ETMİR, yalnız dekanlığa sual/izah kanalıdır.
GRADE_APPEAL_KIND_CODE = "qiymet"
GRADE_APPEAL_HINT = (
    "Rəsmi apellyasiya «Apellyasiyalarım» bölməsindən verilir — bu müraciət " "yalnız dekanlığa izah/sual kanalıdır."
)

#: (code, label, note, allowed_sender_families, unit_code, sla_days, palette, route_overrides)
DEFAULT_KIND_SEED = (
    {
        "code": "transkript",
        "label": "Transkript sorğusu",
        "note": "Rəsmi transkriptin verilməsi",
        "allowed_sender_families": ["student"],
        "unit_code": "telebe",
        "sla_days": 3,
        "badge_palette": "primary",
    },
    {
        "code": "arayis",
        "label": "Arayış sorğusu",
        "note": "Təhsil, hərbi və ya bank arayışı",
        "allowed_sender_families": ["student"],
        "unit_code": "telebe",
        "sla_days": 2,
        "badge_palette": "primary",
    },
    {
        "code": GRADE_APPEAL_KIND_CODE,
        "label": "Qiymətə etiraz",
        "note": f"İmtahan nəticəsinə apellyasiya. {GRADE_APPEAL_HINT}",
        "allowed_sender_families": ["student"],
        "unit_code": "dekan",
        "sla_days": 5,
        "badge_palette": "warning",
    },
    {
        "code": "sikayet",
        "label": "Şikayət",
        "note": "Tədris prosesi ilə bağlı şikayət",
        "allowed_sender_families": ["student", "teacher"],
        "unit_code": "dekan",
        "sla_days": 10,
        "badge_palette": "danger",
    },
    {
        "code": "hereket",
        "label": "Tələbə hərəkəti",
        "note": "Köçürmə, akademik məzuniyyət, bərpa",
        "allowed_sender_families": ["student"],
        "unit_code": "dekan",
        "sla_days": 7,
        "badge_palette": "neutral",
    },
    {
        "code": "odenis",
        "label": "Təhsil haqqı",
        "note": "Güzəşt, hissə-hissə ödəniş, qaytarma",
        "allowed_sender_families": ["student"],
        "unit_code": "maliyye",
        "sla_days": 5,
        "badge_palette": "neutral",
    },
    {
        "code": "teqdimat",
        "label": "Təqdimat",
        "note": "Kafedraya rəsmi təklif və ya təqdimat",
        "allowed_sender_families": ["teacher"],
        "unit_code": "kafedra",
        "sla_days": 10,
        "badge_palette": "primary",
    },
    {
        "code": "texniki",
        "label": "Texniki problem",
        "note": "Sistemə giriş, jurnal, e-poçt",
        "allowed_sender_families": ["student", "teacher", "staff"],
        "unit_code": "rim",
        "sla_days": 2,
        "badge_palette": "neutral",
    },
    {
        "code": "cedvel",
        "label": "Dərs cədvəli",
        "note": "Cədvəl toqquşması, auditoriya və ya saat dəyişikliyi",
        "allowed_sender_families": ["student", "teacher"],
        "unit_code": "koordinator",
        "sla_days": 3,
        "badge_palette": "neutral",
    },
    {
        "code": "davamiyyet",
        "label": "Davamiyyət düzəlişi",
        "note": "Səhv qeyd olunmuş qayıb və ya üzrlü sənəd",
        "allowed_sender_families": ["student"],
        "unit_code": "dekan",
        "sla_days": 5,
        "badge_palette": "warning",
    },
    {
        "code": "melumat",
        "label": "Tələbə məlumatının düzəlişi",
        "note": "Ad, soyad, əlaqə və ya şəxsiyyət sənədi məlumatı",
        "allowed_sender_families": ["student"],
        "unit_code": "telebe",
        "sla_days": 3,
        "badge_palette": "primary",
    },
    {
        "code": "senedler",
        "label": "Sənəd sorğusu",
        "note": "Diplom, diploma əlavə və digər rəsmi sənəd",
        "allowed_sender_families": ["student"],
        "unit_code": "telebe",
        "sla_days": 3,
        "badge_palette": "primary",
    },
    {
        "code": "hr",
        "label": "Kadr məsələsi",
        "note": "Əmək müqaviləsi, məzuniyyət, kadr sənədi",
        "allowed_sender_families": ["teacher", "staff"],
        "unit_code": "kadrlar",
        "sla_days": 5,
        "badge_palette": "neutral",
    },
    {
        "code": "imtahan",
        "label": "İmtahan məsələsi",
        "note": "İmtahan təşkili, PIN, nəticə",
        "allowed_sender_families": ["student", "teacher"],
        "unit_code": "imtahan",
        "sla_days": 3,
        "badge_palette": "warning",
    },
    {
        # «Digər» hər ailə üçün AYRI ünvana gedir — ona görə route_overrides.
        "code": "diger",
        "label": "Digər",
        "note": "Yuxarıdakı bölmələrə uyğun gəlməyən müraciət",
        "allowed_sender_families": ["student", "teacher", "staff"],
        "unit_code": "rim",
        "sla_days": 5,
        "badge_palette": "neutral",
        "route_overrides": {"student": "koordinator", "teacher": "kafedra", "staff": "rim"},
    },
)


__all__ = [
    "ALLOWED_ATTACHMENT_EXTENSIONS",
    "AUTO_CLOSE_WORKING_DAYS",
    "BADGE_PALETTES",
    "CLOSED_STATUSES",
    "DEFAULT_KIND_SEED",
    "DEFAULT_UNIT_SEED",
    "EventKind",
    "GRADE_APPEAL_HINT",
    "GRADE_APPEAL_KIND_CODE",
    "HANDLER_ACTION_SOURCES",
    "MAX_ATTACHMENTS_PER_ACTION",
    "MAX_ATTACHMENT_MB",
    "MIN_BODY_LENGTH",
    "MIN_NOTE_LENGTH",
    "MIN_SUBJECT_LENGTH",
    "OPEN_STATUSES",
    "PAGE_SIZE",
    "PERM_CREATE",
    "PERM_HANDLE",
    "PERM_MANAGE",
    "RESOLVE_BY_FALLBACK_UNIT_TYPES",
    "RESOLVE_BY_UNIT_TYPE",
    "ResolveBy",
    "STATUS_PALETTE",
    "SENDER_FAMILIES",
    "SenderFamily",
    "ApplicationStatus",
]
