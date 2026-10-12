# Rol auditi — 2026-10-13: «hər rol öz norması qədər görürmü?»

**Baza:** QA klonu `emsarena_rehearsal_a0d170000901` (`:55433`), miqrasiyalar `organizations 0060` /
`registrar 0088`-ə qədər tətbiq edildi. Prod-a və `emsarena_db`-yə toxunulmayıb.
**Ölçmə:** `scripts/role_open_all.py` — 24 rol, 780+ bölmə açılışı, **0 × 500**. Cədvəl:
[`docs/ROL_MATRISI.md`](../../ROL_MATRISI.md).
**Analiz:** 4 rol qrupu (rəhbərlik/inzibati · fakültə/kafedra · müəllim/tələbə · imtahan mərkəzi + qapı
ardıcıllığı) + 2 əhatə (scope) yoxlaması. Hər iddia `fayl:sətir` ilə yoxlanılıb; aşağıdakı «düzəldildi»
bəndləri əlavə olaraq testlə (köhnə kodda QIRMIZI, yenidə YAŞIL) təsdiqlənib.

Ümumi nəticə: **menyu ↔ server qapısı sağlamdır** — fraqment ucu (`sections_api.py:360-379`) menyu ilə
eyni `allowed_sections`-a baxır, gizli bölmə URL ilə açılmır; panellərin əksəriyyəti datanı öz
`scope_unit` alt-ağacı ilə süzür. Problemlər iki sinifdədir: (1) **`org_admin` ALİASI** (səviyyə ≥ 80 və ya
admin-ekvivalent ad — dekan, dekan müavini, kafedra müdiri) bəzi yerlərdə real açarın yerini tutur;
(2) bir neçə səth **rol ADI** ilə qapılıdır və icazə redaktoru onu idarə edə bilmir.

## A. Düzəldildi (bu sessiya, testlə — `apps/accounts/tests/test_role_audit_2026_10_13.py`)

| # | Problem | Düzəliş |
|---|---|---|
| A1 | **Kafedra müdiri / dekan müavini struktur reyestrində rəhbər və rol təyin edə bilirdi** (dekan müavini öz dekanını əvəz edə bilərdi — köhnə rəhbərin üzvlüyü deaktiv olurdu). Səbəb: `can_assign_members` / `can_assign_head` `org_admin` aliası ilə açılırdı, `member.edit` olmadan. Sahibin 2026-10-11 qaydası («Dekan rol verə bilir — olmaz») yalnız kabinet menyularında bağlanmışdı. | `structure_views/_shared.py`, `registry_base.py`: təyinat yalnız real `member.edit` / `unit.assign_head` (və superadmin/sahib). Vahid yarat/redaktə/sil olduğu kimi qalır (dekanın öz fakültəsində kafedra yaratması testlə kilidli). |
| A2 | **Dekan (və alias alan hər UNIT rolu) bildirişi BÜTÜN universitetə və bütün şöbə hədəflərinə göndərə bilirdi** — modulun öz sənədi «dekan yalnız öz alt-ağacı» deyir. | `notification_scopes.py`: org-wide = org-wide `unit.view` əhatəsi VƏ YA ORGANIZATION əhatəli admin üzvlüyü; «bütün təşkilat» hədəfi `can_target_whole_organization` ilə (siyahı + server). Rektor/prorektor/sahib dəyişmir. |
| A3 | **«Apellyasiyalarım» HR, tyutor, tələbə xidmətləri və s. heyətə fraqment URL-i ilə açılırdı** (menyuda yox idi) — inkar-qayda. `my-results` üçün P3-5-də bağlanan eyni sinif. | `rbac.py`: capability menyu ilə eyni şərtdən. |
| A4 | **Qəyyumlar Şurasının sədri (`board_chair`) tək üzvlüklə view-as ala bilmirdi** — `ROLE_MODE_MAP`-da yox idi (prod-da əlavə rektor üzvlüyü ilə maskalanırdı). | `view_as.py`: `board_chair → FULL`, «admin» süzgəcinə əlavə. |
| A5 | **HR-ın «Rol təyin et» / «Rolları idarə et» menyusu rol ADI ilə açılırdı** — redaktorda `role.assign` alınsa menyu qalırdı, əməl 403 verirdi. | `rbac.py`: `_can_manage_roles` ilə (şablonda HR-da `role.assign` var — prod-da görünüş dəyişmir). |
| A6 | Ölçmə skripti çoxrollu nümunə götürürdü («teacher» = müəllim+müdir, 49 bölmə), müəllimin `/jurnal/` linkini görmürdü, dashboard vidcetlərindəki açarları sayırdı, RLS altında «0 rol» ilə uğurlu çıxırdı. | `role_open_all.py`: tək-rollu nümunə, yalnız sidebar, jurnal linki, exit 2. |

## B. Qərarlar — HAMISI tövsiyə olunan variantla TƏTBİQ OLUNDU (sahib 2026-10-13: «tövsiyə olunan variantlarla et»)

