"""Profil «student-intake» bölməsi — Tələbə idxalı (`user.import`).

Bölmə profil shell-inin İÇİNDƏ açılır (sol sidebar qalır, panel sağdadır).
Server YALNIZ ÇƏRÇİVƏNİ verir: icazə bayrağı, endpoint URL-ləri, sütun kataloqu
və hədd rəqəmləri. Fayl, sətirlər və birdəfəlik parollar serverdə SAXLANILMIR —
onlar yalnız iki JSON sorğusunun cavabında yaşayır (bax `views/student_intake.py`).

──────────────────────────────────────────────────────────────────────────────
CONTEXT MÜQAVİLƏSİ (UI buna söykənir — açar adları dəyişməz)
──────────────────────────────────────────────────────────────────────────────
``student_intake_section`` (dict):

    has_access            bool  — `user.import` (fail-closed)
    access_denied_message str
    template_url          str   — boş şablonun endirilməsi (GET)
    preview_url           str   — quru icra (POST, multipart)
    apply_url             str   — tətbiq (POST, multipart)
    columns               list  — [{key, header, hint, required}]
    max_rows              int   — bir faylda maksimum sətir
    max_upload_mb         int   — faylın yuxarı həddi
    scope_label           str   — aktiv təşkilatın adı (kimin adından yazılır)
"""

from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.services import intake

_CTX = "student_intake"


def build_student_intake_section(request, section, *, active_organization, allowed_sections, active_section):
    """``section`` dict-ini YERİNDƏ mutasiya edir (schedule-manage naxışı)."""

    if "student-intake" not in allowed_sections or active_section != "student-intake":
        return

    section["access_denied_message"] = pgettext(
        _CTX,
        "Tələbə idxalı üçün icazəniz yoxdur — bu bölmə yalnız `user.import` açarı olan rollar üçündür.",
    )
    has_access = bool(active_organization is not None and intake.can_import(request.user, active_organization))
    section["has_access"] = has_access
    if not has_access:
        return

    section["template_url"] = reverse("accounts:student_intake_template")
    section["preview_url"] = reverse("accounts:student_intake_preview")
    section["apply_url"] = reverse("accounts:student_intake_apply")
    section["columns"] = [
        {"key": column.key, "header": column.header, "hint": column.hint, "required": column.required}
        for column in intake.columns()
    ]
    section["max_rows"] = intake.MAX_ROWS
    section["max_upload_mb"] = intake.MAX_UPLOAD_BYTES // (1024 * 1024)
    section["scope_label"] = getattr(active_organization, "name", "") or ""


__all__ = ["build_student_intake_section"]
