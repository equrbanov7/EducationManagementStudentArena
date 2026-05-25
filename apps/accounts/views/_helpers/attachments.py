"""
Submission attachment extraction helper.

Normalizes the legacy single-file field and the modern ``files`` JSON list
into a single, de-duplicated list of ``{name, url}`` dicts.
"""

from pathlib import PurePosixPath


def _extract_assignment_attachments(submission):
    attachments = []
    seen_attachments = set()

    def _append_attachment(name, url):
        clean_name = (name or "").strip()
        clean_url = (url or "").strip()
        if not clean_url:
            return
        attachment_key = (clean_name, clean_url)
        if attachment_key in seen_attachments:
            return
        seen_attachments.add(attachment_key)
        attachments.append({"name": clean_name or PurePosixPath(clean_url).name, "url": clean_url})

    legacy_file = getattr(submission, "file", None)
    if legacy_file:
        _append_attachment(
            PurePosixPath(getattr(legacy_file, "name", "fayl")).name,
            getattr(legacy_file, "url", ""),
        )

    files_payload = getattr(submission, "files", None)
    if not isinstance(files_payload, list):
        return attachments

    def _normalize_url(candidate_url):
        if candidate_url.startswith(("http://", "https://", "/")):
            return candidate_url
        return f"/media/{candidate_url.lstrip('/')}"

    for item in files_payload:
        if isinstance(item, str):
            clean = item.strip()
            if clean:
                _append_attachment(PurePosixPath(clean).name, _normalize_url(clean))
            continue
        if not isinstance(item, dict):
            continue

        candidate_url = (item.get("url") or item.get("file") or item.get("path") or "").strip()
        if not candidate_url:
            continue
        candidate_name = (item.get("name") or item.get("filename") or "").strip()
        _append_attachment(candidate_name or PurePosixPath(candidate_url).name, _normalize_url(candidate_url))

    return attachments
