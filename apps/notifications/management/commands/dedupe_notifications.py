"""Təkrar (dublikat) daxili bildirişləri OXUNMUŞ edir — sahib 2026-10-17 «İkinci bildirişləri oxunmuş et».

Səbəb: 2026-10-17 prod-da ``assign_task_rows_from_timetable`` (magistratura II kurs) «Yer kadastrı və meşəçilik
kafedrası» tapşırığını iki dəfə təsdiqlədi → yükü olan hər müəllimə «Dərs yükü təyin edildi» (tip
``assignment``) iki dəfə getdi; əvvəlki yenidən təsdiqlər də təkrar göndərmiş ola bilər.

QAYDA:

* Təşkilat (``--org`` slug) + tip (``--type``) + tarix aralığı (``--since`` … ``--until``, hər ikisi daxil,
  serverin vaxt qurşağında gün) üzrə YALNIZ oxunmamış, silinməmiş bildirişlər.
* Eyni alıcı + eyni başlıq + mətn + keçid (``link``) + ``metadata`` → bir dəstə. Dəstədə ən erkən bildiriş
  saxlanılır; ondan sonra ``--window-minutes`` (defolt 120) daxilində yaranan eyniləri OXUNMUŞ edilir
  (``is_read`` + ``read_at`` — modelin öz oxunma sahələri). Pəncərədən kənar eyni bildiriş yeni dəstə açır
  (sonrakı həqiqi hadisə kimi qalır). Oxunmuş bildirişlər nəzərə alınmır. Heç nə SİLİNMİR.
* DEFOLT DRY-RUN; ``--apply`` ilə yazır. İdempotent: ikinci işə salınma heç nə tapmır.
* Stdout-a YALNIZ saylar: ``groups`` (təkrarı olan dəstə), ``duplicates_marked_read``, ``users``. Ad yoxdur.

Nümunə::

    python manage.py dedupe_notifications --org qku --type assignment --since 2026-10-17
    python manage.py dedupe_notifications --org qku --type assignment --since 2026-10-01 --until 2026-10-17 --apply
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.notifications.models import InAppNotification, NotificationType
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

_BATCH = 500


def _parse_day(value: str, flag: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CommandError(f"{flag} formatı YYYY-MM-DD olmalıdır") from exc


def _day_start(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())


def find_duplicates(queryset, window: timedelta) -> tuple[list, int, int]:
    """→ (oxunmuş ediləcək pk-lar, təkrarı olan dəstə sayı, alıcı sayı). ``queryset`` — oxunmamışlar."""
    rows = queryset.order_by("recipient_id", "created_at", "pk").values_list(
        "pk", "recipient_id", "title", "message", "link", "metadata", "created_at"
    )
    keepers: dict = {}  # dəstə açarı → (saxlanılan bildirişin vaxtı, dəstədə təkrar varmı)
    duplicate_ids, groups, users = [], 0, set()
    for pk, recipient_id, title, message, link, metadata, created_at in rows.iterator(chunk_size=2000):
        key = (recipient_id, title, message, link, json.dumps(metadata or {}, sort_keys=True, default=str))
        kept = keepers.get(key)
        if kept is None or created_at - kept[0] > window:
            keepers[key] = (created_at, False)
            continue
        if not kept[1]:
            groups += 1
            keepers[key] = (kept[0], True)
        duplicate_ids.append(pk)
        users.add(recipient_id)
    return duplicate_ids, groups, len(users)


class Command(BaseCommand):
    help = "Eyni tip/başlıq/mətn/keçidli təkrar oxunmamış bildirişləri oxunmuş edir (silmir). Defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku).")
        parser.add_argument("--type", required=True, choices=list(NotificationType.values), dest="notification_type")
        parser.add_argument("--since", required=True, help="Başlanğıc gün (YYYY-MM-DD, daxil).")
        parser.add_argument("--until", default="", help="Son gün (YYYY-MM-DD, daxil; boş = bu gün).")
        parser.add_argument("--window-minutes", type=int, default=120, help="Təkrar pəncərəsi (dəqiqə, defolt 120).")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (verilməsə dry-run).")

    def handle(self, *args, **options):
        since = _parse_day(options["since"], "--since")
        until = _parse_day(options["until"], "--until") if options["until"] else timezone.localdate()
        if until < since:
            raise CommandError("--until --since-dən əvvəl ola bilməz")
        minutes = int(options["window_minutes"])
        if minutes <= 0:
            raise CommandError("--window-minutes müsbət olmalıdır")
        apply = bool(options["apply"])

        with transaction.atomic(), rls_worker_atomic(), bypass_rls():
            Organization = django_apps.get_model("organizations", "Organization")
            organization = Organization.objects.filter(slug=options["org"]).first()
            if organization is None:
                raise CommandError(f"organization_not_found: {options['org']}")
            unread = InAppNotification.objects.filter(
                organization=organization,
                notification_type=options["notification_type"],
                is_read=False,
                deleted_at__isnull=True,
                created_at__gte=_day_start(since),
                created_at__lt=_day_start(until + timedelta(days=1)),
            )
            duplicate_ids, groups, users = find_duplicates(unread, timedelta(minutes=minutes))
            marked = 0
            if apply:
                now = timezone.now()
                for start in range(0, len(duplicate_ids), _BATCH):
                    batch = duplicate_ids[start : start + _BATCH]
                    marked += InAppNotification.objects.filter(pk__in=batch, is_read=False).update(
                        is_read=True, read_at=now
                    )

        mode = "APPLY" if apply else "DRY-RUN (heç nə yazılmadı)"
        count = marked if apply else len(duplicate_ids)
        self.stdout.write(f"{mode}: groups={groups} · duplicates_marked_read={count} · users={users}")
