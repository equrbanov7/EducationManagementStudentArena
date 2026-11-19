"""«Kafedra materialları» (``unit-subject-folders``) — tyutor / laborantın YALNIZ-OXU qovluq görünüşü.

Sahib 2026-10-27: «özlərinə aid olan kafedra … dərs materialı varsa ona baxmaq olsun». Vəziyyətlər (``state``):
``no_org`` · ``noscope`` (açar / əhatə yoxdur) · ``list`` · ``folder`` (``sf_folder``) · ``missing``.
Əhatə və görünüş qaydası ``services.unit_view``-dadır; bu panel heç bir yazı formu / düyməsi göstərmir.
Sorğu sayı sətir sayından asılı deyil (sayğac subquery-dir, siyahı ``LIST_CAP`` ilə kəsilir).
"""

from __future__ import annotations

from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils.translation import pgettext

from .. import public
from ..constants import SECTION_UNIT
from ..models import FolderMaterial, SubjectFolder
from ..services import lookups, unit_view
from ..services.queries import tolerant_q
from . import common

_CTX = "subject_folder.ui"

#: Siyahıda göstərilən qovluq tavanı (süzgəc + axtarış daraldır).
LIST_CAP = 120


def unit_panel(context) -> dict:
    request, organization, user, base = common.resolve(context)
    if organization is None or not lookups.is_authenticated(user):
        return {"state": "no_org"}
    urls = {"list": common.section_url(base, SECTION_UNIT)}
    if not unit_view.has_unit_view(user, organization):
        return {"state": "noscope", "urls": urls}
    folder_id = common.uuid_param(request, "folder")
    if folder_id is not None:
        return _folder_state(organization, user, urls, folder_id)
    return _list_state(request, organization, user, base, urls)


def _period_label(period) -> str:
    return getattr(period, "name", "") or pgettext(_CTX, "Semestrsiz")


def _visible_material_count():
    rows = (
        FolderMaterial.objects.filter(folder_id=OuterRef("pk"), is_published=True, is_archived=False)
        .filter(Q(topic__isnull=True) | Q(topic__is_archived=False))
        .order_by()
        .values("folder_id")
        .annotate(n=Count("pk"))
        .values("n")
    )
    return Coalesce(Subquery(rows, output_field=IntegerField()), Value(0))


def _list_state(request, organization, user, base, urls) -> dict:
    period_id = common.uuid_param(request, "period")
    search = common.param(request, "q", limit=120)
    folders = unit_view.visible_folders(user, organization).select_related("subject", "period", "owner")
    periods = {
        pk: name
        for pk, name in folders.order_by().exclude(period=None).values_list("period_id", "period__name").distinct()
    }
    if period_id is not None:
        folders = folders.filter(period_id=period_id)
    clause = tolerant_q(
        search, ("title", "subject__name", "owner__first_name", "owner__last_name"), compact_fields=("subject__code",)
    )
    if clause is not None:
        folders = folders.filter(clause)
    folders = folders.annotate(visible_materials=_visible_material_count()).order_by(
        "-period__start_date", "subject__name", "title"
    )
    total = folders.count()
    rows = [
        {
            "folder": folder,
            "url": common.section_url(base, SECTION_UNIT, folder=folder.pk),
            "teacher": common.user_name(folder.owner),
            "period_label": _period_label(folder.period),
            "materials": folder.visible_materials,
        }
        for folder in folders[:LIST_CAP]
    ]
    everything = [{"value": "", "label": pgettext(_CTX, "Hamısı")}]
    return {
        "state": "list",
        "urls": urls,
        "folders": rows,
        "has_more": total > LIST_CAP,
        "list_cap": LIST_CAP,
        "is_filtered": bool(period_id or search),
        "filter_count_label": pgettext(_CTX, "Nəticə: %(count)d qovluq") % {"count": total},
        "filter_fields": [
            {
                "name": "sf_period",
                "label": pgettext(_CTX, "Semestr"),
                "kind": "select",
                "options": everything
                + [{"value": str(pk), "label": name} for pk, name in sorted(periods.items(), key=lambda x: x[1])],
                "value": str(period_id or ""),
            },
            {
                "name": "sf_q",
                "label": pgettext(_CTX, "Axtarış"),
                "kind": "search",
                "value": search,
                "placeholder": pgettext(_CTX, "Fənn, qovluq və ya müəllim…"),
                "wide": True,
            },
        ],
        "kpi_tiles": [
            {"label": pgettext(_CTX, "QOVLUQLAR"), "value": total},
            {
                "label": pgettext(_CTX, "MATERİAL"),
                "value": sum(row["materials"] for row in rows),
                "note": pgettext(_CTX, "dərc edilmiş"),
            },
        ],
    }


def _folder_state(organization, user, urls, folder_id) -> dict:
    folder = (
        SubjectFolder.objects.filter(organization=organization, pk=folder_id)
        .select_related("organization", "subject", "period", "owner")
        .first()
    )
    if folder is None or not unit_view.covers_folder(user, folder):
        return {"state": "missing", "urls": urls}
    # Sahib 2026-11-19 (Monitorinq şöbəsi: «fənn qovluqlarına FULL baxmaq»): jurnalı oxuya bilən əməkdaş
    # (``unit_view.is_full_viewer``) qovluğu TAM görür: dərc edilməmiş
    # material və tapşırıqlar da (göndəriş sayı ilə). Yalnız ``subject_folder.view_unit`` daşıyan (tyutor /
    # laborant) əvvəlki kimi yalnız dərc edilmiş materialı görür. Yazı əməli heç bir halda yoxdur.
    full = unit_view.is_full_viewer(user, folder)
    topics: dict = {}
    general = {"materials": [], "tasks": []}

    def bucket(item):
        if item.topic_id is None:
            return general
        return topics.setdefault(item.topic_id, {"topic": item.topic, "materials": [], "tasks": []})

    materials = unit_view.all_materials(folder) if full else unit_view.published_materials(folder)
    for material in materials:
        bucket(material)["materials"].append(_material_row(material))
    task_count = 0
    if full:
        for task in unit_view.all_tasks(folder):
            bucket(task)["tasks"].append(_task_row(task))
            task_count += 1
    return {
        "state": "folder",
        "urls": urls,
        "folder": folder,
        "teacher": common.user_name(folder.owner),
        "period_label": _period_label(folder.period),
        "topics": sorted(topics.values(), key=lambda row: (row["topic"].order, row["topic"].week_no or 0)),
        "general": general if (general["materials"] or general["tasks"]) else None,
        "is_full_view": full,
        "task_count": task_count,
    }


def _task_row(task) -> dict:
    return {
        "task": task,
        "kind_label": str(public.TaskKind(task.kind).label),
        "max_points": task.max_points if task.kind == public.TaskKind.SELFWORK else None,
        "hidden": not unit_view.is_visible_item(task),
        "sent": task.sent_count,
    }


def _material_row(material) -> dict:
    return {
        "material": material,
        "hidden": not unit_view.is_visible_item(material),
        "download_url": common.material_download_url(material) if material.file else "",
        "size": common.human_size(material.size) if material.file else "",
        "kind_label": str(public.MaterialKind(material.kind).label),
    }


__all__ = ["LIST_CAP", "unit_panel"]
