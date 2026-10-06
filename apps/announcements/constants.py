"""«Elanlar» (2026-10-06) — sabitlər, seçimlər və limitlər.

Modulun ümumi müqaviləsi ``public.py``-dadır; burada yalnız DATA saxlanılır.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

_CTX = "announcements.model"

#: İdarə açarı (icazə redaktorunda «Elanlar» kateqoriyası). Rektor / RİM rəhbəri ``*`` ilə əhatəlidir.
PERM_MANAGE = "announcement.manage"

#: Kabinet bölməsinin açarı (``?section=announcements``).
PROFILE_SECTION = "announcements"

#: ``Organization.settings`` açarı — aktiv elanların sıfır-sorğulu xülasəsi (bax ``services/snapshot``).
SNAPSHOT_KEY = "announcements_snapshot"
#: Xülasədə saxlanılan maksimum elan sayı (xülasə hər sorğuda yüklənən təşkilat sətrinin içindədir).
SNAPSHOT_LIMIT = 200

#: Sessiya açarı — «bu xülasə versiyası üçün gözləyən popup yoxdur» işarəsi (sıfır sorğu).
POPUP_SESSION_KEY = "ann_popup_clear"
#: Bir modalda göstərilən maksimum elan sayı (stepper).
POPUP_MAX_ITEMS = 5

#: Popup heç vaxt göstərilməyən yollar: imtahan axını, canlı imtahan, sorğu formu, giriş/çıxış,
#: elanların öz səhifələri və JSON uçları. Kabinetdə imtahan bölmələri də istisnadır.
POPUP_EXEMPT_PREFIXES = (
    "/exams/",
    "/exmas/",
    "/live/",
    "/sorgu/",
    "/elanlar/",
    "/api/",
    "/accounts/login",
    "/accounts/logout",
    "/accounts/profile/api/",
)
POPUP_EXEMPT_SECTIONS = frozenset({"assigned-exams", "my-exams", "exam-center-pins", "exam-center-stats"})

TITLE_MAX = 200
SUMMARY_MAX = 300
BODY_MAX = 20000
APPLY_NOTE_MAX = 2000
APPLY_LABEL_MAX = 60
URL_MAX = 500

ATTACHMENT_EXTENSIONS = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".webp", ".docx", ".xlsx", ".pptx"})
ATTACHMENT_MAX_MB = 10
ATTACHMENTS_PER_ANNOUNCEMENT = 5
ATTACHMENT_ACCEPT = ",".join(sorted(ATTACHMENT_EXTENSIONS))

PAGE_SIZE = 10
MANAGE_PAGE_SIZE = 20
#: «Yeni» nişanı yalnız son N gündə dərc olunmuş oxunmamış elanlara (köhnə arxiv «yeni» deyil).
UNREAD_WINDOW_DAYS = 60
#: Unit seçimi: maksimum hədəf bölmə sayı.
MAX_TARGET_UNITS = 50


class Category(models.TextChoices):
    GENERAL = "general", pgettext_lazy(_CTX, "Ümumi")
    ACADEMIC = "academic", pgettext_lazy(_CTX, "Tədris")
    EXAM = "exam", pgettext_lazy(_CTX, "İmtahan")
    EVENT = "event", pgettext_lazy(_CTX, "Tədbir")
    URGENT = "urgent", pgettext_lazy(_CTX, "Təcili")


class Priority(models.IntegerChoices):
    NORMAL = 0, pgettext_lazy(_CTX, "Adi")
    HIGH = 1, pgettext_lazy(_CTX, "Yüksək")
    CRITICAL = 2, pgettext_lazy(_CTX, "Kritik")


class Status(models.TextChoices):
    DRAFT = "draft", pgettext_lazy(_CTX, "Qaralama")
    PUBLISHED = "published", pgettext_lazy(_CTX, "Dərc olunub")
    ARCHIVED = "archived", pgettext_lazy(_CTX, "Arxiv")


class Audience(models.TextChoices):
    """Rol ailələri (``services/audience.family_of``)."""

    STUDENTS = "students", pgettext_lazy(_CTX, "Tələbələr")
    TEACHERS = "teachers", pgettext_lazy(_CTX, "Müəllimlər")
    STAFF = "staff", pgettext_lazy(_CTX, "Əməkdaşlar")


ALL_FAMILIES = frozenset(choice.value for choice in Audience)


class ApplyMode(models.TextChoices):
    NONE = "none", pgettext_lazy(_CTX, "Müraciət yoxdur")
    INTERNAL = "internal", pgettext_lazy(_CTX, "Daxili müraciət (Müraciətlər modulu)")
    URL = "url", pgettext_lazy(_CTX, "Keçid (link)")


#: Elan ailəsi → ``applications.SenderFamily`` dəyəri (növün ailəyə açıq olması yoxlaması).
FAMILY_TO_SENDER = {"students": "student", "teachers": "teacher", "staff": "staff"}

#: Effektiv vəziyyətlər (tarixdən asılı; DB sütunu deyil).
STATE_SCHEDULED = "scheduled"
STATE_ACTIVE = "active"
STATE_EXPIRED = "expired"

#: Kabinet siyahısının filtr/sıralama dəyərləri (klientdən gələn hər şey bu dəstlərlə süzülür).
USER_STATES = ("active", "expired", "all")
SORTS = ("new", "deadline", "priority")
MANAGE_STATES = ("all", "draft", "scheduled", "active", "expired", "archived")
