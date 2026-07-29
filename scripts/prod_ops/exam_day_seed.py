"""İmtahan günü hazırlığı — fənn / qrup / tələbə / imtahan təyinatı.

DEFAULT DRY-RUN: `SEED_APPLY=yes` verilməyibsə HEÇ NƏ YAZILMIR, yalnız plan
çap olunur. Prod-da real tələbələrə toxunduğu üçün əvvəl plan baxılır.

Bütün addımlar İDEMPOTENTDİR (get_or_create / update) — təkrar işə salmaq
təhlükəsizdir.

Mühit dəyişənləri:
    SEED_ORG              təşkilat slug (default: qerbi-kaspi-universiteti)
    SEED_APPLY            "yes" → faktiki yazır
    EXAM_TEMP_PASSWORD    yeni tələbə hesablarının parolu (repo secret-dən)
    SEED_GROUP_TEACHER    StudentGroup sahibi olacaq müəllim username-i
    SEED_AZ_EXAM_ID       Az dili imtahanının id-si (default 8)
    SEED_WINDOW_DAYS      imtahan pəncərəsinin uzunluğu, gün (default 7)

Qərarlar (istifadəçi ilə razılaşdırılıb 2026-07-30):
  * Az dili: mövcud #8 imtahanı işlədilir — 200 sualı hazırdır. Ona təyin
    olunmuş 5 QRUP SİLİNİR ki, köhnə tələbələr yenidən çıxış almasın; yerinə
    yalnız Toğrul allowed_users kimi qoyulur.
  * Mülki müdafiə: fənn + BOŞ imtahan yaradılır; 299 sual UI-dan idxal olunacaq.
  * OTP söndürülür: password_change_required=False + email_verified=True.
"""

import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.exams.models import Exam, StudentGroup
from apps.organizations.models import Membership, Organization, Role
from apps.registrar.models import Subject
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

User = get_user_model()

APPLY = (os.environ.get("SEED_APPLY") or "").strip().lower() == "yes"
ORG_SLUG = (os.environ.get("SEED_ORG") or "qerbi-kaspi-universiteti").strip()
PASSWORD = os.environ.get("EXAM_TEMP_PASSWORD") or ""
GROUP_TEACHER = (os.environ.get("SEED_GROUP_TEACHER") or "").strip()
AZ_EXAM_ID = int((os.environ.get("SEED_AZ_EXAM_ID") or "8").strip())
WINDOW_DAYS = int((os.environ.get("SEED_WINDOW_DAYS") or "7").strip())

GROUP_NAME = "532 Bİ"
STUDENTS = [
    {
        "username": "wcu_togrul_suleymanli",
        "first_name": "Toğrul",
        "last_name": "Süleymanlı",
        "patronymic": "Nazim",
        "exam": "az",
    },
    {
        "username": "wcu_turay_huseynov",
        "first_name": "Turay",
        "last_name": "Hüseynov",
        "patronymic": "Zaur",
        "exam": "mm",
    },
]
MM_SUBJECT_CODE = "MM101"
MM_SUBJECT_NAME = "Mülki müdafiə"
MM_EXAM_TITLE = "Mülki müdafiə"


def out(text=""):
    print(text)


def act(description):
    """Planı çap et; APPLY deyilsə False qaytar (yazma addımı buraxılır)."""
    out(f"    {'→ YAZILIR ' if APPLY else '→ [dry-run] '}{description}")
    return APPLY


