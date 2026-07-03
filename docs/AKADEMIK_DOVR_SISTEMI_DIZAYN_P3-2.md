# EMSArena — Akademik Dövr Sistemi: Tam Dizayn və Tətbiq Planı (P3-2)

**Tarix:** 4 İyul 2026
**Status:** DİZAYN (tətbiq sonra — bu sənəd təsdiqdən sonra fazalı icra olunur)
**Mənbə audit:** `EMSArena_Tam_Texniki_Audit_2026-07-03.docx` (BUSINESS / P3-2)
**Kontekst:** EMSArena Azərbaycanda **elektron universitet** sistemi kimi istifadə olunacaq. Bu sənəd tam akademik dövrü (qəbuldan məzuniyyətə) modelləşdirir.

> **Vacib prinsip:** EMSArena çox-tenantlıdır və hər universitetin öz qaydaları var (Xəzər, UNEC, AzTU və s. fərqli qiymətləndirmə siyasətlərinə malikdir). Ona görə **model konfiqurasiya-əsaslı** olmalıdır — sərt kodlanmış qaydalar yox, hər təşkilat (tenant) üçün tənzimlənən sxemlər. Bütün yeni modellər `organization` FK daşıyır (RLS tenant izolyasiyası).

---

## 1. İcmal və əhatə

Hazırda EMSArena güclü **imtahan/LMS** nüvəsinə malikdir (Course, StudentGroup, Exam, ExamAttempt, rollar), lakin **formal registrar (qeydiyyat) qatı yoxdur**: akademik il/semestr, tədris planı (curriculum), kredit-daşıyan fənlər, semestr üzrə fənn təklifi, tələbə qeydiyyatı, komponent-əsaslı qiymətləndirmə, transkript və ÜOMG (GPA), tələbə status idarəetməsi.

Bu sənəd həmin qatı **mövcud arxitekturanı sındırmadan** əlavə edir və mərhələli miqrasiya planı verir.

## 2. Azərbaycan ali təhsil konteksti (araşdırma ilə əsaslandırılmış)

**Kredit sistemi:** Azərbaycan 2005-də Boloniya prosesinə qoşulub; 2009 Təhsil Qanunu ilə ECTS, üç-pilləli təhsil və diplom əlavəsi (diploma supplement) rəsmiləşib.

**Dərəcələr:**
- **Bakalavr** — 4–5 il, 240–300 ECTS (tibb 300–360).
- **Magistr** — 1.5–2 il, 90–120 ECTS.
- **Doktorantura** — Fəlsəfə doktoru (PhD) + Elmlər doktoru.

**Semestr strukturu:** akademik il = payız + yaz semestrləri (bəzən yay). Hər semestr ~30 ECTS, il ~60 ECTS.

**100-ballıq qiymətləndirmə (tipik dövlət modeli):**
- **Semestr (cari) — maks. 50 bal:** davamiyyət maks. 10 + seminar/laboratoriya fəallığı 20 + kollokvium 30.
- **İmtahan (yekun) — maks. 50 bal:** keçid üçün **minimum 17 bal** (imtahandan 17-dən aşağı → fənn kəsilmiş sayılır).
- **Yekun = cari + imtahan (0–100).**

**Hərfi qiymət (ECTS-uyğun, tipik):** A (91–100), B (81–90), C (71–80), D (61–70), E (51–60), F (<51 = kəsr). *Universitetlərarası fərqlər var — konfiqurasiya edilməlidir.*

**Keçid həddi və təkrar imtahan:** ümumi ≥51 (bəzi universitetlərdə bakalavr üçün 60) tələb olunur; hədddən aşağı → **təkrar imtahan / borc (təkrar fənn)**. Bəzi hallarda 57–59 üçün əlavə cəhd verilir.

**ÜOMG (Ümumi Orta Müvəffəqiyyət Göstəricisi = GPA):** kredit-çəkili orta; təqaüd, məzuniyyət, xaric qərarlarında istifadə olunur.

**Nəticə:** qiymətləndirmə komponentləri, çəkilər, keçid həddi, hərfi-qiymət cədvəli, ÜOMG düsturu — **hamısı tenant (universitet) səviyyəsində konfiqurasiya olunmalıdır.**

## 3. Referans sistemlər

