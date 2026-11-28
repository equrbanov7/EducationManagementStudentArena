import re
from uuid import uuid4

from django import forms
from django.utils.translation import gettext_lazy as _

from core.roles import resolve_seeded_role_label

from .faq_catalog import GUIDES, media_metadata
from .faq_uploads import check_vtt, video_duration
from .faq_visibility import GENERAL


def chapter_text(chapters):
    lines = []
    for row in chapters:
        millis = round(float(row["start"]) * 1000)
        key = f"{millis // 60000:02}:{millis // 1000 % 60:02}"
        if millis % 1000:
            key += f".{millis % 1000:03}"
        lines.append(f"{key} {row['title']}")
    return "\n".join(lines)


def version(row):
    return f"{row.pk}:{row.revision}" if row else "0"


class GuideForm(forms.Form):
    version = forms.CharField(widget=forms.HiddenInput)
    create_token = forms.UUIDField(required=False, widget=forms.HiddenInput)
    title = forms.CharField(label=_("Sual və ya dərsin adı"), max_length=200)
    topic = forms.CharField(label=_("Mövzu"), max_length=120)
    audience = forms.MultipleChoiceField(
        label=_("Görə bilən rollar"),
        required=False,
        help_text=_(
            "Ən azı bir rol seçin. Dərsi hamıya göstərmək istəyirsinizsə, «Bütün rollar» seçimini ayrıca işarələyin."
        ),
        widget=forms.CheckboxSelectMultiple,
    )
    all_roles = forms.BooleanField(label=_("Bütün rollar"), required=False)
    required_guides = forms.MultipleChoiceField(
        label=_("Videoda göstərilən əməliyyatlar"),
        help_text=_(
            "Videonu yalnız seçdiyiniz bütün əməliyyatlara icazəsi olanlar görəcək. Ctrl və ya ⌘ ilə bir neçə əməliyyat seçə bilərsiniz."
        ),
        widget=forms.SelectMultiple(attrs={"size": 6}),
    )
    steps = forms.CharField(
        label=_("İzahın addımları"),
        max_length=12000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Hər addımı ayrıca sətirdə yazın."),
    )
    video = forms.FileField(
        label=_("MP4 video"),
        required=False,
        widget=forms.FileInput(attrs={"accept": "video/mp4,.mp4"}),
        help_text=_("Ən çox 200 MiB."),
    )
    subtitles = forms.FileField(
        label=_("Subtitrlər"),
        required=False,
        widget=forms.FileInput(attrs={"accept": ".vtt,text/vtt"}),
        help_text=_("İstəyə bağlı WebVTT faylı, ən çox 1 MB."),
    )
    omit_subtitles = forms.BooleanField(label=_("Mövcud subtitrləri çıxar"), required=False)
    chapters = forms.CharField(
        label=_("Fəsillərin başlanğıc vaxtları və adları"),
        max_length=200000,
        required=False,
        help_text=_("Hər fəsli ayrıca sətirdə yazın, məsələn 00:00 Giriş və 01:35 Nəticəni yoxlamaq."),
        widget=forms.Textarea(attrs={"rows": 5, "placeholder": "00:00 Giriş\n01:35 Nəticəni yoxlamaq"}),
    )

    def __init__(self, *args, org, row, original, **kwargs):
        self.creating = not (row or original)
        old_video = bool(row and row.video_file)
        self.duration = media_metadata().get(original.video, {}).get("duration", 0) if original else 0
        if old_video:
            self.duration = row.duration
        self.needs_video = not (old_video or (original and original.video))
        super().__init__(*args, **kwargs)
        operations = self.fields["required_guides"]
        operations.required = original is None
        operations.choices = [(GENERAL, _("Ümumi təlimat (əlavə əməliyyat icazəsi tələb etmir)"))] + sorted(
            ((guide.key, guide.title) for guide in GUIDES if not guide.key.startswith("tour-")),
            key=lambda pair: pair[1].casefold(),
        )
        if original:
            operations.help_text = _(
                "İlkin dərsin icazələri həmişə tətbiq olunur. Əlavə əməliyyat göstərirsinizsə, onu da seçin."
            )
        existing_roles = row.audience_roles if row else []
        active_roles = org.roles.filter(is_active=True).values_list("name", "display_name")
        choices = {name: resolve_seeded_role_label(name, label) for name, label in active_roles}
        for name in existing_roles:
            choices.setdefault(name, _("%(name)s (qeyri-aktiv rol)") % {"name": name})
        self.fields["audience"].choices = sorted(choices.items(), key=lambda item: str(item[1]).casefold())
        # A tombstone for an unmodified original contains only its key.
        effective = row if row and row.title else original
        self.previous_chapters = list(effective.chapters) if effective else []
        self.initial.update(
            version=version(row),
            create_token=uuid4() if self.creating else None,
            title=effective.title if effective else "",
            topic=effective.topic if effective else "",
            steps="\n".join(effective.steps) if effective else "",
            chapters=chapter_text(self.previous_chapters),
            audience=existing_roles,
            required_guides=row.required_guides if row else [],
            all_roles=bool((row or original) and not existing_roles),
        )

    def clean_required_guides(self):
        operations = self.cleaned_data["required_guides"]
        if GENERAL in operations and len(operations) > 1:
            raise forms.ValidationError(_("Ümumi təlimatı və ya videoda göstərilən əməliyyatları seçin."))
        return operations

    def clean_steps(self):
        return [line.strip() for line in self.cleaned_data["steps"].splitlines() if line.strip()]

    def clean_video(self):
        video = self.cleaned_data["video"]
        if video:
            self.duration = video_duration(video)
        elif self.needs_video:
            raise forms.ValidationError(_("Yeni dərs üçün MP4 video seçin."))
        return video

    def clean_chapters(self):
        chapters = []
        previous = {}
        if not self.cleaned_data.get("video"):
            previous = {(c["start"], c["title"]): c for c in self.previous_chapters}
        for line in self.cleaned_data["chapters"].splitlines():
            if not line.strip():
                continue
            match = re.fullmatch(r"(\d{1,4}):([0-5]\d)(?:\.(\d{1,3}))?\s+(.{1,180})", line.strip())
            if not match or len(chapters) >= 1000:
                raise forms.ValidationError(_("Hər fəsil üçün mm:ss və ad yazın. Ən çox 1000 fəsil əlavə olunur."))
            mins, sec, frac, title = match.groups()
            start_ms = (int(mins) * 60 + int(sec)) * 1000 + int((frac or "").ljust(3, "0"))
            start = start_ms / 1000
            if (chapters and start <= chapters[-1]["start"]) or start >= self.duration:
                raise forms.ValidationError(_("Fəsillər artan vaxt sırası ilə videonun müddəti daxilində olmalıdır."))
            title = title.strip()
            chapters.append(
                {**previous.get((start, title), {}), "start": start, "time": f"{int(mins)}:{sec}", "title": title}
            )
        return chapters

    def clean(self):
        data = super().clean()
        if "audience" in data and bool(data["audience"]) == bool(data.get("all_roles")):
            self.add_error("audience", _("Bir və ya bir neçə rol seçin, yaxud «Bütün rollar» seçimini təsdiqləyin."))
        if self.creating and not data.get("create_token"):
            self.add_error("create_token", _("Formanı yenidən açın."))
        if data.get("subtitles"):
            if data.get("omit_subtitles"):
                self.add_error(
                    "omit_subtitles", _("Yeni subtitr yükləyərkən mövcud subtitri çıxarma seçimini götürün.")
                )
            else:
                try:
                    check_vtt(data["subtitles"], self.duration)
                except forms.ValidationError as exc:
                    self.add_error("subtitles", exc)
        return data
