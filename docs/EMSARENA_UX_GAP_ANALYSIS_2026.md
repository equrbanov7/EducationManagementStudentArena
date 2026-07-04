# EMSArena — UI/UX və Funksional Boşluq Analizi + Best-Practice Yol Xəritəsi

**Tarix:** 2026-07-04 · **Sənəd sahibi:** Product Architecture · **Status:** Analiz / tövsiyə (implementasiya deyil)

---

## 0. Metodologiya və vacib qeyd (şəffaflıq)

Bu sənəd **klonlama planı deyil** — məqsəd Figma-nı kor-koranə köçürmək yox, EMSArena-nı yalnız
**həqiqətən dəyər qatan** hissələrlə gücləndirməkdir.

> **Figma haqqında dürüst qeyd:** Verilən Figma faylı (`ai4JzVx3I7JBkjMHVCwJuO`) canvas-əsaslı və
> auth-qapalı render olunur; onun **piksel məzmunu proqramla oxuna bilmir** (yalnız "Figma" başlığı
> qayıdır). Ona görə bu analiz **üç etibarlı mənbəyə** əsaslanır: (1) **EMSArena-nın real kod bazası**
> (bu iş dövründə registrar konsolu, elektron jurnal, cədvəl, transkript, status və s. birbaşa işlənib),
> (2) **universitet informasiya sistemləri** (Banner, PeopleSoft Campus, UNEC ASC) best-practice-i,
> (3) **müasir LMS/SaaS UX** standartları (Canvas, Moodle, Brightspace, Notion, Linear, Stripe).
> Figma-nın konkret ekranları görülə bilsəydi, aşağıdakı "Figma-da daha yaxşı" sütunu daha dəqiq
> doldurula bilərdi — hazırda o sütun "tipik universitet-idarəetmə Figma-larında rast gəlinən nümunə"
> əsasında ehtiyatla qeyd olunub və **kod ilə təsdiq tələb edir**.

**Prinsip:** EMSArena-nın mövcud üstünlüyü Figma-dan güclüdürsə — **saxla**. Figma daha yaxşıdırsa —
**adaptasiya et**. Hər ikisi zəifdirsə — **enterprise səviyyəsində yenidən dizayn et**.

---

## 1. EMSArena-nın real inventarı (analizin təməli)

Mövcud modullar (`apps/`): `accounts`, `organizations`, `registrar`, `exams`, `live_exam`,
`trial_exams`, `appeals`, `assignments`, `projects`, `labs`, `courses`, `notifications`, `audit`,
`ai_assistant`, `blog`, `contact`, `task_submission_core`.

**Güclü tərəflər (Figma-dan asılı olmayaraq saxlanmalı):**

- Çox-tenant + **PostgreSQL RLS** (row-level security) — enterprise izolyasiya. Bu, əksər LMS-lərdə
  olmayan ciddi üstünlükdür.
- **21 rol + akademik iyerarxiya** (Fakültə→Kafedra→İxtisas→Qrup) + scope enforcement.
- **Registrar provisioning konsolu** (proqram→fənn→tədris planı→offering→tələbə təyinatı → auto-enroll).
- **UNEC-üslublu elektron jurnal** (dərs-bə-dərs iə/qb + seminar balı, kilid pəncərələri, audit).
- **Yekun qiymət + təkrar imtahan + transkript/GPA** (kredit-çəkili).
- **Dərs cədvəli** (üst/alt həftə + konflikt yoxlaması + imtahan inteqrasiyası).
- **İmtahan nüvəsi** (test/yazılı/coding + live exam + supervision/proctoring + question bank).
- **Apellyasiya + audit log + bildiriş + i18n (4 dil)** + AI köməkçi.

**Boşluqlar (dedikeytid modul yoxdur):** Maliyyə (təqaüd/ödəniş), Kitabxana, Mesajlaşma/Chat,
Sertifikat/Diplom, Sənəd idarəetməsi (DMS), qlobal Axtarış, dedikeytid Analitika/Hesabat,
tam Akademik Təqvim (yalnız `AcademicPeriod` var).

