"""Köçürülmüş imtahan nəticələrinin dəqiqləşdirilməsi — OXU qatı (İmtahan Mərkəzi).

Bu modul «hansı köhnə nəticə baxılmalıdır» sualına cavab verir. Cavab HƏMİŞƏ
bazadakı sübut qatından (``LegacyGradeFact`` + canlı ``FinalGrade`` güzgüsü)
hesablanır — heç bir sətir siyahısı, TSV və ya ID dəsti kodda saxlanmır. Səbəb:
köçürmə repetisiyaları təkrarlanır, hər dəfə UUID-lər dəyişir; kodda dondurulan
siyahı növbəti repetisiyada səssizcə yalan danışardı.

KATEQORİYA NECƏ DOĞULUR
-----------------------
İki mənbədən, hər ikisi sübut qatının ÖZ dəyəridir:

1. **Uyğunlaşdırma statusundan** — :class:`LegacyGradeMappingStatus`-un
   ``linked``-dən başqa hər üzvü avtomatik bir kateqoriyaya çevrilir
   (:func:`category_specs` enum üzərində dövr edir). Enum-a yeni üzv əlavə
   olunsa, kateqoriya BU MODULA TOXUNMADAN siyahıda peyda olur.
2. **Faktın öz xam dəyərlərindən** — diapazon, canlı balla fərq, kəsilmə halında
   imtahan balının mövcudluğu. Bunlar enum dəyəri deyil, ona görə predikat kimi
   yazılıb; hər biri YALNIZ faktın öz sütunlarına və canlı ``FinalGrade``-ə baxır.

⚠️ «Bal cəmi / 100 bal bölgüsü» mövzusuna QƏSDƏN toxunulmur: burada heç bir
kateqoriya ``yekun = giriş + imtahan`` kimi arifmetika QURMUR. «İmtahan balı
yekunla uyğun deyil» halı da düstur yolu ilə deyil, **canlı sistemdəki
``FinalGrade.exam_score`` ilə müqayisə** yolu ilə tapılır — yəni köçürmənin
özünün dəqiqliyi ölçülür, universitetin qiymətləndirmə qaydası yox.

⚠️ Sübut qatı APPEND-ONLY qalır: bu modul heç nə yazmır. Yazı
``legacy_grade_review_actions``-dadır və o da yalnız YENİ sətir yaradır.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import NamedTuple

from django.db.models import F, FilteredRelation, Q, Subquery, Window
from django.db.models.functions import RowNumber
from django.utils.translation import pgettext_lazy

from .grading_scale import bands_for
from .models import (
    LegacyGradeFact,
    LegacyGradeMappingStatus,
    LegacyGradeReview,
    LegacyGradeReviewDecision,
)
from .models.legacy_grade import LEGACY_GRADE_REVIEW_PERMISSION

# Tərcümə konteksti hər çağırışda HƏRFİ sətirdir, dəyişən DEYİL: ``xgettext``
# ``pgettext``-in kontekst arqumentini yalnız hərfi sətir olanda oxuya bilir —
# dəyişən verilsə sətri SƏSSİZCƏ atır və mətn heç bir dilə çıxmır.

# ── Köhnə mənbənin öz bal hədləri ────────────────────────────────────────────
#
# Bu hədlər cari sistemin qiymətləndirmə sxemi DEYİL — köçürməni aparan
# ``apps/legacy_import/services/rehearsal_legacy_grade_facts_source.py``-dakı
# ``_score_range_rules`` funksiyasının işlətdiyi MƏNBƏ hədləridir. Ora birbaşa
# import etmirik: ``registrar → legacy_import`` yeni modul-sərhəd tili (və dövr)
# açardı. Əvəzində dəyərlərin eyni qalması testlə kilidlənir
# (``test_legacy_grade_review.py::test_source_bounds_match_importer``) — yəni
# həqiqət mənbəyi yenə importerdir, sadəcə qapı testdən keçir.
#
# Təkrar-imtahan da mənbənin imtahan xanası ilə eyni 0..50 şkalasındadır.
# İmporter bunu ayrıca ``resit`` arqumenti ilə yoxlayır; aşağıdakı güzgü
# dəyərlərin eyni qalmasını test kilidləyir.
LEGACY_ENTRY_MAX = Decimal("50")
LEGACY_EXAM_MAX = Decimal("50")
LEGACY_RESIT_MAX = Decimal("50")
LEGACY_FINAL_MAX = Decimal("100")


class Severity:
    """Şiddət — YALNIZ sıralama və süzgəc üçün; icazəyə təsiri yoxdur."""

    CRITICAL = "critical"
    WARN = "warn"
    WATCH = "watch"


SEVERITY_ORDER = (Severity.CRITICAL, Severity.WARN, Severity.WATCH)

SEVERITY_LABELS = {
    Severity.CRITICAL: pgettext_lazy("registrar.legacy_grade_review", "Kritik"),
    Severity.WARN: pgettext_lazy("registrar.legacy_grade_review", "Diqqət"),
    Severity.WATCH: pgettext_lazy("registrar.legacy_grade_review", "İzlənilir"),
}

# Uyğunlaşdırma statusundan doğan kateqoriyaların şiddəti. Xəritədə OLMAYAN yeni
# enum üzvü `WATCH` alır — yəni enum genişlənəndə kateqoriya itmir, sadəcə ən
# aşağı şiddətlə görünür (fail-visible, fail-silent deyil).
_STATUS_SEVERITY = {
    LegacyGradeMappingStatus.CONFLICT: Severity.CRITICAL,
    LegacyGradeMappingStatus.UNRESOLVED: Severity.WATCH,
    LegacyGradeMappingStatus.GROUP_MISMATCH: Severity.WATCH,
    LegacyGradeMappingStatus.DISCARDED_SOURCE: Severity.WATCH,
}

# Statusdan doğan kateqoriyaların insan dilində izahı (nə etməli).
_STATUS_HINTS = {
    LegacyGradeMappingStatus.CONFLICT: pgettext_lazy(
        "registrar.legacy_grade_review",
        "Birləşən jurnallar eyni xanaya fərqli dəyər iddia edib — hədəfdə yalnız "
        "biri qalıb. Kağız jurnalla tutuşdurulmalıdır.",
    ),
    LegacyGradeMappingStatus.UNRESOLVED: pgettext_lazy(
        "registrar.legacy_grade_review",
        "Köhnə sətir heç bir cari qeydiyyata bağlana bilməyib — sahibi müəyyənləşdirilməlidir.",
    ),
    LegacyGradeMappingStatus.GROUP_MISMATCH: pgettext_lazy(
        "registrar.legacy_grade_review", "Tələbənin köhnə jurnaldakı qrupu cari qeydiyyatı ilə üst-üstə düşmür."
    ),
    LegacyGradeMappingStatus.DISCARDED_SOURCE: pgettext_lazy(
        "registrar.legacy_grade_review",
        "Mənbə jurnal köhnə sistemdə silinmiş sayılıb — dəyəri rəsmi qəbul edilməzdən əvvəl yoxlanmalıdır.",
    ),
}

# Xam dəyərdən doğan kateqoriyaların kodları (enum üzvü deyil, ona görə sabitdir).
CATEGORY_LIVE_MISMATCH = "live_exam_mismatch"
CATEGORY_OUT_OF_RANGE = "out_of_range"
CATEGORY_FAILED_WITH_EXAM = "failed_with_exam_score"


class CategorySpec(NamedTuple):
    """Bir dəqiqləşdirmə kateqoriyası: kod, etiket, şiddət və SQL şərti."""

    code: str
    label: object
    hint: object
    severity: str
    source: str  # "mapping_status" | "raw_value" — kateqoriyanın haradan gəldiyi
    condition: Q


def pass_threshold(organization) -> Decimal:
    """Təşkilatın öz hərf şkalasından «kəsilmə» həddi (sabit 51 DEYİL).

    Şkala tenant-konfiqurasiyalıdır (``grading_scale.bands_for``); ən aşağı
    keçid bantının həddini götürürük, yəni universitet şkalanı dəyişsə bu
    kateqoriya da onunla birlikdə sürüşür.
    """
    bands = bands_for(organization)
    # Sonuncu bant həmişə 0-dır (kəsilmə bantı); ondan bir yuxarısı ən aşağı keçid.
    return Decimal(bands[-2][0]) if len(bands) >= 2 else Decimal("51")


def _out_of_range_condition() -> Q:
    """Xam dəyər mənbənin öz hədlərindən kənardadırmı (NULL sahə iştirak etmir)."""
    condition = Q(pk__in=())
    for field, ceiling in (
        ("entry_score", LEGACY_ENTRY_MAX),
        ("exam_score", LEGACY_EXAM_MAX),
        ("resit_score", LEGACY_RESIT_MAX),
        ("final_score", LEGACY_FINAL_MAX),
    ):
        condition |= Q(**{f"{field}__lt": Decimal("0")}) | Q(**{f"{field}__gt": ceiling})
    return condition


# ── Qərardan sonra da növbədə qalmaq («yapışqan» kateqoriya) ─────────────────
#
# Kateqoriyaların əksəriyyəti ``LegacyGradeFact``-ın ÖZ sütunundan doğulur; fakt
# append-only olduğuna görə onlar qərardan sonra da avtomatik doğru qalır.
# Yeganə istisna ``live_exam_mismatch``-dır: o, canlı ``FinalGrade``-lə
# müqayisədən doğulur, yəni düzəliş tətbiq olunan an şərt pozulur. Heç nə
# etməsək düzəldilmiş sətir növbədən TAMAM yox olardı — «Düzəldilib» süzgəci
# boş qalar, irəlişiş məxrəci isə iş gördükcə kiçilərdi (sahibin istədiyi
# «N-dən M-i baxılıb» göstəricisi geriyə sürüşərdi).
#
# Ona görə qərar anında faktın hansı kateqoriyalarda olduğu ``LegacyGradeReview
# .category_codes``-a möhürlənir və canlı-mənbəli kateqoriya həmin möhürü də
# qəbul edir. Möhür kateqoriya-DƏQİQ-dir: başqa səbəbdən düzəldilmiş sətir bu
# çipin sayğacına sızmır.

CATEGORY_CODE_SEPARATOR = "|"


def encode_category_codes(codes) -> str:
    """``("a", "b")`` → ``"|a|b|"`` — kənar ayırıcı dəqiq uyğunluq üçündür."""
    unique: list[str] = []
    for code in codes:
        if code and code not in unique:
            unique.append(code)
    if not unique:
        return ""
    return CATEGORY_CODE_SEPARATOR + CATEGORY_CODE_SEPARATOR.join(unique) + CATEGORY_CODE_SEPARATOR


def decode_category_codes(value) -> tuple[str, ...]:
    return tuple(part for part in str(value or "").split(CATEGORY_CODE_SEPARATOR) if part)


def _reviewed_fact_ids(organization, *, code: str = ""):
    """Qərar verilmiş faktların id-ləri — KORRELYASİYASIZ alt-sorğu.

    ``Exists(fact_id=OuterRef("pk"))`` yazsaydıq Postgres bu alt-sorğunu hər
    sətir üçün bir dəfə (169 min dəfə) icra edərdi. ``pk__in`` isə korrelyasiya
    daşımır: qərar cədvəli BİR DƏFƏ oxunub hash-lənir, sonra hər fakt həmin
    hash-dən yoxlanır. Nəticə eynidir, qiymət isə iki tərtib ucuzdur.
    """
    queryset = LegacyGradeReview.objects.filter(organization=organization)
    if code:
        queryset = queryset.filter(
            category_codes__contains=f"{CATEGORY_CODE_SEPARATOR}{code}{CATEGORY_CODE_SEPARATOR}",
        )
    return queryset.values("fact_id")


def reviewed_condition(organization) -> Q:
    """«Bu fakta ən azı bir qərar yazılıb» — sayğac və status süzgəcinin şərti."""
    return Q(pk__in=_reviewed_fact_ids(organization))


def _reviewed_under(organization, code: str) -> Q:
    """«Bu fakt məhz BU kateqoriya üçün baxılıb» — yapışqan kateqoriya möhürü."""
    return Q(pk__in=_reviewed_fact_ids(organization, code=code))


def category_specs(organization) -> tuple[CategorySpec, ...]:
    """Bu təşkilat üçün dəqiqləşdirmə kateqoriyaları — sübut qatından qurulur.

    Sıra: əvvəlcə xam dəyər kateqoriyaları (ən konkret sual), sonra
    uyğunlaşdırma statusundan avtomatik doğulanlar.
    """
    specs = [
        CategorySpec(
            code=CATEGORY_LIVE_MISMATCH,
            label=pgettext_lazy("registrar.legacy_grade_review", "İmtahan balı canlı sistemlə uyğun deyil"),
            hint=pgettext_lazy(
                "registrar.legacy_grade_review",
                "Köhnə sistemin imtahan xanası ilə cari sistemdəki imtahan balı fərqlidir — "
                "köçürmə bu sətirdə dəyəri dəyişib.",
            ),
            severity=Severity.CRITICAL,
            source="raw_value",
            # Annotasiya üzərində süzülür (bax `annotated_facts`). Sonuncu şərt
            # «yapışqan» hissədir: düzəliş canlı balı faktla üst-üstə salandan
            # sonra da sətir öz kateqoriyasında qalır (bax `_reviewed_under`).
            condition=(
                Q(exam_score__isnull=False, live__exam_score__isnull=False) & ~Q(exam_score=F("live__exam_score"))
            )
            | _reviewed_under(organization, CATEGORY_LIVE_MISMATCH),
        ),
        CategorySpec(
            code=CATEGORY_OUT_OF_RANGE,
            label=pgettext_lazy("registrar.legacy_grade_review", "Bal diapazondan kənardır"),
            hint=pgettext_lazy(
                "registrar.legacy_grade_review",
                "Köhnə sistemdəki xam dəyər mənbənin öz hədlərini aşır — dəyər olduğu kimi "
                "saxlanıb, çünki sübut qatı yuvarlaqlaşdırma etmir.",
            ),
            severity=Severity.CRITICAL,
            source="raw_value",
            condition=_out_of_range_condition(),
        ),
        CategorySpec(
            code=CATEGORY_FAILED_WITH_EXAM,
            label=pgettext_lazy("registrar.legacy_grade_review", "Kəsilib, amma imtahan balı var"),
            hint=pgettext_lazy(
                "registrar.legacy_grade_review",
                "Köhnə yekun kəsilmə həddindən aşağıdır, buna baxmayaraq imtahan xanasında "
                "bal yazılıb — birinin səhv olduğu aydındır.",
            ),
            severity=Severity.WARN,
            source="raw_value",
            condition=Q(
                final_score__isnull=False,
                final_score__lt=pass_threshold(organization),
                exam_score__isnull=False,
                exam_score__gt=Decimal("0"),
            ),
        ),
    ]
    # Uyğunlaşdırma statusundan AVTOMATİK doğulanlar — siyahı enum-dan gəlir.
    for status in LegacyGradeMappingStatus:
        if status == LegacyGradeMappingStatus.LINKED:
            continue  # sağlam hal — dəqiqləşdirmə tələb etmir
        specs.append(
            CategorySpec(
                code=str(status.value),
                label=status.label,
                hint=_STATUS_HINTS.get(
                    status, pgettext_lazy("registrar.legacy_grade_review", "Uyğunlaşdırma nəticəsi yoxlanmalıdır.")
                ),
                severity=_STATUS_SEVERITY.get(status, Severity.WATCH),
                source="mapping_status",
                condition=Q(mapping_status=status),
            )
        )
    return tuple(specs)


def category_map(organization) -> dict[str, CategorySpec]:
    return {spec.code: spec for spec in category_specs(organization)}


def matched_category_codes(*, organization, fact_id) -> tuple[str, ...]:
    """Faktın HAZIRDA hansı kateqoriyalarda olduğu — qərar möhürü üçün.

    Qərar YAZILMAZDAN ƏVVƏL çağırılır: düzəliş canlı balı dəyişdikdən sonra
    ``live_exam_mismatch`` şərti artıq doğru olmazdı və möhür boş qalardı.
    """
    base = annotated_facts(organization=organization).filter(pk=fact_id)
    return tuple(spec.code for spec in category_specs(organization) if base.filter(spec.condition).exists())


# ── Aktorun əhatəsi ──────────────────────────────────────────────────────────


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def actor_scope(user, organization):
    """``final_score.entry`` üzrə struktur əhatəsi (model qatı ilə EYNİ açar)."""
    from django.apps import apps as django_apps

    org_unit = django_apps.get_model("organizations", "OrgUnit")
    return org_unit.user_permission_scope(user, organization, LEGACY_GRADE_REVIEW_PERMISSION)


def can_review(user, organization) -> bool:
    """Yoxlama qərarı yaza bilərmi — ``LegacyGradeReview.clean`` ilə eyni qapı.

    Burada təkrar yoxlamaq «səssiz 403» qarşısını alır: səth düyməni yalnız
    həqiqətən işləyəcəksə göstərir. Son söz yenə modeldədir (fail-closed).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if _is_superadmin(user):
        return True
    if organization is None or not getattr(organization, "is_active", False):
        return False
    if organization.owner_id == user.pk:
        return True
    return actor_scope(user, organization).has_structure_access


