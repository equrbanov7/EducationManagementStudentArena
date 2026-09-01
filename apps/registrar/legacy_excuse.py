"""Köhnə üzrlü-qayıb sənədlərinin JURNAL OXU qatı (sarı xana + ✎ tarixçə).

Nə edir
-------
``registrar.LegacyExcuseDocument`` sətirlərini jurnalın ``excused`` (üq)
xanaları ilə üzləşdirir və mövcud düzəliş-tarixçə payload-unun EYNİ formasında
qeyd qaytarır.  Beləliklə UI-da paralel ikinci mexanizm YOXDUR: sarı xana,
✎ nişanı və modal — hamısı ``_correction_history_modal.html`` +
``correction_history.js`` cütünün özüdür.

Bağlantı qaydası (uydurma FK yox)
---------------------------------
Mənbədə sənədin jurnala/dərsə FK-sı YOXDUR: ``allowed_qb.uniq`` sənəd paketinin
açarıdır, jurnal ``uniqid``-i deyil (canlı mənbədə ``journals`` ilə 0 uyğunluq).
Ona görə köçürmə də, bu oxu qatı da EYNİ qaydanı işlədir — tələbə + tarix
aralığı (``rehearsal_journal_points_source.is_excused``).  Xana yalnız
``excused``-dırsa bağlanır: məhz həmin statusu yaradan qayda budur.

Nə ETMİR
--------
* Xananı müəllim üçün KİLİDLƏMİR — ``cell["corrected"]`` toxunulmaz qalır, o,
  rəsmi (sənədli) ``JournalCorrection`` deməkdir və kilid mənasını daşıyır.
  Köhnə sənəd ayrıca ``cell["legacy_excuse"]`` bayrağı ilə işarələnir.
* Heç bir bal/status/qayıb saatı dəyişmir — yalnız oxu.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from apps.registrar.models import AttendanceStatus, LegacyExcuseDocument, LegacyExcuseMappingStatus, LessonMark

#: Payload-da qeydin növü — JS eyni modalda fərqli blok göstərsin deyə.
ENTRY_KIND = "legacy_excuse"


def _date_text(value) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def _entry(document: LegacyExcuseDocument, *, include_document: bool) -> dict:
    """Bir sənədin modal qeydi — düzəliş qeydi ilə eyni açar dəsti + ``kind``."""

    period = f"{_date_text(document.starts_on)} – {_date_text(document.ends_on)}".strip(" –")
    entry = {
        "kind": ENTRY_KIND,
        "id": str(document.id),
        # Sənədin köhnə sistemə yüklənmə anı (mənbənin ``added_date``-i).
        "date": (document.source_recorded_at_text or "")[:10].replace("-", ".") or period,
        "field_display": pgettext("registrar.legacy_excuse", "Üzrlü qayıb sənədi"),
        "period": period,
        "reason": pgettext("registrar.legacy_excuse", "Köhnə sistemdən köçürülüb"),
        "note": document.note,
        "by": pgettext("registrar.legacy_excuse", "Köhnə sistem qeydi"),
        "document": document.document_name,
        "document_available": bool(document.document),
        # Fayl hələ köhnə serverdədir: UI sınıq link vermir, dürüst yazır.
        "document_note": pgettext(
            "registrar.legacy_excuse",
            "Sənədin özü köhnə sistemdədir — hələ köçürülməyib.",
        ),
        # ``old``/``new`` QƏSDƏN yoxdur: burada dəyişiklik yoxdur, sübut var.
    }
    # Fayl sonradan qoşulubsa keçid YALNIZ jurnal sahibinə/korrektora verilir
    # (``JournalCorrection`` ilə eyni qayda).  Fayl yoxdursa heç kimə link yox.
    if include_document and document.document:
        entry["document_url"] = document.document.url
    return entry


def _linked_documents(*, organization_id, student_ids, first_date, last_date):
    if not student_ids or first_date is None or last_date is None:
        return []
    return list(
        LegacyExcuseDocument.objects.filter(
            organization_id=organization_id,
            student_id__in=list(student_ids),
            mapping_status=LegacyExcuseMappingStatus.LINKED,
            starts_on__lte=last_date,
            ends_on__gte=first_date,
        ).order_by("starts_on", "source_pk")
    )


def _build_map(marks, documents, *, include_document: bool) -> dict[str, list[dict]]:
    """``{mark_id: [qeyd, ...]}`` — tələbə + tarix aralığı üzləşdirməsi."""

    by_student: dict[object, list[LegacyExcuseDocument]] = {}
    for document in documents:
        by_student.setdefault(document.student_id, []).append(document)
    result: dict[str, list[dict]] = {}
    for mark_id, student_id, lesson_date in marks:
        for document in by_student.get(student_id, ()):
            if document.starts_on <= lesson_date <= document.ends_on:
                result.setdefault(str(mark_id), []).append(_entry(document, include_document=include_document))
    return result


def _excused_marks(queryset):
    return list(
        queryset.filter(status=AttendanceStatus.EXCUSED).values_list("id", "enrollment__student_id", "lesson__date")
    )


def excuse_map_for_offering(offering, *, include_document: bool = True) -> dict[str, list[dict]]:
    """Müəllim jurnalı üçün: ``{mark_id: [sənəd qeydi]}`` (iki sorğu)."""

    marks = _excused_marks(LessonMark.objects.filter(lesson__offering=offering))
    if not marks:
        return {}
    dates = [row[2] for row in marks]
    documents = _linked_documents(
        organization_id=offering.organization_id,
        student_ids={row[1] for row in marks},
        first_date=min(dates),
        last_date=max(dates),
    )
    return _build_map(marks, documents, include_document=include_document)


def excuse_map_for_enrollment(enrollment) -> dict[str, list[dict]]:
    """Tələbə jurnalı üçün: yalnız öz xanaları."""

    marks = _excused_marks(LessonMark.objects.filter(enrollment=enrollment))
    if not marks:
        return {}
    dates = [row[2] for row in marks]
    documents = _linked_documents(
        organization_id=enrollment.organization_id,
        student_ids={enrollment.student_id},
        first_date=min(dates),
        last_date=max(dates),
    )
    # Tələbə görünüşü sənəd faylını AÇMIR (düzəliş tarixçəsi ilə eyni qayda).
    return _build_map(marks, documents, include_document=False)


def annotate_journal(journal, excuse_map) -> None:
    """Qridin xanalarına ``legacy_excuse`` bayrağı qoy (yerində, sorğusuz)."""

    if not excuse_map:
        return
    for row in journal.get("rows") or ():
        for cell in row.get("cells") or ():
            mark = cell.get("mark")
            cell["legacy_excuse"] = bool(mark is not None and str(mark.id) in excuse_map)


def attach_document(document: LegacyExcuseDocument, upload) -> bool:
    """Köhnə serverdən gətirilən faylı BOŞ qeydə qoş (yeganə icazəli mutasiya).

    Qeydin bütün digər sahələri dəyişməzdir (model ``save`` + PG trigger); fayl
    bir dəfə qoşulandan sonra əvəzlənə də, silinə də bilmir.  Prosedur:
    ``docs/migration/UZRLU_QAYIB_SENEDLERI.md``.  Fayl artıq varsa ``False``
    qaytarır — çağıran yenidən yükləməyə cəhd etməsin.
    """

    if document.document or upload is None:
        return False
    document.document = upload
    document.full_clean(exclude=None, validate_unique=False)
    document.save(update_fields=["document", "updated_at"])
    return True


def attach_to_offering_journal(offering, journal: dict, corrections_map: dict) -> dict:
    """Müəllim/korrektor jurnalını bir çağırışla annotasiya et (view-lar üçün).

    Qrid xanalarına ``legacy_excuse`` bayrağı qoyur və sənəd qeydlərini mövcud
    düzəliş-tarixçə payload-una qatır — beləliklə çağıran view-da cəmi bir sətir
    olur (``views.journal_detail`` və ``correction_views``).
    """

    excuse_map = excuse_map_for_offering(offering)
    annotate_journal(journal, excuse_map)
    return merge_into(corrections_map, excuse_map)


def merge_into(corrections_map: dict, excuse_map: dict) -> dict:
    """Sənəd qeydlərini mövcud düzəliş tarixçəsinin ARDINA əlavə et.

    Eyni ``json_script`` payload-u işlədilir, ona görə ✎ nişanı hər iki qeyd
    növünü tək modalda göstərir; sıra xronolojidir (əvvəl düzəlişlər).
    """

    for mark_id, entries in excuse_map.items():
        corrections_map.setdefault(mark_id, []).extend(entries)
    return corrections_map


__all__ = [
    "ENTRY_KIND",
    "attach_document",
    "attach_to_offering_journal",
    "annotate_journal",
    "excuse_map_for_enrollment",
    "excuse_map_for_offering",
    "merge_into",
]
