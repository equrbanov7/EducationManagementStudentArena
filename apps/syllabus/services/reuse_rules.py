"""Sillabusun TƏKRAR İSTİFADƏSİ — QAYDALAR (oxu tərəfi, DB yazısı yoxdur).

Sahibin tələbi (2026-10-08): müəllim eyni fənni eyni semestrdə bir neçə qrupa
(açılışa) keçirsə, sillabusu iki dəfə yazmağa məcbur olmasın — saatlar eynidirsə
BAĞLASIN, deyilsə KOPYALAYIB uyğunlaşdırsın.

Terminlər
---------
* **qonşu** (sibling) — eyni təşkilat + eyni fənn + eyni semestr, FƏRQLİ açılış,
  aktiv, özü başqasına bağlı OLMAYAN dosye (bağ ulduz formalıdır, zəncir yoxdur);
  yalnız aktorun OXUYA BİLDİYİ dosyelər (``queries._scope_filter`` — siyahı ilə
  eyni fail-closed qapı) görünür.
* **bağla** (link) — hədəfin məzmunu mənbənin TƏSDİQLƏNMİŞ versiyasının EYNİ
  nüsxəsi olur və ``approval_source = reuse`` damğası ilə qüvvəyə minir.
* **kopyala** (copy) — mənbənin məzmunu hədəfə QARALAMA kimi yazılır, həftəlik
  cədvəl hədəfin saatına uyğunlaşdırılır, sonra adi təsdiq axını.

Bağlamanın şərtləri (hamısı ödənməlidir, əks halda səbəb kodu qaytarılır):

1. mənbənin müəllifi aktorun ÖZÜDÜR (``is_author``) — ``info`` bölməsi (müəllim,
   məsləhət saatı) şəxsi məlumatdır, başqasının adı tələbəyə getməsin;
2. mənbənin QÜVVƏDƏ olan versiyası var və o, İNSAN qərarı ilə təsdiqlənib
   (``approval_source = human``) — köçürmə/bağlama damğalı təsdiq zəncirlənmir;
3. hədəfin saatı MƏLUMDUR və mənbə versiyanın ``plan_hours``-u ilə EYNİDİR
   (növ-növ; 1 dərs = 2 saat, sətir sayı ``ceil(max/2)`` — saat eynidirsə həftəlik
   cədvəlin forması da eynidir);
4. hədəfin kafedrası (təsdiq əhatəsi) mənbəninki ilə EYNİDİR — başqa kafedranın
   müdirinin təsdiqi bu kafedraya köçürülmür;
5. hədəfdə qüvvədə olan təsdiq və ya göndərilmiş/baxışda/düzəlişdə versiya YOXDUR
   (yalnız boş/qaralama dosye və ya hələ yaradılmamış dosye bağlana bilər).

Kopyalamanın şərti ``copy_from_previous`` ilə EYNİ əhatə qapısıdır: mənbənin
müəllifi və ya mənbənin kafedrasını ``syllabus.edit`` ilə əhatə edən aktor.
"""

from __future__ import annotations

from django.db.models import Case, Count, F, IntegerField, Q, Value, When

from ..constants import LESSON_HOUR_KINDS, OPEN_STATUSES, PERM_EDIT, SyllabusStatus
from ..models import ApprovalSource, Syllabus
from .queries import _scope_filter, own_q
from .scoping import is_author

# ── Səbəb kodları (UI mətni ``accounts/views/syllabus/labels.py``-dadır) ─────────
CODE_NOT_OWN = "reuse.not_own_source"
CODE_SOURCE_NOT_APPROVED = "reuse.source_not_approved"
CODE_SOURCE_NOT_HUMAN = "reuse.source_not_human_approved"
CODE_HOURS_UNKNOWN = "reuse.hours_unknown"
CODE_HOURS_DIFFER = "reuse.hours_differ"
CODE_CHAIR_DIFFERS = "reuse.chair_differs"
CODE_TARGET_LOCKED = "reuse.target_locked"
CODE_TARGET_LINKED = "reuse.target_linked"
CODE_NOT_SIBLING = "reuse.not_sibling"
CODE_NOT_PREVIOUS = "reuse.not_previous"
CODE_COPY_OUT_OF_SCOPE = "reuse.copy_out_of_scope"
CODE_NOT_LINKED = "reuse.not_linked"
CODE_UP_TO_DATE = "reuse.up_to_date"
CODE_LINKED_UNLINK_FIRST = "reuse.linked_unlink_first"
CODE_BASE_MISSING = "version.base_missing"

