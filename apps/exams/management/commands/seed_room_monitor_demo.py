"""Zal monitorunu REAL yüklə göstərmək üçün demo data.

Mövcud zala (default: AQR-101) qarışıq statuslu tələbələr doldurur:
imtahanda olanlar (bir qismi pozuntulu), gözləyənlər, bitirənlər, çıxarılanlar —
bir neçə FƏRQLİ fənn imtahanı üzrə. Beləliklə zallar səhifəsindəki
"Hazırda gedən imtahanlar" bölməsi və zal monitorunun xəritəsi/filtrləri
dolu vəziyyətdə görünür.

İşə salma (təkrar işə salına bilər — köhnə demo sətirlərini təmizləyib yenidən qurur):
    python manage.py seed_room_monitor_demo
    python manage.py seed_room_monitor_demo --room AQR-101 --active 14 --waiting 5 --completed 4 --removed 3

QEYD: bitirənlər xəritədə yalnız ~3 dəq görünür (FINAL_RESULT_VISIBLE_SECONDS),
çıxarılanlar ~15 dəq (REMOVED_VISIBLE_SECONDS) — komandadan dərhal sonra baxın.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.exams.domain.final_center import (
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_READY,
    TICKET_STATUS_REMOVED,
    TICKET_STATUS_WAITING,
)
from apps.exams.models import Exam, ExamAttempt, ExamQuestion, ExamQuestionOption, ExamRoom, FinalExamTicket
from apps.exams.services.final_center import open_entry, start_room
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic
from core.roles import ProfileRole

from ._seed_helpers import UsersSeedMixin

_USERNAME_PREFIX = "monitor_demo_"

_DEMO_EXAMS = (
    "Riyaziyyat — Final imtahanı (Demo)",
    "Fizika — Final imtahanı (Demo)",
    "İnformatika — Final imtahanı (Demo)",
)


class Command(UsersSeedMixin, BaseCommand):
    help = "Zal monitoru üçün qarışıq statuslu demo tələbələr (imtahanda/gözləyir/bitirib/çıxarılıb)."

    def add_arguments(self, parser):
        parser.add_argument("--room", default="AQR-101", help="Zal kodu (mövcud olmalıdır).")
        parser.add_argument("--active", type=int, default=14, help="İmtahanda olan tələbə sayı.")
        parser.add_argument("--waiting", type=int, default=5, help="Gözləyən tələbə sayı.")
        parser.add_argument("--completed", type=int, default=4, help="Bitirmiş tələbə sayı.")
        parser.add_argument("--removed", type=int, default=3, help="Çıxarılmış tələbə sayı.")
        parser.add_argument("--password", default="DemoPass123!", help="Demo tələbə şifrəsi.")

    @transaction.atomic
    @rls_worker_atomic()
    @bypass_rls()
    def handle(self, *args, **options):
        room = ExamRoom.objects.filter(code=options["room"]).select_related("organization").first()
        if room is None:
            raise CommandError(f"'{options['room']}' kodlu zal tapılmadı — əvvəl zalı yaradın.")
        org = room.organization
        operator = org.owner
        now = timezone.now()

        # ── Təkrar işə salma: köhnə demo izlərini təmizlə ────────────────────
        FinalExamTicket.objects.filter(student__username__startswith=_USERNAME_PREFIX).delete()
        ExamAttempt.objects.filter(user__username__startswith=_USERNAME_PREFIX).delete()

        # ── Bir neçə fərqli fənn imtahanı (canlı siyahı dolu görünsün) ──────
        exams = [self._ensure_demo_exam(org, operator, title) for title in _DEMO_EXAMS]

        # ── Canlı oturum: mövcudu götür, yoxdursa yarat + başlat ────────────
        session = room.sessions.filter(state__in=("entry_open", "active")).order_by("scheduled_start", "id").first()
        if session is None:
            session = room.sessions.create(
                organization=org,
                scheduled_start=now,
                scheduled_end=now + timedelta(hours=4),
                created_by=operator,
            )
            open_entry(session, operator)
            session.refresh_from_db()
        if session.state == "entry_open":
            start_room(session, operator)
            session.refresh_from_db()

        # Yalnız BOŞ kompüterlər paylanır: bir oturumda seat unikaldır
        # (uniq_seat_per_session) — tələbə sayı kompüterdən çoxdursa qalanlar
        # seat-siz yaradılır (siyahıda görünür, xəritədə yer tutmur).
        taken_seats = set(session.tickets.filter(seat_number__isnull=False).values_list("seat_number", flat=True))
        computers = [
            computer
            for computer in room.computers.filter(is_active=True).order_by("seat_number", "id")
            if computer.seat_number not in taken_seats
        ]
        student_role = self._resolve_role(org, ProfileRole.STUDENT)

        counters = {"active": 0, "violated": 0, "waiting": 0, "completed": 0, "removed": 0}
        index = 0

        def next_student():
            nonlocal index
            index += 1
            username = f"{_USERNAME_PREFIX}{index:03d}"
            user = self._ensure_user(username, f"{username}@example.com", options["password"])
            self._assign_profile(user, org, ProfileRole.STUDENT)
            self._ensure_membership(user, org, student_role, operator)
            user.first_name, user.last_name = "Demo", f"Tələbə {index:03d}"
            user.save(update_fields=["first_name", "last_name"])
            return user

        def computer_for(position):
            # Dövrə vurmuruq — kompüter bitəndə None (seat toqquşması olmasın).
            return computers[position] if position < len(computers) else None

        # ── İmtahanda olanlar (hər 4-cüsü pozuntulu) ─────────────────────────
        for position in range(options["active"]):
            student = next_student()
            exam = exams[position % len(exams)]
            computer = computer_for(position)
            violated = position % 4 == 1
            attempt = ExamAttempt.objects.create(
                user=student,
                exam=exam,
                attempt_number=1,
                status="in_progress",
                started_at=now - timedelta(minutes=10 + position),
                room=room,
                room_computer=computer,
                supervision_status="active",
                supervision_violation_count=3 + (position % 3) if violated else 0,
            )
            FinalExamTicket.objects.create(
                organization=org,
                session=session,
                exam=exam,
                student=student,
                attempt=attempt,
                status=TICKET_STATUS_ACTIVE,
                seat_number=computer.seat_number if computer else None,
                started_at=attempt.started_at,
            )
            if violated:
                self._seed_incidents(org, attempt, student, exam, count=attempt.supervision_violation_count)
            counters["active"] += 1
            counters["violated"] += int(violated)

        # ── Gözləyənlər (waiting + bir neçə ready — ekranda ikisi də "Gözləyir") ─
        for position in range(options["waiting"]):
            student = next_student()
            FinalExamTicket.objects.create(
                organization=org,
                session=session,
                exam=exams[position % len(exams)],
                student=student,
                status=TICKET_STATUS_READY if position % 3 == 2 else TICKET_STATUS_WAITING,
            )
            counters["waiting"] += 1

        # ── Bitirənlər (təzə — xəritədə hələ görünsün) ──────────────────────
        for position in range(options["completed"]):
            student = next_student()
            exam = exams[position % len(exams)]
            attempt = ExamAttempt.objects.create(
                user=student,
                exam=exam,
                attempt_number=1,
                status="submitted",
                started_at=now - timedelta(minutes=40),
                finished_at=now - timedelta(seconds=30 + position * 10),
                room=room,
                room_computer=None,
            )
            FinalExamTicket.objects.create(
                organization=org,
                session=session,
                exam=exam,
                student=student,
                attempt=attempt,
                status=TICKET_STATUS_COMPLETED,
                started_at=attempt.started_at,
                completed_at=attempt.finished_at,
            )
            counters["completed"] += 1

        # ── Çıxarılanlar (pozuntu limiti) ───────────────────────────────────
        for position in range(options["removed"]):
            student = next_student()
            exam = exams[position % len(exams)]
            attempt = ExamAttempt.objects.create(
                user=student,
                exam=exam,
                attempt_number=1,
                status="submitted",
                started_at=now - timedelta(minutes=30),
                finished_at=now - timedelta(minutes=2),
                room=room,
                supervision_status="removed",
                supervision_violation_count=6,
            )
            FinalExamTicket.objects.create(
                organization=org,
                session=session,
                exam=exam,
                student=student,
                attempt=attempt,
                status=TICKET_STATUS_REMOVED,
                removal_action="removed",
                removal_reason="Təkrar tam ekran pozuntusu — nəzarətçi qərarı ilə imtahandan çıxarıldı.",
                removed_at=attempt.finished_at,
                started_at=attempt.started_at,
            )
            self._seed_incidents(org, attempt, student, exam, count=6)
            counters["removed"] += 1

        self.stdout.write(self.style.SUCCESS(f"Zal: {room.name} [{room.code}] — oturum #{session.pk} (active)"))
        self.stdout.write(
            "Yaradıldı: {active} imtahanda ({violated} pozuntulu), {waiting} gözləyir, "
            "{completed} bitirib, {removed} çıxarılıb".format(**counters)
        )
        self.stdout.write(f"Fənlər: {', '.join(e.title for e in exams)}")
        self.stdout.write("Bax: /exams/center/rooms/ (canlı siyahı) və zal monitoru.")
        self.stdout.write("QEYD: bitirənlər ~3 dəq, çıxarılanlar ~15 dəq sonra xəritədən düşür (sayğaclar qalır).")

    # Pozuntu ssenarisi: tam ekrandan çıxma → tab dəyişmə → kopyalama cəhdi …
    # Hesabatın "Pozuntular" vərəqi məhz bu qeydlərdən qurulur.
    INCIDENT_SCRIPT = [
        ("fullscreen_exited", "high", {"reason": "Escape"}),
        ("tab_switched", "high", {"detail": "başqa tab-a keçdi"}),
        ("copy_attempt", "medium", {"key": "Ctrl+C"}),
        ("window_blurred", "medium", {"detail": "pəncərə fokusu itdi"}),
        ("paste_attempt", "critical", {"key": "Ctrl+V"}),
        ("keyboard_shortcut", "low", {"key": "Alt+Tab"}),
    ]

    def _seed_incidents(self, org, attempt, student, exam, *, count):
        from datetime import timedelta

        from apps.exams.models import SupervisionIncident

        for index in range(min(count, len(self.INCIDENT_SCRIPT))):
            event_type, severity, metadata = self.INCIDENT_SCRIPT[index]
            incident = SupervisionIncident.objects.create(
                organization=org,
                exam=exam,
                attempt=attempt,
                student=student,
                event_type=event_type,
                severity=severity,
                metadata=metadata,
                violation_count_at_time=index + 1,
            )
            # `timestamp` auto_now_add-dır — demo üçün imtahan gedişinə yay.
            SupervisionIncident.objects.filter(pk=incident.pk).update(
                timestamp=attempt.started_at + timedelta(minutes=3 * (index + 1))
            )

    def _ensure_demo_exam(self, org, author, title):
        exam, created = Exam.objects.get_or_create(
            organization=org,
            title=title,
            defaults={
                "author": author,
                "exam_type": "test",
                "exam_type_extended": "final",
                "is_active": True,
                "total_duration_minutes": 60,
            },
        )
        if created:
            question = ExamQuestion.objects.create(exam=exam, order=1, text="Demo sual?", points=1)
            ExamQuestionOption.objects.create(question=question, label="A", text="Cavab", is_correct=True)
        return exam
