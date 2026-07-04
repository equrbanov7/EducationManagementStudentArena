# EMSArena — Elektron Universitet Sistemi: Tam Yol Xəritəsi

**Tarix:** 2026-07-04 · **Status:** dizayn + mərhələli icra (bəziləri artıq tətbiq olunub)
**Kontekst:** Qərbi Kaspi Universiteti (və digər AZ dövlət universitetləri — UNEC, ADA, AzTU) üçün çox-tenantlı elektron universitet.

Bu sənəd **mövcud vəziyyəti** (nə var) və **növbəti addımları** (nə lazımdır) tam xəritələyir. Registrar/curriculum domen modeli üçün əsas mənbə: [`AKADEMIK_DOVR_SISTEMI_DIZAYN_P3-2.md`](AKADEMIK_DOVR_SISTEMI_DIZAYN_P3-2.md). Bu sənəd onun üstünə **tələbə-üzü axını**, **elektron jurnal**, **dərs cədvəli**, **25% / təkrar imtahan qaydası**, **qrup köçürmə** və **imtahana əlavə** hissələrini əlavə edir.

> **Prinsip (P3-2-dən):** hər universitetin qaydaları fərqlidir → bütün model **tenant-konfiqurasiya əsaslıdır** (sərt-kod yox), hər model `organization` FK + RLS daşıyır.

---

## 0. Artıq TƏTBİQ OLUNUB (bu iş dövründə)

| Sahə | Vəziyyət |
|------|----------|
| **Rollar** | 21 rol — rektor, prorektor, dekan, kafedra müdürü, HR, imtahan mərkəzi, müəllim, assistent, **laborant (lab_assistant)**, tyutor, baş tələbə, tələbə + məktəb/kurs-mərkəzi rolları (`default_roles.py`, `core/roles.py`) |
| **Akademik iyerarxiya (unit)** | Fakültə → Kafedra → **İxtisas (specialty)** → **Qrup** (OrgUnit; I1-də tamamlandı) |
| **Fənn = Course** | `Course` (unit=ixtisas/qrup, `period`=AcademicPeriod/semestr); fənn içi = `CourseTopic` + `CourseResource` |
| **Semestr** | `AcademicPeriod` (semester/trimester/quarter/year) |
| **Qeydiyyat provisioning** | Public signup **söndürülüb**; hesablar administrasiya tərəfindən yaradılır ([`ACCOUNT_PROVISIONING.md`](ACCOUNT_PROVISIONING.md)) |
| **İlk-giriş** | Provisional user ilk girişdə email-OTP təsdiqi + öz parolunu qurur (`FirstLoginPasswordMiddleware`, `set_initial_password`) |
| **Kabinet** | Login sonrası profilə/kabinetə landing |
| **İmtahan nüvəsi** | Test imtahanı + live exam + supervision + coding exam (işlək) |
| **Nümunə tenant** | `seed_western_caspian` — tam rol iyerarxiyası + akademik ağac |

## 1. Registrar / curriculum qatı (P3-2 — DİZAYN, tətbiq gözləyir)

P3-2 bu modelləri təyin edir (tətbiq mərhələli):
`AcademicYear`, `Semester`, `Program` (=İxtisas), `Subject` (=Fənn kataloqu), **`Curriculum`** (proqram×qəbul-ili tədris planı), **`CurriculumSubject`** (plan sətri: semestr + `is_elective` + `elective_group`), `CourseOffering` (semestrdə tədris olunan fənn/section), `Enrollment`, `AssessmentScheme`, `GradeComponent`, `FinalGrade`, `ResitRecord`, `StudentAcademicRecord`.

> **Vacib:** istifadəçinin istədiyi "ixtisas → fənlər → seçmə blok → fənn içi" axını üçün **əsas model artıq P3-2-də var** (`CurriculumSubject.is_elective` + `elective_group`). Aşağıdakı §2 həmin modellərin ÜZƏRİNDƏ tələbə-üzü axını təyin edir.

---

## 2. Tələbə akademik axını (istifadəçi tələbi — YENİ)

