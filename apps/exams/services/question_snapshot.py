"""Delivered-question snapshot (EXAM-P0-03 tam versiya, re-audit §5.4).

Tələbəyə çatdırılan an sualın TAM görünüşü dondurulur — mətn, media referensi,
düzgün cavab, variant mətni/sırası/düzgünlüyü. Sonradan müəllif sualı redaktə
etsə də keçmiş cəhdin nəticəsi/appeal sübutu dəyişməz qalır. Nəticə/appeal
render-i mümkün olduqda bu snapshot-dan oxumalıdır.

Format v2 (geriyə-uyğun — v1 ``points/answer_mode/options[id,is_correct]``
oxuyan kod işləməyə davam edir; v2 həmin açarları saxlayır və üstünə əlavə
edir).
"""


def _option_snapshot(opt):
    return {
        "id": opt.id,
        "is_correct": bool(getattr(opt, "is_correct", False)),
        "text": getattr(opt, "text", "") or "",
        "label": getattr(opt, "label", "") or "",
    }


def build_question_snapshot(question, options=None):
    """Bir sualın tam çatdırılma snapshot-u (dict)."""
    if options is None:
        options = list(question.options.all())
    image = getattr(question, "image", None)
    video = getattr(question, "video", None)
    return {
        "v": 2,
        "points": int(getattr(question, "points", 1) or 1),
        "answer_mode": getattr(question, "answer_mode", "") or "",
        "text": getattr(question, "text", "") or "",
        "correct_answer": getattr(question, "correct_answer", "") or "",
        "image": image.name if image else "",
        "video": video.name if video else "",
        "options": [
            {
                "id": opt["id"] if isinstance(opt, dict) else opt.id,
                "is_correct": bool(opt["is_correct"]) if isinstance(opt, dict) else bool(opt.is_correct),
                **(
                    {"text": opt.get("text", ""), "label": opt.get("label", "")}
                    if isinstance(opt, dict)
                    else {"text": getattr(opt, "text", "") or "", "label": getattr(opt, "label", "") or ""}
                ),
            }
            for opt in options
        ],
    }


def delivered_question_view(answer):
    """Cavabın çatdırılma anındakı sual görünüşü (snapshot varsa ondan).

    Snapshot v2-dirsə mətn/media/variantlar dondurulmuş dəyərdən qaytarılır;
    əks halda (v1 və ya boş) canlı suala düşülür (geriyə-uyğunluq).
    """
    snapshot = getattr(answer, "question_snapshot", None)
    question = answer.question
    if isinstance(snapshot, dict) and snapshot.get("v") == 2:
        return {
            "text": snapshot.get("text", ""),
            "correct_answer": snapshot.get("correct_answer", ""),
            "image": snapshot.get("image", ""),
            "video": snapshot.get("video", ""),
            "points": snapshot.get("points", getattr(question, "points", 1)),
            "answer_mode": snapshot.get("answer_mode", getattr(question, "answer_mode", "")),
            "options": snapshot.get("options", []),
            "from_snapshot": True,
        }
    return {
        "text": getattr(question, "text", "") or "",
        "correct_answer": getattr(question, "correct_answer", "") or "",
        "image": question.image.name if getattr(question, "image", None) else "",
        "video": question.video.name if getattr(question, "video", None) else "",
        "points": getattr(question, "points", 1),
        "answer_mode": getattr(question, "answer_mode", "") or "",
        "options": [_option_snapshot(o) for o in question.options.all()],
        "from_snapshot": False,
    }


def _media_url(name):
    """Storage-relativ ad → tam URL (canlı `FieldFile.url` ilə eyni backend)."""
    if not name:
        return ""
    from django.core.files.storage import default_storage

    try:
        return default_storage.url(name)
    except (ValueError, NotImplementedError):
        return ""


def delivered_question_render(answer, selected_ids):
    """Nəticə/appeal template-i üçün dondurulmuş sual görünüşü.

    ``delivered_question_view``-nin üstünə media URL-lərini və hər variant üçün
    ``is_selected`` bayrağını (dondurulmuş seçimdən) əlavə edir ki, template
    canlı ``q.text``/``opt in ans.selected_options.all`` əvəzinə çatdırılma
    anındakı görünüşü render etsin. ``selected_ids`` — dondurulmuş (yoxdursa
    canlı) seçilmiş variant id-ləri.
    """
    from types import SimpleNamespace

    view = delivered_question_view(answer)
    options = [
        SimpleNamespace(
            id=opt["id"],
            text=opt.get("text", ""),
            label=opt.get("label", ""),
            is_correct=bool(opt.get("is_correct")),
            is_selected=opt["id"] in selected_ids,
        )
        for opt in view["options"]
    ]
    return SimpleNamespace(
        text=view["text"],
        correct_answer=view["correct_answer"],
        image_url=_media_url(view["image"]),
        video_url=_media_url(view["video"]),
        points=view["points"],
        answer_mode=view["answer_mode"],
        options=options,
        from_snapshot=view["from_snapshot"],
    )


__all__ = [
    "build_question_snapshot",
    "delivered_question_view",
    "delivered_question_render",
]