Commit-lər: `f1801cec` (açar verilişi + miqrasiya 0061), `742d7872` (B1), `0dc45f94` (B8/B9/B15), `5f56b570`
(B12/B13/B17/B18/B19), `234487b3` (B2/B3/B5/B7/B10/B11/B14/B16/B21, miqrasiya 0062), sonrakı düzəliş commit-i
(miqrasiya 0063). Əlavə sahib qərarları (2026-10-13 axşam):

* **«Qrupum» — yalnız şəxsi:** qrup yoldaşları üçün yalnız ad + tələbə nömrəsi; davamiyyət (fənn üzrə qayıb)
  YALNIZ baxanın özünə («Mənim davamiyyətim»).
* **`org.view` çıxarıldı** (heç nəyi qapılamırdı) — kataloq, bütün şablonlar, miqrasiya 0063.
* **Başqa tövsiyələr:** RİM əməkdaşına `workload.report` / `plan.view` / `semester.view`, qəyyuma
  `workload.report` (yalnız-oxu icmallar; şablon vədləri) — miqrasiya 0063.
* B9-un genişlənməsi: rol daşıyanı (müavin/koordinator/rəhbər) SİLMƏK də onu verən açarı tələb edir.
* Diqqət: HR artıq tələbə idxal etmir — prod-da tələbə qəbulunu Tələbə xidmətləri rolu aparmalıdır.

Aşağıdakı siyahı tarixi qeyd kimi saxlanılır (nə tapılmışdı):

### Yüksək

1. **RİM əməkdaşı və imtahan mərkəzi işçisi apellyasiya QƏRARI verir, ikinci şans verir, kollokvium
   pəncərəsini idarə edir, sual göndərişlərini qəbul/rədd edir** — rol adı ilə
   (`appeals/services/permissions.py:95-114`, `views/exam_chance.py:68`, `kollokvium_windows.py:108-114`;
   alias `core/roles.py:116-117`). Şablon isə RİM əməkdaşı üçün «görür və köməklik edir, dəyişdirmir»
   deyir (`default_roles_rim.py:32`), `appeal.decide/respond` yalnız rəhbərdədir.
   *Tövsiyə:* qərar əməllərini `appeal.decide` / `appeal.respond` / yeni `exam.second_chance` açarına bağla
   (işçi yalnız görür). ⚠️ İmtahan sistemidir — `exam_activity_probe` ilə, sessiya olmayan vaxt.
2. **«Akademik qeydlər» (GPA/transkript) rol adı ilə açılır və mərkəzi rollara (imtahan mərkəzi işçisi,
   RİM əməkdaşı daxil) `grade.view` olmadan org-wide verilir** (`academic_records.py:38-110`,
   `rbac_university_sections.py:63`). Redaktorda `grade.view` almaq heç nəyi bağlamır, vermək heç nəyi açmır.
   *Tövsiyə:* menyu + data yalnız `grade.view` əhatəsi ilə; Tədris şöbəsinə `grade.view` ver (bax 5).
3. **Tələbə xidmətləri «Müəllim idxalı»nı görür (toplu müəllim hesabı yaradır)** — `teacher-intake` tələbə
   qəbulu ilə eyni `user.import` açarındadır (`rbac_sections.py:312-313`); şablon `user.import`-u yalnız
   tələbə qəbulu üçün verir (`default_roles_student_services.py:18-20`).
   *Tövsiyə:* yeni `user.import_staff` açarı (HR-a), miqrasiya ilə.
4. **`assistant` (assistent) müəllim interfeysini görür, amma heç vaxt fənnin müəllimi ola bilmir**:
   `grade.input` yoxdur (`registrar/integrity.py:133-152` — yük sinxronu `instructor_blocked`),
   `syllabus.*` yoxdur, `exam.create` yoxdur; buna baxmayaraq TAPŞIRIQ idxalı onu müəllim kimi bağlayır
   (`task_workbook_teachers.py:59`). *Tövsiyə:* QKU-da «assistent» elmi-pedaqoji vəzifədir → müəllim
   açarlarını ver (`grade.input`, `syllabus.view/edit/submit`, `exam.create/edit`), miqrasiya ilə.

### Orta

5. **Tədris şöbəsi** jurnal/qeyd səthlərindən kənardadır: `academic-records`, `lessons-log`
   (`journal.lessons_unit`), jurnal oxusu (`journal.view` — sidebar qapısı bu açarı nəzərə almır,
   `rbac_university_sections.py:50`), rəhbər üçün `student-registry` (plan: xaric dekan + Tədris şöbəsi
   rəhbəri, `HANDOFF_FULL_PLAN.md:146`), `schedule-manage` (heç bir `schedule.*` yoxdur).
   *Tövsiyə:* oxu açarlarını ver; cədvəl redaktəsi — qərar.
6. **HR tələbə tərəfi:** `student-admission`, `student-intake`, `people-students` (kontakt sütunları ilə).
   `user.import` HR-a 2026-09-02-də, tələbə xidmətləri yaranmazdan BİR gün əvvəl verilib.
   *Tövsiyə:* 3-dən sonra HR-dan `user.import` və `people.view_students`-i al.
