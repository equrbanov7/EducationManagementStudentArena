"""Fənn təhvili — TOPLU (bulk) oxu köməkçiləri: N+1-siz siyahı, təsir, xülasə.

Qərar qatı (:mod:`apps.registrar.handover`) bir SƏTİR üçün cavab verir:
«bu açılış təhvil oluna bilərmi?». Siyahı səthi isə eyni sualı 25–100 sətir üçün
verir və hər sətrə ayrıca sorğu getsə ekran ölür. Bu modul həmin sualların
CƏDVƏL variantıdır — hər funksiya SABİT sayda sorğu işlədir, sətir sayından
ASILI DEYİL.

⚠️ **Qayda təkrarlanmır.** Bloker tərifləri (bağlı jurnal, keçmiş dövr, aktiv
olmayan açılış, öz jurnalını atma) burada YENİDƏN yazılmır — SQL forması
``handover.py``-dakı Python tərifinin EYNİSİDİR və ikisi bir yerdə, yan-yana
saxlanılır (:func:`past_period_q` şərhinə bax). Tərif dəyişsə hər iki yer
dəyişməlidir; ona görə testdə eyni datada iki yol müqayisə olunur
(``test_handover_bulk_matches_row_by_row``).

ÖLÇÜLƏN NƏTİCƏ (2026-09-09, dekan aktoru, 60 açılış):
    əvvəl  5 sətir = 24 sorğu · 50 sətir = 69 sorğu   (sətir başına +1)
    sonra  5 sətir = 20 sorğu · 50 sətir = 20 sorğu   (sabit)
"""

from __future__ import annotations

from django.db.models import Count, Exists, OuterRef, Q

from apps.registrar.exam_eligibility import _LOCKED_STATUSES
from apps.registrar.models import AssessmentScheme

__all__ = [
    "blocker_facets",
    "bulk_blockers",
    "closed_journal_q",
    "impact_counts",
    "impact_totals",
    "in_scope_offering_ids",
    "list_queryset",
    "past_period_q",
]


# ── Əhatə (scope) — bir sorğuda ──────────────────────────────────────────────


def in_scope_offering_ids(user, organization, offerings) -> set:
    """:func:`handover.offering_in_scope`-un TOPLU variantı — TƏK sorğu.

    Sətir-sətir çağırışda hər açılış üçün ayrıca ``OrgUnit … exists()`` gedirdi
    (org-wide aktorda yox, amma dekan/kafedra müdirində — yəni məhz bu ekranın
    ƏSAS istifadəçisində). Burada bütün qrup id-ləri BİR dəfə soruşulur.

    Fail-closed: əhatəsi olmayan aktor BOŞ dəst alır (heç bir sətir «əhatədə»
    sayılmır), qrupsuz açılış isə yalnız org-wide aktorda əhatəyə düşür — hər
    iki davranış tək-sətir funksiyası ilə eynidir.
    """
    from apps.registrar import handover as handover_read

    pairs = [(offering.pk, getattr(offering, "group_id", None)) for offering in offerings]
    if not pairs:
        return set()
    scope = handover_read.actor_scope(user, organization)
    if not scope.has_structure_access:
        return set()
    if scope.is_org_wide:
        return {pk for pk, _ in pairs}
    group_ids = {group_id for _, group_id in pairs if group_id}
    if not group_ids:
        return set()
    from django.apps import apps as django_apps

    org_unit = django_apps.get_model("organizations", "OrgUnit")
    allowed = set(
        org_unit.objects.filter(organization=organization, pk__in=group_ids)
        .filter(scope.unit_subtree_q())
        .values_list("pk", flat=True)
    )
    return {pk for pk, group_id in pairs if group_id in allowed}


# ── Blokerlərin SQL forması ──────────────────────────────────────────────────


def closed_journal_q(alias: str = "_handover_closed") -> tuple:
    """(annotasiya adı, ``Exists`` ifadəsi) — jurnalı BAĞLI açılışlar.

    Meyar :func:`handover.closed_offering_ids` ilə eynidir: sxem ya
    ``is_published``, ya da kilidli ``approval_status``-dadır.
    """
    scheme = AssessmentScheme.objects.filter(offering_id=OuterRef("pk")).filter(
        Q(is_published=True) | Q(approval_status__in=_LOCKED_STATUSES)
    )
    return alias, Exists(scheme)


def past_period_q(today) -> Q:
    """:func:`handover.period_is_past`-in SQL EKVİVALENTİ.

    Python tərifi::

        period is None                       → keçmiş
        period.is_current                    → keçmiş DEYİL (rəsmi uzadılma)
        end_date and end_date < today        → keçmiş

    ``end_date`` boş olan dövr keçmiş sayılmır — həmin şərt burada da yoxdur.
    """
    return Q(period__isnull=True) | Q(period__is_current=False, period__end_date__lt=today)


