# Tədris modulunun tam formalaşdırılması — proses, memarlıq və qərarlar

**Tarix:** 2026-08-21 · **Status:** dizayn razılaşdırıldı, icra gözləyir
**Kontekst:** Qərbi Kaspi Universiteti (WCU). Köhnə `myedudb` (MySQL/CodeIgniter, ~10 il istehsalatda) sisteminin tədris hissəsinin yeni EMSArena (Django/PostgreSQL) sisteminə **tam köçürülməsi və formalaşdırılması**.

> Bu sənəd istifadəçi (WCU tədris tərəfi) ilə aparılan dərin analiz nəticəsində razılaşdırılmış **real biznes prosesini**, **jurnal memarlığı qərarını** və **bağlanacaq boşluqları** qeydə alır. Registrar domen modeli üçün baza: [`UNIVERSITY_SYSTEM_ROADMAP.md`](UNIVERSITY_SYSTEM_ROADMAP.md), [`AKADEMIK_DOVR_SISTEMI_DIZAYN_P3-2.md`](AKADEMIK_DOVR_SISTEMI_DIZAYN_P3-2.md).

---

## 1. Real biznes prosesi (tam axın)

```
ATİS (dövlət qəbulu) → yeni tələbələr
  └▶ Tələbə Mərkəzi — sənədləri FİZİKİ qəbul edir → təsdiqlənmiş siyahı
     └▶ Tələbə Şöbəsi → Tədris Şöbəsi → ixtisas/fakültə bölgüsü → dekanlıq
        └▶ DEKANLIQ:
             • qrupları ƏL İLƏ formalaşdırır, hər qrupa KOD verir (məs. "245KM")
             • tədris planından fənləri açır (ixtisas/seçmə, kredit, saat, semestr)
             • → İXTİSASIN YÜKÜ formalaşır
        └▶ TƏDRİS: ixtisasa aid KAFEDRANIN yükünü tam formalaşdırır
             • Tədris → dekanlığa TƏSDİQ → dekanlıq → KAFEDRALARA yönləndirir
        └▶ KAFEDRA: fənnə uyğun MÜƏLLİM təyin edir + yükü heyət arasında paylayır
        └▶ MÜƏLLİM + PROQRAM KOORDİNATORU: dərs cədvəlini qurur
             (gün, sabit saat, otaq, üst/alt həftə)
        └▶ TƏDRİS PROSESİ (elektron jurnal): davamiyyət + seminar/lab balı
             • → GİRİŞ BALI (semestr, ≈50)
        └▶ İMTAHAN MƏRKƏZİ: tələbə giriş balı ilə imtahana girir
             • forma: TEST (avtomatik) / YAZILI (əl ilə) / PRAKTİKİ (əl ilə)
             • → İMTAHAN BALI (≈50)
        └▶ YEKUN = giriş balı + imtahan balı
             • kəsilən tələbə → aşağıdakı §5 remediation yolları
```

---

## 2. Qərarlaşmış domen qaydaları

| Sahə | Qayda |
|---|---|
| **Qrup kodu** | Dekanlıq **əl ilə** verir (avtomatik yox), məs. "245KM". |
| **Seçmə fənn** | Qrup səviyyəsində, **tələbə sorğusu + səs çoxluğu** ilə. Bütün qrupa tətbiq olunur. |
| **Seçmə vaxtı** | **1-ci kurs, 1-ci semestrdə seçmə fənn YOXDUR.** |
| **Mühazirə/seminar** | Ayrı müəllimlər ola bilər. Mühazirə çox vaxt **potok** (bir neçə qrup birləşir); seminarlar qruplara ayrı. |
| **Otaqlar** | 5 bina, hər birinin adı var. Otaq **mətn** kimi saxlanılır (adlandırma: "bina + otaq" → təkrar nömrə qarışmasın). |
| **Saatlar** | **Sabitdir** (standart cüt/slot vaxtları). |
| **Üst/alt həftə** | **Bütün universitetdə eynidir** (bir semestr başlanğıcından hesablanır). |
| **Proqram koordinatoru** | **Hər ixtisasın öz koordinatoru var**; cədvəl qurur + kəsilən tələbəyə remediation təklif edir. |
| **İmtahan formaları** | Test (avtomatik qiymət), Yazılı (əl ilə), Praktiki (əl ilə). İmtahan mərkəzi keçirir. |
| **Giriş balı körpüsü** | Tədris (jurnal) → giriş balı → imtahan modulu; imtahan balı → yekun. |

