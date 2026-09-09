"""«Fənn təhvili» panelinin SÜZGƏC, KPI və seçim siyahıları (server-render qat).

Bölmə 2026-09-09-da SPA-dan `ems_ui` server-render panelinə keçirildi (sahib:
«proses çox aydın olsun, performans kəskin»). Bu modul yalnız EKRAN ELEMENTLƏRİNİ
qurur — qaydalar `apps.registrar.handover*`-dadır və toxunulmur.

Süzgəc parametrləri `th_` ad fəzasındadır (`ems_ui/_filter_bar.html` müqaviləsi).
Tab açarı QƏSDƏN prefiksdən KƏNARDIR (`handover_tab`): «Sıfırla» bütün prefiksli
parametrləri atır, tab isə sıfırlanmamalıdır.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from apps.registrar import handover as handover_read

_CTX = "accounts.handover"

#: Süzgəc parametrlərinin ad fəzası.
PREFIX = "th_"

#: Tab açarı — prefiksdən KƏNAR (bax modul başlığı).
TAB_PARAM = "handover_tab"
TAB_TRANSFER = "transfer"
TAB_HISTORY = "history"

#: Səhifə ölçüləri. Cədvəl 25 sətir: bir ekranda oxunur, aqreqatlar isə onsuz da
#: bütün süzülmüş dəst üzrədir (KPI-lar səhifə ilə dəyişmir).
PAGE_SIZE = 25
HISTORY_PAGE_SIZE = 20

#: Açılan siyahıların tavanı — menyunun öz daxili axtarışı var (bootstrap-select).
OPTION_CAP = 300


def param(request, name: str, default: str = "") -> str:
    return (request.GET.get(PREFIX + name) or default).strip()[:120]


def active_tab(request) -> str:
    return TAB_HISTORY if (request.GET.get(TAB_PARAM) or "").strip() == TAB_HISTORY else TAB_TRANSFER


def filter_values(request) -> dict:
    """Süzgəc sözlüyü — `apps.accounts.views.handover.filters.apply_filters` üçün."""
    return {key: param(request, key) for key in ("q", "teacher", "period", "faculty", "kafedra", "state")}


# ── Açılan siyahılar ─────────────────────────────────────────────────────────


def _option(value, label):
    return {"value": value, "label": label}


def _all_option():
    return _option("", pgettext(_CTX, "Hamısı"))


def source_teacher_options(scoped_queryset, selected: str) -> list:
    """«Kimin fənləri» — əhatədə DƏRSİ OLAN müəllimlər (təkrarsız, tək sorğu).

    Siyahı QƏSDƏN bütün müəllimlərdən deyil, məhz açılışı olanlardan qurulur:
    dekan yalnız öz fakültəsində dərs deyən adamı seçə bilməlidir.
    """
    from django.contrib.auth import get_user_model

    instructor_ids = scoped_queryset.filter(instructor_id__isnull=False).values("instructor_id")
    rows = (
        get_user_model()
        .objects.filter(pk__in=instructor_ids)
        .order_by("last_name", "first_name", "username")
        .values_list("pk", "first_name", "last_name", "username")[:OPTION_CAP]
    )
    options = [_option("", pgettext(_CTX, "Hamısı"))]
    options += [_option(str(pk), _person_label(first, last, username)) for pk, first, last, username in rows]
    options.append(_option("__none__", pgettext(_CTX, "Müəllim təyin edilməyib")))
    if selected and selected not in {option["value"] for option in options}:
        options.append(_option(selected, selected))
    return options


def target_teacher_options(organization, *, blank_label=None) -> list:
    """«Kimə» — bal yaza bilən AKTİV üzvlər.

    Əhatə ilə daraldılMIR (kafedra müdiri fənni başqa kafedranın müəlliminə də
    verə bilər) — `handover.target_queryset` ilə eyni qayda.
    """
    rows = handover_read.target_queryset(organization).values_list("pk", "first_name", "last_name", "username")[
        :OPTION_CAP
    ]
    options = [_option("", blank_label or pgettext(_CTX, "Müəllim seçin…"))]
    options += [_option(str(pk), _person_label(first, last, username)) for pk, first, last, username in rows]
    return options


def _person_label(first, last, username) -> str:
    full = f"{first or ''} {last or ''}".strip()
    return full or str(username or "")


def period_options(organization, selected: str) -> list:
    from django.apps import apps as django_apps

    from apps.accounts.views.handover.policy import period_label

    model = django_apps.get_model("organizations", "AcademicPeriod")
    rows = model.objects.filter(organization=organization).order_by("-start_date")[:60]
    options = [_all_option()]
    for period in rows:
        label = period_label(period)
        if period.is_current:
            label = f"{label} · {pgettext(_CTX, 'cari')}"
        options.append(_option(str(period.pk), label))
    if selected and selected not in {option["value"] for option in options}:
        options.append(_option(selected, selected))
    return options


def unit_options(organization, scope, unit_types, selected: str) -> list:
    """Fakültə / kafedra süzgəci — aktorun əhatəsi daxilində."""
    from django.apps import apps as django_apps

    org_unit = django_apps.get_model("organizations", "OrgUnit")
    queryset = org_unit.objects.filter(organization=organization, is_active=True, unit_type__in=unit_types)
    if not scope.is_org_wide:
        queryset = queryset.filter(scope.unit_subtree_q())
    options = [_all_option()]
    options += [
        _option(str(row["id"]), row["name"]) for row in queryset.order_by("name").values("id", "name")[:OPTION_CAP]
    ]
    if selected and selected not in {option["value"] for option in options}:
        options.append(_option(selected, selected))
    return options


def state_options() -> list:
    return [
        _option("", pgettext(_CTX, "Hamısı")),
        _option("open", pgettext(_CTX, "Yalnız təhvil oluna bilənlər")),
        _option("blocked", pgettext(_CTX, "Yalnız bloklananlar")),
    ]


# ── Filtr paneli ─────────────────────────────────────────────────────────────


def filter_fields(values, *, sources, periods, faculties, kafedras) -> list:
    """`ems_ui/_filter_bar.html` sahələri (hamısı Bootstrap select / axtarış)."""
    return [
        {
            "name": PREFIX + "q",
            "label": pgettext(_CTX, "Axtarış"),
            "kind": "search",
            "value": values["q"],
            "wide": True,
            "placeholder": pgettext(_CTX, "fənn adı, kodu və ya qrup"),
        },
        {
            "name": PREFIX + "teacher",
            "label": pgettext(_CTX, "Hansı müəllimin fənləri?"),
            "kind": "select",
            "options": sources,
            "value": values["teacher"],
            "searchable": True,
        },
        {
            "name": PREFIX + "period",
            "label": pgettext(_CTX, "Semestr"),
            "kind": "select",
            "options": periods,
            "value": values["period"],
            "searchable": True,
        },
        {
            "name": PREFIX + "faculty",
            "label": pgettext(_CTX, "Fakültə"),
            "kind": "select",
            "options": faculties,
            "value": values["faculty"],
            "searchable": True,
        },
        {
            "name": PREFIX + "kafedra",
            "label": pgettext(_CTX, "Kafedra"),
            "kind": "select",
            "options": kafedras,
            "value": values["kafedra"],
            "searchable": True,
        },
        {
            "name": PREFIX + "state",
            "label": pgettext(_CTX, "Vəziyyət"),
            "kind": "select",
            "options": state_options(),
            "value": values["state"],
        },
    ]


# ── KPI + mərhələ zolağı ─────────────────────────────────────────────────────


def kpi_tiles(facets: dict) -> list:
    """Beş kart. Sonuncu ikisi SEÇİMƏ bağlıdır və JS tərəfindən yenilənir
    (`data-ems-kpi-key`) — istifadəçi «nə seçdim, nəyə toxunuram» sualının
    cavabını cədvələ baxmadan görür."""
    return [
        {
            "label": pgettext(_CTX, "Əhatədəki fənn"),
            "value": facets["total"],
            "tone": "accent-primary",
            "note": pgettext(_CTX, "süzgəcə uyğun"),
        },
        {
            "label": pgettext(_CTX, "Təhvil verilə bilər"),
            "value": facets["open"],
            "tone": "accent-success",
            "note": pgettext(_CTX, "bloker yoxdur"),
        },
        {
            "label": pgettext(_CTX, "Təhvil verilə bilməz"),
            "value": facets["blocked"],
            "tone": "accent-warning" if facets["blocked"] else "accent-success",
            "note": blocker_breakdown(facets) or pgettext(_CTX, "hamısı açıqdır"),
        },
        {
            "label": pgettext(_CTX, "Seçilmiş fənn"),
            "value": 0,
            "tone": "accent-primary",
            "key": "selected",
            "note": pgettext(_CTX, "təhvilə hazır"),
        },
        {
            "label": pgettext(_CTX, "Təsirlənən tələbə"),
            "value": 0,
            "tone": "accent-primary",
            "key": "students",
            "note": pgettext(_CTX, "seçilmiş fənlərdə"),
        },
    ]


def blocker_breakdown(facets: dict) -> str:
    """«2 bağlı jurnal · 1 keçmiş semestr» — səbəblərin YIĞCAM sayı.

    Qırmızı mətn divarı əvəzinə bir cümlə: istifadəçi neçəsinin və NİYƏ
    bloklandığını cədvələ enmədən görür (sətirdə səbəb onsuz da yazılır).
    """
    parts = []
    for key, template in (
        ("journal_closed", pgettext(_CTX, "%(n)d bağlı jurnal")),
        ("past_period", pgettext(_CTX, "%(n)d keçmiş semestr")),
        ("offering_inactive", pgettext(_CTX, "%(n)d arxiv açılış")),
        ("actor_is_current_instructor", pgettext(_CTX, "%(n)d öz fənniniz")),
    ):
        count = facets.get(key) or 0
        if count:
            parts.append(template % {"n": count})
    return " · ".join(parts)


def steps(values: dict, facets: dict) -> list:
    """Dörd mərhələ: kimdən → nə → kimə → təsdiq (`ems_ui/_stepper.html`).

    Server yalnız BAŞLANĞIC vəziyyəti verir; seçim dəyişdikcə 2-ci və 3-cü
    mərhələni `teaching_handover.js` yeniləyir.
    """
    picked_source = bool(values.get("teacher"))
    return [
        {
            "label": pgettext(_CTX, "Kimin fənləri"),
            "note": (
                pgettext(_CTX, "müəllim seçilib")
                if picked_source
                else pgettext(_CTX, "boş = səlahiyyət sahənizdəki bütün fənlər")
            ),
            "state": "done" if picked_source else "current",
        },
        {
            "label": pgettext(_CTX, "Təhvil veriləcək fənləri seçin"),
            "note": pgettext(_CTX, "%(n)d fənn təhvilə açıqdır") % {"n": facets["open"]},
            "state": "current" if picked_source else "todo",
        },
        {
            "label": pgettext(_CTX, "Yeni müəllimi təyin edin"),
            "note": pgettext(_CTX, "təsdiq pəncərəsində seçilir"),
            "state": "todo",
        },
        {
            "label": pgettext(_CTX, "Təsdiqləyin"),
            "note": pgettext(_CTX, "bal və davamiyyət dəyişmir"),
            "state": "todo",
        },
    ]


__all__ = [
    "HISTORY_PAGE_SIZE",
    "OPTION_CAP",
    "PAGE_SIZE",
    "PREFIX",
    "TAB_HISTORY",
    "TAB_PARAM",
    "TAB_TRANSFER",
    "active_tab",
    "blocker_breakdown",
    "filter_fields",
    "filter_values",
    "kpi_tiles",
    "param",
    "period_options",
    "source_teacher_options",
    "state_options",
    "steps",
    "target_teacher_options",
    "unit_options",
]