**Ssenari:** tələbəyə ixtisas təyin olunanda, o ixtisasın tədris planındakı fənləri görməlidir; fənnə klik → fənn içi (mövzular/resurslar); bəzi fənlər **seçmə blokdur** — tələbə blokdan birini seçir, o köçürülür; seçmələr də görünməli və içinə baxıla bilməlidir.

### 2.1 Axın (state → data → görünüş)

```
1. Tələbəyə İxtisas (Program/specialty OrgUnit) + qəbul ili təyin olunur
   → StudentAcademicRecord(program, curriculum) yaradılır (registrar/HR).

2. Sistem cari semestr üçün Curriculum planını oxuyur:
   CurriculumSubject WHERE curriculum=X AND semester=cari
   ├── is_elective=False  → MƏCBURİ fənlər → avtomatik Enrollment yaradılır
   └── is_elective=True   → SEÇMƏ BLOKLARI (elective_group üzrə qruplaşdırılır)

3. Tələbə kabinetində "Fənlərim (bu semestr)" bölməsi:
   ├── Məcburi fənlər (artıq qeydiyyatlı) — kart siyahısı
   └── Seçmə bloklar — hər blok: "N fəndən 1-ni seç" (elective_group + required_choices)
        tələbə seçir → Enrollment(kind="elective") yaradılır.

4. İstənilən fənnə klik → CourseOffering/Course detalı:
   CourseTopic + CourseResource (mövzular, materiallar) — HƏM məcburi HƏM seçilmiş
   fənlər üçün eyni "fənn içi" görünüşü (mövcud course_dashboard pattern-i).
```

### 2.2 Hansı komponent nəyi edir

| Addım | Model | View / UI |
|------|-------|-----------|
| İxtisas təyini | `StudentAcademicRecord` | registrar/HR provisioning ekranı |
| Plan oxunması | `Curriculum` + `CurriculumSubject` | servis: `get_semester_plan(record, semester)` |
| Məcburi auto-enroll | `Enrollment(kind="mandatory")` | signal/servis: `enroll_mandatory_subjects()` |
| Seçmə blok seçimi | `CurriculumSubject(is_elective, elective_group)` → `Enrollment(kind="elective")` | profil bölməsi: "Seçmə fənlər" — blok başına radio/seçim |
| Fənn içi | `Course` + `CourseTopic` + `CourseResource` | mövcud `courses/course_dashboard.html` (yenidən istifadə) |

### 2.3 Yeni model əlavəsi (minimal, P3-2 üstünə)

`CurriculumSubject`-ə (P3-2) əlavə:
```python
elective_group = models.CharField(max_length=50, blank=True)   # eyni blokun fənləri
required_choices = models.PositiveSmallIntegerField(default=1)  # blokdan neçə seçilməli
```
`Enrollment`-a:
```python
kind = models.CharField(choices=[("mandatory","Məcburi"),("elective","Seçmə"),
                                 ("retake","Təkrar")], default="mandatory")
```

### 2.4 Qayda-yoxlaması (validation)
- Tələbə seçmə blokdan tam `required_choices` qədər seçməlidir (nə az, nə çox).
- Seçim müddəti (add/drop window) `Semester`-in registration pəncərəsi ilə məhdudlaşır.
- Qeydiyyat yalnız öz `StudentAcademicRecord.program`-ının planından (RLS + scope yoxlaması).

---

## 3. Elektron jurnal (elektron vedomost)

**Tələb:** müəllim elektron jurnala keçid; tələbə öz qiymətlərinə baxır; hər kəs uyğun səviyyədə görür.

### 3.1 Dizayn
- **Jurnal = `CourseOffering` üzrə qeydiyyatlı tələbələrin `ComponentGrade` roster-i** (P3-2 `GradeComponent` + `ComponentGrade`).
- Müəllim görünüşü: offering → tələbə sətirləri × komponent sütunları (davamiyyət, aralıq, layihə, imtahan) → bal daxil edir → `FinalGrade` avtomatik hesablanır (`AssessmentScheme` çəkiləri).
- Tələbə görünüşü: yalnız ÖZ sətri (komponent balları + yekun + hərf + GPA nöqtəsi).
- İcazə: `grade.input` (müəllim/assistent/laborant), `grade.view` (tələbə öz balı), `grade.publish` (kafedra/imtahan mərkəzi finalizasiya).
- **Audit:** hər bal dəyişikliyi `AuditLog`-a (kim, nə vaxt, köhnə→yeni) — akademik dürüstlük.

