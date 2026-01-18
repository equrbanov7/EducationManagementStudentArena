from django.contrib.auth import get_user_model

User = get_user_model()

def _has_group(self, name: str) -> bool:
    return self.is_authenticated and self.groups.filter(name=name).exists()

User.add_to_class("is_teacher", property(lambda self: _has_group(self, "teacher")))
User.add_to_class("is_student", property(lambda self: _has_group(self, "student")))
User.add_to_class("is_assistant_teacher", property(lambda self: _has_group(self, "assistant_teacher")))
User.add_to_class("is_moderator", property(lambda self: _has_group(self, "moderator")))