def unit_subtree_ids(organization, unit_id):
    """Fakültə/kafedra/ixtisas/qrup alt-ağacı — tanınmayan id BOŞ siyahı verir."""
    from django.apps import apps as django_apps

    org_unit = django_apps.get_model("organizations", "OrgUnit")
    unit = org_unit.objects.filter(organization=organization, pk=unit_id).only("id", "path").first()
    if unit is None:
        return []
    condition = Q(pk=unit.pk)
    if unit.path:
        condition |= Q(path__startswith=f"{unit.path}/")
    return list(org_unit.objects.filter(organization=organization).filter(condition).values_list("pk", flat=True))


# ── Sorğu ────────────────────────────────────────────────────────────────────


def annotated_facts(*, organization, user=None):
    """Təşkilatın bütün faktları + canlı bal güzgüsü.

    ``live_exam_score`` cari ``FinalGrade.exam_score``-dur: köçürmənin dəqiqliyi
    məhz onunla müqayisədə ölçülür.

    NİYƏ JOIN, NİYƏ SUBQUERY YOX
    ----------------------------
    Əvvəl bu güzgü korrelyasiyalı skalyar ``Subquery`` idi. O, süzgəcin ÖZ
    şərtinə düşdüyünə görə Postgres onu HƏR fakt üçün ayrıca icra edirdi — 169
    min sətir × 2 alt-plan. Tək bir ``COUNT`` bir milyondan çox bufer toxunuşu
    edirdi.

    ``FinalGrade.enrollment`` **OneToOne**-dur (bazada unikal), ona görə LEFT
    JOIN sətir ÇOXALDA BİLMİR — join ilə subquery burada riyazi olaraq eyni
    cavabı verir, amma cədvəllər bir dəfə oxunub hash-lənir.

    Elan olunan tip məsələsi də bununla YOX OLUR: artıq annotasiya sütunun
    ÖZÜNƏ istinad edir, deməli miqyas həmişə sütunun öz miqyasıdır (əvvəl bu,
    əl ilə təkrarlanan ``DecimalField`` elanı tələb edirdi).
    """
    queryset = (
        LegacyGradeFact.objects.filter(organization=organization)
        .annotate(
            live=FilteredRelation(
                "enrollment__final_grade",
                condition=Q(enrollment__final_grade__organization=organization),
            )
        )
        .annotate(live_exam_score=F("live__exam_score"))
    )
    if user is not None and not _is_superadmin(user):
        scope = actor_scope(user, organization)
        if not scope.has_structure_access:
            return queryset.none()
        if not scope.is_org_wide:
            # Unit-scoped aktor (dekan/kafedra müdiri) yalnız öz alt-ağacını görür.
            # Qeydiyyatı olmayan fakt struktura bağlana bilmir → onlara görünmür.
            from django.apps import apps as django_apps

            org_unit = django_apps.get_model("organizations", "OrgUnit")
            unit_ids = org_unit.objects.filter(organization=organization).filter(scope.unit_subtree_q()).values("pk")
            queryset = queryset.filter(enrollment__offering__group__in=Subquery(unit_ids))
    return queryset


