"""
Role-based access control helpers.

Centralized RBAC logic for account views: resolving a user's profile roles,
computing per-user capabilities and allowed profile sections, and collecting
effective/grantable permissions. Keep tenant and permission checks strict.
"""

from ...models import ProfileRole
from ...policies import is_superadmin_user, permission_is_grantable, user_has_any_role
from .constants import PROFILE_ROLE_LABELS, PROFILE_ROLE_NAMES, PROFILE_ROLE_NAMES_MANAGEABLE
from .rbac_sections import apply_permission_section_gates
from .rbac_university_sections import university_role_sections
from .tenant import _bind_active_role_context


def _is_superadmin_user(user):
    return is_superadmin_user(user)


def _user_has_any_role(user, role_names):
    return user_has_any_role(user, role_names)


def _permission_is_grantable(permission, effective_permissions, grantable_permissions):
    return permission_is_grantable(permission, effective_permissions, grantable_permissions)


def _extract_profile_roles_for_user(user):
    if not user:
        return []

    active_organization = getattr(user, "active_organization", None)
    if active_organization is not None:
        _bind_active_role_context(
            user,
            active_organization,
            memberships=getattr(user, "_active_org_memberships", None),
        )

    roles = []
    if hasattr(user, "get_all_roles"):
        candidates = user.get_all_roles()
    else:
        candidates = []

    for role_name in candidates:
        if role_name in PROFILE_ROLE_NAMES and role_name not in roles:
            roles.append(role_name)

    return roles


def _assignable_profile_roles_for_user(user):
    if _is_superadmin_user(user):
        return [(name, display) for name, display in ProfileRole.CHOICES if name in PROFILE_ROLE_NAMES_MANAGEABLE]

    user_level = user._highest_role_level() if hasattr(user, "_highest_role_level") else 0
    return [
        (name, display)
        for name, display in ProfileRole.CHOICES
        if name in PROFILE_ROLE_NAMES_MANAGEABLE and ProfileRole.LEVELS.get(name, 0) < user_level
    ]


def _decorate_manage_role_profiles(profiles, *, actor_level, is_superadmin, organization=None, actor_user=None):
    actor_user_id = getattr(actor_user, "id", None)
    owner_self_management_enabled = bool(
        actor_user_id and organization is not None and getattr(organization, "owner_id", None) == actor_user_id
    )

    for profile in profiles:
        _bind_active_role_context(profile.user, organization)
        profile_user_is_superadmin = getattr(profile.user, "is_superuser", False) or getattr(
            profile.user, "is_superadmin", False
        )
        if profile_user_is_superadmin:
            current_roles = PROFILE_ROLE_NAMES_MANAGEABLE
        else:
            current_roles = _extract_profile_roles_for_user(profile.user)
        primary_role_name = None
        if current_roles:
            primary_role_name = max(current_roles, key=lambda role_name: ProfileRole.LEVELS.get(role_name, 0))
        profile.current_roles = current_roles
        profile.current_role_items = [
            {
                "name": role_name,
                "label": PROFILE_ROLE_LABELS.get(role_name, role_name),
                "level": ProfileRole.LEVELS.get(role_name, 0),
                "is_primary": role_name == primary_role_name,
            }
            for role_name in current_roles
        ]
        profile.primary_role = None
        if primary_role_name:
            profile.primary_role = {
                "name": primary_role_name,
                "label": PROFILE_ROLE_LABELS.get(primary_role_name, primary_role_name),
                "level": ProfileRole.LEVELS.get(primary_role_name, 0),
            }

        target_level = profile.user._highest_role_level() if hasattr(profile.user, "_highest_role_level") else 0
        is_self_profile = actor_user_id is not None and profile.user_id == actor_user_id
        profile.can_edit_roles = (
            is_superadmin or actor_level > target_level or (is_self_profile and owner_self_management_enabled)
        )


