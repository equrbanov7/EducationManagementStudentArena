"""İmtahan günü — DƏRİN yalnız-oxu hesabat (2-ci mərhələ).

Birinci probe göstərdi ki, tələbələr/qrup/fənn yoxdur. Yazmazdan ƏVVƏL qalan
naməlumları bağlayır:

  * mövcud imtahanların sual mənbəyi (imtahan daxili sual, yoxsa sual bankı) —
    yeni imtahan yaratmaq, yoxsa mövcudu işlətmək qərarını bu həll edir;
  * e-poçt konvensiyası (yeni hesablar üçün);
  * org-dakı rol obyektləri (Membership yaratmaq üçün lazımdır);
  * imtahan müəllifi/təyinat nümunəsi.

Heç nə yazmır.
"""

import os

from django.contrib.auth import get_user_model

from apps.exams.models import Exam
from apps.organizations.models import Organization, Role
from apps.registrar.models import Subject
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

User = get_user_model()


def out(text=""):
    print(text)


@rls_worker_atomic()
@bypass_rls()
def main():
    org_slug = (os.environ.get("PROBE_ORG") or "qerbi-kaspi-universiteti").strip()
    organization = Organization.objects.filter(slug=org_slug).first()
    if organization is None:
        out(f"!! '{org_slug}' tapılmadı")
        return

    out("=" * 74)
    out("MÖVCUD İMTAHANLAR — sual mənbəyi və təyinat")
    out("=" * 74)
    for exam in Exam.objects.filter(organization=organization).order_by("-id")[:10]:
        own = exam.questions.count()
        allowed_u = exam.allowed_users.count()
        allowed_g = exam.allowed_groups.count()
        out(f"\n  #{exam.pk} {exam.title[:56]}")
        out(
            f"     tip={exam.exam_type}/{exam.exam_type_extended or '—'} aktiv={exam.is_active} "
            f"müddət={exam.total_duration_minutes}dəq random_sual={exam.random_question_count}"
        )
        out(f"     ÖZ SUALI={own}  təyin_tələbə={allowed_u}  təyin_qrup={allowed_g}")
        out(f"     müəllif={exam.author.username if exam.author_id else '—'}")
        out(f"     fənn={exam.subject.code if exam.subject_id else '—'}")
        out(f"     pəncərə={exam.start_datetime} → {exam.end_datetime}")

    out("\n" + "=" * 74)
    out("SUAL BANKI (fənn üzrə)")
    out("=" * 74)
    try:
        from apps.exams.models import BankQuestion, QuestionBank

        for bank in QuestionBank.objects.filter(organization=organization).order_by("name"):
            count = BankQuestion.objects.filter(bank=bank, is_active=True).count()
            out(f"  bank='{bank.name[:38]}' fənn='{bank.subject}' aktiv_sual={count}")
        out(
            f"\n  org üzrə ümumi aktiv bank sualı: {BankQuestion.objects.filter(bank__organization=organization, is_active=True).count()}"
        )
    except Exception as exc:  # noqa: BLE001
        out(f"  (bank oxunmadı: {exc})")

    out("\n" + "=" * 74)
    out("E-POÇT KONVENSİYASI (wcu_ hesabları)")
    out("=" * 74)
    for user in User.objects.filter(username__startswith="wcu_").order_by("username")[:8]:
        out(f"  {user.username:26} {user.email}")

    out("\n" + "=" * 74)
    out("ORG ROLLARI (Membership üçün)")
    out("=" * 74)
    for role in Role.objects.filter(organization=organization).order_by("-level"):
        out(f"  {role.name:18} lvl={role.level:<4} aktiv={role.is_active}")

    out("\n" + "=" * 74)
    out("FƏNLƏR (tam siyahı)")
    out("=" * 74)
    for subject in Subject.objects.filter(organization=organization).order_by("code"):
        out(f"  {subject.code:14} {subject.name}")


main()