def review_conditions(organization) -> Q:
    """«Dəqiqləşdirmə tələb edən» faktların BİRLƏŞMİŞ şərti (kateqoriyaların VEYA-sı)."""
    condition = Q(pk__in=())
    for spec in category_specs(organization):
        condition |= spec.condition
    return condition


def review_queue(*, organization, user=None, categories=(), filters=None):
    """Baxış tələb edən faktlar — süzgəclər tətbiq olunmuş queryset.

    ``categories`` boşdursa BÜTÜN kateqoriyalar; tanınmayan kod SƏSSİZCƏ
    atılmır — sadəcə heç nə seçmir, çünki xəritədə yoxdur.
    """
    specs = category_map(organization)
    selected = [specs[code] for code in categories if code in specs] or list(specs.values())
    condition = Q(pk__in=())
    for spec in selected:
        condition |= spec.condition
    queryset = annotated_facts(organization=organization, user=user).filter(condition)
    return apply_filters(queryset, organization=organization, filters=filters or {})


def apply_filters(queryset, *, organization, filters):
    """Struktur, fənn, müəllim, dövr, şiddət və status süzgəcləri.

    Struktur süzgəcləri (fakültə → kafedra → ixtisas → qrup) EYNİ alt-ağac
    məntiqi ilə işləyir, ona görə kaskadın hansı pilləsindən gəldiyinin fərqi
    yoxdur — hamısı ``offering.group``-un ata-ağacına düşür.
    """
    for key in ("faculty", "kafedra", "specialty", "group"):
        unit_id = str(filters.get(key) or "").strip()
        if unit_id:
            queryset = queryset.filter(
                enrollment__offering__group__in=unit_subtree_ids(organization, unit_id),
            )
    subject_id = str(filters.get("subject") or "").strip()
    if subject_id:
        queryset = queryset.filter(enrollment__offering__subject_id=subject_id)
    teacher_id = str(filters.get("teacher") or "").strip()
    if teacher_id:
        queryset = queryset.filter(enrollment__offering__instructor_id=teacher_id)
    period_id = str(filters.get("period") or "").strip()
    if period_id:
        queryset = queryset.filter(enrollment__offering__period_id=period_id)
    year = str(filters.get("year") or "").strip()
    if year:
        queryset = queryset.filter(enrollment__offering__period__name__icontains=year)
    severity = str(filters.get("severity") or "").strip()
    if severity in SEVERITY_ORDER:
        condition = Q(pk__in=())
        for spec in category_specs(organization):
            if spec.severity == severity:
                condition |= spec.condition
        queryset = queryset.filter(condition)
    queryset = _apply_status_filter(queryset, str(filters.get("status") or "").strip(), organization)
    term = str(filters.get("q") or "").strip()
    if term:
        queryset = queryset.filter(
            Q(enrollment__student__first_name__icontains=term)
            | Q(enrollment__student__last_name__icontains=term)
            | Q(enrollment__student__username__icontains=term)
            | Q(enrollment__offering__subject__name__icontains=term)
            | Q(enrollment__offering__subject__code__icontains=term)
            | Q(source_student_ref=term)
        )
    return queryset


