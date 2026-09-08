"""Ekran 21 «Keçilmiş dərslər» — kabinet bölməsi (`lessons-log`).

GLUE qatı: domen məntiqi ``apps.registrar.lessons_log``-dadır, bura yalnız
kontekst yığımı düşür (mövcud `teaching_office.py` naxışı).

SCOPE (README §8/8): müəllim YALNIZ öz dərslərini görür; nəzarət açarı
(``journal.roster`` — kafedra müdiri / dekanlıq / RİM, ``journal.lessons_unit``
— laborant) daşıyan aktor öz alt-ağacını görür və «Müəllim» filtri ona AÇILIR.
Əhatəsiz aktor boş vəziyyət alır.

FİLTR PANELİ (sahib, 2026-09-08): «Tətbiq et» YOXDUR — avto rejim (debounce +
skeleton); select-lər Bootstrap tərzli, uzun siyahılarda daxili axtarış;
tədris ili + semestr fəsli (Payız/Yaz/Yay); başlanğıc/son tarix; təhsil forması
(əyani/qiyabi). BOŞ dəyər = default (cari semestr), «hamısı» ayrıca `all`
dəyəridir — ona görə «Sıfırla» hər zaman cari semestrə qayıdır.

CONTEXT MÜQAVİLƏSİ (`lessons_log_section`)
    has_access   bool          — aktiv təşkilat konteksti var
    is_supervisor bool         — nəzarət görünüşü (müəllim filtri açıqdır)
    range        dict          — {key, start, end, chips}
    kpi_tiles    list          — `ems_ui/_kpi_row.html` müqaviləsi
    days         list          — [{date, weekday, summary, rows}]
    filters      dict          — {fields, applied} `ems_ui/_filter_bar.html` müqaviləsi
    export_url   str           — CSV
    state_*      …             — boş / əhatəsiz vəziyyət
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar import lessons_log as service

_CTX = "accounts.lessons_log"

#: Filtr parametrlərinin ad fəzası (`ems_ui/_filter_bar.html` müqaviləsi).
PREFIX = "ll_"

#: Seçici siyahılarının tavanı (fənn / qrup / müəllim) — menyunun daxili axtarışı var.
OPTION_CAP = 300


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

    legacy_period = _param(request, "period")
    period_view = schedule_service.resolve_display_period(active_organization, requested=legacy_period)
    current = period_view["period"]

    selection = service.resolve_selection(
        active_organization,
        current=current,
        year=_param(request, "year"),
        season=_param(request, "season"),
        legacy_period=legacy_period,
        range_key=_param(request, "range", service.RANGE_SEMESTER),
        start_raw=_param(request, "from"),
        end_raw=_param(request, "to"),
    )
    window = selection["window"]

    lessons_all = service.scoped_lessons(request.user, active_organization, supervisor=supervisor)
    lessons = lessons_all.filter(date__gte=window["start"], date__lte=window["end"])
    if selection["apply_period_filter"]:
        lessons = lessons.filter(offering__period__in=selection["periods"])

    values = {
        "q": _param(request, "q"),
        "offering": _param(request, "offering"),
        "kind": _param(request, "kind"),
        "group": _param(request, "group"),
        "teacher": _param(request, "teacher") if supervisor else "",
        "form": _param(request, "form"),
        "range": window["key"],
        "year": selection["year"],
        "season": selection["season"],
    }
    only_flagged = _param(request, "flagged") == "1"
    lessons = service.apply_filters(
        lessons,
        q=values["q"],
        offering=values["offering"],
        kind=values["kind"],
        group=values["group"],
        teacher=values["teacher"],
        form=values["form"],
        supervisor=supervisor,
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
            "period": current,
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
    # Seçici siyahıları SEÇİLMİŞ dövrlərə görə daralır (yoxsa bütün əhatə).
    option_source = lessons_all
    if selection["periods"] is not None:
        option_source = option_source.filter(offering__period__in=selection["periods"])
    section["filters"] = _filter_fields(
        option_source,
        selection=selection,
        current=current,
        supervisor=supervisor,
        values=values,
    )
    section["export_url"] = "%s?%s" % (
        reverse("registrar:lessons_log_csv"),
        request.GET.urlencode(),
    )
    section["journal_list_url"] = reverse("registrar:journal_list")
    section["header_subtitle"] = (
        pgettext(
            _CTX,
            "Əhatənizdəki müəllimlər hansı dərsi, hansı qrupa, hansı mövzu ilə keçib. Jurnalı "
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


def _filter_fields(option_source, *, selection, current, supervisor, values) -> dict:
    """`ems_ui/_filter_bar.html` sahələri — seçicilər TƏK aqreqat sorğudan.

    Hər select-in `default`-u var: filtr çipinin «×»-i və «Sıfırla» ora qayıdır
    (index-0 seçimə deyil). Uzun siyahılar `searchable` — menyuda axtarış sətri.
    """
    from django.apps import apps as django_apps

    from apps.registrar.models import LessonKind

    academic_period = django_apps.get_model("organizations", "AcademicPeriod")

    options = list(
        option_source.values_list(
            "offering_id", "offering__subject__code", "offering__subject__name", "offering__group__name"
        ).distinct()[:OPTION_CAP]
    )
    offering_options = [{"value": "", "label": pgettext(_CTX, "Bütün fənlər")}]
    offering_labels: dict = {}
    group_names: list = []
    for offering_id, code, name, group_name in options:
        label = "%s · %s — %s" % (code or "", name or "", group_name or "")
        offering_options.append({"value": str(offering_id), "label": label})
        offering_labels[str(offering_id)] = label
        if group_name and group_name not in group_names:
            group_names.append(group_name)
    group_names.sort(key=str.casefold)

    current_year = getattr(current, "academic_year", "") or ""
    current_season = service.season_of(current) if current is not None else ""
    years = service.year_options(selection["catalog"])
    all_years = pgettext(_CTX, "Bütün illər")
    all_seasons = pgettext(_CTX, "Bütün semestrlər")
    season_labels = {key: str(label) for key, label in service.SEASON_LABELS}
    form_options = service.education_form_options()
    kind_labels = {key: str(label) for key, label in LessonKind.choices}
    range_labels = {key: str(label) for key, label in service.RANGE_LABELS}

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
            "name": PREFIX + "year",
            "label": pgettext(_CTX, "Tədris ili"),
            "kind": "select",
            "value": values["year"],
            "default": current_year or service.ALL,
            "searchable": len(years) > 8,
            "options": years + [{"value": service.ALL, "label": all_years}],
        },
        {
            "name": PREFIX + "season",
            "label": pgettext(_CTX, "Semestr"),
            "kind": "select",
            "value": values["season"],
            "default": current_season or service.ALL,
            "options": [{"value": key, "label": label} for key, label in service.SEASON_LABELS]
            + [{"value": service.ALL, "label": all_seasons}],
        },
        {
            "name": PREFIX + "range",
            "label": pgettext(_CTX, "Tarix aralığı"),
            "kind": "select",
            "value": values["range"],
            "default": service.RANGE_SEMESTER,
            "options": [{"value": key, "label": label} for key, label in service.RANGE_LABELS],
        },
        {
            "name": PREFIX + "from",
            "label": pgettext(_CTX, "Başlanğıc"),
            "kind": "date",
            "value": selection["window"]["start"].isoformat(),
            "range_select": PREFIX + "range",
            "range_custom": service.RANGE_CUSTOM,
        },
        {
            "name": PREFIX + "to",
            "label": pgettext(_CTX, "Son"),
            "kind": "date",
            "value": selection["window"]["end"].isoformat(),
            "range_select": PREFIX + "range",
            "range_custom": service.RANGE_CUSTOM,
        },
        {
            "name": PREFIX + "form",
            "label": pgettext(_CTX, "Təhsil forması"),
            "kind": "select",
            "value": values["form"],
            "default": "",
            "options": [{"value": "", "label": pgettext(_CTX, "Hamısı")}] + form_options,
        },
        {
            "name": PREFIX + "offering",
            "label": pgettext(_CTX, "Fənn"),
            "kind": "select",
            "value": values["offering"],
            "default": "",
            "searchable": True,
            "wide": True,
            "options": offering_options,
        },
        {
            "name": PREFIX + "group",
            "label": pgettext(_CTX, "Qrup"),
            "kind": "select",
            "value": values["group"],
            "default": "",
            "searchable": len(group_names) > 8,
            "options": [{"value": "", "label": pgettext(_CTX, "Bütün qruplar")}]
            + [{"value": name, "label": name} for name in group_names],
        },
        {
            "name": PREFIX + "kind",
            "label": pgettext(_CTX, "Dərsin tipi"),
            "kind": "select",
            "value": values["kind"],
            "default": "",
            "options": [{"value": "", "label": pgettext(_CTX, "Bütün tiplər")}]
            + [{"value": key, "label": label} for key, label in LessonKind.choices],
        },
    ]
    teacher_labels: dict = {}
    if supervisor:
        teachers = []
        for teacher_id, first, last, username in (
            option_source.exclude(offering__instructor__isnull=True)
            .values_list(
                "offering__instructor_id",
                "offering__instructor__first_name",
                "offering__instructor__last_name",
                "offering__instructor__username",
            )
            .distinct()[:OPTION_CAP]
        ):
            key = str(teacher_id)
            if key in teacher_labels:
                continue
            label = ("%s %s" % (first or "", last or "")).strip() or username or key
            teacher_labels[key] = label
            teachers.append({"value": key, "label": label})
        teachers.sort(key=lambda item: item["label"].casefold())
        fields.append(
            {
                "name": PREFIX + "teacher",
                "label": pgettext(_CTX, "Müəllim"),
                "kind": "select",
                "value": values["teacher"],
                "default": "",
                "searchable": True,
                "options": [{"value": "", "label": pgettext(_CTX, "Bütün müəllimlər")}] + teachers,
            }
        )

    # Tətbiq olunmuş (default olmayan) filtrlər — çip kimi, «×» ilə geri qaytarılır.
    applied = []
    if values["year"] != (current_year or service.ALL):
        applied.append(
            {
                "name": PREFIX + "year",
                "label": pgettext(_CTX, "Tədris ili"),
                "value_label": (
                    all_years if values["year"] == service.ALL else academic_period.format_year(values["year"])
                ),
            }
        )
    if values["season"] != (current_season or service.ALL):
        applied.append(
            {
                "name": PREFIX + "season",
                "label": pgettext(_CTX, "Semestr"),
                "value_label": (
                    all_seasons
                    if values["season"] == service.ALL
                    else season_labels.get(values["season"], values["season"])
                ),
            }
        )
    if values["range"] != service.RANGE_SEMESTER:
        applied.append(
            {
                "name": PREFIX + "range",
                "label": pgettext(_CTX, "Tarix aralığı"),
                "value_label": "%s (%s — %s)"
                % (
                    range_labels.get(values["range"], values["range"]),
                    selection["window"]["start"].isoformat(),
                    selection["window"]["end"].isoformat(),
                ),
            }
        )
    for key, label, value_label in (
        (
            "form",
            pgettext(_CTX, "Təhsil forması"),
            {o["value"]: o["label"] for o in form_options}.get(values["form"], ""),
        ),
        ("offering", pgettext(_CTX, "Fənn"), offering_labels.get(values["offering"], values["offering"])),
        ("group", pgettext(_CTX, "Qrup"), values["group"]),
        ("kind", pgettext(_CTX, "Dərsin tipi"), kind_labels.get(values["kind"], values["kind"])),
        ("teacher", pgettext(_CTX, "Müəllim"), teacher_labels.get(values["teacher"], values["teacher"])),
        ("q", pgettext(_CTX, "Axtarış"), values["q"]),
    ):
        if values[key]:
            applied.append({"name": PREFIX + key, "label": label, "value_label": value_label or values[key]})

    return {"fields": fields, "applied": applied, "section": "lessons-log", "prefix": PREFIX}


__all__ = ["OPTION_CAP", "PREFIX", "build_lessons_log_section"]