REASON_CODES = (
    CODE_NOT_OWN,
    CODE_SOURCE_NOT_APPROVED,
    CODE_SOURCE_NOT_HUMAN,
    CODE_HOURS_UNKNOWN,
    CODE_HOURS_DIFFER,
    CODE_CHAIR_DIFFERS,
    CODE_TARGET_LOCKED,
    CODE_TARGET_LINKED,
    CODE_NOT_SIBLING,
    CODE_NOT_PREVIOUS,
    CODE_COPY_OUT_OF_SCOPE,
    CODE_NOT_LINKED,
    CODE_UP_TO_DATE,
    CODE_LINKED_UNLINK_FIRST,
)


def normalize_hours(hours) -> dict:
    """``{növ: müsbət tam}`` — boş/0/yanlış dəyərlər atılır (``set_plan_hours`` ilə eyni)."""
    cleaned = {}
    for kind in LESSON_HOUR_KINDS:
        try:
            value = int((hours or {}).get(kind) or 0)
        except (TypeError, ValueError, AttributeError):
            value = 0
        if value > 0:
            cleaned[kind] = value
    return cleaned


def hours_match(source_hours, target_hours) -> bool:
    """Saatlar EYNİDİRMİ — iki tərəf də MƏLUM olmalıdır (boş ≠ boş: «bilinmir»)."""
    source, target = normalize_hours(source_hours), normalize_hours(target_hours)
    return bool(source) and source == target


def hours_rows(source_hours, target_hours) -> list:
    """UI üçün növ-növ müqayisə: ``[{kind, source, target, same}]``."""
    source, target = normalize_hours(source_hours), normalize_hours(target_hours)
    return [
        {
            "kind": kind,
            "source": source.get(kind, 0),
            "target": target.get(kind, 0),
            "same": source.get(kind, 0) == target.get(kind, 0),
        }
        for kind in LESSON_HOUR_KINDS
        if source.get(kind) or target.get(kind)
    ]


def reuse_root(syllabus):
    """Bağın KÖKÜ — bağlı dosye verilsə onun mənbəyi (zəncir yaranmır)."""
    if syllabus is None:
        return None
    return syllabus.reused_from if syllabus.reused_from_id else syllabus


def link_base(source):
    """Bağlana bilən mənbə versiya: qüvvədə olan, İNSAN qərarı ilə təsdiqlənmiş."""
    version = getattr(source, "approved_version", None)
    if version is None or version.status != SyllabusStatus.APPROVED.value:
        return None
    if version.approval_source != ApprovalSource.HUMAN.value:
        return None
    return version


def copy_base(source):
    """Kopyalama mənbəyi — təsdiqlənmiş nüsxə, yoxdursa ən son versiya."""
    approved = getattr(source, "approved_version", None)
    if approved is not None and approved.status == SyllabusStatus.APPROVED.value:
        return approved
    return source.current_version or source.versions.order_by("-major", "-minor").first()


def target_state_code(target) -> str:
    """Mövcud hədəf dosye bağlana/kopyalana bilərmi (``""`` — bəli).

    Yalnız HƏLƏ QÜVVƏDƏ OLMAYAN dosyeyə yazılır: təsdiqlənmiş nüsxə, göndərilmiş /
    baxışda / düzəlişdə versiya və artıq bağlı dosye TOXUNULMUR.
    """
    if target is None:
        return ""
    if target.reused_from_id:
        return CODE_TARGET_LINKED
    if target.approved_version_id is not None:
        return CODE_TARGET_LOCKED
    # Göstərici köhnəlmiş ola bilər — həqiqət versiyaların statusudur (bir sorğu).
    blocking_statuses = (OPEN_STATUSES - {SyllabusStatus.DRAFT.value}) | {SyllabusStatus.APPROVED.value}
    blocking = target.versions.filter(status__in=sorted(blocking_statuses)).exists()
    return CODE_TARGET_LOCKED if blocking else ""