---

## 3. Əsas memarlıq qərarı — elektron jurnal

**Sual (istifadəçi):** qrupa bir jurnal yaradaq, bütün fənlər içində olsun, müəllim yalnız öz fənnini görsün.

**Qərar:** Üç anlayışı ayırırıq — **saxlama (həqiqət mənbəyi)**, **təqdimat (view)**, **icazə**.

- **Atomik vahid (saxlama/qiymət/icazə) = `CourseOffering` (fənn × qrup × müəllim).**
  Səbəb: (1) tədris **yükü** offering-formalıdır — kafedra müəllimi fənnə təyin edir; (2) **qiymət** fənnindir (hər fənnin öz 50+50, öz keçid qaydası, öz təsdiqi); (3) **icazə** RLS ilə sətir-səviyyə təmiz alınır (`offering.instructor` → müəllim yalnız öz sətirini görür); (4) real topologiya (**potok mühazirə + qrup seminarları, mühazirə/seminar ayrı müəllim, təkrar**) yalnız offering modelində təmiz oturur.

- **"Qrup jurnalı" = AQREQAT VIEW** — qrupun bütün offering-lərini bir ekranda göstərir:
  `offering.group = G` (seminarlar) **VƏ** `offering.group = null & ixtisas = G-nin ixtisası` (potok mühazirələr).
  Müəllim hamısını görür, yalnız öz sütununu redaktə edir; dekan/tyutor hamısını oxuyur; tələbə bütün fənlər üzrə öz sətrini (davamiyyət cəmi → 25% qaydası bir baxışda).

- **Yeni header obyekti: `GroupSemesterLoad` (Qrup-semestr yükü / "Qrup jurnalı")** — hər (qrup, period) üçün. Dekanlıq qrupu formalaşdırıb planı tətbiq edəndə yaranır; qrupun offering-lərini birləşdirir; **yük iş-axını state + təsdiqlərini** daşıyır. İstifadəçinin "qrupa bir jurnal" mental modeli **elə budur** — konteyner/iş-axını header-i, içindəki vahidlər offering-lərdir.

**Bənzətmə:** bir qrup jurnal dəftəri; hər fənn ayrı səhifə; hər müəllim yalnız öz səhifəsini doldurur; dekan bütün səhifələri görür.

**Presedent:** yetkin universitet sistemləri (Banner, PeopleSoft Campus) — vahid = "section/offering"; "qrup registri" və "cədvəl" view-dur.

---

## 4. Yük formalaşdırma iş-axını (state-machine)

Prosesə uyğun offering (və/və ya `GroupSemesterLoad`) üzərində lifecycle:

```
planlı ──▶ yük-formalaşıb ──▶ Tədris-təsdiqi ──▶ kafedraya-yönləndirilib
        ──▶ müəllim-təyin-olunub ──▶ aktiv
```
Hər keçid **aktoru** (kim, nə vaxt) audit olunur. Bu, qiymət-təsdiq zəncirindən (`AssessmentScheme.approval_status`) AYRIDIR — o, qiymətlər üçündür; bu, yük üçün.

---

## 5. Kəsilmədən sonrakı yollar (remediation)

Yekun kəsilən tələbə üçün — **proqram koordinatoru təklif edir**:

