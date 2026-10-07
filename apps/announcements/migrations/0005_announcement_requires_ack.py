"""Məcburi tanışlıq (sahib, 2026-10-07): ``Announcement.requires_ack`` + ``AnnouncementReceipt.acknowledged_at``.

* ``requires_ack`` ``db_default=False`` ilə gəlir: köhnə kod (rolling deploy) sütunsuz INSERT etsə
  də sətir «məcburi deyil» sayılır; mövcud sətirlər üçün cədvəlin yenidən yazılması lazım deyil
  (PostgreSQL ≥ 11 sabit DEFAULT-u metadata ilə əlavə edir).
* ``ann_ack_needs_popup`` — məcburi elan həmişə popup-dur (``requires_ack ⇒ show_as_popup``).
  Mövcud sətirlərin hamısında ``requires_ack = false`` olduğundan CHECK dərhal ödənir.
* RLS: ``0002_rls_announcements`` siyasəti cədvəl səviyyəsindədir və yalnız ``organization_id``-yə
  baxır — ADD COLUMN onu dəyişmir.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("announcements", "0004_announcement_soft_delete"),
    ]

    operations = [
        migrations.AddField(
            model_name="announcement",
            name="requires_ack",
            field=models.BooleanField(db_default=False, default=False),
        ),
        migrations.AddField(
            model_name="announcementreceipt",
            name="acknowledged_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="announcement",
            constraint=models.CheckConstraint(
                condition=models.Q(("requires_ack", False), ("show_as_popup", True), _connector="OR"),
                name="ann_ack_needs_popup",
            ),
        ),
    ]
