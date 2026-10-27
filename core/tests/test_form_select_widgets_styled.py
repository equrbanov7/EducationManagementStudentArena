"""Form widget-i ilə render olunan GÖRÜNƏN select-lər layihə komponentindədir (sahib 2026-10-27).

«Seçilmiş hər yerdə, filterdə search etmək olsun»: menyu-daxili axtarış
`static/js/bootstrap_select.js`-də DEFAULT açıqdır, amma yalnız komponentə
qoşulan select-lər üçün. Şablon qapısı (`test_no_native_selects.py`) yalnız
hərfi `<select>` teqlərini görür — `{{ form.field }}` ilə gələn widget-lər
ondan yayınırdı (əlaqə forması, şərh reytinqi, imtahan qrupu formu). Bu test
həmin widget-lərin atributlarını kilidləyir.
"""

from django.test import SimpleTestCase

from apps.blog.forms import CommentForm
from apps.contact.forms import ContactForm
from apps.exams.forms.group import StudentGroupForm


def _attrs(form_class, field):
    return form_class.base_fields[field].widget.attrs


class StyledSelectWidgetTests(SimpleTestCase):
    def assert_single(self, form_class, field):
        attrs = _attrs(form_class, field)
        self.assertIn("data-bootstrap-select", attrs, f"{form_class.__name__}.{field}")
        self.assertIn("bootstrap-single-select__native", attrs.get("class", ""), f"{form_class.__name__}.{field}")

    def test_contact_subject_uses_styled_select(self):
        self.assert_single(ContactForm, "subject")

    def test_comment_rating_uses_styled_select(self):
        self.assert_single(CommentForm, "rating")

    def test_student_group_single_selects_use_styled_select(self):
        self.assert_single(StudentGroupForm, "primary_teacher")
        self.assert_single(StudentGroupForm, "org_unit")

    def test_student_group_subjects_use_multi_select(self):
        self.assertIn("data-ems-multi-select", _attrs(StudentGroupForm, "subjects"))
