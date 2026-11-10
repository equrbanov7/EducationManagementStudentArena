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

from apps.registrar.public import lessons_log as service

_CTX = "accounts.lessons_log"

#: Filtr parametrlərinin ad fəzası (`ems_ui/_filter_bar.html` müqaviləsi).
PREFIX = "ll_"

#: Seçici siyahılarının tavanı (fənn / qrup / müəllim) — menyunun daxili axtarışı var.
OPTION_CAP = 300

#: KPI kartlarının açarları (`data-ems-kpi-key`) — tənbəl uc kartı bu açarla tapır.
KPI_KEYS = ("lessons", "hours", "attendance", "empty", "late")

#: «Daha çox süzgəc» altına yığılan (ikinci dərəcəli) sahələr — əsas sırada axtarış, aralıq, müəllim, fənn, qrup qalır.
SECONDARY_FIELDS = ("year", "season", "from", "to", "form", "faculty", "kafedra", "kind")


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

    # Sorğunun TƏK həlli (əhatə → dövr → fakültə/kafedra → süzgəclər) — tənbəl uclar və müəllim cədvəli ilə eyni.
    ctx = service.resolve_request(request, active_organization)
    supervisor = ctx["supervisor"]
    section["has_access"] = True
    section["is_supervisor"] = supervisor
    selection, window, current = ctx["selection"], ctx["window"], ctx["current"]
    values, units, lessons = ctx["values"], ctx["units"], ctx["lessons"]
    only_flagged = ctx["only_flagged"]

    # PERF 2026-11-11 (sahib: «girəndə bir az yavaşlama olur»): ilk cavab ağır hesabı GÖZLƏMİR.
    # * KPI: dərs sayı + saat yüngül aqreqatdır; iştirak / boş / gec (xana cədvəli üzərində aqreqat) keşdədirsə
    #   dərhal, yoxdursa tənbəl ucdan (`lessons_log_insights`) dolur.
    # * «Cədvəldə var, qeydə alınmayıb»: keşdədirsə dərhal, yoxdursa eyni tənbəl ucdan.
    # * Gün siyahısı: ilk səhifə (`PAGE_SIZE` dərs), qalanı «Daha çox göstər» ilə; gün başlığı günün TAM cəmidir.
    # * Seçici siyahıları (fakültə / kafedra / fənn / qrup / müəllim) 120 s keşlidir (`cached_by_query`).
    full_totals = service.cached_range_totals(lessons)
    totals = full_totals or service.quick_totals(lessons)
    page = service.page_rows(lessons)
    rows = page["rows"]
    unrecorded = service.unrecorded_for(request, active_organization, ctx, cached_only=True)
    section["unrecorded"] = unrecorded
    section["insights_pending"] = full_totals is None or unrecorded is None
    section["unrecorded_pending"] = unrecorded is None
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
            "days": _group_by_day(rows, page["day_totals"]),
            "page_size": service.PAGE_SIZE,
            "next_offset": page["next_offset"],
            "has_more": page["next_offset"] is not None,
            "only_flagged": only_flagged,
            "prefix": PREFIX,
        }
    )
    section["kpi_tiles"] = _kpi_tiles(totals, pending=full_totals is None)
    section["filters"] = _filter_fields(
        # Kaskad: fənn / qrup / müəllim siyahıları seçilmiş fakültə və kafedraya görə daralır.
        service.apply_filters(ctx["option_source"], **ctx["unit_filters"]),
        selection=selection,
        current=current,
        supervisor=supervisor,
        values=values,
        units=units,
    )
    # İxrac və AJAX ucları bölmə ilə EYNİ effektiv filtrləri daşıyır (kaskadda atılmış kafedra URL-də qalmasın).
    export_params = request.GET.copy()
    for key in ("faculty", "kafedra"):
        if values[key]:
            export_params[PREFIX + key] = values[key]
        else:
            export_params.pop(PREFIX + key, None)
    for key in ("section", PREFIX + "offset", "row"):
        export_params.pop(key, None)
    query = export_params.urlencode()
    section["export_url"] = "%s?%s" % (reverse("registrar:lessons_log_csv"), query)
    section["insights_url"] = "%s?%s" % (reverse("accounts:lessons_log_insights"), query)
    section["rows_url"] = "%s?%s" % (reverse("accounts:lessons_log_rows"), query)
    # «Cədvəl formasında bax» (sahib 2026-11-11): nəzarətçidə YALNIZ müəllim seçiləndə; müəllim öz cədvəlini görür.
    section["teacher_table"] = {
        "show": bool(values["teacher"]) if supervisor else True,
        "table_url": "%s?%s" % (reverse("registrar:lessons_log_teacher_table"), query),
        "lessons_url": "%s?%s" % (reverse("registrar:lessons_log_teacher_lessons"), query),
        "xlsx_url": "%s?%s" % (reverse("registrar:lessons_log_teacher_xlsx"), query),
    }
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
    section["header_note"] = "%s — %s" % (window["start"].strftime("%d.%m.%Y"), window["end"].strftime("%d.%m.%Y"))

    if not rows:
        _empty_state(
            section,
            pgettext(_CTX, "Seçilmiş dövrdə dərs qeydi yoxdur"),
            pgettext(_CTX, "Dövrü genişləndirin və ya filtrləri sıfırlayın."),
        )
    return section