#: «Status» süzgəcinin dəyərləri — baxış vəziyyəti (kateqoriya ilə qarışmasın).
STATUS_PENDING = "pending"
STATUS_VERIFIED = "verified"
STATUS_CORRECTED = "corrected"
STATUS_DISPUTED = "disputed"

STATUS_LABELS = {
    STATUS_PENDING: pgettext_lazy("registrar.legacy_grade_review", "Baxılmayıb"),
    STATUS_VERIFIED: pgettext_lazy("registrar.legacy_grade_review", "Təsdiqlənib"),
    STATUS_CORRECTED: pgettext_lazy("registrar.legacy_grade_review", "Düzəldilib"),
    STATUS_DISPUTED: pgettext_lazy("registrar.legacy_grade_review", "Mübahisəli"),
}


def _latest_reviews(organization):
    """Hər faktın son append-only qərarı; tenant-scope və sıra təqdimatla eynidir."""
    ranked_ids = (
        LegacyGradeReview.objects.filter(organization=organization)
        .order_by()
        .annotate(
            _latest_rank=Window(
                expression=RowNumber(),
                partition_by=(F("fact_id"),),
                order_by=(F("created_at").desc(), F("id").desc()),
            )
        )
        .filter(_latest_rank=1)
        .values("pk")
    )
    return LegacyGradeReview.objects.filter(
        organization=organization,
        pk__in=Subquery(ranked_ids),
    ).order_by()


