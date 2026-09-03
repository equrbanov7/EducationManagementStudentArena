"""Jurnal siyahısının idarəsi — «alt qrupdan tələbə əlavə et» (guest roster).

NİYƏ YENİ MODEL YOXDUR (qərar, 2026-08)
───────────────────────────────────────
Jurnal sətirləri qrupdan DEYİL, ``offering.enrollments``-dan qurulur (bax
:func:`apps.registrar.gradebook.get_offering_journal`). Yəni «başqa qrupdan
tələbə» əslində **həmin açılışa əlavə qeydiyyatdır**. Ona görə ayrıca
``GuestEnrollment`` modeli yaradılmır — o, hər jurnal səthini (grid, export,
analitika, transkript, imtahan körpüsü, düzəliş axını) iki mənbənin
birləşməsinə məcbur edərdi. Əvəzinə mövcud :class:`~apps.registrar.models.Enrollment`
sətrinə MƏNBƏ işarəsi əlavə olunub:

* ``source_group``  — tələbənin öz qrupu (doludursa sətir «alt qrup»dur),
* ``added_by`` / ``added_at`` — kim, nə vaxt əlavə etdi.

Beləliklə:

* tələbə **yalnız həmin açılışın** jurnalında görünür (qeydiyyat offering-ə
  bağlıdır — eyni fənnin başqa qrup jurnalına təsir etmir);
* onun balı/davamiyyəti yalnız bu açılışa aiddir (``LessonMark`` → enrollment);
* öz qrupunun jurnalları toxunulmaz qalır;
* təkrar əlavə mümkün deyil — mövcud ``uniq_student_offering`` unikal
  məhdudiyyəti (organization, student, offering) onsuz da qadağan edir.

İCAZƏ VƏ ƏHATƏ
──────────────
Əməl müəllimin deyil — koordinator/dekanlıq səviyyəsindədir:
:data:`ROSTER_PERMISSION` (``journal.roster``). Əhatə mövcud struktur-scope
məntiqinə tabedir (``OrgUnit.user_permission_scope``): aktor HƏM açılışın
qrupunu, HƏM də tələbənin gəldiyi qrupu öz alt-ağacında görməlidir. Org-wide
rollar (rektor/RİM/superadmin) məhdudiyyətsizdir. Fail-closed.

DONDURULMUŞ JURNAL / KEÇMİŞ DÖVR
────────────────────────────────
Siyahı dəyişikliyi TARİXİ DATANI toxunulmaz saxlamalıdır: köçürülmüş köhnə
semestrlərin jurnalları da bu səthdə görünə bilir, ona görə hər iki mutasiya
:func:`assert_roster_open` qapısından keçir:

* **kilid** — mövcud, paylaşılan qapı :func:`gradebook.journal_is_locked`
  (RİM-in bağladığı / yayımlanmış jurnal). Yeni meyar İCAD OLUNMUR ki, davranış
  qalan jurnal mutasiya yolları (dərs, xana, komponent, rubrika, yekun, düzəliş)
  ilə eyni olsun;
* **dövr** — dəyişiklik yalnız AKTİV CARİ akademik dövrdə mümkündür. Meyar
  rəsmi qrup köçürməsininki ilə eynidir (:func:`apps.registrar.transfer.
  _validate_scope`): ``period.is_current and period.is_active``. Bağlı/keçmiş
  semestrə əlavə tələbənin TRANSKRİPTİNİ dəyişərdi — qadağandır.

Qapı HƏM servis, HƏM HTTP qatındadır: səthi (düyməni) gizlətmək kifayət deyil.

ALT QRUP BİRLƏŞMƏSİ (öz jurnalından azad et)
────────────────────────────────────────────
Mandat fənlər hər qrup üçün avtomatik açılış yaradır — yəni alt qrupun ÖZ
jurnalı onsuz da var və sadə əlavə «bu fənn üzrə artıq başqa jurnalda aktivdir»
qapısına dəyirdi. ``add_guest_student(..., release_source=True)`` bu dalanı
açır: mənbə qeydiyyat ``dropped`` + ``superseded_by`` → hədəf sətir olur (rəsmi
qrup köçürməsinin naxışı; yeni semantika icad olunmur), köhnə bal/davamiyyət
bazada qalır, qayıb saatı isə hədəf jurnala KÖÇÜRÜLÜR. Səbəb məcburidir, audit
tamdır, geri götürmə mənbə qeydiyyatı bərpa edir. Qərarın əsaslandırması:
:mod:`apps.registrar.guest_merge`.

GERİ GÖTÜRMƏ
────────────
Silinmə YOXDUR: sətir ``dropped`` olur (bal/davamiyyət tarixçəsi qalır, grid-dən
düşür), birləşmə ilə azad edilmiş mənbə qeydiyyat BƏRPA olunur və audit yazılır.
Adi (öz qrupundan) tələbə bu yolla ÇIXARILA BİLMƏZ — onun üçün rəsmi qrup
köçürməsi axını var (:mod:`apps.registrar.transfer`).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction, OrgUnitType

from . import guest_merge
from .models import AcademicStatus, Enrollment, EnrollmentKind, StudentAcademicRecord

#: Jurnal siyahısını idarə etmək (alt qrupdan əlavə/geri götürmə) icazəsi.
ROSTER_PERMISSION = "journal.roster"

_CTX = "registrar.guest_roster"


# ── Dondurulmuş jurnal / keçmiş dövr qapısı ──────────────────────────────────


def period_allows_roster(period) -> bool:
    """Akademik dövr siyahı dəyişikliyinə açıqdırmı (fail-closed).

    Meyar UYDURULMUR — rəsmi qrup köçürməsi (:mod:`apps.registrar.transfer`)
    ilə EYNİDİR: yalnız AKTİV CARİ dövr. Dövrü olmayan açılış da bağlı sayılır.
    """
    return bool(getattr(period, "is_current", False) and getattr(period, "is_active", False))


def roster_block_reason(offering) -> str:
    """Siyahı dəyişikliyi qadağandırsa səbəb mətni, açıqdırsa boş sətir."""
    from apps.registrar import gradebook

    if gradebook.journal_is_locked(offering):
        return pgettext(_CTX, "Jurnal bağlanıb — siyahısı dəyişdirilə bilməz.")
    if not period_allows_roster(getattr(offering, "period", None)):
        return pgettext(
            _CTX,
            "Bu semestr bağlıdır — keçmiş dövrün jurnalına tələbə əlavə etmək və ya çıxarmaq olmaz.",
        )
    return ""


def roster_is_open(offering) -> bool:
    """Bu açılışın siyahısı hazırda dəyişdirilə bilirmi (kilid + dövr)."""
    return not roster_block_reason(offering)


def assert_roster_open(offering):
    """Qapı — bağlıdırsa istifadəçiyə göstərilə bilən ``ValidationError``."""
    reason = roster_block_reason(offering)
    if reason:
        raise ValidationError(reason)


# ── İcazə + əhatə ────────────────────────────────────────────────────────────


def _scope(user, organization):
    from django.apps import apps as django_apps

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    return org_unit_model.user_permission_scope(user, organization, ROSTER_PERMISSION)


def can_manage_roster(user, organization) -> bool:
    """``journal.roster`` aktora struktur əhatəsi verirmi (org və ya unit)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    return _scope(user, organization).has_structure_access


