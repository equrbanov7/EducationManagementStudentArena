"""Plagiat yoxlaması: eyni fayl/mətn, yaxın-dublikat (MinHash + dəqiq yoxlama), hədlər, yalançı pozitiv yoxdur."""

from __future__ import annotations

import io
import zipfile

import pytest

from apps.subject_folder import public
from apps.subject_folder.models import SimilarityMatch, Submission
from apps.subject_folder.services.plagiarism import minhash
from apps.subject_folder.services.plagiarism.engine import run_similarity_check
from apps.subject_folder.services.plagiarism.normalize import normalize_text, words_of

from . import factories as f
from .conftest import upload

pytestmark = pytest.mark.django_db

ESSAY_A = (
    "Alqoritm müəyyən məsələni həll etmək üçün ardıcıl yerinə yetirilən addımlar toplusudur. Hər bir alqoritmin "
    "girişi, çıxışı və sonlu sayda addımı olmalıdır. Proqramlaşdırmada alqoritmin səmərəliliyi onun zaman və yaddaş "
    "mürəkkəbliyi ilə ölçülür. Məsələn, xətti axtarış ən pis halda bütün elementləri yoxlayır, ikili axtarış isə "
    "sıralanmış massivdə hər addımda axtarış sahəsini iki dəfə kiçildir. Sıralama alqoritmləri arasında qabarcıq, "
    "seçmə, birləşdirmə və sürətli sıralama ən çox öyrənilənlərdir. Birləşdirmə sıralaması böl və idarə et "
    "prinsipinə əsaslanır və həmişə n log n vaxtda işləyir. Sürətli sıralama orta halda çox sürətlidir, lakin ən pis "
    "halda kvadratik vaxt tələb edə bilər. Düzgün alqoritmin seçilməsi verilənlərin həcmindən və strukturundan asılıdır."
)
ESSAY_B = (
    "Azərbaycanın iqlimi olduqca müxtəlifdir və ölkənin ərazisində on bir iqlim tipindən doqquzu müşahidə olunur. "
    "Xəzər dənizi sahilində yay isti və quraq keçir, dağlıq rayonlarda isə qış soyuq və qarlı olur. Kür və Araz "
    "çayları ölkənin ən böyük su mənbələridir və kənd təsərrüfatı üçün mühüm əhəmiyyət daşıyır. Böyük Qafqaz "
    "dağlarının cənub yamacları sıx meşələrlə örtülüdür. Lənkəran ovalığında subtropik bitkilər, xüsusilə çay və "
    "sitrus meyvələri becərilir. Abşeron yarımadası neft yataqları ilə tanınır və burada neft hasilatı qədim "
    "dövrlərdən mövcuddur. Ölkənin təbii sərvətləri iqtisadiyyatın inkişafında əsas rol oynayır."
)
# A-nın «gizlədilmiş» köçürməsi: registr, durğu, ə→e, kiril «\u0430», görünməz boşluq, 2 söz dəyişikliyi + əlavə cümlə.
ESSAY_A_DISGUISED = (
    ESSAY_A.upper()
    .replace(".", " ;")
    .replace("məsələni", "mesələni")
    .replace("addımlar", "\u0430ddımlar")  # kiril «\u0430»
    .replace("girişi", "gi\u200brişi")
    .replace("Məsələn", "Misal üçün")
    .replace("kvadratik", "çox böyük")
    + " Bu mövzu imtahanda da soruşulur."
)


def _submit(ready, student, text=None, files=(), task=None):
    return public.submit(
        task=task or ready.homework, assignment=ready.assignment, student=student, text=text, files=list(files)
    )


def _check(*rows):
    for row in rows:
        run_similarity_check(row.pk)
    for row in rows:
        row.refresh_from_db()
    return rows


