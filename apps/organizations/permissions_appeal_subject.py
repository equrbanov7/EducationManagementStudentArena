"""Explicit read-only subject-chair appeal access; no decision or response grant."""

KEY = "appeal.view_subject"
ROLES = frozenset({"chair_head", "lab_assistant"})


def apply_subject_appeal_grants(roles):
    for role in roles:
        permissions = role.setdefault("permissions", [])
        if role.get("name") in ROLES and not any(key in permissions for key in (KEY, "appeal.*", "*")):
            permissions.append(KEY)
    return roles
