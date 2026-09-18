"""Sahibin qərarı 2026-09-19 (gecə tapşırığı): Elvin Qurbanovun 2026/2027 Payız
açılışları üçün — cədvəl slotları (göndərilən dərs cədvəlindən, yalnız QKU
xanaları), «Müasir Veb proqramlaşdırma vasitələri · 233 K ing» sillabusu
(masaüstündəki rəsmi sillabusdan), təsdiqi, ilk dərs (15.09.2026, 15:15–16:45,
otaq 11) və bütün tələbələr üçün «iştirak edir».

İstehsalda: docker exec -i <app> python manage.py shell < scripts/ops/seed_elvin_fall_2026_journal.py
İdempotentdir: mövcud sillabus / slot / dərs təkrarlanmır. Yalnız oxumaq üçün:
    DRY=1 docker exec -i -e DRY=1 <app> python manage.py shell < …
"""

import os
from datetime import date, time

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.organizations.models import AcademicPeriod, Organization
from apps.registrar.gradebook import save_marks
from apps.registrar.gradebook_lessons import create_lesson
from apps.registrar.models import CourseOffering, Lesson, ScheduleSlot
from apps.syllabus.constants import SectionKey
from apps.syllabus.models import Syllabus
from apps.syllabus.services.drafts import create_draft, recompute_completion, save_section
from apps.syllabus.services.scoping import resolve_actor as syllabus_actor
from apps.syllabus.services.workflow import approve, start_review, submit
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

DRY = os.environ.get("DRY") == "1"
User = get_user_model()

# Cədvəl (göndərilən şəkil, yalnız Qərbi Kaspi xanaları). weekday 1=B.e … 5=Cümə.
SLOTS = [
    # (qrup, fənn açar sözü, weekday, start, end, kind, week_type, otaq)
    ("233 K ing", "Müasir Veb", 2, time(15, 15), time(16, 45), "lecture", "all", "11"),
    ("233 İT ing", "Müasir Veb", 2, time(16, 55), time(18, 25), "lecture", "all", ""),
    ("234 K ing", "Mobil", 3, time(11, 50), time(13, 20), "lecture", "odd", ""),
    ("234 K ing", "Mobil", 3, time(11, 50), time(13, 20), "seminar", "even", ""),
    ("233 K ing", "Müasir Veb", 3, time(13, 35), time(15, 5), "seminar", "odd", ""),
    ("233 İT ing", "Müasir Veb", 3, time(13, 35), time(15, 5), "seminar", "even", ""),
    ("233 İ ing", "", 3, time(15, 15), time(16, 45), "seminar", "odd", ""),
    ("233 İ ing", "", 3, time(16, 55), time(18, 25), "lecture", "all", ""),
    ("234 K az", "Mobil", 5, time(11, 50), time(13, 20), "lecture", "odd", ""),
    ("234 K az", "Mobil", 5, time(11, 50), time(13, 20), "seminar", "even", ""),
]

