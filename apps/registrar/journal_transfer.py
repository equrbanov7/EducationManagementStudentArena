"""Jurnalın və ya onun DƏRS NÖVÜNÜN başqa müəllimə köçürülməsi — TƏK yazı yolu (sahib 2026-11-11).

Sahib: «Yük bölgüsündə müəllimi dəyişəndə fənn də təhvil olsun (Fənn təhvili ilə eyni nəticə); yalnız seminarı
təhvil vermək də işləsin». İki səth bu modulu çağırır:

* «Fənn təhvili» (:mod:`apps.registrar.handover_actions`) — blokerlər, səbəb və icazə orada yoxlanır;
* «Yük bölgüsü» (``apps.workload.services.offering_transfer``) — kafedranın açıq müəllim dəyişikliyi.

İKİ REJİM
---------
* **Tam təhvil** (``kinds`` boş və ya hamısı) — köhnə davranış olduğu kimi: ``CourseOffering.instructor`` yeni
  müəllimə keçir, iki tərəfin aktiv payları söndürülüb qeyddə saxlanır, köhnə sahibin slotları sahibi izləyir.
* **Növ təhvili** (məs. yalnız seminar) — növü daşıyan müəllimin payı söndürülür, qalan növləri üçün YENİ pay
  açılır, hədəf həmin növ(lər)lə pay alır. Mühazirə (və ya sahibin bütün növləri) köçəndə sahiblik də köçür,
  köhnə sahib qalan növləri ilə pay sahibi olur — «başqa növü varsa jurnal ondan getmir».

Bal, davamiyyət, ``Lesson.instructor`` və sillabusa TOXUNULMUR — yalnız sahiblik və giriş (pay) dəyişir.

QEYD VƏ GERİ QAYTARMA (sxem dəyişmədən)
--------------------------------------
Hər köçürmə ``TeachingHandover`` sətri yaradır. Növ təhvilinin yaratdığı payların ``batch`` sahəsində işarə var:
``ho<o|k><növ kodları>:<qeyd id-si>`` — ``o`` = sahiblik də köçüb, kodlar ``L``/``S``/``B`` (mühazirə/seminar/
laboratoriya). Geri qaytarma bu payları söndürür, qeyddəki köhnə payları qaytarır, sahiblik köçübsə müəllimi də.
İşarəli ``manual`` pay «Fənn təhvili» qərarıdır — yük sinxronu onun növünü başqasına vermir
(:mod:`apps.registrar.journal_workload_shares`), yalnız kafedranın HƏMİN növdəki açıq dəyişikliyi onu əvəzləyir.
"""

from __future__ import annotations

from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from .journal_shares import ALL_KINDS, active_shares, forget
from .models import CourseOffering, JournalShare, JournalShareSource, ScheduleSlot, TeachingHandover

#: Təhvil paylarının ``batch`` işarəsi.
MARKER_PREFIX = "ho"
KIND_ORDER = ("lecture", "seminar", "lab")
_KIND_CODES = {"lecture": "L", "seminar": "S", "lab": "B"}
OWNER_KIND = "lecture"

ORIGIN_HANDOVER = "handover"
ORIGIN_WORKLOAD = "workload"

#: «Yük bölgüsü»ndən gələn köçürmənin qeyd səbəbi (data — tərcümə olunmur, tarixçədə görünür).
WORKLOAD_REASON = "Dərs yükü bölgüsü: kafedra müəllimi dəyişdi"