def _zip_bytes(name="data.txt", content=b"layihe fayli"):
    """Deterministik ZIP: ``writestr(<str>, …)`` elementə CARİ vaxtı (2 s dəqiqlik) yazır —
    eyni məzmunlu iki arxiv 2 s sərhədinin iki tərəfində fərqli bayt verirdi (CI-da ara-sıra düşürdü)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), content)
    return buffer.getvalue()


def test_normalization_is_azerbaijani_aware():
    assert normalize_text("İSMAYIL Əliyev") == normalize_text("ismayil eliyev") == "ismayil eliyev"
    assert normalize_text("Şəki, Gəncə!") == "seki gence"
    assert normalize_text("\u0430\u200bddım") == "addim"  # kiril «\u0430» + zero-width
    assert normalize_text("  A-B   c ") == "a b c"


def test_minhash_is_deterministic_and_stable():
    shingles = minhash.shingles(words_of(normalize_text(ESSAY_A)))
    assert minhash.signature(shingles) == minhash.signature(set(sorted(shingles)))
    assert len(minhash.signature(shingles)) == minhash.NUM_PERMUTATIONS
    assert minhash.hash64("alqoritm addimlar toplusu ve giris") == 2898683832067101959


def test_near_duplicate_is_flagged_for_both_sides(ready, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        original = _submit(ready, ready.students[0], text=ESSAY_A)
        copy = _submit(ready, ready.students[1], text=ESSAY_A_DISGUISED)
    original.refresh_from_db()
    copy.refresh_from_db()
    match = SimilarityMatch.objects.get()
    assert match.method == "shingle" and match.is_flagged and match.score >= 0.8
    assert match.detail["samples"] and match.detail["containment"] >= 0.8
    assert original.plagiarism_flagged and copy.plagiarism_flagged
    assert copy.plagiarism_status == "done" and copy.similarity_max == match.score
    assert copy.events.filter(kind="plagiarism_flagged").exists()


def test_unrelated_texts_do_not_match(ready):
    _check(_submit(ready, ready.students[0], text=ESSAY_A), _submit(ready, ready.students[1], text=ESSAY_B))
    assert not SimilarityMatch.objects.exists()
    assert not Submission.objects.filter(plagiarism_flagged=True).exists()


def test_partial_overlap_is_stored_but_not_flagged(ready):
    sentences_a = ESSAY_A.split(". ")
    sentences_b = ESSAY_B.split(". ")
    mixed = ". ".join(sentences_a[:5] + sentences_b[:4])  # olma payı ≈ 0.61
    one, two = _check(_submit(ready, ready.students[0], text=ESSAY_A), _submit(ready, ready.students[1], text=mixed))
    match = SimilarityMatch.objects.get()
    assert 0.5 <= float(match.score) < 0.8 and not match.is_flagged
    assert not one.plagiarism_flagged and not two.plagiarism_flagged


def test_identical_file_is_exact_match_but_teacher_template_is_not(ready):
    public.add_task_attachment(
        ready.homework, by_user=ready.teacher, file=upload("sablon.zip", _zip_bytes(), "application/zip")
    )
    template = [upload("sablon.zip", _zip_bytes(), "application/zip")]
    first, second = _check(
        _submit(ready, ready.students[0], files=template),
        _submit(ready, ready.students[1], files=[upload("sablon.zip", _zip_bytes(), "application/zip")]),
    )
    assert not SimilarityMatch.objects.exists()  # müəllimin öz şablonu «eyni fayl» sayılmır
    third_bytes = _zip_bytes(content=b"telebenin oz layihesi")
    one, two = _check(
        _submit(ready, ready.students[0], task=ready.slot1, files=[upload("x.zip", third_bytes, "application/zip")]),
        _submit(ready, ready.students[1], task=ready.slot1, files=[upload("y.zip", third_bytes, "application/zip")]),
    )
    match = SimilarityMatch.objects.get()
    assert match.method == "exact" and match.detail["kind"] == "file" and match.is_flagged
    assert one.plagiarism_flagged and two.plagiarism_flagged


def test_own_attempts_are_never_compared(ready):
    first = _submit(ready, ready.students[0], text=ESSAY_A)
    public.return_for_revision(first, by_user=ready.teacher, feedback="Mənbə əlavə edin")
    second = _submit(ready, ready.students[0], text=ESSAY_A)
    _check(first, second)
    assert not SimilarityMatch.objects.exists()


def test_copied_task_instructions_are_not_plagiarism(ready):
    public.update_task(ready.homework, by_user=ready.teacher, instructions=ESSAY_B)
    _check(
        _submit(ready, ready.students[0], text=ESSAY_B + " Mənim cavabım: iqlim kənd təsərrüfatına təsir edir."),
        _submit(ready, ready.students[1], text=ESSAY_B + " Cavab: neft sənayesi tarixən çox önəmlidir."),
    )
    assert not SimilarityMatch.objects.filter(is_flagged=True).exists()


def test_teacher_can_dismiss_a_flag(ready):
    one, two = _check(
        _submit(ready, ready.students[0], text=ESSAY_A), _submit(ready, ready.students[1], text=ESSAY_A_DISGUISED)
    )
    match = SimilarityMatch.objects.get()
    outsider = f.make_teacher(ready.org)
    with pytest.raises(public.FolderError):
        public.dismiss_match(match, by_user=outsider)
    public.dismiss_match(match, by_user=ready.teacher, note="Birgə layihədir")
    one.refresh_from_db()
    two.refresh_from_db()
    assert not one.plagiarism_flagged and not two.plagiarism_flagged and one.similarity_max is None
    public.restore_match(match, by_user=ready.teacher)
    one.refresh_from_db()
    assert one.plagiarism_flagged


def test_pdf_and_docx_text_is_extracted(ready):
    import docx
    import fitz

    pdf = fitz.open()
    page = pdf.new_page()
    # Base-14 PDF şrifti «ə/ş/ğ» qliflərini daşımır — mətn ASCII-yə qatlanmış formada yazılır;
    # normallaşdırma onsuz da ə→e, ş→s … edir, ona görə DOCX-dakı orijinal mətnlə eyni çıxmalıdır.
    page.insert_textbox(fitz.Rect(40, 40, 560, 800), normalize_text(ESSAY_A), fontsize=9)
    pdf_bytes = pdf.tobytes()
    document = docx.Document()
    for sentence in ESSAY_A.split(". "):
        document.add_paragraph(sentence)
    buffer = io.BytesIO()
    document.save(buffer)
    rows = _check(
        _submit(ready, ready.students[0], files=[upload("esse.pdf", pdf_bytes, "application/pdf")]),
        _submit(
            ready,
            ready.students[1],
            files=[
                upload(
                    "esse.docx",
                    buffer.getvalue(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ],
        ),
    )
    assert all(row.fingerprint.extracted_chars > 500 for row in rows)
    match = SimilarityMatch.objects.get()
    assert match.is_flagged and float(match.score) >= 0.8


def test_images_are_skipped_but_hashed(ready):
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    (row,) = _check(_submit(ready, ready.students[0], files=[upload("sekil.png", png, "image/png")]))
    assert row.fingerprint.skipped_files == [{"file": "sekil.png", "reason": "unsupported"}]
    assert len(row.fingerprint.file_hashes) == 1 and row.plagiarism_status == "done"


def test_other_organizations_are_never_compared(ready):
    org = f.make_org()
    teacher = f.make_teacher(org)
    offering = f.make_offering(org, subject=f.make_subject(org), period=f.make_period(org), instructor=teacher)
    student = f.make_student(org)
    f.enroll(offering, student)
    f.approve_syllabus(offering, teacher)
    folder, _c, _s = public.create_folder(
        organization=org, subject=offering.subject, owner=teacher, by_user=teacher, period=offering.period
    )
    assignment = public.assign_folder(folder, [offering], by_user=teacher)[0]["assignment"]
    homework = public.create_homework(folder, by_user=teacher, title="Ev", is_published=True)
    homework.lineage_key = ready.homework.lineage_key  # hətta eyni nəsil açarı ilə belə
    homework.save(update_fields=["lineage_key"])
    foreign = public.submit(task=homework, assignment=assignment, student=student, text=ESSAY_A)
    _check(_submit(ready, ready.students[0], text=ESSAY_A), foreign)
    assert not SimilarityMatch.objects.exists()
