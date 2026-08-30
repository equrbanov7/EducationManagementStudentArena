"""structure_views paketi — vahid (fakültə/kafedra) "ətraflı görünüş" context-i.

Kafedra/fakültə kartına klikləndikdə açılan modalın datasını qurur. Scope
təhlükəsizliyi bu modula DAXİL DEYİL — çağıran (``endpoints.organization_unit_detail``)
``_get_visible_unit``-dən keçən, artıq scope-təsdiqlənmiş ``unit`` ötürür (eyni
funksiya redaktə/silmə formalarını da qoruyur, bax ``_shared.py``).

Performans qeydi: bu, SƏHİFƏLƏNMİŞ siyahı deyil — tək vahid üçün tək sorğudur,
ona görə burada "vahid sayı ilə artmayan sorğu" tələbi tətbiq olunmur (list
context builder-lərindəki kimi). Yenə də hər əlaqə üçün AYRI-AYRI yüngül
sorğular işlədilir (N+1-in özü yoxdur, çünki N=1 vahiddir)."""

from django.db.models import Count, Q
from django.urls import reverse

from core.constants import OrgUnitType

from ..models import AcademicPeriod, OrgUnit
from ._shared import (
    _active_teacher_user_ids,
    _current_academic_year_period_ids,
    _teacher_memberships_qs,
    _unit_permission_flags,
)
from .constants import (
    DETAIL_SUBJECT_PREVIEW_LIMIT,
    DETAIL_TEACHER_LIST_LIMIT,
    DETAIL_YEAR_BREAKDOWN_LIMIT,
    KAFEDRA_UNIT_TYPES,
)


def _parent_chain(unit):
    """Kökdən vahidə qədər valideyn zənciri (breadcrumb üçün) — adətən 0-1
    addım (fakültə → kafedra), amma iyerarxiya dərinləşsə də işləyir."""
    chain = []
    node = unit.parent
    while node is not None:
        chain.append(node)
        node = node.parent
    chain.reverse()
    return chain


