# FAZA 32 — Yekun rol × funksiya matrisi

**Tarix:** 2026-09-02 · **Baza:** QA klonu `emsarena_rehearsal_a0d170000901`
**Mənbələr:** FAZA 27 (uçdan-uca axınlar — bu auditin ƏSAS dəlili) · PHASE21 §1/§7 (252 bölmə açılışı,
konsol/CSP, responsiv) · PHASE23 §A (56 mənfi hal) + PHASE23_SECURITY_FIXES · PHASE22 (ana səhifə) ·
PHASE4 (dərs yükü) · PHASE5 (cədvəl) · PHASE11/18 (müraciətlər) · PHASE1_STUDENT_INTAKE · PHASE24 (performans).

**İşarələr:** ✅ işləyir · ⚠️ işləyir, amma qeyd olunmuş problemi var · ❌ işləmir / rol üçün açıq deyil, amma OLMALI idi · — bu rol üçün aid deyil (qəsdən bağlıdır)

**Sütunlar:** *UI testi* = bölmə/ekran real HTTP-də açılır və düzgün render olunur ·
*İcazə testi* = müsbət + mənfi qapı yoxlaması · *Data testi* = real köçürülmüş data ilə
məzmun/yazma doğrulaması.

---

## 0. Yekun say

35 funksiya × 9 rol = **315 xana**:

| | ✅ | ⚠️ | ❌ | — |
|---|---:|---:|---:|---:|
| **Cəmi xana** | **155** | **30** | **11** | **119** |

11 ❌-in **9-u tək bir sətirdəndir** (32 — köçürülmüş hesabla giriş, **R-8**); qalan 2-si
sillabus təsdiqi (**R-2**, `chair_head`) və `workload-distribution` (`program_coordinator`,
sahib qərarı). Yəni **fərqli defekt sayı 3-dür**.
30 ⚠️-in çoxu iki kökdən doğur: **R-1/R-4** (köhnəlmiş cari dövr + `my-schedule`-də dövr seçicisinin
olmaması — 9 xana) və rol adlarının ingiliscə qalması (PHASE21 U-2 — 9 xana).

---

## 1. Rol × bölmə görünürlüyü (klondan canlı oxunub, 2026-09-02)

| rol | bölmə sayı |
|---|---:|
| `student` | 17 |
| `teacher` | 20 |
| `program_coordinator` | 14 |
| `hr` | 22 |
| `exam_center` | 28 |
| `dean` | 32 |
| `chair_head` | 33 |
| `rector` | 39 |
| `ikt_rehber` (RİM) | 46 |

> ⚠️ **`chair_head` (33) və `dean` (32) siyahıları demək olar eynidir** — dekanda əlavə heç nə,
> kafedra müdirində isə yalnız `workload-distribution` var. ISSUES **P1-10** (`org_admin` alias
> sızması) hələ AÇIQdır: fakültə əhatəli dekan ilə kafedra əhatəli müdir eyni idarəetmə səthini
> görür (məzmun əhatə ilə süzülür — PHASE23 A-27 artıq 302 verir — amma menyu səthi eynidir).

---

## 2. Matris

Qısaltmalar: **st**=student · **tc**=teacher · **ch**=chair_head · **pc**=program_coordinator ·
**dn**=dean · **ec**=exam_center · **rm**=ikt_rehber/RİM · **rc**=rector · **hr**=hr

