"""
seed_stress_test — Yük/stress testi üçün izolyasiya olunmuş universitet mühiti.

Bir universitet təşkilatı + fakültə/kafedra (OrgUnit) + owner + müəllim + N qrup
+ M tələbə yaradır. BÜTÜN test istifadəçiləri:
  * eyni parolla girir (--password),
  * OTP/ilk-giriş axınından KEÇMİR (email_verified=True,
    password_change_required=False) → kabinetə bir addımda daxil olur.

Real məlumatlara toxunmur — hər şey ayrıca "stress" təşkilatındadır və
username prefiksi ilə (default: ``stress_``) asanlıqla təmizlənir.

İdempotentdir (təkrar işlətmək təhlükəsizdir). Sıfırlamaq üçün ``--purge``.

Nümunələr:
    python manage.py seed_stress_test --students 50 --groups 5 --password 'StressTest2026!'
    python manage.py seed_stress_test --purge
"""

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.exams.models import StudentGroup
from apps.organizations.default_roles import get_default_roles_for_org_type
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType
from core.management.command_safety import ProductionCommandSafetyMixin
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic
from core.roles import ProfileRole

User = get_user_model()


class Command(ProductionCommandSafetyMixin, BaseCommand):
    safety_command_name = "seed_stress_test"
    help = "Seed an isolated university + groups + students for load/stress testing (shared password, no OTP)."

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=50, help="Neçə tələbə (default 50).")
        parser.add_argument("--groups", type=int, default=5, help="Neçə qrup (default 5).")
        parser.add_argument("--password", default="StressTest2026!", help="Bütün test userləri üçün ORTAQ parol.")
        parser.add_argument("--org-slug", default="stress-test-university")
        parser.add_argument("--org-name", default="Stress Test University")
        parser.add_argument("--prefix", default="stress", help="Username/email prefiksi (təmizləmə üçün).")
        parser.add_argument("--purge", action="store_true", help="Əvvəl seed olunmuş stress datanı sil və çıx.")

    # ── helpers ──────────────────────────────────────────────────────────────
    def _ensure_user(self, username, email, password):
        user, _ = User.objects.get_or_create(username=username, defaults={"email": email})
        user.email = email
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.set_password(password)
        user.save()
        return user

    def _ensure_profile(self, user, organization, role, *, group_number=None):
        """Profili OTP-siz birbaşa-giriş üçün konfiqurasiya edir."""
        UserProfile = django_apps.get_model("accounts", "UserProfile")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.organization = organization
        profile.organization_type = OrganizationType.UNIVERSITY
        profile.student_university_name = organization.name
        profile.role = role
        profile.email_verified = True  # → ilk-giriş/OTP axını YOX
        profile.password_change_required = False  # → parol dəyişmə məcburiyyəti YOX
        fields = [
            "organization",
            "organization_type",
            "student_university_name",
            "role",
            "email_verified",
            "password_change_required",
            "updated_at",
        ]
        if group_number is not None and hasattr(profile, "student_group_number"):
            profile.student_group_number = group_number
            fields.append("student_group_number")
        profile.save(update_fields=fields)
        return profile

    def _ensure_membership(self, user, organization, role, assigned_by, *, is_primary=False):
        if role is None:
            return None
        membership, _ = Membership.objects.get_or_create(
            user=user,
            organization=organization,
            defaults={"role": role, "is_primary": is_primary, "is_active": True, "assigned_by": assigned_by},
        )
        changed = []
        if membership.role_id != role.id:
            membership.role = role
            changed.append("role")
        if not membership.is_active:
            membership.is_active = True
            changed.append("is_active")
        if is_primary and not membership.is_primary:
            membership.is_primary = True
            changed.append("is_primary")
        if changed:
            membership.save(update_fields=changed + ["updated_at"])
        return membership

    def _ensure_roles(self, organization):
        roles = {}
        for tmpl in get_default_roles_for_org_type(OrganizationType.UNIVERSITY):
            role, _ = Role.objects.update_or_create(
                organization=organization,
                name=tmpl["name"],
                defaults={
                    "display_name": tmpl["display_name"],
                    "description": tmpl.get("description", ""),
                    "level": tmpl["level"],
                    "scope_type": tmpl["scope_type"],
                    "permissions": tmpl["permissions"],
                    "is_system": True,
                    "is_active": True,
                },
            )
            roles[role.name] = role
        return roles

    def _ensure_unit(self, organization, slug, *, unit_type, name, code, parent, head):
        unit, _ = OrgUnit.objects.update_or_create(
            organization=organization,
            slug=slug,
            defaults={
                "parent": parent,
                "unit_type": unit_type,
                "name": name,
                "code": code,
                "head": head,
                "is_active": True,
            },
        )
        return unit

    def _purge(self, prefix, org_slug):
        removed = User.objects.filter(username__startswith=f"{prefix}_").count()
        User.objects.filter(username__startswith=f"{prefix}_").delete()
        org = Organization.objects.filter(slug=org_slug).first()
        if org is not None:
            org.delete()  # cascades roles / units / groups / memberships
        self.stdout.write(self.style.SUCCESS(f"Purged {removed} '{prefix}_*' user(s) and org '{org_slug}'."))

    # ── main ─────────────────────────────────────────────────────────────────
    @transaction.atomic
    @rls_worker_atomic()
    @bypass_rls()
    def handle(self, *args, **options):
        prefix = options["prefix"]
        org_slug = options["org_slug"]

        if options["purge"]:
            self._purge(prefix, org_slug)
            return

        n_students = max(1, options["students"])
        n_groups = max(1, options["groups"])
        password = options["password"]
        domain = f"{prefix}.emsarena.local"

        # 1) Owner (Organization.owner FK-ni ödəyir) + teacher (imtahanları qurur/başladır).
        owner = self._ensure_user(f"{prefix}_owner", f"{prefix}_owner@{domain}", password)
        teacher = self._ensure_user(f"{prefix}_teacher", f"{prefix}_teacher@{domain}", password)

        # 2) Təşkilat.
        organization, _ = Organization.objects.update_or_create(
            slug=org_slug,
            defaults={
                "name": options["org_name"],
                "org_type": OrganizationType.UNIVERSITY,
                "owner": owner,
                "description": "Isolated environment for load/stress testing (seed_stress_test).",
                "country": "Azerbaijan",
                "organization_identifier": "STRESS-UNI",
                "email": f"{prefix}@{domain}",
                "is_active": True,
                "status": "active",
            },
        )

        roles = self._ensure_roles(organization)
        owner_role = roles.get("rector") or max(roles.values(), key=lambda r: r.level)
        teacher_role = roles.get("teacher") or roles.get("instructor")
        student_role = roles.get("student") or min(roles.values(), key=lambda r: r.level)

        self._ensure_profile(owner, organization, ProfileRole.ORG_OWNER)
        self._ensure_membership(owner, organization, owner_role, owner, is_primary=True)
        self._ensure_profile(teacher, organization, ProfileRole.TEACHER)
        self._ensure_membership(teacher, organization, teacher_role, owner, is_primary=True)

        # 3) Fakültə → Kafedra (kafedranın parent-i fakültədir).
        faculty = self._ensure_unit(
            organization,
            f"{prefix}-faculty",
            unit_type="faculty",
            name="Stress Test Fakültəsi",
            code="STF",
            parent=None,
            head=owner,
        )
        department = self._ensure_unit(
            organization,
            f"{prefix}-department",
            unit_type="department",
            name="Stress Test Kafedrası",
            code="STK",
            parent=faculty,
            head=teacher,
        )

        # 4) Qruplar (hər biri müəllimə və kafedraya bağlı).
        groups = []
        for i in range(1, n_groups + 1):
            group, _ = StudentGroup.objects.get_or_create(
                organization=organization,
                teacher=teacher,
                name=f"{prefix.upper()}-QRUP-{i}",
            )
            if group.org_unit_id != department.id:
                group.org_unit = department
                group.save(update_fields=["org_unit"])
            group.teachers.set([teacher])
            groups.append(group)

        # 5) Tələbələr — qruplara növbə ilə paylanır; eyni parol, OTP yox.
        buckets = {g.id: [] for g in groups}
        for idx in range(1, n_students + 1):
            username = f"{prefix}_student_{idx:03d}"
            student = self._ensure_user(username, f"{username}@{domain}", password)
            group = groups[(idx - 1) % n_groups]
            self._ensure_profile(student, organization, ProfileRole.STUDENT, group_number=group.name)
            self._ensure_membership(student, organization, student_role, owner)
            buckets[group.id].append(student)

        for group in groups:
            group.students.set(buckets[group.id])

        # ── xülasə ─────────────────────────────────────────────────────────────
        line = "─" * 64
        self.stdout.write(self.style.SUCCESS(line))
        self.stdout.write(self.style.SUCCESS("STRESS TEST MÜHİTİ HAZIRDIR"))
        self.stdout.write(f"  Təşkilat  : {organization.name}  ({organization.slug})")
        self.stdout.write(f"  Fakültə   : {faculty.name}")
        self.stdout.write(f"  └ Kafedra : {department.name}  (parent = {faculty.name})")
        self.stdout.write(f"  Qruplar   : {n_groups} → {', '.join(g.name for g in groups)}")
        self.stdout.write(f"  Tələbələr : {n_students}  (~{n_students // n_groups}/qrup)")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("  GİRİŞ (hamısı EYNİ parol, OTP YOX, birbaşa kabinet):"))
        self.stdout.write(f"    Müəllim (imtahan qurur/başladır) : {teacher.username}")
        self.stdout.write(f"    Owner   (təşkilat idarəçisi)      : {owner.username}")
        self.stdout.write(
            f"    Tələbələr                         : {prefix}_student_001 … {prefix}_student_{n_students:03d}"
        )
        self.stdout.write("    Ortaq parol command inputundan götürülüb; dəyəri loglanmır.")
        self.stdout.write("")
        self.stdout.write(
            f"  Təmizləmək: python manage.py seed_stress_test --purge --prefix {prefix} --org-slug {org_slug}"
        )
        self.stdout.write(self.style.SUCCESS(line))
