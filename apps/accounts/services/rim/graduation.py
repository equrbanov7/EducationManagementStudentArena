"""RİM detal kartından «Məzun et» (sahib 2026-11-04: «məzun … olanda çıxara bilim»).

MEXANİZM TƏKRAR YARADILMIR: məzun etmə «Tələbə reyestri»ndəki hərəkət əmridir —
``people.movements.create_movement(kind="graduation")`` (əmr № + tarix MƏCBURİ, səbəb istəyə bağlı;
superadmin üçün avtomatik «SA-…» əmri). O, akademik qeydi «Məzun»a keçirir, cari dövr qeydiyyatlarını dondurur,
hesabın girişini bağlayır (``access_state='archived'``), ledger + audit yazır və bildiriş göndərir.

Bu modul yalnız RİM qatını əlavə edir: hədəf aktorun RİM idarə sahəsindədir (``assert_can_manage``) və qeyd
HƏDƏFİN özünə aiddir (başqasının ``record_id``-si ilə əmr yazıla bilməz). Reyestr açarları
(``student.movement`` + ``people.manage_academic``) və onların struktur əhatəsi kataloq aktoru ilə yoxlanılır —
RİM aktorunun rol icazələrindən qurulur (eyni üzvlüklər, eyni ``grant:`` qaydası).
"""

from __future__ import annotations

from django.utils.translation import pgettext

from .policy import RimAccessError, RimActor, assert_can_manage

_CTX = "accounts.rim.graduation"
_ENROLLED = "enrolled"
_GRADUATED = "graduated"


def people_actor(actor: RimActor):
    """RİM aktorundan kataloq aktoru (``PeopleActor``) — reyestr qapıları ONUN üzərindən işləyir."""
    from ..people.permissions import PeopleActor

    return PeopleActor(
        user=actor.user,
        organization=actor.organization,
        permissions=frozenset(str(perm) for perm in actor.permissions),
        is_superadmin=actor.is_superadmin,
    )


def _records(actor: RimActor, user):
    """Hədəfin aktorun İDARƏ əhatəsindəki akademik qeydləri (qrup + ixtisas ilə)."""
    from ..people.academic import scoped_records_qs

    return (
        scoped_records_qs(people_actor(actor))
        .filter(student=user)
        .select_related("group", "program")
        .order_by("-is_active", "-admission_year", "pk")
    )


def _status_label(value: str) -> str:
    labels = {
        _ENROLLED: pgettext(_CTX, "Oxuyur"),
        "academic_leave": pgettext(_CTX, "Akademik məzuniyyətdə"),
        "expelled": pgettext(_CTX, "Xaric olunub"),
        _GRADUATED: pgettext(_CTX, "Məzun olub"),
    }
    return labels.get(value, value)


def _record_row(record) -> dict:
    program = getattr(record, "program", None)
    return {
        "id": str(record.pk),
        "group": getattr(getattr(record, "group", None), "name", "") or "",
        "program": str(getattr(program, "display_label", "") or getattr(program, "name", "") or ""),
        "admission_year": record.admission_year,
        "status": record.status,
        "status_label": _status_label(record.status),
    }


def card(actor: RimActor, user, *, manageable: bool) -> dict | None:
    """Tələbə hesabının «Akademik vəziyyət / Məzun et» bloku; tələbə deyilsə ``None``."""
    from core import superadmin_waiver

    from .staff_archive import is_student_account

    organization = actor.organization or getattr(getattr(user, "profile", None), "organization", None)
    if organization is None or not is_student_account(user, organization):
        return None
    pa = people_actor(actor)
    records = list(_records(actor, user)) if pa.can_manage_academic else []
    enrolled = [record for record in records if record.status == _ENROLLED and record.is_active]
    allowed = manageable and pa.can_move_students and pa.can_manage_academic
    if not (pa.can_move_students and pa.can_manage_academic):
        note = pgettext(
            _CTX, "Məzun əmri üçün «Tələbə hərəkəti» (student.movement) və «Akademik qeyd» icazələri lazımdır."
        )
    elif not manageable:
        note = pgettext(_CTX, "Bu hesab sizin idarə sahənizdə deyil.")
    elif not records:
        note = pgettext(_CTX, "Tələbənin sizin əhatənizdə akademik qeydi yoxdur.")
    elif not enrolled and any(record.status == _GRADUATED for record in records):
        note = pgettext(
            _CTX, "Tələbə artıq məzun olub. Səhvdirsə, «Tələbə reyestri»ndə bərpa əmri ilə geri qaytarılır."
        )
    elif not enrolled:
        note = pgettext(_CTX, "Yalnız «Oxuyur» statuslu tələbə məzun edilə bilər.")
    else:
        note = ""
    return {
        "records": [_record_row(record) for record in records],
        "enrolled": [_record_row(record) for record in enrolled],
        "can_graduate": bool(allowed and enrolled),
        "disabled_reason": note,
        # Superadmin əmr №/tarixi yazmadan keçir — server avtomatik «SA-…» əmri yazır (registry ilə eyni).
        "order_optional": superadmin_waiver.waives(actor.user),
    }


def graduate(actor: RimActor, user, *, record_id="", order_number="", order_date="", reason="", request=None):
    """Hədəfin «Oxuyur» qeydini məzun edir — reyestrin hərəkət servisi ilə (əmr, ledger, audit, bildiriş)."""
    from ..people import movements as movement_service

    assert_can_manage(actor, user)
    enrolled = [record for record in _records(actor, user) if record.status == _ENROLLED and record.is_active]
    if not enrolled:
        raise RimAccessError(
            "no_enrolled_record",
            pgettext(_CTX, "Tələbənin sizin əhatənizdə «Oxuyur» statuslu akademik qeydi yoxdur."),
            status=409,
        )
    wanted = str(record_id or "").strip()
    if wanted:
        record = next((item for item in enrolled if str(item.pk) == wanted), None)
        if record is None:
            raise RimAccessError("record_not_found", pgettext(_CTX, "Akademik qeyd tapılmadı."), status=404)
    elif len(enrolled) == 1:
        record = enrolled[0]
    else:
        raise RimAccessError(
            "record_required", pgettext(_CTX, "Tələbənin bir neçə aktiv qeydi var — qeydi seçin."), status=400
        )
    return movement_service.create_movement(
        people_actor(actor),
        record_id=str(record.pk),
        kind=_GRADUATED_KIND,
        order_number=order_number,
        order_date=order_date,
        reason=reason,
        request=request,
    )


#: ``registrar.MovementKind.GRADUATION`` dəyəri (accounts → registrar statik importu qəsdən yoxdur).
_GRADUATED_KIND = "graduation"

__all__ = ["card", "graduate", "people_actor"]
