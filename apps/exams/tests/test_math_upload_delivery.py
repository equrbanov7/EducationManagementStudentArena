"""Follow a teacher's math DOCX through preview, approval, bank, and student delivery."""

import io
import tempfile
from copy import deepcopy

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils.translation import override

import docx
from docx.opc.constants import CONTENT_TYPE, RELATIONSHIP_TYPE
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from lxml import etree
from PIL import Image, ImageDraw

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, QuestionSubmission, StudentGroup
from apps.exams.services.parsing.docx_reader import read_docx
from apps.exams.services.question_bank_attach import attach_bank_questions_to_exam
from apps.exams.services.question_chair_review import chair_approve
from apps.exams.services.question_snapshot import build_question_snapshot
from apps.exams.services.question_submission import accept_submission
from apps.exams.tests.test_exam_center_policy import _assign_user_to_org
from apps.exams.tests.test_question_submission import _Base
from apps.exams.tests.test_w3_import_docx import _FRACTION, _omath
from core.media_urls import protected_media_url

MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"


def math_sheet(*, picture_fallback=True, image_format="PNG"):
    document = docx.Document()
    question = document.add_paragraph("1. Qrafikdə x")
    question.add_run("2").font.superscript = True
    question.add_run(" və a")
    question.add_run("1").font.subscript = True
    question.add_run(" üçün hesablayın: ")
    question._p.append(_omath(_FRACTION))
    graph = Image.new("RGB", (121, 91), "white")
    draw = ImageDraw.Draw(graph)
    draw.line([(10, 5), (10, 80), (115, 80)], fill="black", width=2)
    draw.line([(12, 72), (40, 52), (70, 34), (105, 14)], fill="blue", width=3)
    media = io.BytesIO()
    graph.save(media, image_format)
    run = document.add_paragraph().add_run()
    run.add_picture(io.BytesIO(media.getvalue()))
    picture = run._r.find(f"{{{WORD}}}drawing")
    alternate = etree.SubElement(run._r, f"{{{MC}}}AlternateContent", nsmap={"c": CHART})
    choice = etree.SubElement(alternate, f"{{{MC}}}Choice", Requires="c")
    chart_drawing = deepcopy(picture)
    graphic_data = chart_drawing.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}graphicData")
    graphic_data.clear()
    graphic_data.set("uri", CHART)
    chart = etree.SubElement(graphic_data, f"{{{CHART}}}chart")

    chart_xml = f"""<c:chartSpace xmlns:c="{CHART}"><c:chart><c:plotArea>
        <c:lineChart><c:grouping val="standard"/><c:ser><c:idx val="0"/><c:order val="0"/>
        <c:val><c:numLit><c:ptCount val="2"/><c:pt idx="0"><c:v>1</c:v></c:pt>
        <c:pt idx="1"><c:v>2</c:v></c:pt></c:numLit></c:val></c:ser></c:lineChart>
        </c:plotArea></c:chart></c:chartSpace>"""
    part = Part(PackURI("/word/charts/chart1.xml"), CONTENT_TYPE.DML_CHART, chart_xml.encode(), document.part.package)
    chart.set(
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id",
        document.part.relate_to(part, RELATIONSHIP_TYPE.CHART),
    )
    choice.append(chart_drawing)
    if picture_fallback:
        etree.SubElement(alternate, f"{{{MC}}}Fallback").append(picture)
    else:
        run._r.remove(picture)
    document.add_paragraph("A) 0")
    option = document.add_paragraph("*B) ")
    option._p.append(_omath("<m:r><m:t>α</m:t></m:r><m:r><m:t>x</m:t></m:r>"))
    document.add_paragraph("C) 2")
    document.add_paragraph("D) 3")
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


