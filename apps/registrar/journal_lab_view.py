"""Lab qrupunun və seminar alt qrupunun ayrıca görünüşü — siyahıda alt sətir, jurnalda ``?lab=N`` / ``?seminar=N``.

Sahib 2026-11-08: «236 SBİO Lab-1 vuranda oradakı uşaqlar, aşağıda 236 SBİO Lab-2 vuranda oradakı uşaqlar görünsün» +
«ana qrup hamısı olanda elə görünsün, mühazirə olanda da; seminar seçiləndə bölünən, lab seçəndə bölünənlər». Jurnal
BİR qalır; bu yalnız GÖRÜNÜŞDÜR:

* siyahı (:func:`attach_list_rows`): «Laboratoriya» süzgəcində lab qrupu olan jurnalın altında hər lab qrupu, «Seminar»
  süzgəcində hər seminar alt qrupu üçün sətir — ad, tələbə sayı, keçid. «Hamısı» / «Mühazirə»-də alt sətir YOXDUR
  (ana qrup bütöv). Seçilmiş növ üçün İKİ sorğu (sayılar + adlar), N+1 yoxdur;
* jurnal (:func:`resolve` + :func:`apply`): yalnız həmin qrupun tələbələri və o qrupa aid dərslər (qrupun öz
  dərsləri + qrupsuz, hamıya aid dərslər). Yazı qaydaları dəyişmir (``lab_groups.applies``).
"""

from __future__ import annotations

from collections import defaultdict

from . import lab_groups, seminar_groups
from .models import Enrollment, LabGroup, LessonKind, SeminarGroup

#: növ → (sorğu parametri, qeydiyyat/dərs sahəsi, ad cədvəli, qayda modulu, ad memo-su, siyahı atributu)
_SPLITS = {
    LessonKind.LAB: ("lab", "lab_group", LabGroup, lab_groups, "_lab_group_names_memo", "lab_sections"),
    LessonKind.SEMINAR: (
        "seminar",
        "seminar_group",
        SeminarGroup,
        seminar_groups,
        "_seminar_group_names_memo",
        "seminar_sections",
    ),
}


def resolve(request, offering, kind=LessonKind.LAB):
    """``?lab=N`` / ``?seminar=N`` → jurnalda mövcud qrupun nömrəsi; yoxdursa ``None`` (adi görünüş)."""
    param, _field, _model, rules, _memo, _attr = _SPLITS[kind]
    raw = str(request.GET.get(param) or "").strip() if request is not None else ""
    if not raw.isdigit():
        return None
    number = int(raw)
    return number if number in rules.offering_groups(offering) else None


def apply(journal, number, kind=LessonKind.LAB) -> None:
    """Jurnal lüğətini bir qrupa daralt: sətirlər + sütunlar (xanalar sütun sırası ilə)."""
    field = _SPLITS[kind][1]
    keep = [
        index
        for index, meta in enumerate(journal["lesson_meta"])
        if meta["lesson"].kind == kind and getattr(meta["lesson"], field) in (None, number)
    ]
    journal["lesson_meta"] = [journal["lesson_meta"][index] for index in keep]
    journal["lessons"] = [meta["lesson"] for meta in journal["lesson_meta"]]
    rows = [row for row in journal["rows"] if getattr(row["enrollment"], field) == number]
    for row in rows:
        row["cells"] = [row["cells"][index] for index in keep]
    journal["rows"] = rows
    journal["guest_rows"] = [row for row in rows if row["is_guest"]]


def attach_list_rows(offerings, selected_kind: str = "") -> None:
    """Hər açılışa ``lab_sections`` / ``seminar_sections = [{"number", "label", "count"}]`` (seçilməyən növdə boş)."""
    offerings = list(offerings)
    for _param, _field, _model, _rules, _memo, attr in _SPLITS.values():
        for offering in offerings:
            setattr(offering, attr, [])
    if selected_kind not in _SPLITS or not offerings:
        return
    _param, field, model, rules, memo, attr = _SPLITS[selected_kind]
    counts = defaultdict(dict)
    for offering_id, number, total in _counts(offerings, field):
        counts[offering_id][number] = total
    names = defaultdict(dict)
    for offering_id, number, name in model.objects.filter(offering_id__in=list(counts), name__gt="").values_list(
        "offering_id", "number", "name"
    ):
        names[offering_id][number] = name
    for offering in offerings:
        groups = counts.get(offering.pk)
        if not groups or getattr(offering, "journal_entry_url", ""):
            continue
        setattr(offering, memo, names.get(offering.pk, {}))
        setattr(
            offering,
            attr,
            [
                {"number": number, "label": rules.label(number, offering), "count": groups[number]}
                for number in sorted(groups)
            ],
        )


def _counts(offerings, field):
    from django.db.models import Count

    return (
        Enrollment.objects.filter(
            offering_id__in=[offering.pk for offering in offerings],
            status=Enrollment.Status.ENROLLED,
            **{f"{field}__isnull": False},
        )
        .values("offering_id", field)
        .order_by()
        .annotate(total=Count("pk"))
        .values_list("offering_id", field, "total")
    )


__all__ = ["apply", "attach_list_rows", "resolve"]
