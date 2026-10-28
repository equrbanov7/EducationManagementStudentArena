"""Tam jurnal təhvili: iki sahibin paylarını arxivlə, digər müəllimlərin paylarını qoru."""

from django.utils import timezone

from .journal_shares import forget
from .models import JournalShare


class HandoverShareConflict(Exception):
    """Undo əvvəlki icazə vəziyyətini təhlükəsiz qaytara bilmir."""


def deactivate_for_handover(offering, previous, target):
    """Köhnə sahibin yazısını götür; yeni sahibin əvvəlki dar payı tam sahibliyi məhdudlaşdırmasın.

    Pay silinmir: eyni sətir və onun növ/tələbə seçimləri undo üçün olduğu kimi qalır.
    Yalnız təhvilin iki tərəfi; başqa müəllimin bölünmüş jurnal payına toxunulmur.
    Çağıran offering kilidini və atomik tranzaksiyanı saxlayır.
    """
    teachers = {user.pk for user in (previous, target) if user is not None}
    shares = list(
        JournalShare.objects.select_for_update()
        .filter(organization=offering.organization, offering=offering, teacher_id__in=teachers, is_active=True)
        .order_by("pk")
    )
    ids = [share.pk for share in shares]
    if ids:
        JournalShare.objects.filter(pk__in=ids).update(is_active=False, updated_at=timezone.now())
    forget(offering)
    return [str(pk) for pk in ids]


def restore_for_revert(record, offering):
    """Təhvilin öz söndürdüyü payları qaytar; arada yeni pay yaradılıbsa səssizcə əzmə."""
    ids = record.deactivated_share_ids or []
    if not ids:
        return  # Köhnə təhvil qeydlərinin davranışı dəyişmir.
    teachers = {pk for pk in (record.from_instructor_id, record.to_instructor_id) if pk is not None}
    shares = list(
        JournalShare.objects.select_for_update()
        .filter(pk__in=ids, organization=record.organization, offering=offering, teacher_id__in=teachers)
        .order_by("pk")
    )
    if len(shares) != len(set(ids)) or any(share.is_active for share in shares):
        raise HandoverShareConflict
    if JournalShare.objects.filter(
        organization=record.organization,
        offering=offering,
        teacher_id__in=[share.teacher_id for share in shares],
        is_active=True,
    ).exists():
        raise HandoverShareConflict
    JournalShare.objects.filter(pk__in=[share.pk for share in shares]).update(is_active=True, updated_at=timezone.now())
    forget(offering)
