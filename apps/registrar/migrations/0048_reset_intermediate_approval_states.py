"""Ara təsdiq statuslarını DRAFT-a endir (təsdiq zəncirinin ləğvi).

SAHİBİN QƏRARI (2026-08): müəllim → kafedra → dekan qiymət təsdiq zənciri ləğv
edildi. ``AssessmentScheme.approval_status`` sahəsi SXEMDƏ QALIR (legacy import
J7 fazası + ``registrar_scheme_publish_state_valid`` CheckConstraint ondan
asılıdır), lakin indi yalnız iki mənası var:

* ``draft``    — jurnal açıqdır;
* ``approved`` + ``is_published=True`` — jurnal BAĞLIDIR (RİM bağlayıb).

Ara vəziyyətlərdə (``submitted`` / ``chair_approved`` / ``returned``) qalmış
sətirlər ARTIQ heç kim tərəfindən irəli aparıla bilməzdi — o jurnallar əbədi
kilidli qalardı (``journal_is_locked`` submitted/chair_approved-u da kilid
sayırdı). Ona görə onlar DRAFT-a endirilir: müəllim jurnalını yenidən yaza bilir.

``approved`` sətirlərinə TOXUNULMUR — onlar həqiqətən yekunlaşmış jurnallardır.

GERİ DÖNÜŞ: miqrasiya reversible-dır, lakin ara statusun ORİJİNAL dəyəri
bərpa OLUNMUR (qəsdən — hansı sətrin hansı ara mərhələdə olduğu artıq məna
daşımır). Reverse no-op-dur ki, geri qayıdış zənciri bloklanmasın.
"""

from django.db import migrations

_INTERMEDIATE = ("submitted", "chair_approved", "returned")


def reset_to_draft(apps, schema_editor):
    AssessmentScheme = apps.get_model("registrar", "AssessmentScheme")
    AssessmentScheme.objects.filter(approval_status__in=_INTERMEDIATE).update(
        approval_status="draft",
        is_published=False,
    )


def noop(apps, schema_editor):
    """Geri dönüş: ara statuslar bərpa edilmir (məlumat qəsdən itirilir)."""


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0047_rls_journal_close_notice"),
    ]

    operations = [migrations.RunPython(reset_to_draft, noop)]
