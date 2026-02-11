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

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    django.setup()
    seed_data()