def _group_by_day(rows, day_totals=None) -> list:
    """Sətirləri günə görə qruplaşdırır. ``day_totals`` (`lessons_log_pages.day_totals`) verilibsə gün başlığının
    «N dərs · M saat»ı günün TAM cəmidir — səhifə günü yarıda kəsə bilər."""
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
    for bucket in days:
        full = (day_totals or {}).get(bucket["date"])
        if full:
            bucket["lessons"], bucket["hours"] = full["lessons"], full["hours"]
    return days


def _kpi_tiles(totals, *, pending: bool = False) -> list:
    """KPI kartları. ``pending`` — ağır aqreqat hələ hesablanmayıb: iştirak / boş / gec kartları skelet kimi
    gəlir və ``lessons_log.js`` onları tənbəl ucun cavabı ilə (``key`` üzrə) doldurur."""
    tiles = [
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
    ]
    if pending:
        tiles += [
            _kpi(pgettext(_CTX, "Orta iştirak"), "—", note=pgettext(_CTX, "hesablanır…"), tone="skeleton"),
            _kpi(pgettext(_CTX, "Jurnalı boş dərs"), "—", note=pgettext(_CTX, "hesablanır…"), tone="skeleton"),
            _kpi(pgettext(_CTX, "Gec yazılan qeyd"), "—", note=pgettext(_CTX, "hesablanır…"), tone="skeleton"),
        ]
    else:
        tiles += [
            _kpi(
                pgettext(_CTX, "Orta iştirak"),
                "%s%%" % totals["attendance_rate"],
                note=pgettext(_CTX, "dərsə gələn tələbə payı"),
            ),
            _kpi(
                pgettext(_CTX, "Jurnalı boş dərs"),
                totals["empty"],
                note=(
                    pgettext(_CTX, "mövzu və qiymət yazılmayıb")
                    if totals["empty"]
                    else pgettext(_CTX, "hamısı doldurulub")
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
    for tile, key in zip(tiles, KPI_KEYS):
        tile["key"] = key
    return tiles


def _unit_field(name, label, all_label, value, options, *, locked=False) -> dict:
    """Fakültə / Kafedra seçicisi — layihə komponenti (bootstrap select + menyuda axtarış).

    ``locked`` (sahib, 2026-10-14): aktorun əhatəsində TƏK seçim var — dəyər server tərəfindən
    seçilib, sahə göstərilmir (gizli input URL-i ardıcıl saxlayır)."""
    if locked:
        return {"name": PREFIX + name, "label": label, "kind": "hidden", "value": value}
    return {
        "name": PREFIX + name,
        "label": label,
        "kind": "select",
        "value": value,
        "default": "",
        "searchable": True,
        "wide": True,
        "options": [{"value": "", "label": all_label}] + options,
    }


def _filter_fields(option_source, *, selection, current, supervisor, values, units=None) -> dict:
    """`ems_ui/_filter_bar.html` sahələri — seçicilər TƏK aqreqat sorğudan.

    Hər select-in `default`-u var: filtr çipinin «×»-i və «Sıfırla» ora qayıdır
    (index-0 seçimə deyil). Uzun siyahılar `searchable` — menyuda axtarış sətri.
    """
    from django.apps import apps as django_apps

    from apps.registrar.models import LessonKind

    academic_period = django_apps.get_model("organizations", "AcademicPeriod")

    options = service.offering_option_rows(option_source, OPTION_CAP)
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
        _unit_field(
            "faculty",
            pgettext(_CTX, "Fakültə"),
            pgettext(_CTX, "Bütün fakültələr"),
            values.get("faculty", ""),
            (units or {}).get("faculty_options", []),
            locked=bool((units or {}).get("faculty_locked")),
        ),
        _unit_field(
            "kafedra",
            pgettext(_CTX, "Kafedra"),
            pgettext(_CTX, "Bütün kafedralar"),
            values.get("kafedra", ""),
            (units or {}).get("kafedra_options", []),
            locked=bool((units or {}).get("kafedra_locked")),
        ),
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
        teacher_rows = service.teacher_option_rows(option_source, OPTION_CAP)
        for teacher_id, first, last, username in teacher_rows:
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
    unit_labels = {}
    for key in ("faculty", "kafedra"):
        resolved = (units or {}).get(key)
        labels = {o["value"]: o["label"] for o in (units or {}).get(f"{key}_options", [])}
        unit_labels[key] = labels.get(values.get(key, "")) or (resolved.name if resolved is not None else "")
    for key, label, value_label in (
        (
            "form",
            pgettext(_CTX, "Təhsil forması"),
            {o["value"]: o["label"] for o in form_options}.get(values["form"], ""),
        ),
        ("faculty", pgettext(_CTX, "Fakültə"), unit_labels["faculty"]),
        ("kafedra", pgettext(_CTX, "Kafedra"), unit_labels["kafedra"]),
        ("offering", pgettext(_CTX, "Fənn"), offering_labels.get(values["offering"], values["offering"])),
        ("group", pgettext(_CTX, "Qrup"), values["group"]),
        ("kind", pgettext(_CTX, "Dərsin tipi"), kind_labels.get(values["kind"], values["kind"])),
        ("teacher", pgettext(_CTX, "Müəllim"), teacher_labels.get(values["teacher"], values["teacher"])),
        ("q", pgettext(_CTX, "Axtarış"), values["q"]),
    ):
        if values[key] and not (units or {}).get(f"{key}_locked"):
            applied.append({"name": PREFIX + key, "label": label, "value_label": value_label or values[key]})

    # REDİZAYN 2026-11-11 (sahib: «daha səliqəli»): əsas sırada axtarış, müəllim, fənn, qrup, tarix aralığı;
    # qalan sahələr «Daha çox süzgəc» altındadır (ikinci dərəcəli süzgəc tətbiq olunubsa blok açıq gəlir).
    secondary = {PREFIX + name for name in SECONDARY_FIELDS}
    primary_order = {PREFIX + name: index for index, name in enumerate(("q", "teacher", "offering", "group", "range"))}
    for field in fields:
        field["secondary"] = field["name"] in secondary and field["kind"] != "hidden"
    fields.sort(key=lambda field: (field["secondary"], primary_order.get(field["name"], len(primary_order))))
    more_count = sum(1 for chip in applied if chip["name"] in secondary)
    return {
        "fields": fields,
        "applied": applied,
        "section": "lessons-log",
        "prefix": PREFIX,
        "has_more_fields": any(field["secondary"] for field in fields),
        "more_count": more_count,
        "more_open": bool(more_count) or values["range"] == service.RANGE_CUSTOM,
    }


__all__ = ["OPTION_CAP", "PREFIX", "build_lessons_log_section"]
