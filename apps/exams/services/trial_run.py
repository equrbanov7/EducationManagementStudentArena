"""Müəllimin «Sınaq keç» (trial run) icazəsi — imtahanın vəziyyətindən asılı olmayaraq (2026-10-20).

Sahibin tələbi: «imtahan yaradarkən "Sınaqdan keç"ə click edərkən imtahan deaktivdə olsa, tarixə də
çatmasa yenə mümkün olsun». Yəni sınaq cəhdi (``ExamAttempt.is_trial``):

* deaktiv (qaralama) imtahanda da başlayır və davam edir;
* başlanğıc tarixi çatmamış və ya bitmə tarixi keçmiş imtahanda da başlayır;
* final/midterm qapılarından (şəbəkə, PIN, «gündə bir rəsmi imtahan», qayıb buraxılışı) keçmir —
  sınaq nəticəyə/statistikaya/jurnala sayılmır.

Sərhəd: bu güzəşt YALNIZ ``?trial=1`` ilə gələn və ``can_trial_run_exam`` icazəsi olan istifadəçiyə
şamildir. Tələbə (və ya icazəsiz istifadəçi) ``trial=1`` əlavə etsə də adi, sərt yola düşür
(deaktiv → 404, tarixlər yoxlanılır). Arxivlənmiş / silinmiş imtahan sınaq üçün də bağlı qalır.
Sınaqda ən azı bir aktiv sual tələbi dəyişmir.
"""

from __future__ import annotations

TRIAL_PARAM = "trial"


def trial_run_requested(request) -> bool:
    """Sorğu «Sınaq keç» niyyəti daşıyırmı (``?trial=1`` — təsdiq səhifəsinin POST-u da)."""
    if request is None:
        return False
    return request.GET.get(TRIAL_PARAM) == "1" or request.POST.get(TRIAL_PARAM) == "1"


def can_trial_run_exam(user, exam) -> bool:
    """Bu istifadəçi imtahanı istənilən vəziyyətdə sınaqdan keçirə bilərmi.

    * İmtahan müəllifi — həmişə (əvvəlki davranış; müəllifin sınaq cəhdi heç vaxt adi cəhdə çevrilmir).
    * Müəllif olmayan — yalnız imtahanın suallarını idarə edə bilən imtahan mərkəzi / superadmin
      (``can_manage_exam_questions`` — detal səhifəsindəki «Sınaq keç» düyməsinin eyni şərti).
      ``can_manage_exam_questions`` final olmayan imtahan üçün hamıya ``True`` qaytarır, ona görə
      müəllif olmayan üçün imtahan mərkəzi rolu ayrıca şərtdir — tələbə heç vaxt keçmir.

    Tenant izolyasiyası çağıranın queryset-indədir (``tenant_scoped_exams``).
    """
    if user is None or not getattr(user, "is_authenticated", False) or exam is None:
        return False
    user_pk = getattr(user, "pk", None)
    if user_pk is not None and user_pk == getattr(exam, "author_id", None):
        return True
    from apps.exams.services.access_policy import can_manage_exam_questions, is_exam_center_user

    return bool(is_exam_center_user(user) and can_manage_exam_questions(user, exam))


def is_trial_run_request(request, exam) -> bool:
    """``?trial=1`` + sınaq icazəsi — start yolunun bütün güzəştləri bu şərtə bağlıdır."""
    return trial_run_requested(request) and can_trial_run_exam(getattr(request, "user", None), exam)


def trial_attempt_ignores_exam_state(attempt, user) -> bool:
    """Davam edən sınaq cəhdi deaktiv imtahanda da açıqdırmı (yalnız cəhdin sahibi + sınaq icazəsi)."""
    if not getattr(attempt, "is_trial", False):
        return False
    user_pk = getattr(user, "pk", None)
    if user_pk is None or user_pk != getattr(attempt, "user_id", None):
        return False
    return can_trial_run_exam(user, attempt.exam)


__all__ = [
    "TRIAL_PARAM",
    "can_trial_run_exam",
    "is_trial_run_request",
    "trial_attempt_ignores_exam_state",
    "trial_run_requested",
]
