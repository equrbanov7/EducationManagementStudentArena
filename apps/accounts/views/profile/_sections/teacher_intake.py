"""Profil «teacher-intake» bölməsi — Müəllim idxalı (`user.import`, 2026-09-08).

Tələbə idxalı ilə eyni çərçivə müqaviləsi (`teacher_intake_section`): icazə
bayrağı, endpoint URL-ləri, sütun kataloqu, hədd rəqəmləri. Fayl və parollar
serverdə saxlanılmır.
"""

from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.services import intake
from apps.accounts.services.intake import teachers

_CTX = "teacher_intake"


def build_teacher_intake_section(request, section, *, active_organization, allowed_sections, active_section):
    if "teacher-intake" not in allowed_sections or active_section != "teacher-intake":
        return
    section["access_denied_message"] = pgettext(
        _CTX, "Müəllim idxalı üçün icazəniz yoxdur — bu bölmə yalnız `user.import` açarı olan rollar üçündür."
    )
    has_access = bool(active_organization is not None and intake.can_import(request.user, active_organization))
    section["has_access"] = has_access
    if not has_access:
        return
    section["template_url"] = reverse("accounts:teacher_intake_template")
    section["preview_url"] = reverse("accounts:teacher_intake_preview")
    section["apply_url"] = reverse("accounts:teacher_intake_apply")
    section["columns"] = [
        {"key": column.key, "header": column.header, "hint": column.hint, "required": column.required}
        for column in teachers.columns()
    ]
    section["max_rows"] = intake.MAX_ROWS
    section["max_upload_mb"] = intake.MAX_UPLOAD_BYTES // (1024 * 1024)
    section["scope_label"] = getattr(active_organization, "name", "") or ""


__all__ = ["build_teacher_intake_section"]
