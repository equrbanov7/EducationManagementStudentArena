"""Səviyyə qrupları keçidləri — kabinet sidebar-ı və jurnal qridi üçün.

* ``language_cohort_nav`` (2026-11-01) — sidebar bəndi: «Xarici dil səviyyə qrupları»
  «Tədris şöbəsi → Qruplar»-ın yanında (roster əhatəsi olan heyət) və ya müəllimin
  «Elektron jurnal» bəndinin yanında (yalnız öz səviyyə jurnalı olan müəllim).
  Əvvəl jurnal siyahısının üstündə üzən düymə idi (sahib: «sidebara qrupların yanına
  qoy»). Görünürlük reyestrin mərkəzi icazə əhatəsinə uyğundur
  (``language_cohorts.department_choices`` / səviyyə açılışının müəllimi); nəticə
  bir request-də BİR dəfə hesablanır (`request._ems_language_cohort_nav`) — sidebar
  bir neçə şablonda eyni açarı oxuyur.
* ``language_cohort_manage_entry`` — jurnal alət zolağında «Xarici dil səviyyə qrupları» düyməsi.
  Sahib 2026-11-10: müəllimə GÖRÜNMÜR — yalnız kohortun kafedrası `journal.roster` əhatəsində
  olan heyətə (laborant, tyutor, dekanlıq, kafedra müdiri …), bax
  ``language_cohorts.can_manage_as_staff``. Səhifənin öz qapısı (``can_manage``) dəyişməyib.
"""

from django import template
from django.db.models import Q
from django.urls import reverse

from apps.registrar.integrity import is_authorized_instructor
from apps.registrar.language_cohorts import can_manage_as_staff, department_choices
from apps.registrar.language_levels import LEVEL_RE
from apps.registrar.models import CourseOffering, LanguageLevelCohort

register = template.Library()

_NAV_CACHE_ATTR = "_ems_language_cohort_nav"
_HIDDEN = {"staff": False, "teacher": False, "visible": False, "url": ""}


def _own_level_offering_exists(user, organization):
    return (
        CourseOffering.objects.filter(organization=organization, is_active=True, subject__name__iregex=LEVEL_RE.pattern)
        .filter(Q(instructor=user) | Q(shares__teacher=user, shares__is_active=True))
        .exists()
    )


def _compute_nav(request, capabilities=None):
    """Kabinet renderində `role_capabilities` (artıq hesablanmış rol/əhatə bayraqları) sorğu büdcəsini
    qoruyur: `journal.roster` əhatəsi olmayan və müəllim olmayan istifadəçi üçün HEÇ BİR sorğu getmir
    (kabinet büdcə testləri üzvlük oxularını sayır). Bayraqlar yoxdursa (müstəqil səhifə) tam yoxlama."""
    organization = getattr(request, "organization", None)
    user = getattr(request, "user", None)
    if not (organization and user and user.is_authenticated and user.is_active):
        return dict(_HIDDEN)
    caps = capabilities if isinstance(capabilities, dict) else None
    if caps is None:
        staff = department_choices(user, organization).exists()
        teacher = (
            not staff
            and is_authorized_instructor(organization=organization, instructor=user)
            and _own_level_offering_exists(user, organization)
        )
    else:
        # `can_manage_journal_roster` = eyni `journal.roster` struktur əhatəsi (rbac-da hesablanıb);
        # kafedra/şöbə vahidinin mövcudluğu burada sorğu ilə yoxlanmır — səhifənin öz qapısı
        # (`language_cohort_views.index`) yenə `department_choices` ilə qərar verir.
        staff = bool(caps.get("can_manage_journal_roster"))
        teacher = not staff and bool(caps.get("is_teacher")) and _own_level_offering_exists(user, organization)
    return {
        "staff": staff,
        "teacher": teacher,
        "visible": staff or teacher,
        "url": reverse("registrar:language_cohorts") if (staff or teacher) else "",
    }


@register.simple_tag(takes_context=True)
def language_cohort_nav(context):
    """``{% language_cohort_nav as lc_nav %}`` → ``{staff, teacher, visible, url}`` (request-keşli)."""
    request = context.get("request")
    if request is None:
        return dict(_HIDDEN)
    cached = getattr(request, _NAV_CACHE_ATTR, None)
    if cached is None:
        cached = _compute_nav(request, context.get("role_capabilities"))
        try:
            setattr(request, _NAV_CACHE_ATTR, cached)
        except AttributeError:  # pragma: no cover — yalnız-oxu request obyekti
            pass
    return cached


@register.inclusion_tag("registrar/partials/_language_cohort_manage_entry.html")
def language_cohort_manage_entry(offering, user):
    if not getattr(offering, "pk", None):
        return {"cohort": None}
    group = offering._state.fields_cache.get("group")
    if group is not None and not (group.settings or {}).get("language_level_cohort"):
        return {"cohort": None}
    cohort = (
        LanguageLevelCohort.objects.filter(organization_id=offering.organization_id, offering_id=offering.pk)
        .select_related("organization", "offering")
        .first()
    )
    return {"cohort": cohort if cohort is not None and can_manage_as_staff(user, cohort) else None}