class MathUploadDeliveryTests(_Base):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=self.media.name, MEDIA_ACCEL_REDIRECT_URL=""))
        self.client = self._client_for(self.teacher)
        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="Riyaziyyat")
        subject = self._subject(name="Riyaziyyat", code="MAT", group=group)
        self.form = dict(
            title="Riyaziyyat testi", group_id=str(group.pk), subject=str(subject.pk), exam_kind="quiz", language="az"
        )
        self.url = reverse("exams:question_submission_create")

    def upload(self, document, action="preview"):
        return self.client.post(
            self.url, {**self.form, "action": action, "upload_file": SimpleUploadedFile("test.docx", document)}
        )

    def test_answers_in_nested_word_table_appear_once(self):
        document = docx.Document()
        cell = document.add_table(rows=1, cols=1).cell(0, 0)
        cell.text = "1. Hesablayın"
        table = cell.add_table(rows=2, cols=2)
        options = ["*A) 1", "B) 2", "C) 3", "D) 4"]
        for cell, option in zip(table._cells, options):
            cell.text = option
        out = io.BytesIO()
        document.save(out)
        self.assertEqual(read_docx(out.getvalue()).text.splitlines(), ["1. Hesablayın", *options])

    def test_chart_without_picture_requires_visual_pdf(self):
        with override("az"), self.assertRaisesRegex(ValueError, "PDF"):
            read_docx(math_sheet(picture_fallback=False))
        response = self.upload(math_sheet(picture_fallback=False), action="save")
        self.assertContains(response, "PDF")
        self.assertFalse(QuestionSubmission.objects.filter(title=self.form["title"]).exists())

    def test_partial_equation_without_images_warns_teacher(self):
        document = docx.Document()
        paragraph = document.add_paragraph("1. Sual ")
        paragraph._p.append(_omath("<m:unknown><m:r><m:t>zz</m:t></m:r></m:unknown>"))
        for option in ("*A) 1", "B) 2", "C) 3", "D) 4"):
            document.add_paragraph(option)
        out = io.BytesIO()
        document.save(out)
        preview = self.upload(out.getvalue())
        warnings = [item["msg"] for item in preview.context["test_level_warnings"] if item["type"] == "import_source"]
        self.assertEqual(len(warnings), 1)
        self.assertContains(preview, warnings[0])

    def test_teacher_math_and_chart_reach_student(self):
        preview = self.upload(math_sheet(image_format="JPEG"))
        for formula in (r"\({}^{2}\)", r"\({}_{1}\)", r"\(\frac{a}{b}\)", r"\(\alpha x\)"):
            self.assertContains(preview, formula)
        token = preview.context["math_token"]
        preview_url = reverse("exams:question_import_visual_preview", args=[token, 0])
        image = self.client.get(preview_url)
        self.assertEqual(image.status_code, 200)
        with Image.open(io.BytesIO(image.content)) as picture:
            self.assertEqual(picture.format, "PNG")
            preview_pixels = picture.convert("RGB").tobytes()
        saved = self.client.post(
            self.url,
            {
                **self.form,
                "action": "save",
                "raw_text": preview.context["raw_text"],
                "math_token": token,
                "selected_indices": "1",
            },
        )
        self.assertEqual(saved.status_code, 302)
        submission = QuestionSubmission.objects.get(title=self.form["title"])
        chair_approve(submission, actor=self.chair_head)
        bank, count = accept_submission(submission, reviewer=self.exam_center)
        self.assertEqual(count, 1)
        exam = Exam.objects.create(
            title="Qrafik testi", author=self.teacher, organization=self.org, is_active=True, is_public=True
        )
        [question] = attach_bank_questions_to_exam(exam, [bank.library_questions.get().pk])
        student = get_user_model().objects.create_user("math_reader")
        _assign_user_to_org(student, self.org, ProfileRole.STUDENT, "student")
        attempt = ExamAttempt.objects.create(user=student, exam=exam, status="in_progress", attempt_number=1)
        options = list(question.options.all())
        self.assertEqual([opt.text for opt in options if opt.is_correct], [r"\(\alpha x\)"])
        ExamAnswer.objects.create(
            attempt=attempt, question=question, question_snapshot=build_question_snapshot(question, options)
        )
        student_client = self._client_for(student)
        page = student_client.get(reverse("exams:take_exam", args=[exam.slug, attempt.pk]))
        self.assertContains(page, r"\(\frac{a}{b}\)")
        self.assertContains(page, r"\(\alpha x\)")
        self.assertContains(page, "data-ems-math")
        image_url = protected_media_url(question.image)
        self.assertContains(page, image_url)
        image = student_client.get(image_url)
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image["Content-Type"], "image/jpeg")
        with Image.open(io.BytesIO(b"".join(image.streaming_content))) as picture:
            self.assertEqual(picture.convert("RGB").tobytes(), preview_pixels)