def can_manage_offering_roster(user, offering) -> bool:
    """Aktor MƏHZ bu açılışın siyahısını idarə edə bilirmi (fail-closed)."""
    organization = offering.organization
    if not can_manage_roster(user, organization):
        return False
    return unit_in_scope(user, organization, offering.group_id)


def unit_in_scope(user, organization, unit_id) -> bool:
    """Verilmiş struktur vahidi aktorun alt-ağacındadırmı."""
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    scope = _scope(user, organization)
    if not scope.has_structure_access:
        return False
    if scope.is_org_wide:
        return True
    if unit_id is None:
        return False
    from django.apps import apps as django_apps

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    return org_unit_model.objects.filter(organization=organization, pk=unit_id).filter(scope.unit_subtree_q()).exists()


def scoped_group_queryset(user, organization):
    """Aktorun seçə biləcəyi AKADEMİK QRUPLAR (fail-closed, alt-ağac üzrə)."""
    from django.apps import apps as django_apps

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    queryset = org_unit_model.objects.filter(organization=organization, is_active=True, unit_type=OrgUnitType.GROUP)
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return queryset
    scope = _scope(user, organization)
    if not scope.has_structure_access:
        return queryset.none()
    return queryset.filter(scope.unit_subtree_q())


# ── Namizəd tələbələr ────────────────────────────────────────────────────────


