"""Jurnal demo data — bir qrupa N tələbə + mühazirə/seminar dərsləri +
davamiyyət/bal doldurur ki, elektron jurnal test edilə bilsin.

İdempotentdir (təkrar işlədilə bilər). Nümunə:

    python manage.py seed_journal_demo --count 15 --password 12345678
    python manage.py seed_journal_demo --group "KE-101 (Az" --count 15
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.exams.models import StudentGroup
from apps.registrar import gradebook as gb
from apps.registrar import journal_extras
from apps.registrar.models import CourseOffering, Enrollment, LessonMark, SelfWorkTopic
from core.rls import bypass_rls

User = get_user_model()


class Command(BaseCommand):
    help = "Bir qrupun elektron jurnalı üçün demo tələbələr + davamiyyət/bal doldurur (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--group", default="KE-101 (Az", help="Qrup adının bir hissəsi (icontains).")
        parser.add_argument("--count", type=int, default=15, help="Ümumi tələbə sayı hədəfi.")
        parser.add_argument("--password", default="12345678", help="Yeni tələbələrin parolu.")

    def handle(self, *args, **opts):
        with bypass_rls():
            self._run(opts)

    def _run(self, opts):
        group = StudentGroup.objects.filter(name__icontains=opts["group"]).order_by("id").first()
        if group is None:
            self.stderr.write(self.style.ERROR(f"Qrup tapılmadı: {opts['group']}"))
            return
        org = group.organization

        # CourseOffering.group registrar OrgUnit-ə işarə edir (exams.StudentGroup deyil) —
        # exams qrupunun org_unit-i ilə offering-ləri tapırıq.
        org_unit = group.org_unit
        if org_unit is None:
            from apps.organizations.models import OrgUnit

            org_unit = OrgUnit.objects.filter(organization=org, name=group.name).first()
        if org_unit is None:
            self.stderr.write(self.style.ERROR(f"'{group.name}' üçün registrar OrgUnit tapılmadı."))
            return
        offerings = list(CourseOffering.objects.filter(group=org_unit).select_related("subject"))
        if not offerings:
            self.stderr.write(self.style.ERROR(f"'{group.name}' (OrgUnit) üçün offering yoxdur."))
            return
        teacher = User.objects.filter(username="wcu_teacher").first()

        # 1) Roster: offering-lərdə artıq qeydiyyatlı tələbələr + exams qrup üzvləri;
        #    çatışmırsa yeni demo tələbələr yarat (hədəf = --count).
        roster = []
        seen = set()
        for offering in offerings:
            for enr in offering.enrollments.select_related("student"):
                if enr.student_id not in seen:
                    seen.add(enr.student_id)
                    roster.append(enr.student)
        for student in group.students.all():
            if student.id not in seen:
                seen.add(student.id)
                roster.append(student)

        base_slug = (group.name.split(" ")[0] or "grp").lower().replace("-", "")  # "ke101"
        i = 1
        while len(roster) < opts["count"]:
            uname = f"{base_slug}_demo_s{i}"
            i += 1
            user, was_created = User.objects.get_or_create(
                username=uname,
                defaults={
                    "email": f"{uname}@qku.edu.az",
                    "first_name": f"Demo{i - 1}",
                    "last_name": "Tələbə",
                    "is_active": True,
                },
            )
            if was_created:
                user.set_password(opts["password"])
                user.save()
            group.students.add(user)
            if user.id not in seen:
                seen.add(user.id)
                roster.append(user)
        roster = roster[: opts["count"]]

        # 2) Hər offering üçün: enrollment + dərslər + davamiyyət/bal.
        base = datetime.date(2024, 10, 1)
        plan = [("lecture", 0), ("seminar", 3), ("lecture", 7), ("seminar", 10), ("lecture", 14), ("seminar", 17)]
        for offering in offerings:
            gb.ensure_assessment_scheme(offering=offering)

            enrollments = []
            for student in roster:
                enr, _ = Enrollment.objects.get_or_create(
                    organization=org,
                    student=student,
                    offering=offering,
                    defaults={"status": Enrollment.Status.ENROLLED},
                )
                enrollments.append(enr)

            # Dərslər yoxdursa mühazirə + seminar qarışığı yarat.
            lessons = list(offering.lessons.order_by("date"))
            if not lessons:
                for kind, day_off in plan:
                    gb.create_lesson(
                        allow_past=True,
                        offering=offering,
                        kind=kind,
                        created_by=teacher,
                        date=base + datetime.timedelta(days=day_off),
                        topic="Demo dərs",
                    )
                lessons = list(offering.lessons.order_by("date"))

            # Davamiyyət qarışıq + seminar/lab balı (5..10). İdempotent get_or_create.
            for idx, lesson in enumerate(lessons):
                for j, enr in enumerate(enrollments):
                    absent = (idx + j) % 7 == 0
                    score = None if (lesson.kind == "lecture" or absent) else 5 + ((idx + j) % 6)
                    LessonMark.objects.get_or_create(
                        organization=org,
                        lesson=lesson,
                        enrollment=enr,
                        defaults={"status": "absent" if absent else "present", "score": score},
                    )

            # Sərbəst iş: 3 mövzu + bəzi "təhvil verilib" işarələri.
            topics = list(SelfWorkTopic.objects.filter(offering=offering).order_by("order"))
            while len(topics) < 3:
                topic = journal_extras.add_selfwork_topic(
                    offering=offering, title=f"Sərbəst iş mövzusu {len(topics) + 1}"
                )
                if topic is None:
                    break
                topics.append(topic)
            for ti, topic in enumerate(topics):
                for j, enr in enumerate(enrollments):
                    if (ti + j) % 2 == 0:
                        journal_extras.set_selfwork_mark(
                            offering=offering, topic_id=topic.id, enrollment_id=enr.id, done=True, by_user=teacher
                        )

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Demo jurnal dolduruldu: qrup '{group.name}' → {len(roster)} tələbə, "
                f"{len(offerings)} offering (mühazirə+seminar davamiyyət/bal + sərbəst iş)."
            )
        )