def _collect_actor_permissions(user, organization, *, request=None):
    """
    Return two sets:
    1. effective permissions user currently has in org
    2. explicitly grantable permissions declared as `grant:<permission>` in role permissions

    P1.4 — Per-request memoization (təhlükəsiz):
    Eyni request boyunca eyni (user_id, organization_id) cütü üçün təkrar
    DB sorğusu olmaması üçün nəticə `request._actor_perms_cache` dict-ində
    saxlanılır. Cross-request cache yoxdur — RLS və icazə dəyişiklikləri
    request başında həmişə yenidən qiymətləndirilir.
    """
    from apps.organizations.models import Membership

    user_id = getattr(user, "pk", None) or getattr(user, "id", None)
    org_id = getattr(organization, "pk", None) or getattr(organization, "id", None)
    cache_key = (user_id, org_id)
    cache_owner = request if request is not None else None
    if cache_owner is not None and user_id is not None and org_id is not None:
        cache = getattr(cache_owner, "_actor_perms_cache", None)
        if cache is None:
            cache = {}
            try:
                cache_owner._actor_perms_cache = cache
            except Exception:  # noqa: BLE001 — request obyekti immutable ola bilər
                cache_owner = None
        if cache_owner is not None and cache_key in cache:
            cached_effective, cached_grantable = cache[cache_key]
            # Cache-i mutasiya etməmək üçün surət qaytarırıq.
            return set(cached_effective), set(cached_grantable)

    effective_permissions = set()
    grantable_permissions = set()

    memberships = Membership.objects.filter(user=user, organization=organization, is_active=True).select_related("role")
    for membership in memberships:
        for permission in membership.role.permissions or []:
            if permission.startswith("grant:"):
                grantable_permissions.add(permission.split("grant:", 1)[1].strip())
            else:
                effective_permissions.add(permission)

    if cache_owner is not None and user_id is not None and org_id is not None:
        cache = getattr(cache_owner, "_actor_perms_cache", None)
        if cache is not None:
            cache[cache_key] = (set(effective_permissions), set(grantable_permissions))

    return effective_permissions, grantable_permissions


