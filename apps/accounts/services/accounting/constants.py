"""«Mühasibatlıq» bölməsinin sabitləri (sahib 2026-10-18).

Etiketlər ``pgettext_lazy`` ilə — modul import vaxtında dil seçilməyib.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

CTX = "accounts.accounting"
#: İcazə açarı — kataloqdakı tərif: ``apps/organizations/permissions_accounting.py`` (eyni literal).
PERM_ACCOUNTING_VIEW = "accounting.view"
SECTION = "accounting"
PARAM_PREFIX = "ac_"
PAGE_SIZE = 25
LESSON_PAGE_SIZE = 50
#: İxracda dərs siyahısının tavanı (yalnız bir müəllimin dərsləri çıxır — semestr ~200 sətirdir).
EXPORT_LESSON_LIMIT = 5000

#: Auditoriya fəaliyyətləri — jurnalın ``LessonKind`` dəyərləri ilə dərs yükünün ``Activity`` dəyərləri
#: EYNİ sətirlərdir («lecture» / «seminar» / «lab»), ona görə plan və fakt birbaşa tutuşdurulur.
KIND_LECTURE = "lecture"
KIND_SEMINAR = "seminar"
KIND_LAB = "lab"
KINDS = (
    (KIND_LECTURE, pgettext_lazy(CTX, "Mühazirə")),
    (KIND_SEMINAR, pgettext_lazy(CTX, "Seminar")),
    (KIND_LAB, pgettext_lazy(CTX, "Laboratoriya")),
)
KIND_KEYS = tuple(key for key, _label in KINDS)
#: ``dataset.planned_matrix`` sətrində saathesabı (``is_hourly_paid``) plan saatlarının açarı — növlərlə toqquşmur.
HOURLY_KEY = "_hourly"

#: Dərs yükünün sayılan tapşırıq statusları — «Dərs yüküm» / kafedra profili ilə EYNİ
#: (``workload.services.queries.teacher_workload_summaries``): bölgüsü bitmiş və ya düzəliş edilmiş.
PLANNED_TASK_STATUSES = ("distributed", "amended")

#: Fəsillər (``workload.constants.Season`` dəyərləri ilə eyni sətirlər).
SEASON_FALL = "fall"
SEASON_SPRING = "spring"
SEASON_SUMMER = "summer"
SEASON_LABELS = {
    SEASON_FALL: pgettext_lazy(CTX, "Payız semestri"),
    SEASON_SPRING: pgettext_lazy(CTX, "Yaz semestri"),
    SEASON_SUMMER: pgettext_lazy(CTX, "Yay semestri"),
}

#: Planın aylara bölgüsündə sayılan həftə günləri (0 = bazar ertəsi … 4 = cümə). Bax ``calendar.py``.
TEACHING_WEEKDAYS = (0, 1, 2, 3, 4)

#: Kənarlaşma bandı: keçirilmiş saat planın ±10%-i daxilindədirsə «plana uyğun».
#: 2026-10-19 (sahib): band «Sistem tənzimləmələri» → ``accounting.deviation_percent`` (defolt 10) ilə idarə olunur;
#: bu sabit yalnız tənzimləmə oxuna bilməyəndə ehtiyat dəyərdir. Oxu nöqtəsi: :func:`deviation_tolerance`.
DEVIATION_TOLERANCE = 0.10


def deviation_percent() -> int:
    """Cari band (tam faiz, məs. 10) — «Sistem tənzimləmələri»ndən; oxunmasa sabitə düşür."""
    try:
        from core import runtime_settings

        return int(runtime_settings.get_int("accounting.deviation_percent"))
    except Exception:  # noqa: BLE001 — tənzimləmə xətası hesabatı sındırmır
        return int(round(DEVIATION_TOLERANCE * 100))


def deviation_tolerance() -> float:
    """Cari band payı (məs. 0.10)."""
    return deviation_percent() / 100


#: Status ailəsi (``core/ui/status_catalog.py`` → ``accounting_plan``).
STATUS_FAMILY = "accounting_plan"
STATUS_ON_PLAN = "on_plan"
STATUS_UNDER = "under"
STATUS_OVER = "over"
STATUS_NO_PLAN = "no_plan"
STATUS_IDLE = "idle"
DEVIATION_STATUSES = (STATUS_UNDER, STATUS_OVER, STATUS_NO_PLAN)

MONTH_NAMES = {
    1: pgettext_lazy(CTX, "Yanvar"),
    2: pgettext_lazy(CTX, "Fevral"),
    3: pgettext_lazy(CTX, "Mart"),
    4: pgettext_lazy(CTX, "Aprel"),
    5: pgettext_lazy(CTX, "May"),
    6: pgettext_lazy(CTX, "İyun"),
    7: pgettext_lazy(CTX, "İyul"),
    8: pgettext_lazy(CTX, "Avqust"),
    9: pgettext_lazy(CTX, "Sentyabr"),
    10: pgettext_lazy(CTX, "Oktyabr"),
    11: pgettext_lazy(CTX, "Noyabr"),
    12: pgettext_lazy(CTX, "Dekabr"),
}

SORT_KEYS = ("name", "planned", "held", "diff", "pct")
SORT_DEFAULT = "name"
