"""Tələbə kabinetində («Nəticələrim» / «Ümumi tədris məlumatı») fənnin müəllim(lər)i — tələbənin ÖZ payına görə.

Şikayət (MR-000490, 2026-11-18): bölünmüş jurnalda seminar başqa müəllimdədir (:class:`JournalShare`), kabinet isə
yalnız ``offering.instructor``-u (jurnal sahibi = mühazirəçi) göstərirdi — seminar müəlliminin adı görünmürdü.

Qayda jurnal siyahısındakı «müəllim — dərs növü» ilə eynidir (:mod:`.journal_list_load_teachers`): aktiv paylar
(növlər; boş = hamısı) + sahib; sahibə yalnız payların götürmədiyi növlər qalır. Fərq: tələbəyə yalnız ONU əhatə
edən paylar sayılır (tələbə siyahılı pay başqa tələbələrindirsə, onun müəllimi bu tələbəyə göstərilmir).
Bir müəllim qalırsa — əvvəlki kimi yalnız ad; bir neçəsi — «Ad (Mühazirə) · Ad (Seminar)». Sorğular: paylar +
pay–tələbə bağları + dərs tipləri (sabit say, N+1 yoxdur).
"""

from __future__ import annotations

from collections import defaultdict

from .models import JournalShare

_KINDS = ("lecture", "seminar", "lab")


def _name(user) -> str:
    return ((user.get_full_name() or "").strip() or user.username) if user is not None else ""


def teacher_names(rows) -> dict:
    """``rows`` = transkript sətirləri (``offering`` + ``enrollment_id``) → ``{enrollment_id: "müəllim mətni"}``."""
    offerings = {}
    for row in rows:
        offering = row.get("offering")
        if offering is not None and getattr(offering, "pk", None) is not None:
            offerings.setdefault(offering.pk, offering)
    if not offerings:
        return {}
    shares = list(
        JournalShare.objects.filter(offering_id__in=list(offerings), is_active=True)
        .select_related("teacher")
        .order_by("created_at")
    )
    names = {}
    if not shares:
        for row in rows:
            offering = row.get("offering")
            names[row["enrollment_id"]] = _name(getattr(offering, "instructor", None))
        return names

    from .page_contexts import attach_kind_labels

    attach_kind_labels(list(offerings.values()))  # slot_kinds + kind_labels_map (praktiki etiketi daxil)
    covered = defaultdict(set)
    for share_id, enrollment_id in JournalShare.enrollments.through.objects.filter(
        journalshare_id__in=[s.pk for s in shares]
    ).values_list("journalshare_id", "enrollment_id"):
        covered[share_id].add(enrollment_id)
    by_offering = defaultdict(list)
    for share in shares:
        by_offering[share.offering_id].append(share)

    for row in rows:
        offering = row.get("offering")
        enrollment_id = row["enrollment_id"]
        if offering is None or getattr(offering, "pk", None) is None:
            continue
        mine = [s for s in by_offering.get(offering.pk, ()) if s.pk not in covered or enrollment_id in covered[s.pk]]
        if not mine:
            names[enrollment_id] = _name(offering.instructor)
            continue
        known = [k for k in (getattr(offering, "slot_kinds", None) or ()) if k in _KINDS]
        kinds = known or list(_KINDS)
        entries: dict = {}
        claimed: set = set()
        for share in mine:
            share_kinds = [k for k in kinds if not share.kinds or k in share.kinds]
            claimed |= set(share_kinds)
            entry = entries.setdefault(share.teacher_id, {"name": _name(share.teacher), "kinds": []})
            entry["kinds"] += [k for k in share_kinds if k not in entry["kinds"]]
        if offering.instructor_id:
            owner_kinds = [k for k in kinds if k not in claimed]
            if owner_kinds or offering.instructor_id in entries:
                entry = entries.setdefault(offering.instructor_id, {"name": _name(offering.instructor), "kinds": []})
                entry["kinds"] = [k for k in kinds if k in owner_kinds or k in entry["kinds"]]
        # Sahib birinci (adətən mühazirəçi), sonra paylar.
        ordered = sorted(entries.items(), key=lambda item: item[0] != offering.instructor_id)
        if len(ordered) == 1:
            names[enrollment_id] = ordered[0][1]["name"]
            continue
        labels = getattr(offering, "kind_labels_map", None) or {}
        parts = []
        for _teacher_id, entry in ordered:
            shown = " · ".join(str(labels.get(k, k)) for k in entry["kinds"]) if known else ""
            parts.append(f"{entry['name']} ({shown})" if shown else entry["name"])
        names[enrollment_id] = " · ".join(parts)
    return names
