from django.db import transaction
from django.db.models.deletion import RestrictedError
from django.http import JsonResponse
from django.utils.translation import pgettext

from ...models import LabBlock, LabQuestion


@transaction.atomic
def delete_unused_questions(target):
    if isinstance(target, LabBlock):
        if not LabBlock.objects.select_for_update().filter(pk=target.pk).exists():
            return JsonResponse({"success": True})
        questions = target.questions.all()
    else:
        questions = LabQuestion.objects.filter(pk=target.pk)

    # Wait for an in-flight answer before Django collects rows for deletion.
    list(questions.order_by("pk").select_for_update().values_list("pk", flat=True))
    try:
        target.delete()
    except RestrictedError:
        return JsonResponse(
            {
                "success": False,
                "error": pgettext(
                    "labs.view.error", "This item contains a question with student answers and cannot be deleted."
                ),
            },
            status=409,
        )
    return JsonResponse({"success": True})