WEEKS = [
    ("Versiya nəzarət sistemləri – 1. Git-ə giriş: əmrlər, budaqlar, birləşmələr, iş axınları.", 2, 0),
    ("Versiya nəzarət sistemləri – 2. GitHub/GitLab ilə kollektiv proqram təminatının inkişafı.", 2, 0),
    ("HTML texnologiyası – 1. HTML nədir, sənəd strukturu, teq və atributlar, meta məlumatlar, formalar və linklər.", 2, 0),
    ("HTML texnologiyası – 2. Image, video, audio; input və select elementləri.", 2, 2),
    ("CSS – kaskad cədvəl stili. Box model, fon və border, pozisiyalar (static, relative, absolute, fixed).", 2, 2),
    ("CSS Flexbox və pseudo-class-lar. Flex yönümləri, yerləşdirmə, item tərtibatı.", 2, 2),
    ("CSS responsive dizayn və CSS Grid. Media queries, Grid strukturu, Flexbox ilə müqayisə.", 2, 2),
    ("SASS və SCSS. Sintaksis, mixins, variables, loops; preprosessorların üstünlükləri.", 2, 0),
    ("JavaScript-ə giriş və yerləşdirmə. head/body daxilində JS, xarici fayllar, dəyişənlər (var/let/const), operatorlar.", 2, 2),
    ("Şərtlər: if / else if / else və switch-case. Break və dövrlərin dayandırılması.", 2, 2),
    ("JavaScript data tipləri: string, number, boolean, undefined, null, object, array.", 2, 2),
    ("JavaScript-də dövrlər (loops): while, do-while, for, for-in, for-of; break və continue.", 2, 0),
    ("JavaScript-də funksiyalar: təyin, parametrlər, qaytarma, arrow funksiyalar, scope.", 2, 0),
    ("JavaScript-də massivlər: xüsusiyyətlər, length, prototip, massiv üsulları.", 2, 0),
    ("JavaScript-də obyektlər: obyekt üsulları, istifadəçi obyektləri, Date, requlyar ifadələr, Error.", 2, 1),
]  # fmt: skip
OUTCOMES = [
    "HTML5/CSS3 və JS/TS əsasında responsiv, komponent-əsaslı UI qurur.",
    "Git/GitHub iş axınında (branch → PR → code review → merge) komanda ilə effektiv işləyir.",
    "Node.js mühitində paket idarəetməsi, yığım/transpilyasiya və kod stili alətlərindən istifadə edir.",
    "REST/GraphQL API-lərini async/await ilə istehlak edir, JSON məlumatını emal edir və səhvləri idarə edir.",
    "Test (Jest/Testing Library) yazır, performansı optimallaşdırır, təhlükəsizlik və əlçatanlıq prinsiplərinə əməl edir.",
]
DESCRIPTION = (
    "«Müasir Veb Proqramlaşdırma Vasitələri» fənni veb inkişaf ekosisteminin müasir alətlərini və iş axınlarını "
    "nəzəri və praktiki yanaşma ilə təqdim edir. Tələbələr HTML5/CSS3 və JavaScript/TypeScript əsasında "
    "komponent-əsaslı UI quracaq, React və ya Vue kimi çərçivələrlə modul memarlıq, yönləndirmə və vəziyyət "
    "idarəetməsini tətbiq edəcəklər. Node.js mühitində paket idarəetməsi (npm/yarn/pnpm), yığım və transpilyasiya "
    "(Vite/Webpack/Babel), kod keyfiyyəti alətləri (ESLint, Prettier) və Git/GitHub üzərindən komanda işi "
    "öyrədiləcək. REST/GraphQL API-ləri ilə məlumat mübadiləsi, asinxron proqramlaşdırma, autentifikasiya və səhv "
    "emalının əsasları praktiki laboratoriyalarla möhkəmləndiriləcək."
)
GOAL = (
    "Tələbələrə veb inkişafın müasir alətlərini və metodologiyalarını öyrətmək, komponent-əsaslı ön uclu tətbiqlərin "
    "qurulması, serverlərlə məlumat mübadiləsi və layihə axınlarının idarə edilməsi bacarıqlarını formalaşdırmaq."
)
METHODS = [
    "Mühazirə",
    "Seminar / praktiki məşğələ",
    "Layihə əsaslı öyrənmə (mini-tapşırıqlar və yekun layihə)",
    "Kod baxışı (code review) və müzakirə",
]
PRIMARY = [
    "Flanagan, D. — JavaScript: The Definitive Guide (7-ci nəşr).",
    "Haverbeke, M. — Eloquent JavaScript (3-cü nəşr).",
    "Simpson, K. — You Don’t Know JS Yet (seriya).",
    "Wieruch, R. — The Road to React.",
    "Robbins, J. N. — Learning Web Design (5-ci nəşr).",
]
ADDITIONAL = [
    "Martin, R. C. — Clean Code.",
    "Fowler, M. — Refactoring (2-ci nəşr).",
    "Duckett, J. — HTML & CSS; JavaScript & jQuery.",
    "MDN Web Docs — https://developer.mozilla.org",
    "web.dev (Google) — https://web.dev",
]
SELF_TOPICS = [
    "Kiçik bir layihənin yaradılması, Git vasitəsilə idarə olunması və kollaborativ iş təcrübəsinin əldə olunması.",
    "Dəyişənlər, operatorlar və şərt ifadələrindən istifadə edərək sadə kalkulyator tətbiqi hazırlanması.",
]


def log(msg):
    print(("[DRY] " if DRY else "") + msg)


def find_offerings(org, period, teacher):
    return list(
        CourseOffering.objects.filter(
            organization=org, period=period, instructor=teacher, is_active=True
        ).select_related("subject", "group")
    )


def offering_for(offerings, group_name, subject_hint):
    for off in offerings:
        if off.group.name.replace("  ", " ") == group_name and (
            not subject_hint or subject_hint.lower() in off.subject.name.lower()
        ):
            return off
    return None


