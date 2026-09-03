"""Jurnal DİLİMLƏRİ (J-V7 yeni qaydası): «hər qrupun bir jurnalı olsun».

Niyə (sahibin qərarı, 2026-08-28)
---------------------------------
Əvvəlki qayda çoxqruplu legacy jurnalı ``group=NULL`` TƏK offering-ə yığırdı.
Nəticə ölçüldü: ən böyük açılış 352 dərs × 554 tələbə = 195 008 xana → jurnal
səhifəsi 61 MB HTML verirdi və brauzerdə açılmırdı (median açılış cəmi 140
xanadır).  Yeni qayda: ``journals.groups_id`` massivindəki HƏR qrup öz
``CourseOffering``-ini alır — dərslər hər dilimə TƏKRARLANIR, tələbə isə
YALNIZ öz qrupunun dilimə yazılır.

Dilim açarı
-----------
Ledger möhür açarı ``uniqid:<legacy group pk>`` formasındadır (``slice_key``).
Açar HEÇ VAXT geri parçalanmır — ``uniqid``-in özü ``:`` daşıya bilər
(``OPAQUE_KEY_PATTERN``), ona görə dilim siyahısı həmişə MƏNBƏDƏN
(``journals.groups_id``) yenidən qurulur, açar mətnindən çıxarılmır.

Bu modul heç nə yazmır: yalnız oxu indeksləri və saf qərar funksiyaları.  Bütün
jurnal fazaları (J1…J8) EYNİ funksiyalarla dilim həll edir — ona görə tələbənin
xanası öz qrupunun açılışından başqa yerə düşə bilmir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from django.apps import apps as django_apps

from .rehearsal_contracts import RehearsalContext
from .rehearsal_journal_offerings_source import journal_rows, migrated_target_index, parse_group_ids, validated_uniqid

# Tələbənin qrupu tapılmır / jurnalın qrup siyahısında deyil / o qrupun dilimi
# materiallaşmayıb — üçü də EYNİ fail-closed nəticə verir (sətir atlanır), amma
# qərar kimliyində fərqli token qalır ki, histoqram səbəbi göstərsin.
GROUP_MISSING = "group_missing"
GROUP_MISMATCH = "group_mismatch"
SLICE_MISSING = "slice_missing"


def slice_key(uniqid: str, group_ref: str) -> str:
    """Dilim möhür açarı; ``group_ref`` legacy qrup pk-sının mətnidir."""

    return f"{uniqid}:{group_ref}"


def journal_group_index(context: RehearsalContext) -> dict[str, tuple[str, ...]]:
    """``uniqid`` → jurnalın qrup siyahısı (mənbə sırası, dublikatsız).

    Parse alınmayan/boş ``groups_id`` boş cüt qaytarır: J1 belə jurnalı onsuz da
    ``legacy_journal_groups_invalid`` ilə karantinə atır, burada təxmin yoxdur.
    """

    index: dict[str, tuple[str, ...]] = {}
    for _legacy_pk, row in journal_rows(context):
        members = parse_group_ids(row["groups_id"])
        index[validated_uniqid(row["uniqid"])] = () if members is None else tuple(str(m) for m in members)
    return index


def student_unit_index(context: RehearsalContext) -> dict[str, str]:
    """``students.id`` (legacy) → tələbənin qrup ``OrgUnit`` pk-sı.

    Mənbəyə YENİ axın açılmır: cavab artıq HƏDƏFdədir — SAR fazası (order 28)
    hər tələbə üçün ``StudentAcademicRecord.group``-u yazıb, ledger isə legacy
    ``students.id``-ni həmin qeydə bağlayıb.  Beləliklə J4/J5 nə ``students``
    cədvəlini yenidən oxuyur, nə də table-plan-a yeni asılılıq gətirir.
    """

    from .rehearsal_sar_targets import SAR_ENTITY_TYPE

    records = migrated_target_index(context, SAR_ENTITY_TYPE)
    if not records:
        return {}
    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    units = {
        str(pk): "" if group_id is None else str(group_id)
        for pk, group_id in record_model.objects.filter(
            organization=context.organization, pk__in=set(records.values())
        ).values_list("pk", "group_id")
    }
    index: dict[str, str] = {}
    for legacy_pk, record_pk in records.items():
        unit_pk = units.get(str(record_pk), "")
        if unit_pk:
            index[str(legacy_pk)] = unit_pk
    return index


def enrollment_offering_index(context: RehearsalContext) -> dict[str, str]:
    """``Enrollment`` pk → ``CourseOffering`` pk (bu tenantın hamısı, bir sorğu).

    J4/J5 xanası öz açılışını MƏHZ buradan alır: yazılışı J2 tələbənin öz qrup
    dilimə bağlayıb, ona görə bu indeks «xana hansı jurnala düşür» sualının
    yeganə doğru cavabıdır — qrup həllinin təkrarı deyil, onun NƏTİCƏSİDİR.
    """

    model = django_apps.get_model("registrar", "Enrollment")
    rows = model.objects.filter(organization=context.organization).values_list("pk", "offering_id")
    return {str(pk): str(offering_id) for pk, offering_id in rows.iterator(chunk_size=10_000)}


@dataclass(frozen=True)
class JournalSlices:
    """Bir run-un dilim mənzərəsi: jurnal → qruplar, tələbə → qrup, dilim → açılış."""

    groups_by_journal: Mapping[str, tuple[str, ...]]
    group_units: Mapping[str, str]  # legacy qrup pk → ``OrgUnit`` pk
    student_units: Mapping[str, str]  # legacy tələbə pk → ``OrgUnit`` pk
    offerings: Mapping[str, str]  # dilim açarı → ``CourseOffering`` pk

    def slice_keys(self, uniqid: str) -> tuple[str, ...]:
        """Bu jurnalın MATERİALLAŞMIŞ dilimləri, mənbə sırasında."""

        keys = (slice_key(uniqid, group_ref) for group_ref in self.groups_by_journal.get(uniqid, ()))
        return tuple(key for key in keys if key in self.offerings)

    def slice_pairs(self, uniqid: str) -> tuple[tuple[str, str], ...]:
        """``(qrup ref, açılış pk)`` cütləri — J3 dərsi hər dilimə təkrarlayır."""

        pairs = ((group_ref, slice_key(uniqid, group_ref)) for group_ref in self.groups_by_journal.get(uniqid, ()))
        return tuple((group_ref, self.offerings[key]) for group_ref, key in pairs if key in self.offerings)

    def journal_uniqids(self) -> frozenset[str]:
        """Heç olmasa bir dilimi materiallaşmış jurnalların ``uniqid`` dəsti."""

        return frozenset(uniqid for uniqid in self.groups_by_journal if self.slice_keys(uniqid))

    def has_offering(self, uniqid: str) -> bool:
        """J4/J5/J6/J8 orphan qapısı: jurnalın heç olmasa bir dilimi varmı."""

        return bool(self.slice_keys(uniqid))

    def primary_offering(self, uniqid: str) -> str:
        """Jurnal-səviyyə möhürün göstərəcəyi açılış — ilk dilim (deterministik)."""

        keys = self.slice_keys(uniqid)
        return self.offerings[keys[0]] if keys else ""

    def resolve_student(self, uniqid: str, student_ref: str) -> tuple[str, str]:
        """``(dilim açarı, səbəb)`` — səbəb "" olduqda dilim tapılıb.

        TƏK qruplu jurnalda seçim yoxdur: jurnalın özü qrupu ELAN edir, ona görə
        siyahıdakı hər tələbə həmin dilimə yazılır.  Bu qəsdəndir —
        ``students.group_id`` tələbənin BUGÜNKÜ qrupudur, 2021-ci il jurnalının
        qrupu deyil; ölçüyə görə (real çıxarış) ciddi uyğunluq tələb etmək
        tarixi jurnalların 12.3 %-ini, o cümlədən artıq mövcud olmayan qrupların
        BÜTÜN balını atardı.

        ÇOX qruplu jurnalda isə seçim var və mənbədə başqa siqnal yoxdur:
        tələbənin cari qrupu dilimlərdən birinə baxmalıdır, yoxsa sətir
        fail-closed atlanır (təxminlə "birinci qrupa" atmaq balı yad qrupun
        jurnalına yazardı).
        """

        groups = self.groups_by_journal.get(uniqid, ())
        if len(groups) == 1:
            key = slice_key(uniqid, groups[0])
            return (key, "") if key in self.offerings else ("", SLICE_MISSING)

        unit_pk = self.student_units.get(str(student_ref), "")
        if not unit_pk:
            return "", GROUP_MISSING
        # Uyğunluq HƏDƏF vahidi üzərindən qurulur: iki legacy qrup açarı bir
        # ``OrgUnit``-ə baxa bilər (§5.1 birləşməsi), legacy açarı müqayisə
        # etmək belə tələbəni nahaq yerə uyğunsuz sayardı.
        for group_ref in groups:
            if self.group_units.get(group_ref, "") != unit_pk:
                continue
            key = slice_key(uniqid, group_ref)
            return (key, "") if key in self.offerings else ("", SLICE_MISSING)
        return "", GROUP_MISMATCH

    def offering_for_student(self, uniqid: str, student_ref: str) -> str:
        """Tələbənin xanasının düşəcəyi açılış; tapılmasa "" (fail-closed)."""

        key, _reason = self.resolve_student(uniqid, student_ref)
        return self.offerings.get(key, "") if key else ""


def build_journal_slices(context: RehearsalContext, offerings: Mapping[str, str]) -> JournalSlices:
    """Dilim mənzərəsini qur; ``offerings`` J1-in MIGRATED ledger indeksidir."""

    from .rehearsal_structure_targets import GROUP_ENTITY_TYPE

    return JournalSlices(
        groups_by_journal=journal_group_index(context),
        group_units=migrated_target_index(context, GROUP_ENTITY_TYPE),
        student_units=student_unit_index(context),
        offerings=offerings,
    )


def build_offering_slices(context: RehearsalContext, offerings: Mapping[str, str]) -> JournalSlices:
    """Yalnız jurnal→dilim istiqaməti lazım olan fazalar üçün (J3, J8).

    Tələbə indeksi qəsdən qurulmur — bu formada ``resolve_student`` HƏMİŞƏ
    ``GROUP_MISSING`` qaytarır, ona görə tələbə-səviyyə qərar verən faza
    ``build_journal_slices`` işlətməlidir.
    """

    return JournalSlices(
        groups_by_journal=journal_group_index(context), group_units={}, student_units={}, offerings=offerings
    )


__all__ = [
    "GROUP_MISMATCH",
    "GROUP_MISSING",
    "SLICE_MISSING",
    "JournalSlices",
    "build_journal_slices",
    "build_offering_slices",
    "enrollment_offering_index",
    "journal_group_index",
    "slice_key",
    "student_unit_index",
]
