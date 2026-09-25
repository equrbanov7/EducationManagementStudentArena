"""«Sorğu nəticələri» (F2) testləri üçün dünya — F1 ``build_world`` + əlavə struktur
və BİRBAŞA yaradılmış anonim cavablar (analitika yalnız cavab snapshot-unu oxuyur).

Struktur (``build_world`` üstündən):
* fakültə F → kafedra A (müəllim A, C, E), kafedra B (müəllim B); fakültə F2 →
  kafedra D (müəllim D); qruplar G (A altında), G2 (B altında).
* Cari kampaniya (açıq, k = 3) və əvvəlki dövrün kampaniyası (bağlı).

Cari kampaniyanın cavabları (müəllim bölməsi):
* A — 6 (riyaziyyat · G), şərhlərlə; C — 3 (riyaziyyat · G); E — 2 (< k, gizli);
* B — 5: 4 (fizika · G) + 1 (fizika · G2) → G filtri tamamlayıcı qaydanı işə salır;
* D — 4 (kimya · G2, fakültə F2).
Ümumi bölmə: 5 (G) + 1 (G2), «suggestions» mətnləri ilə. Əvvəlki dövr: A — 4.
"""

from __future__ import annotations

import datetime

from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar.models import Subject
from apps.surveys.constants import CampaignStatus, Section
from apps.surveys.models import SurveyAnswer, SurveyReceipt, SurveyResponse
from core.constants import AcademicPeriodType, OrgUnitType
from core.rls import bypass_rls

from .factories import build_world, close_all, member, open_campaign


def _questions(campaign):
    return list(campaign.template.questions.all())


def add_responses(
    world,
    campaign,
    *,
    teacher,
    department,
    faculty,
    subject,
    group,
    count,
    score=4,
    overall=8,
    strengths="",
    improve="",
    scores=None,
):
    """``count`` anonim müəllim cavabı (bütün ballı suallar + istəyə görə şərh)."""
    questions = _questions(campaign)
    with bypass_rls():
        for index in range(count):
            response = SurveyResponse.objects.create(
                organization=world["org"],
                campaign=campaign,
                scope=Section.TEACHER,
                teacher=teacher,
                teacher_department=department,
                faculty=faculty,
                subject=subject,
                group=group,
            )
            answers = []
            for question in questions:
                if question.section != Section.TEACHER:
                    continue
                if question.kind == "likert5":
                    value = (scores or {}).get(question.code, score)
                    answers.append(
                        SurveyAnswer(organization=world["org"], response=response, question=question, score=value)
                    )
                elif question.kind == "scale10":
                    answers.append(
                        SurveyAnswer(organization=world["org"], response=response, question=question, score=overall)
                    )
                elif question.code == "strengths" and strengths:
                    answers.append(
                        SurveyAnswer(
                            organization=world["org"], response=response, question=question, text=f"{strengths} {index}"
                        )
                    )
                elif question.code == "improve" and improve:
                    answers.append(
                        SurveyAnswer(
                            organization=world["org"], response=response, question=question, text=f"{improve} {index}"
                        )
                    )
            SurveyAnswer.objects.bulk_create(answers)


def add_general(world, campaign, *, group, faculty, count, score=4, texts=()):
    questions = _questions(campaign)
    with bypass_rls():
        for index in range(count):
            response = SurveyResponse.objects.create(
                organization=world["org"], campaign=campaign, scope=Section.GENERAL, group=group, faculty=faculty
            )
            answers = []
            for question in questions:
                if question.section != Section.GENERAL:
                    continue
                if question.kind == "likert5":
                    answers.append(
                        SurveyAnswer(organization=world["org"], response=response, question=question, score=score)
                    )
                elif question.kind == "text" and index < len(texts):
                    answers.append(
                        SurveyAnswer(organization=world["org"], response=response, question=question, text=texts[index])
                    )
            SurveyAnswer.objects.bulk_create(answers)


def add_receipts(world, campaign, offering, teacher, department, students):
    with bypass_rls():
        for student in students:
            SurveyReceipt.objects.create(
                organization=world["org"],
                campaign=campaign,
                student=student,
                scope=Section.TEACHER,
                offering=offering,
                teacher=teacher,
                teacher_department=department,
                completed_on=datetime.date(2026, 9, 20),
            )


SUGGESTIONS = (
    "Kitabxana həftə sonu da açıq olsun",
    "Kitabxanada Wi-Fi zəifdir",
    "Yeməkxana qiymətləri yüksəkdir",
    "Kitabxana saatları uzadılsın, Wi-Fi gücləndirilsin",
    "Laboratoriya avadanlığı yenilənsin",
    '=HYPERLINK("http://x")',
)


