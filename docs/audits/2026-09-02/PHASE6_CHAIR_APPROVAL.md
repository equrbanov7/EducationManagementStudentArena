# FAZA 6 — Sillabusun təsdiqçisi: KAFEDRA MÜDİRİ (sahibin qərarı)

**Tarix:** 2026-09-03 · **Branch:** `audit/post-migration-qa-2026-09` · **Commit edilməyib**
**Baza:** QA klonu `emsarena_rehearsal_a0d170000901` (:55433) — prod `emsarena_db` (:5432)
**heç vaxt açılmadı**. pytest: öz bazam `ems_syl_a91k3` (:55432).

---

## 0. Qərar və nəticə

FAZA 27 (R-2) göstərmişdi ki, `Syllabus.chair_unit` ixtisasa bağlandığı üçün kafedra
müdiri sillabusu praktikada heç görmürdü; qərar açarları isə HƏM kafedra müdirində,
HƏM DƏ dekanda idi. Dekanın fakültə scope-u alt-ağacdakı bütün kafedraları örtdüyü
üçün (`user_scope_covers_unit` alt-ağac yoxlamasıdır) **de-fakto təsdiqçi dekan idi**.

**SAHİBİN QƏRARI (2026-09-03): sillabusu təsdiq edən KAFEDRA MÜDİRİDİR.**

| tərəf | sonra |
|---|---|
| `chair_head` | `view` · `review` · **`approve` · `revise` · `reject`** (dəyişmədi) |
| `dean` | `view` · `review` — **qərar açarları ÇIXARILDI** (oxuyur, açır, şərh yazır) |
| `rector` (`*`) · `vice_rector` · `ikt_rehber` (RİM, `syllabus.*`) | override QALIR (org-wide, hər əməl auditli) |
| `teacher` | dəyişmədi (`edit` + `submit`) |

Əlavə olaraq: qərar açarı ƏLİNDƏ OLSA BELƏ, əhatə artıq **kafedra səviyyəsində**
yoxlanılır — köhnə tenant-da və ya icazə redaktorundan əl ilə açar verilmiş
fakültə-scope rol da fail-closed dayanır.

---

## 1. Dəyişikliklər

### 1.1 Siyasət (icazə kataloqu)

| fayl | dəyişiklik |
|---|---|
| `apps/organizations/default_roles_university.py` | `dean` rolundan `syllabus.approve/revise/reject` çıxarıldı; `syllabus.view` + `syllabus.review` qaldı (izahlı şərh ilə) |
| `apps/organizations/migrations/0035_dean_syllabus_review_only.py` | mövcud tenantların backfill-i — `0034_seed_user_import_permission`-dan asılı, **idempotent**, **reversible** (geriyə: eyni üç açar `dean` rollarına qaytarılır). `*` və ya `syllabus.*` daşıyan rola TOXUNMUR |

### 1.2 Əhatə — «kafedra səviyyəsi» qaydası (fail-closed)

| fayl | dəyişiklik |
|---|---|
| `apps/syllabus/services/units.py` | `is_chair_unit()`, `chair_level_scope_covers(scope_unit_ids, chair_unit_id)`, `has_chair_level_unit()`, `ensure_chair_unit(syllabus)` |
| `apps/syllabus/services/scoping.py` | `SyllabusActor.covers_chair_unit(unit_id, permission)` — org-wide override, əks halda aktoru sillabusa bağlayan `Membership.scope_unit` **kafedra tipli** (özü və ya kafedra tipli əcdad) olmalıdır; `has_decision_scope(actor)` (UI düymələri üçün) |
| `apps/syllabus/services/workflow.py` | `_CHAIR_LEVEL_TRANSITIONS = {approve, request_revision, reject}` → bu üçü `covers_chair_unit` ilə yoxlanılır. `start_review` və `archive` QƏSDƏN siyahıda deyil: dekan növbəni açıb oxuya bilir |

Qayda bir yerdədir — HTTP səthi, `available_actions` və növbə ekranı eyni funksiyadan
keçir; state maşınının özü (`state_machine.check`) toxunulmadı, ona verilən `in_scope`
bayrağı daraldı.

### 1.3 HTTP səthi

| fayl | dəyişiklik |
|---|---|
| `apps/accounts/views/syllabus/review_api.py` | `_FORBIDDEN_CODES` — `permission_denied` / `out_of_scope` / `author_only` artıq **403**, qalan `TransitionDenied` 409 qalır (səlahiyyət ≠ vəziyyət; əvvəl hamısı 409 idi, kliyent «yenidən cəhd et» deyirdi). `syllabus_review_open`-dakı iki eyni budaq bir yerə yığıldı |
| `apps/syllabus/public.py` | `build_review_queue_context` → `can_decide` (yeni) və `can_approve/can_revise/can_reject` artıq `can_decide` ilə AND-lanır |
| `apps/accounts/views/syllabus/review.py` | context-ə `can_decide` + `read_only` |

### 1.4 Struktur bağının möhkəmliyi (R-2 davamı)

