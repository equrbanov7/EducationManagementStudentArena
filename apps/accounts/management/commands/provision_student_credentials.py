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
    # QRUP-QRUP çap (kurator siyahını qrupa paylayır):
    python manage.py provision_student_credentials --org <slug> --group "634 Qrafik" \
        --generate --csv /tmp/634-qrafik.csv

Default qorunma: artıq setup-u tamamlamış (email təsdiqli, parolunu özü
qoymuş) tələbələrə TOXUNMUR — onları da sıfırlamaq üçün ``--force`` verin.

2026-09-15 (sahibin qərarı, deploy hazırlığı): ``--audience teachers`` müəllim
hesabları üçün (rollar: teacher, assistant); CSV artıq PAYLAMA siyahısıdır —
fakültə / kafedra / proqram / qrup / tələbə kodu / ad-soyad sütunları ilə,
fakültə → qrup → ad sırasında (kurator öz qrupunu, kafedra öz müəllimlərini
kəsib paylayır). İlk girişdə e-poçt + OTP + yeni parol məcburidir (dəyişməyib).
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.crypto import get_random_string

from core.export_safety import safe_csv_writer
from core.management.command_safety import ProductionCommandSafetyMixin

User = get_user_model()

# Oxunaqlı, oxşar simvolsuz (0/O, 1/l/I yox) generasiya əlifbası.
_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"


class Command(ProductionCommandSafetyMixin, BaseCommand):
    safety_command_name = "provision_student_credentials"
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
            "--group",
            dest="group",
            help="Yalnız bu qrupun tələbələri (OrgUnit adı və ya kodu) — siyahını qrup-qrup çap etmək üçün",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Setup-u artıq tamamlamış tələbələri də sıfırla (email təsdiqi + parol yenidən tələb olunacaq)",
        )
        parser.add_argument("--dry-run", action="store_true", help="Heç nə yazma — yalnız kimlərə dəyəcəyini göstər")
        parser.add_argument(
            "--username",
            action="append",
            dest="usernames",
            default=[],
            help="Yalnız bu istifadəçi adları (təkrarlana bilər) — məs. iki RİM rəhbəri üçün",
        )
        parser.add_argument(
            "--audience",
            choices=("students", "teachers"),
            default="students",
            help="students (defolt: student/lead_student rolları) və ya teachers (teacher/assistant rolları)",
        )

    def handle(self, *args, **options):
        # Request-xarici (management command) DB işi RLS transaction-pooling
        # təhlükəsiz kontekstdə icra olunmalıdır. Superadmin aləti olduğu üçün
        # bütün təşkilat tələbələri görünsün deyə bypass_rls.
        from core.rls import bypass_rls
        from core.rls_pooling import rls_worker_atomic

        with rls_worker_atomic(), bypass_rls():
            self._provision(*args, **options)

    def _provision(self, *args, **options):
        from django.db.models import Q

        from apps.organizations.models import Membership, Organization, OrgUnit
        from core.constants import OrgUnitType

        try:
            organization = Organization.objects.get(slug=options["org"])
        except Organization.DoesNotExist:
            raise CommandError(f"Təşkilat tapılmadı: {options['org']!r}")

        shared_password = options.get("password")
        generate = options.get("generate", False)
        if generate and not options.get("csv_path") and not options.get("dry_run"):
            raise CommandError("--generate rejimində parollar bir daha görünməyəcək — --csv ilə fayla yazın.")

        audience = options.get("audience") or "students"
        role_names = ("teacher", "assistant") if audience == "teachers" else ("student", "lead_student")
        student_user_ids = (
            Membership.objects.filter(
                organization=organization,
                is_active=True,
                role__name__in=role_names,
            )
            .values_list("user_id", flat=True)
            .distinct()
        )
        # Qrup filtri — parol siyahısı praktikada QRUP-QRUP çap olunur (kurator
        # öz qrupuna paylayır), ona görə hədəf dəsti akademik qeyddən daraldılır.
        group_name = (options.get("group") or "").strip()
        if group_name:
            from apps.registrar.models import StudentAcademicRecord

            group_unit = (
                OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP)
                .filter(Q(name__iexact=group_name) | Q(code__iexact=group_name))
                .first()
            )
            if group_unit is None:
                raise CommandError(f"Qrup tapılmadı: {group_name!r}")
            in_group = StudentAcademicRecord.objects.filter(organization=organization, group=group_unit).values_list(
                "student_id", flat=True
            )
            student_user_ids = set(student_user_ids) & set(in_group)
        users = (
            User.objects.filter(id__in=list(student_user_ids), is_active=True)
            .filter(is_superuser=False, is_staff=False)
            .select_related("profile")
            .order_by("username")
        )
        wanted = [name.strip() for name in (options.get("usernames") or []) if name.strip()]
        if wanted:
            users = users.filter(username__in=wanted)
            missing = sorted(set(wanted) - set(users.values_list("username", flat=True)))
            if missing:
                raise CommandError(f"İstifadəçi tapılmadı / hədəf rolda deyil: {missing}")

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

        placement = _placement_index(organization, [u.pk for u in targets], audience)
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
                info = placement.get(user.pk, {})
                full_name = (f"{user.last_name} {user.first_name}").strip() or user.username
                rows.append(
                    (
                        info.get("faculty", ""),
                        info.get("unit", ""),
                        info.get("program", ""),
                        info.get("group", ""),
                        info.get("code", ""),
                        full_name,
                        user.username,
                        password,
                    )
                )
        rows.sort(key=lambda r: (r[0], r[1], r[3], r[5]))

        if options.get("csv_path"):
            with open(options["csv_path"], "w", newline="", encoding="utf-8") as fh:
                writer = safe_csv_writer(fh)
                writer.writerow(
                    ["fakulte", "kafedra", "proqram", "qrup", "telebe_kodu", "ad_soyad", "username", "ilkin_parol"]
                )
                writer.writerows(rows)
            self.stdout.write(f"CSV yazıldı: {options['csv_path']}")

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ {len(rows)} tələbəyə default parol verildi və ilk-giriş axınına salındı "
                f"({skipped_configured} artıq qurulmuş hesab ötürüldü). "
                "İlk girişdə: yeni email + OTP təsdiqi + yeni parol tələb olunacaq."
            )
        )