def same_slot(source, *, organization_id, subject_id, period_id) -> bool:
    """Eyni təşkilat + fənn + semestr (qonşu tərifi)."""
    return (
        source.organization_id == organization_id
        and source.subject_id == subject_id
        and source.period_id is not None
        and source.period_id == period_id
    )


def previous_slot(source, *, organization_id, subject_id, period_id) -> bool:
    """«Keçən ildən köçür» mənbəyi: eyni təşkilat + fənn, BAŞQA semestr və ya semestrsiz baza."""
    return (
        source.organization_id == organization_id
        and source.subject_id == subject_id
        and (source.period_id is None or source.period_id != period_id)
    )


def effective_chair_unit_id(syllabus, memo=None):
    """Təsdiq marşrutunun GÖRDÜYÜ kafedra — ``units.ensure_chair_unit`` ilə eyni həll, YAZISIZ.

    Köhnə (köçürülmüş) dosyelərdə ``chair_unit`` ixtisasa/fakültəyə işarə edir;
    yeni versiya açılanda ``ensure_chair_unit`` onu özü kafedraya çəkir
    (struktur əcdadı → müəllifin kafedra üzvlüyü).  Bağlamanın «eyni kafedra»
    şərti həmin EFFEKTİV kafedra ilə tutuşdurulmalıdır, əks halda köhnə dosyeyə
    bağlanma səhvən «fərqli kafedra» ilə rədd olunurdu.  ``memo`` —
    ``{(chair_unit_id, author_id): effektiv_id}`` (siyahıda sətir başına sorğu olmasın).
    """
    from .units import is_chair_unit, resolve_syllabus_chair_unit

    if syllabus is None:
        return None
    key = (syllabus.chair_unit_id, syllabus.author_id)
    if memo is not None and key in memo:
        return memo[key]
    current = syllabus.chair_unit if syllabus.chair_unit_id else None
    if is_chair_unit(current):
        result = current.pk
    else:
        resolved = resolve_syllabus_chair_unit(
            unit=current, author=syllabus.author, organization=syllabus.organization_id
        )
        result = resolved.pk if resolved is not None else syllabus.chair_unit_id
    if memo is not None:
        memo[key] = result
    return result


def link_code(
    source,
    *,
    actor,
    target_hours,
    target_chair_unit_id,
    target=None,
    target_code=None,
    source_chair_unit_id=None,
) -> str:
    """Bağlamanın qadağa səbəbi (``""`` — bağlamaq olar). Bax modul docstring-i.

    Kafedra müqayisəsi EFFEKTİV kafedra ilədir (``effective_chair_unit_id``);
    çağıran onu əvvəlcədən hesablayıbsa ``source_chair_unit_id`` ilə ötürür.
    """
    if not is_author(actor, source):
        return CODE_NOT_OWN
    approved = getattr(source, "approved_version", None)
    if approved is None or approved.status != SyllabusStatus.APPROVED.value:
        return CODE_SOURCE_NOT_APPROVED
    if approved.approval_source != ApprovalSource.HUMAN.value:
        return CODE_SOURCE_NOT_HUMAN
    if not normalize_hours(target_hours):
        return CODE_HOURS_UNKNOWN
    if not hours_match(approved.plan_hours, target_hours):
        return CODE_HOURS_DIFFER
    if source_chair_unit_id is None:
        source_chair_unit_id = effective_chair_unit_id(source)
    if source_chair_unit_id != target_chair_unit_id:
        return CODE_CHAIR_DIFFERS
    return target_state_code(target) if target_code is None else target_code


