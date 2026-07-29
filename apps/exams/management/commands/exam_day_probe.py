"""İmtahan günü hazırlığı üçün YALNIZ-OXU vəziyyət hesabatı.

Serverə birbaşa çıxış olmayanda (prod LAN-dadır) self-hosted runner üzərindən
işlədilir: "bu tələbələr / qruplar / fənlər sistemdə varmı?" sualına cavab verir.
Heç nə YAZMIR — məqsəd yazı əməliyyatından ƏVVƏL faktiki vəziyyəti bilməkdir,
çünki səhv org/qrup seçimi real imtahanı poza bilər.

Nümunə:
    python manage.py exam_day_probe \
        --org qerbi-kaspi \
        --student "Süleymanlı Toğrul" --student "Hüseynov Turay" \
        --group "532 Bİ" \
        --subject "Mülki müdafiə" --subject "Azərbaycan dilində işgüzar"
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.exams.models import Exam, StudentGroup
from apps.organizations.models import Membership, Organization
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

User = get_user_model()


class Command(BaseCommand):
    help = "İmtahan günü üçün prod vəziyyətini oxuyur (yazmır)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="", help="Təşkilat slug-ı (boşdursa hamısı sadalanır).")
        parser.add_argument("--student", action="append", default=[], help="Tələbə adı (təkrarlana bilər).")
        parser.add_argument("--group", action="append", default=[], help="Qrup adı (təkrarlana bilər).")
        parser.add_argument("--subject", action="append", default=[], help="Fənn adı (təkrarlana bilər).")

    @rls_worker_atomic()
    @bypass_rls()
    def handle(self, *args, **options):
        org_slug = (options["org"] or "").strip()

        self.stdout.write("=" * 70)
        self.stdout.write("TƏŞKİLATLAR")
        self.stdout.write("=" * 70)
        for org in Organization.objects.order_by("name"):
            mark = " ←" if org_slug and org.slug == org_slug else ""
            self.stdout.write(f"  {org.slug:42} {org.name} [{org.status}]{mark}")

        organization = None
        if org_slug:
            organization = Organization.objects.filter(slug=org_slug).first()
            if organization is None:
                self.stdout.write(self.style.ERROR(f"\n'{org_slug}' slug-lı təşkilat TAPILMADI — yuxarıdan seçin."))
                return

        if organization is None:
            self.stdout.write("\n(--org verilməyib; qalan yoxlamalar üçün slug seçin.)")
            return

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(f"TƏLƏBƏLƏR — {organization.name}")
        self.stdout.write("=" * 70)
        for needle in options["student"]:
            parts = [p for p in needle.split() if p]
            query = Q()
            for part in parts:
                query |= Q(last_name__icontains=part) | Q(first_name__icontains=part) | Q(username__icontains=part)
            found = User.objects.filter(query).distinct()[:10] if parts else User.objects.none()
            self.stdout.write(f"\n  axtarış: '{needle}' → {found.count()} nəticə")
            for user in found:
                membership = Membership.objects.filter(user=user, organization=organization).first()
                profile = getattr(user, "profile", None)
                self.stdout.write(
                    f"    • {user.username:24} {user.get_full_name():32} "
                    f"org_üzv={'bəli' if membership else 'XEYR'} "
                    f"rol={getattr(membership.role, 'name', '—') if membership else '—'} "
                    f"aktiv={getattr(membership, 'is_active', '—')}"
                )
                if profile is not None:
                    self.stdout.write(
                        f"      profil: rol={profile.role} qrup={profile.student_group_number or '—'} "
                        f"parol_dəyiş={profile.password_change_required} email_təsdiq={profile.email_verified}"
                    )

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("QRUPLAR (exams.StudentGroup)")
        self.stdout.write("=" * 70)
        for needle in options["group"]:
            found = StudentGroup.objects.filter(organization=organization, name__icontains=needle.strip())
            self.stdout.write(f"\n  axtarış: '{needle}' → {found.count()} nəticə")
            for group in found:
                self.stdout.write(
                    f"    • {group.name:16} müəllim={group.teacher.username:20} tələbə={group.students.count()}"
                )

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("FƏNLƏR (registrar.Subject)")
        self.stdout.write("=" * 70)
        from apps.registrar.models import Subject

        for needle in options["subject"]:
            found = Subject.objects.filter(organization=organization, name__icontains=needle.strip())
            self.stdout.write(f"\n  axtarış: '{needle}' → {found.count()} nəticə")
            for subject in found:
                self.stdout.write(f"    • {subject.code:12} {subject.name} aktiv={subject.is_active}")

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("MÜƏLLİM ROLLU İSTİFADƏÇİLƏR (qrup sahibi üçün lazımdır)")
        self.stdout.write("=" * 70)
        teachers = Membership.objects.filter(
            organization=organization, is_active=True, role__name__in=("teacher", "org_admin", "org_owner")
        ).select_related("user", "role")[:15]
        for membership in teachers:
            self.stdout.write(
                f"    • {membership.user.username:24} {membership.user.get_full_name():30} rol={membership.role.name}"
            )

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("SON YARADILAN İMTAHANLAR (nümunə parametrlər üçün)")
        self.stdout.write("=" * 70)
        for exam in Exam.objects.filter(organization=organization).order_by("-id")[:8]:
            self.stdout.write(
                f"    • #{exam.pk} {exam.title[:44]:46} tip={exam.exam_type}/{exam.exam_type_extended or '—'} "
                f"müddət={exam.total_duration_minutes}dəq sual={exam.random_question_count}"
            )
