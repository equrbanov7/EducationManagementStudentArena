"""«Aydındır, Vakant saxla və təsdiqlə» — bölünməmiş saatları «Vakant» yazıb bölgünü təsdiqləmək (sahib 2026-11-12).

Sahib: «kimsə təyin olunmasa, mən bölgünü təsdiqləyəndə aydın info versin və "aydındır" deyəndən sonra
təsdiqlənsin, onda vakantda qalsın». Təsdiq dialoqu natamam sətirləri göstərir; istifadəçi açıq razılıq
verəndə UI ``fill_vacant=1`` göndərir və burada BİR tranzaksiyada:

* hər natamam sətrin hər fəaliyyətinin QALAN saatı ``assign_amended`` ilə «Vakant» bölgüsü olur
  (``teacher=None`` — bölgü dialoqundakı «Vakant» seçimi ilə eyni). Təsdiqlənmiş sənəddə açıq düzəliş
  hədəfi olmayan sətir üçün düzəliş sistem səbəbi/qeydi ilə açılır (və ya UI-ın göndərdiyi səbəb/qeydlə);
* vakant bölgü jurnalı KÖÇÜRMÜR (``live_edit=False``) və sətir sinxronu çağırılmır (``sync_offerings=False``):
  jurnal sahibi yalnız vakant olmayan bölgüdən gəlir; təsdiqin öz sinxronu əvvəlki qaydalarla işləyir;
* ``confirm_distribution`` — bildiriş qaydası dəyişmir (vakant bölgü heç kimə bildiriş vermir);
* audit: hansı sətirlər / fəaliyyətlər / neçə saat «Vakant» saxlanıldı.

Artıq bölgü (bölünmüş saat > cəm) və intensiv kursun natamam sətri sərt maneədir — «Vakant» bunları düzəltmir;
o zaman HEÇ NƏ yazılmır.
"""

from __future__ import annotations

from django.db import transaction
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason
from ..models import TeachingTaskRow
from .distribution import confirm_distribution, distribution_readiness, ensure_confirmable, ensure_not_over_assigned
from .row_edit import assign_amended
from .scoping import WorkloadDenied

#: Vakant bölgünün qeydi və düzəlişin sistem qeydi (UI səbəb/qeyd göndərməyibsə).
VACANT_NOTE = "Təsdiq zamanı bölünməmiş saatlar Vakant saxlanıldı"
INTENSIVE_INCOMPLETE = "workload.intensive_incomplete"


def _amend(amend) -> dict:
    """UI düzəliş səbəbi + qeyd göndəribsə onlar, yoxsa sistem səbəbi («Digər») + :data:`VACANT_NOTE`."""
    amend = amend or {}
    reason = str(amend.get("reason") or "").strip()
    note = str(amend.get("note") or "").strip()
    if reason and note:
        return {"reason": reason, "note": note}
    return {"reason": AmendmentReason.OTHER.value, "note": VACANT_NOTE}


def _ensure_fillable(readiness: dict) -> None:
    ensure_not_over_assigned(readiness)
    intensive = [item for item in readiness["incomplete_rows"] if item["is_intensive"]]
    if intensive:
        raise WorkloadDenied(
            INTENSIVE_INCOMPLETE,
            pgettext(
                "workload",
                "İntensiv kurs sətri natamamdır: %(names)s. Onun müəllimi «İntensiv kurs» dialoqundan təyin "
                "olunur — «Vakant» burada yazılmır.",
            )
            % {"names": ", ".join(dict.fromkeys(item["subject"] for item in intensive[:3]))},
        )


@transaction.atomic
def confirm_with_vacant(*, task, actor, request=None, amend=None) -> dict:
    """Qalan saatları «Vakant» yaz → bölgünü təsdiqlə. Qaytarır: ``confirm_distribution`` nəticəsi + ``vacant_filled``."""
    ensure_confirmable(task, actor)
    readiness = distribution_readiness(task)
    _ensure_fillable(readiness)
    amend = _amend(amend)
    ids = [item["row_id"] for item in readiness["incomplete_rows"]]
    rows = {
        str(row.pk): row for row in TeachingTaskRow.objects.filter(task=task, pk__in=ids).prefetch_related("groups")
    }
    filled = []
    for item in readiness["incomplete_rows"]:
        row = rows.get(item["row_id"])
        if row is None:
            continue
        row.task = task  # düzəliş statusu (``amended``) eyni obyektdə qalsın — təsdiq onu görür
        for gap in item["gaps"]:
            if gap["remaining"] <= 0:
                continue
            saved = assign_amended(
                row=row,
                actor=actor,
                amend=amend,
                request=request,
                activity=gap["activity"],
                teacher_id=None,
                hours=gap["remaining"],
                note=VACANT_NOTE,
                sync_offerings=False,
                live_edit=False,
            )
            filled.append(
                {
                    "row_id": item["row_id"],
                    "subject": item["subject"],
                    "groups": item["groups"],
                    "activity": gap["activity"],
                    "hours": gap["remaining"],
                    "assignment_id": str(saved.pk),
                }
            )
    hours = sum(entry["hours"] for entry in filled)
    if filled:
        log_action(
            AuditAction.UPDATE,
            user=getattr(actor, "user", None),
            organization=task.organization,
            obj=task,
            new_values={"rows": len({entry["row_id"] for entry in filled}), "hours": hours, "filled": filled},
            reason="workload.confirm_vacant_filled",
            request=request,
            resource_type="workload.TeachingTask",
            resource_id=str(task.pk),
            resource_repr=f"{task.chair_id} · {task.academic_year}",
        )
    result = confirm_distribution(task=task, actor=actor, request=request)
    result["vacant_filled"] = {"rows": len({entry["row_id"] for entry in filled}), "hours": hours}
    return result


__all__ = ["INTENSIVE_INCOMPLETE", "VACANT_NOTE", "confirm_with_vacant"]
