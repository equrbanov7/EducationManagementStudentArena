"""«Yoxlanılacaq işlər» / «Dəyərləndirilmiş nəticələr» — imtahan əhatəsi (sahib 2026-10-26).

Sahib: «dəyərləndirilmiş nəticələrdə imtahan mərkəzi işçisi və s. o da görsün». Əvvəl hər iki
növbə yalnız ``author=request.user`` imtahanlarını yığırdı — RİM / başqa mərkəz hesabının yaratdığı
midterm/final nəticələri mərkəz işçisinə görünmürdü. Qayda «İmtahanlarım» və müəllim paneli ilə
EYNİDİR (``apps.exams.services.access_policy.manageable_exams_q``): öz imtahanları HƏMİŞƏ + imtahan
mərkəzi üzvü (rəhbər / işçi, AKTİV təşkilatda) üçün təşkilatın bütün midterm/final-ı. Quiz və
kateqoriyasız imtahanlar əvvəlki kimi yalnız müəllifindir; tenant sərhədi çağıranın
``_tenant_scoped_exams``-ındadır.
"""

from apps.exams.public import manageable_exams_q


def review_exams_q(user):
    """``Exam`` süzgəci — növbələrin imtahan əhatəsi (mərkəz üzvü deyilsə ``author=user``)."""
    return manageable_exams_q(user, getattr(user, "active_organization", None))


__all__ = ["review_exams_q"]
