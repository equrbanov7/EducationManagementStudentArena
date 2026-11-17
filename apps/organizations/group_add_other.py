"""«Tələbəni qrupa əlavə et» — BAŞQA qrupdakı tələbə (sahib 2026-11-18).

Əvvəl dialoq yalnız qrupsuz tələbələri göstərirdi. Sahib: «axtardıqca bütün tələbələr görünsün; başqa
qrupdadırsa göstərin — ya əlavə olaraq (əcnəbi tələbə 2 qrupda ola bilər, əsas qrupuna dəymirik), ya da
məcburi keçid edək». İki rejim (``other_mode``):

* ``extra`` — öz qrupu QALIR; tələbə bu qrupun cari semestr jurnallarına əlavə olunur (registrar xidməti,
  jurnal modalının eyni zənciri — bax :mod:`apps.registrar.group_extra_member`);
* ``transfer`` — rəsmi köçürmə (:func:`student_transfer.transfer_student_group`), «Qrupu dəyiş» ilə eyni.

Qrupsuz tələbələr əvvəlki kimi gedir (``group_actions._add_students``). Səbəb tələb olunmur (sahib 2026-09-08);
verilməyibsə audit üçün avtomatik mətn yazılır.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from . import student_transfer as hooks

_CTX = "accounts.groups"

OTHER_MODE_EXTRA = "extra"
OTHER_MODE_TRANSFER = "transfer"
OTHER_MODES = (OTHER_MODE_EXTRA, OTHER_MODE_TRANSFER)
#: Seçicidə başqa qrupdakı tələbənin id-si bu önəkli gəlir (JS rejim seçimini göstərsin); server təmizləyir.
OTHER_ID_PREFIX = "x:"


def clean_record_id(value: str) -> str:
    value = (value or "").strip()
    return value[len(OTHER_ID_PREFIX) :] if value.startswith(OTHER_ID_PREFIX) else value


def add_other_group_students(*, records, unit, mode, period, by_user, reason) -> dict:
    """Başqa qrupdakı tələbələri ``mode`` ilə bu qrupa bağla. ValidationError yuxarı keçir (rollback)."""
    transferred, extra, warnings = [], [], []
    for record in records:
        old_name = getattr(record.group, "name", "") or "—"
        if mode == OTHER_MODE_TRANSFER:
            hooks.transfer_student_group(
                record=record,
                new_group=unit,
                period=period,
                by_user=by_user,
                reason=reason
                or pgettext(_CTX, "Qrup reyestrindən məcburi köçürmə: %(old)s → %(new)s")
                % {"old": old_name, "new": unit.name},
            )
            transferred.append(record)
            continue
        outcome = hooks.add_student_extra_group(
            record=record,
            group=unit,
            period=period,
            by_user=by_user,
            reason=reason or pgettext(_CTX, "Qrup reyestrindən əlavə üzv (öz qrupu: %s)") % old_name,
        )
        name = (record.student.get_full_name() or "").strip() or record.student.username
        if outcome.get("added"):
            extra.append(record)
        for item in outcome.get("skipped") or []:
            warnings.append(f"{name} — {item['subject']}: {item['message']}")
    return {"transferred": transferred, "extra": extra, "warnings": warnings}


def result_message(*, added: int, transferred: int, extra: int) -> str:
    parts = []
    if added:
        parts.append(pgettext(_CTX, "%d tələbə qrupa əlavə olundu") % added)
    if transferred:
        parts.append(pgettext(_CTX, "%d tələbə bu qrupa köçürüldü") % transferred)
    if extra:
        parts.append(pgettext(_CTX, "%d tələbə öz qrupunda qalaraq bu qrupun jurnallarına əlavə olundu") % extra)
    return "; ".join(parts) + "." if parts else ""


__all__ = [
    "OTHER_ID_PREFIX",
    "OTHER_MODES",
    "OTHER_MODE_EXTRA",
    "OTHER_MODE_TRANSFER",
    "add_other_group_students",
    "clean_record_id",
    "result_message",
]
