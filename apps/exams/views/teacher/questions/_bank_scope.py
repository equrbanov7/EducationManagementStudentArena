"""teacher questions paketi — sual bankı süzgəci (GET siyahısı və «bütün uyğun sualları seç» üçün ORTAQ).

Sahib 2026-11-11: toplu zolaqda «Bütün N sualı seç» səhifələmədən asılı deyil — klient ID siyahısı
göndərmir, yalnız ``select_scope=all_matching`` + cari süzgəc sahələrini; server eyni süzgəci özü tətbiq edib
sualları özü müəyyən edir (siyahı səhifəsi ilə EYNİ funksiya — iki yol bir-birindən ayrıla bilməz).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models.functions import Lower

from apps.exams.constants import EXAM_LANGUAGE_VALUES
from apps.exams.services.bank_analysis import analyze_question_bank
from core.search_text import tolerant_q

from .constants import QUESTION_BANK_SEARCH_MAX_LENGTH

ALLOWED_STATUSES = frozenset({"all", "active", "inactive"})
ALLOWED_SORTS = frozenset({"newest", "oldest", "az", "za"})
ALLOWED_FLAGS = frozenset({"has-error", "has-warning", "has-dup", "has-structure", "has-balance", "is-clean"})
SCOPE_FIELD = "select_scope"
SCOPE_ALL_MATCHING = "all_matching"


@dataclass(frozen=True)
class BankFilter:
    q: str = ""
    status: str = "all"
    sort: str = "newest"
    language: str = ""
    flag: str = ""

    @classmethod
    def from_params(cls, params) -> "BankFilter":
        def text(name, default=""):
            return (params.get(name) or default).strip()

        status = text("status", "all").lower()
        sort = text("sort", "newest").lower()
        language = text("language").lower()
        flag = text("flag").lower()
        return cls(
            q=text("q")[:QUESTION_BANK_SEARCH_MAX_LENGTH],
            status=status if status in ALLOWED_STATUSES else "all",
            sort=sort if sort in ALLOWED_SORTS else "newest",
            language=language if language in EXAM_LANGUAGE_VALUES else "",
            flag=flag if flag in ALLOWED_FLAGS else "",
        )

    def as_audit(self) -> dict:
        pairs = (("q", self.q), ("status", self.status), ("language", self.language), ("flag", self.flag))
        return {key: value for key, value in pairs if value and value != "all"}


def filtered_questions(exam, flt: BankFilter, *, analysis=None):
    """Süzgəcə uyğun suallar (sırasız, prefetch-siz). ``analysis`` — artıq hesablanıbsa təkrar istifadə."""
    questions = exam.questions.all()
    # Sual/blok/variant mətni — az/ing hərfə dözümlü, tokenli (sahib 2026-09-26).
    search_q = tolerant_q(flt.q, ("text", "block__name", "options__text"))
    if search_q is not None:
        matched_ids = exam.questions.filter(search_q).values_list("id", flat=True).distinct()
        questions = questions.filter(id__in=matched_ids)
    if flt.status == "active":
        questions = questions.filter(is_active=True)
    elif flt.status == "inactive":
        questions = questions.filter(is_active=False)
    if flt.language:
        questions = questions.filter(language=flt.language)
    if flt.flag:
        # Keyfiyyət çipi (dublikat, xəbərdarlıq, balans və s.) — bütün bank üzrə hesablanmış flag dəstləri.
        if analysis is None:
            analysis = analyze_question_bank(exam, language=flt.language or None)
        if analysis.enabled:
            questions = questions.filter(id__in=analysis.flagged_ids.get(flt.flag, set()))
    return questions


def ordered_questions(questions, sort: str):
    if sort == "oldest":
        return questions.order_by("created_at", "id")
    if sort == "az":
        return questions.order_by(Lower("text"), "id")
    if sort == "za":
        return questions.order_by(Lower("text").desc(), "id")
    return questions.order_by("-created_at", "-id")


def wants_all_matching(post) -> bool:
    return (post.get(SCOPE_FIELD) or "").strip() == SCOPE_ALL_MATCHING


__all__ = [
    "ALLOWED_FLAGS",
    "ALLOWED_SORTS",
    "ALLOWED_STATUSES",
    "SCOPE_ALL_MATCHING",
    "SCOPE_FIELD",
    "BankFilter",
    "filtered_questions",
    "ordered_questions",
    "wants_all_matching",
]
