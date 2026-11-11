"""Təhvil siyahısının SÜZGƏC məntiqi — JSON endpoint-i və kabinet paneli üçün ORTAQ.

İki səth eyni siyahını göstərir (server-render panel + `handover_offerings`
JSON-u), ona görə süzgəc tərifi TƏK yerdədir: parametr adları fərqli ola bilər
(`?q=` ↔ `?th_q=`), qayda yox.

⚠️ «Yalnız təhvil oluna bilənlər» süzgəci əvvəllər TƏXMİNİ idi
(``period__is_current=True, is_active=True``) — bağlı jurnalı olan cari
semestr sətri siyahıda qalırdı və istifadəçi onu seçib 409 alırdı. Artıq süzgəc
blokerlərin ÖZ tərifindən (``handover_query``) qurulur: «açıq» = heç bir bloker
tutmayan sətir.
"""

from __future__ import annotations

from django.db.models import Q

from apps.registrar.public import handover_query
from core.search_text import tolerant_q

#: «Vəziyyət» süzgəcinin dəyərləri.
STATE_ALL = ""
STATE_OPEN = "open"
STATE_BLOCKED = "blocked"


def blocked_q(*, actor, today) -> tuple:
    """(annotasiya sözlüyü, ``Q``) — bloklanmış sətirlərin SQL şərti.

    Tərif :func:`apps.registrar.handover_query.blocker_facets`-dəki ilə eynidir
    (eyni funksiyalardan qurulur), yəni KPI sayğacı ilə süzgəc heç vaxt
    fərqlənmir.
    """
    alias, closed = handover_query.closed_journal_q()
    condition = Q(**{alias: True}) | handover_query.past_period_q(today) | Q(is_active=False)
    actor_id = getattr(actor, "pk", None)
    if actor_id:
        condition |= Q(instructor_id=actor_id)
    return {alias: closed}, condition


def apply_filters(queryset, values, *, organization, actor, today=None):
    """Süzgəcləri tətbiq edir. ``values`` — normallaşdırılmış sözlük.

    Açarlar: ``teacher`` (``__none__`` = müəllimsiz), ``period``, ``faculty``,
    ``kafedra``, ``q``, ``state``.
    """
    from django.utils import timezone

    today = today or timezone.localdate()

    teacher = (values.get("teacher") or "").strip()
    if teacher == "__none__":
        queryset = queryset.filter(instructor__isnull=True)
    elif teacher.isdigit():
        # 2026-11-11: seminar/lab müəllimi də (aktiv jurnal payı) — onun növünü ayrıca təhvil vermək üçün.
        queryset = queryset.filter(Q(instructor_id=teacher) | Q(pk__in=_shared_with(teacher)))
    elif teacher:
        queryset = queryset.none()

    period = (values.get("period") or "").strip()
    if period:
        queryset = queryset.filter(period_id=period)

    for key in ("faculty", "kafedra"):
        unit_id = (values.get(key) or "").strip()
        if unit_id:
            queryset = queryset.filter(group__in=unit_subtree_ids(organization, unit_id))

    # Az/ing dözümlü; fənn kodu və qrup adı kod rejimində («234king» → «234 K ing»). 2026-11-11: müəllim adı da
    # (sahib və ya seminar/lab payı olan müəllim).
    term = values.get("q") or ""
    search = tolerant_q(
        term,
        ("subject__name", "instructor__first_name", "instructor__last_name"),
        compact_fields=("subject__code", "group__name"),
    )
    if search is not None:
        teachers = tolerant_q(term, ("teacher__first_name", "teacher__last_name", "teacher__username"))
        if teachers is not None:
            search |= Q(pk__in=_share_model().objects.filter(is_active=True).filter(teachers).values("offering_id"))
        queryset = queryset.filter(search)

    state = (values.get("state") or "").strip()
    if state in (STATE_OPEN, STATE_BLOCKED):
        annotations, condition = blocked_q(actor=actor, today=today)
        queryset = queryset.annotate(**annotations)
        queryset = queryset.filter(condition) if state == STATE_BLOCKED else queryset.exclude(condition)
    return queryset


def _share_model():
    from django.apps import apps as django_apps

    return django_apps.get_model("registrar", "JournalShare")


def _shared_with(teacher_id):
    """Müəllimin aktiv jurnal payı olan açılışlar (subquery)."""
    return _share_model().objects.filter(teacher_id=teacher_id, is_active=True).values("offering_id")


def unit_subtree_ids(organization, unit_id):
    """Fakültə/kafedra alt-ağacındakı OrgUnit id-ləri (tanınmayan id → boş)."""
    from django.apps import apps as django_apps

    org_unit = django_apps.get_model("organizations", "OrgUnit")
    unit = org_unit.objects.filter(organization=organization, pk=unit_id).only("id", "path").first()
    if unit is None:
        return []
    condition = Q(pk=unit.pk)
    if unit.path:
        condition |= Q(path__startswith=f"{unit.path}/")
    return list(org_unit.objects.filter(organization=organization).filter(condition).values_list("pk", flat=True))


__all__ = [
    "STATE_ALL",
    "STATE_BLOCKED",
    "STATE_OPEN",
    "apply_filters",
    "blocked_q",
    "unit_subtree_ids",
]
