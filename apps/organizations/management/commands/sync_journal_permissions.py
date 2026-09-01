"""MÖVCUD təşkilatlara `journal.*` icazələrini əlavə edir (`roster`, `reassign`, …).

NİYƏ LAZIMDIR. Default rol şablonları (``default_roles_university.UNIVERSITY_ROLES``)
YALNIZ təşkilat YARADILANDA tətbiq olunur (``organizations/signals.py``). Yəni
şablona `journal.roster` əlavə etmək artıq mövcud universitetin dekanına və
proqram koordinatoruna heç nə vermir — «Alt qrupdan tələbə əlavə et» düyməsi
onlara GÖRÜNMƏZ. Bu əmr həmin boşluğu bağlayır.

Əmr PREFİKS-ƏSASLIDIR: şablona əlavə olunan HƏR yeni `journal.*` açarı
avtomatik buradan yayılır — ayrıca əmr yazmağa ehtiyac yoxdur. 2026-08-30-da
`journal.reassign` (fənnin başqa müəllimə təhvili) məhz bu yolla verildi;
kanonik çağırış:

    python manage.py sync_journal_permissions            # kim nə alacaq (yazmır)
    python manage.py sync_journal_permissions --apply    # tətbiq

``sync_people_permissions`` ilə EYNİ təhlükəsizlik qaydaları:

* **Yalnız ƏLAVƏ edir, heç vaxt SİLMİR.**
* **Defolt QURU İŞLƏYİŞ** — yazmaq üçün ``--apply`` məcburidir.
* **Yalnız ``is_system`` rollara** toxunur; universitetin öz xüsusi rolları
  toxunulmaz qalır.
* Mənbə TƏK yerdədir: şablonun özü («kim nə alsın» siyahısı burada saxlanmır).

İstifadə::

    python manage.py sync_journal_permissions              # hesabat (yazmır)
    python manage.py sync_journal_permissions --apply      # tətbiq et
    python manage.py sync_journal_permissions --org qku --apply
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.models import Organization, Role
from core.constants import OrganizationType
from core.rls_pooling import rls_worker_atomic

PREFIX = "journal."


def journal_permissions_by_role() -> dict:
    """{rol adı: [journal.* açarları]} — şablondan çıxarılır (tək mənbə)."""
    mapping = {}
    for template in UNIVERSITY_ROLES:
        keys = [perm for perm in template.get("permissions", []) if str(perm).startswith(PREFIX)]
        if keys:
            mapping[template["name"]] = keys
    return mapping


class Command(BaseCommand):
    help = "Mövcud universitetlərin sistem rollarına `journal.*` icazələrini əlavə edir (additive)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Dəyişikliyi HƏQİQƏTƏN yaz (defolt: quru işləyiş).")
        parser.add_argument("--org", default="", help="Yalnız bu slug-lı təşkilat.")

    def _plan(self, options) -> list:
        wanted = journal_permissions_by_role()
        organizations = Organization.objects.filter(org_type=OrganizationType.UNIVERSITY, is_active=True)
        if options["org"]:
            organizations = organizations.filter(slug=options["org"])

        planned = []
        for organization in organizations.order_by("name"):
            roles = Role.objects.filter(organization=organization, is_system=True, name__in=wanted.keys())
            for role in roles.order_by("-level", "name"):
                current = list(role.permissions or [])
                # `*` daşıyan rol (rektor) onsuz da hər şeyi əhatə edir — toxunma.
                if "*" in current or "journal.*" in current:
                    continue
                missing = [key for key in wanted[role.name] if key not in current]
                if missing:
                    planned.append((organization, role, current + missing, missing))
        return planned

    def handle(self, *args, **options):
        # Request-dən kənar entry-point: bütün DB işi tək worker-atomic sarğısındadır
        # (scripts/check_worker_atomic_coverage.py qapısı).
        with rls_worker_atomic():
            planned = self._plan(options)

        if not planned:
            self.stdout.write(self.style.SUCCESS("Əlavə ediləcək icazə yoxdur — hamısı yerindədir."))
            return

        for organization, role, _new, missing in planned:
            self.stdout.write(f"  {organization.slug} · {role.name}: +{', '.join(missing)}")

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING(f"\nQURU İŞLƏYİŞ — {len(planned)} rol dəyişəcəkdi. Yazmaq üçün: --apply")
            )
            return

        with rls_worker_atomic(), transaction.atomic():
            for _organization, role, new_permissions, _missing in planned:
                Role.objects.filter(pk=role.pk).update(permissions=new_permissions)
        self.stdout.write(self.style.SUCCESS(f"\n{len(planned)} rol yeniləndi."))
