"""Köhnə sual göndərişlərinin YENİ vəziyyət maşınına köçürülməsi.

2026-09-ə qədər axın «müəllim → İmtahan Mərkəzi» idi və mərkəzdə gözləyən
göndərişin statusu ``pending`` olurdu.  Yeni zəncirdə (müəllim → KAFEDRA
MÜDİRİ → mərkəz) mərkəz mərhələsinin adı ``center_review``-dir.

Bu miqrasiya:

* ``pending`` → ``center_review`` (köhnə göndərişlər mərkəzin növbəsində
  QALIR — kafedraya geri atılmır, çünki mərkəz onlara artıq baxırdı);
* ``reached_center_at`` bütün mərkəzə çatmış sətirlərdə doldurulur
  (``reviewed_at``, o yoxdursa ``created_at``) — mərkəzin görünürlük qapısı
  məhz bu sahədir, boş qalsa köhnə göndərişlər mərkəzdən İTƏRDİ.

``chair_unit`` qəsdən BOŞ qalır: köhnə göndərişlər kafedra mərhələsindən
keçməyib, uydurma bağ yaratmırıq (yeni göndərişlərdə servis qatı doldurur).
İdempotentdir; geri dönüşdə ``center_review`` yenidən ``pending`` olur.
"""

from django.db import migrations
from django.db.models import F, Q


def forward(apps, schema_editor):
    QuestionSubmission = apps.get_model("exams", "QuestionSubmission")
    QuestionSubmission.objects.filter(status="pending").update(status="center_review")
    QuestionSubmission.objects.filter(
        Q(status__in=("center_review", "accepted", "rejected")) & Q(reached_center_at__isnull=True)
    ).update(reached_center_at=F("created_at"))


def backward(apps, schema_editor):
    QuestionSubmission = apps.get_model("exams", "QuestionSubmission")
    QuestionSubmission.objects.filter(status="center_review").update(status="pending")


class Migration(migrations.Migration):

    dependencies = [("exams", "0063_question_submission_chair_stage")]

    operations = [migrations.RunPython(forward, backward)]
