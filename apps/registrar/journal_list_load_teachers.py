"""Geniş jurnal siyahısında cari bölgü: hər sətirdə «müəllim — dərs növü» (sahib 2026-11-05).

Şikayət: «müəllim öz səhifəsində jurnalı düzgün görür, hamının jurnallarına baxış yerində isə yük dəyişəndə də
köhnə görünür». Geniş siyahı yalnız ``offering.instructor``-u göstərirdi; bölünmüş jurnalın seminarçısı (payı yük
sinxronundan gəlir — :mod:`.journal_workload_shares`) görünmürdü, sahib isə bütün növlərin müəllimi kimi qalırdı.

İndi müəllimin ÖZ görünüşü ilə eyni mənbə: aktiv :class:`JournalShare` payları (növlər; boş = hamısı) + sahib —
sahibə yalnız BÜTÜN siyahını örtən başqa payların götürmədiyi növlər qalır (``journal_shares.journal_scope``
qaydası). Səhifə dilimi üçün İKİ sorğu (paylar + sətir bağları), N+1 yoxdur.

«Mənim jurnallarım» / seçilmiş müəllimin öz siyahısında (``only_teacher_id``) sətir YALNIZ həmin müəllimi göstərir —
seminarçının siyahısında mühazirəçinin (jurnal sahibinin) adı çıxmır (sahib 2026-11-05).
"""

from __future__ import annotations

from collections import defaultdict

from .models import JournalShare

_KINDS = ("lecture", "seminar", "lab")


def _name(user) -> str:
    return (user.get_full_name() or user.username).strip() if user is not None else ""


def attach(offerings, *, only_teacher_id=None) -> None:
    """Hər açılışa ``load_teachers = [{"name", "kinds"}]`` (növ etiketləri ``kind_label`` ilə eyni dildə)."""
    if not offerings:
        return
    shares = list(
        JournalShare.objects.filter(offering_id__in=[o.pk for o in offerings], is_active=True)
        .select_related("teacher")
        .order_by("created_at")
    )
    partial = set(
        JournalShare.enrollments.through.objects.filter(journalshare_id__in=[s.pk for s in shares]).values_list(
            "journalshare_id", flat=True
        )
    )
    by_offering = defaultdict(list)
    for share in shares:
        by_offering[share.offering_id].append(share)
    for offering in offerings:
        kinds = [k for k in (getattr(offering, "slot_kinds", None) or _KINDS) if k in _KINDS]
        labels = getattr(offering, "kind_labels_map", None) or {}
        rows: dict = {}
        claimed: set = set()
        for share in by_offering.get(offering.pk, ()):
            share_kinds = [k for k in kinds if not share.kinds or k in share.kinds]
            if share.pk not in partial:
                claimed |= set(share_kinds)
            entry = rows.setdefault(share.teacher_id, {"name": _name(share.teacher), "kinds": []})
            entry["kinds"] += [k for k in share_kinds if k not in entry["kinds"]]
        if offering.instructor_id:
            owner_kinds = [k for k in kinds if k not in claimed]
            if owner_kinds or offering.instructor_id in rows or not rows:
                entry = rows.setdefault(offering.instructor_id, {"name": _name(offering.instructor), "kinds": []})
                entry["kinds"] = [k for k in kinds if k in owner_kinds or k in entry["kinds"]]
        if only_teacher_id is not None and only_teacher_id in rows:
            rows = {only_teacher_id: rows[only_teacher_id]}
        offering.load_teachers = [
            {"name": entry["name"], "kinds": " · ".join(str(labels.get(k, k)) for k in entry["kinds"])}
            for entry in rows.values()
        ]
