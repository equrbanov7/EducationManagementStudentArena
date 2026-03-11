"""
Script to seed test data for EMS Arena.
Placeholder for future implementation.
"""


def seed_data():
    """
    Seed test data for development.
    """
    print("ℹ️  Seed data script - Not yet implemented")
    # TODO: Implement data seeding logic


if __name__ == "__main__":
    import os

    import django

    if not os.environ.get("DJANGO_SETTINGS_MODULE"):
        raise RuntimeError("DJANGO_SETTINGS_MODULE must be set before running scripts/seed_data.py.")
    django.setup()
    seed_data()
