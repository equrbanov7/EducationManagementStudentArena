"""``profile_completion_report`` — «məlumat natamam» hesabların sayı (sahib 2026-10-17).

Siyasət: :mod:`apps.accounts.profile_completion`. Qapının girişdən sonra dayandıracağı aktiv hesablar rol ailəsinə
(tələbə / heyət) və boş sahəyə (FİN, telefon, e-poçt) görə sayılır. YALNIZ oxuyur, stdout-a YALNIZ saylar çıxır —
istifadəçi adı, FİN, telefon heç vaxt çap olunmur.

İstifadə::

    manage.py profile_completion_report --org qku
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts import profile_completion as policy
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Məcburi profil məlumatları: boş FİN / telefon / e-poçtu olan aktiv hesabların sayı (yalnız oxuyur)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")

    def handle(self, *args, **options):
        Organization = django_apps.get_model("organizations", "Organization")
        Membership = django_apps.get_model("organizations", "Membership")
        User = get_user_model()
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=options["org"]).first()
            if organization is None:
                raise CommandError(f"Təşkilat tapılmadı: {options['org']}")
            memberships: dict = {}
            rows = Membership.objects.filter(organization=organization, is_active=True).select_related("role")
            for membership in rows:
                memberships.setdefault(membership.user_id, []).append(membership)
            users = User.objects.filter(pk__in=list(memberships)).select_related("profile")
            counts: Counter = Counter()
            for user in users.iterator(chunk_size=500):
                family = policy.role_family(memberships.get(user.pk))
                if not family or policy.is_exempt_user(user):
                    counts["exempt_or_no_role"] += 1
                    continue
                counts[f"{family}_total"] += 1
                missing = [
                    spec.key for spec in policy.required_fields(user, memberships[user.pk])
                    if not policy.has_value(user, spec.key)
                ]  # fmt: skip
                if missing:
                    counts[f"{family}_incomplete"] += 1
                for key in missing:
                    counts[f"{family}_missing_{key}"] += 1
        state = "AÇIQ" if policy.gate_enabled() else "SÖNÜLÜ"
        self.stdout.write(f"Qapı: {state} · təşkilat: {organization.slug}")
        for family in (policy.ROLE_STUDENT, policy.ROLE_STAFF):
            parts = [f"cəmi={counts[f'{family}_total']}", f"natamam={counts[f'{family}_incomplete']}"]
            parts += [f"{key}_boş={counts[f'{family}_missing_{key}']}" for key in policy.FIELDS]
            self.stdout.write(f"{family}: " + " · ".join(parts))
        self.stdout.write(f"azad / rolsuz: {counts['exempt_or_no_role']}")
