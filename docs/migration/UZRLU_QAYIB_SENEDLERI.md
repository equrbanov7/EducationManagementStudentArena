# Üzrlü qayıb sənədləri (`allowed_qb`) — köçürmə + sonradan fayl qoşma

**Faza:** `journal_excuse_documents` (J13, registry sırası **50**)
**Mənbə:** `myedudb.allowed_qb`
**Hədəf:** `registrar.LegacyExcuseDocument` (append-only, tenant-scoped)
**Tarix:** 2026-08-31

---

## 1. Niyə bu iş var

Sahibin sözü:

> «Köhnə datadan, əgər köçməyibsə, kiminsə qayıbı düzələrkən yüklənən
> təqdimat/izahat varsa, onu da üzərinə əlavə et; məndə dizayn olmalı idi,
> sarı ilə göstərən — orada olmuş olsun.»

Ölçülmüş vəziyyət (repetisiya mənbəsi, `emsarena-legacy-source-rehearsal`):

| Göstərici | Dəyər |
|---|---:|
| `allowed_qb` sətri | **2,964** |
| fərqli tələbə | 1,130 |
| fərqli göndərən (`owner_id`) | 4 |
| sənəd paketi (`uniq`) | 977 |
| fərqli fayl adı (`file`) | 773 |
| fayl adı olan sətir | **2,964** (100 %) |
| izah mətni (`desc`) olan sətir | **2,927** |
| `students`-də tapılmayan `student_id` | **8** |
| `allowed_date_end < allowed_date_start` | **0** |
| çoxgünlük aralıq | 916 (ən uzunu 369 gün) |
| fayl uzantıları | jpg 928 · pdf 674 · docx 574 · jpeg 486 · png 295 · jfif 7 |

**Cədvəl hədəfə YALNIZ QAYDA kimi çatırdı.** J4 (`journal_marks`) bu tarix
aralıqlarını oxuyub qayıbı `excused` (üq) yazır
(`rehearsal_journal_points_source.is_excused`, J-V3 qaydası) — amma sənədin
ÖZÜ (kim göndərib, nə vaxt, hansı izahla, hansı fayl) heç yerə köçmürdü.

Bu, sahibin «köhnə datanı dəyişmirik» qaydasının pozulması deyil, **tələbidir**:
mövcud heç bir dəyər dəyişmir, yalnız hədəfə çatmayan sətirlər əlavə olunur.

---

## 2. Niyə `JournalCorrection` DEYİL (paralel sistem qurulmayıb)

Layihədə üzrlü qayıb üçün mövcud mexanizm var: `registrar.JournalCorrection`
(sənədli audited düzəliş — səbəb + qeyd + PDF, sarı xana, ✎ tarixçə modalı).
**UI həmin mexanizmin özüdür**, amma MODEL ayrıdır. Səbəb:

* `JournalCorrection` bir **dəyişikliyin** qeydidir: `old_status → new_status`.
  Köçürmədə isə dəyişiklik YOXDUR — xana artıq `excused`-dır və məhz bu
  sənədlərin pəncərəsi onu belə etmişdi.  `old_status == new_status` olan sətir
  saxta audit qeydi olardı.
* `JournalCorrection.document` **məcburi PDF**-dir.  Bizdə fayl YOXDUR (aşağı),
  yəni köçürmə ya uydurma PDF yaratmalı, ya da kontraktı pozmalı idi.
* `JournalCorrection` xananı müəllim üçün **kilidləyir** (`gradebook`
  `corrected_ids`).  Köhnə sənəd bu səlahiyyəti daşımır.

Ona görə model `LegacyGradeFact`/`LegacyGradeArtifact` ailəsindəndir: xam mənbə
faktının append-only snapshot-u.  **UI qatında isə paralel heç nə yoxdur** —
sənəd qeydləri mövcud `corrections_map` payload-una qatılır və eyni
`_correction_history_modal.html` + `correction_history.js` cütü göstərir.

---

## 3. Sənədin ÖZÜ hələ bizdə YOXDUR

Bazada yalnız fayl **ADI** var (`1693211126.jpg` — vaxt möhürü + uzantı).
Faylların özü köhnə serverdədir; `~/Downloads` altında da yoxdur (yoxlanıb).

Buna görə:

* `LegacyExcuseDocument.document` **BOŞ** köçürülür;
* hər sətir `legacy_excuse_document_absent` (INFO) müşahidəsi ilə gəlir —
  hesabatda «2,964 sənəd gözlənilir» rəqəmi görünsün deyə;
* UI **sınıq yükləmə linki VERMİR**: fayl adını göstərir və açıq yazır
  «Sənədin özü köhnə sistemdədir — hələ köçürülməyib.»

---

## 4. UI-da necə görünür (sahibin «sarı dizaynı»)

| Yer | Görünüş |
|---|---|
| Müəllim jurnalı (`_jd_grid.html`) | üq xanası **açıq sarı** (`.jd2-cell.corr-excuse`) + `✎` nişanı |
| Düzəliş rejimi (İKT korrektoru) | eyni sarı + nişan; korrektor «üq» yazılmasının əsasını görür |
| Tələbə jurnalı (`_journal_student_content.html`) | sətir sarı (`.sjx-row--excuse`) + `✎`; gün modalında ayrıca qeyd |
| `✎` nişanına klik | mövcud **düzəliş tarixçəsi modalı** açılır; sənəd qeydi `kind="legacy_excuse"` blokunda |

Sənəd qeydi bloku: tarix · **tarix aralığı** · «Köhnə sistemdən köçürülüb» ·
izah mətni · fayl adı (+ «sənəd köhnə sistemdədir» qeydi) · «Köhnə sistem qeydi».

Rəsmi düzəlişin sarısından bir çalar **açıqdır** (`#fff8e1` vs `#fff3cd`) və
xananı müəllim üçün **kilidləmir** — `cell["corrected"]` toxunulmaz qalır.

Bağlantı qaydası köçürmə ilə eynidir (uydurma FK yoxdur): xana `excused`
olmalı **və** dərsin tarixi sənədin `[starts_on, ends_on]` aralığına düşməlidir.
`allowed_qb.uniq` jurnal `uniqid`-i DEYİL (canlı mənbədə 0 uyğunluq) — o, bir
imzalanmış aktın öz açarıdır və hədəfdə `source_batch_ref` kimi saxlanır.

---

## 5. Faza müqaviləsi

| | |
|---|---|
| `phase_key` | `journal_excuse_documents` |
| `order` | **50** (sonuncu — `legacy_grade_artifacts` 49-dan sonra) |
| `source_tables` | `()` — cədvəl İDDİA edilmir (J4 onu pəncərə üçün oxuyur) |
| `entity_types` | `("legacy_excuse_document",)` |
| ledger açarı | `allowed_qb:<id>` (sətir başına bir möhür) |
| asılılıq | `identity_cohort` (tələbə hesabı) |

**Kontrakt:** `excuse_field_contracts.ALLOWED_QB_DOCUMENT_FIELDS`
(`excuse-v1`, 9 sütun).  J4-ün dar `ALLOWED_QB_FIELDS` (`journal-v1`, 4 sütun)
**toxunulmazdır** — genişləndirsək J4-ün indiyə qədər yazdığı bütün
`source_row_hash` dəyərləri dəyişərdi.  İki kontrakt eyni cədvəli oxuyur; bu,
`yekun`/`sillabus` ilə eyni presedentdir və `EXCUSE_SUPERSET_INVARIANTS` ilə
qorunur (sintetik fixture cədvəli GENİŞ kontraktla qurulmalıdır).

**Fail-closed / taksonomiya** (heç biri ERROR deyil — bu faza run-u bloklamır):

| kod | severity | mənası |
|---|---|---|
| `legacy_excuse_student_unresolved` | WARNING | tələbə tapılmadı (canlı: 8) — sətir SAXLANIR, bağlanmır |
| `legacy_excuse_window_invalid` | WARNING | tarix aralığı pozuq / tip drift-i (canlı: 0) |
| `legacy_excuse_document_absent` | INFO | fayl hədəfdə yoxdur (canlı: 2,964 — hamısı) |
| `legacy_excuse_document_name_invalid` | INFO | fayl adı təhlükəsiz formada deyil → ad saxlanmır |
| `legacy_excuse_note_empty` | INFO | izah boşdur (canlı: 37) |
| `legacy_excuse_note_truncated` | INFO | izah 2000 simvoldan uzun idi (canlı: ən uzunu 109) |