def _apply_status_filter(queryset, status, organization):
    from .legacy_grade_review_actions import REASON_CORRECTED

    if status == STATUS_PENDING:
        return queryset.filter(~reviewed_condition(organization))
    latest = _latest_reviews(organization)
    if status == STATUS_CORRECTED:
        latest = latest.filter(reason_code=REASON_CORRECTED)
    elif status == STATUS_VERIFIED:
        latest = latest.filter(decision=LegacyGradeReviewDecision.VERIFIED).exclude(reason_code=REASON_CORRECTED)
    elif status == STATUS_DISPUTED:
        latest = latest.exclude(reason_code=REASON_CORRECTED).exclude(decision=LegacyGradeReviewDecision.VERIFIED)
    else:
        return queryset
    return queryset.filter(pk__in=Subquery(latest.values("fact_id")))


def progress(*, organization, user=None, filters=None):
    """«N-dən M-i baxılıb» — iş bitdiyini görmək üçün irəliləyiş göstəricisi.

    Sayğac SÜZGƏCLƏ birlikdə hərəkət edir (status süzgəci istisna olmaqla:
    əks halda «baxılmayıb» seçiləndə məxrəc də daralır və faiz həmişə 0 olardı).

    ⚠️ Səth İKİ sayğac dəstini də eyni ekranda göstərir, ona görə ordan
    :func:`legacy_grade_review_counts.queue_counts` çağırılır — bu sarğı yalnız
    tək-göstərici lazım olan yer (və test) üçündür.
    """
    from .legacy_grade_review_counts import queue_counts

    return queue_counts(organization=organization, user=user, filters=filters)["progress"]


