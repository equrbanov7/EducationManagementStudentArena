"""Tələbəyə göstərilən test variantları üçün qeyri-şəffaf (opaque) tokenlər.

Audit 2026-09-28 EX28-01 (P0): əvvəllər radio/checkbox ``value``-su xam
``ExamQuestionOption.id`` idi. Id-lər ardıcıldır və müəllif sırası (A→E) ilə
yaradılırdı; END_QUESTION konvensiyasında düzgün cavab birinci variantdır —
yəni ən kiçik ``value`` düzgün cavabı açırdı. İndi tələbə yalnız attempt-ə
bağlı HMAC tokeni görür; server onu sualın öz variantları arasında geri
xəritələyir. Naməlum token sadəcə nəzərə alınmır (heç vaxt 500 deyil).
"""

from django.conf import settings
from django.utils.crypto import salted_hmac

_TOKEN_SALT = "exams.option-token"
_TOKEN_LENGTH = 16


def option_token(attempt_id, option_id) -> str:
    """``(attempt, option)`` cütü üçün sabit, proqnozlaşdırılmaz token."""
    return salted_hmac(_TOKEN_SALT, f"{attempt_id}:{option_id}", algorithm="sha256").hexdigest()[:_TOKEN_LENGTH]


def _legacy_raw_ids_allowed() -> bool:
    # Deploy pəncərəsi üçün ops rıçağı: köhnə (tokensiz) açıq səhifələrin xam
    # id-ləri yalnız bu bayraq açıq olanda və yalnız sualın öz variantı olduqda
    # qəbul edilir. Default — bağlı (xam id qəbul edilmir).
    return bool(getattr(settings, "EXAM_OPTION_TOKENS_ACCEPT_RAW_IDS", False))


def option_ids_from_tokens(attempt_id, option_ids, raw_values):
    """Göndərilmiş tokenləri sualın variant id-lərinə çevir.

    Qaytarır: ``set[int]`` — tanınan seçimlər; ``None`` — dəyər göndərilib,
    amma heç biri tanınmayıb (saxta/köhnə token). ``None`` çağırana "seçimi
    dəyişmə" deməkdir: köhnə səhifədən gələn yazı mövcud cavabı silməsin.
    """
    values = [str(value).strip() for value in raw_values if str(value or "").strip()]
    if not values:
        return set()
    option_ids = list(option_ids)
    lookup = {option_token(attempt_id, option_id): option_id for option_id in option_ids}
    legacy_ids = {str(option_id): option_id for option_id in option_ids} if _legacy_raw_ids_allowed() else {}

    selected = set()
    for value in values:
        option_id = lookup.get(value)
        if option_id is None:
            option_id = legacy_ids.get(value)
        if option_id is not None:
            selected.add(option_id)
    if not selected:
        return None
    return selected


__all__ = ["option_ids_from_tokens", "option_token"]