def enrolled_student_ids(offering) -> set:
    """Bu açılışın jurnalında hazırda AKTİV olan tələbələrin id-ləri."""
    return set(
        Enrollment.objects.filter(
            organization=offering.organization, offering=offering, status=Enrollment.Status.ENROLLED
        ).values_list("student_id", flat=True)
    )


# ── Provenans ≠ cari vəziyyət ────────────────────────────────────────────────
#
# ``Enrollment.source_group`` TARİXİ faktdır və 0056-nın trigger-i ilə write-once-dır
# (audit izi sonradan «düzəldilə» bilməz). Amma jurnaldakı «alt qrup» ÇİPİ tarixi
# yox, CARİ iddiadır: «bu adam başqa qrupdandır». Tələbə sonradan hədəf qrupa
# RƏSMİ köçürüləndə bu iddia YALANA çevrilirdi — sətir sağ qalır, provenans dolu
# qalır və artıq həqiqi G1 tələbəsi «alt qrupdan əlavə olunub: G2» kimi görünürdü.
# Provenansı silmək olmaz (və trigger onsuz da qoymur), ona görə ÇİP ŞƏRTİ dəyişir:
# sətir yalnız tələbənin CARİ qrupu açılışın qrupundan fərqli olduqda qonaqdır.
# Eyni predikat geri götürmə qapısını da idarə edir — əks halda rəsmi köçürmədən
# sonra həqiqi qrup üzvü «qonaq çıxar» yolu ilə jurnaldan atıla bilərdi.


class _Missing:
    pass


_MISSING = _Missing()


def current_group_map(*, organization_id, student_ids) -> dict:
    """``{student_id: cari qrup id}`` — aktiv akademik qeyddən (toplu, N+1 yox)."""
    student_ids = [value for value in student_ids if value]
    if not student_ids:
        return {}
    rows = (
        StudentAcademicRecord.objects.filter(
            organization_id=organization_id, student_id__in=student_ids, is_active=True
        )
        .order_by("student_id", "-created_at")
        .values_list("student_id", "group_id")
    )
    result: dict = {}
    for student_id, group_id in rows:
        result.setdefault(student_id, group_id)
    return result


def row_is_guest(enrollment, *, offering=None, current_group_id=_MISSING) -> bool:
    """Sətir HAZIRDA «alt qrupdan əlavə»dirmi (provenans + cari qrup)."""
    if getattr(enrollment, "source_group_id", None) is None:
        return False
    offering = offering if offering is not None else enrollment.offering
    if offering.group_id is None:
        return True
    if isinstance(current_group_id, _Missing):
        current_group_id = current_group_map(
            organization_id=enrollment.organization_id, student_ids=[enrollment.student_id]
        ).get(enrollment.student_id)
    return current_group_id != offering.group_id