def build_unit_detail_context(request, organization, scope, unit):
    """Tək vahid (fakültə/kafedra) üçün "ətraflı görünüş" context-i."""
    from apps.registrar.models import CourseOffering, Program, StudentAcademicRecord

    flags = _unit_permission_flags(request, organization)
    is_faculty = unit.unit_type == OrgUnitType.FACULTY

    # `group` FK-lı modellər üçün alt-ağac filtri (özü + bütün törəmələri) —
    # `apps/accounts/academic_records.py`-dəki eyni nümunə (materialized path).
    group_subtree_q = Q(group_id=unit.id) | Q(group__path__startswith=f"{unit.path}/")

    current_year_period_ids = _current_academic_year_period_ids(organization)
    active_teacher_ids = _active_teacher_user_ids(organization, current_year_period_ids)

    # ---- Kafedra siyahısı (yalnız fakültə) ---------------------------------
    kafedra_units = []
    if is_faculty:
        kafedra_units = list(
            OrgUnit.objects.filter(
                organization=organization, is_active=True, unit_type__in=KAFEDRA_UNIT_TYPES, parent_id=unit.id
            )
            .select_related("head")
            .order_by("name")
        )
    kafedra_ids = [k.id for k in kafedra_units]
    teacher_scope_ids = kafedra_ids if is_faculty else [unit.id]

    # ---- Müəllimlər ---------------------------------------------------------
    teacher_memberships = []
    if teacher_scope_ids:
        teacher_memberships = list(_teacher_memberships_qs(organization).filter(scope_unit_id__in=teacher_scope_ids))
    for membership in teacher_memberships:
        membership.is_active_teacher = membership.user_id in active_teacher_ids
    teacher_memberships.sort(
        key=lambda m: (not m.is_active_teacher, (m.user.get_full_name() or m.user.username).lower())
    )
    total_teacher_count = len(teacher_memberships)
    active_teacher_count = sum(1 for m in teacher_memberships if m.is_active_teacher)

    kafedra_rows = []
    if is_faculty:
        teachers_by_kafedra = {}
        for membership in teacher_memberships:
            teachers_by_kafedra.setdefault(membership.scope_unit_id, []).append(membership)
        for kafedra in kafedra_units:
            members = teachers_by_kafedra.get(kafedra.id, [])
            kafedra_rows.append(
                {
                    "unit": kafedra,
                    "teacher_count": len(members),
                    "active_teacher_count": sum(1 for m in members if m.is_active_teacher),
                }
            )

    # ---- Tələbə / qrup / ixtisas sayı ---------------------------------------
    student_count = (
        StudentAcademicRecord.objects.filter(organization=organization, is_active=True)
        .filter(group_subtree_q)
        .order_by()
        .values("student_id")
        .distinct()
        .count()
    )
    group_count = OrgUnit.objects.filter(
        organization=organization,
        is_active=True,
        unit_type=OrgUnitType.GROUP,
        path__startswith=f"{unit.path}/",
    ).count()
    program_count = (
        Program.objects.filter(organization=organization, is_active=True)
        .filter(Q(specialty_unit_id=unit.id) | Q(specialty_unit__path__startswith=f"{unit.path}/"))
        .count()
    )

    # ---- Fənlər (kataloq) + açılışlar ---------------------------------------
    # QEYD: `CourseOffering.group` opsionaldır ("boşdursa — bütün ixtisas
    # üçün"); `group=None` olan açılışlar bu alt-ağac filtrinə düşmür (heç bir
    # konkret qrupa bağlı olmadığı üçün hansı kafedraya aid olduğu birmənalı
    # deyil) — statistikada kiçik bir görünməzlik, amma yanlış say vermir.
    offerings_all = CourseOffering.objects.filter(organization=organization, is_active=True).filter(group_subtree_q)
    offering_total_count = offerings_all.count()
    offering_current_year_count = (
        offerings_all.filter(period_id__in=current_year_period_ids).count() if current_year_period_ids else 0
    )
    subject_rows = [
        {"id": subject_id, "code": code, "name": name}
        for subject_id, code, name in offerings_all.order_by("subject__code")
        .values_list("subject_id", "subject__code", "subject__name")
        .distinct()
    ]
    subject_count = len(subject_rows)
    subject_preview = subject_rows[:DETAIL_SUBJECT_PREVIEW_LIMIT]
    subject_hidden_count = max(0, subject_count - len(subject_preview))

    # ---- Tədris ili üzrə açılış bölgüsü (son bir neçə il) -------------------
    year_breakdown = []
    if offering_total_count:
        periods = list(
            AcademicPeriod.objects.filter(organization=organization).only("id", "academic_year", "start_date")
        )
        year_by_period_id = {p.id: p.year_display for p in periods}
        year_counts = {}
        for row in offerings_all.values("period_id").annotate(n=Count("id")):
            year = year_by_period_id.get(row["period_id"]) or "—"
            year_counts[year] = year_counts.get(year, 0) + row["n"]
        year_breakdown = sorted(year_counts.items(), key=lambda item: item[0], reverse=True)[
            :DETAIL_YEAR_BREAKDOWN_LIMIT
        ]
        max_year_count = max((count for _year, count in year_breakdown), default=0)
    else:
        max_year_count = 0

    return {
        "organization": organization,
        "unit": unit,
        "is_faculty": is_faculty,
        "unit_type_label": unit.get_unit_type_display(),
        "parent_chain": _parent_chain(unit),
        "teacher_memberships": teacher_memberships[:DETAIL_TEACHER_LIST_LIMIT],
        "teacher_hidden_count": max(0, total_teacher_count - DETAIL_TEACHER_LIST_LIMIT),
        "total_teacher_count": total_teacher_count,
        "active_teacher_count": active_teacher_count,
        "kafedra_rows": kafedra_rows,
        "student_count": student_count,
        "group_count": group_count,
        "program_count": program_count,
        "offering_total_count": offering_total_count,
        "offering_current_year_count": offering_current_year_count,
        "subject_count": subject_count,
        "subject_preview": subject_preview,
        "subject_hidden_count": subject_hidden_count,
        "year_breakdown": year_breakdown,
        "max_year_count": max_year_count,
        "can_assign_teachers": flags["can_assign_members"],
        "structure_list_url": reverse(
            "organizations:structure_faculties" if is_faculty else "organizations:structure_kafedras",
            kwargs={"slug": organization.slug},
        ),
    }
