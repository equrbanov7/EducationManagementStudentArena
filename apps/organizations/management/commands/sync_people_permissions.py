"""MÖVCUD təşkilatlara «Müəllimlər/Tələbələr» kataloqu icazələrini əlavə edir.

NİYƏ LAZIMDIR. Default rol şablonları (``default_roles_university.UNIVERSITY_ROLES``)
YALNIZ təşkilat YARADILANDA tətbiq olunur (``organizations/signals.py``). Yəni
şablona yeni açar əlavə etmək artıq mövcud universitetin dekanına heç nə vermir —
onlar üçün açar əl ilə (icazə redaktorundan) və ya bu əmrlə verilməlidir.

TƏHLÜKƏSİZLİK QAYDALARI (dəyişdirməzdən əvvəl oxu):

* **Yalnız ƏLAVƏ edir, heç vaxt SİLMİR.** Əməliyyatçının redaktordan çıxardığı
  açarı geri qaytarmaq üçün əmr təkrar işlədilməlidir — səssiz «bərpa» yoxdur.
* **Defolt olaraq QURU İŞLƏYİR** (yalnız hesabat). Yazmaq üçün ``--apply``
  MƏCBURİDİR: icazə paylamaq təsadüfən baş verməməlidir.
* **Yalnız ``is_system`` rollara toxunur** — universitetin öz əli ilə qurduğu
  xüsusi rollar toxunulmaz qalır.
* Mənbə TƏK yerdədir: şablonun özü. Burada ayrıca «kim nə alsın» siyahısı
  saxlanmır ki, iki yer bir-birindən ayrılmasın.

İstifadə::

    python manage.py sync_people_permissions              # hesabat (yazmır)
    python manage.py sync_people_permissions --apply      # tətbiq et
    python manage.py sync_people_permissions --org qku --apply
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.models import Organization, Role
from core.constants import OrganizationType

PREFIX = "people."


def people_permissions_by_role() -> dict:
    """{rol adı: [people.* açarları]} — şablondan çıxarılır (tək mənbə)."""
    mapping = {}
    for template in UNIVERSITY_ROLES:
        keys = [perm for perm in template.get("permissions", []) if str(perm).startswith(PREFIX)]
        if keys:
            mapping[template["name"]] = keys
    return mapping


class Command(BaseCommand):
    help = "Mövcud universitetlərin sistem rollarına `people.*` kataloq icazələrini əlavə edir (additive)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Dəyişikliyi HƏQİQƏTƏN yaz (defolt: quru işləyiş).")
        parser.add_argument("--org", default="", help="Yalnız bu slug-lı təşkilat.")

    def handle(self, *args, **options):
        wanted = people_permissions_by_role()
        organizations = Organization.objects.filter(org_type=OrganizationType.UNIVERSITY, is_active=True)
        if options["org"]:
            organizations = organizations.filter(slug=options["org"])

        planned = []
        for organization in organizations.order_by("name"):
            roles = Role.objects.filter(organization=organization, is_system=True, name__in=wanted.keys())
            for role in roles.order_by("-level", "name"):
                current = list(role.permissions or [])
                # `*` daşıyan rol (rektor) onsuz da hər şeyi əhatə edir — toxunma.
                if "*" in current:
                    continue
                missing = [key for key in wanted[role.name] if key not in current]
                if missing:
                    planned.append((organization, role, current + missing, missing))

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

        with transaction.atomic():
            for _organization, role, new_permissions, _missing in planned:
                Role.objects.filter(pk=role.pk).update(permissions=new_permissions)
        self.stdout.write(self.style.SUCCESS(f"\n{len(planned)} rol yeniləndi."))