- **UNEC e-University / digər AZ elektron-universitet portalları** — tələbə kabineti, elektron vedomost (qiymət cədvəli), transkript, təqaüd hesablanması.
- **Moodle** — kurs/qiymət kitabçası (gradebook) komponent-çəki modeli; bizim AssessmentScheme buna bənzəyir.
- **Ellucian Banner / Oracle PeopleSoft Campus Solutions** — klassik registrar modeli: Term → Course Catalog → Section → Enrollment → Grade Roll → Transcript. Bizim dizayn bu sınanmış modeli izləyir.
- **ECTS / Diploma Supplement** — kredit-transfer, hərfi qiymət ekvivalentliyi.

## 4. Mövcud EMSArena — boşluq analizi

**Var:**
- `Organization` (universitet = tenant), `Institution`, `Country`.
- Fakültə / Kafedra strukturu (structure_views).
- `Course` + `CourseTopic/Resource`, `CourseMembership`, `CourseInstructor`, `CourseGroup` (courses).
- `StudentGroup` (exams) — tələbə qrupu + müəllimlər.
- `Exam` / `ExamAttempt` — imtahan icrası + `total_duration_minutes`, nəticə hesablanması.
- Rollar: superadmin, org owner/admin, **rector, prorector, dean (dekan), department_head (kafedra müdiri), exam_center, hr**, teacher, assistant_teacher, student, lead_student, staff, member.
- RBAC (core/permissions), RLS tenant izolyasiya, i18n, audit.

**Çatmır (bu dizaynın əlavə etdiyi):**
- Akademik il / semestr / akademik təqvim.
- İxtisas/proqram (Program) + tədris planı (Curriculum).
- Kredit-daşıyan **Fənn (Subject)** — mövcud `Course` LMS-kursudur, formal fənn deyil.
- Semestr üzrə **fənn təklifi (CourseOffering/Section)**.
- Semestr üzrə **qeydiyyat (Enrollment)**.
- Konfiqurasiya olunan **qiymətləndirmə sxemi + komponentlər**.
- **Qiymət (Grade)**, transkript, **ÜOMG (GPA)**.
- **Tələbə akademik status state-machine** (aktiv / akad. məzuniyyət / xaric / məzun / köçürülmə).
- **Təkrar imtahan / borc** qeydiyyatı.

**Xəritələmə qərarı:** mövcud `Course`-u dağıtmırıq. Yeni `Subject` (kredit-daşıyan kataloq vahidi) əlavə edirik; `CourseOffering` bir Subject-i semestrdə konkret qrupa/müəllimə bağlayır və mövcud `Course`/`Exam`/`StudentGroup` ona **əlaqələndirilir** (aşağıda §11).

## 5. Hədəf domen modeli

Bütün modellər: `organization` FK (RLS), `created_at/updated_at`, uyğun indekslər, `db_index` status/tarix sahələrində. Aşağıda Django-pseudokod (yekun sahələr icra zamanı dəqiqləşir).

### 5.1 Dövr və təqvim

```python
class AcademicYear(models.Model):            # Akademik il
    organization = FK(Organization)
    name = Char("2025–2026")
    start_date = Date; end_date = Date
    is_current = Bool(db_index=True)          # tenant üzrə bir cari il
    # Meta: unique(organization, name)

class Semester(models.Model):                # Semestr / Term
    organization = FK(Organization)
    academic_year = FK(AcademicYear, related_name="semesters")
    kind = Char(choices=["autumn","spring","summer"])  # payız/yaz/yay
    start_date = Date; end_date = Date
    enrollment_opens_at = DateTime; enrollment_closes_at = DateTime
    exam_period_start = Date; exam_period_end = Date
    state = Char(choices=["planned","enrollment","active","exams","grading","closed"], db_index=True)
    # Meta: unique(academic_year, kind)

class AcademicCalendarEvent(models.Model):   # Akademik təqvim hadisəsi
    organization = FK; semester = FK(null=True)
    title = Char; event_type = Char(["lecture_period","exam","holiday","deadline","resit"])
    starts_at = DateTime; ends_at = DateTime
    scope = Char(["org","faculty","program","group"])  # kimə aiddir
```

### 5.2 Proqram, tədris planı, fənn