---

## 2. Faza 1 — Modul-bə-modul boşluq analizi (Gap Matrix)

Statuslar: **VAR** · **YOX** · **EMS↑** (EMSArena üstündür) · **REDIZAYN** · **BİRLƏŞDİR** ·
**QURMA** (implementasiya edilməməli).

| Modul | Status | Qeyd / tövsiyə |
|---|---|---|
| Authentication (login/OTP/first-login) | **EMS↑** | Redizayn olunub, OTP + provisioning axını güclüdür. Saxla. |
| Dashboard (rol-aware) | **REDIZAYN** | Var, amma rol-spesifik "aksiya-mərkəzli" widget-lər zəifdir (aşağı, §8). |
| Organization / University management | **VAR** | Struktur (fakültə/kafedra/unit) idarəetməsi var. |
| Faculty / Department / Specialty | **VAR** | OrgUnit iyerarxiyası + scope. |
| Programs / Curriculum / Semester | **VAR** | Registrar konsolu (K3). |
| Academic Calendar | **YOX→BİRLƏŞDİR** | Yalnız `AcademicPeriod`. Tam təqvim (bayram/imtahan sessiyası/qeydiyyat pəncərəsi) yoxdur → cədvəl+period üzərində qur. |
| Students / Teachers / HR | **VAR** | Rol + membership + provisioning. |
| Attendance | **VAR (EMS↑)** | Dərs-bə-dərs iə/qb + 25% qaydası + avtomatik hesab. UNEC modeli — güclüdür. |
| Assignments / Projects / Labs | **VAR** | Dedikeytid app-lər var; jurnal ilə inteqrasiya zəif (§3 boşluq). |
| Notifications | **VAR** | In-app + org bildirişləri. |
| Messaging / Chat | **YOX** | Diskussiya/DM yoxdur. Aşağı prioritet (§5). |
| Calendar (şəxsi/qrup) | **YOX→BİRLƏŞDİR** | Cədvəl var; şəxsi/iCal ixrac yoxdur. |
| Exam Center / Question Bank / Online Exams | **VAR (EMS↑)** | Güclü nüvə; proctoring + coding exam. Saxla. |
| Exam Monitoring / Supervision | **VAR (EMS↑)** | SupervisionIncident + proctoring. |
| Appeals | **VAR** | Dedikeytid app; jurnal-qiymətə birbaşa bağ zəif (§3). |
| Certificates / Diploma | **YOX** | Sertifikat/transkript-PDF generasiyası yoxdur → §5, Orta prioritet. |
| Reports / Analytics | **YOX (qismən)** | Profil statistikası var; dedikeytid analitika/eksport yoxdur. |
| Finance / Tuition | **YOX** | Ödəniş/təqaüd yoxdur. İş qərarı tələb edir (§5). |
| Library | **YOX** | Aşağı prioritet / QURMA (əgər tələb yoxdursa). |
| Settings / Permissions / Profile | **VAR** | RBAC + profil bölmələri. |
| Files / Document Management | **YOX (qismən)** | App daxili fayl var; mərkəzi DMS yoxdur. |
| Activity / Audit Logs | **VAR (EMS↑)** | Enterprise audit log — güclüdür. |
| Global Search | **YOX** | Yalnız modul-daxili axtarış. Yüksək UX dəyəri (§4). |
| Global Navigation | **REDIZAYN** | Sidebar/topbar var; universitet rejimi üçün informasiya arxitekturası sadələşdirilməlidir (§4). |

---

## 3. Faza 3 — Elektron Jurnal / Gradebook (ƏN YÜKSƏK PRİORİTET)

### 3.1 Mövcud vəziyyət (real kod)

EMSArena jurnalı **UNEC / AZ-Boloniya sadələşdirilmiş modeli**dir:

- `Lesson` + `LessonMark` — dərs-bə-dərs **iştirak/qayıb (iə/qb)** + seminar/lab **balı**.
- `AssessmentScheme` (offering üzrə): `entry_score_max=50` (semestr "giriş balı" tavanı),
  `pass_threshold=51`, `min_final_exam_score=17`, `is_published` (kilid).
- `FinalGrade` (yekun imtahan ≤50) + `ResitRecord` (təkrar imtahan).
- `finals.compute_final_result` → **giriş balı + imtahan → 0-100 → hərf (A–F) + GPA + keçdi/kəsildi/kəsilir**.
- `transcript.build_student_transcript` → **kredit-çəkili semestr/kumulyativ GPA**.
- Kilid pəncərələri: dərs tarixi **5 dəq**, bal **1 gün**; publish → tam kilid + audit.
- **25% qayıb** → imtahana buraxılmır (barred).

### 3.2 Enterprise tələbləri ilə tutuşdurma (VAR / QİSMƏN / BOŞLUQ)

| Tələb | Status | Şərh |
|---|---|---|
| Attendance | **VAR** | Dərs-bə-dərs iə/qb. |
| Homework / Quiz / Midterm(Kollokvium) / Practical / Lab / Project | **BOŞLUQ** | Hazırda hər şey **"seminar/lab balı cəmi ≤50"**-yə yığılır. Ayrı **çəkili komponent tipləri** yoxdur (əvvəlki `GradeComponent` modeli X1-də dərs-bə-dərs modelinə görə silinmişdi). |
| Bonus / Penalty / Extra Credit | **BOŞLUQ** | Bonus/cərimə (gecikmə) sahələri yoxdur. |
| Weighted grading (çəki) | **BOŞLUQ** | Komponent çəkiləri yoxdur — bu, ən böyük enterprise boşluqdur. |
| Rubrics | **BOŞLUQ** | Rubrika modeli yoxdur. |
| Manual grade adjustment | **VAR** | Kilid pəncərəsində redaktə + imtahanda `score_adjustments`. |
| Grade history / audit trail (bal-bə-bal) | **QİSMƏN** | Publish audit var; **hər bal dəyişikliyinin versiyası** izlənmir (`entered_by` var, tarixçə yox). |
| Grade locking | **VAR** | `is_published` + tarix/bal pəncərələri. |
| **Approval workflow (dekan/kafedra təsdiqi)** | **BOŞLUQ** | Yalnız müəllim publish edir; **çox-mərhələli təsdiq zənciri yoxdur**. |
| GPA / Credit / Semester / Cumulative GPA | **VAR** | `transcript.py`. |
| Percentage / Letter / Numeric | **VAR** | 0-100 + A-F. |
| Custom grading systems | **QİSMƏN** | Hərf zolaqları sərt-kod (`_LETTER_BANDS`); scheme yalnız threshold-ları konfiqurasiya edir. |
| Bulk grading | **VAR** | Grid `save_marks`. |
| Import / Export | **BOŞLUQ** | Jurnalda ixrac/idxal yoxdur (imtahanda xlsx var). |
| Grade comments / feedback | **BOŞLUQ** | `LessonMark`-da rəy sahəsi yoxdur. |
| Late penalty / missing handling | **QİSMƏN** | Assignments-də deadline ola bilər; jurnal modelləşdirmir. |
| Exam absence / Retake | **VAR** | Barred + `ResitRecord`. |
| Appeals integration (jurnal balı) | **QİSMƏN** | Appeals app var; jurnal-balına birbaşa bağ zəif. |
| Publishing workflow | **VAR** | `publish_offering` + audit. |
| Transcript integration | **VAR** | `transcript.py`. |

### 3.3 Tövsiyə olunan enterprise gradebook arxitekturası (additiv, mərhələli)

**Kritik #1 — Çəkili komponent modeli (BOŞLUQ-un bağlanması).** UNEC-də belədir: cari qiymətləndirmə
(≈50) → seminar + kollokvium(lar) + SDF/sərbəst iş komponentlərindən **çəki ilə** yığılır. Tövsiyə:

