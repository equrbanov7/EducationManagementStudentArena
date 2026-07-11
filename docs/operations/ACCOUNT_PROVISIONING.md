# Hesab provisioning modeli (e-universitet)

**Tarix:** 2026-07-04 · **Status:** public signup söndürülüb (default), rol-əsaslı provisioning

EMSArena elektron universitet platformasıdır (Qərbi Kaspi Universiteti və digər
dövlət universitetləri üçün). Real universitetlərin (UNEC, ADA, BDU, …) və
beynəlxalq təhsil-IAM praktikasının modelinə uyğun olaraq **son istifadəçilər
özləri qeydiyyatdan keçmir** — hesablar universitet administrasiyası tərəfindən
yaradılır və rollar təyin olunur.

Bu, standart universitet SIS (Student Information System) modelidir:
- **Admin-controlled provisioning** — hesablar özünü-xidmət deyil, admin
  tərəfindən yaradılır (kimlik təsdiqi əvvəldən).
- **RBAC (rol-əsaslı giriş)** — hər istifadəçi yalnız öz vəzifəsinə uyğun
  resurslara çıxır.
- **Least privilege + lifecycle** — onboarding → rol dəyişikliyi →
  deprovisioning; ən aşağı zəruri icazə.

İstinad: [Higher-ed account management best practice](https://www.lepide.com/blog/tips-to-securely-manage-user-accounts-in-higher-education/),
[UVA provisioning standard](https://security.virginia.edu/accounts-provisioning-and-deprovisioning-standard),
[User provisioning best practices 2026](https://www.techprescient.com/blogs/user-provisioning/).

---

## 1. Public signup söndürülüb

- **Flag:** `PUBLIC_SIGNUP_ENABLED` (`config/settings/components/security.py`),
  production default **OFF**. Env: `PUBLIC_SIGNUP_ENABLED`.
- Söndürüləndə `accounts:register` və `accounts:verify_code` login-ə yönləndirir
  ("Hesablar universitet administrasiyası tərəfindən yaradılır…" mesajı ilə).
- Navbar / footer / login / blog CTA-larındakı signup linkləri gizlənir
  (context processor `core.context_processors.feature_flags` →
  `public_signup_enabled`).
- Test settings (`config/settings/test.py`) flag-ı **ON** saxlayır ki, mövcud
  registration-flow testləri işləsin; ayrıca `PublicSignupDisabledTest` disabled
  yolunu yoxlayır.

---

## 2. Kim kimi yarada/təyin edə bilər (rol iyerarxiyası)

Rollar `apps/organizations/default_roles.py`-də, icazə yoxlaması
`apps/organizations/permissions.py` + RBAC-də. "Provisioning" = yeni üzv
əlavə etmək / rol təyin etmək / dəvət göndərmək.

| Provisioning edən | Kimi yarada/təyin edə bilər | İcazə (RBAC) | Scope |
|---|---|---|---|
| **Superadmin** (platform) | Təşkilatlar + təşkilat sahibi (rektor/direktor); istənilən rol | `*` | Platform (Django admin + superadmin panel) |
| **Rektor / Org Owner / Org Admin** | Prorektor, dekan, kafedra müdürü, HR, imtahan mərkəzi, müəllim, tələbə | `member.*`, `role.assign` | Bütün təşkilat |
| **Prorektor (vice_rector)** | Dekan, kafedra, müəllim, tələbə | `member.*` (org-scoped) | Bütün təşkilat |
| **HR** | Müəllim / əməkdaş (dəvət + vəzifə/kafedra təyinatı) | `member.invite/edit/remove`, `role.assign` | Bütün təşkilat (imtahan/kurs YOX) |
| **Dekan (dean/vice_dean)** | Müəllim, assistent, tələbə (öz fakültəsi alt-ağacı) | `member.invite/edit` (unit-scoped) | Öz unit alt-ağacı |
| **Kafedra müdürü (department_head)** | Müəllim, assistent (öz kafedrası) | `member.view` + delegasiya | Öz kafedrası |
| **İmtahan mərkəzi (exam_center)** | Provisioning YOX (yalnız imtahan həyat dövrü) | `exam.*`, `grade.*` | Org |
| **Müəllim (teacher)** | Standart olaraq YOX; delegasiya ilə öz kursuna tələbə | `member.student_manage` (delegasiya) | Öz kursu |
| **Tələbə / assistent / tyutor** | Provisioning YOX | — | — |

**Prinsip:** heç kim özündən yüksək və ya bərabər səviyyəli rol yarada/təyin edə
bilməz (`_assignable_profile_roles_for_user` → `ProfileRole.LEVELS < user_level`).
İcazə delegasiyası `grant:<permission>` ilə (bax `_collect_actor_permissions`).

---

## 3. Yeni hesab necə yaradılır (signup olmadan)

Mövcud infrastruktur:

1. **Superadmin → Django admin** (`/admin/`): brand-new `User` + `UserProfile` +
   `Membership` yaradır (istənilən rol). Platform səviyyəli onboarding.
2. **Dəvət (invitation)**: org admin / HR / dekan / delegasiyalı müəllim mövcud
   istifadəçini emailə görə tapıb dəvət edir
   (`apps/accounts/views/organization/_management_flow/_invites.py`;
   `Membership(is_active=False, title=STUDENT_PENDING_INVITE_TITLE)`). İstifadəçi
   profil → bildirişlər bölməsində qəbul edir
   (`student_org_invitation_action`).
3. **Seed command-ları** (demo/CI): `create_sample_orgs`, `seed_ci_e2e_user`,
   `seed_ci_e2e_scenario`, `seed_group_demo_data`.

---

## 4. Növbəti addımlar (tam SIS provisioning — gələcək)

Bu buraxılışda public signup söndürülüb və provisioning modeli sənədləşdirilib.
Tam SIS-üslubu onboarding üçün növbəti işlər (demo-dan sonra, ayrıca PR-lar):

- [ ] **Admin "hesab yarat" axını** — org admin / HR üçün brand-new user
  yaratma (müvəqqəti parol generasiyası + xoş-gəldin e-poçtu + ilk girişdə parol
  dəyişmə məcburiyyəti). Hazırda yalnız superadmin Django admin-dən edə bilir.
- [ ] **Toplu tələbə idxalı (CSV/Excel)** — registrar üçün qeydiyyat datasından
  toplu hesab yaratma (SIS inteqrasiyası nöqtəsi).
- [ ] **Deprovisioning** — məzuniyyət/xaric zamanı hesabın avtomatik deaktivi
  (lifecycle sonu).
- [ ] **SSO/LDAP** — universitetin mərkəzi kimlik provayderi ilə inteqrasiya
  (passwordless / federated login).

Hər biri auth-kritikdir; xarakteristik test + `-m postgres` RLS regressiya ilə
təhlükəsiz əlavə olunmalıdır.
