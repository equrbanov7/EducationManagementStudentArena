# View-as (rollararası baxış) — rejim modeli

Bu sənəd «başqa istifadəçinin adından işləmək» (impersonation) səlahiyyətinin
kimə, hansı həcmdə verildiyini və qərarların **niyə** belə olduğunu qeyd edir.
2026-07-31 auditindən sonra yazılıb.

## Qayda

> Başqa rolun səhifəsinə **dəyişiklik səlahiyyəti** ilə yalnız **İmtahan Mərkəzi**
> və **İKT Mərkəzi** girə bilər. Bütün digər icazəli rollar **yalnız-oxu** alır.
> İmtahan Mərkəzinin dəyişikliyi imtahan əməliyyatları ilə, İKT Mərkəzinin
> dəyişikliyi isə texniki dəstək və **açıq şəkildə icazə verilmiş** sistem
> əməliyyatları ilə məhdudlaşır. Heç biri avtomatik olaraq bütün məxfi akademik,
> HR və şəxsi məlumatlara məhdudiyyətsiz giriş almır.

## Rejimlər

| Rejim | Kim alır | Yazma səlahiyyəti |
|---|---|---|
| `full` | təşkilat sahibi, `org_admin`, superadmin | hədəfin edə bildiyi hər şey (həssas istisnalarla) |
| `limited` | `exam_center`, `exam_center_head`, `ikt_rehber` | **yalnız** rolun açıq marşrut siyahısı |
| `readonly` | `tutor`, `dean`, `vice_dean`, `department_head`, `hr` | yoxdur |
| — | qalan bütün rollar | view-as ümumiyyətlə açılmır |

Xəritə: `apps/accounts/services/view_as.py` → `ROLE_MODE_MAP`.

### Nə üçün səviyyə-əsaslı qərar götürüldü

Əvvəl rejim `actor_level >= LEVELS[org_admin]` (=80) şərti ilə verilirdi. Rol
səviyyələri isə belədir:

```
ikt_rehber        88
exam_center       85
exam_center_head  85
org_admin         80
```

Yəni bu üç rol **səssizcə tam** view-as alırdı və `org_admin`-i (80) impersonasiya
edə bilirdi — çünki hədəf filtri də eyni səviyyə müqayisəsinə söykənir. Səviyyə
iyerarxiyası **hədəf seçimi** üçündür; səlahiyyət qapısı üçün deyil. İndi xəritə
açıqdır və səviyyə-əsaslı geri düşmə yoxdur.

## İmtahan Mərkəzinin yazma siyahısı

`EXAM_OPERATION_URL_NAMES` — 40 marşrut, hamısı `exams:` namespace-ində.

Siyahı təxminlə deyil, layihənin **bütün 128 mutasiya marşrutunun** təsnifatından
çıxarılıb: hər marşrutun view-u oxunub, sonra ayrıca əks-yoxlama (red team)
keçidində «imtahandan kənar akademik nəticəyə, HR/şəxsi məlumata və ya
rol/icazəyə toxunanlar» geri endirilib. Arxiv:
`docs/audits/2026-08-emsarena-tam-audit/faza6-view-as-marsrut-tesnifati.json`.

### Qəsdən **çıxarılan** marşrutlar

| Marşrut | Çıxarılma səbəbi |
|---|---|
| `exams:exam_center_ticket_remove` | Tələbəni imtahandan çıxarır; `sync_attempt_to_journal` körpüsü jurnala 0 (F) yazır və `readmit` bunu geri qaytarmır — imtahan əməliyyatı deyil, akademik nəticədir. |
| `accounts:exam_chance` | Final biletinin proktorinq sübutunu (`removed_by`, `removal_reason`, `reconnect_count`) snapshot-suz silir; `extra_attempts` kumulyativdir və ümumi limit yoxdur. |
| `exams:exam_center_room_assign_invigilators` | Nəzarətçi M2M-i eyni zamanda **giriş hüququ** qapısıdır (`_user_is_room_invigilator`) — yazma yox, səlahiyyət paylanmasıdır. |
| `exams:question_submission_create/detail/delete` | `question_submission_decide` ilə birlikdə verilsə, eyni aktor həm göndərişi uydurar, həm qəbul edər. |
| `registrar:*` | Jurnal balı və davamiyyət — imtahandan kənar akademik nəticə. |

## İKT Mərkəzinin yazma siyahısı — **boş**

`IKT_TECHNICAL_URL_NAMES = frozenset()`.

Qayda «**açıq şəkildə icazə verilmiş** sistem əməliyyatları» deyir. Təsnifatda İKT
üçün namizəd olan yeganə iki axın — `registrar:correction_apply` və
`registrar:correction_delete` — əks-yoxlamada rədd edildi:

1. **Mövzu üzrə kənar.** Hər ikisi `LessonMark` (davamiyyət + jurnal balı),
   `SelfWorkTopic`, `CourseWork` və kollokvium komponentini dəyişir. Davamiyyət
   isə `recompute_absence_hours` → `get_exam_eligibility` zənciri ilə tələbənin
   imtahana buraxılıb-buraxılmamasını təyin edir.
2. **Atribusiya saxtakarlığı.** `ViewAsMiddleware` `request.user`-i hədəflə əvəz
   edir, view isə `by_user=request.user` ötürür. Nəticədə
   `JournalCorrection.corrected_by`, `grade_audit` və `log_action` — hamısı
   **hədəfin** adına yazılır. Sənədli düzəlişin bütün zəmanəti («düzəldənin adı
   avtomatik profildən götürülür və dəyişdirilə bilməz») impersonasiya altında
   əksinə işləyir.
3. **`correction_delete` sənədsizdir.** Apply-ın PDF+səbəb tələbi revert-ə şamil
   olunmur: `revert_last_grade_correction` heç bir əsaslandırma istəmədən
   `JournalCorrection` sətrini (bəzən `LessonMark`-ın özünü) silir — yəni başqa
   vəzifəli şəxsin rəsmi düzəlişinin izi yox olur.

İKT Rəhbəri `journal.correct` səlahiyyətini **öz kimliyi ilə** saxlayır; view-as
onun üçün müşahidə alətidir. Konkret sistem əməliyyatına ehtiyac yaranarsa,
marşrutun adı `IKT_TECHNICAL_URL_NAMES`-ə əlavə olunur — mexanizm hazırdır.

## Hədəf məhdudiyyəti

`LIMITED` aktor `org_owner`, `org_admin`, `hr`, `rector`, `vice_rector`
rollarındakı istifadəçini hədəf seçə bilməz (`LIMITED_FORBIDDEN_TARGET_ROLES`).
Səviyyə filtri tək başına kifayət etmirdi: `ikt_rehber` (88) `org_admin`-dən (80)
yuxarıdır, yəni iyerarxiya onu buraxardı.

## Django admin — tam bağlı

View-as sessiyası aktiv ikən `admin:` prefiksli **bütün** sorğular (GET daxil)
rədd olunur. Səbəb: admin-də `password_change`, admin 2FA təsdiqi (`verify-otp`,
`resend-otp`) və bütün modellərin CRUD marşrutları var; middleware isə yalnız
`is_superuser` **hədəflərini** istisna edir, `is_staff`-i yox — yəni staff hədəf
seçilsə bu səth bütövlükdə açılırdı.

## Audit

* **Middleware qatı** — hər unsafe sorğu (icazəli və **bloklanmış**) `real_user`
  adına yazılır: `reason="view_as_action"` / `"view_as_action_blocked"`,
  `changes` içində `url_name`, `mode`, `allowed`.
* **Domen qatı** — `core.audit.log_action` `request` ötürülən hər qeydə
  `changes["impersonated_by"] = {id, username, mode}` damğası vurur. Domen
  çağırışları hədəfi yazmağa davam edir (kod dəyişmir), lakin əsl aktor qeydin
  içindədir.

## Testlər

`apps/accounts/tests/test_view_as.py`:

* `ViewAsLimitedModeTests` — rejim həlli, xəritədə olmayan yüksək səviyyəli rolun
  giriş ala bilməməsi, hədəf məhdudiyyəti, siyahıdan kənar POST-un bloklanması,
  İKT siyahısının boş olması, bloklanmış cəhdin audit-ə düşməsi.
* `ViewAsAdminSurfaceTests` — admin view-as altında bağlıdır, view-as-sız açıqdır.
* `ViewAsAuditAttributionTests` — domen qeydi əsl aktoru daşıyır.

## Açıq qalan

* Domen qatındakı `by_user=request.user` çağırışlarının özü hələ hədəfi yazır.
  Damğa bunu **görünən** edir, amma sahənin özünü düzəltmir; tam həll üçün
  domen servisləri aktoru ayrıca parametr kimi qəbul etməlidir.
* `EXAM_OPERATION_URL_NAMES` içindəki bəzi marşrutların öz riskləri var və audit
  arxivində qeyd olunub (məs. `exam_center_session_end` aktiv cəhdləri təhvil
  verib jurnala imtahan balı yazır). Bunlar imtahan mərkəzinin ayrılmaz
  funksiyası sayılıb; siyahıdan çıxarmaq qərarı biznes qərarıdır.
