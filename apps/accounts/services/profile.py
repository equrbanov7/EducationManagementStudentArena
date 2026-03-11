"""
Profile-related services for accounts.
"""


def update_user_profile(user, **kwargs):
    """Update allowed profile fields and return the saved profile."""
    profile = user.profile
    allowed_fields = [
        "bio",
        "location",
        "website",
        "phone",
        "birthday",
        "linkedin_url",
        "github_url",
        "twitter_url",
        "student_id",
        "student_university_name",
        "student_school_identifier",
        "avatar",
    ]

    for field in allowed_fields:
        if field in kwargs:
            setattr(profile, field, kwargs[field])

    profile.save()
    return profile


def update_user_role(user, new_role, updated_by):
    """Update the user's profile role."""
    del updated_by

    profile = user.profile
    profile.role = new_role
    profile.save()
    return profile


__all__ = ["update_user_profile", "update_user_role"]
