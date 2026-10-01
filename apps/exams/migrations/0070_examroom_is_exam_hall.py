"""İmtahan zalı bayrağı — ``ExamRoom.is_exam_hall`` (sahib 2026-10-01).

``ExamRoom`` təşkilatın YEGANƏ otaq reyestridir: legacy idxal (J10 / R-5 /
``scripts/ops/seed_qku_campuses_rooms.py``) bütün sinif otaqlarını buraya yazıb,
ona görə imtahan mərkəzinin «İmtahan zalları» siyahısında 150+ adi otaq
görünürdü. Bu miqrasiya:

1. ``is_exam_hall`` sahəsini əlavə edir (additiv; defolt True — mövcud kod/test
   müqaviləsi «ExamRoom = zal» qorunur) + ``(organization, is_exam_hall)`` indeksi;
2. MÖVCUD sətirləri təsnif edir — zal olaraq YALNIZ imtahan izi olan otaqlar
   qalır: ən azı bir qeydli kompüter (aktiv/deaktiv), ən azı bir zal oturumu
   (istənilən vəziyyət) və ya zala möhürlənmiş imtahan cəhdi. Qalan hamısı
   (izi olmayan adi otaqlar) ``False`` olur. Heç bir sətir silinmir, oturum /
   bilet / cəhd bağları toxunulmur — istifadə olunmuş zal zal olaraq qalır.

İdempotentdir (yalnız izsiz otaqları False edir). Geri dönüş: sütun silinir
(bayraq məlumatı itir — əvvəlki «hamısı zal» vəziyyəti ilə eynidir).
RLS: ``exams_examroom`` FORCE RLS altındadır — bütün tenant-ləri görmək üçün
``bypass_rls`` (bax 0050).
"""

from django.db import migrations, models
from django.db.models import Exists, OuterRef


def classify_existing_rooms(apps, schema_editor):
    from core.rls import bypass_rls

    ExamRoom = apps.get_model("exams", "ExamRoom")
    ExamRoomComputer = apps.get_model("exams", "ExamRoomComputer")
    ExamRoomSession = apps.get_model("exams", "ExamRoomSession")
    ExamAttempt = apps.get_model("exams", "ExamAttempt")

    with bypass_rls():
        has_computer = Exists(ExamRoomComputer.objects.filter(room_id=OuterRef("pk")))
        has_session = Exists(ExamRoomSession.objects.filter(room_id=OuterRef("pk")))
        has_attempt = Exists(ExamAttempt.objects.filter(room_id=OuterRef("pk")))
        ExamRoom.objects.filter(~has_computer, ~has_session, ~has_attempt, is_exam_hall=True).update(is_exam_hall=False)


class Migration(migrations.Migration):

    dependencies = [("exams", "0069_rls_exam_allowed_units")]

    operations = [
        migrations.AddField(
            model_name="examroom",
            name="is_exam_hall",
            field=models.BooleanField(default=True, help_text="is_exam_hall", verbose_name="is_exam_hall"),
        ),
        migrations.AddIndex(
            model_name="examroom",
            index=models.Index(fields=["organization", "is_exam_hall"], name="examroom_org_hall_idx"),
        ),
        migrations.RunPython(classify_existing_rooms, migrations.RunPython.noop),
    ]
