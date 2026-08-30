"""Redaktorun HƏDƏF versiyasının həlli — `?version=` / `?syllabus=` sorğusundan.

Ayrıca modul saxlanılır ki, context builder ağır redaktor modulunu yalnız bölmə
AKTİV olanda import etsin (profil səhifəsinin qalan 60+ bölməsi bu koddan
təsirlənmir).

FAIL-CLOSED: təşkilat filtri HƏMİŞƏ tətbiq olunur — başqa kirayəçinin UUID-i
verilsə nəticə ``None``-dur (RLS onsuz da ikinci qat qorumadır).
"""

from __future__ import annotations

import uuid


def safe_uuid(raw):
    """Sorğudakı xam mətni UUID-ə çevirir; yanlış formatda ``None`` qaytarır.

    Filtrdə xam mətn işlətsək Django ``ValidationError`` atır və istifadəçi 500
    görür — sorğu parametri istifadəçi girişidir, ona görə burada süzülür.
    """
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return None


def resolve_editor_version(request, organization):
    """``SyllabusVersion`` və ya ``None``.

    Prioritet: ``?version=<uuid>`` → dosyenin ``?syllabus=<uuid>`` cari versiyası.
    """
    if organization is None:
        return None

    from apps.syllabus.models import Syllabus, SyllabusVersion

    related = (
        "syllabus",
        "syllabus__subject",
        "syllabus__period",
        "syllabus__program",
        "syllabus__chair_unit",
        "syllabus__offering",
        "syllabus__offering__group",
    )

    version_id = safe_uuid((request.GET.get("version") or "").strip())
    if version_id is not None:
        return (
            SyllabusVersion.objects.filter(organization=organization, pk=version_id)
            .select_related(*related)
            .first()
        )

    syllabus_id = safe_uuid((request.GET.get("syllabus") or "").strip())
    if syllabus_id is None:
        return None
    syllabus = (
        Syllabus.objects.filter(organization=organization, pk=syllabus_id)
        .select_related("subject", "period", "program", "current_version")
        .first()
    )
    if syllabus is None or syllabus.current_version_id is None:
        return None
    return (
        SyllabusVersion.objects.filter(organization=organization, pk=syllabus.current_version_id)
        .select_related(*related)
        .first()
    )


__all__ = ["resolve_editor_version", "safe_uuid"]
