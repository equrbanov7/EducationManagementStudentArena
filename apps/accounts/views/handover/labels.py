"""Təhvil səthinin TƏRCÜMƏ OLUNAN mətnləri (bloker etiketləri + xəta mesajları).

Servis qatı (``apps.registrar.handover``) qəsdən tərcüməsizdir: o, KOD qaytarır
(``journal_closed``, ``past_period`` …). Kodları insan mətninə çevirmək HTTP
səthinin işidir və məhz burada olur — belədə eyni kod jurnal səhifəsində,
bölmədə və gələcək API-də fərqli sözlərlə göstərilə bilər, servis isə
dəyişməz qalır.

⚠️ ``pgettext`` (lazy DEYİL) qəsdəndir: nəticə JSON cavabına düşür, yəni sorğu
anındakı aktiv dildə hesablanmalıdır. Lazy proxy JSON-a serializasiya olunmur.

⚠️ **«blocked» SIZINTISI.** ``HandoverError("blocked", …)``-un mətni servisdə
qurulurdu (``handover_actions.BLOCKER_MESSAGES``) və AZ idi; ``error_message``
xəritəsində «blocked» açarı olmadığı üçün bu AZ mətn fallback kimi cavaba
düşürdü — nəticədə POST cavabı DÖRD dildə də azərbaycanca qayıdırdı. Artıq
kodlar exception-la birlikdə gəlir (``HandoverError.codes``) və mətn BURADA,
aktiv dildə qurulur.
"""

from __future__ import annotations

from django.utils.translation import pgettext

_CTX = "accounts.handover"

#: Geri qaytarma istiqamətinin adı — ``blocker_labels(action=…)`` üçün.
REVERT = "revert"


def blocker_labels(*, action: str = "reassign") -> dict:
    """Bloker kodu → istifadəçi mətni (cari dildə).

    ``action="revert"`` verildikdə istiqamətə görə fərqlənən üç kod öz mətnini
    alır: geri qaytarmada «təhvil verilə bilməz» yox, «geri qaytarıla bilməz»
    deyilməlidir, əks halda istifadəçi hansı əməlin bloklandığını anlamır.
    """
    labels = {
        "outside_scope": pgettext(_CTX, "Bu fənn sizin səlahiyyət sahənizə düşmür"),
        "journal_closed": pgettext(_CTX, "Jurnal bağlanıb — bağlı semestrin müəllimi dəyişdirilmir"),
        "past_period": pgettext(_CTX, "Semestr başa çatıb — tarixi jurnal toxunulmazdır"),
        "offering_inactive": pgettext(_CTX, "Dərs açılışı aktiv deyil"),
        "same_instructor": pgettext(_CTX, "Fənn onsuz da bu müəllimdədir"),
        "target_not_eligible": pgettext(_CTX, "Seçilmiş müəllim bal yazma səlahiyyətinə malik deyil"),
        "actor_is_current_instructor": pgettext(_CTX, "Öz fənninizi özünüz təhvil verə bilməzsiniz"),
        "no_target": pgettext(_CTX, "Yeni müəllim seçilməyib"),
    }
    if action == REVERT:
        labels.update(
            {
                "past_period": pgettext(
                    _CTX, "Semestr təhvildən sonra başa çatıb — tarixi jurnalın sahibliyi geri qaytarılmır"
                ),
                "journal_closed": pgettext(_CTX, "Jurnal bağlanıb — geri qaytarmadan əvvəl RİM jurnalı açmalıdır"),
                "offering_inactive": pgettext(_CTX, "Dərs açılışı arxivləşdirilib — geri qaytarma mümkün deyil"),
                # Zəncir irəli getdikdə server ``chain_moved`` ilə 409 verir
                # (``handover_actions.revert``). Bu kod bloker SİYAHISINDA deyil,
                # amma tarixçə sətri onu da SƏBƏB kimi göstərməlidir — əks halda
                # düymənin niyə olmadığı istifadəçiyə heç yerdə deyilmir.
                # msgid ``error_message``-dəki mətnin EYNİSİDİR (dörd dildə hazır).
                "chain_moved": pgettext(
                    _CTX, "Fənn təhvildən sonra yenidən başqasına verilib — əvvəlcə sonuncu təhvili geri qaytarın."
                ),
            }
        )
    return labels


def blocked_message(codes, *, action: str = "reassign") -> str:
    """Bloker kodları → cari dildə bir cümlə (``code == "blocked"`` cavabı).

    Kodlar boş gəlirsə (məs. köhnə serializasiya) ümumi mətn qaytarılır —
    istifadəçi heç vaxt boş mesaj görmür.
    """
    labels = blocker_labels(action=action)
    parts = [labels.get(code, code) for code in (codes or ()) if code]
    if not parts:
        return (
            pgettext(_CTX, "Geri qaytarma mümkün deyil.")
            if action == REVERT
            else pgettext(_CTX, "Təhvil mümkün deyil.")
        )
    return ". ".join(parts) + "."


def error_message(code: str, fallback: str = "", *, codes=(), action: str = "reassign") -> str:
    """Servis xəta kodunu tərcümə olunmuş mətnə çevirir (tapılmasa fallback).

    ``fallback`` adətən servisin AZ mətnidir — o, YALNIZ son çarədir; tanınan
    hər kod burada, aktiv dildə cavab verməlidir.
    """
    if code == "blocked":
        return blocked_message(codes, action=action)
    messages = {
        "reason_required": pgettext(_CTX, "Təhvil üçün səbəb yazılmalıdır."),
        "nothing_selected": pgettext(_CTX, "Heç bir fənn seçilməyib."),
        "too_many_rows": pgettext(_CTX, "Bir dəfəyə çox sayda fənn seçilib — seçimi azaldın."),
        "offering_not_found": pgettext(_CTX, "Dərs açılışı tapılmadı."),
        "handover_not_found": pgettext(_CTX, "Təhvil qeydi tapılmadı."),
        "already_reverted": pgettext(_CTX, "Bu təhvil artıq geri qaytarılıb."),
        "chain_moved": pgettext(
            _CTX, "Fənn təhvildən sonra yenidən başqasına verilib — əvvəlcə sonuncu təhvili geri qaytarın."
        ),
        "concurrent_change": pgettext(_CTX, "Bu fənnin müəllimi az öncə dəyişdirilib — səhifəni yeniləyin."),
        "target_not_eligible": pgettext(_CTX, "Seçilmiş müəllim bal yazma səlahiyyətinə malik deyil."),
        "journal_closed": pgettext(_CTX, "Jurnal bağlanıb — əvvəlcə RİM jurnalı açmalıdır."),
        "permission_denied": pgettext(_CTX, "Bu əməliyyat üçün icazəniz yoxdur."),
        "unknown_action": pgettext(_CTX, "Naməlum əməliyyat."),
    }
    return messages.get(code) or blocker_labels(action=action).get(code) or fallback or _generic_failure()


def _generic_failure() -> str:
    return pgettext(_CTX, "Əməliyyat yerinə yetirilmədi.")


__all__ = ["REVERT", "blocked_message", "blocker_labels", "error_message"]
