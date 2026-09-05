"""Sillabus UI-nın MƏTN qatı — domen kodlarının insan dilindəki qarşılığı.

:mod:`apps.syllabus` qəsdən mətn saxlamır: tamamlanma yoxlaması strukturlaşmış
ISSUE KODLARI (16 ədəd), state maşını isə KEÇİD XƏTA KODLARI (15 ədəd) qaytarır.
Onların tərcüməsi UI qatına — bura — aiddir. Beləliklə eyni domen kodu profil
bölməsində, PDF-də və gələcək mobil səthdə fərqli formalarda göstərilə bilər.

⚠️ Rəng burada YOXDUR: status → «ton» adı verilir (``success``/``warning``/…),
CSS isə tonu ``static/css/design-tokens.css``-dəki tokenə bağlayır (dizayn
təhvili §1). Beləliklə şablonda hardcode hex qalmır.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

from apps.syllabus.constants import SyllabusStatus

_CTX = "accounts.syllabus"

#: Status → CSS «ton» adı (rəng tokenləri `syllabus.css`-dədir, dizayn §3.1).
STATUS_TONES = {
    SyllabusStatus.DRAFT.value: "neutral",
    SyllabusStatus.SUBMITTED.value: "submitted",
    SyllabusStatus.REVIEW.value: "review",
    SyllabusStatus.REVISION.value: "warning",
    SyllabusStatus.APPROVED.value: "success",
    SyllabusStatus.REJECTED.value: "danger",
    SyllabusStatus.ARCHIVED.value: "archived",
}

#: «Növbəti əməl» sütununun ton seçimi (dizayn: düzəliş/rədd sarı, bitmişlər solğun).
NEXT_STEP_TONES = {
    SyllabusStatus.REVISION.value: "warning",
    SyllabusStatus.REJECTED.value: "warning",
    SyllabusStatus.APPROVED.value: "muted",
    SyllabusStatus.ARCHIVED.value: "muted",
}

#: Auditoriya saatı növünün adı — `week.hours_mismatch` mesajına yerləşdirilir.
HOUR_KIND_LABELS = {
    "lecture": pgettext_lazy(_CTX, "Mühazirə"),
    "seminar": pgettext_lazy(_CTX, "Seminar"),
    "lab": pgettext_lazy(_CTX, "Laboratoriya"),
}

#: ``completion.Issue.code`` → şablon mətni (``%(ad)s`` yer tutucuları ilə).
ISSUE_MESSAGES = {
    "info.teacher_missing": pgettext_lazy(_CTX, "Dərsi aparan müəllim göstərilməyib"),
    "info.office_hours_missing": pgettext_lazy(_CTX, "Məsləhət saatı doldurulmayıb"),
    "desc.description_too_short": pgettext_lazy(
        _CTX, "Fənnin təsviri ən azı %(min)s simvol olmalıdır (hazırda %(have)s)"
    ),
    "desc.goal_too_short": pgettext_lazy(_CTX, "Fənnin məqsədi ən azı %(min)s simvol olmalıdır (hazırda %(have)s)"),
    "out.too_few": pgettext_lazy(_CTX, "Ən azı %(min)s təlim nəticəsi tələb olunur (hazırda %(have)s)"),
    "out.orphan_outcomes": pgettext_lazy(_CTX, "%(count)s təlim nəticəsi heç bir həftə ilə əlaqələndirilməyib"),
    "week.too_few_topics": pgettext_lazy(_CTX, "Ən azı %(min)s həftənin mövzusu yazılmalıdır (hazırda %(have)s)"),
    "week.hours_mismatch": pgettext_lazy(
        _CTX, "%(kind)s saatı tədris planındakı %(expected)s saatla uyğun gəlmir (hazırda %(have)s)"
    ),
    "week.hours_without_topic": pgettext_lazy(_CTX, "%(count)s həftədə saat yazılıb, mövzu boşdur"),
    "week.topic_without_hours": pgettext_lazy(_CTX, "%(count)s mövzuya heç bir dərs növü üzrə saat verilməyib"),
    "week.outcome_not_linked": pgettext_lazy(_CTX, "%(count)s həftədə təlim nəticəsi seçilməyib"),
    "assess.split_mismatch": pgettext_lazy(
        _CTX,
        "Sərbəst bölünən %(need)s bal tam paylanmayıb (hazırda %(have)s) — cəm 100 olmalıdır",
    ),
    "assess.negative_weight": pgettext_lazy(_CTX, "Qiymətləndirmə çəkisi mənfi ola bilməz"),
    "method.too_few": pgettext_lazy(_CTX, "Ən azı %(min)s tədris metodu seçilməlidir (hazırda %(have)s)"),
    "self.option_not_allowed": pgettext_lazy(_CTX, "Sərbəst iş strukturu seçilməyib"),
    "self.topic_count_mismatch": pgettext_lazy(
        _CTX, "Sərbəst iş mövzularının sayı seçilmiş struktura uyğun deyil (%(have)s / %(need)s)"
    ),
    "lit.primary_too_few": pgettext_lazy(_CTX, "Əsas ədəbiyyatda ən azı %(min)s mənbə olmalıdır (hazırda %(have)s)"),
    "lit.additional_too_few": pgettext_lazy(
        _CTX, "Əlavə ədəbiyyatda ən azı %(min)s mənbə olmalıdır (hazırda %(have)s)"
    ),
}

#: ``TransitionDenied.code`` → istifadəçiyə göstərilən mətn (API cavabları).
TRANSITION_MESSAGES = {
    "transition.unknown": pgettext_lazy(_CTX, "Bu əməliyyat tanınmır."),
    "transition.invalid_source": pgettext_lazy(_CTX, "Sillabusun cari statusunda bu əməliyyat mümkün deyil."),
    "transition.permission_denied": pgettext_lazy(_CTX, "Bu əməliyyat üçün icazəniz yoxdur."),
    "transition.out_of_scope": pgettext_lazy(_CTX, "Bu sillabus sizin struktur əhatənizdə deyil."),
    "transition.author_only": pgettext_lazy(_CTX, "Sillabusu yalnız onun müəllimi redaktə edə bilər."),
    "transition.reason_required": pgettext_lazy(_CTX, "Səbəb göstərilməlidir."),
    "transition.incomplete": pgettext_lazy(_CTX, "Bütün məcburi tələblər ödənilməyib — çatışmayan bəndlərə baxın."),
    "version.approved_locked": pgettext_lazy(
        _CTX, "Bu versiya təsdiqlənib və dəyişdirilə bilmir — yeni versiya yaradın."
    ),
    "version.locked": pgettext_lazy(_CTX, "Versiya kilidlidir — redaktə bağlıdır."),
    "version.open_version_exists": pgettext_lazy(_CTX, "Bu sillabusda artıq açıq versiya var: %(version)s"),
    "version.base_missing": pgettext_lazy(_CTX, "Mənbə versiya tapılmadı."),
    "version.kind_unknown": pgettext_lazy(_CTX, "Versiya növü tanınmır."),
    "section.unknown": pgettext_lazy(_CTX, "Bölmə tanınmır."),
    "section.invalid_shape": pgettext_lazy(_CTX, "Bölmə məzmununun formatı düzgün deyil (%(field)s)."),
    "section.too_long": pgettext_lazy(_CTX, "Məzmun həddindən böyükdür — ən çox %(max)s (%(field)s)."),
    "syllabus.exists": pgettext_lazy(_CTX, "Bu açılış üçün sillabus artıq mövcuddur — siyahıdan açın."),
    "section.conflict": pgettext_lazy(_CTX, "Bu bölmə başqa sessiyada dəyişdirilib — dəyişikliklər göndərilmədi."),
    "self.option_not_allowed": pgettext_lazy(_CTX, "Seçilmiş sərbəst iş strukturu universitet siyasətinə uyğun deyil."),
    "assess.split_mismatch": pgettext_lazy(
        _CTX,
        "Qiymətləndirmə bölgüsü siyasətə uyğun deyil: sərbəst bölünən %(need)s bal tam paylanmalıdır.",
    ),
    "version.structural_change_requires_major": pgettext_lazy(
        _CTX,
        "Mövzu, çəki və ya struktur dəyişdiyi üçün versiya avtomatik BÖYÜK versiyaya qaldırıldı — "
        "dəyişiklik növbəti semestrdən qüvvəyə minir.",
    ),
    "import.status_not_allowed": pgettext_lazy(_CTX, "Bu status köçürmə borusu üçün icazəli deyil."),
}

_FALLBACK = pgettext_lazy(_CTX, "Əməliyyat yerinə yetirilmədi.")


def issue_text(issue: dict) -> str:
    """``{"section","code","params"}`` → oxunaqlı AZ mətni."""
    template = ISSUE_MESSAGES.get(issue.get("code"))
    if template is None:
        return issue.get("code", "")
    params = dict(issue.get("params") or {})
    if "kind" in params:
        params["kind"] = HOUR_KIND_LABELS.get(params["kind"], params["kind"])
    try:
        return str(template) % params
    except (KeyError, TypeError, ValueError):
        return str(template)


def transition_text(code: str, params: dict | None = None) -> str:
    """``TransitionDenied.code`` → oxunaqlı AZ mətni."""
    template = TRANSITION_MESSAGES.get(code, _FALLBACK)
    try:
        return str(template) % dict(params or {})
    except (KeyError, TypeError, ValueError):
        return str(template)


__all__ = [
    "HOUR_KIND_LABELS",
    "ISSUE_MESSAGES",
    "NEXT_STEP_TONES",
    "STATUS_TONES",
    "TRANSITION_MESSAGES",
    "issue_text",
    "transition_text",
]
