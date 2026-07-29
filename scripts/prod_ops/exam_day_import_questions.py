"""Mülki müdafiə imtahanına sualların idxalı + fənn müəlliminin yaradılması.

Bu skript `data/mm_questions.py` ilə BİRLİKDƏ stdin-ə verilir (workflow onları
birləşdirir), ona görə `QUESTIONS` adı artıq mövcud olur:

    cat data/mm_questions.py exam_day_import_questions.py | manage.py shell

Doğru cavab hər sualda A-dır (mənbə sənədin alt qeydi).

DEFAULT DRY-RUN — `SEED_APPLY=yes` olmadan heç nə yazılmır.
İDEMPOTENT: imtahanda artıq sual varsa, əvvəlcə TƏMİZLƏNİR, sonra yenidən
yazılır (suallar dəyişəndə təkrar işə salmaq təhlükəsizdir).

Mühit dəyişənləri:
    SEED_ORG              təşkilat slug
    SEED_APPLY            "yes" → yazır
    MM_EXAM_TITLE         hədəf imtahanın adı (default "Mülki müdafiə")
    MM_TEACHER_USERNAME   fənn müəllimi username (default wcu_elshen_emrahov)
    MM_TEACHER_FIRST/LAST müəllimin adı/soyadı
    EXAM_TEMP_PASSWORD    müəllim hesabı yaradılırsa parolu
"""

import os

from django.contrib.auth import get_user_model

from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption, StudentGroup
from apps.organizations.models import Membership, Organization, Role
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

User = get_user_model()

APPLY = (os.environ.get("SEED_APPLY") or "").strip().lower() == "yes"
ORG_SLUG = (os.environ.get("SEED_ORG") or "qerbi-kaspi-universiteti").strip()
EXAM_TITLE = (os.environ.get("MM_EXAM_TITLE") or "Mülki müdafiə").strip()
TEACHER_USERNAME = (os.environ.get("MM_TEACHER_USERNAME") or "wcu_elshen_emrahov").strip()
TEACHER_FIRST = (os.environ.get("MM_TEACHER_FIRST") or "Elşən").strip()
TEACHER_LAST = (os.environ.get("MM_TEACHER_LAST") or "Əmrahov").strip()
PASSWORD = os.environ.get("EXAM_TEMP_PASSWORD") or ""
GROUP_NAME = "532 Bİ"


def out(text=""):
    print(text)


def act(description):
    out(f"    {'→ YAZILIR ' if APPLY else '→ [dry-run] '}{description}")
    return APPLY


@rls_worker_atomic()
@bypass_rls()
def main():
    out("=" * 74)
    out(f"REJİM: {'FAKTİKİ YAZMA' if APPLY else 'DRY-RUN — heç nə yazılmır'}")
    out(f"Sual mənbəyi: {len(QUESTIONS)} sual")  # noqa: F821 — data faylından gəlir
    out("=" * 74)

    organization = Organization.objects.filter(slug=ORG_SLUG).first()
    if organization is None:
        out(f"!! '{ORG_SLUG}' tapılmadı")
        return

    # ── 1. Fənn müəllimi ───────────────────────────────────────────────────
    out(f"\n1) FƏNN MÜƏLLİMİ — {TEACHER_LAST} {TEACHER_FIRST}")
    teacher = User.objects.filter(username=TEACHER_USERNAME).first()
    if teacher is None:
        if act(f"User yaradılır: {TEACHER_USERNAME} — {TEACHER_USERNAME}@qku.edu.az"):
            if not PASSWORD:
                out("    !! EXAM_TEMP_PASSWORD boşdur — müəllim yaradıla bilmir")
                return
            teacher = User.objects.create_user(
                username=TEACHER_USERNAME,
                email=f"{TEACHER_USERNAME}@qku.edu.az",
                password=PASSWORD,
                first_name=TEACHER_FIRST,
                last_name=TEACHER_LAST,
            )
    else:
        out(f"    mövcuddur: {TEACHER_USERNAME}")

    teacher_role = Role.objects.filter(organization=organization, name="teacher").first()
    if teacher is not None and teacher_role is not None:
        profile = getattr(teacher, "profile", None)
        if profile is not None and act(f"{TEACHER_USERNAME}: profil (rol=teacher, OTP söndürülür)"):
            profile.role = "teacher"
            profile.organization = organization
            profile.organization_type = organization.org_type
            profile.password_change_required = False
            profile.email_verified = True
            profile.save()
        membership = Membership.objects.filter(user=teacher, organization=organization).first()
        if membership is None:
            if act(f"{TEACHER_USERNAME}: Membership (teacher, aktiv)"):
                Membership.objects.create(
                    user=teacher, organization=organization, role=teacher_role, is_primary=True, is_active=True
                )
        elif act(f"{TEACHER_USERNAME}: Membership teacher roluna yenilənir"):
            membership.role = teacher_role
            membership.is_active = True
            membership.save()

    # ── 2. Qrup sahibini müəllimə keçir ────────────────────────────────────
    out(f"\n2) QRUP SAHİBİ — {GROUP_NAME}")
    group = StudentGroup.objects.filter(organization=organization, name=GROUP_NAME).first()
    if group is None:
        out("    qrup tapılmadı — buraxılır")
    elif teacher is None:
        out("    müəllim yoxdur — buraxılır")
    else:
        out(f"    hazırkı sahib: {group.teacher.username}")
        if act(f"sahib dəyişdirilir → {TEACHER_USERNAME}"):
            group.teacher = teacher
            group.save()

    # ── 3. İmtahan + suallar ───────────────────────────────────────────────
    out(f"\n3) İMTAHAN — '{EXAM_TITLE}'")
    exam = Exam.objects.filter(organization=organization, title=EXAM_TITLE).first()
    if exam is None:
        out(f"    !! '{EXAM_TITLE}' adlı imtahan tapılmadı — dayandırıldı")
        return
    existing = exam.questions.count()
    out(f"    #{exam.pk} — hazırkı sual sayı: {existing}")

    if teacher is not None and act(f"imtahan müəllifi → {TEACHER_USERNAME}"):
        exam.author = teacher
        exam.save(update_fields=["author"])

    if existing and act(f"köhnə {existing} sual silinir (təkrar idxal)"):
        exam.questions.all().delete()

    if act(f"{len(QUESTIONS)} sual yazılır (doğru cavab = A)"):  # noqa: F821
        created = 0
        for index, item in enumerate(QUESTIONS, start=1):  # noqa: F821
            question = ExamQuestion.objects.create(
                exam=exam,
                text=item["text"],
                order=index,
                points=1,
                difficulty=item["difficulty"],
                answer_mode="single",
                is_active=True,
            )
            ExamQuestionOption.objects.bulk_create(
                [
                    ExamQuestionOption(
                        question=question,
                        label=label,
                        text=text,
                        is_correct=(label == "A"),
                    )
                    for label, text in item["options"]
                ]
            )
            created += 1
        out(f"    yazıldı: {created} sual, {created * 5} variant")
        exam.refresh_from_db()
        out(f"    yoxlama — imtahanda indi {exam.questions.count()} sual var")

    out("\n" + "=" * 74)
    out("TAMAMLANDI." if APPLY else "DRY-RUN bitdi — heç nə yazılmadı.")
    out("=" * 74)


main()