def category_counts(*, organization, user=None, filters=None):
    """Hər kateqoriya üçün (ümumi, baxılmış) cütü — süzgəc çipləri üçün."""
    from .legacy_grade_review_counts import queue_counts

    return queue_counts(organization=organization, user=user, filters=filters)["categories"]


def decimal_or_none(value):
    """Mətn/Decimal → Decimal; pozuq dəyər ``None`` (səth heç vaxt çökmür)."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


__all__ = [
    "CATEGORY_CODE_SEPARATOR",
    "CATEGORY_FAILED_WITH_EXAM",
    "CATEGORY_LIVE_MISMATCH",
    "CATEGORY_OUT_OF_RANGE",
    "CategorySpec",
    "LEGACY_ENTRY_MAX",
    "LEGACY_EXAM_MAX",
    "LEGACY_FINAL_MAX",
    "LEGACY_RESIT_MAX",
    "SEVERITY_LABELS",
    "SEVERITY_ORDER",
    "STATUS_LABELS",
    "Severity",
    "actor_scope",
    "annotated_facts",
    "apply_filters",
    "can_review",
    "category_counts",
    "category_map",
    "category_specs",
    "decode_category_codes",
    "decimal_or_none",
    "encode_category_codes",
    "matched_category_codes",
    "pass_threshold",
    "progress",
    "review_conditions",
    "reviewed_condition",
    "review_queue",
    "unit_subtree_ids",
]