7. **`member` ≈ 28 xəritələnməmiş ofis işçisidir** (mühasib, kitabxanaçı…, `staff_roster.py:167`), amma
   tələbə səthlərini görür (`assigned-exams`, `my-results`, `pending-answers`…) və elan/sorğu auditoriyasından
   kənardadır. *Tövsiyə:* universitet rejimində tələbə bölmələrini çıxar, `application.create` ver, iki
   auditoriya modulunda heyət say; ya da onları real heyət roluna köçür.
8. **`student-organization-management` yazıları yalnız səviyyə ≥ 65 ilə** (`_management_flow/flow.py:63-67`)
   — dekan/müavin/müdir təşkilata bölməsiz üzv dəvət edə, müraciət təsdiqləyə bilir; `member.invite`
   yoxlanmır. *Tövsiyə:* `member.invite` + əhatə yoxlaması.
9. **Dekanın rəhbər təyini** (dekanda `member.edit` var → A1-dən sonra da öz fakültəsində kafedra
   müdiri / müavin / koordinator təyin edir). «Dekan rol verə bilir — olmaz» buna da aiddirmi? Əgər bəli —
   dekandan `member.edit`-i al (miqrasiya).
10. **`lead_student`** «məhdud qrup görünüşü» vəd edir (`member.view`), amma tələbə dəstindən fərqi yoxdur;
    AI köməkçi ona açılmayan `org-members` linki təklif edir. *Tövsiyə:* «Qrupum» oxu bölməsi və ya vədi sil.
11. **Prorektorun cədvəl çıxışı yoxdur; `schedule.view` heç nəyi açmır** (RİM əməkdaşı, qəyyum, inzibati
    şöbədə var). *Tövsiyə:* `schedule-manage`-i `schedule.view` ilə YALNIZ-OXU aç, prorektora ver.
12. **Sərbəst iş / kurs işi açarları kurs sisteminə tətbiq olunmur** — müəllimin `pending-review` /
    `review-results`, tələbənin `assigned-courses` / `my-results` bölmələri «Sərbəst iş» etiketi ilə qalır
    (2026-10-10 qaydası ilə ziddiyyət). *Tövsiyə:* `selfwork_enabled` / `coursework_enabled` ilə qapıla.

### Aşağı / texniki borc

13. **Ölü açarlar** (redaktorda var, heç nəyi qapılamır): `appeal.decide`, `appeal.respond`,
    `grade.publish`, `org.view`, `schedule.view`, `assignment.edit`. Drift testi
    (`test_audit_2026_09_13_rbac.py:226-242`) hər sitatlı sətri sayır — tutmur.
14. **Rol ADI ilə qapılı səthlər** (redaktor idarə edə bilmir): imtahan mərkəzi panelləri, `manage-appeals`,
    `question-bank`, `publish-notification` (açar yoxdur), `org-members`/`org-roles`/`unit-exams`/`my-journal`/
    `lessons-log`/`subject-folders` (`rbac_university_sections.py:50-94`), post təsdiqi (səviyyə ≥ 60).
15. `org-roles` alias ilə bütün rolları + icazə açarlarını göstərir (`role.view` yoxlanmır);
    üzv CSV ixracı alias ilə (`member.edit`-siz müavin/müdir) açıqdır (alt-ağacla məhdud).
16. `my-workload` iş yükü olmayan rollara (Tədris şöbəsi, RİM əməkdaşı, qəyyum) boş səhifə kimi görünür.
17. Semestr yazı əməlləri (`semester_actions.py:155-307`) yalnız açara baxır, əhatəyə yox — hazırda yalnız
    org-wide rollarda olduğundan təhlükəsizdir.
18. İş yükü «təsdiq gözləyir» bildirişi açarı olmayan dekan müavini / koordinatora gedir
    (`workload/workflow.py:430,464`).
19. `unit-exams`: başqa kafedrada əlavə üzvlüyü olan müəllimin imtahanları da düşür (`unit_exams.py:48-55`).
20. İmtahan mərkəzi işçisi `org-members`-də hamının e-poçtunu görür, amma «Tələbələr/Müəllimlər»
    kataloqu ona bağlıdır — ya kataloqu (kontaktsız) ver, ya `org-members`-i bağla.
21. Menyu icazə yığımı (`rbac.py:156`) deaktiv rolu süzmür (panel süzür).

## C. Qəsdən belədir (dəyişmə)

`ikt_rehber` hər menyunu görür (sahib 2026-09-14/21); `alumni` 0 bölmə (giriş bağlı); `legacy-grade-review`,
`system-settings`, `journal-hygiene` yalnız RİM rəhbəri; `exam-score-entry` yalnız mərkəz rəhbəri
(`final_score.entry`); rektor imtahan mərkəzi panellərini görmür; müəllim `analytics` görmür (şəxsi
`statistics`); `groups` bölməsi 2026-09-08-də çıxarılıb; `surveys-inbox` hamıda (auditoriya müəllim/heyəti
də əhatə edir); `semester-opening` / `curriculum-editor` org-wide YALNIZ-OXU (müdafiə oluna bilər).