def candidate_records(*, offering, group):
    """*group* qrupunun AKTİV tələbə qeydləri — jurnalda OLANLAR DA daxil.

    Artıq jurnalda olan tələbə siyahıdan QƏSDƏN çıxarılmır (sahibin UX tələbi):
    o görünür, amma seçilə bilmir və səbəbi yazılır — əks halda istifadəçi
    «axtardığım tələbə niyə yoxdur?» sualı ilə qalırdı. Seçilə bilməzliyi HTTP
    qatı ``disabled`` bayrağı ilə işarələyir (:func:`enrolled_student_ids`),
    servis qatı isə :func:`_validate_addition` ilə onsuz da rədd edir — yəni
    görünürlük heç bir icazə/bütövlük qapısını zəiflətmir.
    """
    return (
        StudentAcademicRecord.objects.filter(
            organization=offering.organization,
            group=group,
            is_active=True,
            status=AcademicStatus.ENROLLED,
        )
        .select_related("student", "group")
        .order_by("student__last_name", "student__first_name", "student__username")
    )


def student_label(record) -> str:
    student = record.student
    return (student.get_full_name() or "").strip() or student.username


# ── Əlavə etmə ───────────────────────────────────────────────────────────────


def _record_for(*, offering, student, source_group=None, lock=False):
    """Tələbənin bu əməl üçün UYĞUN akademik qeydi.

    ⚠️ Süzgəc namizəd siyahısı ilə (:func:`candidate_records`) EYNİ olmalıdır:
    ``is_active=True`` **və** ``status=ENROLLED``. Əks halda funksiyanın iki
    fərqli «uyğun tələbə» tərifi olurdu — axtarışda görünməyən (məs. xaric
    edilmiş, amma ``is_active=True`` qalmış) tələbə birbaşa POST ilə jurnala
    salına bilirdi. ``lock=True`` sətri əməl boyunca kilidləyir (TOCTOU: açıq
    modalda tələbənin statusu dəyişə bilər).
    """
    queryset = StudentAcademicRecord.objects.filter(
        organization=offering.organization,
        student=student,
        is_active=True,
        status=AcademicStatus.ENROLLED,
    )
    if lock:
        # ``of=("self",)`` MƏCBURİDİR — nullable FK-lı select_related + FOR UPDATE
        # yalnız PostgreSQL-də çökür.
        queryset = queryset.select_for_update(of=("self",))
    # Tələbənin bir neçə proqram qeydi ola bilər. Çağırış MƏNBƏ qrupu göstəribsə
    # provenans məhz ondan götürülür — əks halda «ən yeni qeyd» seçimi HTTP
    # qatının yoxladığı qrupdan FƏRQLİ qrup yaza bilərdi (audit izi yanlış olardı).
    if source_group is not None:
        queryset = queryset.filter(group=source_group)
    return queryset.select_related("group").order_by("-created_at").first()


def _validate_addition(*, offering, student, record, release_source=False, lock=False):
    """Əlavənin ilkin şərtləri + münaqişəli (öz jurnal) qeydiyyatların siyahısı.

    Münaqişə NORMAL haldır: mandat fənlər hər qrup üçün avtomatik açılış yaradır,
    yəni alt qrupun öz jurnalı onsuz da var. ``release_source=False`` ikən xəta
    mətni istifadəçiyə NƏ ETMƏLİ olduğunu deyir (dalan yox); ``True`` ikən
    münaqişəli sətirlər azad edilə bilən olub-olmadığına görə yoxlanır.
    """
    if record is None or record.group_id is None:
        raise ValidationError(pgettext(_CTX, "Tələbənin aktiv akademik qeydi (qrupu) yoxdur."))
    if offering.group_id is not None and record.group_id == offering.group_id:
        raise ValidationError(
            pgettext(_CTX, "Tələbə onsuz da bu qrupun tələbəsidir — alt qrupdan əlavə tələb olunmur.")
        )
    conflicts = guest_merge.conflicting_enrollments(offering=offering, student=student, lock=lock)
    if not conflicts:
        return []
    if not release_source:
        raise ValidationError(
            pgettext(
                _CTX,
                "Tələbə bu fənn üzrə bu semestrdə öz qrupunun jurnalında aktivdir. "
                "Alt qrup birləşməsi üçün «öz jurnalından azad et» seçimini işarələyin — "
                "əvvəlki qeydiyyat tarixçəyə keçir, bal və davamiyyət saxlanılır.",
            )
        )
    if len(conflicts) > 1:
        raise ValidationError(
            pgettext(
                _CTX,
                "Tələbənin bu fənn üzrə birdən çox aktiv jurnalı var — birləşmə avtomatik aparıla bilməz.",
            )
        )
    for conflict in conflicts:
        guest_merge.assert_releasable(conflict)
    return conflicts


