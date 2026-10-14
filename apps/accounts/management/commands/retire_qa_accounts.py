"""QA test hesablarını (``qa.*``) prod üzvlük reyestrindən çıxar — silmədən, geri qaytarıla bilən şəkildə.

Sahib 2026-10-14: «QA deyə açılmış vəzifələri sil, burdan görünməsin» — prod reyestrində (Rol=Dekan)
real dekanın yanında «QA Dean · qa.dean@qa.local» görünürdü.

TAPMA QAYDASI (konservativ, hər iki şərt birlikdə)::

    username  ^qa\\.            VƏ
    (email  @qa.local ilə bitir  VƏ YA  username scripts/qa_live/accounts.py siyahısındadır)

Yəni adı «qa» ilə başlayan, amma real e-poçtlu istifadəçiyə TOXUNULMUR. Hesablar sintetikdir (şəxsi data
deyil) — istifadəçi adları çap olunur.

DEFOLT QURU QAÇIŞDIR (heç nə yazmır). ``--apply`` ilə (hər hesab üçün, tək tranzaksiyada)::

* ``--org``-dakı AKTİV üzvlüklər ``is_active=False`` olur (silinmir);
* ``auth_user.is_active=False`` (başqa təşkilatda aktiv üzvlüyü yoxdursa) — girişin yeganə qapısı budur;
* hər hesab üçün bir audit sətri: səbəb «QA test hesabı prod-dan çıxarıldı (sahib 2026-10-14)» + paket id-si.

``access_state='archived'`` QƏSDƏN qoyulmur: ``archived → active`` keçidi DB trigger-i (0016) ilə rəsmi
bərpa sübutu tələb edir, yəni əmr geri qaytarıla bilməzdi. ``is_active=False`` isə hər giriş səthini
(ModelBackend, OTP, parol sıfırlama) bağlayır və ``--undo`` ilə birbaşa açılır.

``--undo`` — eyni PAKETİN hesablarını bərpa edir (audit sətirlərindəki üzvlük id-ləri və əvvəlki
``is_active`` ilə); ``--batch`` verilməsə, bu təşkilatın hələ geri qaytarılmamış ən son paketi götürülür.

İstifadə::

    manage.py retire_qa_accounts --org qku                      # hesabat
    manage.py retire_qa_accounts --org qku --apply              # çıxar (paket id-si çap olunur)
    manage.py retire_qa_accounts --org qku --undo [--batch ID]  # geri qaytar
"""

from __future__ import annotations

import re
import uuid

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

RETIRE_REASON = "QA test hesabı prod-dan çıxarıldı (sahib 2026-10-14)"
RESTORE_REASON = "QA test hesabı bərpa edildi"
USERNAME_RE = r"^qa\."
EMAIL_SUFFIX = "@qa.local"
_BATCH_RE = re.compile(r"\[batch (?P<id>[0-9a-z-]+)\]")
_UNDO_RE = re.compile(r"\[undo (?P<id>[0-9a-z-]+)\]")


def known_qa_usernames() -> set[str]:
    """``scripts/qa_live/accounts.py`` siyahısı; image-də yoxdursa boş (qayda yalnız e-poçta düşür)."""

    try:
        from scripts.qa_live.accounts import BY_USERNAME
    except ImportError:  # pragma: no cover - scripts/ olmayan quraşdırma
        return set()
    return set(BY_USERNAME)