| # | Funksiya | UI testi | İcazə testi | Data testi | st | tc | ch | pc | dn | ec | rm | rc | hr | Dəlil |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Profil (`profile-info`, `edit-profile`, `change-password`) | PHASE21 §1 (252 açılış, 0×500) | öz profili; avatar mənfi PASS (A-45) | `position` xam msgid düzəldildi | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | PHASE21 §4.2 |
| 2 | **Ana səhifə (`dashboard`)** | PHASE22 · F1/9 200 | vidjet yalnız `allowed_sections`-dan qurulur (sızma testli) | rol-aware sayğaclar | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | PHASE22 §2 · F1 addım 9 |
| 3 | Bildirişlər (zəng + `notifications`) | PHASE21 | öz bildirişləri | **F2/F4/F7/F13/F16/F17-də hər addımda real bildiriş sayıldı** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | F3a, 6b, 7d, 8c/8f, 13c, 16c, 20c, 22d |
| 4 | **Cədvələ baxış (`my-schedule`)** | 200 | tələbə/müəllim ayrımı düzəldildi | slot **yalnız cari dövrdə** görünür; dövr seçicisi YOXDUR | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | **R-1 · R-4**; F5/F6 vs F5′/F6′ |
| 5 | **Cədvəl idarəetməsi (`schedule-manage`)** | 200 (F4a) | müəllim **403** (3 uc); tələbə 403 | slot yarandı + audit + bildiriş; **bitmiş semestrə yazmaq 400** | — | — | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | F4a–4d · N-1 · PHASE5 |
| 6 | Müəllim jurnalı (`/jurnal/<off>/`, dərs əlavəsi) | 200 | yad açılış 404 (A-28/A-43) | dərs + mövzu (sillabusdan) + otaq yazıldı | — | ✅ | — | — | — | — | ✅ | ✅ | — | F9a–9c |
| 7 | Davamiyyət + dərs balı | 200 | `att__`/`score__` yalnız birbaşa redaktora | 3 `LessonMark` yazıldı | — | ✅ | — | — | — | — | ✅ | ✅ | — | F11–12 |
| 8 | **Tələbə jurnalı (`my-journal`)** | 200 | yalnız öz sətri; başqa tələbə adı sızmır | mövzu ✓ otaq ✓ «QAYIB 2 saat» ✓ · «bu günün qeydləri sabah» qaydası | ✅ | ✅ | ✅ | — | ✅ | — | ✅ | ✅ | — | F10, F10′ |
| 9 | Nəticələr (`my-results`, `overall-academic`) | 200 | öz datası | 72 / 64 sorğu (regresiya yox) | ✅ | — | — | — | — | — | — | — | — | F27 · PHASE24 |
| 10 | **Sənədli düzəliş (`?correct=1`)** | 200 | `journal.correct`-siz müəllim **404** (A-7/A-8) | `absent→present`, `JournalCorrection` + **PDF**, tələbəyə bildiriş, tarixçə nişanı | — | — | — | — | — | — | ✅ | ✅ | — | F16a–16d |
| 11 | **Kollokvium pəncərəsi** | 200 | koordinator **403** (A-20); `exam_center_staff` əlavə gün 302 (A-21) | K1 yaradıldı → açıldı → müəllim 7 yazdı → bağlandı → **yazma bloklandı** | — | — | — | — | — | ✅ | ✅ | — | — | F13–F15 |
| 12 | Müəllim K balı (`/jurnal/<off>/kollokvium/`) | 302 → jurnal | pəncərə bağlıdırsa **yazmır** + xəbərdarlıq | 3 `ComponentScore` = 7.00, bağlıdan sonra dəyişmədi | — | ✅ | — | — | — | — | ✅ | ✅ | — | F14, F15 |
| 13 | Jurnal bağlama (`journal-close`) | 200 | kafedra müdiri **403** (A-22) | — (bu dalğada icra edilmədi) | — | — | — | — | — | — | ✅ | ✅ | — | A-22 · PHASE21 §1 |
| 14 | Sillabus siyahısı (`syllabus-list`) | 200, kontrast düzəldildi | yalnız öz fənləri | 8 bölmə real ucdan dolduruldu → **100 %** | — | ✅ | ✅ | — | ✅ | — | ✅ | ✅ | — | F7b · PHASE21 §4.5 |
| 15 | Sillabus redaktoru (`…/section/`) | 200 | yad sillabus 400/409 (A-15/A-16); **klonlama 404** (A-46) | ilk dəfə **real 100 % məzmun** | — | ✅ | ✅ | — | ✅ | — | ✅ | ✅ | — | F7b · A-46 · **R-3** |
| 16 | **Sillabus təsdiqi (`syllabus-review`)** | dekanda 200 + sətir var | `syllabus.approve`-suz 404 (A-17/18/19) | `submit → revise → resubmit → approve` **tam dövrə + 3 bildiriş** | — | — | ❌ | — | ✅ | — | ✅ | ✅ | — | **R-2**: `chair_head` sillabusu nə görür, nə qərar verir (404) |
| 17 | **Yük bölgüsü (`workload-distribution`)** | 200 | müəllim 403, tələbə 403 | tapşırıq → sətir → 2 bölgü → təsdiq → **müəllimə bildiriş** | — | — | ✅ | ❌ | — | — | ✅ | ✅ | — | F2 · N-3a; `pc`-də bölmə YOXDUR (PHASE21 U-7 → sahib qərarı) |
| 18 | **Dərs yüküm (`my-workload`)** | 200 | `workload.view` | 1 sətir / 45 saat göründü | — | ✅ | ⚠️ | ⚠️ | ⚠️ | — | ⚠️ | ⚠️ | — | F3b–3c; ⚠️ = tədris aparmayan rolda həmişə boş (PHASE21 U-5/U-6) |
| 19 | **Müraciət göndərən (`applications`)** | panel kabinet içində, sidebar qalır | yalnız öz müraciətləri (`tab=inbox` = 0 sətir) | MR-000006 `submitted→seen→forwarded→resolved→closed` + tam tarixçə | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | F17, F21, F22, F23 · PHASE18 |
| 20 | **Müraciət icraçısı** (`tab=inbox`, `forward/resolve`) | 200 | yad müraciəti `resolve` → **404** | koordinator → RİM yönləndirmə → həll; kafedra müdiri «Təqdimat»ı həll etdi | — | — | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | F18–20, F22, F23; `rc` üçün ayrıca vahid yoxdur |
| 21 | **Tələbə idxalı (`student-intake`)** | 200 | tələbə şablon **403**, apply **403** | 2 hesab yaradıldı → OTP → giriş → 4 bölmə | — | — | — | — | — | — | ✅ | ✅ | ✅ | F1 · N-2 · PHASE1_STUDENT_INTAKE |
| 22 | RİM mərkəzi (`rim-center`) | 200 | HR-də `user.block` yox → 403 (A-23); bərabər səviyyə 404 (A-24/25) | — | — | — | — | — | — | — | ✅ | ✅ | ⚠️ | A-23…A-25; ⚠️ HR görür, amma blok edə bilmir |
| 23 | İmtahan mərkəzi (`exam-center-*`, `superadmin-exam-rooms`) | 200 | **tələbə `/exams/center/rooms/` → 403** (əvvəl 200) | — | — | — | — | — | — | ✅ | ✅ | — | — | **A-39 DÜZƏLİB** |
| 24 | Apellyasiyalar (`manage-appeals`, `appeal-stats`) | 200 | kafedra müdiri **403** (A-30); müəllim 302 (A-29) | — | ⚠️ | — | — | — | — | ✅ | ✅ | — | — | A-29/A-30; st = yalnız `my-appeals` |
| 25 | Adamlar / akademik qeydlər (`people-*`, `academic-records`) | 200 | əhatə ilə süzülür | — | — | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | PHASE21 §1 |
| 26 | **Sual bankı (`question-bank`)** | 200 | yad bankda **toplu silmə 403** (əvvəl silinirdi) | sətir sayı dəyişmədi | — | ✅ | ✅ | — | ✅ | ⚠️ | ✅ | ✅ | — | **A-31f DÜZƏLİB**; ⚠️ `ec` yad bankı hələ OXUYUR (**R-7**, qəsdli) |
| 27 | Qruplar (`groups`) | 200, lazy yükləmə | əhatə ilə süzülür | 63 sorğu / 113 ms (regresiya yox) | — | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | — | F27 · PHASE24 P2-1 |
| 28 | Rol / icazə redaktorları (`org-roles`, `permission-editor`, `role-assignment`, `manage-roles`) | 200 | özünü yüksəltmə 302 (A-35/36); müəllim 302 (A-38); **dekan matris 302** | icazə dəyişmədi | — | — | ⚠️ | — | ⚠️ | — | ✅ | ✅ | ⚠️ | **A-27 DÜZƏLİB**; ⚠️ = P1-10 menyu sızması |
| 29 | Audit jurnalı (`audit-log`) | 200 | admin-dən **silinmir** (`has_delete_permission=False` + `delete()` raise + PG trigger) | — | — | — | — | — | — | ✅ | ✅ | ✅ | ✅ | PHASE23_SECURITY_FIXES P1-3 |
| 30 | Tenant izolyasiyası (RLS) | — | **82 test / 0 uğursuz** NOBYPASSRLS rolu ilə | organizations · registrar · applications · workload | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | F25 |
| 31 | Portal qapısı + ilk giriş | 200 | tələbə neytral `POST /accounts/login/` ilə keçə bilmir | **6/6 `test_staged_portal_login.py`**; OTP axını real işlədi | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | F1/4–8 · F26 · PHASE23 P1-1 |
| 32 | **Köçürülmüş hesabla giriş** | — | — | **8 543 hesabın parolu «unusable»; parol bərpası e-poçt GÖNDƏRMİR** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **R-8** (PHASE31 §2) |
| 33 | Responsiv 375 / 768 / 1280 | 768-də 200 px üfüqi sürüşmə **düzəldildi** | — | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | PHASE21 §4.4 |
| 34 | AZ tarix adları / dil | 16 korlanmış giriş düzəldildi | — | jurnalda «01.09» düzgün render | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | PHASE21 §4.1 |
| 35 | Rol adlarının dili | ⚠️ **İngiliscə** (`Teacher`, `Dean`, …) | — | klon datası | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | PHASE21 U-2 (AÇIQ) |

