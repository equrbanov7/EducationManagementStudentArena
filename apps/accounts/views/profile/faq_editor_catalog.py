"""Apply tenant overrides while preserving each original guide's access gates."""

from dataclasses import dataclass

from apps.organizations.public import get_active_memberships, has_faq_video_editor_grant

from ...models import FaqVideoGuide
from .faq_catalog import BUILTIN_BY_KEY, Guide, media_metadata
from .faq_visibility import guide_allowed, required_capabilities, upload_allowed


def memberships(request):
    org = getattr(request, "organization", None)
    tenant_user = (getattr(org, "pk", None), request.user.pk)
    if getattr(request, "_faq_membership_subject", None) != tenant_user:
        request._faq_membership_subject = tenant_user
        request._faq_memberships = tuple(get_active_memberships(request.user, org)) if org else ()
    return request._faq_memberships


def can_manage_videos(request):
    if getattr(request, "is_view_as", False) or not getattr(request.user, "is_active", False):
        return False
    return has_faq_video_editor_grant(memberships(request))


@dataclass(frozen=True)
class TenantGuide(Guide):
    video_file: object = None
    subtitle_file: object = None
    chapter_rows: tuple = ()
    duration_seconds: float = 0
    omit_subtitles: bool = False
    original_start: float = 0

    @property
    def chapters(self):
        return self.chapter_rows

    @property
    def length(self):
        seconds = round(self.duration_seconds)
        return f"{seconds // 60}:{seconds % 60:02d}"

    @property
    def has_subtitles(self):
        return bool(self.subtitle_file or (self.video and not self.video_file and not self.omit_subtitles))

    @property
    def start(self):
        return self.original_start


def edited_entry(record, original):
    return TenantGuide(
        key=record.key,
        title=record.title,
        topic=record.topic,
        section=original.section if original else "",
        destination=original.destination if original else "",
        video=original.video if original else "",
        steps=tuple(record.steps),
        aliases=original.aliases if original else "",
        flags=original.flags if original else (),
        video_file=record.video_file or None,
        subtitle_file=record.subtitle_file or None,
        chapter_rows=tuple(record.chapters),
        duration_seconds=record.duration
        or (media_metadata().get(original.video, {}).get("duration", 0) if original else 0),
        omit_subtitles=record.omit_subtitles,
        original_start=original.start if original and not record.video_file else 0,
    )


def _visible(original, record, roles, sections, capabilities):
    if original and not guide_allowed(original, sections, capabilities):
        return None
    if not record:
        return original
    if record.hidden or (record.audience_roles and roles.isdisjoint(record.audience_roles)):
        return None
    if not upload_allowed(record, original, sections, capabilities, BUILTIN_BY_KEY):
        return None
    return edited_entry(record, original)


def _overlay_org(request):
    org = getattr(request, "organization", None)
    if org and org.is_active and org.status == "active" and (memberships(request) or org.owner_id == request.user.pk):
        return org
    return None


def list_entries(request, *, sections, capabilities):
    org = _overlay_org(request)
    records = {r.key: r for r in FaqVideoGuide.objects.filter(organization=org).order_by("-id")} if org else {}
    roles = {m.role.name for m in memberships(request)} if records else set()
    originals = BUILTIN_BY_KEY
    keys = [k for k in records if k not in originals]
    keys.extend(originals)
    return [
        guide
        for key in keys
        if (guide := _visible(originals.get(key), records.get(key), roles, sections, capabilities))
    ]


def resolve_entry(request, key, *, sections, capabilities=None, base_capabilities=None):
    org = _overlay_org(request)
    original = BUILTIN_BY_KEY.get(key)
    row = FaqVideoGuide.objects.filter(organization=org, key=key).first() if org else None
    roles = {m.role.name for m in memberships(request)} if row and row.audience_roles else set()
    if capabilities is None:
        if not original and not row:
            return None
        from .faq import faq_capabilities

        required = required_capabilities(original)
        if row and isinstance(row.required_guides, list):
            for operation in row.required_guides:
                if isinstance(operation, str):
                    required.update(required_capabilities(BUILTIN_BY_KEY.get(operation)))
        capabilities = faq_capabilities(request, base_capabilities, required=required)
    return _visible(original, row, roles, sections, capabilities)
