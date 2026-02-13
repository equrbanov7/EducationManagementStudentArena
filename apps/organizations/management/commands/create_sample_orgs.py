"""
Management command to create sample organizations for testing.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType

User = get_user_model()


class Command(BaseCommand):
    help = "Create sample organizations for testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default="admin",
            help="Username of the organization owner",
        )

    def handle(self, *args, **options):
        username = options["username"]

        # Get or create admin user
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@example.com",
                "is_staff": True,
                "is_superuser": True,
            },
        )

        if created:
            user.set_password("admin123")
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f"Created user: {username} (password: admin123)")
            )
        else:
            self.stdout.write(self.style.WARNING(f"Using existing user: {username}"))

        # Create University
        university, created = Organization.objects.get_or_create(
            slug="sample-university",
            defaults={
                "name": "Sample University",
                "org_type": OrganizationType.UNIVERSITY,
                "owner": user,
                "description": "A sample university for testing",
                "email": "info@sample-university.edu",
                "phone": "+1-555-0100",
                "address": "123 University Ave",
                "website": "https://sample-university.edu",
            },
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Created organization: {university.name}")
            )

            # Create some units
            faculty = OrgUnit.objects.create(
                organization=university,
                unit_type="faculty",
                name="Faculty of Computer Science",
                slug="cs-faculty",
                code="CS",
            )

            dept = OrgUnit.objects.create(
                organization=university,
                parent=faculty,
                unit_type="department",
                name="Software Engineering Department",
                slug="se-dept",
                code="SE",
            )

            # Assign user as rector
            rector_role = university.roles.filter(name="rector").first()
            if rector_role:
                Membership.objects.create(
                    user=user,
                    organization=university,
                    role=rector_role,
                    is_primary=True,
                )
                self.stdout.write(self.style.SUCCESS(f"Assigned {username} as rector"))
        else:
            self.stdout.write(
                self.style.WARNING(f"Organization already exists: {university.name}")
            )

        # Create School
        school, created = Organization.objects.get_or_create(
            slug="sample-school",
            defaults={
                "name": "Sample High School",
                "org_type": OrganizationType.SCHOOL,
                "owner": user,
                "description": "A sample high school for testing",
                "email": "info@sample-school.edu",
                "phone": "+1-555-0200",
                "address": "456 School St",
                "website": "https://sample-school.edu",
            },
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Created organization: {school.name}")
            )

            # Create some units
            section = OrgUnit.objects.create(
                organization=school,
                unit_type="section",
                name="Science Section",
                slug="science-section",
                code="SCI",
            )

            grade = OrgUnit.objects.create(
                organization=school,
                parent=section,
                unit_type="grade_level",
                name="Grade 10",
                slug="grade-10",
                code="G10",
            )

            # Assign user as director
            director_role = school.roles.filter(name="director").first()
            if director_role:
                Membership.objects.create(
                    user=user, organization=school, role=director_role
                )
                self.stdout.write(
                    self.style.SUCCESS(f"Assigned {username} as director")
                )
        else:
            self.stdout.write(
                self.style.WARNING(f"Organization already exists: {school.name}")
            )

        # Create Course Center
        center, created = Organization.objects.get_or_create(
            slug="sample-course-center",
            defaults={
                "name": "Sample Course Center",
                "org_type": OrganizationType.COURSE_CENTER,
                "owner": user,
                "description": "A sample course center for testing",
                "email": "info@sample-courses.com",
                "phone": "+1-555-0300",
                "address": "789 Learning Blvd",
                "website": "https://sample-courses.com",
            },
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Created organization: {center.name}")
            )

            # Create some units
            branch = OrgUnit.objects.create(
                organization=center,
                unit_type="branch",
                name="Downtown Branch",
                slug="downtown-branch",
                code="DT",
            )

            # Assign user as manager
            manager_role = center.roles.filter(name="manager").first()
            if manager_role:
                Membership.objects.create(
                    user=user, organization=center, role=manager_role
                )
                self.stdout.write(self.style.SUCCESS(f"Assigned {username} as manager"))
        else:
            self.stdout.write(
                self.style.WARNING(f"Organization already exists: {center.name}")
            )

        self.stdout.write(
            self.style.SUCCESS("\nSample organizations created successfully!")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"\nYou can now log in as '{username}' and switch between organizations."
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Visit /organizations/select/ to see your organizations."
            )
        )