def _role_capabilities(user, profile):
    scoped_roles = _extract_profile_roles_for_user(user)
    profile_role = getattr(profile, "role", ProfileRole.MEMBER) if profile else ProfileRole.MEMBER
    active_organization = getattr(user, "active_organization", None)
    has_active_org_context = bool(scoped_roles or active_organization)
    role = scoped_roles[0] if scoped_roles else profile_role
    is_superadmin = _is_superadmin_user(user)
    is_student = _user_has_any_role(user, {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT})
    if not has_active_org_context and profile_role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
        is_student = True
    is_teacher = _user_has_any_role(user, {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER})
    is_owner_of_active_org = bool(
        active_organization is not None and getattr(active_organization, "owner_id", None) == user.id
    )
    # HR artıq org_admin-ə bərabər tutulmur — öz ayrıca səlahiyyət dəsti var
    # (üzv/vəzifə idarəetməsi, imtahan-kurs idarəetməsi YOX).
    is_org_admin = _user_has_any_role(user, {ProfileRole.ORG_ADMIN, ProfileRole.ORG_OWNER}) or is_owner_of_active_org
    is_hr = _user_has_any_role(user, {ProfileRole.HR})
    is_exam_center = _user_has_any_role(user, {"exam_center", "exam_center_head", "exam_center_staff"})
    is_lead_student = _user_has_any_role(user, {ProfileRole.LEAD_STUDENT})
    # Tyutor — qrup kurasiyası: öz unit alt-ağacındakı tələbə/kurs/statistika
    # görünüşü; imtahan-qiymətləndirmə-üzv idarəetməsi yoxdur. Proqram
    # koordinatoru eyni işi görür (tyutor-ekvivalent) — hər ikisi is_tutor ilə.
    is_program_coordinator = _user_has_any_role(user, {"program_coordinator"})
    is_tutor = _user_has_any_role(user, {"tutor"}) or is_program_coordinator
    # Dekan / kafedra müdürü — unit-scoped idarəetmə rolları.
    # (chair_head/section_head adları department_head-ə normallaşdırılır.)
    is_dean = _user_has_any_role(user, {"dean", "vice_dean"})
    is_department_head = _user_has_any_role(user, {"department_head"})
    is_unit_manager = is_dean or is_department_head
    user_level = 999 if is_superadmin else (user._highest_role_level() if hasattr(user, "_highest_role_level") else 0)

    can_manage_org = is_superadmin or is_org_admin
    # Final imtahan mərkəzi naviqasiyası: imtahan mərkəzi rolu HƏMİŞƏ, digər
    # istifadəçilər (məs. müəllim-nəzarətçi) yalnız təyin olunmuş oturumu varsa.
    # Yüngül .exists() sorğusu; icazə view/consumer qatında yenidən yoxlanır.
    can_access_final_center = is_exam_center or is_superadmin
    if not can_access_final_center and (is_teacher or is_tutor or is_unit_manager):
        from apps.exams.public import user_supervises_final_sessions

        can_access_final_center = user_supervises_final_sessions(user)
    # İmtahan zalı + kompüter/MAC idarəsi: superadmin, İKT Rəhbəri (rolun öz
    # tərifində `exam.*` var), YAXUD superadminin per-user bayraqla həvalə
    # etdiyi istifadəçi. Yalnız naviqasiya görünürlüyü; icazə view qatında
    # (``ensure_can_manage_exam_rooms``) EYNİ funksiya ilə yenidən yoxlanır —
    # ona görə nav ilə view arasında uyğunsuzluq yaranmır.
    from apps.exams.public import can_manage_exam_rooms as _can_manage_exam_rooms

    can_manage_exam_rooms = _can_manage_exam_rooms(user)
    # View qapısı ilə eyni permission-specific, fail-closed scope semantikası.
    if active_organization is not None:
        from apps.organizations.public import get_permission_scope

        can_manage_registrar = get_permission_scope(user, active_organization, "course.edit").is_org_wide
        # Semestr sonu TOPLU jurnal bağlama (RİM). Köhnə `grade.approve_chair` /
        # `grade.approve_final` cütünü əvəz edir — təsdiq zənciri ləğv olunub.
        can_close_journals = get_permission_scope(user, active_organization, "journal.close").has_structure_access
        # Jurnal siyahısının idarəsi (alt qrupdan tələbə əlavə/geri götürmə) —
        # koordinator/dekanlıq. Bu açarı daşıyan aktor jurnal iş sahəsinə çata
        # bilməlidir (əks halda düymə heç vaxt görünmür).
        can_manage_journal_roster = get_permission_scope(
            user, active_organization, "journal.roster"
        ).has_structure_access
        # Kağız (yazılı/praktiki) imtahan balının əl ilə daxil edilməsi — İmtahan
        # Mərkəzi səthi. Rol ADINDAN deyil, `final_score.entry` açarından gəlir.
        can_enter_exam_scores = get_permission_scope(
            user, active_organization, "final_score.entry"
        ).has_structure_access
        analytics_all_scope = get_permission_scope(user, active_organization, "analytics.view_all")
        analytics_unit_scope = get_permission_scope(user, active_organization, "analytics.view_unit")
        can_view_unit_analytics = analytics_all_scope.has_structure_access or analytics_unit_scope.has_structure_access
        # Kataloq axtarışı (⌘K, U8): struktur heyəti imzası — member.view + unit.view.
        # Burada QƏSDƏN scope (`get_permission_scope`) yox, rol icazəsi yoxlanır:
        # axtarış naviqasiya rahatlığıdır və scope_unit hələ təyin edilməmiş
        # dekan/kafedra müdiri onu itirməməlidir (təsdiq əməliyyatlarından fərqli).
        # Tək `member.view` kifayət etmir — lead_student/tutor da daşıyır; `unit.view`
        # cütlüyü auditoriyanı köhnə is_unit_manager dairəsinə yaxın saxlayır.
        from core.permissions import has_permission as _has_search_perm

        _actor_perms_all, _ = _collect_actor_permissions(user, active_organization)
        _actor_perm_list = list(_actor_perms_all)
        can_search_directory = is_superadmin or (
            _has_search_perm(_actor_perm_list, "member.view") and _has_search_perm(_actor_perm_list, "unit.view")
        )
    else:
        can_manage_registrar = can_close_journals = can_view_unit_analytics = False
        can_enter_exam_scores = False
        can_manage_journal_roster = False
        can_search_directory = False
    can_view_owned_learning = is_superadmin or is_teacher or is_org_admin or is_exam_center
    can_review_submissions = is_superadmin or is_teacher
    can_view_student_assignments = is_student or _user_has_any_role(user, {ProfileRole.MEMBER})
    can_manage_blog = getattr(user, "is_authenticated", False)
    can_approve_posts = is_superadmin or user_level >= ProfileRole.LEVELS.get(ProfileRole.TEACHER, 60)

    # Allow tenant admins to delegate either student-management or
    # invite-only access to teachers without elevating them to full admins.
    teacher_can_manage_students = False
    teacher_can_invite_members = False
    teacher_has_student_org_access = False
    if is_teacher and not is_org_admin and not is_superadmin and active_organization:
        from core.permissions import has_permission as _has_permission

        actor_perms, _ = _collect_actor_permissions(user, active_organization)
        teacher_can_manage_students = _has_permission(list(actor_perms), "member.student_manage")
        teacher_can_invite_members = _has_permission(list(actor_perms), "member.invite")
        teacher_has_student_org_access = teacher_can_manage_students or teacher_can_invite_members

    if is_superadmin:
        allowed_sections = {
            # «Ana səhifə» — kabinetin default açılış bölməsi (FAZA 22).  Rol
            # qapısı YOXDUR: panel özü yalnız icazəli bölmələrin vidjetlərini
            # yığır, ona görə görünürlük hər üzv üçün eynidir.
            "dashboard",
            "profile-info",
            "notifications",
            "posts",
            "my-results",
            "my-exams",
            "my-courses",
            "courses",
            "assigned-exams",
            "assigned-courses",
            "groups",
            "pending-review",
            "review-results",
            "role-assignment",
            "student-organization-management",
            "permission-editor",
            "manage-roles",
            "create-category",
            "category-management",
            "superadmin-org-features",
            "superadmin-org-inspector",
            "superadmin-organizations",
            "superadmin-users",
            "superadmin-ai",
            "superadmin-exam-rooms",  # imtahan zalı + kompüter/MAC idarəsi
            "exam-center-pins",  # PIN axtarışı (canlı search + inline detal)
            "exam-center-stats",  # imtahan statistikaları / nəticələr
            "appeal-stats",  # apellyasiya statistikası (imtahan mərkəzi)
            "kollokvium-windows",  # kollokvium bal-yazma pəncərələri (imtahan mərkəzi)
            "exam-score-entry",  # kağız imtahan balının daxil edilməsi (imtahan mərkəzi)
            "journal-close",  # semestr sonu toplu jurnal bağlaması (RİM)
            "exam-chance",  # imtahan şansı ver (ikinci şans — imtahan mərkəzi)
            "superadmin-contact-messages",  # public contact form inbox
            "system-monitoring",  # Sistem Monitorinqi (yalnız superadmin; server-side qorunur)
            "pending-post-approvals",
            "blog",
            "edit-profile",
            "change-password",
            "publish-notification",
            "delete-account",
            "statistics",
        }
    else:
        allowed_sections = {
            # bax yuxarıdakı şərh — «Ana səhifə» hər kəsdə var.
            "dashboard",
            "profile-info",
            "notifications",
            "posts",
            "blog",
            "edit-profile",
            "change-password",
            "delete-account",
            "statistics",
        }
        allowed_sections.add("my-results")
        if can_view_student_assignments:
            allowed_sections.add("pending-answers")

        # Superadminin həvalə etdiyi (bayraqlı) qeyri-superadmin zal idarəçisi:
        # öz aktiv təşkilatının zallarını idarə edə bilir (cross-org yalnız
        # superadminə açıqdır).
        if can_manage_exam_rooms:
            allowed_sections.add("superadmin-exam-rooms")

        if is_org_admin:
            allowed_sections.update(
                {
                    "my-exams",
                    "my-courses",
                    "groups",
                    "role-assignment",
                    "student-organization-management",
                    "permission-editor",
                    "manage-roles",
                    "publish-notification",
                }
            )

        if is_teacher:
            allowed_sections.update(
                {"my-exams", "my-courses", "groups", "pending-review", "review-results", "publish-notification"}
            )
            if teacher_has_student_org_access:
                allowed_sections.add("student-organization-management")

        # İmtahan mərkəzi — imtahan həyat dövrü: yaratma, qruplar, sual bankı,
        # apellyasiyalar, bildiriş dərci. Üzv/rol idarəetməsi YOXDUR.
        if is_exam_center:
            allowed_sections.update(
                {
                    "my-exams",
                    "groups",
                    "publish-notification",
                    "exam-center-pins",
                    "exam-center-stats",
                    "appeal-stats",
                    "kollokvium-windows",
                    "exam-chance",
                    # Mərkəzi rol → bütün tələbələrin akademik qeydlərini görür.
                    "academic-records",
                }
            )

        # HR — əməkdaş/üzv idarəetməsi və rol təyinatları. İmtahan/kurs YOXDUR.
        if is_hr:
            allowed_sections.update(
                {"student-organization-management", "role-assignment", "manage-roles", "publish-notification"}
            )

        if is_student:
            allowed_sections.update({"assigned-exams", "assigned-courses"})
            # Universitet rejimində tələbə öz akademik "Fənlərim" kabinetini görür
            # (kredit tərəqqisi + qayıb/imtahan statusu + qrup-seçmə blokları).
            from django.conf import settings as _dj_settings

            from apps.registrar import public as _registrar_public

            if getattr(_dj_settings, "UNIVERSITY_MODE", True):
                allowed_sections.add("my-subjects")
                allowed_sections.add("overall-academic")
                # Transkript rəsmi sənəddir — tələbə onu kabinetdən birbaşa
                # ALMIR, müraciət (ərizə) pəncərəsindən keçməlidir. Bayraq
                # bağlı ikən bölmə siyahıya DÜŞMÜR, ona görə həm sidebar,
                # həm də birbaşa `?section=my-transcript` / bölmə API-si
                # bağlanır (hər ikisi bu siyahıya baxır). PDF endpoint-i
                # eyni bayrağı ayrıca yoxlayır. Bax: registrar/public.py.
                if _registrar_public.STUDENT_TRANSCRIPT_SELF_SERVICE:
                    allowed_sections.add("my-transcript")

        # ADİ ÜZV səthləri: «Kurslarım», «Təyin edilmiş tapşırıqlar», qruplar.
        #
        # TARİXÇƏ (2026-07-31 auditi): bu qayda NEGATİV idi —
        # ``if not (is_student or is_teacher or is_org_admin)`` — yəni
        # «sadalanmayan hər kəs» alırdı: HR, imtahan mərkəzi, dekan, kafedra
        # müdiri, tyutor, İKT rəhbəri. Nəticədə əməkdaş menyusunda tələbə
        # bölmələri («Mənə təyin edilmiş imtahanlar») çıxırdı, ``groups`` isə
        # sidebar-da **«Müəllim»** qrup başlığının şərti olduğu üçün HR-ın
        # menyusunda «Müəllim» bölməsi görünürdü.
        #
        # İndi qayda müsbətdir və YALNIZ ``member`` roluna aiddir. Tələbə öz
        # bölmələrini yuxarıdakı ``if is_student`` blokundan alır — ona ``courses``
        # QƏSDƏN verilmir, əks halda «Kurslarım» sidebar-da iki dəfə çıxardı
        # (bax ``test_student_profile_keeps_single_assigned_courses_sidebar_entry``).
        # Matris: ``apps/accounts/tests/test_sidebar_role_matrix.py``.
        if _user_has_any_role(user, {ProfileRole.MEMBER}):
            allowed_sections.update({"courses", "assigned-exams", "assigned-courses", "groups"})

    # «Qruplar» bölməsi — permission-əsaslı görünürlük (rol bayraqlarına ƏLAVƏ,
    # mövcud is_org_admin/is_teacher qolları qalır). Permission-editordan hər
    # hansı rola verilmiş `group.view` / `group.manage` bölməni açır; faktiki
    # icazə view qatında (`exams.views.teacher.groups`) yenidən yoxlanılır.
    if "groups" not in allowed_sections and active_organization is not None:
        from core.permissions import has_permission as _groups_has_permission

        _groups_actor_perms, _ = _collect_actor_permissions(user, active_organization)
        _groups_perm_list = list(_groups_actor_perms)
        if _groups_has_permission(_groups_perm_list, "group.view") or _groups_has_permission(
            _groups_perm_list, "group.manage"
        ):
            allowed_sections.add("groups")

    has_admin_control_role = (
        _user_has_any_role(user, {ProfileRole.ORG_ADMIN, ProfileRole.ORG_OWNER}) or is_owner_of_active_org
    )

    if (
        profile_role
        in {
            ProfileRole.STUDENT,
            ProfileRole.LEAD_STUDENT,
            ProfileRole.TEACHER,
            ProfileRole.ASSISTANT_TEACHER,
            ProfileRole.MEMBER,
            ProfileRole.HR,
        }
        and not is_superadmin
        and not has_admin_control_role
    ):
        allowed_sections.add("student-organization-request")

    if can_manage_blog:
        allowed_sections.add("create-post")
    if can_approve_posts:
        allowed_sections.add("pending-post-approvals")

    # Rol-əsaslı universitet bölmələri (U12 kabineti + struktur menyusu) —
    # saf hesablama, bax `rbac_university_sections.university_role_sections`.
    allowed_sections |= university_role_sections(
        is_superadmin=is_superadmin,
        is_org_admin=is_org_admin,
        is_unit_manager=is_unit_manager,
        is_hr=is_hr,
        is_tutor=is_tutor,
        is_exam_center=is_exam_center,
        is_teacher=is_teacher,
        is_student=is_student,
        has_active_org_context=has_active_org_context,
        can_manage_journal_roster=can_manage_journal_roster,
        can_close_journals=can_close_journals,
        can_enter_exam_scores=can_enter_exam_scores,
        can_view_unit_analytics=can_view_unit_analytics,
    )
    # U16 — Kabinet modul görünürlüyü: superadminin söndürdüyü modulların
    # bölmələri allowed_sections-dan çıxarılır (sidebar + render + fragment API
    # eyni yerdən bağlanır).
    # U20: superadmin İSTİSNA DEYİL — bağlı modul heç kimə görünmür ("URL ilə
    # yazılsa da girməsin"). Superadmin modulu org-features panelindən açır;
    # panel bölməsi cabinet modullarına daxil deyil, ona görə kilidlənmə yoxdur.
    if active_organization is not None:
        from apps.organizations.cabinet_modules import disabled_sections as _disabled_cabinet_sections

        allowed_sections -= _disabled_cabinet_sections(active_organization)
    else:
        # Org konteksti yoxdursa modul DEFAULT-ları tətbiq olunur (postlar → gizli).
        from apps.organizations.cabinet_modules import default_disabled_sections as _default_disabled_sections

        allowed_sections -= _default_disabled_sections()

    # İmtahan sistemi redizaynı (Faza 5) — yeni modulların sidebar görünürlüyü.
    # Faktiki icazə yoxlaması yenə də view səviyyəsində (appeals.services.permissions,
    # _ensure_teacher) aparılır; bu flag-lar yalnız menyu görünürlüyü üçündür.
    can_use_question_bank = is_superadmin or is_teacher or is_org_admin or is_exam_center
    can_manage_appeals = is_superadmin or is_exam_center
    can_view_my_appeals = is_student or not (is_teacher or is_org_admin or is_exam_center or is_superadmin)

    # İcazə-qapılı bölmələr (audit / RİM / müəllim-tələbə kataloqu) TƏK yerdən:
    # bax `rbac_sections.apply_permission_section_gates` (yalnız GÖRÜNÜRLÜK).
    _permission_gates = apply_permission_section_gates(
        user,
        active_organization,
        allowed_sections,
        is_superadmin=is_superadmin,
        is_owner=is_owner_of_active_org,
    )

    # "Sual Bankı" profil sidebar bölməsi (sağda AJAX açılır) — görünürlük flag-ı ilə eyni şərt.
    if can_use_question_bank:
        allowed_sections.add("question-bank")

    # "Sual göndərişləri" — müəllim imtahan mərkəzinə sual göndərir, mərkəz
    # qutuda baxır. Hər iki tərəf eyni bölmə açarını görür (məzmun rola görə).
    if is_teacher or is_exam_center or is_superadmin:
        allowed_sections.add("question-submissions")

    # "Apellyasiyalarım" — tələbə (və ya org-a bağlı olmayan istifadəçi) öz
    # apellyasiyalarını dashboard daxilində (sağ content, AJAX) görür.
    if can_view_my_appeals:
        allowed_sections.add("my-appeals")

    # "Apellyasiyalar" (idarəetmə) — bütün müraciətlər imtahan mərkəzinə düşür.
    # Faktiki data scope-u və qərar icazəsi view səviyyəsində yenidən yoxlanılır.
    if can_manage_appeals:
        allowed_sections.add("manage-appeals")

    return {
        "role": role,
        "is_superadmin": is_superadmin,
        "is_student": is_student,
        "is_teacher": is_teacher,
        "is_org_admin": is_org_admin,
        "is_hr": is_hr,
        "is_exam_center": is_exam_center,
        "is_lead_student": is_lead_student,
        "is_tutor": is_tutor,
        "is_program_coordinator": is_program_coordinator,
        "is_dean": is_dean,
        "is_department_head": is_department_head,
        "is_unit_manager": is_unit_manager,
        # audit-log / rim-center / people-* bayraqları (bax rbac_sections).
        **_permission_gates,
        "can_use_question_bank": can_use_question_bank,
        "can_manage_appeals": can_manage_appeals,
        "can_view_my_appeals": can_view_my_appeals,
        "can_manage_org": can_manage_org,
        "can_manage_registrar": can_manage_registrar,
        "can_access_final_center": can_access_final_center,
        "can_manage_exam_rooms": can_manage_exam_rooms,
        # Grade-approval chain (U7.2): permission-scope əsaslı (yuxarıda hesablanır);
        # köhnə rol-əsaslı ifadə nav↔view uyğunsuzluğu yaradırdı.
        "can_close_journals": can_close_journals,
        "can_manage_journal_roster": can_manage_journal_roster,
        "can_enter_exam_scores": can_enter_exam_scores,
        "can_search_directory": can_search_directory,
        "can_view_owned_learning": can_view_owned_learning,
        "can_review_submissions": can_review_submissions,
        "can_view_student_assignments": can_view_student_assignments,
        "can_view_blog": True,
        "can_manage_blog": can_manage_blog,
        "can_approve_posts": can_approve_posts,
        "allowed_sections": allowed_sections,
        "teacher_can_manage_students": teacher_can_manage_students,
        "teacher_can_invite_members": teacher_can_invite_members,
        "teacher_has_student_org_access": teacher_has_student_org_access,
    }
