"""Qaydaya uyğun olmayan STAROSTA (``lead_student``) üzvlüklərini tap və (``--apply`` ilə) düzəlt.

2026-10-13 (gecə): köhnə rol axınları starostanı ``scope_unit``-siz (və ya fakültəyə / başqa qrupa bağlı)
yaradırdı — «Starosta» bölməsi açılmırdı. Yeni qayda: starosta yalnız qrup reyestrindən, qrupun qeydiyyatlı
tələbəsi kimi, bir qrupda bir nəfər (``services/group_lead.py``).

DEFOLT QURU QAÇIŞDIR (heç nə yazmır). ``--apply`` ilə KONSERVATİV düzəliş:

* ``no_scope`` / ``scope_not_group`` — tələbənin TƏK aktiv qeydiyyatlı qrupu varsa VƏ həmin qrupun etibarlı
  starostası yoxdursa → starosta həmin qrupa bağlanır (``assign_group_lead``, bildirişsiz, auditli);
  əks halda «əl ilə» kimi çap olunur (dəyişmir).
* ``not_in_group`` — tələbə artıq həmin qrupun qeydiyyatlı tələbəsi deyil (köçürülüb / xaric) → sətir
  deaktiv olur (yeni qrupda AVTOMATİK starosta edilmir — bu, qrupun qərarıdır).
* ``duplicate`` — eyni qrupda ikinci starosta: «əl ilə» (reyestrdə «Starosta təyin et» birini saxlayır).

İstifadə::

    manage.py repair_group_leads --org qku            # hesabat
    manage.py repair_group_leads --org qku --apply    # düzəliş
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.services.group_lead import (
    GroupLeadError,
    assign_group_lead,
    broken_lead_memberships,
    group_lead_map,
    student_groups,
)
from core.audit import log_action
from core.constants import AuditAction
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Starosta (lead_student) üzvlüklərini yoxla; --apply ilə konservativ düzəlt (defolt: quru qaçış)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı")
        parser.add_argument("--apply", action="store_true", help="Düzəlişləri yaz (defolt: yalnız hesabat)")

    def handle(self, *args, **options):
        from apps.organizations.models import Organization

        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=options["org"]).first()
            if organization is None:
                raise CommandError(f"Təşkilat tapılmadı: {options['org']}")
            problems = broken_lead_memberships(organization)
            if not problems:
                self.stdout.write(self.style.SUCCESS("Problemli starosta üzvlüyü yoxdur."))
                return
            apply = options["apply"]
            fixed = manual = 0
            for membership, problem in problems:
                label = f"{membership.user.username} [{problem}] scope={getattr(membership.scope_unit, 'name', '—')}"
                action = (
                    self._fix(organization, membership, problem)
                    if apply
                    else self._plan(organization, membership, problem)
                )
                if action.startswith("manual"):
                    manual += 1
                else:
                    fixed += 1 if apply else 0
                self.stdout.write(f"{label} → {action}")
            mode = "DÜZƏLİŞ" if apply else "QURU QAÇIŞ"
            self.stdout.write(
                self.style.SUCCESS(f"{mode}: {len(problems)} problem, düzəldilib {fixed}, əl ilə {manual}.")
            )

    # ── qərar ─────────────────────────────────────────────────────────────
    def _target(self, organization, membership):
        records = student_groups(organization, membership.user_id)
        if len(records) != 1:
            return None, "manual: tələbənin tək aktiv qrupu yoxdur"
        record = records[0]
        valid = [
            lead
            for lead in group_lead_map(organization, [record.group_id]).get(record.group_id, [])
            if not lead.not_in_group and lead.user_id != membership.user_id
        ]
        if valid:
            return None, f"manual: «{record.group.name}» qrupunun artıq starostası var ({valid[0].username})"
        return record, ""

    def _plan(self, organization, membership, problem):
        if problem == "not_in_group":
            return "deaktiv ediləcək (tələbə bu qrupda deyil)"
        if problem == "duplicate":
            return "manual: qrupda ikinci starosta — reyestrdən birini seçin"
        record, why = self._target(organization, membership)
        return why if record is None else f"«{record.group.name}» qrupuna bağlanacaq"

    def _fix(self, organization, membership, problem):
        if problem == "duplicate":
            return "manual: qrupda ikinci starosta — reyestrdən birini seçin"
        if problem == "not_in_group":
            with transaction.atomic():
                membership.is_active = False
                membership.is_primary = False
                membership.save(update_fields=["is_active", "is_primary", "updated_at"])
                log_action(
                    action=AuditAction.UPDATE,
                    organization=organization,
                    obj=membership,
                    reason="group lead: repair — lead no longer enrolled in scope group",
                    old_values={"lead": membership.user.username, "group": getattr(membership.scope_unit, "name", "")},
                    new_values={"event": "repair_deactivated"},
                )
            return "deaktiv edildi"
        record, why = self._target(organization, membership)
        if record is None:
            return why
        try:
            assign_group_lead(
                organization=organization,
                group=record.group,
                record_id=record.pk,
                actor=None,
                reason="repair_group_leads",
                notify=False,
            )
        except GroupLeadError as exc:
            if exc.code != "already_lead":
                return f"manual: {exc.message}"
            # Tələbə onsuz da qrupun etibarlı starostasıdır — yalnız sınıq ikinci sətir söndürülür.
            membership.is_active = False
            membership.is_primary = False
            membership.save(update_fields=["is_active", "is_primary", "updated_at"])
            return "artıq etibarlı starostadır — sınıq sətir deaktiv edildi"
        return f"«{record.group.name}» qrupuna bağlandı"