**Heç bir sətir ATILMIR.** Ledger vəziyyəti hər halda `MIGRATED`-dır (J-facts
ilə eyni qayda: xam sübut materiallaşır, mapping problemi metadatadır).

---

## 6. Dəyişməzlik (append-only) — iki qat

1. **Sxem qatı** (`LegacyExcuseDocument.save/delete` + `_AppendOnlyManager`):
   `update()`/`delete()` həmişə `ValidationError`; sətir səviyyəsində yalnız
   `document` sahəsi BOŞDAN DOLUYA gedə bilər.
2. **DB qatı** (migrasiya `0060`, PostgreSQL):
   * `registrar_legacy_excuse_append_only_delete` / `_truncate` — tam qadağa;
   * `registrar_legacy_excuse_attach_only_update` — UPDATE yalnız o halda keçir
     ki, `document`-dən başqa HEÇ BİR sütun dəyişməsin, `OLD.document` boş,
     `NEW.document` dolu olsun;
   * `rls_tenant_isolation` (FORCE RLS) — org izolyasiyası.

---

## 7. ⚠️ Faylları sonradan qoşma runbook-u

Sahib faylları köhnə serverdən gətirəndə:

### Addım 1 — faylları topla
Köhnə serverdə `allowed_qb.file` sütunundakı adlarla saxlanan qovluğu tap
(`1697461819.jpg` formasında vaxt möhürlü adlar).  Adları DƏYİŞMƏ — bağlantı
məhz `document_name` üzərindəndir.

### Addım 2 — faylları hədəf maşına köçür
Məsələn `/srv/legacy-excuse-files/` altına.  İcazə: yalnız oxu.

### Addım 3 — qoşma skripti (prod ops runner kanalı)
`manage.py shell < script` ilə (bax `project_prod_ops_runner_channel`):

```python
from pathlib import Path
from django.core.files import File
from apps.registrar import legacy_excuse
from apps.registrar.models import LegacyExcuseDocument
from core.rls import bypass_rls

SOURCE_DIR = Path("/srv/legacy-excuse-files")
attached = missing = skipped = 0
with bypass_rls():
    for document in LegacyExcuseDocument.objects.filter(document="").exclude(document_name=""):
        path = SOURCE_DIR / document.document_name
        if not path.is_file():
            missing += 1
            continue
        with path.open("rb") as handle:
            if legacy_excuse.attach_document(document, File(handle, name=document.document_name)):
                attached += 1
            else:
                skipped += 1
print(f"attached={attached} missing={missing} skipped={skipped}")
```

`attach_document` bu modelin YEGANƏ icazəli mutasiyasıdır:
* eyni fayl İKİNCİ dəfə qoşulmur (`False` qaytarır);
* qoşulmuş fayl silinə/əvəzlənə bilmir (model + PG trigger);
* uzantı allowlist-i `LEGACY_EXCUSE_EXTENSIONS`
  (`.pdf .jpg .jpeg .jfif .png .docx`), ölçü tavanı 25 MB;
* `core.upload_security` imza yoxlaması da tətbiq olunur.

### Addım 4 — UI-ı yoxla
Fayl qoşulandan sonra `✎` modalında fayl adı **linkə** çevrilir — amma yalnız
müəllim/korrektor görünüşündə (`excuse_map_for_offering`).  Tələbə görünüşü
faylı AÇMIR (`JournalCorrection` tarixçəsi ilə eyni qayda).

---

## 8. Toxunulan fayllar

| Qat | Fayl |
|---|---|
| Model | `apps/registrar/models/legacy_excuse.py`, migrasiya `0060_legacy_excuse_documents.py` |
| Kontrakt | `apps/legacy_import/services/excuse_field_contracts.py` |
| Mənbə/materializasiya | `apps/legacy_import/services/rehearsal_excuse_documents.py` |
| Faza | `apps/legacy_import/services/rehearsal_excuse_documents_phase.py` |
| Registry + allowlist | `rehearsal_contracts.py`, `rehearsal_authorizer.py`, `source_extraction.py` |
| Jurnal oxu qatı | `apps/registrar/legacy_excuse.py` |
| UI | `_jd_grid.html`, `_journal_student_content.html`, `correction.css`, `correction_history.js`, `sjx_journal.js` |
| Testlər | `apps/legacy_import/tests/test_rehearsal_excuse_documents_phase.py`, `apps/registrar/tests/test_legacy_excuse.py` |
