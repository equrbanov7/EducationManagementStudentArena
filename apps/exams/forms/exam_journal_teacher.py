"""İmtahan formasının «Müəllim (jurnal)» sahəsi — müəllim → fənn asılı seçimi (sahib 2026-10-24).

Yaradan əvvəl MÜƏLLİMİ seçir; fənn siyahısı (``exams:journal_teacher_subjects``) onun cari dövrdə
tədris etdiyi fənlərə daralır. Müəllim boşdursa bütün fənlər (əvvəlki kimi). Server avtoritetdir:
müəllim + fənn birlikdə dəyişibsə fənnin həmin müəllimin fənni olduğu burada yoxlanılır (klientin
süzgəci yan keçilə bilər). Bağlantının özü (hər qrupun jurnal açılışı) ``services.exam_journal_link``-dədir.
"""

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import pgettext_lazy

from apps.organizations.public import organization_role_user_queryset
from core.roles import ProfileRole

User = get_user_model()

#: Jurnal sahibi ola bilən rollar (``bank_teacher_search`` seçicisi ilə EYNİ dəst).
JOURNAL_TEACHER_ROLES = {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}


def journal_teacher_queryset(organization, *, include_id=None):
    """Təşkilatın aktiv müəllimləri (+ redaktədə mövcud dəyər, rolu sonradan dəyişsə də)."""
    if organization is None:
        base = User.objects.none()
    else:
        base = organization_role_user_queryset(
            organization, JOURNAL_TEACHER_ROLES, queryset=User.objects.filter(is_active=True)
        )
    condition = Q(pk__in=base.values("pk"))
    if include_id:
        condition |= Q(pk=include_id)
    return User.objects.filter(condition).order_by("first_name", "last_name", "username")


class JournalTeacherFieldMixin(forms.Form):
    journal_teacher = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label=pgettext_lazy("exams.form.exam.label", "Müəllim (jurnal)"),
        help_text=pgettext_lazy(
            "exams.form.exam.help",
            "Müəllimi seçsəniz, fənn siyahısı onun cari dövrdə tədris etdiyi fənlərlə məhdudlaşır və "
            "midterm nəticəsi həmin fənnin qrup jurnallarına yazılır. Boş qalarsa bütün fənlər göstərilir.",
        ),
        widget=forms.Select(attrs={"class": "d-none", "data-exam-teacher-native": ""}),
    )

    def _init_journal_teacher(self, organization):
        field = self.fields.get("journal_teacher")
        if field is not None:
            field.queryset = journal_teacher_queryset(
                organization, include_id=getattr(self.instance, "journal_teacher_id", None)
            )

    def journal_teacher_selected(self):
        """Şablon üçün seçili müəllim ``{"id", "text"}`` (bağlı formada göndərilən, redaktədə mövcud) və ya ``None``."""
        field = self.fields.get("journal_teacher")
        value = self["journal_teacher"].value() if field is not None else None
        if not value or not str(value).isdigit():
            return None
        user = field.queryset.filter(pk=int(value)).first()
        if user is None:
            return None
        return {"id": user.pk, "text": user.get_full_name() or user.username}

    def _clean_journal_link(self, cleaned_data):
        teacher = cleaned_data.get("journal_teacher")
        subject = cleaned_data.get("subject")
        organization = getattr(self, "_organization", None) or cleaned_data.get("organization")
        if teacher is None or subject is None or organization is None:
            return
        instance = getattr(self, "instance", None)
        if instance is not None and instance.pk:
            if instance.journal_teacher_id == teacher.pk and instance.subject_id == subject.pk:
                return  # dəyişməyib — keçmiş dövrün imtahanı redaktədə sınmasın
        from apps.registrar.public import exam_journal_link

        if subject.pk not in exam_journal_link.teacher_subject_ids(organization, teacher):
            self.add_error(
                "subject",
                pgettext_lazy("exams.form.exam.error", "Seçilmiş müəllim bu fənni cari dövrdə tədris etmir."),
            )


__all__ = ["JOURNAL_TEACHER_ROLES", "JournalTeacherFieldMixin", "journal_teacher_queryset"]