class TransferRejected(Exception):
    """Köçürmə mümkün deyil (``code`` — ``handover_actions.BLOCKER_MESSAGES`` açarı)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# ── Növlər və işarə ──────────────────────────────────────────────────────────


def normalize_kinds(values) -> frozenset:
    """Seçilmiş növlər; boş = hamısı. Naməlum dəyər ``ValueError`` verir (səssiz genişlənmə yoxdur)."""
    if isinstance(values, str):
        values = [part for part in values.replace(";", ",").split(",")]
    picked = {str(value).strip() for value in (values or []) if str(value or "").strip()}
    picked.discard("all")
    unknown = picked - ALL_KINDS
    if unknown:
        raise ValueError(sorted(unknown)[0])
    return frozenset(picked) or ALL_KINDS


def ordered(kinds) -> list:
    return [kind for kind in KIND_ORDER if kind in (kinds or ())]


def marker(record_pk, kinds, owner_move: bool) -> str:
    codes = "".join(_KIND_CODES[kind] for kind in ordered(kinds))
    head = f"{MARKER_PREFIX}{'o' if owner_move else 'k'}{codes}:"
    return head + record_pk.hex[: 32 - len(head)]


def parse_marker(batch):
    """``(sahiblik_köçübmü, növlər)`` və ya ``None`` (təhvil payı deyil)."""
    value = str(batch or "")
    if not value.startswith(MARKER_PREFIX) or ":" not in value:
        return None
    head = value[len(MARKER_PREFIX) :].split(":", 1)[0]
    if not head or head[0] not in "ok":
        return None
    return head[0] == "o", frozenset(kind for kind, code in _KIND_CODES.items() if code in head[1:])


def is_handover_share(share) -> bool:
    """«Fənn təhvili» ilə verilmiş (əl ilə) növ payı — yük sinxronu onun növünü əzmir."""
    return share.source == JournalShareSource.MANUAL and parse_marker(share.batch) is not None


def _share_kinds(share) -> set:
    return (set(share.kinds or ()) & ALL_KINDS) or set(ALL_KINDS)


def record_shares(record):
    """Bu təhvil qeydinin YARATDIĞI paylar (işarə ilə)."""
    suffix = record.pk.hex[:24]
    return JournalShare.objects.filter(
        organization_id=record.organization_id,
        offering_id=record.offering_id,
        batch__startswith=MARKER_PREFIX,
        batch__contains=f":{suffix}",
    )


def record_states(records) -> dict:
    """``{qeyd id: {"owner_move", "kinds", "intact"}}`` — tarixçə üçün TOPLU (bir sorğu).

    İşarəsiz qeyd = tam təhvil. ``intact`` — təhvilin yaratdığı payların HAMISI hələ aktivdir (geri qaytarıla bilər).
    """
    records = list(records)
    by_suffix = {record.pk.hex[:24]: record.pk for record in records}
    result = {record.pk: {"owner_move": True, "kinds": ALL_KINDS, "intact": True} for record in records}
    if not records:
        return result
    rows = JournalShare.objects.filter(
        offering_id__in={record.offering_id for record in records}, batch__startswith=MARKER_PREFIX
    ).values_list("batch", "is_active")
    for batch, is_active in rows:
        parsed = parse_marker(batch)
        record_id = by_suffix.get(batch.split(":", 1)[1][:24]) if parsed else None
        if record_id is None:
            continue
        state = result[record_id]
        state["owner_move"], state["kinds"] = parsed
        state["intact"] = state["intact"] and bool(is_active)
    return result


def record_kinds(records) -> dict:
    """``{qeyd id: (sahiblik köçübmü, növlər)}``."""
    return {key: (state["owner_move"], state["kinds"]) for key, state in record_states(records).items()}


# ── Kim hansı növü aparır ────────────────────────────────────────────────────


def kind_holders(offering, shares=None) -> dict:
    """``{növ: {müəllim id}}`` — jurnalda növü FAKTİKİ aparanlar (sahib: başqa payın tam iddia etmədiyi növlər)."""
    from .journal_shares import _claimed_kinds

    shares = active_shares(offering) if shares is None else shares
    owner_id = offering.instructor_id
    holders = {kind: set() for kind in KIND_ORDER}
    own = None
    others = []
    for share in shares:
        if share.teacher_id == owner_id:
            own = share
            continue
        others.append(share)
        for kind in _share_kinds(share):
            holders[kind].add(share.teacher_id)
    if owner_id:
        unclaimed = set(ALL_KINDS) - _claimed_kinds(offering, others)
        owner_kinds = (set(own.kinds) & ALL_KINDS) | unclaimed if own is not None and own.kinds else unclaimed
        for kind in owner_kinds:
            holders[kind].add(owner_id)
    return holders


def current_holders(offering) -> dict:
    """:func:`kind_holders` təzə oxu ilə (offering-dəki pay memo-su atılır)."""
    forget(offering)
    return kind_holders(offering)


def bulk_holders(offerings) -> dict:
    """Siyahı üçün ``{açılış id: {növ: [müəllim id]}}`` — TƏK sorğu (sətir-məhdud pay sahibin növünü almır)."""
    offerings = list(offerings)
    shares = defaultdict(list)
    limited = set(
        JournalShare.enrollments.through.objects.filter(
            journalshare__offering_id__in=[offering.pk for offering in offerings], journalshare__is_active=True
        ).values_list("journalshare_id", flat=True)
    )
    for share in JournalShare.objects.filter(
        offering_id__in=[offering.pk for offering in offerings], is_active=True
    ).order_by("created_at"):
        shares[share.offering_id].append(share)
    result = {}
    for offering in offerings:
        holders = {kind: [] for kind in KIND_ORDER}
        claimed, own = set(), None
        for share in shares.get(offering.pk, []):
            if share.teacher_id == offering.instructor_id:
                own = share
                continue
            for kind in ordered(_share_kinds(share)):
                holders[kind].append(share.teacher_id)
                if share.pk not in limited:
                    claimed.add(kind)
        if offering.instructor_id:
            owner_kinds = set(ALL_KINDS) - claimed
            if own is not None and own.kinds:
                owner_kinds |= set(own.kinds) & ALL_KINDS
            for kind in ordered(owner_kinds):
                holders[kind].insert(0, offering.instructor_id)
        result[offering.pk] = holders
    return result


# ── Köçürmə ──────────────────────────────────────────────────────────────────


def _display_name(user) -> str:
    if user is None:
        return ""
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return full or str(getattr(user, "username", "") or "")


def _user(user_id):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(pk=user_id).first() if user_id else None


def _move_owner(offering, target, expected_id) -> None:
    updated = CourseOffering.objects.filter(pk=offering.pk, instructor_id=expected_id).update(instructor=target)
    if not updated:
        raise TransferRejected("concurrent_change")
    offering.instructor = target


def _full(offering, target, *, actor, reason, from_user) -> TeachingHandover:
    """Tam təhvil — köhnə ``_apply_one`` yazısı (davranış dəyişmir)."""
    from .handover_shares import deactivate_for_handover

    expected_id = offering.instructor_id
    _move_owner(offering, target, expected_id)
    # Köhnə sahibə YAZILMIŞ slot jurnal sahibinin slotudur — yeni sahibi izləsin (NULL).
    if expected_id is not None:
        ScheduleSlot.objects.filter(offering_id=offering.pk, instructor_id=expected_id).update(
            instructor=None, updated_at=timezone.now()
        )
    deactivated = deactivate_for_handover(offering, from_user, target)
    return _record(offering, from_user, target, actor=actor, reason=reason, deactivated=deactivated)


def _record(offering, source, target, *, actor, reason, deactivated) -> TeachingHandover:
    return TeachingHandover.objects.create(
        organization=offering.organization,
        offering=offering,
        from_instructor=source,
        to_instructor=target,
        from_instructor_name=_display_name(source),
        to_instructor_name=_display_name(target),
        reason=reason,
        performed_by=actor if getattr(actor, "pk", None) else None,
        deactivated_share_ids=deactivated,
    )


def transfer(
    *, offering, target, kinds=None, actor=None, reason="", origin=ORIGIN_HANDOVER, from_teacher_id=None
) -> TeachingHandover:
    """Jurnalı (``kinds`` boş) və ya növ(lər)i ``target``-ə köçür. ``offering`` SATIR KİLİDLİDİR, blokerlər çağırandadır.

    Qaytarır: yaradılmış ``TeachingHandover``; ``record.transfer_summary`` — nə köçdü (UI mesajı üçün).
    """
    kinds = frozenset(kinds or ()) & ALL_KINDS or ALL_KINDS
    owner_id = offering.instructor_id
    forget(offering)
    shares = active_shares(offering)
    holders = kind_holders(offering, shares)
    owner_kinds = {kind for kind in KIND_ORDER if owner_id and owner_id in holders[kind]}
    if kinds >= ALL_KINDS:
        if owner_id == target.pk:
            raise TransferRejected("same_instructor")
        source = offering.instructor
        record = _full(offering, target, actor=actor, reason=reason, from_user=source)
        record.transfer_summary = {"kinds": ordered(ALL_KINDS), "owner_move": True, "from": [_display_name(source)]}
        return record

    sources = {teacher for kind in kinds for teacher in holders[kind]} - {target.pk}
    if from_teacher_id:
        sources &= {int(from_teacher_id)} if str(from_teacher_id).isdigit() else set()
        if not sources:
            raise TransferRejected("kind_not_held")
    owner_is_source = bool(owner_id and owner_id in sources and owner_kinds & kinds)
    owner_move = owner_id != target.pk and (
        owner_id is None or (owner_is_source and (OWNER_KIND in kinds or not owner_kinds - kinds))
    )
    if not sources and not owner_move:
        raise TransferRejected("same_instructor")

    by_teacher = {share.teacher_id: share for share in shares}
    deactivated, creates = [], []
    moved_rows, moved_full = set(), False
    for teacher_id in sorted(sources):
        share = by_teacher.get(teacher_id)
        held = {kind for kind in KIND_ORDER if teacher_id in holders[kind]}
        if teacher_id == owner_id and share is not None and share.kinds:
            # Sahibin AÇIQ növ payı varsa qalanı odur — sahibliyin «iddiasız növləri» təhvildən sonra ona qalmır.
            held = (set(share.kinds) & ALL_KINDS) | (held & kinds)
        rows = set(share.enrollment_id_set) if share is not None else set()
        if share is not None:
            deactivated.append(share)
        if rows:
            moved_rows |= rows
        else:
            moved_full = True
        remaining = held - kinds
        if remaining:  # başqa növü qalır — jurnal ondan getmir, yalnız həmin növlərlə
            creates.append((teacher_id, remaining, rows))
    target_share = by_teacher.get(target.pk)
    target_kinds = {kind for kind in KIND_ORDER if target.pk in holders[kind]} | set(kinds)
    if target_share is not None:
        deactivated.append(target_share)
    target_full = moved_full or (target_share is not None and not target_share.enrollment_id_set)
    target_rows = set() if target_full else moved_rows | set(getattr(target_share, "enrollment_id_set", ()) or ())
    becomes_owner = owner_move or owner_id == target.pk
    if not (becomes_owner and target_kinds >= ALL_KINDS and not target_rows):
        creates.append((target.pk, target_kinds, target_rows))

    if deactivated:
        JournalShare.objects.filter(pk__in=[share.pk for share in deactivated]).update(
            is_active=False, updated_at=timezone.now()
        )
    now = timezone.now()
    if owner_move:
        _move_owner(offering, target, owner_id)
        if owner_id is not None:
            ScheduleSlot.objects.filter(offering_id=offering.pk, instructor_id=owner_id, kind__in=kinds).update(
                instructor=None, updated_at=now
            )
    else:
        slots = ScheduleSlot.objects.filter(offering_id=offering.pk, kind__in=kinds)
        slots.filter(instructor_id__in=sources - {owner_id}).update(instructor=target, updated_at=now)
        if owner_is_source:
            slots.filter(instructor__isnull=True).update(instructor=target, updated_at=now)
            slots.filter(instructor_id=owner_id).update(instructor=target, updated_at=now)

    primary = owner_id if owner_move else (sorted(sources)[0] if sources else None)
    source_user = _user(primary)
    record = _record(
        offering,
        source_user,
        target,
        actor=actor,
        reason=reason,
        deactivated=[str(share.pk) for share in deactivated],
    )
    batch = marker(record.pk, kinds, owner_move)
    source_value = JournalShareSource.WORKLOAD if origin == ORIGIN_WORKLOAD else JournalShareSource.MANUAL
    for teacher_id, share_kinds, rows in creates:
        share = JournalShare.objects.create(
            organization=offering.organization,
            offering=offering,
            teacher_id=teacher_id,
            kinds=ordered(share_kinds),
            source=source_value,
            batch=batch,
            created_by=actor if getattr(actor, "pk", None) else None,
        )
        if rows:
            share.enrollments.set(sorted(rows))
    forget(offering)
    names = [_display_name(_user(teacher_id)) for teacher_id in sorted(sources)]
    record.transfer_summary = {"kinds": ordered(kinds), "owner_move": owner_move, "from": names}
    return record


def revert_shares(record, offering) -> bool:
    """Növ təhvilinin paylarını geri qaytar. Qaytarır: qeyd növ təhvili idimi (sahiblik köçməyibsə False-un mənası
    çağıranda — ``revert`` sahibliyi yalnız ``owner_move`` olanda qaytarır). Ziddiyyətdə ``HandoverShareConflict``."""
    from .handover_shares import HandoverShareConflict, restore_for_revert

    created = list(record_shares(record).select_for_update())
    if not created:
        restore_for_revert(record, offering)
        return False
    if any(not share.is_active for share in created):
        raise HandoverShareConflict
    JournalShare.objects.filter(pk__in=[share.pk for share in created]).update(
        is_active=False, updated_at=timezone.now()
    )
    restore_for_revert(record, offering)
    return True


def record_owner_move(record) -> bool:
    parsed = next((parse_marker(batch) for batch in record_shares(record).values_list("batch", flat=True)), None)
    return True if parsed is None else parsed[0]


def notify_on_commit(records, *, organization) -> None:
    """Yeni müəllimə bildiriş tranzaksiya bitəndən SONRA (yük sinxronu atomik blokdadır)."""
    from .handover_actions import _notify

    records = [record for record in records if record is not None]
    if records:
        transaction.on_commit(lambda: _notify(records, organization=organization, actor=None))


__all__ = [
    "KIND_ORDER",
    "MARKER_PREFIX",
    "ORIGIN_HANDOVER",
    "ORIGIN_WORKLOAD",
    "WORKLOAD_REASON",
    "TransferRejected",
    "bulk_holders",
    "current_holders",
    "is_handover_share",
    "kind_holders",
    "marker",
    "normalize_kinds",
    "notify_on_commit",
    "ordered",
    "parse_marker",
    "record_kinds",
    "record_owner_move",
    "record_states",
    "record_shares",
    "revert_shares",
    "transfer",
]