```python
class Program(models.Model):                 # İxtisas / Proqram
    organization = FK; faculty = FK(Faculty); department = FK(Kafedra, null=True)
    name = Char; code = Char                  # məs. "Kompüter elmləri"
    degree_level = Char(["bachelor","master","phd"])
    duration_semesters = PositiveInt          # bakalavr=8, magistr=3–4
    total_ects = PositiveInt                  # 240 / 120 ...
    language = Char(choices=EXAM_LANGUAGE_CHOICES)

class Subject(models.Model):                 # Fənn (kataloq vahidi)
    organization = FK; department = FK(Kafedra, null=True)
    code = Char("CS101"); name = Char
    ects_credits = PositiveInt                # ECTS kredit
    lecture_hours = PositiveInt; seminar_hours = PositiveInt; lab_hours = PositiveInt
    default_assessment_scheme = FK(AssessmentScheme, null=True)

class Curriculum(models.Model):              # Tədris planı (proqram × qəbul ili)
    organization = FK; program = FK(Program)
    entry_year = FK(AcademicYear)             # "2025 qəbulu üçün plan"
    is_active = Bool
    # Meta: unique(program, entry_year)

class CurriculumSubject(models.Model):       # Plan sətri: hansı semestrdə hansı fənn
    curriculum = FK(Curriculum, related_name="rows")
    subject = FK(Subject)
    semester_number = PositiveInt(1..N)       # planın neçənci semestri
    is_elective = Bool                        # seçmə / məcburi
    prerequisites = M2M(Subject, blank=True)  # ilkin şərt fənlər
```

### 5.3 Fənn təklifi və qeydiyyat

```python
class CourseOffering(models.Model):          # Semestrdə tədris olunan fənn (Section)
    organization = FK
    subject = FK(Subject); semester = FK(Semester)
    program = FK(Program, null=True)
    student_group = FK("exams.StudentGroup", null=True)   # mövcud qrupa bağlanır
    lms_course = FK("courses.Course", null=True)          # mövcud LMS kursu (materiallar)
    assessment_scheme = FK(AssessmentScheme)
    capacity = PositiveInt(null=True)
    state = Char(["draft","open","closed","graded"], db_index=True)
    # instruktorlar: mövcud CourseInstructor və ya ayrıca OfferingInstructor

class OfferingInstructor(models.Model):      # Fənni tədris edən müəllim(lər)
    offering = FK(CourseOffering, related_name="instructors")
    teacher = FK(User); role = Char(["lecturer","seminar","lab"])

class Enrollment(models.Model):              # Tələbənin semestrdə fənnə qeydiyyatı
    organization = FK
    student = FK(User); offering = FK(CourseOffering, related_name="enrollments")
    enrolled_at = DateTime; status = Char(["enrolled","withdrawn","completed"], db_index=True)
    attempt_kind = Char(["first","retake"])   # ilk / təkrar (borc)
    # Meta: unique(student, offering)
```

### 5.4 Qiymətləndirmə sxemi və qiymətlər

```python
class AssessmentScheme(models.Model):        # Konfiqurasiya olunan qiymətləndirmə modeli
    organization = FK; name = Char("Standart 50+50")
    max_total = PositiveInt(default=100)
    passing_total = Decimal(default=51)       # keçid həddi (tenant görə 51/60)
    min_final_exam = Decimal(default=17)      # imtahandan minimum
    is_default = Bool

class GradeComponent(models.Model):          # Sxem komponenti (çəki)
    scheme = FK(AssessmentScheme, related_name="components")
    kind = Char(["attendance","seminar","lab","colloquium","coursework","final_exam"])
    label = Char("Kollokvium")
    max_points = Decimal                      # məs. davamiyyət=10, seminar=20, kollokvium=30, imtahan=50
    order = PositiveInt
    exam = FK("exams.Exam", null=True)        # bu komponent bir EMSArena imtahanı ilə doldurula bilər

class LetterGradeBand(models.Model):         # 100-bal → hərf + GPA nöqtəsi (tenant görə)
    scheme = FK(AssessmentScheme, related_name="bands")
    letter = Char("A"); min_score = Decimal(91); max_score = Decimal(100)
    gpa_points = Decimal(4.0); is_passing = Bool

class ComponentGrade(models.Model):          # Bir tələbənin bir komponent üzrə balı
    enrollment = FK(Enrollment, related_name="component_grades")
    component = FK(GradeComponent)
    points = Decimal(null=True)               # verilmiş bal
    graded_by = FK(User, null=True); graded_at = DateTime(null=True)
    source_attempt = FK("exams.ExamAttempt", null=True)  # imtahandan avtomatik
    # Meta: unique(enrollment, component)

class FinalGrade(models.Model):              # Fənn üzrə yekun qiymət (hesablanan)
    enrollment = OneToOne(Enrollment, related_name="final_grade")
    total_points = Decimal                    # Σ komponentlər
    letter = Char; gpa_points = Decimal; is_passing = Bool
    state = Char(["provisional","published","appealed","final"], db_index=True)
    published_at = DateTime(null=True)
```