> **32-ci sətir bütün rollarda ❌-dir və auditin ən ağır tapıntısıdır** — ekran-ekran hər şey
> işləyir, amma köçürülmüş 8 543 nəfərin heç biri bu gün öz hesabına daxil ola bilmir.
> Yuxarıdakı say cədvəlində bu sətir bir defekt kimi (4 ❌-dən biri olaraq) hesablanıb, 9 dəfə yox.

---

## 3. Rol-rol qısa hökm

| rol | hökm | qalan problem |
|---|---|---|
| **student** | ✅ kabinet, jurnal, nəticələr, cədvəl, müraciətlər — hamısı işlədi | R-1 (cədvəl dövrü) · R-8 (köçürülmüş tələbə girə bilmir) · P2-5 «Qoşul» düyməsi |
| **teacher** | ✅ jurnal, kollokvium, sillabus, dərs yüküm, müraciət — tam dövrə | R-2 (sillabusunu kafedra müdiri deyil, **dekan** təsdiqləyir) · U-4/U-5 etiket-məzmun |
| **chair_head** | ✅ yük bölgüsü + müraciət icrası; ❌ **sillabus təsdiqi** | **R-2** · P1-10 (dekanla eyni menyu) |
| **program_coordinator** | ✅ cədvəl idarəetməsi + müraciət icrası (ən dar, ən təmiz səth) | ❌ `workload-distribution` yoxdur (sahib qərarı) · R-1 |
| **dean** | ✅ faktiki sillabus təsdiqçisi + müraciət icraçısı | P1-10 · A-27 düzəlib, menyu sızması qalır |
| **exam_center** | ✅ kollokvium pəncərəsi uçdan-uca | R-7 (yad bankı oxuya bilir) · U-13 `analytics` 3 s |
| **ikt_rehber (RİM)** | ✅ sənədli düzəliş + tələbə idxalı + 46 bölmə, 0×500 | — |
| **rector** | ✅ ən geniş oxu səthi | müraciətlərdə öz vahidi yoxdur (⚠️) |
| **hr** | ✅ tələbə idxalı + kadr müraciətləri | ⚠️ `rim-center` görünür, amma blok edə bilmir (A-23 — qəsdən) |