with rls_worker_atomic(), bypass_rls():
    org = Organization.objects.get(slug="qku")
    period = AcademicPeriod.objects.get(organization=org, name="Payız", academic_year="2026/2027")
    superadmin = User.objects.get(username="superadmin")
    teacher = (
        CourseOffering.objects.filter(
            organization=org,
            period=period,
            instructor__first_name__iexact="Elvin",
            instructor__last_name__istartswith="Qurbanov",
        )
        .values_list("instructor", flat=True)
        .first()
    )
    teacher = User.objects.get(pk=teacher) if teacher else None
    if teacher is None:
        raise SystemExit("Elvin Qurbanovun Payız 2026/2027 açılışı tapılmadı")
    offerings = find_offerings(org, period, teacher)
    log(
        f"Müəllim: {teacher.username} · açılış: {len(offerings)} → "
        + "; ".join(f"{o.subject.name[:30]}·{o.group.name}" for o in offerings)
    )

    with transaction.atomic():
        # 1) Cədvəl slotları
        created_slots = 0
        for group_name, hint, weekday, start, end, kind, week_type, room in SLOTS:
            off = offering_for(offerings, group_name, hint)
            if off is None:
                log(f"  slot ötürüldü (açılış yoxdur): {group_name} {hint} {weekday} {start}")
                continue
            exists = ScheduleSlot.objects.filter(
                offering=off, weekday=weekday, start_time=start, kind=kind, week_type=week_type
            ).exists()
            if exists:
                continue
            created_slots += 1
            if not DRY:
                ScheduleSlot.objects.create(
                    organization=org, offering=off, weekday=weekday, start_time=start, end_time=end,
                    room=room, week_type=week_type, kind=kind, created_by=superadmin,
                )  # fmt: skip
        log(f"Cədvəl slotu yaradıldı: {created_slots}")

        # 2) Sillabus — Müasir Veb · 233 K ing
        target = offering_for(offerings, "233 K ing", "Müasir Veb")
        if target is None:
            raise SystemExit("233 K ing · Müasir Veb açılışı tapılmadı")
        syllabus = Syllabus.objects.filter(organization=org, offering=target, is_active=True).first()
        if syllabus is None and not DRY:
            author_actor = syllabus_actor(teacher, org)
            admin_actor = syllabus_actor(superadmin, org)
            actor = author_actor if author_actor.has("syllabus.edit") else admin_actor
            syllabus, version = create_draft(
                organization=org, subject=target.subject, period=period, actor=actor, offering=target,
                chair_unit=target.group.parent, author=teacher,
                plan_hours={"lecture": sum(w[1] for w in WEEKS), "seminar": sum(w[2] for w in WEEKS), "lab": 0},
            )  # fmt: skip
            sections = {
                SectionKey.INFO.value: {
                    "teacher": "Elvin Qurbanov Şahin oğlu",
                    "office_hours": "Çərşənbə axşamı 14:00–15:00, otaq 11 (və e-poçtla)",
                    "prerequisites": "Proqramlaşdırmanın əsasları",
                },
                SectionKey.DESC.value: {"description": DESCRIPTION, "goal": GOAL},
                SectionKey.OUT.value: {"outcomes": OUTCOMES},
                SectionKey.WEEK.value: {
                    "rows": [
                        {
                            "topic": topic,
                            "lecture": lec,
                            "seminar": sem,
                            "lab": 0,
                            "outcome": f"TN{(i % len(OUTCOMES)) + 1}",
                        }
                        for i, (topic, lec, sem) in enumerate(WEEKS)
                    ]
                },
                SectionKey.METHOD.value: {"methods": METHODS, "note": ""},
                SectionKey.SELF.value: {"option": "2x5", "topics": [{"title": t} for t in SELF_TOPICS], "archived": []},
                SectionKey.LIT.value: {"primary": PRIMARY, "additional": ADDITIONAL},
            }
            for section_id, data in sections.items():
                save_section(version=version, section_id=section_id, data=data, actor=actor)
            report = recompute_completion(version)
            version.refresh_from_db()
            log(f"Sillabus v{version.label}: tamamlanma {version.completion_percent}%")
            if version.completion_percent < 100:
                log(f"  çatışmazlıq: {getattr(report, 'issues', report)}")
            version = submit(version=version, actor=actor)
            version = start_review(version=version, actor=admin_actor)
            version = approve(
                version=version, actor=admin_actor, comment="RİM: idxal olunmuş rəsmi sillabus (2026-09-19)"
            )
            log(f"Sillabus təsdiqləndi: {version.status}")
        else:
            log(f"Sillabus mövcuddur: {syllabus.pk if syllabus else '(DRY)'}")

        # 3) İlk dərs + iştirak
        first_date = date(2026, 9, 15)
        lesson = Lesson.objects.filter(offering=target, date=first_date).first()
        if lesson is None and not DRY:
            lesson = create_lesson(
                offering=target, date=first_date, kind="lecture", topic=WEEKS[0][0], hours=2,
                start_time=time(15, 15), end_time=time(16, 45), created_by=teacher, instructor=teacher,
                allow_past=True,
            )  # fmt: skip
        enrollments = list(target.enrollments.filter(status="enrolled"))
        if lesson is not None:
            entries = [
                {"lesson_id": str(lesson.pk), "enrollment_id": str(e.pk), "status": "present", "score": ""}
                for e in enrollments
            ]
            result = save_marks(offering=target, entries=entries, by_user=teacher, enforce_day=False, report=True)
            log(f"İlk dərs {first_date}: tələbə {len(enrollments)} · iştirak yazıldı {result}")
        else:
            log(f"İlk dərs (DRY): tələbə {len(enrollments)}")
        if DRY:
            transaction.set_rollback(True)