def copy_code(source, *, actor, target=None, target_code=None, copyable=None) -> str:
    """Kopyalamanın qadağa səbəbi (``""`` — kopyalamaq olar)."""
    if copyable is None:
        copyable = is_author(actor, source) or actor.covers_unit(source.chair_unit_id, PERM_EDIT)
    if not (actor.has(PERM_EDIT) and copyable):
        return CODE_COPY_OUT_OF_SCOPE
    if source.current_version_id is None and source.approved_version_id is None:
        return CODE_BASE_MISSING
    return target_state_code(target) if target_code is None else target_code


def reuse_origin(version):
    """``reuse`` damğalı versiyanın mənbəyi (UI «Təsdiq: <qrup> sillabusundan» üçün).

    Qayıdış ``None`` (adi təsdiq) və ya ``{group, source_syllabus_id, source_version,
    approved_by, approved_at}`` — ``approved_by`` MƏNBƏNİN insan təsdiqləyənidir,
    hədəfin deyil (hədəfdə təsdiqləyən uydurulmur).
    """
    if version is None or getattr(version, "approval_source", "") != ApprovalSource.REUSE.value:
        return None
    base = version.source_version if version.source_version_id else None
    syllabus = base.syllabus if base is not None else None
    offering = syllabus.offering if syllabus is not None and syllabus.offering_id else None
    group = offering.group if offering is not None and offering.group_id else None
    return {
        "group": (getattr(group, "name", "") or "") if group is not None else "",
        "source_syllabus_id": getattr(syllabus, "pk", None),
        "source_version": base,
        "approved_by": getattr(base, "approved_by", None) if base is not None else None,
        "approved_at": getattr(base, "approved_at", None) if base is not None else None,
    }


def _own_q(actor) -> Q:
    return own_q(actor)


def _copyable_annotation(actor):
    """``copy_from_previous`` qapısının SQL qarşılığı — sətir başına sorğu YOX."""
    own = _own_q(actor)
    if not actor.has(PERM_EDIT):
        return Value(0, output_field=IntegerField())
    if actor.is_superadmin:
        return Value(1, output_field=IntegerField())
    scope = actor.scope_for(PERM_EDIT)
    if scope.is_org_wide:
        return Value(1, output_field=IntegerField())
    condition = own
    if scope.is_unit_scoped:
        condition = own | scope.unit_subtree_q(path_field="chair_unit__path", id_field="chair_unit__id")
    return Case(When(condition, then=Value(1)), default=Value(0), output_field=IntegerField())


def _copyable_roots(*, organization, actor, subject_ids):
    """Aktorun KOPYALAYA bildiyi kök dosyelər (``copy_from_previous`` qapısı, SQL-də)."""
    queryset = Syllabus.objects.filter(
        organization=organization, is_active=True, subject_id__in=list(subject_ids), reused_from__isnull=True
    ).filter(Q(current_version__isnull=False) | Q(approved_version__isnull=False))
    return _scope_filter(queryset, actor).annotate(_copyable=_copyable_annotation(actor)).filter(_copyable=1)


def previous_source_pairs(*, organization, actor, subject_ids) -> set:
    """``{(fənn_id, semestr_id|None)}`` — «Keçən ildən köçür» düyməsinin göstərilməsi üçün TƏK sorğu.

    Çağıran tərəf açılışın semestrindən FƏRQLİ cütə baxır (bax ``has_previous``).
    """
    if organization is None or not subject_ids or not actor.has(PERM_EDIT):
        return set()
    rows = _copyable_roots(organization=organization, actor=actor, subject_ids=subject_ids)
    return set(rows.order_by().values_list("subject_id", "period_id").distinct())


def has_previous(pairs, *, subject_id, period_id) -> bool:
    """Cütlər arasında bu fənnin BAŞQA semestrə (və ya bazaya) aid mənbəyi varmı."""
    return any(subject == subject_id and period != period_id for subject, period in pairs)