def blocker_facets(queryset, *, actor, today=None) -> dict:
    """Süzülmüş DƏSTİN bloker xülasəsi — TƏK aqreqat sorğu.

    KPI kartları və «3 fənn təhvil verilə bilməz: 2 bağlı jurnal, 1 keçmiş
    semestr» lenti buradan qidalanır. Sayğaclar SƏHİFƏNİN yox, bütün süzülmüş
    dəstin sayıdır — istifadəçi «neçəsi bloklanıb» sualının cavabını 2-ci
    səhifəyə keçmədən görməlidir.

    ``outside_scope`` sayılmır: ``queryset`` onsuz da ``scoped_offerings``-dən
    gəlir, yəni tərifə görə hamısı əhatədədir.
    """
    from django.utils import timezone

    today = today or timezone.localdate()
    # ⚠️ Alias süzgəcinkindən FƏRQLİDİR: `filters.blocked_q` eyni queryset-i
    # onsuz da `_handover_closed` ilə annotasiya edə bilər («yalnız bloklananlar»
    # süzgəci), ikinci dəfə eyni adla annotasiya isə kövrək davranışdır.
    alias, closed = closed_journal_q("_facet_closed")
    past = past_period_q(today)
    inactive = Q(is_active=False)
    actor_id = getattr(actor, "pk", None)
    own = Q(instructor_id=actor_id) if actor_id else Q(pk__in=[])
    closed_q = Q(**{alias: True})
    blocked = closed_q | past | inactive | own
    rows = queryset.annotate(**{alias: closed}).aggregate(
        total=Count("pk"),
        journal_closed=Count("pk", filter=closed_q),
        past_period=Count("pk", filter=past),
        offering_inactive=Count("pk", filter=inactive),
        actor_is_current_instructor=Count("pk", filter=own),
        blocked=Count("pk", filter=blocked),
    )
    rows = {key: int(value or 0) for key, value in rows.items()}
    rows["open"] = max(rows["total"] - rows["blocked"], 0)
    return rows


def bulk_blockers(offerings, *, actor, organization, today=None) -> dict:
    """``{offering_id: [bloker kodu, …]}`` — səhifə üçün SABİT sayda sorğu.

    Üç toplu sorğu (əhatə + bağlı jurnallar + bugünkü tarix onsuz da yaddaşda)
    hesablanır, sonra qərar qatının ÖZ funksiyası (:func:`handover.blockers`)
    hazır dəstlərlə çağırılır — qayda ikinci dəfə yazılmır.
    """
    from django.utils import timezone

    from apps.registrar import handover as handover_read

    rows = list(offerings)
    if not rows:
        return {}
    today = today or timezone.localdate()
    ids = [offering.pk for offering in rows]
    closed_ids = handover_read.closed_offering_ids(ids)
    in_scope = in_scope_offering_ids(actor, organization, rows) if actor is not None else None
    return {
        offering.pk: handover_read.blockers(
            offering,
            actor=actor,
            organization=organization,
            closed_ids=closed_ids,
            today=today,
            in_scope=None if in_scope is None else offering.pk in in_scope,
        )
        for offering in rows
    }


# ── Təsir sayğacları ─────────────────────────────────────────────────────────


def impact_counts(offering_ids) -> dict:
    """«Neçə tələbə / dərs / bal xanası / yekun qiymət» — DÖRD toplu aqreqat.

    ⚠️ Sayğaclar QƏSDƏN cədvəl sorğusunun annotasiyası DEYİL. Əvvəl
    ``Count("enrollments") + Count("lessons", distinct=True)`` eyni sorğuda idi;
    bu, hər açılış üçün tələbə × dərs KARTEZİAN birləşməsi yaradırdı (30 tələbə
    × 60 dərs = 1800 sətir/açılış) və `DISTINCT` onu sonradan yığırdı. Ayrı
    ``GROUP BY`` sorğuları həm ucuzdur, həm də sətir sayından asılı deyil.
    """
    from apps.registrar.models import Enrollment, FinalGrade, Lesson, LessonMark

    ids = [offering_id for offering_id in offering_ids if offering_id]
    if not ids:
        return {}

    def _grouped(queryset, key):
        return {row[0]: row[1] for row in queryset.values_list(key).annotate(total=Count("id")).order_by()}

    students = _grouped(
        Enrollment.objects.filter(offering_id__in=ids, status=Enrollment.Status.ENROLLED),
        "offering_id",
    )
    lessons = _grouped(Lesson.objects.filter(offering_id__in=ids), "offering_id")
    marks = _grouped(LessonMark.objects.filter(lesson__offering_id__in=ids), "lesson__offering_id")
    finals = _grouped(FinalGrade.objects.filter(enrollment__offering_id__in=ids), "enrollment__offering_id")
    return {
        offering_id: {
            "students": int(students.get(offering_id, 0)),
            "lessons": int(lessons.get(offering_id, 0)),
            "marks": int(marks.get(offering_id, 0)),
            "finals": int(finals.get(offering_id, 0)),
        }
        for offering_id in ids
    }


def impact_totals(queryset) -> dict:
    """Süzülmüş DƏSTİN ümumi təsiri — «neçə tələbə, neçə dərs» KPI-ları üçün.

    İki ayrı aqreqat (yenə kartezian birləşmədən qaçmaq üçün); hər ikisi alt
    sorğu ilə açılış id-lərinə bağlanır.
    """
    from apps.registrar.models import Enrollment, Lesson

    ids = queryset.values("pk")
    students = Enrollment.objects.filter(offering_id__in=ids, status=Enrollment.Status.ENROLLED).count()
    lessons = Lesson.objects.filter(offering_id__in=ids).count()
    return {"students": students, "lessons": lessons}


def list_queryset(queryset):
    """Cədvəl sorğusunun ORTAQ formalaşdırılması — FK-lar bir join ilə gəlir."""
    return queryset.select_related("subject", "period", "group", "instructor").order_by(
        "-period__start_date", "subject__code", "group__name", "pk"
    )