### 5.5 Transkript, ÜOMG, təkrar

```python
# Transkript hesablanan görünüşdür (materialized view / servis); ayrıca cədvəl ŞƏRT deyil.
# Semestr/kumulyativ ÜOMG servis-səviyyəsində FinalGrade + Subject.ects_credits-dən hesablanır:
#   GPA = Σ(gpa_points_i × ects_i) / Σ(ects_i)   (yalnız keçilmiş/qiymətlənmiş fənlər)

class ResitRecord(models.Model):             # Təkrar imtahan / borc
    organization = FK; enrollment = FK(Enrollment)
    scheduled_for = FK(Semester, null=True); scheduled_at = DateTime(null=True)
    resit_exam = FK("exams.Exam", null=True)
    result_points = Decimal(null=True); resolved = Bool
```

### 5.6 Tələbə akademik statusu

```python
class StudentAcademicRecord(models.Model):   # Tələbənin universitetdəki akademik profili
    organization = FK; student = OneToOne(User) və ya FK
    program = FK(Program); curriculum = FK(Curriculum)
    current_semester_number = PositiveInt
    status = Char(["applicant","enrolled","active","academic_leave",
                   "expelled","graduated","transferred_out"], db_index=True)
    entry_year = FK(AcademicYear); expected_graduation = FK(AcademicYear, null=True)
    cumulative_gpa = Decimal(null=True)       # keş; hesablamadan yenilənir

class StatusTransition(models.Model):        # Status keçidləri audit-i
    record = FK(StudentAcademicRecord, related_name="transitions")
    from_status = Char; to_status = Char
    reason = Text; effective_from = Date
    approved_by = FK(User, null=True); created_at = DateTime
```

## 6. Tələbə status state-machine

```
applicant ──qəbul──▶ enrolled ──qeydiyyat──▶ active
   active ⇄ academic_leave        (dekan/rektor təsdiqi ilə hər iki istiqamət)
   active ──proqram tamamlandı──▶ graduated
   active ──akademik uğursuzluq / intizam──▶ expelled
   active ──köçürmə──▶ transferred_out
```

**Qaydalar:** hər keçid `StatusTransition` yaradır (səbəb + təsdiqləyən + tarix); yalnız icazəli rollar tetikləyə bilər (dekan/exam_center/rektor); geriyə-dönməz keçidlər (graduated/expelled) əlavə təsdiq tələb edir. State-machine servis qatında mərkəzləşir (icazəsiz keçid rədd).

## 7. Qiymətləndirmə və qiymət hesablanması

1. Müəllim komponent ballarını daxil edir (davamiyyət/seminar/kollokvium) → `ComponentGrade`. Kollokvium/final bir `Exam`-a bağlıdırsa, `ExamAttempt` nəticəsindən **avtomatik** doldurulur (`source_attempt`).
2. İmtahan komponenti (final_exam) EMSArena imtahan axını ilə keçirilir; nəticə komponent balına çevrilir.
3. Servis yekunu hesablayır: `total = Σ points`; **`min_final_exam` yoxlanışı** (imtahandan aşağı → kəsr, hərf=F); `LetterGradeBand`-dən hərf + gpa; `is_passing`.
4. `FinalGrade` "provisional" → müəllim/dekan təsdiqindən sonra "published"; apellyasiya pəncərəsi (mövcud `appeals` app ilə); sonra "final".
5. Keçməyən fənn → `ResitRecord` (təkrar imtahan) və ya növbəti semestrdə təkrar `Enrollment(attempt_kind="retake")`.

**Konfiqurasiya:** komponent çəkiləri, keçid həddi, min-imtahan, hərf cədvəli — hamısı `AssessmentScheme` üzərindən tenant-a görə.

## 8. ÜOMG / GPA

Kredit-çəkili: `GPA = Σ(gpa_points × ects) / Σ(ects)`. Semestr ÜOMG-si (bir semestr) + kumulyativ ÜOMG (bütün keçilmiş fənlər). Yalnız qiymətlənmiş/keçilmiş fənlər daxil (siyasət tenant-a görə: kəsr fənlər F=0 kimi daxil olsun/olmasın — konfiqurasiya). Nəticə `StudentAcademicRecord.cumulative_gpa`-da keşlənir, `FinalGrade` dəyişəndə yenilənir (signal/servis).

## 9. Qeydiyyat (enrollment) workflow-u

