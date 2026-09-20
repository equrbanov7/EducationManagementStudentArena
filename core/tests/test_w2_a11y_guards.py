"""Dalğa 2 (2026-09-14) əlçatanlıq qoruyucuları — audit FE-F15/F17/F18/F19/F21.

Statik (SimpleTestCase) yoxlamalar — brauzer yoxdur, amma reqressiya sinifləri
ucuz tutulur:

* FE-F19 — `apps/**/static/**/*.js` və `static/js/**/*.js`-də native `confirm()`
  YALNIZ açıq siyahıdakı fayllarda qala bilər (EMSConfirm-in öz ehtiyat yolu,
  tələbə imtahan JS-i — sahib qaydası: toxunulmur). Qalan hər yer
  `EMSConfirm.open(...)` işlətməlidir (vahid dialoq, ləğv = sorğu yoxdur).
* FE-F18 — düzəldilən CSS fayllarında `outline: none/0` yalnız eyni qaydada
  və ya dərhal ardınca gələn qaydada görünən fokus əvəzi (`box-shadow` /
  `border-color` / `outline:` qeyri-sıfır) olduqda qalır (WCAG 2.4.7).
* FE-F15 — auth şablonlarında xəta blokları `role="alert"` və Django 5.2-nin
  `aria-describedby="<auto_id>_error"`-ına uyğun `id` daşıyır.
* FE-F17 — audit siyahısındakı ikon-only düymələr `aria-label` daşıyır.
* FE-F21 — `create_combo.js` `box()` `closest`-i qoruyur.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

BASE = Path(settings.BASE_DIR)

# Native `confirm(` / `window.confirm(` — `EMSConfirm.open(`, `.confirm(`,
# `openConfirm(`, `confirmDelete(` və s. tutulmur.
_NATIVE_CONFIRM = re.compile(r"(?<![\w.$])(?:window\.)?confirm\(")

# FE-F19: qalmasına icazə verilən fayllar (səbəbi ilə).
CONFIRM_ALLOWLIST = {
    "static/js/ems_confirm.js": "EMSConfirm-in özü — bootstrap yoxdursa ehtiyat yolu",
    "apps/accounts/static/accounts/js/superadmin_exam_rooms.js": "EMSConfirm yoxdursa ehtiyat yolu (Promise.resolve)",
    "apps/exams/static/exams/js/coding_exam/ui.js": "tələbə imtahan JS-i — modal yoxdursa ehtiyat yolu (toxunulmur)",
    "apps/exams/static/exams/js/final_center/waiting_room.js": "tələbə imtahan JS-i (toxunulmur)",
    "apps/accounts/static/accounts/js/profile/applications_dialogs.js": "lokal `function confirm(title, text, onYes)` — native deyil",
}

# FE-F18: `outline:none` qalıqlarına baxılan fayllar.
OUTLINE_FILES = [
    "apps/registrar/static/registrar/css/jd2.css",
    "static/css/ems_ui/table.css",
    "apps/accounts/static/accounts/css/profile/sections/people_directory.css",
    "apps/accounts/static/accounts/css/profile/sections/permission_editor_ui.css",
    "apps/accounts/static/accounts/css/profile/sections/teaching_office_plan.css",
    "apps/accounts/static/accounts/css/profile/sections/roles_ui.css",
    "apps/accounts/static/accounts/css/profile/sections/teaching_handover.css",
]

_OUTLINE_NONE = re.compile(r"outline\s*:\s*(?:none|0)(?:px)?\s*(?:!important)?\s*;")
_FOCUS_REPLACEMENT = re.compile(r"box-shadow\s*:|border(?:-color)?\s*:|outline\s*:\s*(?!none|0\b)")


def _strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))


class NativeConfirmGuardTest(SimpleTestCase):
    def _js_files(self):
        roots = [BASE / "static" / "js", *BASE.glob("apps/*/static")]
        for root in roots:
            for path in sorted(root.rglob("*.js")):
                rel = str(path.relative_to(BASE))
                if "/vendor/" in rel or "node_modules" in rel:
                    continue
                yield rel, path

    def test_native_confirm_only_in_allowlist(self):
        offenders = {}
        for rel, path in self._js_files():
            text = _strip_comments(path.read_text(encoding="utf-8", errors="ignore"))
            hits = [m.start() for m in _NATIVE_CONFIRM.finditer(text)]
            if hits and rel not in CONFIRM_ALLOWLIST:
                lines = sorted({text.count("\n", 0, h) + 1 for h in hits})
                offenders[rel] = lines
        self.assertEqual(
            offenders,
            {},
            "native confirm() qalıb — EMSConfirm.open({...}).then(ok => …) işlədin "
            f"(və ya CONFIRM_ALLOWLIST-ə səbəblə əlavə edin): {offenders}",
        )

    def test_allowlist_entries_still_exist_and_still_need_it(self):
        # Siyahı boşa çıxmasın: fayl silinibsə və ya artıq confirm() yoxdursa
        # siyahıdan çıxarılmalıdır ki, qoruyucu «yalançı icazə» saxlamasın.
        stale = []
        for rel in CONFIRM_ALLOWLIST:
            path = BASE / rel
            if not path.exists():
                stale.append(rel)
                continue
            text = _strip_comments(path.read_text(encoding="utf-8", errors="ignore"))
            if not _NATIVE_CONFIRM.search(text):
                stale.append(rel)
        self.assertEqual(stale, [], f"CONFIRM_ALLOWLIST köhnəlib: {stale}")

    def test_converted_files_use_emsconfirm(self):
        # FE-F19 siyahısından nümunə fayllar — vahid dialoq həqiqətən çağırılır.
        for rel in [
            "apps/accounts/static/accounts/js/profile/workload_distribution.js",
            "apps/accounts/static/accounts/js/profile/teaching_office.js",
            "apps/accounts/static/accounts/js/profile/org_units.js",
            "apps/accounts/static/accounts/js/profile/student_intake.js",
            "apps/accounts/static/accounts/js/profile/legacy_grade_review_actions.js",
            "apps/accounts/static/accounts/js/journal_close.js",
            "static/js/csp_event_handlers.js",
        ]:
            text = (BASE / rel).read_text(encoding="utf-8")
            self.assertIn("EMSConfirm.open(", text, rel)


class SuperadminRejectConfirmTest(SimpleTestCase):
    def test_reject_button_requires_confirmation(self):
        # FE-F19: «Rədd et» səbəb sahəsi ilə birbaşa submit idi.
        tpl = BASE / "apps/accounts/templates/accounts/partials/_superadmin_organizations_content.html"
        text = tpl.read_text(encoding="utf-8")
        reject = re.search(r'<button[^>]*value="reject"[^>]*>', text, flags=re.S)
        self.assertIsNotNone(reject)
        self.assertIn("data-ems-confirm=", reject.group(0))
        handler = (BASE / "static/js/csp_event_handlers.js").read_text(encoding="utf-8")
        self.assertIn("[data-ems-confirm]", handler)


class OutlineNoneGuardTest(SimpleTestCase):
    def test_outline_none_has_visible_focus_replacement(self):
        offenders = []
        for rel in OUTLINE_FILES:
            text = _strip_comments((BASE / rel).read_text(encoding="utf-8"))
            for match in _OUTLINE_NONE.finditer(text):
                # Eyni qayda: əvvəlki `{`-dən sonrakı `}`-ə qədər.
                rule_start = text.rfind("{", 0, match.start())
                rule_end = text.find("}", match.end())
                same_rule = text[rule_start:rule_end]
                # Dərhal ardınca gələn qayda (məs. `.x:focus-within { box-shadow … }`).
                next_rule_end = text.find("}", rule_end + 1)
                next_rule = text[rule_end + 1 : next_rule_end if next_rule_end > 0 else None]
                if not (_FOCUS_REPLACEMENT.search(same_rule) or _FOCUS_REPLACEMENT.search(next_rule)):
                    line = text.count("\n", 0, match.start()) + 1
                    offenders.append(f"{rel}:{line}")
        self.assertEqual(offenders, [], f"`outline:none` görünən fokus əvəzi olmadan: {offenders}")

    def test_jd2_filter_focus_is_visible(self):
        text = (BASE / "apps/registrar/static/registrar/css/jd2.css").read_text(encoding="utf-8")
        self.assertIn(".jd2-filter:focus-within", text)
        self.assertIn(".jd2-filter-search:focus-visible", text)


class AuthErrorMarkupTest(SimpleTestCase):
    def test_login_errors_are_announced_and_linked(self):
        text = (BASE / "apps/accounts/templates/accounts/login.html").read_text(encoding="utf-8")
        self.assertIn('class="auth-global-errors" role="alert"', text)
        self.assertIn('id="{{ form.username.auto_id }}_error"', text)
        self.assertIn('id="{{ form.password.auto_id }}_error"', text)

    def test_password_reset_and_otp_errors(self):
        reset = (BASE / "apps/accounts/templates/accounts/password_reset.html").read_text(encoding="utf-8")
        self.assertIn('id="{{ form.email.auto_id }}_error"', reset)
        self.assertIn('role="alert"', reset)
        confirm = (BASE / "apps/accounts/templates/accounts/password_reset_confirm.html").read_text(encoding="utf-8")
        for field in ("otp_code", "new_password1", "new_password2"):
            self.assertIn(f'id="{{{{ form.{field}.auto_id }}}}_error"', confirm)
        self.assertIn('id="{{ form.new_password1.auto_id }}_helptext"', confirm)
        otp = (BASE / "templates/admin/verify_otp.html").read_text(encoding="utf-8")
        self.assertIn('id="{{ form.code.auto_id }}_error"', otp)
        self.assertIn('role="alert"', otp)
        for rel in ("verify_code.html", "first_login_set_password.html"):
            text = (BASE / "apps/accounts/templates/accounts" / rel).read_text(encoding="utf-8")
            self.assertIn("role=\"{% if 'error' in message.tags %}alert{% else %}status{% endif %}\"", text, rel)


class IconOnlyButtonNamesTest(SimpleTestCase):
    # FE-F17 siyahısı: (şablon, düyməni tanıdan fraqment)
    CASES = [
        # assignments/review.html 2026-09-20 silindi (istinadsız ölü şablon).
        ("apps/exams/templates/exams/teacher/teacher_group_list.html", "jsOpenEditGroup"),
        ("apps/exams/templates/exams/teacher/teacher_group_list.html", "jsConfirmDeleteGroup"),
        ("apps/exams/templates/exams/teacher/teacher_group_list.html", 'id="deleteBtn"'),
        ("apps/labs/templates/labs/manage_blocks.html", "js-edit-question"),
        ("apps/labs/templates/labs/manage_blocks.html", "js-delete-question"),
        ("apps/accounts/templates/accounts/assigned_exams.html", 'type="submit" class="btn btn-primary"'),
        ("apps/accounts/templates/accounts/assigned_exams.html", "data-close-exam-code-modal"),
        ("apps/accounts/templates/accounts/assigned_courses.html", 'type="submit" class="btn btn-primary"'),
        ("apps/assignments/templates/assignments/assignment_detail.html", 'id="clearFile"'),
        ("apps/live_exam/templates/liveExam/host_lobby.html", 'id="closePodiumBtn"'),
        ("apps/courses/templates/courses/course_members.html", "btn-icon-delete"),
        ("apps/courses/templates/courses/partials/_member_accordion.html", "js-delete-member"),
        ("apps/accounts/templates/accounts/profile/sections/_post_edit_modal.html", 'id="closeEditModal"'),
        (
            "apps/accounts/templates/accounts/profile/sections/superadmin/_superadmin_contact_messages.html",
            'class="contact-msg-search"',
        ),
        (
            "apps/accounts/templates/accounts/partials/_student_org_request_content.html",
            'type="submit" class="btn btn-primary"',
        ),
    ]

    @staticmethod
    def _button_tag_for(text, marker):
        """Marker-i əhatə edən `<button …>` teqi; marker düymə teqində deyilsə
        (məs. axtarış formunun class-ı) — markerdən sonrakı ilk düymə."""
        idx = text.find(marker)
        if idx == -1:
            return None
        start = text.rfind("<button", 0, idx)
        end = text.find(">", start) if start != -1 else -1
        if start == -1 or end < idx:
            start = text.find("<button", idx)
            end = text.find(">", start)
        return text[start:end]

    def test_icon_only_buttons_have_aria_label(self):
        missing = []
        for rel, marker in self.CASES:
            text = (BASE / rel).read_text(encoding="utf-8")
            tag = self._button_tag_for(text, marker)
            self.assertIsNotNone(tag, f"{rel}: {marker!r} tapılmadı")
            if "aria-label=" not in tag:
                missing.append(f"{rel} ({marker})")
        self.assertEqual(missing, [], f"aria-label-sız ikon düymələr: {missing}")


class CreateComboClosestGuardTest(SimpleTestCase):
    def test_box_guards_closest(self):
        text = (BASE / "apps/accounts/static/accounts/js/rim_center/create_combo.js").read_text(encoding="utf-8")
        self.assertIn('typeof el.closest === "function"', text)


class AuthErrorRenderTest(TestCase):
    """FE-F15 — real render: Django 5.2 xətalı sahəyə `aria-invalid` +
    `aria-describedby="<auto_id>_error"` yazır; şablon həmin `id`-li xəta
    elementini və `role="alert"` blokunu verməlidir."""

    def test_login_field_error_is_linked_to_input(self):
        response = self.client.post(reverse("accounts:login"), {"username": "", "password": ""})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('aria-invalid="true"', html)
        self.assertRegex(html, r'aria-describedby="id_username_error"')
        self.assertRegex(html, r'id="id_username_error"')

    def test_login_bad_credentials_is_announced(self):
        response = self.client.post(reverse("accounts:login"), {"username": "nobody.here", "password": "wrong-pass"})
        self.assertEqual(response.status_code, 200)
        self.assertIn('class="auth-global-errors" role="alert"', response.content.decode())

    def test_password_reset_invalid_email_is_linked(self):
        response = self.client.post(reverse("accounts:password_reset"), {"email": "not-an-email"})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertRegex(html, r'aria-describedby="id_email_error"')
        self.assertRegex(html, r'id="id_email_error" role="alert"')
