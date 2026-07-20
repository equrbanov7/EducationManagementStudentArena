"""Profil "kollokvium-windows" bölməsi — İmtahan Mərkəzi bal-yazma pəncərələri.

``section`` dict-ini YERİNDƏ mutasiya edir (exam_rooms pattern-i ilə eyni).
Superadmin cross-org (org seçici); İmtahan Mərkəzi istifadəçisi yalnız aktiv
təşkilatı. Tədris ili + semestr AYRICA seçilir (jurnal kimi); K1/K2/K3 üçün
pəncərə sətirləri + əlavə gün grant-ları göstərilir. Fakültə/kafedra siyahıları
əlavə gün modalı üçündür.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.accounts.views._helpers.formatting import _append_query_params

_K_LABELS = [(0, "K1"), (1, "K2"), (2, "K3")]


def _base_status(window, today):
    """Kabinet üçün org-səviyyə vəziyyət (offering-spesifik əlavə gün nəzərə alınmır)."""
    if window is None:
        return "not-set"
    if not window.is_active:
        return "inactive"
    if today < window.opens_on:
        return "scheduled"
    if today > window.closes_on:
        return "closed"
    return "open"


def _season_label(period):
    """Semestrin fəsil adı (Payız/Yaz/Yay semestri) — başlanğıc ayından.

    Jurnaldakı ``page_contexts._season_label`` qaydası ilə eyni (start_date.month):
    avqust–dekabr → Payız, yanvar–may → Yaz, iyun–iyul → Yay. Sezon ``name``-dən
    parse EDİLMİR — həmişə start_date-dən hesablanır (tenant-konfiqurasiyalı).
    """
    month = period.start_date.month if getattr(period, "start_date", None) else 9
    if month >= 8 or month == 12:
        return "Payız semestri"
    if month <= 5:
        return "Yaz semestri"
    return "Yay semestri"


def _current_semester(periods, today):
    """Bu günə uyğun semestr — jurnal ``page_contexts._current_semester`` güzgüsü.

    Əvvəlcə tarixə düşən period (start_date≤today≤end_date); yoxdursa ay→fəsil
    (sentyabr–yanvar → Payız, fevral–iyun → Yaz, iyul–avqust → Yay) + start_date≤today;
    son çarə ən son period. ``periods`` -start_date sırasında ötürülməlidir.
    """
    if not periods:
        return None
    containing = [p for p in periods if p.start_date <= today <= p.end_date]
    if containing:
        return containing[0]
    month = today.month
    if month >= 9 or month == 1:
        season = "Payız semestri"
    elif month <= 6:
        season = "Yaz semestri"
    else:
        season = "Yay semestri"
    matching = [p for p in periods if _season_label(p) == season and p.start_date <= today]
    return matching[0] if matching else periods[0]


def build_kollokvium_windows_section(
    request, section, *, is_superadmin, active_organization, allowed_sections, active_section
):
    if "kollokvium-windows" not in allowed_sections or active_section != "kollokvium-windows":
        return

    from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
    from apps.registrar.models import KollokviumWindow
    from core.constants import OrgUnitType

    kafedra_types = [OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT]

    # ── Hədəf təşkilat ─────────────────────────────────────────────────────
    if is_superadmin:
        org_options = list(Organization.objects.filter(is_active=True).order_by("name").values("id", "name"))
        selected_org_id = (request.GET.get("win_org") or "").strip()
        selected_org = None
        if selected_org_id:
            selected_org = Organization.objects.filter(pk=selected_org_id).first()
        if selected_org is None and org_options:
            selected_org = Organization.objects.filter(pk=org_options[0]["id"]).first()
    else:
        org_options = []
        selected_org = active_organization

    section["is_superadmin"] = is_superadmin
    section["is_head"] = bool(
        getattr(request.user, "is_superadmin", False)
        or request.user.is_superuser
        or getattr(request.user, "is_exam_center_head", False)
    )
    section["org_options"] = org_options
    section["selected_org"] = selected_org

    if selected_org is None:
        section["years"] = []
        section["selected_year"] = None
        section["periods"] = []
        section["period"] = None
        section["k_rows"] = []
        section["faculties"] = []
        section["departments"] = []
        section["post_next_url"] = _append_query_params(reverse("accounts:profile"), section="kollokvium-windows")
        return

    # ── Tədris ili + semestr seçimi (jurnaldakı kimi AYRICA + avtomatik) ───
    today = timezone.localdate()
    all_periods = list(AcademicPeriod.objects.filter(organization=selected_org).order_by("-start_date"))
    # Hər perioda fəsil adını (Payız/Yaz/Yay) yapışdır — dropdown-da göstərilir.
    for p in all_periods:
        p.season_label = _season_label(p)

    # Fərqli tədris illəri (year_display), -start_date sırasında.
    years = []
    seen_years = set()
    for p in all_periods:
        y = p.year_display
        if y and y not in seen_years:
            seen_years.add(y)
            years.append(y)

    # Bu günə uyğun semestr (jurnal qaydası: tarixə düşən → ay→fəsil).
    # DİQQƏT: jurnal heuristikası semestrlərarası fasilədə BİTMİŞ semestri qaytara
    # bilər (məs. 10 yanvar → "Payız" → payıza bənzər ən son bitmiş dövr). Kabinet
    # üçün belə halda REDAKTƏ OLUNA BİLƏN (cari/gələcək) dövrə üstünlük veririk ki,
    # default görünüş kilidli keçmiş semestr olmasın (staff növbəti dövrü hazırlayır).
    auto_period = _current_semester(all_periods, today)
    default_period = None
    if auto_period is not None and not auto_period.is_past:
        default_period = auto_period
    if default_period is None:
        default_period = next((p for p in all_periods if p.is_current and not p.is_past), None)
    if default_period is None:
        upcoming = [p for p in all_periods if not p.is_past]
        if upcoming:
            default_period = min(upcoming, key=lambda p: p.start_date)  # ən yaxın cari/gələcək
    if default_period is None:
        default_period = auto_period  # hamısı keçmişdir → ən son bitmiş (read-only baxış)

    # Seçilmiş tədris ili: ?win_year → DEFAULT (redaktə oluna bilən) dövrün ili → ən son il.
    requested_year = (request.GET.get("win_year") or "").strip()
    selected_year = None
    if requested_year and requested_year in seen_years:
        selected_year = requested_year
    elif default_period is not None:
        selected_year = default_period.year_display
    elif years:
        selected_year = years[0]

    # O ilə aid semestrlər.
    periods_in_year = [p for p in all_periods if p.year_display == selected_year]

    # Eyni ildə eyni fəsil adı təkrarlanırsa (nadir hal: eyni sezonlu 2 dövr),
    # dropdown-da fərqləndirmək üçün ad əlavə olunsun.
    season_counts = {}
    for p in periods_in_year:
        season_counts[p.season_label] = season_counts.get(p.season_label, 0) + 1
    for p in periods_in_year:
        p.needs_disambig = season_counts.get(p.season_label, 0) > 1

    # Seçilmiş semestr: ?period → DEFAULT (bu ildədirsə) → ilin cari/qeyri-keçmiş → ilkin.
    requested_period = (request.GET.get("period") or "").strip()
    period = None
    if requested_period:
        period = next((p for p in periods_in_year if str(p.id) == requested_period), None)
    if period is None and default_period is not None and default_period.year_display == selected_year:
        period = default_period
    if period is None:
        period = next((p for p in periods_in_year if p.is_current and not p.is_past), None)
    if period is None:
        period = next((p for p in periods_in_year if not p.is_past), None)
    if period is None and periods_in_year:
        period = periods_in_year[0]

    section["years"] = years
    section["selected_year"] = selected_year
    section["periods"] = periods_in_year
    section["period"] = period
    # Keçmiş (bitmiş) semestr üçün UI read-only (server-side də view-də bloklanır).
    section["period_is_past"] = bool(period and period.is_past)
    # Bu təşkilatda ümumiyyətlə cari/gələcək (redaktə oluna bilən) semestr varmı?
    # Yoxdursa default keçmiş semestrə düşür — istifadəçiyə SƏBƏBİ + həlli göstərilir
    # ("cari semestr yoxdur, yeni yarat") deyə ayrıca xəbərdarlıq üçün.
    section["has_editable_period"] = any(not p.is_past for p in all_periods)
    section["post_next_url"] = _append_query_params(
        reverse("accounts:profile"),
        section="kollokvium-windows",
        **({"win_org": str(selected_org.pk)} if (is_superadmin and selected_org) else {}),
        **({"win_year": selected_year} if selected_year else {}),
        **({"period": str(period.id)} if period else {}),
    )

    # ── K1/K2/K3 pəncərə sətirləri (+ əlavə gün grant-ları) ────────────────
    windows = {}
    if period is not None:
        for w in KollokviumWindow.objects.filter(organization=selected_org, period=period).prefetch_related(
            "extra_grants__org_unit"
        ):
            windows[w.k_index] = w

    k_rows = []
    for k_index, label in _K_LABELS:
        window = windows.get(k_index)
        grants = []
        if window is not None:
            for g in window.extra_grants.all():
                grants.append(
                    {
                        "id": g.id,
                        "extra_days": g.extra_days,
                        "scope": g.scope,  # xam dəyər — redaktə modalında öncədən doldurmaq üçün
                        "scope_display": g.get_scope_display(),
                        "org_unit_id": str(g.org_unit_id) if g.org_unit_id else "",
                        "unit_name": g.org_unit.name if g.org_unit_id else "",
                        # Effektiv son tarix bu grant üzrə = bağlanış + əlavə gün.
                        "deadline": (window.closes_on + timedelta(days=g.extra_days)) if window.closes_on else None,
                    }
                )
        k_rows.append(
            {
                "k_index": k_index,
                "label": label,
                "window": window,
                "status": _base_status(window, today),
                "grants": grants,
                # Sıra: K{n} yalnız K{n-1} təyin olunduqdan sonra qoyula bilər.
                "can_set": k_index == 0 or windows.get(k_index - 1) is not None,
            }
        )
    section["k_rows"] = k_rows

    # ── Fakültə / kafedra siyahıları (əlavə gün modalı üçün) ───────────────
    section["faculties"] = list(
        OrgUnit.objects.filter(organization=selected_org, is_active=True, unit_type=OrgUnitType.FACULTY)
        .order_by("name")
        .values("id", "name")
    )
    section["departments"] = list(
        OrgUnit.objects.filter(organization=selected_org, is_active=True, unit_type__in=kafedra_types)
        .order_by("name")
        .values("id", "name")
    )
