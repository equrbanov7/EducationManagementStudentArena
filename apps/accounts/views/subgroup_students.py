"""«Alt qrup tələbələri» kabinet bölməsi — panel çərçivəsi, aktor qapısı, hədəf jurnal axtarışı (sahib 2026-11-05).

Sahib: «Sidebarda bir hissə düzəlt — alt qrup tələbələri … filter, search, sort … hansı qrupdandır əsli, hansı
qrupda alt qrupdur, kredit sayı … əlavə olunarkən sənədin özü də … statistika hissəsində göstər ən çox hansı
fəndən olub.» + «bu bölmədən də alt qrupa tələbə əlavə etmək olsun».

QAPI (menyu: ``_helpers/rbac_sections.py``; burada hər sorğuda təkrarlanır, fail-closed):

* görünür — superadmin, təşkilat sahibi, RİM rəhbəri (``ikt_rehber``) və alt qrup yerləşdirmə açarı
  (``retake.manage`` — «Alt qrupa tələbə əlavə et» bölməsi ilə EYNİ açar) olan rollar;
* əhatə — superadmin / sahib / RİM rəhbəri və təşkilat miqyaslı açar bütün təşkilatı, UNIT rolu isə yalnız öz
  alt-ağacını görür: tələbənin ÖZ qrupu VƏ YA hədəf jurnalın qrupu əhatədədirsə sətir görünür;
* «+ Alt qrupa tələbə əlavə et» — əlavə olaraq ``journal.roster`` əhatəsi lazımdır (jurnal modalı ilə EYNİ
  qayda); yazı jurnal modalının rəsmi endpoint-inə gedir (``registrar:journal_guest_add``). «Başqasının adından»
  (view-as) rejimində düymə yoxdur, ixrac bağlıdır.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode
from uuid import UUID

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.registrar.public import subgroup_access
from apps.registrar.public import subgroup_students_journals as journals
from apps.registrar.public import subgroup_students_read as read
from apps.registrar.public import subgroup_students_stats as stats
from core import superadmin_waiver

SECTION = "subgroup-students"
CTX = "accounts.subgroup_students"
_ZERO = str(UUID(int=0))


@dataclass(frozen=True)
class StudentsActor:
    user: object
    organization: object | None
    has_access: bool
    scope: object  # ``None`` — təşkilat miqyası; əks halda əhatədəki qrup id-lərinin queryset-i
    view_as: bool
    can_add: bool


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def resolve_actor(request) -> StudentsActor:
    """Sorğudan aktoru qurur; heç vaxt exception atmır (fail-closed)."""
    from apps.accounts.views._helpers.rbac_sections import _is_rim_head
    from apps.accounts.views._helpers.tenant import _get_active_organization

    user = getattr(request, "user", None)
    view_as = bool(getattr(request, "is_view_as", False))
    denied = StudentsActor(user, None, False, None, view_as, False)
    if user is None or not getattr(user, "is_authenticated", False):
        return denied
    organization = _get_active_organization(request)
    if organization is None:
        return denied
    privileged = bool(
        _is_superadmin(user) or getattr(organization, "owner_id", None) == user.pk or _is_rim_head(user, organization)
    )
    if not (privileged or subgroup_access.has_placement_key(user, organization)):
        return StudentsActor(user, organization, False, None, view_as, False)
    scope = None
    if not (privileged or subgroup_access.is_org_wide(user, organization)):
        scope = subgroup_access.scoped_groups(user, organization).values("pk")
    can_add = not view_as and journals.can_add(user, organization)
    return StudentsActor(user, organization, True, scope, view_as, can_add)


# ── Süzgəc sahələri ──────────────────────────────────────────────────────────


def _options(options, *, all_label) -> list:
    return [{"value": "", "label": all_label}, *options]


def _select(name, label, options, value, *, searchable=False) -> dict:
    every = pgettext(CTX, "Hamısı")
    field = {"name": f"{read.PREFIX}{name}", "label": label, "kind": "select", "value": value}
    field.update(options=_options(options, all_label=every), searchable=searchable)
    return field


def _filter_fields(organization, scope, filters) -> list:
    prefix = read.PREFIX
    return [
        {
            "name": f"{prefix}q",
            "label": pgettext(CTX, "Tələbə"),
            "kind": "search",
            "value": filters.q,
            "placeholder": pgettext(CTX, "Ad, soyad və ya istifadəçi adı"),
            "wide": True,
        },
        _select("faculty", pgettext(CTX, "Fakültə"), read.faculty_options(organization), filters.faculty),
        _select("chair", pgettext(CTX, "Kafedra"), read.chair_options(organization), filters.chair, searchable=True),
        _select(
            "home",
            pgettext(CTX, "Öz qrupu"),
            read.home_group_options(organization, scope),
            filters.home_group,
            searchable=True,
        ),
        _select(
            "target",
            pgettext(CTX, "Alt qrup olduğu qrup"),
            read.target_group_options(organization, scope),
            filters.target_group,
            searchable=True,
        ),
        _select(
            "subject",
            pgettext(CTX, "Fənn"),
            read.subject_options(organization, scope),
            filters.subject,
            searchable=True,
        ),
        {
            "name": f"{prefix}teacher",
            "label": pgettext(CTX, "Müəllim"),
            "kind": "search",
            "value": filters.teacher,
            "placeholder": pgettext(CTX, "Müəllimin adı"),
        },
        _select("period", pgettext(CTX, "Semestr"), read.period_options(organization, scope), filters.period),
        {
            "name": f"{prefix}from",
            "label": pgettext(CTX, "Tarixdən"),
            "kind": "date",
            "value": filters.date_from.isoformat() if filters.date_from else "",
        },
        {
            "name": f"{prefix}to",
            "label": pgettext(CTX, "Tarixədək"),
            "kind": "date",
            "value": filters.date_to.isoformat() if filters.date_to else "",
        },
        _select("status", pgettext(CTX, "Vəziyyət"), read.choice_options(read.STATUS_CHOICES), filters.status),
        _select("kind", pgettext(CTX, "Növ"), read.choice_options(read.KIND_CHOICES), filters.kind),
        _select("doc", pgettext(CTX, "Sənəd"), read.choice_options(read.DOCUMENT_CHOICES), filters.document),
    ]


# ── URL-lər ──────────────────────────────────────────────────────────────────


def section_url(params) -> str:
    return f"{reverse('accounts:profile')}?{urlencode({'section': SECTION, **params})}"


def _export_url(filters) -> str:
    url = reverse("accounts:subgroup_students_export")
    params = filters.as_params(page=1)
    return f"{url}?{urlencode(params)}" if params else url


def _columns(filters) -> dict:
    """Sıralana bilən başlıqlar: ``{açar: {label, url, dir}}`` — ikinci klik istiqaməti çevirir."""
    labels = {
        "student": pgettext(CTX, "Tələbə"),
        "home": pgettext(CTX, "Öz qrupu"),
        "target": pgettext(CTX, "Alt qrup olduğu jurnal"),
        "subject": pgettext(CTX, "Fənn"),
        "teacher": pgettext(CTX, "Müəllim"),
        "period": pgettext(CTX, "Semestr"),
        "status": pgettext(CTX, "Vəziyyət"),
        "credits": pgettext(CTX, "Kredit"),
        "actor": pgettext(CTX, "Əlavə edən"),
        "added": pgettext(CTX, "Tarix"),
    }
    current = filters.sort
    columns = {}
    for key, label in labels.items():
        if current == key:
            direction, next_sort = "ascending", f"-{key}"
        elif current == f"-{key}":
            direction, next_sort = "descending", key
        else:
            direction, next_sort = "", key if key in ("student", "home", "target", "subject", "teacher") else f"-{key}"
        columns[key] = {"label": label, "dir": direction, "url": section_url(filters.as_params(page=1, sort=next_sort))}
    return columns


def _add_context(actor) -> dict:
    if not actor.can_add:
        return {"can_add": False}
    optional = superadmin_waiver.waives(actor.user, scope=superadmin_waiver.SUBGROUP)
    # Formanın data-atributları (CSP: inline JS yoxdur) — URL şablonlarında jurnal id-si yerinə sıfır UUID durur.
    form_data = {
        "data-sst-add-form": "1",
        "data-journals-url": reverse("accounts:subgroup_students_journals"),
        "data-group-url": reverse("registrar:journal_guest_group_search", args=[_ZERO]),
        "data-student-url": reverse("registrar:journal_guest_student_search", args=[_ZERO]),
        "data-add-url": reverse("registrar:journal_guest_add", args=[_ZERO]),
        "data-zero-id": _ZERO,
        "data-document-optional": "1" if optional else "0",
        "data-msg-journal": pgettext(CTX, "Hədəf jurnalı seçin."),
        "data-msg-student": pgettext(CTX, "Mənbə qrupu və tələbəni seçin."),
        "data-msg-reason": pgettext(CTX, "Səbəb yazılmalıdır."),
        "data-msg-document": pgettext(CTX, "Sənəd (təqdimat / sərəncam) yüklənməlidir."),
        "data-msg-generic": pgettext(CTX, "Əməliyyat alınmadı — yenidən cəhd edin."),
        "data-msg-done": pgettext(CTX, "Tələbə jurnala əlavə olundu."),
        "data-ph-group": pgettext(CTX, "Qrup axtarın…"),
        "data-ph-group-idle": pgettext(CTX, "Əvvəlcə jurnal seçin…"),
        "data-ph-student": pgettext(CTX, "Tələbə axtarın…"),
        "data-ph-student-idle": pgettext(CTX, "Əvvəlcə qrup seçin…"),
        "data-empty-journal": pgettext(CTX, "Uyğun jurnal tapılmadı."),
        "data-empty-group": pgettext(CTX, "Uyğun qrup tapılmadı."),
        "data-empty-student": pgettext(CTX, "Bu qrupda uyğun tələbə tapılmadı."),
    }
    return {"can_add": True, "document_optional": optional, "form_data": form_data}


def build_panel_context(request) -> dict:
    actor = resolve_actor(request)
    panel = {
        "has_access": actor.has_access,
        "access_denied_message": pgettext(
            CTX, "Bu bölmə RİM rəhbəri, superadmin və alt qrup yerləşdirmə səlahiyyəti olan rollar üçündür."
        ),
    }
    if not actor.has_access:
        return panel
    organization, scope = actor.organization, actor.scope
    filters = read.parse_filters(request.GET)
    result = read.page(organization, filters, scope)
    panel.update(
        section=SECTION,
        filters=filters,
        filter_fields=_filter_fields(organization, scope, filters),
        filter_count_label=pgettext(CTX, "Nəticə: %(n)s qeyd") % {"n": result["total"]},
        is_filtered=filters.is_filtered,
        stats=stats.build(organization, filters, scope),
        columns=_columns(filters),
        view_as=actor.view_as,
        scope_limited=scope is not None,
        export_url="" if actor.view_as else _export_url(filters),
        prev_url=section_url(filters.as_params(page=result["page"] - 1)) if result["has_prev"] else "",
        next_url=section_url(filters.as_params(page=result["page"] + 1)) if result["has_next"] else "",
        add=_add_context(actor),
        **result,
    )
    return panel


# ── Hədəf jurnal axtarışı (əlavə modalı) ─────────────────────────────────────


def _bounds(request) -> tuple[int, int]:
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(request.GET.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    return min(offset, 2000), max(1, min(limit, 50))


@never_cache
@login_required
@require_GET
def subgroup_students_journals(request):
    """Modalın «Hədəf jurnal» seçicisi — ``{"results": [{id, text}], "has_more"}`` (yalnız oxu)."""
    actor = resolve_actor(request)
    if not actor.has_access or not actor.can_add:
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    offset, limit = _bounds(request)
    query = " ".join(str(request.GET.get("q") or "").split())[:100]
    results, has_more = journals.search(actor.user, actor.organization, query, offset=offset, limit=limit)
    return JsonResponse({"results": results, "has_more": has_more})


__all__ = ["SECTION", "StudentsActor", "build_panel_context", "resolve_actor", "subgroup_students_journals"]