| Kəsilmə səbəbi | Yol |
|---|---|
| **Qaibdan kəsilən** (davamiyyət limiti aşıb) | **Alt qrupa qalır** — fənni aşağı kursla təkrar keçir (güzəşt imtahanı YOX). |
| **Baldan/imtahandan kəsilən** | **25% güzəşt imtahanı** verir. |
| Alternativ | **İntensiv dərs** (sıxılmış təkrar kurs). |
| Alternativ | **Yay məktəbi** (yayda fənni bağlayır). |

**Boşluq:** EMS-də hazırda yalnız `ResitRecord` (təkrar imtahan ≈ güzəşt) var. **Alt qrup / intensiv / yay məktəbi** — bunlar bal deyil, **yeni qeydiyyat/status əməliyyatlarıdır** (tələbə başqa qrupa/kursa/dövrə keçir) → status state-machine tələb edir.

> **Açıq sual:** "25%" dəqiq nəyi bildirir (güzəşt imtahanının payı, yoxsa keçid həddi) — sonra dəqiqləşdirilir.

---

## 6. "Tam formalaşdırmaq" üçün bağlanacaq boşluqlar (iş siyahısı)

| # | Boşluq | Əlavə |
|---|---|---|
| 1 | **`Subject.owner_unit`** (fənn → kafedra) | Yükü kafedraya yönləndirmək üçün. Additiv, nullable. |
| 2 | **Yük lifecycle state-machine** (§4) + aktor auditi | Yeni sahələr/model. |
| 3 | **`GroupSemesterLoad` header** + plandan **avtomatik offering generasiyası** | Dekanlıq qrup+plan seçir → offering-lər (kredit + saat muh/sem/lab). |
| 4 | **Qrup formalaşdırma axını** (təsdiqlənmiş siyahıdan) | ATİS/Tələbə Şöbəsi importu → StudentAcademicRecord + qrup. |
| 5 | **Proqram koordinatoru** cədvəl icazəsi (öz ixtisası üzrə) | RBAC. |
| 6 | **Standart saat slotları** (sabit cütlər) | Tenant-konfiqurasiya. |
| 7 | **Remediation yolları** (alt qrup / güzəşt / intensiv / yay məktəbi) | Status state-machine + təkrar-qeydiyyat (§5). |
| 8 | **İmtahan körpüsü** (giriş balı ↔ imtahan balı) + yazılı/praktiki **əl ilə bal girişi** | `exam_bridge` genişlənməsi. |

Prinsip: hər əlavə **additiv migrasiya** (nullable/default), `organization` FK + RLS, mövcud qiymət/jurnal nüvəsini sındırmır.

---

## 7. Köhnə data köçürməsinə təsiri

Bu qərarlar köçürmə xəritəsini dəqiqləşdirir (bax [`MUQAYISE.md`] mənbə müqayisəsi):

- `journals` (fənn-jurnalı, `lesson_id` + çoxlu `groups_id`) → **CourseOffering** (potok = `group=null`). `journals.parent_id` (mühazirə/seminar bölünməsi) → ayrı offering-lər, qrup-jurnalı view birləşdirir.
- `journals_dates*` / `journals_dates_points` (4.98M, string-açarlı) → **Lesson + LessonMark** rekonstruksiyası (`journal_uniqid+month+day+time` → Lesson FK; il jurnalın semestrindən). `point` varchar → `status` + `score` (profilləmə tələb edir).
- `yekun` (`girish/imtahanda/yekun/kesr/guzest_*`) → **FinalGrade** (+ giriş balı jurnaldan). `guzest_*` → güzəşt/bonus; `kesr` → kəsilmə + remediation yolu.
- `sillabus` (13 cədvəl, ~290k) → **EMS-də yoxdur** — ayrıca sillabus modulu qərarı (sonra).

---

## 8. Növbəti addımlar
1. Bu qərarları koda çevirmək üçün konkret model dəyişikliklərini planla (§6 sırası ilə).
2. Köhnə `myedudb`-də **data profilləməsi** (point/ga/sem_muh/güzəşt/qrup sahələri) — köçürmədən əvvəl qeyri-müəyyən sahələri dekod et.
3. Sonra additiv migrasiyalar + köçürmə management command-ı.
