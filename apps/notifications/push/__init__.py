"""Telefona push bildirişləri — Firebase Cloud Messaging HTTP v1 (sahib 2026-10-25).

* :mod:`.config`   — kredensial (``FCM_SERVICE_ACCOUNT_JSON``) + «Sistem tənzimləmələri» açarı;
* :mod:`.devices`  — cihaz qeydiyyatı (mobil tətbiqin API-si: ``apps/notifications/api_views.py``);
* :mod:`.dispatch` — ``create_notification*`` → ``on_commit`` → Celery ``notifications.push_send`` → FCM;
* :mod:`.messages` — FCM mesajı (alıcının dilində mətn, deep link ``data``);
* :mod:`.fcm`      — OAuth (service account JWT) + ``messages:send`` + cavab təsnifatı.

Mobil komanda üçün sənəd: ``docs/api/PUSH_NOTIFICATIONS.md``.
"""
