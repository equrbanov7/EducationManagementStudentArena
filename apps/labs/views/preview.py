"""
Labs Views - Preview Functionality
Randomizasiya önizləməsi
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import pgettext

from apps.courses.models import CourseMembership

from ..lab_assignment_service import get_lab_assignment_for_student
from ._helpers import _get_tenant_lab_or_404


@login_required
def preview_randomization(request, pk):
    """Randomizasiyanı önizlə"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        messages.error(request, pgettext("labs.view.permission", "permission_denied"))
        return redirect("courses:course_dashboard", pk=lab.course.id)

    # Kurs tələbələrini al

    memberships = CourseMembership.objects.filter(course=lab.course, role="student").select_related("user")

    # Seçilmiş tələbə
    selected_student_id = request.GET.get("student")
    selected_student = None
    questions = []

    if selected_student_id:
        try:
            membership = memberships.filter(user_id=selected_student_id).first()
            if membership:
                selected_student = membership.user

                # Bu tələbə üçün assignment yarat/al
                assignment = get_lab_assignment_for_student(lab, selected_student)
                questions = assignment.assigned_questions.all().order_by("block__order", "question_number")
        except Exception:
            pass

    context = {
        "lab": lab,
        "memberships": memberships,
        "selected_student": selected_student,
        "questions": questions,
    }

    return render(request, "labs/preview_randomization.html", context)
