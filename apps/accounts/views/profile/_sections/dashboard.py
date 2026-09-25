"""Profil «dashboard» bölməsi — kabinetin ANA SƏHİFƏSİ («Ana səhifə»).

NİYƏ VAR (FAZA 21 QA tapıntısı): hər rol kabinetə `profile-info` ilə girirdi —
yəni istifadəçi ilk gördüyü ekran öz doğum tarixi və e-poçtu olurdu.  Ana
səhifə bunu əvəz edir: rola görə YIĞILMIŞ, KEÇİD verən xülasə.

──────────────────────────────────────────────────────────────────────────────
DİZAYN QAYDALARI (dəyişdirməzdən əvvəl oxu)
──────────────────────────────────────────────────────────────────────────────
1. **Yeni məlumat səthi DEYİL.**  Hər vidjet mövcud BÖLMƏYƏ yönləndirir və
   YALNIZ istifadəçinin ``allowed_sections``-ında olan bölmənin rəqəmini
   göstərir.  Aça bilmədiyi bölmənin sayğacı görünmür (sızma yoxdur).
2. **Ucuz.**  Ağır context qurucuları (jurnal xülasəsi, analitika, sillabus
   əhatə hesabatı) çağırılmır; tələbənin fənn-fənn rəqəmləri
   ``dashboard_data.student_subjects``-dən TOPLU gəlir — fənn sayı artanda
   sorğu sayı artmır.  Ümumi hədd testdə kilidlidir.
3. **JS-siz.**  Panel tam server-render-lidir; SPA keçidlərini shell-in öz
   `js-profile-section-link` deleqasiyası tutur.
4. **Bir dövr.**  Bütün vidjetlər EYNİ, tarixə əsaslanan dövrü alır
   (``dashboard_data.current_period``: bu günə düşən → yaxın gələcək →
   bayraqlı → ən son).  Əvvəl yalnız ``is_current`` bayrağına baxılırdı və
   2026-09-25-də başlıqda «2025/2026 · Yaz semestri» görünürdü.

──────────────────────────────────────────────────────────────────────────────
CONTEXT MÜQAVİLƏSİ (şablon buna söykənir — açar adları dəyişməz)
──────────────────────────────────────────────────────────────────────────────
``dashboard_section`` (dict):

    has_access   bool   — aktiv təşkilat konteksti var
    greeting     str    — «Salam, <ad>»
    role_label   str    — aktiv üzvlüyün ən yüksək rolunun LOKALLAŞDIRILMIŞ adı
    period_label str    — cari tədris ili + semestr (varsa)
    today_label  str    — «Cümə axşamı, 25.09.2026»
    week_label   str    — «üst həftə» / «alt həftə» (dövr bu günü əhatə edirsə)
    widgets      list   — bax ``dashboard_widgets.widget()`` müqaviləsi
    empty_text   str    — heç bir vidjet yığılmayanda göstərilən mətn
    kpi_tiles    list   — hero zolağının 2–4 kartı (``dashboard_layout``)
    data_count   int    — rəqəm/siyahı daşıyan vidjetlərin sayı
    link_count   int    — yığcam keçid kartlarının sayı
"""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import pgettext

from . import dashboard_layout as layout
from . import dashboard_staff_widgets as staff
from . import dashboard_student as student
from . import dashboard_teacher as teacher
from . import dashboard_widgets as personal
from .dashboard_lessons import parity_label

_CTX = "accounts.dashboard"

#: Bölmə açarı — qeydiyyat 5 yerdə EYNİ olmalıdır: ``sections_api``
#: (SECTION_PARTIALS + AJAX_SAFE_SECTIONS), ``labels.build_section_titles``,
#: ``profile.html`` (`data-ajax-sections` + dispatch) və ``rbac``.
PROFILE_SECTION = "dashboard"


def _period_label(period) -> str:
    if period is None:
        return ""
    from apps.registrar.public import season_label as _season_label

    return " · ".join(part for part in (str(period.year_display or ""), str(_season_label(period) or "")) if part)


def _role_label(user, organization) -> str:
    """Ən yüksək aktiv rolun adı — seed-dən İngiliscə qalmış ad («Student») lokallaşdırılır."""
    if organization is None:
        return ""
    from apps.organizations.public import get_active_memberships
    from core.roles import resolve_seeded_role_label

    membership = (
        get_active_memberships(user, organization)
        .filter(organization=organization)
        .select_related("role")
        .order_by("-role__level")
        .first()
    )
    if membership is None:
        return ""
    role = membership.role
    return str(resolve_seeded_role_label(getattr(role, "name", ""), getattr(role, "display_name", "")) or "")


