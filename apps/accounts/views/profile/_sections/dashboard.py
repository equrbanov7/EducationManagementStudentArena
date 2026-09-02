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
   əhatə hesabatı) çağırılmır; hər vidjet bir neçə count/aggregate/`[:5]`
   sorğusu ilə kifayətlənir.  Ümumi hədd testdə kilidlidir.
3. **JS-siz.**  Panel tam server-render-lidir; SPA keçidlərini shell-in öz
   `js-profile-section-link` deleqasiyası tutur.

──────────────────────────────────────────────────────────────────────────────
CONTEXT MÜQAVİLƏSİ (şablon buna söykənir — açar adları dəyişməz)
──────────────────────────────────────────────────────────────────────────────
``dashboard_section`` (dict):

    has_access   bool   — aktiv təşkilat konteksti var
    greeting     str    — «Salam, <ad>»
    role_label   str    — aktiv üzvlüyün ən yüksək rolunun adı
    period_label str    — cari tədris ili + semestr (varsa)
    widgets      list   — bax ``dashboard_widgets.widget()`` müqaviləsi
    empty_text   str    — heç bir vidjet yığılmayanda göstərilən mətn
"""

from __future__ import annotations

from django.utils.translation import pgettext

from . import dashboard_staff_widgets as staff
from . import dashboard_widgets as personal

_CTX = "accounts.dashboard"

#: Bölmə açarı — qeydiyyat 5 yerdə EYNİ olmalıdır: ``sections_api``
#: (SECTION_PARTIALS + AJAX_SAFE_SECTIONS), ``labels.build_section_titles``,
#: ``profile.html`` (`data-ajax-sections` + dispatch) və ``rbac``.
PROFILE_SECTION = "dashboard"


def _current_period(organization):
    """Cari semestr (yoxdursa ən son başlayan) — bir sorğu."""
    from apps.organizations.models import AcademicPeriod

    if organization is None:
        return None
    return (
        AcademicPeriod.objects.filter(organization=organization, is_current=True).first()
        or AcademicPeriod.objects.filter(organization=organization).order_by("-start_date").first()
    )


def _period_label(period) -> str:
    if period is None:
        return ""
    from apps.registrar.page_contexts import _season_label

    return " · ".join(part for part in (str(period.year_display or ""), str(_season_label(period) or "")) if part)


def _student_record(organization, user):
    """Tələbənin aktiv akademik qeydi (yoxdursa ``None``) — bir sorğu."""
    from apps.registrar.models import StudentAcademicRecord

    if organization is None:
        return None
    return (
        StudentAcademicRecord.objects.filter(organization=organization, student=user, is_active=True)
        .select_related("program", "group")
        .first()
    )


def _role_label(user, organization) -> str:
    if organization is None:
        return ""
    from apps.organizations.public import get_active_memberships

    membership = (
        get_active_memberships(user, organization)
        .filter(organization=organization)
        .select_related("role")
        .order_by("-role__level")
        .first()
    )
    if membership is None:
        return ""
    return str(getattr(membership.role, "display_name", "") or "")


def _greeting(user) -> str:
    name = (getattr(user, "get_full_name", lambda: "")() or "").strip() or str(getattr(user, "username", "") or "")
    return pgettext(_CTX, "Salam, %(name)s") % {"name": name}


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

    section["has_access"] = True
    section["role_label"] = _role_label(user, active_organization)
    period = _current_period(active_organization)
    section["period_label"] = _period_label(period)

    record = _student_record(active_organization, user) if capabilities.get("is_student") else None

    is_student = bool(capabilities.get("is_student"))
    is_teacher = bool(capabilities.get("is_teacher"))
    # «Sillabus işlərim» ŞƏXSİ kartdır: təsdiq səthi olan aktor (kafedra müdiri,
    # RİM, rektor) onun əvəzinə «Sillabus təsdiqi» vidjetini alır — əks halda
    # eyni domen iki dəfə, üstəlik yanlış nöqteyi-nəzərdən görünərdi.
    shows_own_syllabus = bool(capabilities.get("can_edit_syllabus")) and not capabilities.get("can_review_syllabus")

    widgets = [
        # ── Tələbə ────────────────────────────────────────────────────────
        (
            personal.student_today(
                organization=active_organization,
                record=record,
                period=period,
                allowed_sections=allowed_sections,
            )
            if is_student
            else None
        ),
        (
            personal.student_attendance(
                organization=active_organization,
                user=user,
                record=record,
                period=period,
                allowed_sections=allowed_sections,
            )
            if is_student
            else None
        ),
        (
            personal.student_grades(
                organization=active_organization,
                user=user,
                allowed_sections=allowed_sections,
            )
            if is_student
            else None
        ),
        # ── Müəllim ───────────────────────────────────────────────────────
        (
            personal.teacher_today(
                organization=active_organization,
                user=user,
                period=period,
                allowed_sections=allowed_sections,
            )
            if is_teacher
            else None
        ),
        (
            personal.teacher_offerings(
                organization=active_organization,
                user=user,
                period=period,
                allowed_sections=allowed_sections,
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
        staff.applications(allowed_sections=allowed_sections, pending_count=applications_pending_count),
        staff.syllabus_review(request=request, organization=active_organization, allowed_sections=allowed_sections),
        staff.workload_distribution(
            request=request, organization=active_organization, allowed_sections=allowed_sections
        ),
        staff.schedule_scope(request=request, organization=active_organization, allowed_sections=allowed_sections),
        staff.kollokvium_windows(organization=active_organization, period=period, allowed_sections=allowed_sections),
        staff.upcoming_exams(organization=active_organization, allowed_sections=allowed_sections),
        staff.appeals(capabilities=capabilities, pending_count=pending_appeals_count),
        staff.corrections(organization=active_organization, capabilities=capabilities),
        staff.journal_close(organization=active_organization, allowed_sections=allowed_sections),
        staff.student_intake(allowed_sections=allowed_sections),
        staff.org_kpis(request=request, organization=active_organization, allowed_sections=allowed_sections),
    ]
    section["widgets"] = [item for item in widgets if item is not None]
    _finalise_links(section["widgets"], allowed_sections)
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