Semestr `enrollment` state-inə keçəndə: tələbə tədris planından (məcburi fənlər avtomatik) + seçmə fənlərdən (elective) `Enrollment` yaradır; ilkin-şərt (prerequisite) yoxlanışı; qrup/tutum (capacity) yoxlanışı; borc fənləri `attempt_kind="retake"` ilə. Dekan/exam_center təsdiqi (opsional). Qeydiyyat bağlananda offering-lər "open" olur.

## 10. Mövcud EMSArena ilə inteqrasiya

- **Exam → GradeComponent:** mövcud `Exam`/`ExamAttempt` dəyişmir; `GradeComponent.exam` və `ComponentGrade.source_attempt` ilə körpü qurulur (imtahan nəticəsi avtomatik komponent balına). Bu, imtahan-bütövlüyü testlərini (bax `test_answer_integrity.py`, `test_attempt_timer.py`) toxunmadan saxlayır.
- **Course (LMS) → CourseOffering.lms_course:** materiallar/tapşırıqlar mövcud `Course`-da qalır; offering ona istinad edir.
- **StudentGroup → CourseOffering.student_group:** mövcud qruplar semestr təklifinə bağlanır.
- **Fakültə/Kafedra → Program/Subject:** mövcud struktur Program/Subject üçün valideyn.
- **RBAC:** yeni icazələr (aşağıda §12); registrar/exam_center rolu qeydiyyat + vedomost; dekan təsdiq.
- **RLS/tenant:** bütün yeni modellər `organization` FK + RLS siyasəti (mövcud pattern).
- **i18n:** bütün istifadəçi-mətnləri `pgettext` (bu sessiyada qurulan konvensiya).
- **appeals:** `FinalGrade` "appealed" state-i mövcud apellyasiya axını ilə.

## 11. Miqrasiya strategiyası (təhlükəsiz, fazalı)

Bütün yeni cədvəllər **əlavədir** (mövcud data sındırılmır). Hər faza öz migration + testləri ilə.
- Yeni FK-lar `null=True` başlayır; mövcud data üçün **data-migration** ilə doldurulur (məs. cari il/semestr yaradılır, mövcud StudentGroup-lar offering-ə bağlanır — opsional).
- Geriyə-uyğunluq: köhnə imtahan/kurs axınları toxunulmur; akademik qat onların üstündə işləyir.
- RLS: hər yeni cədvəl üçün RLS siyasəti migration-ı (mövcud `organizations` RLS pattern-i ilə).

## 12. RBAC əlavələri

- **registrar / exam_center**: semestr/təqvim idarəsi, offering yaratma, qeydiyyat, vedomost, transkript.
- **dekan (dean)**: proqram/tədris planı təsdiqi, status keçidləri (akad. məzuniyyət/xaric), qiymət təsdiqi.
- **kafedra müdiri (department_head)**: fənn/subject idarəsi, müəllim təyinatı.
- **müəllim (teacher)**: yalnız öz offering-lərində komponent balı daxil etmə.
- **tələbə (student)**: yalnız öz qeydiyyat/qiymət/transkript/ÜOMG-si.
Yeni icazə açarları: `academic.year.manage`, `curriculum.manage`, `subject.manage`, `offering.manage`, `enrollment.manage`, `grade.enter`, `grade.publish`, `transcript.view`, `student.status.manage`. Mərkəzi RBAC-a (core/permissions) əlavə.

## 13. Hesabatlar

- **Transkript / akademik arayış** (tələbə üzrə, PDF — mövcud pdf skill/DOCX export).
- **Vedomost (qiymət cədvəli)** offering üzrə (Excel export — mövcud pattern).
- **Statistika**: keçid/kəsr faizi, orta ÜOMG, fənn/proqram üzrə uğur; mövcud dashboard/statistika qatına inteqrasiya.
- **Diploma supplement** (ECTS).

## 14. Fazalı tətbiq yol xəritəsi

- **Faza 1 — Dövr & təqvim:** `AcademicYear`, `Semester`, `AcademicCalendarEvent` + admin + RLS + testlər. (Kiçik, təhlükəsiz təməl.)
- **Faza 2 — Kataloq & plan:** `Program`, `Subject`, `Curriculum`, `CurriculumSubject`. Fakültə/Kafedra ilə bağlanma.
- **Faza 3 — Təklif & qeydiyyat:** `CourseOffering`, `OfferingInstructor`, `Enrollment` + qeydiyyat workflow. Mövcud Course/StudentGroup/Exam körpüləri.
- **Faza 4 — Qiymətləndirmə:** `AssessmentScheme`, `GradeComponent`, `LetterGradeBand`, `ComponentGrade`, `FinalGrade` + imtahan→komponent avtomatlaşdırma + apellyasiya.
- **Faza 5 — Transkript/ÜOMG/status:** hesablama servisləri, `StudentAcademicRecord` + state-machine, `ResitRecord`, hesabatlar/PDF.
- **Faza 6 — RBAC/UI/hesabatlar cilası** + statistika inteqrasiyası.

