# Dərs cədvəli + Elektron jurnal — yenidən-dizayn planı

Tarix: 2026-07-12 · Mənbə dizayn: claude.ai/design "Elektron Universitet Sistem Dizaynı"
(`Universitet Sistemi.dc.html`). Mockup-dakı üst demo toggle-bar (Cədvəl/Jurnal ·
Müəllim/Tələbə pilləri) YALNIZ nümunə idi — real UI-da İSTİFADƏ OLUNMUR; rol və
bölmə seçimi mövcud sidebar/RBAC axını ilə gedir.

## 0. Mövcud təməl (dəyişmir, üstündə qurulur)

- `apps/registrar`: `ScheduleSlot` (gün, vaxt, otaq, üst/alt həftə + konflikt
  yoxlaması), `Lesson`/`LessonMark` (davamiyyət + seminar/lab balı),
  `AssessmentScheme` (giriş balı ≈50 + təsdiq zənciri + is_published kilidi),
  `AssessmentComponent`/`ComponentScore` (çəkili komponentlər),
  `FinalGrade`/`ResitRecord`, qayıb limiti (`Program.absence_limit_percent`),
  `grade_audit` tarixçəsi, xlsx export, RLS + tenant scoping.
- Profil SPA shell: sol sidebar + sağ panel bölmələri (`my-schedule`,
  `my-journal`, …), `cabinet_modules` görünürlük paneli.

## 1. FAZA 1 — Dərs cədvəli (yeni dizayn, sidebar qalır)

### 1.1 Görünüş (müəllim + tələbə)
- `registrar/partials/_schedule_content.html` tam yenidən: **saat sətirləri ×
  gün sütunları** grid (mockup), bugünkü günün sütunu tünd vurğulu, hüceyrələr
  Mühazirə(mavi)/Məşğələ(teal)/Laboratoriya(bənövşəyi) rəng kodlu, ÜST/ALT
  badge-ləri; eyni gün+saatda iki paritet slotu bir hücrədə bölünmüş göstərilir.
- Saat sətirləri HARDCODE edilmir — mövcud slotların (start,end) cütlərindən
  yığılır (tenant-configurable prinsipi). 18:00+ slotlar ayrıca "Axşam təhsili"
  bandında (magistratura), yalnız belə slot varsa görünür.
- Həftə naviqasiyası (mövcud `?w=N` offseti): "Bu həftə — ÜST / Gələn həftə —
  ALT" + tarixlər. İmtahan günləri günün başında nişan (mövcud inteqrasiya).
- Hər iki rol baxır: tələbə → qrup cədvəli, müəllim → öz dərsləri (mövcud
  rol-həlli qalır). Slot əlavə/silmə YALNIZ müəllim/org sahibi (mövcud icazə) —
  köhnə inline forma modala keçir. Tələbə üçün yalnız baxış.

### 1.2 Fənn modalı (hüceyrəyə klik)
Slot rənginə uyğun başlıqlı modal: fənn kodu+adı · dərs növü · gün/vaxt/paritet
· otaq · müəllim (tələbə görünüşündə) / qrup (müəllim görünüşündə) · ECTS ·
semestr · tələbəyə əlavə: öz qayıb saatı/limit + giriş balı; müəllimə əlavə:
"Jurnalı aç" linki (yeni tab). Server-render inline data (endpoint yox).

### 1.3 Backend
- `ScheduleSlot.kind` (lecture/seminar/lab) migration + slot formasında seçim.
- Konflikt yoxlaması, ics export, imtahan overlay dəyişmir.

## 2. FAZA 2-3 — Elektron jurnal · MÜƏLLİM

### 2.1 Giriş nöqtəsi
- Sidebar "Elektron jurnal" (müəllim/org_admin): SPA bölməsi YOX — adi link
  `target="_blank"` → `/jurnal/` (standalone; profil sidebarı yoxdur).
- `/jurnal/` qrup seçimi cədvəli (mockup addım 1): qrup, fənn, tip, tələbə sayı,
  "Jurnalı aç" → `/jurnal/<offering>/`.

### 2.2 Jurnal iş sahəsi UI
- Sol panel: təqvim planı — keçirilən dərslər (tarix, növ, mövzu), BU GÜN vurğusu.
- Tabs: **Davamiyyət/Ballar · Kollokvium · Sərbəst iş · Kurs işi · Yekun · Tarixçə**.
- Grid sütun sırası: `[№ + Ad (sticky)] [ƏN YENİ dərs → köhnə] [Qayıb cəmi]` —
  yeni gün həmişə adların yanında, uzun scroll yoxdur.
- Yeni dərs yarananda bütün xanalar boş "—"; sütun başlığında toplu
  "hamısına i/e" / "hamısına q/b" düymələri, sonra fərdi toggle.
- Yeni dərs modalı: tarix (default bu gün; KEÇMİŞ TARİX QADAĞAN), **dərs saatı
  seçimi** (həmin günün cədvəl slotlarından; manual vaxt da olar), növ
  (mühazirə/seminar/lab), mövzu, akademik saat (1-8).
- Tarix başlığına klik → yaradılışdan 2 saat içində redaktə/sil; sonra kilid.
- Seminar/lab bal inputu: **min 0, max 10** (server clamp + UI limit).
- Excel export, təsdiq zənciri, yekunlaşdırma mövcud kimi qalır.

