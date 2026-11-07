"""Lab qrupunun ayrıca görünüşü — siyahıda «236 SBİO · Lab-1» sətri, jurnalda ``?lab=1`` (sahib 2026-11-08).

Sahib: «236 SBİO Lab-1 vuranda oradakı uşaqlar, aşağıda 236 SBİO Lab-2 vuranda oradakı uşaqlar görünsün». Jurnal BİR
qalır; bu yalnız GÖRÜNÜŞDÜR:

* siyahı (:func:`attach_list_rows`): lab qrupu olan jurnalın altında hər qrup üçün sətir — ad
  (:func:`apps.registrar.lab_groups.label`), tələbə sayı, keçid ``?kind=lab&lab=N``. Mühazirə / seminar süzgəcində
  çıxmır. Səhifə dilimi üçün İKİ sorğu (sayılar + adlar), N+1 yoxdur;
* jurnal (:func:`resolve` + :func:`apply`): yalnız həmin qrupun tələbələri və o qrupa aid lab dərsləri (qrupun öz
  dərsləri + qrupsuz, hamıya aid lab dərsləri). Yazı qaydaları dəyişmir (``lab_groups.applies``).
"""

from __future__ import annotations

from collections import defaultdict

from . import lab_groups
from .models import Enrollment, LabGroup, LessonKind


def resolve(request, offering):
    """``?lab=N`` → jurnalda mövcud lab qrupunun nömrəsi; yoxdursa ``None`` (adi görünüş)."""
    raw = str(request.GET.get("lab") or "").strip() if request is not None else ""
    if not raw.isdigit():
        return None
    number = int(raw)
    return number if number in lab_groups.offering_groups(offering) else None


def apply(journal, number) -> None:
    """Jurnal lüğətini bir lab qrupuna daralt: sətirlər + sütunlar (xanalar sütun sırası ilə)."""
    keep = [
        index
        for index, meta in enumerate(journal["lesson_meta"])
        if meta["lesson"].kind == LessonKind.LAB and meta["lesson"].lab_group in (None, number)
    ]
    journal["lesson_meta"] = [journal["lesson_meta"][index] for index in keep]
    journal["lessons"] = [meta["lesson"] for meta in journal["lesson_meta"]]
    rows = [row for row in journal["rows"] if row["enrollment"].lab_group == number]
    for row in rows:
        row["cells"] = [row["cells"][index] for index in keep]
    journal["rows"] = rows
    journal["guest_rows"] = [row for row in rows if row["is_guest"]]


def attach_list_rows(offerings, selected_kind: str = "") -> None:
    """Hər açılışa ``lab_sections = [{"number", "label", "count"}]`` (lab qrupu yoxdursa boş)."""
    offerings = list(offerings)
    for offering in offerings:
        offering.lab_sections = []
    if selected_kind not in ("", LessonKind.LAB) or not offerings:
        return
    counts = defaultdict(dict)
    for offering_id, number, total in _counts(offerings):
        counts[offering_id][number] = total
    names = defaultdict(dict)
    for offering_id, number, name in LabGroup.objects.filter(offering_id__in=list(counts), name__gt="").values_list(
        "offering_id", "number", "name"
    ):
        names[offering_id][number] = name
    for offering in offerings:
        groups = counts.get(offering.pk)
        if not groups or getattr(offering, "journal_entry_url", ""):
            continue
        offering._lab_group_names_memo = names.get(offering.pk, {})
        offering.lab_sections = [
            {"number": number, "label": lab_groups.label(number, offering), "count": groups[number]}
            for number in sorted(groups)
        ]


def _counts(offerings):
    from django.db.models import Count

    return (
        Enrollment.objects.filter(
            offering_id__in=[offering.pk for offering in offerings],
            status=Enrollment.Status.ENROLLED,
            lab_group__isnull=False,
        )
        .values("offering_id", "lab_group")
        .order_by()
        .annotate(total=Count("pk"))
        .values_list("offering_id", "lab_group", "total")
    )


__all__ = ["apply", "attach_list_rows", "resolve"]
