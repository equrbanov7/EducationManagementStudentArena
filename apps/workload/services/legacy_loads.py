"""Köhnə sistem DELTA köçürməsi üçün dərs yükü girişi (``apps.legacy_import.services.delta.workload`` çağırır).

Yeni məntiq YOXDUR: köhnə sistemin jurnalı (fənn + qrup(lar) + müəllim + saat) tədris şöbəsinin «Dərs yükü
faylı» sətrinə çevrilir və EYNİ axından (:func:`.load_upload.run_load_upload`) keçir — kafedranın tapşırığı,
sətir (bölünmüş sənəddə «Rəsmi sərəncam» düzəlişi ilə), müəllim bölgüsü, təsdiq, açılış, qrupun tələbələri.
Müəllim adı dəqiq yazılır (hədəf hesabın adı) — kafedranın müəllim tutuşdurması onu tapır.
"""

from __future__ import annotations

from .load_upload import run_load_upload
from .load_upload_parsing import LoadEntry
from .task_form1_parsing import group_key, group_tokens, name_words


def legacy_load_entry(
    *, line: int, teacher_text: str, season: str, groups_text: str, subject_text: str, hours: dict, credits: str = ""
) -> LoadEntry:
    return LoadEntry(
        line=line,
        teacher_text=teacher_text,
        name_words=name_words(teacher_text),
        hourly=False,
        season=season,
        groups_text=groups_text,
        group_keys=frozenset(group_key(token) for token in group_tokens(groups_text)),
        subject_text=subject_text,
        chosen_subject="",
        chosen_by="",
        hours={activity: int(value) for activity, value in hours.items() if int(value or 0) > 0},
        credits=str(credits or "")[:20],
        students="",
    )


def preview_legacy_entries(*, organization, chair, actor_user, year: str, entries, targets) -> list[str]:
    """Hər yazı üçün ``""`` (təhlükəsiz) və ya ötürmə səbəbi — YAZMIR.

    ``targets`` — yazı ilə eyni sırada ``(subject_id, {group_id, …}, teacher_id)``: axın fənni/qrupu/müəllimi
    MƏTNDƏN həll edir (tapılmayan müəllimə hesab da açır),
    ona görə mətn başqa kataloq sətrinə düşürsə (eyni adlı ikinci fənn, alt qrupa açılma) yazı ötürülür. Mövcud
    tapşırıq sətrinə bənzəyən yazı da ötürülür — o sətrin bölgüsünə (yeni sistemin qərarına) toxunulmasın.
    """
    import io

    from .task_form1_import import _RowIndex
    from .task_workbook_import import Importer
    from .tasks import find_task

    importer = Importer(
        organization=organization,
        year=year,
        actor_user=actor_user,
        apply=False,
        stdout=io.StringIO(),
        create_teachers=False,
        reassign=False,
    )
    task = find_task(organization=organization, chair_id=chair.pk, academic_year=year)
    index = _RowIndex(task) if task is not None else None
    reasons = []
    from ..teacher_hooks import chair_teacher_resolver

    teachers = chair_teacher_resolver(organization, chair, actor_user=actor_user, apply=False, tag="legacy preview")
    for entry, (subject_id, group_ids, teacher_id) in zip(entries, targets):
        resolved_teacher = teachers.resolve(entry.teacher_text)
        if not resolved_teacher.resolved or getattr(resolved_teacher.user, "pk", None) != teacher_id:
            reasons.append("teacher_resolves_elsewhere")
            continue
        if index is not None and index.match(entry)[0]:
            reasons.append("matches_existing_row")
            continue
        subject = importer.find_subject(entry.subject_text)[0]
        if subject is None or subject.pk != subject_id:
            reasons.append("subject_resolves_elsewhere")
            continue
        resolved = set()
        for token in group_tokens(entry.groups_text):
            resolved |= {unit.pk for unit, _action in importer.resolve_group(token, None) if unit is not None}
        reasons.append("" if resolved == set(group_ids) else "group_resolves_elsewhere")
    return reasons


def apply_legacy_loads(*, organization, chair, actor_user, entries, year: str) -> dict:
    """Bir kafedranın legacy yazıları — «Dərs yükü faylı» axını (yazır; tranzaksiyanı çağıran idarə edir).

    Axın qapısı rədd edərsə ``{"denied": kod}`` qaytarır (heç nə yazılmır)."""

    from .scoping import WorkloadDenied

    try:
        return run_load_upload(
            organization=organization,
            chair=chair,
            actor_user=actor_user,
            entries=list(entries),
            skipped=[],
            year=year,
            apply=True,
        )
    except WorkloadDenied as exc:
        # Axının öz qapısı (məs. deaktiv kafedra) — onun savepoint-i artıq geri qayıdıb; çağıran kafedranı ötürür.
        return {"denied": exc.code, "counters": {}}


__all__ = ["apply_legacy_loads", "legacy_load_entry", "preview_legacy_entries"]