def _greeting(user) -> str:
    """«Salam, <ad>» — ad yoxdursa tam ad, o da yoxdursa istifadəçi adı."""
    name = (
        str(getattr(user, "first_name", "") or "").strip()
        or (getattr(user, "get_full_name", lambda: "")() or "").strip()
        or str(getattr(user, "username", "") or "")
    )
    return pgettext(_CTX, "Salam, %(name)s") % {"name": name}


def _set_header(section, *, user, organization, period, today) -> None:
    from apps.registrar.public import dashboard_data

    section["role_label"] = _role_label(user, organization)
    section["period_label"] = _period_label(period)
    section["today_label"] = "%s, %s" % (personal.weekday_label(today), personal.fmt_date(today))
    section["week_label"] = (
        parity_label(dashboard_data.week_parity(period, today)) if dashboard_data.period_contains(period, today) else ""
    )


def build_dashboard_section(
    request,
    section: dict,
    *,
    active_organization=None,
    allowed_sections=None,
    active_section=None,
    capabilities=None,
    applications_pending_count: int = 0,
    pending_appeals_count: int = 0,
):
    """``dashboard_section`` sözlüyünü YERİNDƏ doldurur (qonşu bölmə naxışı)."""
    allowed_sections = set(allowed_sections or ())
    capabilities = capabilities or {}
    if PROFILE_SECTION not in allowed_sections or active_section != PROFILE_SECTION:
        return section

    user = request.user
    section["greeting"] = _greeting(user)
    section["empty_text"] = pgettext(
        _CTX, "Bu kabinet üçün hələ göstəriləcək xülasə yoxdur — sol menyudan bölmə seçin."
    )
    if active_organization is None:
        # Təşkilat konteksti yoxdur (dəvət gözləyən/orqsuz hesab): panel yenə də
        # render olunur, sadəcə vidjetsiz — «boş kabinet» səssiz 403-dən yaxşıdır.
        section["has_access"] = False
        return section

    from apps.registrar.public import dashboard_data

    section["has_access"] = True
    today = timezone.localdate()
    now = timezone.localtime().time()
    period = dashboard_data.current_period(active_organization, today=today)
    _set_header(section, user=user, organization=active_organization, period=period, today=today)

    is_student = bool(capabilities.get("is_student"))
    is_teacher = bool(capabilities.get("is_teacher"))
    record = dashboard_data.student_record(active_organization, user) if is_student else None
    # Fənn-fənn rəqəmlər BİR DƏFƏ hesablanır — «Davamiyyət» və «Cari ballar» paylaşır.
    subjects = None
    if is_student and record is not None and period is not None and "my-journal" in allowed_sections:
        subjects = dashboard_data.student_subjects(organization=active_organization, record=record, period=period)
    offerings = None
    if is_teacher and period is not None and "my-journal" in allowed_sections:
        offerings = dashboard_data.teacher_offerings(
            organization=active_organization, teacher=user, period=period, today=today
        )
    # Aralıq qiymətləndirmə pəncərəsi — müəllim kartı və İmtahan Mərkəzi kartı paylaşır (TƏK sorğu).
    windows = None
    if period is not None and ((offerings and offerings.get("total")) or "kollokvium-windows" in allowed_sections):
        windows = dashboard_data.interim_windows(organization=active_organization, period=period, today=today)
    # «Sillabus işlərim» ŞƏXSİ kartdır: təsdiq səthi olan aktor (kafedra müdiri,
    # RİM, rektor) onun əvəzinə «Sillabus təsdiqi» vidjetini alır — əks halda
    # eyni domen iki dəfə, üstəlik yanlış nöqteyi-nəzərdən görünərdi.
    shows_own_syllabus = bool(capabilities.get("can_edit_syllabus")) and not capabilities.get("can_review_syllabus")
    own_applications = None
    is_handler = False
    if "applications" in allowed_sections:
        from apps.accounts.views._dashboard_helpers.cheap_counts import (
            count_own_applications,
            is_applications_handler,
        )

        own_applications = count_own_applications(user, active_organization)
        # Tələbə emalçı ola bilməz — şöbə kataloqu sorğusu ona sərf olunmur.
        is_handler = not (is_student and not is_teacher) and is_applications_handler(user, active_organization)

    student_kwargs = {"record": record, "period": period, "subjects": subjects, "allowed_sections": allowed_sections}
    widgets = [
        # ── Tələbə ────────────────────────────────────────────────────────
        (
            student.student_today(
                organization=active_organization,
                record=record,
                period=period,
                allowed_sections=allowed_sections,
                today=today,
                now=now,
            )
            if is_student
            else None
        ),
        student.student_attendance(**student_kwargs) if is_student else None,
        student.student_scores(**student_kwargs) if is_student else None,
        # ── Müəllim ───────────────────────────────────────────────────────
        (
            teacher.teacher_today(
                organization=active_organization,
                user=user,
                period=period,
                allowed_sections=allowed_sections,
                today=today,
                now=now,
            )
            if is_teacher
            else None
        ),
        (
            teacher.teacher_offerings(data=offerings, period=period, allowed_sections=allowed_sections)
            if is_teacher
            else None
        ),
        (
            teacher.teacher_midterm(
                windows=windows,
                has_offerings=bool(offerings and offerings.get("total")),
                period=period,
                allowed_sections=allowed_sections,
                today=today,
            )
            if is_teacher
            else None
        ),
        (
            personal.teacher_syllabus(
                request=request,
                organization=active_organization,
                allowed_sections=allowed_sections,
            )
            if shows_own_syllabus
            else None
        ),
        personal.my_workload(
            organization=active_organization,
            user=user,
            allowed_sections=allowed_sections,
            is_teacher=is_teacher,
        ),
        # ── İdarəetmə ─────────────────────────────────────────────────────
        staff.applications(
            allowed_sections=allowed_sections,
            pending_count=applications_pending_count,
            own=own_applications,
            is_handler=is_handler,
        ),
        staff.syllabus_review(request=request, organization=active_organization, allowed_sections=allowed_sections),
        staff.workload_distribution(
            request=request, organization=active_organization, allowed_sections=allowed_sections
        ),
        staff.schedule_scope(request=request, organization=active_organization, allowed_sections=allowed_sections),
        staff.kollokvium_windows(
            organization=active_organization, period=period, allowed_sections=allowed_sections, windows=windows
        ),
        staff.upcoming_exams(organization=active_organization, allowed_sections=allowed_sections),
        staff.appeals(capabilities=capabilities, pending_count=pending_appeals_count),
        staff.corrections(organization=active_organization, capabilities=capabilities),
        staff.journal_close(organization=active_organization, allowed_sections=allowed_sections),
        staff.student_intake(allowed_sections=allowed_sections),
        staff.org_kpis(request=request, organization=active_organization, allowed_sections=allowed_sections),
    ]
    # Dizayn dalğasının (22 ekran) keçid kartları — idarəetmə blokunun sonunda,
    # KPI-dan əvvəl; hər biri rol qapısından keçir (bax staff.design_link_cards).
    kpi = widgets.pop()
    widgets.extend(staff.design_link_cards(allowed_sections=allowed_sections))
    widgets.append(kpi)
    # Təqdimat qatı: sıralama + hero zolağı `dashboard_layout`-dadır (bu fayl
    # NƏYİN yığıldığını, o fayl NECƏ göstərildiyini bilir).
    section["widgets"] = layout.decorate([item for item in widgets if item is not None])
    _finalise_links(section["widgets"], allowed_sections)
    section["kpi_tiles"] = layout.hero_tiles(section["widgets"])
    section["data_count"] = layout.count_variant(section["widgets"], "data")
    section["link_count"] = layout.count_variant(section["widgets"], "link")
    return section


def _finalise_links(widgets, allowed_sections) -> None:
    """Keçid linklərini SON DƏFƏ süzür və hədəf bölmənin RƏSMİ adını yazır.

    İki iş görür:
      * hədəf bölmə ``allowed_sections``-da deyilsə link SİLİNİR — məsələn
        imtahan mərkəzi «Jurnal düzəlişləri» sayğacını görür, amma jurnal
        bölməsini AÇA BİLMİR; qırıq keçid göstərmirik;
      * qalan linkə bölmənin RƏSMİ adı yazılır (SPA panel başlığını
        `data-title`-dan oxuyur — «Cədvələ keç» kimi əməl mətni başlıq olmamalıdır).
    """
    from .labels import build_section_titles

    titles = build_section_titles()
    for item in widgets:
        link = item.get("link")
        if not link:
            continue
        if link["section"] not in allowed_sections:
            item["link"] = None
            continue
        link["title"] = str(titles.get(link["section"], "") or link["label"])


__all__ = ["PROFILE_SECTION", "build_dashboard_section"]
