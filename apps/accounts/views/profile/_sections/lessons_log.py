"""Ekran 21 «Keçilmiş dərslər» — kabinet bölməsi (`lessons-log`).

GLUE qatı: domen məntiqi ``apps.registrar.lessons_log``-dadır, bura yalnız
kontekst yığımı düşür (mövcud `teaching_office.py` naxışı).

SCOPE (README §8/8): müəllim YALNIZ öz dərslərini görür; ``journal.roster``
daşıyan aktor (kafedra müdiri / dekanlıq / RİM) öz alt-ağacını görür və
«Müəllim» filtri ona AÇILIR. Əhatəsiz aktor boş vəziyyət alır.

CONTEXT MÜQAVİLƏSİ (`lessons_log_section`)
    has_access   bool          — aktiv təşkilat konteksti var
    is_supervisor bool         — nəzarət görünüşü (müəllim filtri açıqdır)
    range        dict          — {key, start, end, chips}
    kpi_tiles    list          — `ems_ui/_kpi_row.html` müqaviləsi
    days         list          — [{date, weekday, summary, rows}]
    coverage     list          — açılış üzrə sillabus mövzu əhatəsi
    filter_*     …             — `ems_ui/_filter_bar.html` müqaviləsi
    export_url   str           — CSV
    state_*      …             — boş / əhatəsiz vəziyyət
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar import lessons_log as service

_CTX = "accounts.lessons_log"

#: Sillabus əhatəsi hesablanan maksimum açılış (hər biri 3 sorğu — büdcə qapısı).
COVERAGE_CAP = 4

#: Filtr parametrlərinin ad fəzası (`ems_ui/_filter_bar.html` müqaviləsi).
PREFIX = "ll_"


def _weekday_labels() -> tuple:
    """Həftə günü adları — MODUL SƏVİYYƏSİNDƏ hesablanmır.

    Modul-səviyyəli ``pgettext`` çağırışı həm dili idxal anına dondurur, həm də
    i18n kataloq qapısı üçün görünməz olur (layihə yaddaşı: «module-level
    pgettext ctx invisible to i18n gate»).
    """
    return (
        pgettext(_CTX, "Bazar ertəsi"),
        pgettext(_CTX, "Çərşənbə axşamı"),
        pgettext(_CTX, "Çərşənbə"),
        pgettext(_CTX, "Cümə axşamı"),
        pgettext(_CTX, "Cümə"),
        pgettext(_CTX, "Şənbə"),
        pgettext(_CTX, "Bazar"),
    )


def _param(request, name: str, default: str = "") -> str:
    return (request.GET.get(PREFIX + name) or default).strip()[:80]


def _kpi(label, value, *, unit="", note="", tone=""):
    return {"label": label, "value": value, "unit": unit, "note": note, "tone": tone}


def _empty_state(section, title, body):
    section["state_kind"] = "empty"
    section["state_title"] = title
    section["state_body"] = body


def build_lessons_log_section(request, section, *, active_organization, allowed_sections, active_section):
    """`lessons_log_section` sözlüyünü yerində doldurur."""
    if "lessons-log" not in allowed_sections or active_section != "lessons-log":
        return section
    if active_organization is None:
        section["has_access"] = False
        _empty_state(
            section,
            pgettext(_CTX, "Aktiv təşkilat konteksti yoxdur"),
            pgettext(_CTX, "Təşkilat seçin və ya administratora müraciət edin."),
        )
        return section

    from apps.registrar import schedule as schedule_service

    supervisor = service.is_supervisor(request.user, active_organization)
    section["has_access"] = True
    section["is_supervisor"] = supervisor

    period_view = schedule_service.resolve_display_period(active_organization, requested=_param(request, "period"))
    period = period_view["period"]

    window = service.resolve_range(
        key=_param(request, "range", service.RANGE_SEMESTER),
        start_raw=_param(request, "from"),
        end_raw=_param(request, "to"),
        period=period,
    )

    lessons = service.scoped_lessons(request.user, active_organization, supervisor=supervisor)
    lessons = lessons.filter(date__gte=window["start"], date__lte=window["end"])
    # SEMESTR FİLTRİ yalnız İSTƏNİLƏNDƏ tətbiq olunur.  «Semestr» dövrü onsuz da
    # semestrin tarixlərindən doğur; «Bu ay» / «İl» / «Seçilmiş aralıq» isə
    # TARİX aralığıdır — ora gizli semestr filtri qoysaq istifadəçi seçdiyi
    # aralıqda dərs görməyib boş ekran alır (canlı QA-da ölçüldü).
    period_filter = period if (_param(request, "period") or window["key"] == service.RANGE_SEMESTER) else None
    if period_filter is not None:
        lessons = lessons.filter(offering__period=period_filter)

    # ── Filtrlər (draft ≠ applied — `EMSFilterBar` URL-ə yazır) ──────────────
    search = _param(request, "q")
    offering_id = _param(request, "offering")
    kind = _param(request, "kind")
    group = _param(request, "group")
    teacher_id = _param(request, "teacher") if supervisor else ""
    only_flagged = _param(request, "flagged") == "1"

    if search:
        from django.db.models import Q

        lessons = lessons.filter(
            Q(topic__icontains=search)
            | Q(offering__subject__name__icontains=search)
            | Q(offering__subject__code__icontains=search)
            | Q(offering__group__name__icontains=search)
        )
    if offering_id:
        lessons = lessons.filter(offering_id=offering_id)
    if kind:
        lessons = lessons.filter(kind=kind)
    if group:
        lessons = lessons.filter(offering__group__name=group)
    if teacher_id:
        from django.db.models import Q

        lessons = lessons.filter(
            Q(instructor_id=teacher_id) | Q(instructor__isnull=True, offering__instructor=teacher_id)
        )

    totals = service.range_totals(lessons)
    rows = service.build_rows(lessons)
    if only_flagged:
        rows = [row for row in rows if row["note"] != service.NOTE_ON_TIME]

    section.update(
        {
            "range": {
                "key": window["key"],
                "start": window["start"],
                "end": window["end"],
                "chips": [
                    {"key": key, "label": label, "selected": key == window["key"]}
                    for key, label in service.RANGE_LABELS
                ],
                "from": window["start"].isoformat(),
                "to": window["end"].isoformat(),
            },
            "period": period,
            "totals": totals,
            "rows": rows,
            "days": _group_by_day(rows),
            "row_cap": service.ROW_CAP,
            "has_more": totals["lessons"] > service.ROW_CAP,
            "only_flagged": only_flagged,
            "prefix": PREFIX,
        }
    )
    section["kpi_tiles"] = _kpi_tiles(totals)
    section["coverage"] = _coverage(lessons, totals)
    section["filters"] = _filter_fields(
        request,
        lessons_all=service.scoped_lessons(request.user, active_organization, supervisor=supervisor),
        period=period_filter,
        period_view=period_view,
        supervisor=supervisor,
        values={
            "q": search,
            "offering": offering_id,
            "kind": kind,
            "group": group,
            "teacher": teacher_id,
            "range": window["key"],
        },
    )
    section["export_url"] = "%s?%s" % (
        reverse("registrar:lessons_log_csv"),
        request.GET.urlencode(),
    )
    section["journal_list_url"] = reverse("registrar:journal_list")
    section["header_subtitle"] = (
        pgettext(
            _CTX,
            "Kafedranın müəllimləri hansı dərsi, hansı qrupa, hansı mövzu ilə keçib. Jurnalı "
            "vaxtında doldurulmayan dərslər ayrıca işarələnir.",
        )
        if supervisor
        else pgettext(
            _CTX,
            "Keçdiyiniz dərslərin qeydi — hansı qrupa, hansı mövzunu, neçə saat. Dövrü dəyişib "
            "istənilən aralığa baxa bilərsiniz.",
        )
    )
    section["header_note"] = "%s — %s" % (window["start"].isoformat(), window["end"].isoformat())

    if not rows:
        _empty_state(
            section,
            pgettext(_CTX, "Seçilmiş dövrdə dərs qeydi yoxdur"),
            pgettext(_CTX, "Dövrü genişləndirin və ya filtrləri sıfırlayın."),
        )
    return section


def _group_by_day(rows) -> list:
    weekdays = _weekday_labels()
    days: list = []
    index: dict = {}
    for row in rows:
        key = row["date"]
        bucket = index.get(key)
        if bucket is None:
            bucket = {
                "date": key,
                "weekday": weekdays[key.weekday()],
                "rows": [],
                "lessons": 0,
                "hours": 0,
            }
            index[key] = bucket
            days.append(bucket)
        bucket["rows"].append(row)
        bucket["lessons"] += 1
        bucket["hours"] += row["hours"]
    return days


def _kpi_tiles(totals) -> list:
    return [
        _kpi(
            pgettext(_CTX, "Keçilmiş dərs"),
            totals["lessons"],
            note=pgettext(_CTX, "seçilmiş dövrdə"),
        ),
        _kpi(
            pgettext(_CTX, "Auditoriya saatı"),
            totals["hours"],
            unit=pgettext(_CTX, "saat"),
            note=pgettext(_CTX, "akademik saat cəmi"),
            tone="primary",
        ),
        _kpi(
            pgettext(_CTX, "Orta iştirak"),
            "%s%%" % totals["attendance_rate"],
            note=pgettext(_CTX, "dərsə gələn tələbə payı"),
        ),
        _kpi(
            pgettext(_CTX, "Jurnalı boş dərs"),
            totals["empty"],
            note=(
                pgettext(_CTX, "mövzu və qiymət yazılmayıb") if totals["empty"] else pgettext(_CTX, "hamısı doldurulub")
            ),
            tone="danger" if totals["empty"] else "",
        ),
        _kpi(
            pgettext(_CTX, "Gec yazılan qeyd"),
            totals["late"],
            note=(pgettext(_CTX, "dərsdən 48 saat sonra") if totals["late"] else pgettext(_CTX, "gecikmə yoxdur")),
            tone="warning" if totals["late"] else "",
        ),
    ]


def _coverage(lessons, totals) -> list:
    """Açılış üzrə sillabus mövzu əhatəsi (ən çox dərsi olan `COVERAGE_CAP` açılış)."""
    if not totals["lessons"]:
        return []
    summary = service.offering_totals(lessons)
    summary = sorted(summary, key=lambda row: row["lessons"], reverse=True)[:COVERAGE_CAP]
    if not summary:
        return []
    offering_ids = [row["offering_id"] for row in summary]
    held: dict = {}
    for offering_id, topic in lessons.filter(offering_id__in=offering_ids).values_list("offering_id", "topic"):
        held.setdefault(offering_id, set()).add((topic or "").strip())

    from apps.registrar.journal_policy import syllabus_gate
    from apps.registrar.models import CourseOffering

    offerings = {
        offering.id: offering
        for offering in CourseOffering.objects.filter(id__in=offering_ids).select_related(
            "subject", "group", "period", "organization"
        )
    }
    out = []
    for row in summary:
        offering = offerings.get(row["offering_id"])
        if offering is None:
            continue
        stats = service.coverage_for_offering(offering, held_topics=held.get(offering.id, set()))
        gate = syllabus_gate(offering)
        out.append(
            {
                "offering_id": str(offering.id),
                "subject_code": row["offering__subject__code"] or "",
                "subject_name": row["offering__subject__name"] or "",
                "group": row["offering__group__name"] or "",
                "lessons": row["lessons"],
                "hours": int(row["hours"] or 0),
                "journal_url": reverse("registrar:journal_detail", args=[offering.id]),
                "can_add_lesson": not gate["locked"],
                "lock_title": gate["title"],
                "lock_message": gate["message"],
                "lock_action_label": gate["action_label"],
                "lock_action_url": gate["action_url"],
                **stats,
            }
        )
    return out


def _filter_fields(request, *, lessons_all, period, period_view, supervisor, values) -> dict:
    """`ems_ui/_filter_bar.html` sahələri — seçicilər TƏK aqreqat sorğudan."""
    from apps.registrar.models import LessonKind

    scoped = lessons_all
    if period is not None:
        scoped = scoped.filter(offering__period=period)
    options = list(
        scoped.values_list(
            "offering_id", "offering__subject__code", "offering__subject__name", "offering__group__name"
        ).distinct()[:200]
    )
    offering_options = [{"value": "", "label": pgettext(_CTX, "Bütün fənlər")}]
    group_names = []
    for offering_id, code, name, group_name in options:
        offering_options.append(
            {"value": str(offering_id), "label": "%s · %s — %s" % (code or "", name or "", group_name or "")}
        )
        if group_name and group_name not in group_names:
            group_names.append(group_name)

    fields = [
        {
            "name": PREFIX + "q",
            "label": pgettext(_CTX, "Axtarış"),
            "kind": "search",
            "value": values["q"],
            "placeholder": pgettext(_CTX, "Mövzu, fənn və ya qrup axtar"),
            "wide": True,
        },
        {
            "name": PREFIX + "range",
            "label": pgettext(_CTX, "Dövr"),
            "kind": "select",
            "value": values["range"],
            "options": [{"value": key, "label": label} for key, label in service.RANGE_LABELS],
        },
        {
            "name": PREFIX + "offering",
            "label": pgettext(_CTX, "Fənn"),
            "kind": "select",
            "value": values["offering"],
            "options": offering_options,
        },
        {
            "name": PREFIX + "group",
            "label": pgettext(_CTX, "Qrup"),
            "kind": "select",
            "value": values["group"],
            "options": [{"value": "", "label": pgettext(_CTX, "Bütün qruplar")}]
            + [{"value": name, "label": name} for name in group_names],
        },
        {
            "name": PREFIX + "kind",
            "label": pgettext(_CTX, "Dərsin tipi"),
            "kind": "select",
            "value": values["kind"],
            "options": [{"value": "", "label": pgettext(_CTX, "Bütün tiplər")}]
            + [{"value": key, "label": label} for key, label in LessonKind.choices],
        },
    ]
    if period_view["choices"]:
        fields.append(
            {
                "name": PREFIX + "period",
                "label": pgettext(_CTX, "Semestr"),
                "kind": "select",
                "value": period_view["selected_id"] or "",
                "options": [{"value": str(item["id"]), "label": item["label"]} for item in period_view["choices"]],
            }
        )
    if supervisor:
        teachers = []
        seen = set()
        for teacher_id, first, last, username in scoped.values_list(
            "offering__instructor_id",
            "offering__instructor__first_name",
            "offering__instructor__last_name",
            "offering__instructor__username",
        ).distinct()[:200]:
            if not teacher_id or teacher_id in seen:
                continue
            seen.add(teacher_id)
            label = ("%s %s" % (first or "", last or "")).strip() or username or str(teacher_id)
            teachers.append({"value": str(teacher_id), "label": label})
        fields.append(
            {
                "name": PREFIX + "teacher",
                "label": pgettext(_CTX, "Müəllim"),
                "kind": "select",
                "value": values["teacher"],
                "options": [{"value": "", "label": pgettext(_CTX, "Bütün müəllimlər")}] + teachers,
            }
        )
    return {"fields": fields, "section": "lessons-log", "prefix": PREFIX}


__all__ = ["COVERAGE_CAP", "PREFIX", "build_lessons_log_section"]