Hər faza: model → migration (əlavə, null-safe) → RLS → servis → RBAC → test (red→green) → i18n → UI.

## 15. Açıq suallar (qərar tələb edir)

1. Keçid həddi: 51, yoxsa 60 (bakalavr)? Tenant-görə default nə olsun?
2. Kəsr fənlər ÜOMG-yə F=0 kimi daxil olsun, yoxsa yalnız keçilənlər?
3. `StudentAcademicRecord.student` — `User`-a OneToOne, yoxsa (bir istifadəçi bir neçə proqram/universitet) üçün FK? (Çox-tenant → yəqin FK + unique(organization, student, program).)
4. Seçmə fənn (elective) seçimi tələbə tərəfindən, yoxsa dekan təyinatı?
5. Mövcud `Course` bəzi hallarda "fənn" kimi istifadə olunubmu? Data-miqrasiya lazımdırmı, yoxsa yalnız yeni məlumat üçün?
6. Modul yerləşməsi: yeni `apps/academics/` app, yoxsa mövcud `organizations`/`courses` genişləndirilsin? (Tövsiyə: **yeni `apps/academics/`** — təmiz domen sərhədi, AGENTS.md modul-ölçüsü qaydasına uyğun.)

## 16. Risklər

- **Sxem böyüklüyü:** çox yeni cədvəl; fazalı icra + null-safe migration şərtdir.
- **Performans:** transkript/ÜOMG hesablanması ağır ola bilər → keş (StudentAcademicRecord.cumulative_gpa) + material-view/snapshot.
- **Tenant izolyasiya:** hər yeni cədvəldə RLS siyasəti unudulmamalı (audit checklist).
- **Mövcud imtahan axınına təsir:** körpü modelləri ilə minimuma endirilir; imtahan-bütövlüyü testləri qorunur.
- **Universitetlərarası fərqlər:** sərt-kodlama yox, `AssessmentScheme`/`LetterGradeBand` konfiqurasiyası.

## 17. Növbəti addım

Bu dizayn təsdiqləndikdən sonra **Faza 1**-dən başlanır (AcademicYear/Semester — kiçik, təhlükəsiz təməl). Hazırkı prioritet işlər (P0-1 daxil) bitdikdən sonra bu roadmap ayrıca icra planına çevrilir.

---

## Mənbələr

- [GDU — Qiymətləndirmə Konsepsiyası (PDF)](https://gdu.edu.az/wp-content/uploads/2024/03/GDU-Qiym%C9%99tl%C9%99ndirm%C9%99-Konsepsiyasi.pdf)
- [AzTU — Qiymətləndirmə və imtahanın təşkili qaydaları (PDF)](https://www.aztu.edu.az/web_admin/upload/files/aztu.edu.az/menus/4-2025/Qiym%C9%99tl%C9%99ndirm%C9%99%20v%C9%99%20imtahan%C4%B1n%20t%C9%99%C5%9Fkili%20qaydalar%C4%B1-%20(1).pdf)
- [Dövlət İmtahan Mərkəzi — Yekun qiymətləndirmə](https://dim.gov.az/az/fealiyyet/qebul-ve-imtahanlar/yekun-qiymetlendirme)
- [Xəzər Universitetinin Qiymətləndirmə Siyasəti](https://khazar.org/az/item/149)
- [AzEdu — Ali və orta məktəblərdə qiymətləndirmə müqayisəsi](https://azedu.az/az/news/101321/ali-ve-orta-mekteblerde-qiymetlendirme-azerbaycan-ve-xarici-olkelerin-muqayisesi)
- [UNEC — Təqaüdlər necə müəyyənləşdirilir](https://unec.edu.az/teqaudler-nece-mueyyenlesdirilir/)
- [WENR — Bologna-Inspired Education Reform in Central Asia](https://wenr.wes.org/2015/05/bologna-inspired-education-reform-central-asia)
- [AACRAO EDGE — Azerbaijan](https://www.aacrao.org/edge/country/azerbaijan)
- [ENIC-NARIC — Azerbaijan](https://www.enic-naric.net/page-Azerbaijan)
