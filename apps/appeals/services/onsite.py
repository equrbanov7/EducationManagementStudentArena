"""Apellyasiyanın iki rejimi — «imtahan sonunda» / «sonradan» (sahib 2026-10-20).

Sahib: «Tələbə apellyasiyanı imtahan bitən kimi verirsə düzgün cavabları da görür. Sonradan
(evdən) verirsə YALNIZ sualları görür — nə düzgün cavabı, nə də digər variantları».

Qərar HƏMİŞƏ serverdə, bu modulda verilir; şablon yalnız nəticəni göstərir:

* **imtahan sonunda** (``filed_onsite=True``) — hamısı birlikdə:
  - cəhdin sahibi, sınaq cəhdi deyil, imtahan apellyasiya olunan kateqoriyadadır (final/midterm);
  - «Sistem tənzimləmələri» → ``exam.appeal_onsite_minutes`` (defolt 15, 0 = rejim söndürülüb)
    müddəti ``finished_at``-dan hələ keçməyib;
  - sorğu universitet şəbəkəsindəndir (imtahanın özü ilə EYNİ qayda — ``exam_network_allowed``);
  - **eyni sessiya**: bu sessiya həmin cəhdin təhvildən sonrakı nəticə ekranını görüb
    (``post_finish_result_seen``) — və ya mərkəzin (final/midterm) 5 dəqiqəlik nəticə baxışı hələ gedir
    (nəticə səhifəsi açarı onsuz da həmin anda göstərir, ``secure_answer_key_hidden``).
* **sonradan** — qalan bütün hallar: forma/detal yalnız sualın mətnini (şəkil/video/kod blokları
  daxil) göstərir; variantlar, tələbənin seçimi, düzgün cavab, ideal cavab serverdən ÖTÜRÜLMÜR.

Forma «imtahan sonunda» rejimində açılıbsa (sessiyada qeyd), göndəriş müddət bitdikdən sonra da
``ONSITE_SUBMIT_SLACK`` ərzində həmin rejimdə qeydə alınır — tələbə formanı doldurarkən rejim
«yolda» dəyişməsin (o, cavabları artıq görüb; nişan bunu düzgün əks etdirməlidir).
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone

from apps.exams.public import (
    attempt_answer_key_hidden,
    attempt_in_center,
    exam_answers_release_locked,
    exam_network_allowed,
    post_finish_result_seen,
    secure_answer_key_hidden,
)
from core.runtime_settings_appeals import appeal_onsite_minutes

from .permissions import is_appealable_exam

#: «İmtahan sonunda» rejimində AÇILMIŞ formaların cəhd id-ləri (göndəriş tolerantlığı üçün).
ONSITE_FORM_SESSION_KEY = "appeals_onsite_forms"
#: Forma müddət daxilində açılıbsa, göndəriş üçün əlavə vaxt.
ONSITE_SUBMIT_SLACK = timedelta(minutes=30)
_ONSITE_FORM_MAX_ENTRIES = 10

MODE_ONSITE = "onsite"
MODE_LATER = "later"


def onsite_deadline(attempt):
    """«İmtahan sonunda» rejiminin bitmə anı və ya ``None`` (rejim söndürülüb / cəhd bitməyib)."""
    minutes = appeal_onsite_minutes()
    finished = getattr(attempt, "finished_at", None)
    if minutes <= 0 or not finished:
        return None
    return finished + timedelta(minutes=minutes)


def _session_ids(request, key):
    session = getattr(request, "session", None)
    if session is None:
        return set()
    try:
        return {int(value) for value in (session.get(key) or [])}
    except (TypeError, ValueError):
        return set()


def remember_onsite_form(request, attempt):
    """Forma «imtahan sonunda» rejimində göstərildi — göndəriş tolerantlığı üçün sessiyaya yazılır."""
    session = getattr(request, "session", None)
    if session is None:
        return
    seen = sorted(_session_ids(request, ONSITE_FORM_SESSION_KEY))
    if attempt.id in seen:
        return
    session[ONSITE_FORM_SESSION_KEY] = (seen + [attempt.id])[-_ONSITE_FORM_MAX_ENTRIES:]


def _final_center_review_active(request, attempt, *, is_profile_results, now):
    """Mərkəzin (final; açar yandırılıbsa zal girişli midterm) təhvildən sonrakı 5 dəqiqəlik nəticə baxışı.

    2026-10-20: midterm də imtahan mərkəzi axını ilə verilir — zal girişindən yaranmış midterm cəhdinin
    nəticə baxışı final kimi «imtahan sonunda» sayılır (``attempt_in_center``; kabinet rejimi deyil)."""
    if is_profile_results or not attempt_in_center(attempt):
        return False
    return not secure_answer_key_hidden(attempt, is_profile_results=False, now=now)


def appeal_onsite_eligible(request, attempt, *, is_profile_results=False, for_submit=False, now=None):
    """Bu sorğu «imtahan sonunda» rejimindədirmi (modul sənədinə bax)."""
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False) or attempt.user_id != getattr(user, "id", None):
        return False
    if getattr(attempt, "is_trial", False) or not is_appealable_exam(getattr(attempt, "exam", None)):
        return False
    deadline = onsite_deadline(attempt)
    if deadline is None:
        return False
    current = now or timezone.now()
    if for_submit and attempt.id in _session_ids(request, ONSITE_FORM_SESSION_KEY):
        deadline += ONSITE_SUBMIT_SLACK
    if current > deadline:
        return False
    same_session = post_finish_result_seen(request, attempt.id) or _final_center_review_active(
        request, attempt, is_profile_results=is_profile_results, now=current
    )
    if not same_session:
        return False
    return exam_network_allowed(request, attempt.exam, user=user)


def student_answer_details_visible(request, attempt, *, onsite):
    """Apellyasiya formasında variantlar / tələbənin cavabı / düzgün cavab tələbəyə göstərilirmi.

    YALNIZ «imtahan sonunda» rejimində — və yenə də müəllimin «nəticəni gizlət» seçimi, çox-cəhdli
    imtahanda qalan cəhd haqqı (EX28-03) və ümumi açar kilidi üstündür (açar heç vaxt sızmasın)."""
    if not onsite:
        return False
    exam = attempt.exam
    if getattr(exam, "results_hidden_from_students", False) or exam_answers_release_locked(exam):
        return False
    return not attempt_answer_key_hidden(attempt, user=getattr(request, "user", None))


def stem_only_render(delivered):
    """«Sonradan» rejimi: YALNIZ sualın gövdəsi (mətn + şəkil + video) — variant / açar ötürülmür."""
    return SimpleNamespace(
        text=getattr(delivered, "text", ""),
        image_url=getattr(delivered, "image_url", ""),
        image_replaces_text=getattr(delivered, "image_replaces_text", False),
        video_url=getattr(delivered, "video_url", ""),
        correct_answer="",
        options=[],
    )


__all__ = [
    "MODE_LATER",
    "MODE_ONSITE",
    "ONSITE_FORM_SESSION_KEY",
    "ONSITE_SUBMIT_SLACK",
    "appeal_onsite_eligible",
    "onsite_deadline",
    "remember_onsite_form",
    "stem_only_render",
    "student_answer_details_visible",
]