`create_draft` onsuz da `resolve_syllabus_chair_unit`-dən keçirdi (əcdad → müəllifin
kafedra üzvlüyü → verilən dəyər); `copy_from_previous` isə `create_draft`-a
delegasiya edir. İndi **`create_next_version` və `copy_from_previous` MƏNBƏ dosyeni
də sağaldır** (`ensure_chair_unit`): ixtisasa bağlı qalmış köhnə sətir yeni versiya
açılanda özü kafedraya çəkilir — `syllabus_repair_chair_units` əmrini gözləmədən.
`apps/legacy_import` toxunulmadı (əhatədən kənar).

### 1.5 UI mətni

| yer | mətn |
|---|---|
| `review_text.READ_ONLY` (növbə başlığının altında + panelin altında) | **«Təsdiq kafedra müdirinin səlahiyyətindədir»** + izah: panel yalnız oxunur, şərh yazıla bilər |
| `review_text.POLICY_ROWS` | «Kafedra müdiri təsdiqi» → «YEGANƏ təsdiq mərhələsi»; «İkinci təsdiq — dekan» → «Tətbiq olunmur: dekanlıq görür və şərh yazır, qərar açarı kafedra müdirindədir» |
| `editor.SECTION_TEXTS[send]` (müəllim tərəfi «kimə gedir») | «…kafedra müdirinin növbəsinə düşür. Təsdiq kafedra müdirinin səlahiyyətindədir — dekanlıq baxa bilir, qərarı isə müdir verir.» |
| `notifications.FALLBACK_NOTE` | kafedra müdiri təyin edilməyibsə dekana gedən bildirişin izahı |

CSS: `syllabus_base.css` → `.syl-note--readonly`, `syllabus_review_panel.css` →
`.syl-decide__readonly` (yalnız `--ems-*` tokenləri; inline stil YOXDUR).

⚠️ **Şablon msgid-ləri qəsdən DƏYİŞDİRİLMƏDİ** — `_editor_final.html`,
`_editor_dialog.html`, `_review_coverage.html` öz kataloqlu mətnləri ilə qaldı
(onlar onsuz da «kafedra müdiri» deyir), yeni mətn isə mətn qatındadır. Səbəb:
`scripts/check_i18n_catalogs.py` yeni şablon msgid-ini kataloq borcu kimi
dayandırır və `.po` faylları paralel agentdədir.

### 1.6 Bildirişlər

`notify_submitted` əvvəlki kimi kafedra müdirinə gedir; müdir yoxdursa dekana —
amma indi **açıq qeydlə** («…kafedra müdiri təyin edilməyib… zəhmət olmasa müdir
təyin edin»). Nə müdir, nə dekan tapılmasa hadisə `logger.warning` ilə jurnala
düşür — **səssiz düşmə yoxdur**.

---

## 2. Qırmızı → yaşıl testlər

Yeni: `apps/syllabus/tests/test_chair_approval_authority.py` (13) ·
`apps/accounts/tests/test_syllabus_chair_approval.py` (6) ·
`test_chair_unit_resolution.py`-a 1 (self-healing) · `test_permission_catalog.py`-da
`test_dean_mirrors_the_chair_decision_set` → `test_dean_reads_and_reviews_but_never_decides`.

**Qırmızı sübutu** (düzəlişlər müvəqqəti geri qaytarıldı):

```
FAILED test_dean_default_role_keeps_reading_but_loses_every_decision_key
        AssertionError: syllabus.approve
FAILED test_dean_holding_legacy_decision_keys_is_still_out_of_chair_scope
        DID NOT RAISE TransitionDenied          ← dekan TƏSDİQLƏYİRDİ
2 failed, 11 passed
```

**Yaşıl:**

```
apps/syllabus/tests + apps/organizations/tests/test_permissions.py
  + apps/accounts/tests/test_sidebar_role_matrix.py ......... 223 passed
apps/accounts/tests -k syllabus ............................  62 passed
```

Əhatə olunan hallar: dekan üç qərarda da 403 · öz kafedrasının müdiri 200 ·
BAŞQA kafedranın müdiri 404 (əhatə qapısı, mövcudluq sızmır) · köhnə açarlı
fakültə-scope aktor `out_of_scope` · RİM/rektor override 200 · dekan `start_review`
edə bilir və `can_view` açıqdır · `available_actions` dekana `approve` vermir ·
göndəriş bildirişi müdirə gedir, dekana getmir · müdirsiz kafedrada dekana
QEYDLƏ gedir · `syllabus_repair_chair_units` quru/apply/idempotent.

## 3. Gate-lər

```
black --check ✓   isort --check-only ✓   flake8 ✓        (17 dəyişən .py)
check_module_size.py --check ✓ (SOFT_CAP=600)
module_deps.py --check ✓ (yeni dövr yoxdur)
makemigrations --check --dry-run (sqlite) → No changes detected ✓
check_i18n_catalogs.py ✓ (yeni borc yoxdur)
```

## 4. Klonda canlı təsdiq