@rls_worker_atomic()
@bypass_rls()
def main():
    out("=" * 74)
    out(f"REJİM: {'FAKTİKİ YAZMA (SEED_APPLY=yes)' if APPLY else 'DRY-RUN — heç nə yazılmır'}")
    out("=" * 74)

    organization = Organization.objects.filter(slug=ORG_SLUG).first()
    if organization is None:
        out(f"!! '{ORG_SLUG}' tapılmadı — dayandırıldı.")
        return
    out(f"Təşkilat: {organization.name}")

    if APPLY and not PASSWORD:
        out("!! EXAM_TEMP_PASSWORD boşdur — hesab yaratmaq mümkün deyil. Dayandırıldı.")
        return

    student_role = Role.objects.filter(organization=organization, name="student").first()
    if student_role is None:
        out("!! 'student' rolu tapılmadı — dayandırıldı.")
        return

    # ── 1. Fənn: Mülki müdafiə ─────────────────────────────────────────────
    out("\n1) FƏNN — Mülki müdafiə")
    subject = Subject.objects.filter(organization=organization, code=MM_SUBJECT_CODE).first()
    if subject:
        out(f"    mövcuddur: {subject.code} — {subject.name}")
    elif act(f"Subject yaradılır: {MM_SUBJECT_CODE} — {MM_SUBJECT_NAME}"):
        subject = Subject.objects.create(
            organization=organization, code=MM_SUBJECT_CODE, name=MM_SUBJECT_NAME, ects=2, is_active=True
        )
        out(f"    yaradıldı: {subject.code}")

    # ── 2. Tələbələr ───────────────────────────────────────────────────────
    out("\n2) TƏLƏBƏLƏR")
    created_users = {}
    for spec in STUDENTS:
        username = spec["username"]
        full = f"{spec['last_name']} {spec['first_name']} {spec['patronymic']}"
        user = User.objects.filter(username=username).first()
        email = f"{username}@qku.edu.az"

        if user is None:
            if act(f"User yaradılır: {username} ({full}) — {email}"):
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=PASSWORD,
                    first_name=spec["first_name"],
                    last_name=spec["last_name"],
                )
        else:
            out(f"    mövcuddur: {username}")
            if act(f"{username}: parol yenilənir"):
                user.set_password(PASSWORD)
                user.save(update_fields=["password"])

        created_users[spec["exam"]] = user
        if user is None:
            continue

        profile = getattr(user, "profile", None)
        if profile is not None and act(f"{username}: profil (rol=student, qrup={GROUP_NAME}, OTP söndürülür)"):
            profile.role = "student"
            profile.organization = organization
            profile.organization_type = organization.org_type
            profile.student_group_number = GROUP_NAME
            profile.password_change_required = False
            profile.email_verified = True
            profile.save()

        membership = Membership.objects.filter(user=user, organization=organization).first()
        if membership is None:
            if act(f"{username}: Membership (student, aktiv)"):
                Membership.objects.create(
                    user=user, organization=organization, role=student_role, is_primary=True, is_active=True
                )
        elif act(f"{username}: Membership aktivləşdirilir"):
            membership.role = student_role
            membership.is_active = True
            membership.is_primary = True
            membership.save()

    # ── 3. Qrup ────────────────────────────────────────────────────────────
    # StudentGroup.save() full_clean() çağırır və primary müəllimin TEACHER
    # rolunda olmasını tələb edir (access_policy.py) — exam_center kimi digər
    # rollar qəbul edilmir. Ona görə rol burada əvvəlcədən yoxlanır.
    out(f"\n3) QRUP — {GROUP_NAME}")

    def _teacher_role_users():
        return (
            Membership.objects.filter(organization=organization, is_active=True, role__name="teacher")
            .select_related("user")
            .order_by("user__username")
        )

    teacher = None
    if GROUP_TEACHER:
        candidate = _teacher_role_users().filter(user__username=GROUP_TEACHER).first()
        if candidate:
            teacher = candidate.user
        else:
            out(f"    !! '{GROUP_TEACHER}' bu org-da TEACHER rolunda deyil — model onu qəbul etmir.")
    if teacher is None:
        first = _teacher_role_users().first()
        teacher = first.user if first else None
        if teacher is not None:
            out(f"    (avtomatik seçildi: {teacher.username})")

    if teacher is None:
        out("    !! teacher rollu istifadəçi tapılmadı — qrup buraxılır (imtahanlara təsiri yoxdur)")
    else:
        out(f"    qrup sahibi (müəllim): {teacher.username} — {teacher.get_full_name() or '—'}")
        group = StudentGroup.objects.filter(organization=organization, name=GROUP_NAME).first()
        try:
            if group is None:
                if act(f"StudentGroup yaradılır: {GROUP_NAME}"):
                    group = StudentGroup.objects.create(organization=organization, name=GROUP_NAME, teacher=teacher)
            else:
                out(f"    mövcuddur: {group.name}")
            if group is not None and act(f"{GROUP_NAME}: hər iki tələbə qrupa əlavə olunur"):
                for user in created_users.values():
                    if user is not None:
                        group.students.add(user)
        except Exception as exc:  # noqa: BLE001
            # Qrup köməkçi metadatadır — imtahan təyinatı allowed_users ilə
            # işləyir. Buradakı nasazlıq kritik addımları dayandırmamalıdır.
            out(f"    !! qrup yaradıla bilmədi: {exc}")
            out("    (imtahan təyinatı allowed_users ilə gedir — imtahana təsiri yoxdur)")

    # ── 4. Az dili imtahanı (mövcud #8) ────────────────────────────────────
    now = timezone.now()
    window_end = now + timedelta(days=WINDOW_DAYS)
    out(f"\n4) AZ DİLİ İMTAHANI (#{AZ_EXAM_ID}) — pəncərə {now:%d.%m.%Y %H:%M} → {window_end:%d.%m.%Y %H:%M}")
    az_exam = Exam.objects.filter(pk=AZ_EXAM_ID, organization=organization).first()
    if az_exam is None:
        out(f"    !! #{AZ_EXAM_ID} tapılmadı — buraxılır")
    else:
        out(f"    '{az_exam.title}' — sual={az_exam.questions.count()} aktiv={az_exam.is_active}")
        old_groups = list(az_exam.allowed_groups.values_list("name", flat=True))
        out(f"    hazırkı qrup təyinatı ({len(old_groups)}): {', '.join(old_groups) or '—'}")
        togrul = created_users.get("az")
        if act("köhnə qrup təyinatları silinir, yalnız Toğrul qalır, aktivləşdirilir"):
            az_exam.allowed_groups.clear()
            az_exam.allowed_users.clear()
            if togrul is not None:
                az_exam.allowed_users.add(togrul)
            az_exam.is_active = True
            az_exam.start_datetime = now
            az_exam.end_datetime = window_end
            az_exam.save(update_fields=["is_active", "start_datetime", "end_datetime"])

    # ── 5. Mülki müdafiə imtahanı (yeni, boş) ──────────────────────────────
    out(f"\n5) MÜLKİ MÜDAFİƏ İMTAHANI — pəncərə {now:%d.%m.%Y %H:%M} → {window_end:%d.%m.%Y %H:%M}")
    author = User.objects.filter(username="wcu_exam_center").first() or (az_exam.author if az_exam else None) or teacher
    mm_exam = Exam.objects.filter(organization=organization, title=MM_EXAM_TITLE).first()
    if mm_exam:
        out(f"    mövcuddur: #{mm_exam.pk} (sual={mm_exam.questions.count()})")
    elif act(f"Exam yaradılır: '{MM_EXAM_TITLE}' müəllif={getattr(author, 'username', '—')}"):
        mm_exam = Exam.objects.create(
            title=MM_EXAM_TITLE,
            author=author,
            organization=organization,
            subject=subject,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            total_duration_minutes=60,
            random_question_count=50,
            start_datetime=now,
            end_datetime=window_end,
        )
        out(f"    yaradıldı: #{mm_exam.pk}")

    turay = created_users.get("mm")
    if mm_exam is not None and turay is not None and act("Turay imtahana təyin olunur"):
        mm_exam.allowed_users.add(turay)
        mm_exam.is_active = True
        mm_exam.start_datetime = now
        mm_exam.end_datetime = window_end
        mm_exam.save(update_fields=["is_active", "start_datetime", "end_datetime"])

    out("\n" + "=" * 74)
    if APPLY:
        out("TAMAMLANDI. Qalan tək iş: Mülki müdafiə imtahanına 299 sualın UI-dan idxalı.")
    else:
        out("DRY-RUN bitdi — heç nə yazılmadı. Tətbiq üçün SEED_APPLY=yes.")
    out("=" * 74)


main()
