"""«Alt qrup» nişanı yalnız SƏNƏDLƏ təsdiqlənmiş yerləşdirməyə (sahib 2026-10-25).

Sahib: «Alt qrup məsələsi ciddidir … tələbələr görsə ki dəqiq deyil və alt qrup görünür, problem olacaq. Bilməsən
yazma.» Köçürmə (legacy delta, rollup, intensiv) bir çox qeydiyyata ``source_group`` yazıb: ana qrupun («234 K az»)
jurnalındakı «234 K-1» tələbəsi, ixtisas bölgüsü («635 2» → «635Qrafik»), birgə dərs və s. — bunlar akademik borc
«alt qrupu» DEYİL, amma köhnə predikat (``source_group`` dolu VƏ jurnalın qrupu cari qrup deyil) hamısını nişanlayırdı.

Göstəriş qaydası: nişan YALNIZ bu qeydiyyat üçün sənəd varsa — «Alt qrupdan tələbə əlavə et» modalının
:class:`GuestRosterDocument`-i və ya geri götürülməmiş, sənədli «Alt qrupa yerləşdirildi» sətri
(:class:`SubgroupPlacementEvent`). Köçürmənin sənədsiz sətirləri (``details.via=import``) sayılmır. Data dəyişmir —
``source_group`` provenansı və tarixçə yerində qalır; yalnız GÖSTƏRİŞ və kredit bölgüsü bu süzgəcdən keçir.
"""

from __future__ import annotations

from collections.abc import Iterable


def documented_subgroup_ids(enrollment_ids: Iterable) -> set:
    """*enrollment_ids* içindən sənədlə təsdiqlənmiş «alt qrup» qeydiyyatlarının id-ləri (≤ 2 sorğu)."""
    from .models import GuestRosterDocument, SubgroupPlacementEvent

    ids = [pk for pk in enrollment_ids if pk]
    if not ids:
        return set()
    found = set(GuestRosterDocument.objects.filter(enrollment_id__in=ids).values_list("enrollment_id", flat=True))
    rest = [pk for pk in ids if pk not in found]
    if rest:
        found |= set(
            SubgroupPlacementEvent.objects.filter(
                enrollment_id__in=rest,
                kind="place",
                document__isnull=False,
                undone_by__isnull=True,
            ).values_list("enrollment_id", flat=True)
        )
    return found


def annotate_documented(queryset):
    """Enrollment queryset-inə ``subgroup_documented`` (bool) — eyni qayda, ƏLAVƏ SORĞUSUZ (EXISTS alt sorğusu)."""
    from django.db.models import Exists, OuterRef

    from .models import GuestRosterDocument, SubgroupPlacementEvent

    has_document = Exists(GuestRosterDocument.objects.filter(enrollment_id=OuterRef("pk")))
    has_placement = Exists(
        SubgroupPlacementEvent.objects.filter(
            enrollment_id=OuterRef("pk"), kind="place", document__isnull=False, undone_by__isnull=True
        )
    )
    return queryset.annotate(subgroup_documented=has_document | has_placement)


__all__ = ["annotate_documented", "documented_subgroup_ids"]
