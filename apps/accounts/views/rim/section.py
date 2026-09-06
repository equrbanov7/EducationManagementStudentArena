"""«RİM mərkəzi» profil bölməsinin context qurucusu.

Bölmə SPA panelidir: server yalnız çərçivəni (icazə xəritəsi, endpoint URL-ləri,
statistika) verir; siyahı və detal JSON endpoint-lərindən AJAX-la gəlir. Ona görə
burada ağır sorğu yoxdur — 766 qruplu tenantda seçicilər də type-ahead-dir
(bax `services/rim/create_options.py`).
"""

from __future__ import annotations

from datetime import date

from django.urls import reverse

from apps.accounts.services import intake
from apps.accounts.services.rim import (
    PERM_BLOCK,
    PERM_CREDENTIALS,
    PERM_EDIT,
    PERM_SEARCH,
    PERM_SOFT_DELETE,
    can_create,
    resolve_actor,
)
from apps.accounts.services.rim.create import MAX_NOTE_LENGTH
from apps.accounts.services.rim.lifecycle import MAX_REASON_LENGTH, MIN_REASON_LENGTH
from apps.accounts.services.rim.profile_edit import FIELD_LABELS
from apps.organizations.permissions import get_permission_label as permission_label

#: Qəbul ili seçicisinin əhatəsi — cari ildən neçə il geriyə göstərilir.
ADMISSION_YEAR_SPAN = 8


def _admission_years() -> list:
    """Yeni → köhnə sırada qəbul illəri (gələn il də daxil — erkən qeydiyyat)."""

    top = date.today().year + 1
    return [top - offset for offset in range(ADMISSION_YEAR_SPAN + 1)]


def _create_context(actor) -> dict:
    """«Yeni hesab» axınının çərçivəsi — tək-tək form + toplu fayl.

    TOPLU axın mövcud «Tələbə idxalı» endpoint-lərini çağırır (eyni `user.import`
    qapısı, eyni plan qurucusu) — RİM üçün ayrıca parser/validator yazılmır.
    """

    allowed = can_create(actor)
    return {
        "can_create": allowed,
        "create_url": reverse("accounts:rim_create_account"),
        "create_catalog_url": reverse("accounts:rim_create_catalog"),
        "intake_template_url": reverse("accounts:student_intake_template"),
        "intake_preview_url": reverse("accounts:student_intake_preview"),
        "intake_apply_url": reverse("accounts:student_intake_apply"),
        "intake_max_rows": intake.MAX_ROWS,
        "intake_max_upload_mb": intake.MAX_UPLOAD_BYTES // (1024 * 1024),
        "intake_columns": [
            {"header": column.header, "hint": column.hint, "required": column.required} for column in intake.columns()
        ],
        "admission_years": _admission_years(),
        "max_note_length": MAX_NOTE_LENGTH,
    }


def build_rim_center_section(request) -> dict:
    """«RİM mərkəzi» bölməsi üçün context (bax `context_builder/_stage3.py`)."""
    actor = resolve_actor(request)

    return {
        "can_search": actor.has(PERM_SEARCH),
        "can_set_password": actor.has(PERM_CREDENTIALS),
        "can_block": actor.has(PERM_BLOCK),
        "can_soft_delete": actor.has(PERM_SOFT_DELETE),
        "can_edit": actor.has(PERM_EDIT),
        "is_superadmin": actor.is_superadmin,
        "organization": actor.organization,
        # Aktorun faktiki RİM səlahiyyətləri — paneldə AZ etiketlə göstərilir ki,
        # operator nə edə biləcəyini əvvəlcədən görsün (səhv klik olmasın).
        "granted_permissions": [{"key": key, "label": permission_label(key)} for key in actor.rim_permissions],
        # Endpoint-lər data-atributla JS-ə ötürülür (xarici JS `{% url %}` görmür).
        "search_url": reverse("accounts:rim_user_search"),
        "action_url": reverse("accounts:rim_action"),
        "detail_url_template": reverse("accounts:rim_user_detail", kwargs={"user_id": 0}),
        "role_assignment_url": f"{reverse('accounts:profile')}?section=role-assignment",
        "editable_field_labels": FIELD_LABELS,
        "min_reason_length": MIN_REASON_LENGTH,
        "max_reason_length": MAX_REASON_LENGTH,
        "access_denied_message": ("" if actor.can_use_rim else "Bu bölmə üçün icazəniz yoxdur."),
        **_create_context(actor),
    }


__all__ = ["build_rim_center_section"]
