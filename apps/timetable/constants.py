"""Avtomatik cədvəl modulunun sabitləri — statuslar, növbələr, səviyyələr, defoltlar."""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

_CTX = "timetable.model"

#: Kanonik icazə — registrar-ın cədvəl idarəetməsi ilə EYNİ açar (yeni açar yoxdur).
PERMISSION = "schedule.manage"


class Level(models.TextChoices):
    """Müəllimin həftəlik şəbəkəsində bir xananın səviyyəsi (UniTime pilləsinin sadə forması)."""

    NEUTRAL = "n", pgettext_lazy(_CTX, "Neytral")
    PREFERRED = "p", pgettext_lazy(_CTX, "Üstünlük verilir")
    DISCOURAGED = "d", pgettext_lazy(_CTX, "Dəyişdirilə bilən saat")
    UNAVAILABLE = "u", pgettext_lazy(_CTX, "Gələ bilmir")


LEVEL_CODES = tuple(value for value, _label in Level.choices)


class Band(models.TextChoices):
    """Gün növbəsi (``registrar.schedule_grid.shift_of`` ilə eyni sərhədlər)."""

    MORNING = "morning", pgettext_lazy(_CTX, "Səhər")
    AFTERNOON = "afternoon", pgettext_lazy(_CTX, "Günorta")
    EVENING = "evening", pgettext_lazy(_CTX, "Axşam")


BAND_CODES = tuple(value for value, _label in Band.choices)


class PolicyLevel(models.TextChoices):
    """Susmaya görə növbə siyasətinin açarı (qrup üçün ayrıca sətir yoxdursa)."""

    BACHELOR = "bachelor", pgettext_lazy(_CTX, "Bakalavr")
    MASTER = "master", pgettext_lazy(_CTX, "Magistr")
    PHD = "phd", pgettext_lazy(_CTX, "Doktorantura")
    PART_TIME = "part_time", pgettext_lazy(_CTX, "Qiyabi (bütün pillələr)")


#: Daxili defoltlar — sahibin qaydası: magistr dərsi SƏHƏR qoyulmur (yalnız axşam);
#: qiyabi qruplar həftəlik cədvələ susmaya görə DAXİL EDİLMİR (sessiya ilə oxuyurlar).
BUILTIN_POLICY = {
    PolicyLevel.BACHELOR: {"bands": [Band.MORNING, Band.AFTERNOON], "max_pairs_per_day": 4, "is_excluded": False},
    PolicyLevel.MASTER: {"bands": [Band.EVENING], "max_pairs_per_day": 2, "is_excluded": False},
    PolicyLevel.PHD: {"bands": [Band.EVENING], "max_pairs_per_day": 2, "is_excluded": False},
    PolicyLevel.PART_TIME: {"bands": [Band.EVENING], "max_pairs_per_day": 3, "is_excluded": True},
}


class RunStatus(models.TextChoices):
    DRAFT = "draft", pgettext_lazy(_CTX, "Qaralama")
    QUEUED = "queued", pgettext_lazy(_CTX, "Növbədə")
    RUNNING = "running", pgettext_lazy(_CTX, "İşləyir")
    DONE = "done", pgettext_lazy(_CTX, "Hazırdır")
    FAILED = "failed", pgettext_lazy(_CTX, "Uğursuz")
    PUBLISHED = "published", pgettext_lazy(_CTX, "Dərc edilib")
    DISCARDED = "discarded", pgettext_lazy(_CTX, "Ləğv edilib")


ACTIVE_STATUSES = (RunStatus.QUEUED, RunStatus.RUNNING)
REVIEWABLE_STATUSES = (RunStatus.DONE, RunStatus.PUBLISHED)


class ScopeKind(models.TextChoices):
    FACULTY = "faculty", pgettext_lazy(_CTX, "Fakültə")
    PROGRAM = "program", pgettext_lazy(_CTX, "İxtisas")
    GROUPS = "groups", pgettext_lazy(_CTX, "Seçilmiş qruplar")


class StreamPolicy(models.TextChoices):
    """Mühazirə axınlarının (potok) mənbəyi."""

    TASK_ROWS = "task_rows", pgettext_lazy(_CTX, "Tədris tapşırığındakı birləşmələr + alt qruplar")
    SAME_TEACHER = "same_teacher", pgettext_lazy(_CTX, "Eyni fənn + eyni müəllim + eyni dil")
    NONE = "none", pgettext_lazy(_CTX, "Axın yoxdur (hər qrup ayrıca)")


#: Tədris günləri defoltu — mövcud cədvəl redaktoru ilə eyni (B.e.–Şənbə).
DEFAULT_WEEKDAYS = (1, 2, 3, 4, 5, 6)

#: İşləmə parametrlərinin defoltları və sərhədləri (UI + servis eyni mənbədən oxuyur).
DEFAULT_PARAMS = {
    "time_limit": 45,
    "weekdays": list(DEFAULT_WEEKDAYS),
    "weeks": 15,
    "stream_policy": StreamPolicy.TASK_ROWS,
    "keep_published": False,
    "include_vacant": True,
    "weights": {},
}
TIME_LIMIT_MIN = 5
TIME_LIMIT_MAX = 240

#: Brauzer işləməsi (Celery əlçatmaz olanda sinxron fallback) üçün tavan — sorğu donmasın.
SYNC_TIME_LIMIT = 20

#: Çəkilər UI-da tənzimlənə bilən alt çoxluq (qalanı mühərrik defoltu).
TUNABLE_WEIGHTS = (
    "teacher_idle",
    "discouraged",
    "group_single_day",
    "same_subject_day",
    "group_overload",
    "teacher_overload",
    "move",
)

KIND_LECTURE = "lecture"
KIND_SEMINAR = "seminar"
KIND_LAB = "lab"
KINDS = (KIND_LECTURE, KIND_SEMINAR, KIND_LAB)

__all__ = [
    "ACTIVE_STATUSES",
    "BAND_CODES",
    "BUILTIN_POLICY",
    "Band",
    "DEFAULT_PARAMS",
    "DEFAULT_WEEKDAYS",
    "KINDS",
    "KIND_LAB",
    "KIND_LECTURE",
    "KIND_SEMINAR",
    "LEVEL_CODES",
    "Level",
    "PERMISSION",
    "PolicyLevel",
    "REVIEWABLE_STATUSES",
    "RunStatus",
    "SYNC_TIME_LIMIT",
    "ScopeKind",
    "StreamPolicy",
    "TIME_LIMIT_MAX",
    "TIME_LIMIT_MIN",
    "TUNABLE_WEIGHTS",
]