---

## 4. Bu matrisin bağladığı / açıq saxladığı ISSUES bəndləri

| ISSUES | əvvəlki status | FAZA 27/31/32-dən sonra |
|---|---|---|
| P0-4 (cədvəl icazəsi) | IN-PROGRESS | **FIXED** — F4 + N-1 (3 uc 403) |
| P0-5 (dərs yükü) | FIXED (klon) | **təsdiqləndi canlı axınla** — F2/F3 |
| P0-6 (müraciətlər) | FIXED (klon) | **təsdiqləndi** — F17…F23 |
| P0-9/P0-10/P0-11 | FIXED | **təsdiqləndi** — A-31f, portal qapısı, A-46 |
| P1-1 (sillabus bildirişləri) / U-3 | FIXED / təsdiqlənməmiş | **təsdiqləndi** — F7d, 8c, 8f |
| P1-2 (kollokvium/jurnal bildirişləri) | FIXED | **təsdiqləndi** — F13c |
| P1-3 (jurnalda otaq) | FIXED | **təsdiqləndi**, amma klonda 0 otaq var → **R-5** |
| P1-4 (performans) | FIXED | **regresiya yoxdur** — F27 |
| P2-7 (`test_staged_portal_login`) | OPEN | **BAĞLANA BİLƏR** — 6/6 yaşıl (F26) |
| P1-10 (dean/chair_head alias) | OPEN | **AÇIQ** — menyu səthi hələ eynidir |
| P1-5 (J12) · P1-8 · P1-9 · P2-6 | OPEN/DEFERRED/WONTFIX | dəyişməyib (PHASE31 §1) |
| **YENİ** | — | **R-1, R-2, R-5, R-8, R-9** → PHASE27 §2 |
