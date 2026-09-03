"""Fənn təhvilinin YAZMA qatı — təyin et, toplu təyin et, geri qaytar.

Hər əməl: icazə → əhatə → blokerlər → atomik yazı → audit → bildiriş.
Oxu/qərar qatı :mod:`apps.registrar.handover` modulundadır.

⚠️ **ATOMİKLİK.** Toplu təhvil TƏK tranzaksiyadadır: bir sətir bloklanırsa
HEÇ NƏ yazılmır. Səbəb — «Elvin işdən çıxdı» ssenarisində yarımçıq nəticə
(3 fənn köçdü, 2 köçmədi) ən pis haldır: heç kim hansı jurnalın kimdə olduğunu
bilmir. İstifadəçi əvvəlcə önizləmədə blokerləri görür, sonra təsdiqləyir.

⚠️ **ŞƏRTİ UPDATE.** Açılışın müəllimi ``filter(instructor_id=<gözlənilən>)``
ilə dəyişdirilir. İki operator eyni anda eyni fənni fərqli adama versə, ikincisi
səssizcə üstündən yazmır — 409 alır. (Eyni naxış imtahan state-machine-indədir.)
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.registrar import handover as handover_read
from apps.registrar.models import CourseOffering, TeachingHandover
from core.audit import log_action
from core.constants import AuditAction

#: Audit resurs tipi — audit axtarışında süzgəc açarı.
AUDIT_RESOURCE_TYPE = "registrar.teaching_handover"

#: Toplu təhvilin yuxarı həddi — tək tranzaksiyanın kilid müddətini məhdudlaşdırır.
MAX_BULK_ROWS = 100


class HandoverError(Exception):
    """İstifadəçiyə göstərilə bilən təhvil xətası (kod + mətn + HTTP statusu).

    ``RimAccessError`` ilə EYNİ naxış (``apps/accounts/services/rim/policy.py``):
    ``code`` maşın-oxunaqlıdır (JSON cavab + tərcümə xəritəsinin açarı,
    ``apps/accounts/views/handover/labels.py``), ``message`` isə AZ mətndir.
    QƏSDƏN ``ValidationError`` DEYİL: bu xəta HTTP statusu daşıyır və səhvən
    Django forma validasiyası ilə qarışdırılmamalıdır.
    """

    # Bütün arqumentlər `super().__init__()`-ə ötürülür ki, exception `pickle` /
    # `copy.copy()` ilə düzgün bərpa olunsun (flake8-bugbear B042).
    def __init__(self, code: str, message: str, status: int = 409, codes=()):
        codes = tuple(codes or ())
        super().__init__(code, message, status, codes)
        self.code = code
        self.message = message
        self.status = status
        #: ``code == "blocked"`` olanda BLOKER kodlarının siyahısı. HTTP səthi
        #: mətni məhz bu kodlardan qurur — servisin AZ mətnini yox (i18n).
        self.codes = codes

    def __str__(self):
        return self.code


def _display_name(user) -> str:
    if user is None:
        return ""
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return full or str(getattr(user, "username", "") or "")


def _normalize_reason(reason) -> str:
    text = str(reason or "").strip()
    if len(text) < handover_read.MIN_REASON_LENGTH:
        raise HandoverError(
            "reason_required",
            "Təhvil üçün səbəb yazılmalıdır (ən azı " f"{handover_read.MIN_REASON_LENGTH} simvol).",
            status=400,
        )
    return text[: handover_read.MAX_REASON_LENGTH]


def _require_permission(actor, organization):
    if not handover_read.can_reassign(actor, organization):
        raise PermissionDenied("Fənni başqa müəllimə təhvil vermək üçün icazəniz yoxdur.")


def _resolve_target(organization, user_id):
    from django.contrib.auth import get_user_model

    target = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if target is None or not handover_read.is_eligible_target(organization, user_id):
        raise HandoverError(
            "target_not_eligible",
            "Seçilmiş müəllim bu təşkilatda bal yazma səlahiyyətinə malik aktiv üzv deyil.",
            status=400,
        )
    return target


def _locked_offering(offering_id, organization):
    """Açılışı SATIR KİLİDİ ilə yüklə (rəqabətli təhvil qarşısı).

    ``of=("self",)`` MƏCBURİDİR: ``select_for_update`` + nullable FK-lı
    ``select_related`` Postgres-də outer-join üzərində kilid istəyir və çökür.
    """
    offering = (
        CourseOffering.objects.select_for_update(of=("self",)).filter(pk=offering_id, organization=organization).first()
    )
    if offering is None:
        raise HandoverError("offering_not_found", "Dərs açılışı tapılmadı.", status=404)
    return offering


# ── Tək təhvil (toplu axının da vahididir) ───────────────────────────────────


def _apply_one(*, offering, target, actor, organization, reason, request, closed_ids, today):
    codes = handover_read.blockers(
        offering,
        actor=actor,
        organization=organization,
        closed_ids=closed_ids,
        today=today,
        new_instructor_id=getattr(target, "pk", None),
    )
    if codes:
        raise HandoverError("blocked", blocker_message(codes), status=409, codes=codes)

    previous = offering.instructor
    expected_id = offering.instructor_id
    updated = CourseOffering.objects.filter(pk=offering.pk, instructor_id=expected_id).update(instructor=target)
    if not updated:
        raise HandoverError(
            "concurrent_change",
            "Bu fənnin müəllimi az öncə başqası tərəfindən dəyişdirilib — səhifəni yeniləyin.",
            status=409,
        )
    offering.instructor = target

    record = TeachingHandover.objects.create(
        organization=organization,
        offering=offering,
        from_instructor=previous,
        to_instructor=target,
        from_instructor_name=_display_name(previous),
        to_instructor_name=_display_name(target),
        reason=reason,
        performed_by=actor,
    )
    _audit(
        record=record,
        actor=actor,
        organization=organization,
        request=request,
        action="handover.assigned",
        reason=reason,
    )
    return record


def reassign(*, actor, organization, offering_id, new_instructor_id, reason, request=None) -> dict:
    """Bir fənni başqa müəllimə təhvil ver (atomik + auditli + bildirişli)."""
    return bulk_reassign(
        actor=actor,
        organization=organization,
        items=[{"offering_id": offering_id, "new_instructor_id": new_instructor_id}],
        reason=reason,
        request=request,
    )


def bulk_reassign(*, actor, organization, items, reason, request=None) -> dict:
    """Bir neçə fənni (hər biri AYRI müəllimə ola bilər) təhvil ver.

    ``items`` — ``[{"offering_id": ..., "new_instructor_id": ...}, …]``.
    Sahibin tələbi: «hər birini ayrıca yeni müəllimə təyin etmək mümkün olsun —
    hamısı eyni adama getməyə bilər», ona görə hədəf SƏTİR səviyyəsindədir.
    """
    _require_permission(actor, organization)
    reason = _normalize_reason(reason)
    rows = [row for row in (items or []) if row and row.get("offering_id")]
    if not rows:
        raise HandoverError("nothing_selected", "Heç bir fənn seçilməyib.", status=400)
    if len(rows) > MAX_BULK_ROWS:
        raise HandoverError(
            "too_many_rows",
            f"Bir dəfəyə ən çox {MAX_BULK_ROWS} fənn təhvil verilə bilər.",
            status=400,
        )

    today = timezone.localdate()
    offering_ids = [row["offering_id"] for row in rows]
    closed_ids = handover_read.closed_offering_ids(offering_ids)

    results = []
    with transaction.atomic():
        for row in rows:
            offering = _locked_offering(row["offering_id"], organization)
            target = _resolve_target(organization, row.get("new_instructor_id"))
            record = _apply_one(
                offering=offering,
                target=target,
                actor=actor,
                organization=organization,
                reason=reason,
                request=request,
                closed_ids=closed_ids,
                today=today,
            )
            results.append(record)

    notified = _notify(results, organization=organization, actor=actor)
    return {
        "count": len(results),
        "notified": notified,
        "handover_ids": [str(record.pk) for record in results],
    }


# ── Geri qaytarma ────────────────────────────────────────────────────────────

#: Geri qaytarmada YOXLANAN bloker kodları.
#:
#: ⚠️ ``handover.py`` başlığındakı «təhvilin özü heç vaxt bağlı jurnalda baş verə
#: bilmir» arqumenti geri qaytarmaya ŞAMİL OLUNMUR: təhvil ilə geri qaytarma
#: ARASINDA vaxt keçir və semestr məhz o aralıqda bitə bilər. Jurnallarını
#: bağlamayan universitetdə (``approval_status=draft``) bu, dekana keçmiş
#: semestrin jurnal sahibliyini istənilən vaxt çevirmək imkanı verirdi — yəni
#: ``past_period`` invariantı yalnız təhvildə tutulurdu, geri qaytarmada yox.
#:
#: Siyahıda OLMAYANLAR və səbəbləri:
#: * ``outside_scope`` — aşağıda ayrıca ``offering_in_scope`` ilə yoxlanır və
#:   403 verir (bloker 409-dur; icazə xətası status kodunu itirməməlidir);
#: * ``actor_is_current_instructor`` — təhvilə aid qaydadır (müəllim öz jurnalını
#:   ata bilməz); geri qaytarmada açılışın cari müəllimi QƏBUL EDƏN tərəfdir və
#:   aktorun səlahiyyəti onsuz da ``journal.reassign`` açarı ilə yoxlanıb;
#: * hədəf müəllimlə bağlı kodlar (``no_target``, ``same_instructor``,
#:   ``target_not_eligible``) — geri qaytarmada yeni hədəf seçilmir.
REVERT_BLOCKER_CODES = ("offering_inactive", "journal_closed", "past_period")


def revert(*, actor, organization, handover_id, reason, request=None) -> dict:
    """Səhv təyinatı geri qaytar — açılışın müəllimi ``from_instructor``-a dönür.

    YENİ təhvil sətri yaratmır: mövcud sətir «geri qaytarılıb» kimi işarələnir.
    Səbəb MƏCBURİDİR (dağıdıcı-ekvivalent əməl: jurnal sahibliyi yenidən dəyişir).

    ⚠️ Təhvil kimi bu əməl də oxu qatının BLOKERLƏRİNDƏN keçir
    (:data:`REVERT_BLOCKER_CODES`) — dövr təhvil ilə geri qaytarma ARASINDA
    bitə bilər və tarixi jurnalın sahibi o vaxtdan sonra dəyişdirilməməlidir.
    """
    _require_permission(actor, organization)
    reason = _normalize_reason(reason)

    with transaction.atomic():
        record = (
            TeachingHandover.objects.select_for_update(of=("self",))
            .filter(pk=handover_id, organization=organization)
            .first()
        )
        if record is None:
            raise HandoverError("handover_not_found", "Təhvil qeydi tapılmadı.", status=404)
        if record.reverted_at is not None:
            raise HandoverError("already_reverted", "Bu təhvil artıq geri qaytarılıb.", status=409)

        offering = _locked_offering(record.offering_id, organization)
        if not handover_read.offering_in_scope(actor, organization, offering):
            raise PermissionDenied("Bu fənn sizin səlahiyyət sahənizə düşmür.")
        if offering.instructor_id != record.to_instructor_id:
            raise HandoverError(
                "chain_moved",
                "Bu fənn təhvildən sonra yenidən başqasına verilib — əvvəlcə sonuncu təhvili geri qaytarın.",
                status=409,
            )
        # Blokerlər OXU qatından gəlir — tərif iki yerdə saxlanmır. Aktor
        # ötürülMÜR: əhatə yuxarıda ayrıca (403 ilə) yoxlanıb, `blockers` isə
        # aktor verildikdə `outside_scope`/`actor_is_current_instructor` kodlarını
        # da qaytarardı (bax REVERT_BLOCKER_CODES şərhi).
        codes = [
            code
            for code in handover_read.blockers(offering, organization=organization, today=timezone.localdate())
            if code in REVERT_BLOCKER_CODES
        ]
        if codes:
            raise HandoverError("blocked", blocker_message(codes), status=409, codes=codes)

        CourseOffering.objects.filter(pk=offering.pk, instructor_id=record.to_instructor_id).update(
            instructor_id=record.from_instructor_id
        )
        record.reverted_at = timezone.now()
        record.reverted_by = actor
        record.revert_reason = reason
        record.save(update_fields=["reverted_at", "reverted_by", "revert_reason", "updated_at"])
        _audit(
            record=record,
            actor=actor,
            organization=organization,
            request=request,
            action=REVERT_AUDIT_ACTION,
            reason=reason,
        )

    _notify_revert(record, organization=organization)
    return {
        "handover_id": str(record.pk),
        "restored_to": record.from_instructor_name,
    }


# ── Audit + bildiriş ─────────────────────────────────────────────────────────


#: Geri qaytarma audit sətrində istiqamət TƏRSDİR.
REVERT_AUDIT_ACTION = "handover.reverted"


def _audit(*, record, actor, organization, request, action, reason):
    """Audit sətri — ``old_values``/``new_values`` FAKTİKİ dəyişikliyi göstərir.

    ⚠️ İSTİQAMƏT. Təhvildə açılışın müəllimi ``from → to``, geri qaytarmada isə
    ``to → from`` dəyişir. Əvvəllər hər iki əməl eyni dəyərləri yazırdı, yəni
    audit jurnalını oxuyan komissiya geri qaytarmanı old/new sütunlarından
    GÖRƏ BİLMİRDİ (iki sətir eyni diff-lə düzülürdü). Artıq istiqamət əmələ görə
    çevrilir; hansı əməl olduğu ``changes["action"]``-da qalır.

    ``changes["from_instructor_id"]`` / ``["to_instructor_id"]`` QƏSDƏN
    çevrilMİR: onlar ``TeachingHandover`` SƏTRİNİN öz sütunlarıdır (təhvil
    qeydinin kimliyi), delta deyil — hər iki sətirdə eyni qalmaları düzgündür.
    """
    offering = record.offering
    reverting = action == REVERT_AUDIT_ACTION
    previous_name = record.to_instructor_name if reverting else record.from_instructor_name
    current_name = record.from_instructor_name if reverting else record.to_instructor_name
    log_action(
        AuditAction.UPDATE,
        user=actor if getattr(actor, "pk", None) else None,
        organization=organization,
        obj=offering,
        reason=reason,
        request=request,
        resource_type=AUDIT_RESOURCE_TYPE,
        resource_id=str(record.pk),
        resource_repr=f"{_offering_label(offering)} · {previous_name or '—'} → {current_name or '—'}",
        old_values={"instructor": previous_name},
        new_values={"instructor": current_name},
        changes={
            "action": action,
            "offering_id": str(offering.pk),
            "subject": getattr(offering.subject, "code", ""),
            "group": getattr(offering.group, "name", "") or "",
            "period": getattr(offering.period, "name", "") or "",
            "from_instructor_id": str(record.from_instructor_id or ""),
            "to_instructor_id": str(record.to_instructor_id or ""),
        },
    )


def _offering_label(offering) -> str:
    subject = getattr(offering.subject, "name", "") or getattr(offering.subject, "code", "")
    group = getattr(offering.group, "name", "") or ""
    return f"{subject} · {group}".strip(" ·")


def _notify(records, *, organization, actor):
    """Yeni müəllimə bildiriş — SAHİBİN TƏLƏBİ («yeni müəllim xəbərdar olsun»).

    Bildiriş tranzaksiyadan KƏNARDA göndərilir: bildiriş xidmətinin nasazlığı
    təhvili geri qaytarmamalıdır (təhvil artıq auditə düşüb və qüvvədədir).
    Uğursuzluq halında ``notified`` bayrağı False qalır və əməl loglanır.
    """
    from apps.notifications.public import create_notification

    sent = 0
    for record in records:
        if record.to_instructor is None:
            continue
        try:
            create_notification(
                recipient=record.to_instructor,
                title="Sizə yeni fənn təyin edildi",
                message=(
                    f"«{_offering_label(record.offering)}» fənninin elektron jurnalı sizə təhvil verildi. "
                    f"Səbəb: {record.reason}"
                ),
                link="/registrar/journal/",
                organization=organization,
                metadata={
                    "kind": "teaching_handover",
                    "offering_id": str(record.offering_id),
                    "handover_id": str(record.pk),
                    "from_instructor": record.from_instructor_name,
                },
            )
            sent += 1
        except Exception:  # pragma: no cover — bildiriş təhvili bloklamır
            import logging

            logging.getLogger(__name__).exception("teaching handover notification failed")
    if sent:
        TeachingHandover.objects.filter(pk__in=[r.pk for r in records]).update(notified=True)
    return sent


def _notify_revert(record, *, organization):
    """Geri qaytarmada HƏR İKİ tərəf xəbərdar olur (jurnal sahibliyi dəyişdi)."""
    from apps.notifications.public import create_notification

    recipients = [user for user in (record.from_instructor, record.to_instructor) if user is not None]
    for recipient in recipients:
        try:
            create_notification(
                recipient=recipient,
                title="Fənn təhvili geri qaytarıldı",
                message=(
                    f"«{_offering_label(record.offering)}» fənninin jurnalı yenidən "
                    f"{record.from_instructor_name or '—'} adına qaytarıldı. Səbəb: {record.revert_reason}"
                ),
                link="/registrar/journal/",
                organization=organization,
                metadata={"kind": "teaching_handover_reverted", "handover_id": str(record.pk)},
            )
        except Exception:  # pragma: no cover
            import logging

            logging.getLogger(__name__).exception("teaching handover revert notification failed")


#: Bloker kodu → istifadəçi mətni. Servis qatı tərcüməsizdir (kod qaytarır);
#: bu xəritə HTTP səthində göstərilən son mətni verir.
BLOCKER_MESSAGES = {
    "outside_scope": "Bu fənn sizin səlahiyyət sahənizə düşmür.",
    "journal_closed": "Jurnal bağlanıb — bağlı semestrin müəllimi dəyişdirilmir.",
    "past_period": "Semestr başa çatıb — tarixi jurnalın müəllimi dəyişdirilmir.",
    "offering_inactive": "Dərs açılışı aktiv deyil.",
    "same_instructor": "Fənn onsuz da bu müəllimdədir.",
    "target_not_eligible": "Seçilmiş müəllim bal yazma səlahiyyətinə malik aktiv üzv deyil.",
    "actor_is_current_instructor": "Öz fənninizi özünüz təhvil verə bilməzsiniz — bunu rəhbərlik edir.",
    "no_target": "Yeni müəllim seçilməyib.",
}


def blocker_message(codes) -> str:
    return " ".join(BLOCKER_MESSAGES.get(code, code) for code in codes) or "Təhvil mümkün deyil."


__all__ = [
    "AUDIT_RESOURCE_TYPE",
    "BLOCKER_MESSAGES",
    "MAX_BULK_ROWS",
    "REVERT_AUDIT_ACTION",
    "REVERT_BLOCKER_CODES",
    "HandoverError",
    "blocker_message",
    "bulk_reassign",
    "reassign",
    "revert",
]
