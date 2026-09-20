"""Jurnal səhifəsinin OXU memo-ları (performans, 2026-09-20 gecə auditi).

`journal_detail` GET bir açılış üçün eyni üç şeyi təkrar-təkrar oxuyurdu:
AssessmentScheme (4×), sillabus dosyesi (4×), kollokvium pəncərələri (3×).
Bu modul onları BİR dəfə oxuyub offering obyektinə yapışdırır; oxuyan
köməkçilər (`gradebook.ensure_assessment_scheme`, `syllabus_for_offering_obj`,
`kollokvium_windows.window_for`) memo varsa oradan qayıdır, yoxdursa canlı
sorğu edir. Memo yalnız view-in GET yolunda qoyulur — POST/servis/test yolları
dəyişmir.
"""

from __future__ import annotations

from apps.syllabus import public as syllabus_services

from . import gradebook, kollokvium_windows
from .journal_access import offering_or_404


def preload(offering) -> None:
    gradebook.preload_assessment_scheme(offering)
    syllabus_services.preload_syllabus_for_offering(offering)
    kollokvium_windows.preload_windows(offering)


def offering_for_detail(request, offering_id):
    """Jurnal səhifələri (detal, rubrik) üçün tenant-scope-lu offering; GET-də oxu memo-ları ilə."""
    offering = offering_or_404(request, offering_id)
    if request.method == "GET":
        preload(offering)
    return offering
