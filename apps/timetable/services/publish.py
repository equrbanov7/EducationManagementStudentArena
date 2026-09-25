"""«Dərc et» — qaralama → canlı ``ScheduleSlot`` (registrar servis qatı, BİR transaksiya).

Semantika: işləmənin BÜTÜN açılışlarının köhnə canlı slotları yumşaq silinir və
qaralamanın YERLƏŞDİRİLMİŞ dərsləri yazılır (yerləşdirilməyən dərs canlı cədvəldə
olmayacaq — UI təsdiq dialoqunda bunu açıq yazır). Axın mühazirəsi hər qrupun
açılışına bir slot kimi yazılır (``stream`` açarı ilə — dərcin toqquşma
yoxlaması onları bir dərs sayır). Bildiriş: hər alıcıya BİR (registrar tərəf).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from apps.registrar.public import schedule_grid, schedule_publish

from ..constants import RunStatus

_CTX = "timetable.publish"

PublishError = schedule_publish.PublishError


def draft_slots(run) -> tuple[list, list]:
    """Qaralamadan registrar-ın ``publish_slots`` girişi: ``(offering_ids, slots)``."""
    periods = {row["no"]: row for row in schedule_grid.lesson_periods(run.organization)}
    rows = list(run.slots.order_by("event_key", "offering_id"))
    offering_ids = sorted({str(row.offering_id) for row in rows})
    streams = {}
    for row in rows:
        streams.setdefault(row.event_key, set()).add(row.offering_id)
    slots = []
    for row in rows:
        if row.weekday is None or row.pair not in periods:
            continue
        period = periods[row.pair]
        slots.append(
            {
                "offering_id": str(row.offering_id),
                "weekday": row.weekday,
                "start_time": period["start"],
                "end_time": period["end"],
                "week_type": row.week_type,
                "kind": row.kind,
                "room": row.room,
                "teacher_id": row.teacher_id,
                "stream": row.event_key if len(streams[row.event_key]) > 1 else "",
            }
        )
    return offering_ids, slots


def publish(run, *, actor, request=None, reason="") -> dict:
    """Qaralamanı dərc et; səhvdə ``PublishError`` (403 icazə, 409 toqquşma, 400 yararsız)."""
    if run.status != RunStatus.DONE:
        raise PublishError("not_ready", pgettext(_CTX, "Yalnız hazır (tamamlanmış) qaralama dərc edilə bilər."))
    offering_ids, slots = draft_slots(run)
    if not slots:
        raise PublishError("empty", pgettext(_CTX, "Qaralamada yerləşdirilmiş dərs yoxdur."))
    with transaction.atomic():
        result = schedule_publish.publish_slots(
            actor=actor,
            organization=run.organization,
            period=run.period,
            offering_ids=offering_ids,
            slots=slots,
            request=request,
            source=f"timetable:{run.pk}",
            reason=reason or pgettext(_CTX, "Avtomatik cədvəl generatoru ilə dərc"),
        )
        type(run).objects.filter(pk=run.pk).update(
            status=RunStatus.PUBLISHED, published_at=timezone.now(), published_by=actor
        )
    run.refresh_from_db()
    return result


__all__ = ["PublishError", "draft_slots", "publish"]
