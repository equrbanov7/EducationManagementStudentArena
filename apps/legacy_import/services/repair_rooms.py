"""R-5 təmiri: legacy otaq reyestri → ``exams.ExamRoom`` (artıq köçürülmüş hədəf).

Qüsur (2026-09-02 reqressiya qaçışı).  Mənbədə **158 otaq** var (`rooms`), klonda
isə ``exams.ExamRoom`` **sıfırdır**, ona görə jurnalın dərs modalındakı
KORPUS→OTAQ seçimi bütün tenant üzrə boşdur
(``registrar.lesson_rooms.lesson_room_choices`` təşkilatın aktiv otaqlarını
oxuyur və heç nə tapmır).

Kök səbəb faza qüsuru DEYİL: ``legacy_rooms`` (J10, order 13) fazası tam və
testlidir, sadəcə klondakı run-ın faza siyahısında yox idi.  Ona görə burada
**heç bir yeni xəritələmə yazılmır** — fazanın öz saf funksiyaları
(``LegacyRoomDecision``, ``room_code``, ``room_capacity``, ``materialise_rooms``)
olduğu kimi işlədilir.  Beləcə təmirin nəticəsi ilə növbəti tam repetisiyanın
nəticəsi bir-birinə uyğun gəlir (eyni kod, eyni kodlaşdırma):

* ``code = "myedu-room-<legacy id>"`` — ``(organization, code)`` unikaldır, yəni
  idempotentlik natural açarla təmin olunur (otaq ADI unikal deyil: 158 otaqdan
  25-i ad təkrarıdır);
* ``building`` — ``rooms.bina`` tam ədədinin onluq mətni ("1"/"2"/"3"/"5");
* ``capacity`` — ``max_student_count`` rəqəmdirsə, deyilsə 0;
* ``floor`` — mənbədə belə sütun YOXDUR, ona görə BOŞ qalır (uydurulmur);
* ``room_types`` (Auditoriya / laboratoriya / emalatxana) hədəfdə qarşılığı
  olmayan ölçüdür — yazılmır.

Mövcud sətrin adı/korpusu **üstündən yazılmır** (``materialise_rooms`` qaydası):
imtahan mərkəzi otağı sonradan adlandıra bilər, import insan işini pozmur.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.apps import apps as django_apps

from .lesson_meta_field_contracts import ROOM_REGISTRY_FIELDS
from .rehearsal_lesson_rooms_phase import LegacyRoomDecision, materialise_rooms
from .source_extraction import open_audited_identity_stream

AUDIT_REASON = "legacy_repair:rooms"
TABLE_HEADERS = ("legacy", "kod", "ad", "korpus", "tutum", "qeyd", "qərar")


@dataclass(frozen=True)
class _Ctx:
    """``materialise_rooms`` yalnız ``organization``-a baxır."""

    organization: object


@dataclass(frozen=True)
class RoomDecision:
    legacy_pk: int
    code: str
    name: str
    building: str
    capacity: int
    rule_codes: tuple[str, ...]
    action: str

    def as_row(self):
        return (
            self.legacy_pk,
            self.code,
            self.name[:24],
            self.building,
            self.capacity,
            ",".join(self.rule_codes)[:28] or "—",
            self.action,
        )


def existing_codes(organization) -> set[str]:
    return set(
        django_apps.get_model("exams", "ExamRoom")
        .objects.filter(organization=organization)
        .values_list("code", flat=True)
    )


def plan_rooms(organization, *, connection_factory, limit: int = 0) -> list[RoomDecision]:
    """Mənbəni audited kontraktla oxu və qərar cədvəlini qur (yazmadan)."""

    present = existing_codes(organization)
    decisions: list[RoomDecision] = []
    with open_audited_identity_stream(connection_factory=connection_factory, contract=ROOM_REGISTRY_FIELDS) as stream:
        for row in stream:
            legacy_pk = row["id"]
            if type(legacy_pk) is not int:
                continue
            decision = LegacyRoomDecision(legacy_pk=legacy_pk, row=row)
            decisions.append(
                RoomDecision(
                    legacy_pk=legacy_pk,
                    code=decision.code,
                    name=decision.name,
                    building=decision.building,
                    capacity=decision.capacity,
                    rule_codes=decision.rule_codes,
                    action="already_present" if decision.code in present else "create",
                )
            )
    decisions.sort(key=lambda item: item.legacy_pk)
    return decisions[:limit] if limit else decisions


def materialise(organization, *, connection_factory, limit: int = 0) -> int:
    """Fazanın öz materialiser-i ilə otaqları idempotent yarat; sayı qaytarır."""

    present = existing_codes(organization)
    decisions = []
    with open_audited_identity_stream(connection_factory=connection_factory, contract=ROOM_REGISTRY_FIELDS) as stream:
        for row in stream:
            legacy_pk = row["id"]
            if type(legacy_pk) is int:
                decisions.append(LegacyRoomDecision(legacy_pk=legacy_pk, row=row))
    decisions.sort(key=lambda item: item.legacy_pk)
    if limit:
        decisions = decisions[:limit]
    materialise_rooms(_Ctx(organization=organization), decisions)
    return len(existing_codes(organization) - present)


def coverage(organization) -> dict[str, int]:
    model = django_apps.get_model("exams", "ExamRoom")
    base = model.objects.filter(organization=organization)
    return {
        "otaq": base.count(),
        "aktiv otaq": base.filter(is_active=True).count(),
        "korpus": len({value for value in base.values_list("building", flat=True) if value}),
    }


__all__ = [
    "AUDIT_REASON",
    "TABLE_HEADERS",
    "RoomDecision",
    "coverage",
    "existing_codes",
    "materialise",
    "plan_rooms",
]
