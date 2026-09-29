"""
Canlı imtahan (live_exam) üçün SİNTETİK demo məlumatı — yalnız lokal/sandbox bazası üçün.

Yaradır (idempotent): demo təşkilat, ``exam.host`` icazəli demo müəllim və 8 suallı test
imtahanı (tək/çox seçimli, qısa/uzun mətn, 2–5 variant). Real şəxs məlumatı YOXDUR.

    DATABASE_URL=... python manage.py seed_live_demo
    python manage.py seed_live_demo --password 'LiveDemo-2026!'

Parol defolt olaraq ``LIVE_DEMO_PASSWORD`` mühit dəyişənindən, o da yoxdursa aşağıdakı
test dəyərindən götürülür. İstehsal bazasında işlədilməməlidir (``DEBUG`` və ya
``--i-know-this-is-not-prod`` tələb olunur).
"""

from __future__ import annotations

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

DEFAULT_PASSWORD = "LiveDemo-2026!"
TEACHER_USERNAME = "live_demo_teacher"
ORG_SLUG = "live-demo"
EXAM_TITLE = "Canlı viktorina — demo"

# (mətn, rejim, [(variant, düzgün?)...])
QUESTIONS = [
    (
        "Azərbaycanın paytaxtı hansı şəhərdir?",
        "single",
        [("Bakı", True), ("Gəncə", False), ("Sumqayıt", False), ("Şəki", False)],
    ),
    ("2 + 2 × 2 = ?", "single", [("6", True), ("8", False), ("4", False)]),
    (
        "Aşağıdakılardan hansılar proqramlaşdırma dilidir? (bir neçə düzgün cavab)",
        "multiple",
        [("Python", True), ("HTML", False), ("Rust", True), ("JSON", False), ("Go", True)],
    ),
    (
        "Günəş sistemində ən böyük planet hansıdır?",
        "single",
        [("Yupiter", True), ("Saturn", False), ("Yer", False), ("Mars", False)],
    ),
    ("Su 100 °C-də qaynayır (dəniz səviyyəsində).", "single", [("Doğru", True), ("Yanlış", False)]),
    (
        "Uzun sual mətni yoxlaması: verilənlər bazasında indeks nə üçün istifadə olunur və "
        "hansı halda yazma əməliyyatlarını yavaşlada bilər? Ən dəqiq cavabı seçin.",
        "single",
        [
            ("Axtarışı sürətləndirir, amma hər yazıda indeks də yenilənir", True),
            ("Yalnız ehtiyat nüsxə üçün lazımdır", False),
            ("Cədvəli şifrələyir", False),
            ("Heç bir təsiri yoxdur", False),
        ],
    ),
    (
        "Hansı rənglər əsas (RGB) rənglərdir?",
        "multiple",
        [("Qırmızı", True), ("Yaşıl", True), ("Sarı", False), ("Mavi", True)],
    ),
    ("Bir ildə neçə ay var?", "single", [("12", True), ("10", False), ("13", False), ("11", False)]),
]


class Command(BaseCommand):
    help = "Canlı imtahan üçün sintetik demo müəllim + 8 suallı imtahan yaradır (lokal/sandbox)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default=os.environ.get("LIVE_DEMO_PASSWORD", DEFAULT_PASSWORD))
        parser.add_argument("--i-know-this-is-not-prod", action="store_true", dest="force")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("DEBUG söndürülüb — istehsal bazası ola bilər. Əmin olsanız --i-know-this-is-not-prod.")
        User = get_user_model()
        # Request-dan kənar DB giriş nöqtəsi (FAZA4): layihə standartı rls_worker_atomic + bypass.
        with rls_worker_atomic(), bypass_rls():
            teacher, created = User.objects.get_or_create(
                username=TEACHER_USERNAME,
                defaults={"email": "live-demo-teacher@example.invalid", "first_name": "Demo", "last_name": "Müəllim"},
            )
            teacher.set_password(options["password"])
            teacher.save()
            org, _ = Organization.objects.get_or_create(
                slug=ORG_SLUG,
                defaults={
                    "name": "Canlı Demo Universiteti",
                    "org_type": OrganizationType.UNIVERSITY,
                    "owner": teacher,
                    "status": "active",
                    "is_active": True,
                },
            )
            profile = teacher.profile
            profile.role = ProfileRole.TEACHER
            profile.organization = org
            profile.organization_type = org.org_type
            profile.save()
            role, _ = Role.objects.update_or_create(
                organization=org,
                name="instructor",
                defaults={
                    "display_name": "Instructor",
                    "level": 50,
                    "scope_type": RoleScopeType.ORGANIZATION,
                    "permissions": ["exam.host", "exam.manage"],
                    "is_system": False,
                    "is_active": True,
                },
            )
            Membership.objects.update_or_create(
                user=teacher, organization=org, defaults={"role": role, "is_active": True, "is_primary": True}
            )
            exam, exam_created = Exam.objects.get_or_create(
                title=EXAM_TITLE,
                author=teacher,
                defaults={"organization": org, "exam_type": "test", "is_active": True, "is_public": False},
            )
            if exam_created:
                for order, (text, mode, options_) in enumerate(QUESTIONS, start=1):
                    question = ExamQuestion.objects.create(
                        exam=exam, order=order, text=text, points=1000, answer_mode=mode
                    )
                    for label, (option_text, correct) in zip("ABCDE", options_):
                        ExamQuestionOption.objects.create(
                            question=question, label=label, text=option_text, is_correct=correct
                        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Hazır: müəllim={TEACHER_USERNAME} (parol: --password / LIVE_DEMO_PASSWORD), "
                f"imtahan slug={exam.slug}, suallar={exam.questions.count()}"
            )
        )