@transaction.atomic
def add_guest_student(*, offering, student, by_user, source_group=None, reason="", release_source=False):
    """Tələbəni BU açılışa alt qrupdan əlavə et (idempotent deyil — təkrar xəta).

    ``source_group`` verilibsə provenans MƏHZ ondan götürülür (HTTP qatı seçilmiş
    qrupu onsuz da yoxlayır); verilməyibsə tələbənin aktiv qeydindən oxunur.

    ``release_source=True`` — ALT QRUP BİRLƏŞMƏSİ: tələbənin öz qrupundakı eyni
    fənn qeydiyyatı tarixçəyə keçir (``dropped`` + ``superseded_by`` → bu sətir)
    və işi bura köçürülür (bax :mod:`apps.registrar.guest_merge`). Bu halda səbəb
    MƏCBURİDİR. Qaytarır: yaradılmış/bərpa edilmiş :class:`Enrollment`.
    """
    if by_user is None or not getattr(by_user, "pk", None):
        raise ValidationError(pgettext(_CTX, "Əməliyyat üçün icraçı tələb olunur."))
    assert_roster_open(offering)
    if release_source:
        reason = guest_merge.validate_reason(reason)
    record = _record_for(offering=offering, student=student, source_group=source_group, lock=True)
    conflicts = _validate_addition(
        offering=offering,
        student=student,
        record=record,
        release_source=release_source,
        lock=True,
    )

    existing = (
        Enrollment.objects.select_for_update(of=("self",))
        .filter(organization=offering.organization, student=student, offering=offering)
        .first()
    )
    now = timezone.now()
    if existing is not None:
        if existing.status == Enrollment.Status.ENROLLED:
            raise ValidationError(pgettext(_CTX, "Bu tələbə artıq jurnaldadır."))
        if existing.superseded_by_id is not None:
            raise ValidationError(
                pgettext(_CTX, "Bu tələbənin burada rəsmi köçürmə tarixçəsi var — inzibati yoxlama tələb olunur.")
            )
        if existing.source_group_id is not None and existing.source_group_id != record.group_id:
            raise ValidationError(pgettext(_CTX, "Əvvəlki əlavənin mənbə qrupu fərqlidir."))
        existing.status = Enrollment.Status.ENROLLED
        if existing.source_group_id is None:
            existing.source_group_id = record.group_id
        existing.added_by = by_user
        existing.added_at = now
        existing.save(update_fields=["status", "source_group", "added_by", "added_at", "updated_at"])
        enrollment = existing
        created = False
    else:
        enrollment = Enrollment.objects.create(
            organization=offering.organization,
            student=student,
            offering=offering,
            kind=EnrollmentKind.MANDATORY,
            status=Enrollment.Status.ENROLLED,
            source_group_id=record.group_id,
            added_by=by_user,
            added_at=now,
        )
        created = True

    _audit(
        enrollment=enrollment,
        offering=offering,
        by_user=by_user,
        action=AuditAction.CREATE if created else AuditAction.UPDATE,
        verb="add",
        old_status="" if created else Enrollment.Status.DROPPED,
        reason=reason,
    )
    # Birləşmə: öz jurnalındakı qeydiyyat tarixçəyə keçir və bu sətrə bağlanır.
    # SIRA vacibdir — `superseded_by` mövcud hədəf sətrə işarə etməlidir.
    for conflict in conflicts:
        guest_merge.release_source(source=conflict, target=enrollment, by_user=by_user, reason=reason)
    if conflicts:
        # Köçürülən qayıb saatı denormallaşmış sayğaca dərhal düşsün («Fənlərim»,
        # analitika və imtahan körpüsü yazı gözləmədən düzgün rəqəmi görsün).
        from apps.registrar import gradebook

        gradebook.recompute_absence_hours(enrollment=enrollment)
    return enrollment