### 3.2 UI
- Profil sidebar → "Elektron jurnal" (müəllim üçün offering seçimi → roster grid; artıq mövcud grading UI pattern-ini genişləndirir).
- Tələbə profili → "Qiymətlərim / Transkript" bölməsi (semestr üzrə fənlər + ballar + GPA).

---

## 4. Dərs cədvəli (timetable)

**Tələb:** hər kəs (tələbə/müəllim) öz dərs cədvəlini görsün.

### 4.1 Dizayn (yeni model)
```python
class ScheduleSlot(models.Model):        # bir dərs slotu
    organization = FK; semester = FK(Semester)
    offering = FK(CourseOffering)         # hansı fənn
    group = FK(OrgUnit, limit=GROUP)      # hansı qrup
    instructor = FK(User)                 # müəllim
    weekday = SmallInt (1..7); start_time; end_time
    room = CharField                      # auditoriya
    week_type = choices(all/odd/even)     # üst/alt həftə (opsional)
```
- **Konflikt yoxlaması:** eyni (group | instructor | room) × (weekday, time) təkrarlanmamalı.
- Görünüşlər: tələbə (öz qrupunun cədvəli), müəllim (öz slotları), kafedra (bütün alt-ağac), auditoriya-baxışı.
- İxrac: iCal/PDF (opsional).

### 4.2 UI
- Profil sidebar → "Dərs cədvəli" — həftəlik grid (rol-uyğun scope: tələbə=qrup, müəllim=öz, dekan=fakültə).

---

## 5. Kəsilən tələbə / 25% / təkrar imtahan qaydası

**AZ konteksti:** komponent-əsaslı qiymətləndirmədə imtahan minimum həddi var (məs. yekun imtahandan min 17/50, ümumi keçid 51/100). Kəsilən tələbə üçün **təkrar imtahan (resit)** və ya növbəti semestr **təkrar qeydiyyat (retake)**.

### 5.1 Dizayn (P3-2 üstünə)
- `AssessmentScheme`: `pass_threshold` (məs. 51), `min_exam_score` (imtahan minimumu), komponent çəkiləri.
- Yekun hesablanır → `FinalGrade`. Keçmirsə → `ResitRecord` (təkrar imtahan hüququ) yaradılır.
- **25% qayda** (universitetə görə konfiqurasiya): imtahan komponentinin çəkisi/minimumu `GradeComponent.weight` + `AssessmentScheme.min_exam_score` ilə. "Kəsilən tələbə 25% imtahan" — imtahanın yekunda payı 25% olan sxem → `GradeComponent(weight=25, kind="exam")`.
- Təkrar imtahan öz `Exam`/`CourseOffering`-inə bağlanır; nəticə `ResitRecord.score` → `FinalGrade` yenidən hesablanır.

### 5.2 Axın
```
FinalGrade < pass_threshold  VƏ YA  exam_score < min_exam_score
   → ResitRecord(status="eligible") yaradılır
   → tələbə təkrar imtahana yazılır (imtahan mərkəzi/kafedra açır)
   → yeni bal → FinalGrade yenilənir → GPA yenidən hesablanır.
```

---

## 6. Qrup yazılma / qrupdan-qrupa köçürmə

**Tələb:** "al qrupa yazılma, digər qrupa əlavə olunma".