def previous_queryset(*, organization, actor, subject_id, period_id, limit: int = 20):
    """«Keçən ildən köçür» mənbələri — kopyalana bilən, BAŞQA semestrdəki (və ya baza) dosyelər.

    Sıra: öz dosyesi → ən yeni semestr (baza sonda) → təsdiqlənmiş → ən təzəsi. TƏK sorğu.
    """
    if organization is None or subject_id is None:
        return Syllabus.objects.none()
    queryset = _copyable_roots(organization=organization, actor=actor, subject_ids=[subject_id])
    if period_id is not None:
        queryset = queryset.exclude(period_id=period_id)
    own = Case(When(_own_q(actor), then=Value(1)), default=Value(0), output_field=IntegerField())
    approved_rank = Case(
        When(approved_version__status=SyllabusStatus.APPROVED.value, then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )
    return (
        queryset.select_related(
            "subject",
            "period",
            "offering",
            "offering__group",
            "author",
            "approved_version",
            "approved_version__approved_by",
            "current_version",
        )
        .annotate(_own=own, _approved_rank=approved_rank)
        .order_by("-_own", F("period__start_date").desc(nulls_last=True), "_approved_rank", "-updated_at", "pk")[:limit]
    )


def sibling_queryset(*, organization, actor, subject_id, period_id, exclude_syllabus_id=None, exclude_offering_id=None):
    """Qonşu dosyelər — TƏK sorğu (oxu qapısı + annotasiyalar + select_related).

    Sıra: əvvəl aktorun ÖZ sillabusları, sonra təsdiqlənmişlər, sonra ən təzəsi.
    ``_linked`` — bu mənbəyə bağlı aktiv dosyelərin sayı.
    """
    if organization is None or subject_id is None or period_id is None:
        return Syllabus.objects.none()
    queryset = Syllabus.objects.filter(
        organization=organization,
        is_active=True,
        subject_id=subject_id,
        period_id=period_id,
        reused_from__isnull=True,
    )
    if exclude_syllabus_id is not None:
        queryset = queryset.exclude(pk=exclude_syllabus_id)
    if exclude_offering_id is not None:
        queryset = queryset.exclude(offering_id=exclude_offering_id)
    queryset = _scope_filter(queryset, actor)
    own = Case(When(_own_q(actor), then=Value(1)), default=Value(0), output_field=IntegerField())
    approved_rank = Case(
        When(approved_version__status=SyllabusStatus.APPROVED.value, then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )
    return (
        queryset.select_related(
            "subject",
            "offering",
            "offering__group",
            "author",
            "chair_unit",
            "approved_version",
            "approved_version__approved_by",
            "current_version",
        )
        .annotate(
            _own=own,
            _copyable=_copyable_annotation(actor),
            _approved_rank=approved_rank,
            _linked=Count("reused_by", filter=Q(reused_by__is_active=True), distinct=True),
        )
        .order_by("-_own", "_approved_rank", "-updated_at", "pk")
    )


__all__ = [
    "CODE_BASE_MISSING",
    "CODE_CHAIR_DIFFERS",
    "CODE_COPY_OUT_OF_SCOPE",
    "CODE_HOURS_DIFFER",
    "CODE_HOURS_UNKNOWN",
    "CODE_LINKED_UNLINK_FIRST",
    "CODE_NOT_LINKED",
    "CODE_NOT_OWN",
    "CODE_NOT_PREVIOUS",
    "CODE_NOT_SIBLING",
    "CODE_SOURCE_NOT_APPROVED",
    "CODE_SOURCE_NOT_HUMAN",
    "CODE_TARGET_LINKED",
    "CODE_TARGET_LOCKED",
    "CODE_UP_TO_DATE",
    "REASON_CODES",
    "copy_base",
    "copy_code",
    "effective_chair_unit_id",
    "has_previous",
    "hours_match",
    "hours_rows",
    "link_base",
    "link_code",
    "normalize_hours",
    "previous_queryset",
    "previous_slot",
    "previous_source_pairs",
    "reuse_origin",
    "reuse_root",
    "same_slot",
    "sibling_queryset",
    "target_state_code",
]