def _ancestor_names(unit):
    """OrgUnit → {unit_type: name} özü + valideynləri (ən çox 4 səviyyə)."""
    names = {}
    current = unit
    depth = 0
    while current is not None and depth < 5:
        names.setdefault(current.unit_type, current.name)
        current = current.parent
        depth += 1
    return names


def _placement_index(organization, user_ids, audience):
    """user_id → {faculty, unit(kafedra), program, group, code} — CSV paylama sütunları."""
    from apps.organizations.models import Membership
    from core.constants import OrgUnitType

    index = {}
    if audience == "teachers":
        memberships = Membership.objects.filter(
            organization=organization, user_id__in=user_ids, is_active=True
        ).select_related("scope_unit__parent__parent", "role")
        for membership in memberships:
            names = _ancestor_names(membership.scope_unit) if membership.scope_unit_id else {}
            entry = index.setdefault(membership.user_id, {})
            entry.setdefault("faculty", names.get(OrgUnitType.FACULTY, ""))
            entry.setdefault("unit", names.get(OrgUnitType.CHAIR, ""))
        return index

    from apps.accounts.models import UserProfile
    from apps.registrar.models import StudentAcademicRecord

    codes = dict(UserProfile.objects.filter(user_id__in=user_ids).values_list("user_id", "institutional_identifier"))
    records = (
        StudentAcademicRecord.objects.filter(organization=organization, student_id__in=user_ids)
        .select_related("program", "group__parent__parent__parent")
        .order_by("student_id", "-created_at")
    )
    for record in records:
        if record.student_id in index:
            continue  # ən son qeyd
        names = _ancestor_names(record.group) if record.group_id else {}
        index[record.student_id] = {
            "faculty": names.get(OrgUnitType.FACULTY, ""),
            "unit": names.get(OrgUnitType.CHAIR, ""),
            "program": getattr(record.program, "name", "") or "",
            "group": names.get(OrgUnitType.GROUP, ""),
            "code": codes.get(record.student_id) or "",
        }
    for user_id in user_ids:
        index.setdefault(user_id, {"code": codes.get(user_id) or ""})
    return index
