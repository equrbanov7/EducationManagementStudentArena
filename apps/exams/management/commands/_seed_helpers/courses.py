"""seed_group_demo_data — Kurs və kurs-məzmunu seed köməkçiləri."""

from apps.courses.models import Course, CourseGroup, CourseInstructor, CourseResource, CourseTopic


class CoursesSeedMixin:
    """Kurs və kurs-məzmunu seed köməkçiləri (Command tərəfindən MRO ilə istifadə olunur)."""

    def _ensure_course(self, organization, teacher):
        course, _ = Course.objects.get_or_create(
            owner=teacher,
            title=f"{organization.name} Demo Kursu",
            defaults={
                "description": f"{organization.name} üçün demo kurs.",
                "status": "published",
                "settings": {"seeded": True},
            },
        )
        update_fields = []
        if course.status != "published":
            course.status = "published"
            update_fields.append("status")
        if not course.settings:
            course.settings = {"seeded": True}
            update_fields.append("settings")
        if update_fields:
            course.save(update_fields=update_fields)
        return course

    def _seed_course_content(self, course, teachers, students, group_name):
        topic_specs = [
            ("Giriş və struktur", "Kursun məqsədi, qaydalar və ilkin materiallar.", 1),
            ("Əsas anlayışlar", "Mövzu üzrə baza nümunələr və izah.", 2),
            ("Praktiki tətbiq", "Real task və layihə əsaslı məşğələ.", 3),
        ]
        topics = []
        for title, description, order in topic_specs:
            topic, _ = CourseTopic.objects.get_or_create(
                course=course,
                order=order,
                defaults={"title": title, "description": description},
            )
            update_fields = []
            if topic.title != title:
                topic.title = title
                update_fields.append("title")
            if topic.description != description:
                topic.description = description
                update_fields.append("description")
            if update_fields:
                topic.save(update_fields=update_fields)
            topics.append(topic)

        for idx, topic in enumerate(topics, start=1):
            resource, _ = CourseResource.objects.get_or_create(
                course=course,
                topic=topic,
                title=f"{topic.title} - Material {idx}",
                defaults={
                    "description": "Demo dərs materialı",
                    "resource_type": "link",
                    "url": f"https://example.com/{course.slug}/topic-{idx}",
                },
            )
            update_fields = []
            if resource.resource_type != "link":
                resource.resource_type = "link"
                update_fields.append("resource_type")
            if not resource.url:
                resource.url = f"https://example.com/{course.slug}/topic-{idx}"
                update_fields.append("url")
            if update_fields:
                resource.save(update_fields=update_fields)

        for idx, teacher in enumerate(teachers, start=1):
            role = "primary" if idx == 1 else "assistant"
            instructor, _ = CourseInstructor.objects.get_or_create(
                course=course,
                user=teacher,
                defaults={
                    "role": role,
                    "permissions": {
                        "can_grade": True,
                        "can_edit": idx == 1,
                        "can_publish": idx == 1,
                    },
                },
            )
            update_fields = []
            if instructor.role != role:
                instructor.role = role
                update_fields.append("role")
            if not instructor.permissions:
                instructor.permissions = {
                    "can_grade": True,
                    "can_edit": idx == 1,
                    "can_publish": idx == 1,
                }
                update_fields.append("permissions")
            if update_fields:
                instructor.save(update_fields=update_fields)

        course_group, _ = CourseGroup.objects.get_or_create(
            course=course,
            name=f"{group_name} - Praktik Qrup",
            defaults={
                "schedule": {"day": "Monday", "time": "10:00", "room": "Lab-101"},
                "instructor": teachers[0],
                "max_students": max(30, len(students) + 5),
            },
        )
        group_update_fields = []
        if course_group.instructor_id != teachers[0].id:
            course_group.instructor = teachers[0]
            group_update_fields.append("instructor")
        if not course_group.schedule:
            course_group.schedule = {"day": "Monday", "time": "10:00", "room": "Lab-101"}
            group_update_fields.append("schedule")
        if course_group.max_students < len(students):
            course_group.max_students = len(students) + 5
            group_update_fields.append("max_students")
        if group_update_fields:
            course_group.save(update_fields=group_update_fields)
        course_group.members.set(students)
