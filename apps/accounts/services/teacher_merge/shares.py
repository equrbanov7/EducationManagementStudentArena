"""Bölünmüş jurnal payları (``JournalShare``) — iki hesab EYNİ jurnaldadırsa BİR pay, rol itmir.

Pay qaydaları :mod:`apps.registrar.journal_shares`-dadır: payı olmayan açılış sahibi TAM görür; pay sahibi öz
``kinds`` (boş = bütün növlər) və ``enrollments`` (boş = bütün tələbələr) əhatəsini görür. Birləşmədən sonra şəxs
iki hesabın əhatələrinin BİRLƏŞMƏSİNİ görməlidir:

* mənbənin AKTİV payı, hədəfin həmin jurnalda payı yoxdur:
  - hədəf açılışın sahibidir (payısız → TAM) → mənbənin payı artıq heç nə vermir, DEAKTİV olur
    (``shares_redundant_deactivated``);
  - əks halda pay hədəfə keçir (``shares_moved``) — mənbə sahib idisə, açılış da hədəfə keçir, eyni əhatə;
* hər ikisinin aktiv payı var → hədəfin payı BİRLƏŞMƏ olur (növlər: biri boşdursa boş, yoxsa birləşmə; tələbələr:
  biri boşdursa hamısı, yoxsa birləşmə), mənbənin payı deaktiv (``shares_collapsed``);
* mənbə açılışın payısız SAHİBİ idi (TAM), hədəfin isə həmin jurnalda payı var → açılış hədəfə keçəndə hədəf
  daralmasın deyə hədəfin payı deaktiv olur (``shares_owner_full_deactivated``);
* mənbənin DEAKTİV (tarixi) payları sadəcə hədəfə keçir (unikallıq yalnız aktivlərdədir).

Heç bir pay silinmir; hər dəyişiklik manifestdədir və ``undo`` geri qaytarır.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils import timezone

SHARE_KEY = "registrar.JournalShare.teacher"


def _share_model():
    return django_apps.get_model("registrar", "JournalShare")


def _links(share) -> set:
    return {str(pk) for pk in share.enrollments.through.objects.filter(journalshare_id=share.pk).values_list(
        "enrollment_id", flat=True)}  # fmt: skip


def _deactivate(share, manifest, counts, key) -> None:
    _share_model().objects.filter(pk=share.pk, is_active=True).update(is_active=False, updated_at=timezone.now())
    manifest["shares"]["deactivated"].append(str(share.pk))
    counts[key] += 1


def _union(source_share, target_share, manifest, counts) -> None:
    source_rows, target_rows = _links(source_share), _links(target_share)
    entry = {"id": str(target_share.pk), "kinds": list(target_share.kinds or []), "added": [], "removed": []}
    if not source_share.kinds or not target_share.kinds:
        kinds = []
    else:
        kinds = sorted(set(source_share.kinds) | set(target_share.kinds))
    if not source_rows or not target_rows:
        entry["removed"] = sorted(target_rows)
        target_share.enrollments.remove(*entry["removed"])
    else:
        entry["added"] = sorted(source_rows - target_rows)
        target_share.enrollments.add(*entry["added"])
    _share_model().objects.filter(pk=target_share.pk).update(kinds=kinds, updated_at=timezone.now())
    manifest["shares"]["updated"].append(entry)
    _deactivate(source_share, manifest, counts, "shares_collapsed")


def collapse(organization, source, target, manifest, counts) -> None:
    """Açılışın müəllimi hələ DƏYİŞMƏMİŞ halda çağırılır (sahiblik buradan oxunur)."""
    share_model = _share_model()
    moved = manifest["moved"].setdefault(SHARE_KEY, [])
    owned = set(
        django_apps.get_model("registrar", "CourseOffering")
        .objects.filter(organization=organization, instructor=source)
        .values_list("pk", flat=True)
    )
    owner_full = owned - set(
        share_model.objects.filter(offering_id__in=owned, teacher=source, is_active=True).values_list(
            "offering_id", flat=True
        )
    )
    rows = share_model.objects.filter(organization=organization, teacher=source).select_related("offering")
    for share in rows.order_by("created_at", "pk"):
        if not share.is_active:
            share_model.objects.filter(pk=share.pk, teacher=source).update(teacher=target, updated_at=timezone.now())
            moved.append(str(share.pk))
            counts["shares_history_moved"] += 1
            continue
        target_share = share_model.objects.filter(offering_id=share.offering_id, teacher=target, is_active=True).first()
        if target_share is not None:
            _union(share, target_share, manifest, counts)
        elif share.offering.instructor_id == target.pk:
            _deactivate(share, manifest, counts, "shares_redundant_deactivated")
        else:
            share_model.objects.filter(pk=share.pk, teacher=source).update(teacher=target, updated_at=timezone.now())
            moved.append(str(share.pk))
            counts["shares_moved"] += 1
    narrowing = share_model.objects.filter(offering_id__in=owner_full, teacher=target, is_active=True)
    for share in narrowing.order_by("created_at", "pk"):
        _deactivate(share, manifest, counts, "shares_owner_full_deactivated")


def restore_updated(manifest, counts) -> None:
    """Birləşdirilmiş (hədəf) payların əvvəlki əhatəsi — növlər və tələbə siyahısı."""
    share_model = _share_model()
    for entry in (manifest.get("shares") or {}).get("updated") or []:
        share = share_model.objects.filter(pk=entry["id"]).first()
        if share is None:
            counts["undo_share_missing"] += 1
            continue
        share.enrollments.remove(*entry.get("added") or [])
        share.enrollments.add(*entry.get("removed") or [])
        share_model.objects.filter(pk=share.pk).update(kinds=entry.get("kinds") or [], updated_at=timezone.now())
        counts["undo_shares_restored"] += 1


def reactivate(manifest, counts) -> None:
    """Deaktiv etdiyimiz paylar (köçən paylar ümumi ``moved`` yolu ilə qayıdır)."""
    share_model = _share_model()
    ids = (manifest.get("shares") or {}).get("deactivated") or []
    for share in share_model.objects.filter(pk__in=ids, is_active=False):
        share_model.objects.filter(pk=share.pk).update(is_active=True, updated_at=timezone.now())
        counts["undo_shares_reactivated"] += 1


__all__ = ["SHARE_KEY", "collapse", "reactivate", "restore_updated"]
