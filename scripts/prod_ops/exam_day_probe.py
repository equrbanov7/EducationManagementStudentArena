"""İmtahan günü hazırlığı üçün YALNIZ-OXU prod vəziyyət hesabatı.

`manage.py shell`-ə STDIN ilə ötürülür (runner-dən konteynerə) — belə olanda
kod konteyner image-inə deploy olunmuş olmalı DEYİL, ona görə deploy gözləmədən
işləyir:

    docker compose exec -T app python manage.py shell < scripts/prod_ops/exam_day_probe.py

Parametrlər mühit dəyişənləri ilə verilir (PROBE_ORG / PROBE_STUDENTS /
PROBE_GROUPS / PROBE_SUBJECTS — çoxdəyərlilər sətir-sətir).

Heç nə YAZMIR: məqsəd real imtahan məlumatını yazmazdan ƏVVƏL faktiki vəziyyəti
bilməkdir (səhv org/qrup seçimi real imtahanı poza bilər).
"""

import os

from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.exams.models import Exam, StudentGroup
from apps.organizations.models import Membership, Organization
from apps.registrar.models import Subject
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

User = get_user_model()


def _lines(name):
    return [ln.strip() for ln in (os.environ.get(name) or "").splitlines() if ln.strip()]


def out(text=""):
    print(text)


@rls_worker_atomic()
@bypass_rls()
def main():
    org_slug = (os.environ.get("PROBE_ORG") or "").strip()
    students = _lines("PROBE_STUDENTS")
    groups = _lines("PROBE_GROUPS")
    subjects = _lines("PROBE_SUBJECTS")

    out("=" * 70)
    out("TƏŞKİLATLAR")
    out("=" * 70)
    for org in Organization.objects.order_by("name"):
        mark = " ←" if org_slug and org.slug == org_slug else ""
        out(f"  {org.slug:44} {org.name} [{org.status}]{mark}")

    if not org_slug:
        out("\n(PROBE_ORG verilməyib — qalan yoxlamalar üçün yuxarıdan slug seçin.)")
        return

    organization = Organization.objects.filter(slug=org_slug).first()
    if organization is None:
        out(f"\n!! '{org_slug}' slug-lı təşkilat TAPILMADI — yuxarıdan seçin.")
        return

    out("\n" + "=" * 70)
    out(f"TƏLƏBƏLƏR — {organization.name}")
    out("=" * 70)
    for needle in students:
        parts = [p for p in needle.split() if p]
        query = Q()
        for part in parts:
            query |= Q(last_name__icontains=part) | Q(first_name__icontains=part) | Q(username__icontains=part)
        found = list(User.objects.filter(query).distinct()[:10]) if parts else []
        out(f"\n  axtarış: '{needle}' → {len(found)} nəticə")
        for user in found:
            membership = Membership.objects.filter(user=user, organization=organization).first()
            profile = getattr(user, "profile", None)
            out(
                f"    • {user.username:26} {user.get_full_name():34} "
                f"org_üzv={'bəli' if membership else 'XEYR'} "
                f"rol={getattr(membership.role, 'name', '—') if membership else '—'}"
            )
            if profile is not None:
                out(
                    f"      profil: rol={profile.role} qrup={profile.student_group_number or '—'} "
                    f"parol_dəyiş={profile.password_change_required} email_təsdiq={profile.email_verified}"
                )

    out("\n" + "=" * 70)
    out("QRUPLAR (exams.StudentGroup)")
    out("=" * 70)
    for needle in groups:
        found = StudentGroup.objects.filter(organization=organization, name__icontains=needle)
        out(f"\n  axtarış: '{needle}' → {found.count()} nəticə")
        for group in found:
            out(f"    • {group.name:18} müəllim={group.teacher.username:22} tələbə={group.students.count()}")

    out("\n" + "=" * 70)
    out("FƏNLƏR (registrar.Subject)")
    out("=" * 70)
    for needle in subjects:
        found = Subject.objects.filter(organization=organization, name__icontains=needle)
        out(f"\n  axtarış: '{needle}' → {found.count()} nəticə")
        for subject in found:
            out(f"    • {subject.code:14} {subject.name} aktiv={subject.is_active}")

    out("\n" + "=" * 70)
    out("MÜƏLLİM/ADMIN ROLLU İSTİFADƏÇİLƏR (qrup sahibi + imtahan müəllifi üçün)")
    out("=" * 70)
    for membership in Membership.objects.filter(
        organization=organization, is_active=True, role__name__in=("teacher", "org_admin", "org_owner")
    ).select_related("user", "role")[:15]:
        out(f"    • {membership.user.username:26} {membership.user.get_full_name():32} rol={membership.role.name}")

    out("\n" + "=" * 70)
    out("SON İMTAHANLAR (nümunə parametrlər üçün)")
    out("=" * 70)
    for exam in Exam.objects.filter(organization=organization).order_by("-id")[:8]:
        out(
            f"    • #{exam.pk} {exam.title[:42]:44} tip={exam.exam_type}/{exam.exam_type_extended or '—'} "
            f"müddət={exam.total_duration_minutes}dəq sual={exam.random_question_count}"
        )


main()