- Yeni model `AssessmentComponent(offering, type, weight, max_score)` (type: seminar / kollokvium /
  layihə / lab / SDF / bonus / penalty). Migration additiv (default = mövcud "seminar-cəm" davranışı).
- `LessonMark.score` və müstəqil komponent balları `compute_final_result`-da **çəki ilə** giriş balına
  çevrilir. Geriyə-uyğunluq: komponent yoxdursa → cari məntiq.
- **Fayda:** hər universitet öz qiymətləndirmə sxemini konfiqurasiya edir (multi-tenant). **Risk:** UI
  mürəkkəbliyi → default-la gizlə, "qabaqcıl" rejimdə aç. **Best practice:** Canvas *Assignment Groups +
  Weights*, Banner *Grade Components*.

**Kritik #2 — Qiymət təsdiq zənciri (dekan/kafedra).** `GradeApproval(offering, level, approver,
status, decided_at)` — müəllim publish → **kafedra müdürü** → **dekan** təsdiqi; hər addım audit-ə.
Publish yalnız son təsdiqdən sonra transkriptə keçir. **Best practice:** PeopleSoft *Grade Approval*,
UNEC *dekanlıq təsdiqi*.

> ✅ **İCRA OLUNDU (U7.2).** Ayrıca `GradeApproval` cədvəli əvəzinə mövcud RLS-qorunan
> `AssessmentScheme`-ə `approval_status` (draft→submitted→chair_approved→approved / returned) +
> `submitted_by/chair_approved_by/dean_approved_by/returned_reason` sahələri əlavə olundu (miqrasiya
> 0017). Servis: `apps/registrar/approval.py` (submit/chair_approve/dean_approve/return_for_revision,
> hər addım `audit`-ə yazılır; dekan təsdiqi `is_published=True` edir). Kilid: təsdiq mərhələsində
> jurnal redaktəsi bağlıdır (`gradebook.journal_is_locked`). RBAC: kafedra=`chair_head/department_head`,
> dekan=`dean` (org owner/admin bootstrap). UI: jurnal səhifəsində status-aware əməliyyat paneli +
> kafedra/dekan üçün **"Qiymət təsdiqləri"** inbox-u (`/jurnal/tesdiqler/`). Testlər: `test_approval.py`
> (15 test). Növbəti (#3): qiymət dəyişikliyi audit izi (artıq qismən `audit`-ə yazılır).

> ✅ **İCRA OLUNDU (U7.3) — qiymət dəyişikliyi audit izi.** `apps/registrar/grade_audit.py`:
> `save_marks / save_component_scores / set_exam_score / set_resit_score` funksiyaları hər real
> dəyişiklikdə (**köhnə ≠ yeni**) mövcud `audit.AuditLog`-a (``changes``/``new_values`` JSON) **kim /
> nə vaxt / köhnə → yeni** yazır — save əməliyyatı başına BİR aqreqat qeyd (dəyişməyən xanalar sıfır
> qeyd). `resource_type=registrar.grade.*`, `resource_id=offering`. Jurnal səhifəsində **"Qiymət
> dəyişikliyi tarixçəsi"** paneli (köhnə=qırmızı üstüxətli → yeni=yaşıl). Testlər: `test_grade_audit.py`
> (6 test). Bununla §110-dakı "hər bal dəyişikliyinin versiyası izlənmir" boşluğu bağlanır.

**Yüksək #3 — Bal dəyişiklik tarixçəsi (audit trail).** `LessonMarkHistory` və ya `GradeChangeLog`
(mark, old, new, by, reason, at). Enterprise auditor tələbi + apellyasiya sübutu. Onsuz da `audit`
app var → ora yazmaq kifayətdir (yeni cədvəl minimuma endirilir).

**Yüksək #4 — Rəy + apellyasiya inteqrasiyası.** `LessonMark.comment` + jurnal balına "apellyasiya et"
düyməsi (mövcud `appeals` app-inə bağla). Tələbə "Fənlərim"də balın niyəsini görür.

**Orta #5 — İdxal/İxrac.** Jurnal → XLSX/CSV ixrac (imtahandakı export-registry pattern-i təkrar
istifadə); idxal ehtiyatlı (validasiya + preview).

**Orta #6 — Konfiqurasiya olunan hərf sistemi.** `_LETTER_BANDS`-i `GradingScale` modelinə çıxar
(tenant-konfiqurasiya). Boloniya default qalır.

> **DİQQƏT — kor-koranə köçürmə YOX:** Figma çox güman "komponentli qiymət cədvəli" göstərir, amma
> EMSArena-nın **dərs-bə-dərs davamiyyət + kilid + audit + RLS** təməli əksər Figma prototiplərindən
> güclüdür. Ona görə komponent çəkisi **mövcud dərs-bə-dərs modelin ÜZƏRİNƏ additiv** qurulmalıdır,
> onu əvəz etməməlidir.

---

## 4. Faza 4 — UX təkmilləşdirmələri (enterprise SaaS pattern-ləri)

| Sahə | Cari | Tövsiyə | Prioritet |
|---|---|---|---|
| Qlobal naviqasiya (IA) | Sidebar bölmələri çoxdur | Universitet rejimində rol-aware, qruplaşdırılmış sidebar; "Akademik / İdarəetmə / İmtahan" bölgüsü | Yüksək |
| **Qlobal axtarış** (⌘K) | Yoxdur | Command-palette (tələbə/fənn/offering/imtahan) — Linear/Notion pattern | Yüksək |
| Cədvəllər (data table) | Fərqli səhifələrdə fərqli | Vahid **DataTable** komponenti: sort/filter/paginate/sütun-seçim/CSV | Yüksək |
| Filtrlər | Ad-hoc | Vahid filter-bar (chip + saxlanan filtrlər) | Orta |
| Boş/xəta/yüklənmə vəziyyətləri | Qismən (skeleton var) | Vahid **EmptyState / ErrorState / Skeleton** komponentləri hər siyahıda | Orta |
| Təsdiq dialoqları | `confirm()` (native) | Token-əsaslı modal `ConfirmDialog` (destruktiv aksiyalar üçün) | Orta |
| Dark mode | Qismən (token var) | `--ems-*` token-ləri ilə tam dark rejim auditi | Orta |
| Əlçatanlıq (a11y) | Qismən | Klaviatura naviqasiyası, ARIA, focus-ring auditi; WCAG AA | Yüksək |
| Mikro-interaksiya | Az | Optimist UI (bal yazımı), toast-lar (var), keçid animasiyaları | Aşağı |
| Klaviatura qısayolları | Yoxdur | ⌘K axtarış, jurnal grid-də ox naviqasiyası (Excel kimi) | Orta |
| Mobil UX | Responsive var | Jurnal grid-i mobil üçün "kart" rejimi | Orta |

**Best practice istinadları:** Stripe Dashboard (data-table + filter), Linear (⌘K + sürət),
Notion (empty states), Canvas (gradebook keyboard nav).

---

## 5. Faza 5 — Funksional təkmilləşdirmələr (Figma/LMS-də ola bilən, EMS-də yox)

| Funksiya | Qərar | Səbəb / fayda / risk |
|---|---|---|
| **Sertifikat / Transkript PDF** | ✅ **İCRA OLUNDU (U9 — transkript)** | `apps/registrar/transcript_pdf.py` (PyMuPDF, yeni asılılıq YOX) + `pdf_views.py`. Vendorlanmış DejaVu Sans (`static/fonts/`) AZ hərfləri üçün; font subsetting ilə ~90KB. İki endpoint: tələbə özü (`/jurnal/transkript.pdf`) + registrar konsolu (`.../telebe/<pk>/transkript.pdf`, RBAC). Hər buraxılış audit-ə yazılır. i18n `registrar.pdf` konteksti (msgid toqquşmasından qorunma). Testlər: `test_transcript_pdf.py` (7 test). Qalan: sertifikat/arayış şablonları + rəqəmsal imza (gələcək). |
| **Qlobal axtarış (⌘K)** | ✅ **İCRA OLUNDU (U8)** | `accounts:global_search` JSON endpoint + command-palette overlay (`static/js/global_search.js`, `_global_search.html`). Rol/tenant-aware qruplar: **Naviqasiya** (hamı), **Jurnallarım** (müəllim), **Fənlər/Tələbələr** (yalnız registrar-səlahiyyətli — məxfilik: adi tələbə tələbələri sadalaya bilməz). ⌘K/Ctrl+K + navbar düyməsi, ox-naviqasiyası, a11y (dialog/listbox/option). Testlər: `test_global_search.py` (7 test). Sadə DB `icontains` axtarışı (indeksləmə sonra optimallaşdırıla bilər). |
| **Akademik təqvim** | **BİRLƏŞDİR (Orta)** | Cədvəl+period üzərində sessiya/qeydiyyat pəncərəsi. Yeni ağır model yox. |
| **Analitika/Hesabat paneli** | **QUR (Orta)** | Dekan üçün fakültə/kafedra kəsimləri (keçid %, orta GPA, davamiyyət). |
| **Maliyyə (təqaüd/ödəniş)** | **İŞ QƏRARI (Aşağı)** | Böyük domen; yalnız real tələb olsa. Ayrıca `finance` app + RLS. |
| **Kitabxana** | **QURMA (Aşağı)** | Tələb təsdiqlənməyibsə əlavə etmə (scope creep). |
| **Mesajlaşma/Chat** | **İGNORE/sonra (Aşağı)** | Bildiriş + apellyasiya kifayət edir; real-time chat ağır. |
| **Sənəd idarəetməsi (DMS)** | **BİRLƏŞDİR (Aşağı)** | Mövcud fayl-yükləmə + audit; mərkəzi DMS yalnız tələb olsa. |
| **Rubrika ilə qiymətləndirmə** | **QUR (Orta, §3)** | Layihə/lab üçün. |

---

## 6. Faza 6 — Best-practice müqayisəsi (məhsullar üzrə)

- **Canvas LMS:** Assignment Groups + çəki, SpeedGrader (rubrika + rəy), Gradebook keyboard nav →
  §3 komponent çəkisi + §4 grid nav üçün istinad.
- **Banner / PeopleSoft (universitet IS):** Grade components, **grade approval workflow**, registrar
  provisioning, akademik təqvim → §3 təsdiq zənciri + §5 təqvim üçün istinad. EMSArena registrar konsolu
  artıq bu istiqamətdədir.
- **Brightspace/Moodle:** Configurable grading scales, gradebook export → §3 hərf sistemi + ixrac.
- **Google Classroom / Teams for Education:** sadə axın; EMSArena daha zəngin — **kopyalama YOX**.
- **Linear / Notion / Stripe / GitHub:** ⌘K, data-table, empty/loading states, komponent
  standartizasiyası → §4 UX pattern-ləri.

**Nəticə:** EMSArena universitet-IS tərəfdə (RLS, registrar, jurnal) çox güclüdür; boşluqlar əsasən
**qiymət-komponent çəkisi + təsdiq zənciri** (akademik) və **UX standartizasiyası + qlobal axtarış**
(SaaS) sahələrindədir.

---

## 7-9. Data / Performans / Komponent standartizasiyası

**Data arxitekturası (Faza 7):** Bütün yeni modellər — additiv migration (nullable/default),
`organization` FK + **RLS**, `-m postgres` izolyasiya testi. Yeni cədvəl sayını minimuma endir: bal
tarixçəsi üçün mövcud `audit` app-dən istifadə et. GPA/analitika üçün **materialized/keşlənmiş
aqreqat** (hər səhifə açılışında ağır COUNT yox — mövcud badge-keş pattern-i genişləndir).

**Performans (Faza 8):** Jurnal grid-i çox sətirdə — server-side paginate + `select_related`/
`prefetch_related` (artıq istifadə olunur). Analitikada N+1 yox → annotate/aggregate. Yeni səhifə
DOM-u kiçik; komponent təkrarı yox.

**Komponent standartizasiyası (Faza 9):** Təkrarlanan UI elementləri (button, card, table, input,
dialog, badge, alert, filter, empty-state) → **tək dizayn-sistem partial-ları** (`--ems-*` token,
inline CSS/JS yox — bu qayda artıq tətbiq olunur). Prioritet: `DataTable`, `ConfirmDialog`,
`EmptyState`, `StatusBadge` (registrar-da artıq başlanğıc var), `FilterBar`.

---

## 10. Faza 10 — Yekun prioritet matrisi (icra sırası)

| # | Təkmilləşdirmə | Prioritet | Biznes dəyəri | Effort | Risk | DB | Performans | Təhlükəsizlik |
|---|---|---|---|---|---|---|---|---|
| 1 | Jurnal: **çəkili komponent modeli** (§3.3-1) | **Kritik** | Çox yüksək | Yüksək | Orta | +1 model (additiv, RLS) | Neytral | Neytral |
| 2 | Jurnal: **dekan/kafedra təsdiq zənciri** (§3.3-2) | **Kritik** | Yüksək | Yüksək | Orta | +1 model + audit | Neytral | ↑ (rəsmiləşmə) |
| 3 | **Qlobal axtarış (⌘K)** (§4) | **Yüksək** | Yüksək | Orta | Aşağı | Yox (DB read) | İndeks vacib | Neytral |
| 4 | **DataTable + FilterBar + EmptyState** standartı (§9) | **Yüksək** | Orta | Orta | Aşağı | Yox | ↑ | Neytral |
| 5 | Jurnal: **bal tarixçəsi/audit trail** (§3.3-3) | **Yüksək** | Yüksək | Aşağı | Aşağı | audit-ə yaz | Neytral | ↑ |
| 6 | **a11y/klaviatura auditi** (WCAG AA) (§4) | **Yüksək** | Orta | Orta | Aşağı | Yox | Neytral | Neytral |
| 7 | **Transkript/arayış PDF + sertifikat** (§5) | **Orta** | Yüksək | Orta | Orta | Yox/kiçik | Neytral | Neytral |
| 8 | Jurnal: **rəy + apellyasiya inteqrasiyası** (§3.3-4) | **Orta** | Orta | Aşağı | Aşağı | +1 sahə | Neytral | Neytral |
| 9 | Jurnal: **XLSX ixrac/idxal** (§3.3-5) | **Orta** | Orta | Aşağı | Orta | Yox | Neytral | Neytral |
| 10 | **Dekan analitika paneli** (fakültə/GPA/davamiyyət) (§5) | **Orta** | Yüksək | Orta | Aşağı | keş-aqreqat | keş vacib | Neytral |
| 11 | **Akademik təqvim** (sessiya/qeydiyyat pəncərəsi) (§5) | **Orta** | Orta | Orta | Aşağı | kiçik | Neytral | Neytral |
| 12 | **Rubrika ilə qiymətləndirmə** (§3.3) | **Orta** | Orta | Orta | Orta | +1 model | Neytral | Neytral |
| 13 | Konfiqurasiya olunan **GradingScale** (§3.3-6) | **Aşağı** | Orta | Aşağı | Aşağı | +1 model | Neytral | Neytral |
| 14 | Dark mode tam auditi (§4) | **Aşağı** | Aşağı | Aşağı | Aşağı | Yox | Neytral | Neytral |
| 15 | Maliyyə / Kitabxana / Chat | **Aşağı / İş qərarı** | Dəyişən | Yüksək | Yüksək | Böyük | — | — |

### 10.1 Redizayn tələb edən ekranlar
1. **Rol-aware Dashboard** (aksiya-mərkəzli widget-lər; §8-tip). 2. **Jurnal grid** (komponent
sütunları + rəy + kilid vəziyyəti göstəricisi). 3. **Qlobal naviqasiya/sidebar** (universitet IA).
4. **Registrar konsolu** (böyüdükcə DataTable-a keçid). 5. **Tələbə "Fənlərim/Transkript"**
(komponent breakdown göstərişi).

### 10.2 Redizayn/standartlaşma tələb edən komponentlər
`DataTable`, `FilterBar`, `EmptyState`, `ErrorState`, `Skeleton`, `ConfirmDialog`, `StatusBadge`,
`Card`, `FormField` (label+help+error vahid), `Toast` (var — sabitlə).

---

## 11. Hər tövsiyə üçün: səbəb / fayda / risk / best-practice / yanaşma (xülasə)

- **#1 Komponent çəkisi:** *Səbəb* — universitetlər fərqli qiymətləndirmə sxemi işlədir; hazırkı
  "seminar-cəm ≤50" sərtdir. *Fayda* — multi-tenant konfiqurasiya, real UNEC uyğunluğu. *Risk* — UI
  mürəkkəbliyi (→ default gizli). *Best practice* — Canvas Assignment Groups, Banner Grade Components.
  *Yanaşma* — additiv model + `compute_final_result` genişlənməsi + geriyə-uyğun default.
- **#2 Təsdiq zənciri:** *Səbəb* — qiymət rəsmi sənəddir, tək müəllim publish-i zəifdir. *Fayda* —
  rəsmiləşmə + audit. *Risk* — axın uzanır (→ opsional, tenant flag). *Best practice* — PeopleSoft
  Grade Approval. *Yanaşma* — `GradeApproval` state-machine + audit + publish-lock inteqrasiyası.
- **#3 ⌘K axtarış:** *Səbəb/fayda* — böyük sistemdə sürət. *Risk* — indeks. *Yanaşma* — əvvəl DB
  `icontains` (tələbə/fənn/offering), sonra lazım olsa full-text.
- **#4 DataTable:** *Səbəb* — cədvəl təkrarı + fərqli davranış. *Fayda* — tutarlılıq +
  maintainability. *Yanaşma* — tək partial + token stil, mövcud səhifələr tədricən köçürülür.
- **#5 Bal tarixçəsi:** *Səbəb* — auditor + apellyasiya sübutu. *Yanaşma* — mövcud `audit` app-ə yaz
  (yeni cədvəl minimum).

---

## 12. Yekun tövsiyə (icra strategiyası)

1. **Əvvəl akademik dəqiqlik (Kritik):** #1 komponent çəkisi + #2 təsdiq zənciri + #5 bal tarixçəsi —
   bunlar universitet-IS tələbidir və EMSArena-nı "sadə jurnal"dan "rəsmi qiymət sistemi"nə çevirir.
2. **Sonra UX omurğası (Yüksək):** #3 ⌘K + #4 DataTable/EmptyState + #6 a11y — bütün sistemə yayılan
   tutarlılıq.
3. **Sonra rəsmi çıxışlar (Orta):** #7 transkript/sertifikat PDF + #10 dekan analitika + #9 ixrac.
4. **Ən sonda cilalama:** rubrika, GradingScale, dark-mode auditi, dashboard mikro-interaksiya.

**Dəyişməz prinsip:** hər faza additiv migration + RLS + xarakteristik/`-m postgres` test +
`--ems-*` token + inline CSS/JS yox + i18n(4 dil) + module-boundary təmiz + CI SUCCESS. EMSArena-nın
mövcud üstünlükləri (RLS, registrar, jurnal təməli, audit) **saxlanılır**; Figma yalnız daha yaxşı
olduğu nöqtələrdə (əsasən UX standartizasiyası) adaptasiya olunur.