def build_results_world(slug: str) -> dict:
    world = build_world(slug, students=4)
    org = world["org"]
    with bypass_rls():
        faculty2 = OrgUnit.objects.create(
            organization=org, name="Fakültə F2", slug=f"{slug}-f2", unit_type=OrgUnitType.FACULTY
        )
        chair_d = OrgUnit.objects.create(
            organization=org, name="Kafedra D", slug=f"{slug}-kd", unit_type=OrgUnitType.CHAIR, parent=faculty2
        )
        group2 = OrgUnit.objects.create(
            organization=org, name="G-202", slug=f"{slug}-g2", unit_type=OrgUnitType.GROUP, parent=world["chair_b"]
        )
        teacher_d = member(org, f"{slug}_td", "teacher", unit=chair_d)
        teacher_e = member(org, f"{slug}_te", "teacher", unit=world["chair_a"])
        chem = Subject.objects.create(organization=org, code=f"{slug}-K", name="Kimya", chair_unit=chair_d)
        previous_period = AcademicPeriod.objects.create(
            organization=org,
            name=f"{slug} Yaz",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2025/2026",
            start_date=datetime.date(2026, 2, 1),
            end_date=datetime.date(2026, 6, 30),
            is_current=False,
        )
    close_all(world)
    campaign = open_campaign(world)
    from apps.surveys.services.campaigns import ensure_campaign

    with bypass_rls():
        previous, _created, _opened = ensure_campaign(org, previous_period)
        previous.status = CampaignStatus.CLOSED
        previous.save(update_fields=["status"])
    faculty, chair_a, chair_b, group = world["faculty"], world["chair_a"], world["chair_b"], world["group"]
    math, phys = world["math"], world["phys"]
    add_responses(
        world,
        campaign,
        teacher=world["teacher_a"],
        department=chair_a,
        faculty=faculty,
        subject=math,
        group=group,
        count=6,
        score=5,
        overall=9,
        strengths="Mövzuları aydın izah edir",
        improve="Daha çox praktika",
    )
    add_responses(
        world,
        campaign,
        teacher=world["teacher_c"],
        department=chair_a,
        faculty=faculty,
        subject=math,
        group=group,
        count=3,
        score=4,
        overall=8,
    )
    add_responses(
        world,
        campaign,
        teacher=teacher_e,
        department=chair_a,
        faculty=faculty,
        subject=math,
        group=group,
        count=2,
        score=1,
        overall=2,
    )
    add_responses(
        world,
        campaign,
        teacher=world["teacher_b"],
        department=chair_b,
        faculty=faculty,
        subject=phys,
        group=group,
        count=4,
        score=3,
        overall=6,
    )
    add_responses(
        world,
        campaign,
        teacher=world["teacher_b"],
        department=chair_b,
        faculty=faculty,
        subject=phys,
        group=group2,
        count=1,
        score=2,
        overall=4,
    )
    add_responses(
        world,
        campaign,
        teacher=teacher_d,
        department=chair_d,
        faculty=faculty2,
        subject=chem,
        group=group2,
        count=4,
        score=4,
        overall=7,
    )
    add_general(world, campaign, group=group, faculty=faculty, count=5, score=4, texts=SUGGESTIONS[:5])
    add_general(world, campaign, group=group2, faculty=faculty, count=1, score=2, texts=SUGGESTIONS[5:])
    add_responses(
        world,
        previous,
        teacher=world["teacher_a"],
        department=chair_a,
        faculty=faculty,
        subject=math,
        group=group,
        count=4,
        score=4,
        overall=7,
    )
    add_receipts(world, campaign, world["off_math"], world["teacher_a"], chair_a, world["students"][:3])
    add_receipts(world, campaign, world["off_phys"], world["teacher_b"], chair_b, world["students"][:2])
    with bypass_rls():
        world.update(
            faculty2=faculty2,
            chair_d=chair_d,
            group2=group2,
            teacher_d=teacher_d,
            teacher_e=teacher_e,
            chem=chem,
            campaign=campaign,
            previous=previous,
            rector=member(org, f"{slug}_rector", "rector"),
            chair_head=member(org, f"{slug}_chair", "chair_head", unit=chair_a),
            qc_staff=member(org, f"{slug}_qc", "quality_control_staff"),
            dean=member(org, f"{slug}_dean", "dean", unit=faculty),
        )
    return world
