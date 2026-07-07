"""
Superadmin aləti: təşkilatın bütün tələbələrinə default parol ver və
ilk-giriş axınına sal.

Nə edir:
* Hədəf tələbələrin parolunu default (paylaşılan və ya hər tələbəyə ayrıca
  generasiya olunmuş) parolla əvəzləyir.
* ``profile.password_change_required = True`` qoyur — istifadəçi ilk dəfə
  daxil olanda ``FirstLoginPasswordMiddleware`` onu məcburi setup səhifəsinə
  yönləndirir: yeni email yazır → OTP təsdiqi → yeni parol qoyur → sistemə
  buraxılır (bax: apps/accounts/views/auth/first_login.py).
* ``profile.email_verified = False`` qoyur ki, köhnə/placeholder email
  bərpa üçün istifadə oluna bilməsin.

İstifadə:
    python manage.py provision_student_credentials --org <slug> --password Tel2026!
    python manage.py provision_student_credentials --org <slug> --generate --csv /tmp/creds.csv
    python manage.py provision_student_credentials --org <slug> --password X --dry-run

Default qorunma: artıq setup-u tamamlamış (email təsdiqli, parolunu özü
qoymuş) tələbələrə TOXUNMUR — onları da sıfırlamaq üçün ``--force`` verin.
"""

import csv

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.crypto import get_random_string

User = get_user_model()

# Oxunaqlı, oxşar simvolsuz (0/O, 1/l/I yox) generasiya əlifbası.
_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"


class Command(BaseCommand):
    help = "Təşkilatın tələbələrinə default parol verir və ilk-giriş (email OTP + yeni parol) axınına salır."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--password", help="Bütün tələbələr üçün paylaşılan default parol")
        group.add_argument(
            "--generate",
            action="store_true",
            help="Hər tələbəyə ayrıca təsadüfi parol generasiya et (--csv ilə birlikdə istifadə edin)",
        )
        parser.add_argument("--csv", dest="csv_path", help="username,parol siyahısını bu fayla yaz")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Setup-u artıq tamamlamış tələbələri də sıfırla (email təsdiqi + parol yenidən tələb olunacaq)",
        )
        parser.add_argument("--dry-run", action="store_true", help="Heç nə yazma — yalnız kimlərə dəyəcəyini göstər")

    def handle(self, *args, **options):
        # Request-xarici (management command) DB işi RLS transaction-pooling
        # təhlükəsiz kontekstdə icra olunmalıdır. Superadmin aləti olduğu üçün
        # bütün təşkilat tələbələri görünsün deyə bypass_rls.
        from core.rls import bypass_rls
        from core.rls_pooling import rls_worker_atomic

        with rls_worker_atomic(), bypass_rls():
            self._provision(*args, **options)

    def _provision(self, *args, **options):
        from apps.organizations.models import Membership, Organization

        try:
            organization = Organization.objects.get(slug=options["org"])
        except Organization.DoesNotExist:
            raise CommandError(f"Təşkilat tapılmadı: {options['org']!r}")

        shared_password = options.get("password")
        generate = options.get("generate", False)
        if generate and not options.get("csv_path") and not options.get("dry_run"):
            raise CommandError("--generate rejimində parollar bir daha görünməyəcək — --csv ilə fayla yazın.")

        student_user_ids = (
            Membership.objects.filter(
                organization=organization,
                is_active=True,
                role__name__in=("student", "lead_student"),
            )
            .values_list("user_id", flat=True)
            .distinct()
        )
        users = (
            User.objects.filter(id__in=list(student_user_ids), is_active=True)
            .filter(is_superuser=False, is_staff=False)
            .select_related("profile")
            .order_by("username")
        )

        targets = []
        skipped_configured = 0
        for user in users:
            profile = getattr(user, "profile", None)
            if profile is None:
                continue
            already_configured = bool(profile.email_verified and not profile.password_change_required)
            if already_configured and not options["force"]:
                skipped_configured += 1
                continue
            targets.append(user)

        if options["dry_run"]:
            for user in targets:
                self.stdout.write(f"  → {user.username}")
            self.stdout.write(
                self.style.WARNING(
                    f"DRY-RUN: {len(targets)} tələbəyə default parol veriləcəkdi "
                    f"({skipped_configured} artıq qurulmuş hesab ötürüldü; --force ilə daxil edin)."
                )
            )
            return

        rows = []
        with transaction.atomic():
            for user in targets:
                password = shared_password or get_random_string(10, _PASSWORD_ALPHABET)
                user.set_password(password)
                user.save(update_fields=["password"])

                profile = user.profile
                profile.password_change_required = True
                profile.email_verified = False
                profile.save(update_fields=["password_change_required", "email_verified", "updated_at"])
                rows.append((user.username, password))

        if options.get("csv_path"):
            with open(options["csv_path"], "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["username", "password"])
                writer.writerows(rows)
            self.stdout.write(f"CSV yazıldı: {options['csv_path']}")

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ {len(rows)} tələbəyə default parol verildi və ilk-giriş axınına salındı "
                f"({skipped_configured} artıq qurulmuş hesab ötürüldü). "
                "İlk girişdə: yeni email + OTP təsdiqi + yeni parol tələb olunacaq."
            )
        )
