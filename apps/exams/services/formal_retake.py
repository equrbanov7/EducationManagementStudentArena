"""Midterm / final üzrə yenidən cəhd — YALNIZ rəsmi «Yenidən imtahan cəhdi» axını ilə (sahib 2026-10-24).

Nəticələr səhifəsinin «Yenidən şans ver» (tələbə) və «Qrupa yenidən imtahan cəhdi» (qrup) əməlləri
quiz / placement / practice imtahanlarında dərhal əlavə cəhd verir. Midterm və final üçün isə cəhd hüququ
yalnız İmtahan Mərkəzinin rəsmi səhifəsindən (``/accounts/profile/?section=exam-chance``) verilir: orada
cəhdin əsası, əmr / sərəncam № və tarixi, sənəd və qeyd məcburidir və silinməyən qeyd yazılır
(``registrar.retake_chance``). Bu modul:

* :func:`requires_formal_retake` — imtahan rəsmi axın tələb edirmi (birbaşa endpoint-lər bunu yoxlayıb
  imtina edir — UI-dan yan keçmək olmur);
* :func:`formal_retake_url` — rəsmi səhifəyə ön-doldurulmuş keçid (imtahan, tələbə və ya qrup axtarışı).
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse

from .access_policy import SECURE_EXAM_CATEGORIES

#: Rəsmi səhifə bölməsi və ön-doldurma parametrləri (``accounts`` «exam-chance» bölməsi oxuyur).
EXAM_CHANCE_SECTION = "exam-chance"
FOCUS_PARAM_VALUE = "grant"


def requires_formal_retake(exam) -> bool:
    """Midterm / final — birbaşa əlavə cəhd QADAĞANDIR, yalnız rəsmi «Yenidən imtahan cəhdi»."""
    return (getattr(exam, "exam_type_extended", "") or "") in SECURE_EXAM_CATEGORIES


def formal_retake_url(exam, *, student=None, group_name: str = "") -> str:
    """``/accounts/profile/?section=exam-chance&chance_exam=…`` — imtahan, tələbə / qrup ön-doldurulur.

    * tələbə → yalnız ``chance_student`` (id; bölmə tələbəni org daxilində özü həll edir və çipi işarələyir).
      İstifadəçi adı URL-ə QOYULMUR — nəticələr səhifəsində anonim yoxlama pəncərəsində ad sızmasın;
    * qrup → ``chance_student_q`` = qrup adı (qrupun tələbələri axtarışda çıxır, hər biri ayrıca seçilir).
    """
    params = {"section": EXAM_CHANCE_SECTION, "chance_exam": str(exam.pk), "chance_focus": FOCUS_PARAM_VALUE}
    if student is not None:
        params["chance_student"] = str(getattr(student, "pk", student))
    elif group_name:
        params["chance_student_q"] = str(group_name)[:100]
    return f"{reverse('accounts:profile')}?{urlencode(params)}"


__all__ = [
    "EXAM_CHANCE_SECTION",
    "FOCUS_PARAM_VALUE",
    "formal_retake_url",
    "requires_formal_retake",
]