# ── Geri götürmə ─────────────────────────────────────────────────────────────


@transaction.atomic
def remove_guest_student(*, offering, enrollment, by_user, reason=""):
    """Alt qrupdan əlavə olunmuş tələbəni jurnaldan çıxar (soft — tarixçə qalır)."""
    if by_user is None or not getattr(by_user, "pk", None):
        raise ValidationError(pgettext(_CTX, "Əməliyyat üçün icraçı tələb olunur."))
    assert_roster_open(offering)
    enrollment = (
        Enrollment.objects.select_for_update(of=("self",))
        .select_related("student", "source_group")
        .get(pk=enrollment.pk, organization=offering.organization, offering=offering)
    )
    if not row_is_guest(enrollment, offering=offering):
        raise ValidationError(
            pgettext(
                _CTX,
                "Bu tələbə öz qrupunun tələbəsidir — jurnaldan yalnız rəsmi qrup köçürməsi ilə çıxarıla bilər.",
            )
        )
    if enrollment.status != Enrollment.Status.ENROLLED:
        raise ValidationError(pgettext(_CTX, "Bu tələbə artıq jurnalda deyil."))
    enrollment.status = Enrollment.Status.DROPPED
    enrollment.save(update_fields=["status", "updated_at"])
    # Birləşmə geri qaytarılır: tələbə «heç yerdə» qalmasın deyə öz qrupundakı
    # əvəzlənmiş qeydiyyat bərpa olunur (varsa).
    guest_merge.restore_source(target=enrollment, by_user=by_user, reason=reason)
    _audit(
        enrollment=enrollment,
        offering=offering,
        by_user=by_user,
        action=AuditAction.DELETE,
        verb="remove",
        old_status=Enrollment.Status.ENROLLED,
        reason=reason,
    )
    return enrollment


# ── Audit ────────────────────────────────────────────────────────────────────


def _audit(*, enrollment, offering, by_user, action, verb, old_status, reason):
    """Kim, nə vaxt, hansı tələbəni, hansı qrupdan, hansı jurnala — fail-closed."""
    student = enrollment.student
    source = enrollment.source_group
    log_action(
        action=action,
        user=by_user,
        organization=offering.organization,
        obj=enrollment,
        resource_type="registrar.journal_guest",
        resource_id=str(enrollment.pk),
        resource_repr=f"{(student.get_full_name() or student.username)} → {offering.subject.code}",
        old_values={"status": old_status} if old_status else None,
        new_values={"status": enrollment.status},
        changes={
            "verb": verb,
            "student_id": str(student.pk),
            "offering_id": str(offering.pk),
            "subject": offering.subject.name,
            "target_group": getattr(offering.group, "name", "") or "",
            "source_group": getattr(source, "name", "") or "",
            "source_group_id": str(source.pk) if source is not None else "",
        },
        reason=str(reason or "")
        or (
            f"Alt qrupdan jurnala əlavə: {getattr(source, 'name', '—')} → "
            f"{getattr(offering.group, 'name', '—')} ({offering.subject.code})"
            if verb == "add"
            else f"Alt qrupdan əlavə geri götürüldü: {offering.subject.code}"
        ),
    )