### 2.3 Kollokvium (dizaynda yox idi — ƏLAVƏ)
- `AssessmentComponent.kind` sahəsi: `generic|kollokvium|serbest_is` +
  `held_on` (keçirilmə tarixi).
- "Kollokvium" tabı: 3 kollokvium (K1/K2/K3) — hər birinə tarix + tələbə-tələbə
  bal (hər komponentin öz `max_score`-u, default 10). Giriş balına mövcud
  komponent qaydası ilə daxil olur; tələbə tarixçəsində tarix markeri.

### 2.4 Sərbəst iş (mockup-dakı checklist)
- `SelfWorkTopic` (offering, başlıq, sıra) + `SelfWorkMark` (topic, enrollment,
  done) → cəm avtomatik `kind=serbest_is` komponent balına yazılır (max 10).

### 2.5 Kurs işi
- `CourseWork` (enrollment OneToOne): mövzu, bal 0-100, təhvil tarixi,
  entered_by. Giriş balına DAXİL DEYİL — yekun cədvəldə ayrıca sütun (mockup).

### 2.6 Təhlükəsizlik (sərt qaydalar)
| Qayda | Enforcement |
|---|---|
| Mark (i/e·q/b·bal) yazılandan 2 saat sonra DƏYİŞMƏZ | `MARK_EDIT_WINDOW=2h` servis + Postgres trigger (vendor-guarded) |
| Davamiyyət yalnız dərsin öz günündə yazılır | `lesson.date == localdate` server yoxlaması |
| Keçmiş tarixə dərs yaratmaq qadağan | servis validasiyası |
| Dərs (sütun) yalnız yaradılışdan 2 saat içində edit/sil | `LESSON_EDIT_WINDOW=2h`, silinmə marks-la birgə, auditlə |
| Komponent/kollokvium balı 2 saat sonra kilid | ComponentScore-a edit-window |
| Bal tavanları | seminar/lab ≤10, kollokvium ≤max_score, kurs işi ≤100 — server clamp |
| Hər dəyişiklik izlənir | mövcud `grade_audit` (kim·nə vaxt·köhnə→yeni) |
| Tenant izolyasiyası | mövcud RLS pattern yeni cədvəllərə (0011_rls_scheduleslot nümunəsi) |
| Yekunlaşdırma/təsdiq kilidi | mövcud (is_published + approval chain) |

## 3. FAZA 4 — Elektron jurnal · TƏLƏBƏ (sidebar qalır)

- rbac: `my-journal` tələbəyə də açılır; `_my_journal.html` rol-aware:
  tələbə → yeni student görünüşü; müəllim → yalnız "Jurnalı yeni pəncərədə aç".
- Məzmun: fənn kartları (qayıb saat/limit, giriş balı, status) → fənn
  drill-down: ÖZ tam tarixçəsi — tarix · növ · mövzu · i/e|q/b · bal ·
  kollokvium (bal+tarix) · sərbəst iş çeklisti · kurs işi · giriş balı bölgüsü.
- **Bu günün dərsi GİZLİ** (`lesson.date == today` istisna) — müəllim hələ
  redaktə pəncərəsindədir; sabah görünür.
- Tam read-only: heç bir yazan endpoint tələbə rolunda işləmir.

### 3.1 Bildirişlər (mövcud notifications app)
- `notify_journal_score` (yeni bal), `notify_journal_absence` (q/b),
  `notify_absence_warning` (limitin 75%-i), `notify_absence_barred` (kəsilmə).
- `save_marks`/`save_component_scores` sonunda `transaction.on_commit` ilə;
  eyni gün eyni tip → tək (toplu) bildiriş, spam yoxdur.

## 4. Kod strukturu (clean + reusable, soft cap 600 sətir)

- CSS: `registrar/css/schedule_grid.css`, `journal_workspace.css`, `journal_student.css`
- JS: `registrar/js/schedule_grid.js`, `journal_workspace.js` (böyüyərsə grid/tabs bölünür)
- Templates: `_schedule_content.html` (yenidən) + `_schedule_modal.html`;
  jurnal: `journal_workspace.html` + `partials/_jw_grid.html`, `_jw_kollokvium.html`,
  `_jw_selfwork.html`, `_jw_coursework.html`, `_jw_finals.html`
- Python: `gradebook.py` bölünür → grid/marks qalır + `assessment.py`
  (kollokvium/sərbəst/kurs) + kilid qaydaları sabitləri bir yerdə.
- i18n: bütün mətnlər `{% trans %}` context-lə; trans taglarında `%` işarəsi yox.

## 5. İcra sırası

1. Faza 1 cədvəl (backend kind + UI + modal) → brauzerdə verify
2. Faza 2 jurnal backend security (migrations, pəncərələr, clamp, trigger) → pytest
3. Faza 3 müəllim jurnal UI (standalone) → verify
4. Faza 4 tələbə görünüşü + bildirişlər → verify
5. CI preflight: black/isort/flake8 + module-size/boundary guard + pytest (sqlite
   smoke + postgres konteyner RLS)

## 6. Şüurlu qərarlar (istifadəçi düzəldə bilər)

- Cədvəldə "əlavə et" yalnız müəllim/org sahibinə — tələbə cədvəl əlavə etməz
  (baxış hər iki rolda).
- Kollokvium bal tavanı konfiqurable (`max_score`, default 10).
- Axşam bandı avtomatik (18:00+ slot varsa) — ayrıca konfiqurasiya yox.
- Kurs işi giriş balından kənar ayrıca 0-100 qiymət (mockup-a uyğun).