### 6.1 Dizayn (mövcud modellər üstünə)
- Tələbənin qrupu = `Membership(scope_unit=GROUP OrgUnit)` (artıq var) VƏ `StudentAcademicRecord.group`.
- **Köçürmə (transfer):** registrar/dekan tələbənin `scope_unit`-ini A qrupundan B qrupuna dəyişir → audit + tarix (`StatusTransition` bənzəri).
- **Əlavə (multi-group):** bir tələbə birdən çox qrupda ola bilər (məs. seçmə fənn başqa qrupla) → əlavə `Membership` və ya `Enrollment` səviyyəsində qrup.
- Köçürmə qeydiyyatı (`Enrollment`) və cədvəli (`ScheduleSlot`) uyğunlaşdırılmalıdır (köhnə qrupun məcburi fənləri → yeni qrup).

### 6.2 UI
- Registrar/HR/dekan ekranı: tələbə → "Qrupu dəyiş" (səbəb + tarix + audit).

---

## 7. İmtahana tələbə əlavə etmə

**Tələb:** "imtahanda əlavə etmə əlavə kimisə".

### 7.1 Dizayn
- İmtahan iştirakçıları `StudentGroup` / `Enrollment` üzərindən avtomatik gəlir (offering-ə qeydiyyatlı tələbələr).
- **Əl ilə əlavə:** müəllim/imtahan mərkəzi imtahana ayrıca tələbə əlavə edə bilər (məs. təkrar imtahan, köçmə tələbə) — mövcud exam-group/attempt-provisioning genişləndirilir.
- İcazə: `exam.manage` / `exam.host`. Audit yazılır.

---

## 8. Universitetə uyğun olmayan hissələrin gizlədilməsi

**Tələb:** "diger uni sisteminde olmamali olan yerleri yigisdir gorunmesin".

- Public signup → gizlədildi (H1). ✔
- Marketing "Pulsuz başla / Qeydiyyat" CTA-ları → login-ə çevrildi (H1). ✔
- **Növbəti:** tenant `org_type=UNIVERSITY` olduqda kurs-mərkəzi/fərdi-istifadəçi menyularını (məs. "abunə ol", pulsuz-trial) gizlət; profil sidebar-ını rol + org_type-a görə filtrlə (mövcud `allowed_sections` genişləndirilir).
- Blog/marketing səhifələri yalnız anonim üçün; authenticated universitet istifadəçisi birbaşa kabinetə (artıq I3-də landing profilə).

---

## 9. Mərhələli icra planı (asılılıq sırası)

| Faza | Əhatə | Risk | Demo-dan əvvəl? |
|------|-------|------|-----------------|
| **U0** (bitdi) | Rollar, unit iyerarxiya, provisioning, ilk-giriş, seed | — | ✔ |
| **U1** | Registrar nüvəsi: `AcademicYear`, `Semester`, `Program`, `Subject`, `Curriculum`, `CurriculumSubject` (P3-2 §5.1-5.2) | orta (migration) | sonra |
| **U2** | `CourseOffering` + `Enrollment` + tələbə akademik axını (§2) | orta | sonra |
| **U3** | `AssessmentScheme` + `GradeComponent` + elektron jurnal (§3) + 25%/resit (§5) | orta-yüksək | sonra |
| **U4** | Dərs cədvəli `ScheduleSlot` (§4) | aşağı-orta | sonra |
| **U5** | Transkript + GPA + status state-machine (P3-2 §6-8) | yüksək | sonra |
| **U6** | Qrup köçürmə (§6) + imtahana əlavə (§7) + org_type UI təmizliyi (§8) | aşağı-orta | qismən |

**Hər faza:** additiv migration (nullable/default), `organization` FK + RLS, xarakteristik test + `-m postgres` izolyasiya, tenant-konfiqurasiya. Heç bir faza mövcud imtahan nüvəsini sındırmır (demo təhlükəsizliyi).

## 10. Növbəti konkret addım (təsdiqdən sonra)
1. **U1 migration**-ları (registrar modelləri) — P3-2 §5-dəki modelləri `apps/organizations` (və ya yeni `apps/registrar`) altında yarat.
2. `seed_western_caspian`-a curriculum + subjects + bir seçmə blok əlavə et (demo datası).
3. Tələbə profilinə "Fənlərim / Seçmə fənlər" bölməsi (§2 axını).
4. Elektron jurnal grid-i (§3) — mövcud grading UI-dan genişləndir.
