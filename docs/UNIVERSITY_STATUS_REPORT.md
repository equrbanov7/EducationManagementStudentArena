# Elektron Universitet — Vəziyyət Hesabatı və Qalan İşlər

**Tarix:** 2026-07-04 · **Tenant:** Qərbi Kaspi Universiteti · **Branch:** Develop (CI yaşıl)

Bu hesabat sistemin **hazırkı vəziyyətini** (nə işləkdir) və **elektron universitet
üçün qalan işləri** (prioritet + effort + risk ilə) tam xəritələyir. Mənbə: kod
auditi + [`UNIVERSITY_SYSTEM_ROADMAP.md`](UNIVERSITY_SYSTEM_ROADMAP.md).

---

## 1. Xülasə (bir baxışda)

**Möhkəm təməl var:** çox-tenant + RLS, rol/iyerarxiya, provisioning, bir-login
kabinet marşrutu, akademik plan (registrar) + Boloniya kredit/qayıb + tələbə
"Fənlərim" kabineti, imtahan nüvəsi. **Nüvə akademik funksiyalar hələ yoxdur:**
elektron jurnal/qiymətləndirmə (U3), dərs cədvəli (U4), transkript/GPA (U5),
qrup köçürmə (U6) və **registrar üçün web idarəetmə UI-si**.

Faza tamamlanması: **U0 ✅ · U1 ✅ · U2 ✅ · U2-UI ✅ · U3–U6 ⏳ (yalnız dizayn)**

---

## 2. MÖVCUD — nə işləkdir (DONE)

### 2.1 Platforma / infrastruktur
- **Çox-tenant + PostgreSQL RLS** — bütün registrar cədvəlləri tenant-izolyasiya (postgres testlərlə təsdiq).
- **21 rol** + akademik iyerarxiya (Fakültə → Kafedra → İxtisas → Qrup) + **scope enforcement** (hər rol öz alt-ağacı).
- **Provisioning** — public signup söndürülüb; hesablar admin tərəfindən yaradılır; **ilk-giriş OTP** (email təsdiqi + parol qurma).
- **Bir login → rol-aware kabinet** (`/kabinet/`): tədris heyəti → müəllim kabineti; tələbə + digər rollar → vahid kabinet. *(bu iş dövründə)*
- **Login redizayn + branding** — Qərbi Kaspi Universiteti (logo + 4 dil), köhnə "EMSArena" izləri təmizləndi. *(bu iş dövründə)*
- **Demo seed** — 17 rol + superadmin, dev Postgres-də birbaşa login işlək.
- **İmtahan nüvəsi** — test + live + coding exam + supervision (işlək).
- **CI** — 11 job yaşıl, 4 dil i18n, lint/module-boundary/RLS gate-ləri.

### 2.2 Registrar / akademik plan (U1 + U2 + U2-UI)
| Model | Var? | Qeyd |
|-------|------|------|
| `Program` (ixtisas), `Subject` (fənn), `Curriculum`, `CurriculumSubject` | ✅ | tədris planı + seçmə blok (`is_elective`, `elective_group`) |
| `StudentAcademicRecord` | ✅ | tələbə ↔ ixtisas/qrup/curriculum |
| `CourseOffering`, `Enrollment`, `GroupElectiveChoice` | ✅ | semestr fənni + qeydiyyat + qrup seçmə qərarı |
| **Boloniya ECTS** (`Program.ects_total`, `Subject.ects`) | ✅ | məzuniyyət kredit tərəqqisi |
| **Qayıb limiti** (`absence_limit_percent`, `lesson_hours`, `absence_hours`) | ✅ | 25% qayda → "imtahana buraxılmır" |
| Servislər (auto-enroll, qrup seçmə, kredit, eligibility) | ✅ | `apps/registrar/services.py` |
| Tələbə **"Fənlərim"** kabineti | ✅ | kredit barı + qayıb badge + seçmə blok |
| Django admin (Program/Subject/Curriculum/Record/Offering) | ✅ | yalnız admin — web UI yox |

---

## 3. QALAN İŞLƏR (prioritet sırası ilə)

### 🔴 KRİTİK boşluqlar (real istifadə üçün mütləq — nüvəni tamamlayır)

**K1. Fənn ↔ Kurs məzmunu körpüsü**
`CourseOffering.course` nullable-dır və seed-də doldurulmur → tələbə "Fənlərim"də
fənnə klik edəndə **real fənn içinə (mövzu/resurs) çatmır**. Registrar planı ilə
`courses` (məzmun) arasında bağ qurulmalı: offering açılanda uyğun `Course`
yaradılıb/bağlanmalı, kabinetdə "fənn içi" linki işləməli.
· Effort: **orta** · Risk: aşağı · Dəyər: yüksək (mövcud "Fənlərim"i tamamlayır)