class Command(BaseCommand):
    help = "QA test hesablarını (qa.*) təşkilatdan çıxar: defolt quru qaçış, --apply, --undo (silmir)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="", help="Təşkilatın slug-ı (məcburi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: yalnız hesabat)")
        parser.add_argument("--undo", action="store_true", help="Paketin hesablarını bərpa et")
        parser.add_argument("--batch", default="", help="--undo üçün paket id-si (defolt: ən son paket)")

    def handle(self, *args, **options):
        slug = (options["org"] or "").strip()
        if not slug:
            raise CommandError("--org məcburidir (təşkilatın slug-ı).")
        if options["undo"] and options["apply"]:
            raise CommandError("--apply və --undo birlikdə verilmir.")
        Organization = django_apps.get_model("organizations", "Organization")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=slug).first()
            if organization is None:
                raise CommandError(f"Təşkilat tapılmadı: {slug}")
            if options["undo"]:
                self._undo(organization, options["batch"].strip())
            else:
                self._retire(organization, apply=options["apply"])

    # ── tapma ──────────────────────────────────────────────────────────────
    def _candidates(self, organization):
        """Təşkilatdakı AKTİV qa.* hesabları (aktiv üzvlük VƏ YA aktiv istifadəçi)."""

        User = get_user_model()
        known = known_qa_usernames()
        rule = Q(email__iendswith=EMAIL_SUFFIX)
        if known:
            rule |= Q(username__in=known)
        in_org = Q(memberships__organization=organization) | Q(profile__organization=organization)
        users = (
            User.objects.filter(username__regex=USERNAME_RE).filter(rule).filter(in_org).distinct().order_by("username")
        )
        result = []
        for user in users:
            memberships = list(user.memberships.filter(organization=organization, is_active=True))
            # Aktiv üzvlüyü yoxdursa, yalnız hələ də GİRİŞ edə bilən (başqa təşkilatda da aktiv üzvlüyü olmayan)
            # hesab sayılır — əks halda təkrar qaçış eyni hesabı yenidən «tapardı».
            elsewhere = user.memberships.filter(is_active=True).exclude(organization=organization).exists()
            if memberships or (user.is_active and not elsewhere):
                result.append((user, memberships))
        return result

    # ── çıxarma ────────────────────────────────────────────────────────────
    def _retire(self, organization, *, apply):
        found = self._candidates(organization)
        mode = "ÇIXARILIR" if apply else "QURU QAÇIŞ"
        self.stdout.write(f"QA hesabları ({organization.slug}): {len(found)} tapıldı [{mode}]")
        if not found:
            self.stdout.write(self.style.SUCCESS("Çıxarılacaq QA hesabı yoxdur."))
            return
        batch = f"qa-retire-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
        memberships_total = 0
        for user, memberships in found:
            memberships_total += len(memberships)
            roles = ", ".join(sorted({m.role.name for m in memberships})) or "—"
            self.stdout.write(
                f"  {user.username}  aktiv_üzvlük={len(memberships)}  rollar={roles}  istifadəçi_aktiv={user.is_active}"
            )
            if apply:
                self._retire_one(organization, user, memberships, batch)
        if not apply:
            self.stdout.write(
                self.style.SUCCESS(
                    f"DRY-RUN: {len(found)} hesab, {memberships_total} aktiv üzvlük çıxarılacaq (heç nə yazılmadı)."
                )
            )
            return
        self.stdout.write(
            self.style.SUCCESS(f"YAZILDI: {len(found)} hesab, {memberships_total} üzvlük deaktiv. paket={batch}")
        )

    def _retire_one(self, organization, user, memberships, batch):
        Membership = django_apps.get_model("organizations", "Membership")
        with transaction.atomic():
            ids = [str(m.pk) for m in memberships]
            if ids:
                Membership.objects.filter(pk__in=[m.pk for m in memberships]).update(
                    is_active=False, updated_at=timezone.now()
                )
            was_active = user.is_active
            still_elsewhere = (
                Membership.objects.filter(user=user, is_active=True).exclude(organization=organization).exists()
            )
            user_deactivated = was_active and not still_elsewhere
            if user_deactivated:
                user.is_active = False
                user.save(update_fields=["is_active"])
            log_action(
                action=AuditAction.UPDATE,
                organization=organization,
                obj=user,
                reason=f"{RETIRE_REASON} [batch {batch}]",
                old_values={"is_active": was_active, "memberships": ids},
                new_values={
                    "event": "qa_account_retired",
                    "batch": batch,
                    "username": user.username,
                    "membership_ids": ids,
                    "user_deactivated": user_deactivated,
                },
            )

    # ── geri qaytarma ──────────────────────────────────────────────────────
    def _audit_rows(self, organization):
        AuditLog = django_apps.get_model("audit", "AuditLog")
        return AuditLog.objects.filter(organization=organization, reason__startswith=RETIRE_REASON)

    def _undone_batches(self, organization) -> set[str]:
        AuditLog = django_apps.get_model("audit", "AuditLog")
        reasons = AuditLog.objects.filter(organization=organization, reason__startswith=RESTORE_REASON).values_list(
            "reason", flat=True
        )
        return {m.group("id") for reason in reasons if (m := _UNDO_RE.search(reason))}

    def _latest_open_batch(self, organization) -> str:
        undone = self._undone_batches(organization)
        for reason in self._audit_rows(organization).order_by("-created_at").values_list("reason", flat=True):
            match = _BATCH_RE.search(reason)
            if match and match.group("id") not in undone:
                return match.group("id")
        return ""

    def _undo(self, organization, batch):
        batch = batch or self._latest_open_batch(organization)
        if not batch:
            raise CommandError("Geri qaytarılacaq paket tapılmadı.")
        if batch in self._undone_batches(organization):
            raise CommandError(f"Paket artıq geri qaytarılıb: {batch}")
        rows = list(self._audit_rows(organization).filter(reason__contains=f"[batch {batch}]").order_by("created_at"))
        if not rows:
            raise CommandError(f"Paket tapılmadı: {batch}")
        User = get_user_model()
        Membership = django_apps.get_model("organizations", "Membership")
        self.stdout.write(f"Paket {batch}: {len(rows)} hesab bərpa olunur")
        restored = 0
        for row in rows:
            data = row.new_values or {}
            username = data.get("username", "")
            user = User.objects.filter(pk=row.object_id).first() if row.object_id else None
            if user is None:
                self.stdout.write(f"  {username or row.object_id}  tapılmadı — keçildi")
                continue
            with transaction.atomic():
                Membership.objects.filter(pk__in=data.get("membership_ids", []), organization=organization).update(
                    is_active=True, updated_at=timezone.now()
                )
                if data.get("user_deactivated") and not user.is_active:
                    user.is_active = True
                    user.save(update_fields=["is_active"])
                log_action(
                    action=AuditAction.UPDATE,
                    organization=organization,
                    obj=user,
                    reason=f"{RESTORE_REASON} [undo {batch}]",
                    old_values={"is_active": False},
                    new_values={"event": "qa_account_restored", "batch": batch, "username": user.username},
                )
            restored += 1
            self.stdout.write(f"  {user.username}  bərpa edildi")
        self.stdout.write(self.style.SUCCESS(f"GERİ QAYTARILDI: {restored} hesab. paket={batch}"))
