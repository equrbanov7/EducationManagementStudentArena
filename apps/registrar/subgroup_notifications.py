"""«Alt qrupa yerləşdirmə» bildirişləri — tələbəyə və jurnalın müəlliminə (sahib 2026-10-18).

``transaction.on_commit`` ilə çağırılır (yazı commit olandan sonra); hər iki alıcı TƏK toplu INSERT-də
(``notifications.public.create_notifications``). Asılılıq istiqaməti registrar → notifications
(:mod:`apps.registrar.journal_notifications` ilə eyni).
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext


def _items(event, *, undo: bool) -> list:
    offering = event.offering
    subject = offering.subject.name
    group = getattr(offering.group, "name", "") or "—"
    student = event.student
    student_name = (student.get_full_name() or "").strip() or student.username
    metadata = {
        "event": "subgroup_placement_undo" if undo else "subgroup_placement",
        "offering_id": str(offering.pk),
        "placement_event_id": str(event.pk),
    }
    if undo:
        student_title = pgettext(
            "registrar.subgroup_placement", "Alt qrup yerləşdirməsi geri götürüldü — %(subject)s"
        ) % {"subject": subject}
        student_message = pgettext(
            "registrar.subgroup_placement", "Siz «%(subject)s» fənni üzrə %(group)s qrupunun jurnalından çıxarıldınız."
        ) % {"subject": subject, "group": group}
        teacher_message = pgettext(
            "registrar.subgroup_placement", "%(student)s jurnaldan çıxarıldı (alt qrup yerləşdirməsi geri götürüldü)."
        ) % {"student": student_name}
    else:
        student_title = pgettext("registrar.subgroup_placement", "Alt qrupa yerləşdirildiniz — %(subject)s") % {
            "subject": subject
        }
        student_message = pgettext(
            "registrar.subgroup_placement",
            "«%(subject)s» fənnini bu semestr %(group)s qrupu ilə keçəcəksiniz. Fənn cədvəlinizdə və jurnalınızda görünür.",
        ) % {"subject": subject, "group": group}
        teacher_message = pgettext(
            "registrar.subgroup_placement", "%(student)s alt qrupdan jurnalınıza əlavə olundu (öz qrupu: %(source)s)."
        ) % {"student": student_name, "source": getattr(event.source_group, "name", "") or "—"}
    profile = reverse("accounts:profile")
    items = [
        {
            "recipient": student,
            "title": student_title,
            "message": student_message,
            "link": f"{profile}?section=my-subjects",
            "organization": event.organization,
            "metadata": metadata,
        }
    ]
    if offering.instructor_id and offering.instructor_id != student.pk:
        items.append(
            {
                "recipient": offering.instructor,
                "title": pgettext("registrar.subgroup_placement", "Jurnal siyahısı dəyişdi — %(subject)s · %(group)s")
                % {"subject": subject, "group": group},
                "message": teacher_message,
                "link": reverse("registrar:journal_detail", args=[offering.pk]),
                "organization": event.organization,
                "metadata": metadata,
            }
        )
    return items


def notify(event, *, undo: bool = False) -> int:
    """Bildirişləri yaradır; xəta yerləşdirməni pozmur (bildiriş ikinci dərəcəlidir)."""
    import logging

    from apps.notifications.public import create_notifications

    try:
        items = _items(event, undo=undo)
        create_notifications(items)
        return len(items)
    except Exception:  # noqa: BLE001 — bildiriş xətası commit olunmuş yerləşdirməni geri qaytarmamalıdır
        logging.getLogger(__name__).warning("subgroup placement notification failed", exc_info=True)
        return 0


__all__ = ["notify"]