**K2. Davamiyyət (attendance) qeydiyyatı**
`Enrollment.absence_hours` sahəsi var, amma **müəllimin qayıb işarələməsi üçün
UI/servis yoxdur** (yalnız seed doldurur). Qayıb/imtahan limitinin real işləməsi
üçün müəllim jurnalında davamiyyət qeydiyyatı lazımdır.
· Effort: **orta** · Risk: aşağı · Dəyər: yüksək

**K3. Registrar provisioning web UI**
Hazırda Program/Subject/Curriculum yaratma, tələbəyə ixtisas/qrup təyini,
offering açma, qrup seçmə qərarı — **yalnız Django admin + seed** ilə mümkündür.
Registrar/HR/dekan üçün **web idarəetmə ekranları yoxdur** (`apps/registrar`-da
`urls.py` yoxdur). Real əməliyyat üçün ən vacib boşluq.
· Effort: **yüksək** · Risk: orta · Dəyər: yüksək

### 🟠 U3 — Elektron jurnal + qiymətləndirmə (əsas akademik funksiya)
Modellərin **heç biri yoxdur**: `AssessmentScheme`, `GradeComponent`,
`ComponentGrade`, `FinalGrade`, `ResitRecord`.
- Müəllim **jurnal grid**-i (offering → tələbə × komponent: davamiyyət/aralıq/layihə/imtahan) → çəkili **yekun** hesablanması.
- Tələbə **"Qiymətlərim"** görünüşü (öz balları + yekun + hərf + GPA nöqtəsi).
- **25% / min imtahan həddi** + **təkrar imtahan** (resit) axını.
- Hər bal dəyişikliyi **audit**-ə.
· Effort: **yüksək** · Risk: orta-yüksək · Dəyər: çox yüksək (universitetin əsası)

### 🟡 U4 — Dərs cədvəli (timetable)
`ScheduleSlot` modeli yoxdur.
- Slot (offering + qrup + müəllim + gün/saat + auditoriya) + **konflikt yoxlaması** (qrup/müəllim/otaq təkrarı).
- Rol-uyğun görünüş: tələbə=qrup cədvəli, müəllim=öz slotları, dekan=fakültə. İxrac (iCal/PDF opsional).
· Effort: **orta** · Risk: aşağı-orta · Dəyər: yüksək (gündəlik istifadə)

### 🟡 U5 — Transkript + GPA + akademik status
- Semestr üzrə **transkript** (fənlər + ballar + kreditlər + GPA), kumulyativ **GPA** hesablanması.
- **Status state-machine** (aktiv / akademik məzuniyyət / xaric / məzun) + keçid audit.
· Effort: **yüksək** · Risk: orta · Dəyər: yüksək (U3-dən sonra təbii davam)

### 🟢 U6 — Qrup köçürmə + imtahana əlavə + org_type təmizliyi
- **Qrupdan-qrupa köçürmə** (registrar/dekan UI + audit + tarix + fənn/cədvəl re-enroll uyğunlaşdırma).
- **İmtahana əl ilə tələbə əlavə** (təkrar imtahan / köçmə tələbə) — mövcud exam-group genişlənməsi.
- `org_type=UNIVERSITY` üçün kurs-mərkəzi/abunə menyularının daha dərin gizlədilməsi (sidebar filtrini genişləndir).
· Effort: **aşağı-orta** · Risk: aşağı · Dəyər: orta

---

## 4. Tövsiyə olunan icra sırası

1. **K1 (Fənn↔Kurs körpüsü)** + **K2 (davamiyyət)** — kiçik, mövcud "Fənlərim"i real edir; U3-ə zəmin.
2. **U3 (elektron jurnal + qiymətləndirmə)** — universitetin əsas dəyəri; K2 üzərinə oturur.
3. **K3 (registrar provisioning UI)** — admin work-around-u real web idarəetmə ilə əvəz edir (U3-lə paralel gedə bilər).
4. **U5 (transkript + GPA)** — U3 balları üzərində.
5. **U4 (dərs cədvəli)** — müstəqil, istənilən vaxt.
6. **U6 (köçürmə/əlavə/təmizlik)** — sonuncu cilalama.

**Prinsip (dəyişməz):** hər faza additiv migration (nullable/default), `organization`
FK + RLS, xarakteristik + `-m postgres` test, tenant-konfiqurasiya (sərt-kod yox),
mövcud imtahan nüvəsini sındırmadan.