```
STAGING_POSTGRES_DB=emsarena_rehearsal_a0d170000901 scripts/staging_inspect.sh migrate
  → organizations.0035_dean_syllabus_review_only applied 2026-09-03 00:29:50
  → organizations_role: dean has_approve=f has_review=t · chair_head has_approve=t ✓

syllabus_repair_chair_units            → QURU İCRA: 0 sillabus (düzələsi sətir yoxdur)
syllabus_repair_chair_units --apply    → 0 (idempotent)
  klonun vəziyyəti: 3 sillabusun 3-ü onsuz da `chair` tipinə bağlıdır (FAZA 27-də düzəlib)

QƏRAR SƏTHİ (qa.dean scope-u MÜVƏQQƏTİ olaraq kafedranın əsl fakültəsinə çəkildi,
sonra BƏRPA olundu — əks halda dekan sillabusu ümumiyyətlə görmürdü):
  qa.dean approve → 403 transition.permission_denied
  qa.dean revise  → 403 transition.permission_denied
  qa.dean reject  → 403 transition.permission_denied
  qa.dean növbə   → HTTP 200 · sətir görünür ✓ · «Təsdiq kafedra müdirinin
                    səlahiyyətindədir» qeydi ✓ · təsdiq düyməsi YOX ✓
  qa.chair_head   → HTTP 200 · sətir görünür ✓ · təsdiq düyməsi VAR ✓
  qa.chair_head approve → 200 → status=approved, approved_by=qa.chair_head
  TƏMİZLİK: status=submitted bərpa olundu, qa.dean scope bərpa olundu ✓

TAM AXIN (yaradıldı → göndərildi → təsdiqləndi → SİLİNDİ):
  qa.teacher qaralama → chair_unit = «Proqramlaşdırma və informasiya təhlükəsizliyi» (chair) ✓
  submit → kafedra müdirinə bildiriş 0 → 1 ✓
  qa.chair_head növbəsində görünür ✓ · əməllər: start_review/approve/request_revision/reject ✓
  approve → approved (approved_by=qa.chair_head) ✓
  TƏMİZLİK: dosye tam silindi ✓
```

QA serveri (`:8100`) yeni kodla yenidən başladıldı (`/accounts/login/` → 200).

## 5. Sahibin 2-ci qərarı (sənədləşdirildi)

**R-7 / A-31e → WONTFIX (2026-09-03):** imtahan mərkəzi əməkdaşı BAŞQA müəllimlərin
sual bankını **oxuya bilər** — mərkəz imtahan variantını qurmaq üçün bankı görməlidir,
hər oxu audit olunur. `ISSUES.md` və `FINAL_REPORT.md` §13 yeniləndi.

## 6. Tərcümə borcu (`.po` faylları paralel agentdədir — TOXUNULMADI)

Aşağıdakı **yeni msgid**-lər az/en/ru/tr kataloqlarına əlavə olunmalıdır
(kontekst → msgid):

| kontekst | msgid |
|---|---|
| `accounts.syllabus` | `Təsdiq kafedra müdirinin səlahiyyətindədir` |
| `accounts.syllabus` | `Bu panel sizin üçün YALNIZ OXUNUR: sillabusu aça, müqayisə edə və bölmə şərhi yaza bilərsiniz. Təsdiq, düzəliş və rədd qərarını aid kafedranın müdiri verir.` |
| `accounts.syllabus` | `Bütün sillabuslar üçün məcburidir və YEGANƏ təsdiq mərhələsidir — state maşını ilə tətbiq olunur.` |
| `accounts.syllabus` | `Tətbiq olunmur: dekanlıq sillabusu görür və şərh yazır, qərar açarı isə kafedra müdirindədir.` |
| `accounts.syllabus` | `Bütün məcburi tələblər ödənildikdən sonra sillabus kafedra müdirinin növbəsinə düşür. Təsdiq kafedra müdirinin səlahiyyətindədir — dekanlıq baxa bilir, qərarı isə müdir verir. Göndərildikdən sonra versiya kilidlənir.` |
| `syllabus.notify` | `Bu kafedra üçün kafedra müdiri təyin edilməyib, ona görə bildiriş dekanlığa göndərildi. Təsdiq kafedra müdirinin səlahiyyətindədir — zəhmət olmasa müdir təyin edin.` |

Köhnəlmiş (artıq işlənməyən) msgid-lər: «Bütün sillabuslar üçün məcburidir — state
maşını ilə tətbiq olunur.», «Universitet siyasətindən asılı ikinci mərhələ — hələ
tətbiq olunmayıb.», «Bütün məcburi tələblər ödənildikdən sonra sillabus kafedra
müdirinin növbəsinə düşür. Göndərildikdən sonra versiya kilidlənir.»

## 7. Bilinən məhdudiyyət

`scripts/i18n_source_scan.py`-ın Python skaneri çoxsətirli/dict-daxili
`pgettext_lazy` çağırışlarını GÖRMÜR (şablonları görür) — yuxarıdakı 6 msgid gate
tərəfindən aşkarlanmadı, əl ilə siyahıya alındı. Ayrıca tapıntı kimi qeyd olunur;
bu fazada düzəldilmədi (skaner paralel agentin sahəsindədir).
