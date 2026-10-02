"""Tələbə statusu + parol aktivləşdirmə statistikası — YALNIZ OXUMA, yalnız aqreqat saylar (2026-10-02).

Sahib: «aktiv oxuyan tələbələri və məzunları ayırmaq — hamını aktiv göstərməsin» və «parolunu bərpa etmiş
tələbələrin sayı». Bu probe dizayndan ƏVVƏL real paylanmanı göstərir (ad/e-poçt çap olunmur).
"""

from collections import Counter
from datetime import timedelta

from django.apps import apps
from django.db.models import Count
from django.utils import timezone

from core.rls import bypass_rls

User = apps.get_model("auth", "User")
UserProfile = apps.get_model("accounts", "UserProfile")
Membership = apps.get_model("organizations", "Membership")
SAR = apps.get_model("registrar", "StudentAcademicRecord")
EmailOTP = apps.get_model("accounts", "EmailOTP")
AuditLog = apps.get_model("audit", "AuditLog")

STUDENTISH = ("student", "lead_student", "alumni")

with bypass_rls():
    now = timezone.now()
    print(f"server_time_utc: {now:%Y-%m-%d %H:%M}")

    print("\n== Üzvlük rolu × profil access_state (tələbə tipli rollar)")
    rows = (
        Membership.objects.filter(role__name__in=STUDENTISH, is_active=True)
        .values("role__name", "user__profile__access_state")
        .annotate(n=Count("user", distinct=True))
        .order_by("role__name", "user__profile__access_state")
    )
    for row in rows:
        print(f"  role={row['role__name']:<13} access={row['user__profile__access_state']:<9} {row['n']}")

    print("\n== StudentAcademicRecord: status × access_state")
    for row in (
        SAR.objects.values("status", "student__profile__access_state")
        .annotate(n=Count("id"))
        .order_by("status", "student__profile__access_state")
    ):
        print(f"  status={row['status']:<15} access={row['student__profile__access_state']:<9} {row['n']}")

    print("\n== Qəbul ili × access_state (SAR)")
    years = (
        SAR.objects.values("admission_year", "student__profile__access_state")
        .annotate(n=Count("id"))
        .order_by("admission_year")
    )
    table = {}
    for row in years:
        table.setdefault(row["admission_year"], Counter())[row["student__profile__access_state"]] += row["n"]
    for year in sorted(table):
        print(f"  {year}: " + ", ".join(f"{k}={v}" for k, v in sorted(table[year].items())))

    print("\n== Proqram səviyyəsi × ECTS (SAR)")
    for row in (
        SAR.objects.values("program__degree_level", "program__ects_total")
        .annotate(n=Count("id"))
        .order_by("program__degree_level", "program__ects_total")
    ):
        print(f"  level={row['program__degree_level']:<10} ects={row['program__ects_total']} {row['n']}")

    print("\n== Aktiv girişli, amma oxu müddəti bitmiş görünən SAR (qəbul ili + ECTS/60 il ≤ cari tədris ili)")
    academic_year_start = now.year if now.month >= 9 else now.year - 1
    candidates = Counter()
    for row in SAR.objects.filter(status="enrolled", student__profile__access_state="active").values(
        "admission_year", "program__ects_total", "program__degree_level"
    ):
        years_needed = max(1, round((row["program__ects_total"] or 240) / 60))
        if row["admission_year"] and row["admission_year"] + years_needed <= academic_year_start:
            candidates[(row["program__degree_level"], row["admission_year"], years_needed)] += 1
    for (level, year, dur), n in sorted(candidates.items()):
        print(f"  level={level} qəbul={year} müddət={dur}il → {n}")
    print(f"  cəmi: {sum(candidates.values())} (cari tədris ili başlanğıcı {academic_year_start})")

    print("\n== Parol / hesab aktivləşdirmə (tələbə rolu, aktiv giriş)")
    students = User.objects.filter(
        memberships__role__name__in=("student", "lead_student"),
        memberships__is_active=True,
        profile__access_state="active",
    ).distinct()
    total = students.count()
    print(f"  aktiv tələbə hesabı: {total}")
    print(
        f"  ilkin parolla (hələ öz parolunu qurmayıb): {students.filter(profile__password_change_required=True).count()}"
    )
    print(f"  e-poçtu təsdiqli: {students.filter(profile__email_verified=True).count()}")
    print(f"  heç girməyib (last_login boş): {students.filter(last_login__isnull=True).count()}")
    print(f"  son 7 gündə girib: {students.filter(last_login__gte=now - timedelta(days=7)).count()}")
    print(
        "  aktivləşdirib (öz parolu + təsdiqli e-poçt): "
        f"{students.filter(profile__password_change_required=False, profile__email_verified=True).count()}"
    )
    admin_resets = AuditLog.objects.filter(changes__operation="admin_password_reset")
    print(
        f"  admin parol sıfırlaması (audit sətri): {admin_resets.count()}, fərqli hədəf: "
        f"{admin_resets.values('resource_id').distinct().count()}"
    )
    used = EmailOTP.objects.filter(purpose="password_reset", is_used=True)
    print(
        f"  OTP ilə parol bərpası/ilk giriş (istifadə olunmuş kod): {used.count()}, fərqli istifadəçi: "
        f"{used.values('user').distinct().count()}"
    )
    print(f"  grades_notice_pending: {students.filter(profile__grades_notice_pending=True).count()}")
