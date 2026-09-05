# EMSArena — istehsala hazırlıq üzrə tam QA auditi
**Tarix:** 2026-09-05 (düzəliş dalğası: 2026-09-06) · **Branch:** `audit/full-qa-2026-09-05` · **Baza:** QA klonu `emsarena_rehearsal_a0d170000901` (:8100)
**Sübut qovluğu:** `~/EMSArena-backups/qa-2026-09-05/` · **Problem siyahısı:** `docs/audits/2026-09-05/ISSUES.md`

---

## 1. İcra xülasəsi

22 rol (29 hesab) ilə kabinetin **645 ekranı** avtomatlaşdırılmış brauzer (Playwright) və HTTP süpürgəsi ilə açıldı; 10 rol üçün mobil (375 px) və planşet (768 px) təkrarlandı. Sonra 8 modul üzrə dərin, ssenari əsaslı sınaq aparıldı: tələbə həyat dövrü, müəllim/sillabus/jurnal dövrü, müraciət axını, icazə/IDOR/tenant matrisi, dərs yükü və imtahan modulları, UX/rəng sistemi/i18n.

**Nəticə:** sistemin **əsas iş axınları işləyir və tenant izolyasiyası möhkəmdir** (bölmə səviyyəsində sızma tapılmadı), lakin auditə qədər **giriş validasiyası zəif** idi (uzunluq/UUID/forma yoxlanmadığı yerlərdə onlarla 500), **iki icazə boşluğu** (crafted POST ilə yekun imtahan balı; dekanın öz əhatəsindən kənar rol verməsi) və **bir «səssiz data itkisi»** (naməlum rol adı → hesab məzuna çevrilirdi) mövcud idi. Bunların hamısı düzəldildi.

| Göstərici | 05 sentyabr | **06 sentyabr (indi)** |
|---|---|---|
| Ümumi QA balı | 71 / 100 | **76 / 100** |
| Tapılan problem | 91 | **92** (P1 11 · P2 41 · P3 22 · UX 18) |
| Düzəldilmiş | 43 | **63** (+3 qismən) |
| Açıq qalan | 44 | **24** (heç biri P0 deyil; 1-i P1) |
| P0 (istehsalı bloklayan) | 0 | **0** |
| Yeni reqressiya testi | 8 fayl | **13 fayl** |

**Qərar: ŞƏRTLƏ HAZIR (READY WITH CONDITIONS)** — §9-dakı 5 şərt ödənilməlidir.

---

## 2. Kateqoriya balları

| Kateqoriya | Bal | Əsas |
|---|---:|---|
| Funksional doğruluq | 78 | 13 ədəd 500 bağlandı, yalançı «uğur» mesajları, səssiz defoltlar (dərs tipi/saatı), səssiz fayl atma və ikiqat göndəriş qapıları |
| Biznes məntiqi | 78 | Dərs yükündə 0-saat / dublikat sətir / koordinator vizası qapıları TƏTBİQ EDİLDİ; dərs tarixinin üst həddi qoyuldu; sillabus «kopyala» və məzun kabineti sahib qərarı gözləyir |
| Rollar və icazələr | 85 | Yeni **RİM əməkdaşı** rolu (məhdud dəst); iki icazə boşluğu bağlandı; «Nəticələrim» menyu↔capability uyğunlaşdırıldı; rədd səbəbləri dəqiqləşdi |
| UX / UI | 72 | Jurnalda yapışqan başlıq, AI düyməsinin örtməsi, yüklənmə skeleti; filtr/əməl nümunələrinin vahidləşməsi qalır |
| Rəng sistemi | 66 | 3 AA pozuntusu + bootstrap badge kontrastı (1.63:1 → 10.95:1) düzəldildi; 790 hex / 2 badge sistemi borc olaraq qalır |
| Performans | 72 | Bütün bölmələrdə icazə sorğuları request-də bir dəfə (dashboard 79→50, 42→13 dublikat); imtahan balı 463→129; kafedra profili 425→67; müraciətlər 81→67; analitika 7.69 s → 0.11 s (keşdən). Jurnalın 41 MB HTML-i açıqdır |
| Data ardıcıllığı | 70 | Xaric/məzun ↔ giriş sinxron; «cari tədris ili» tək mənbədən; legacy «Level …» psevdo-qrupları (72) qalır |
| Təhlükəsizlik | 84 | Bölmə sızması yoxdur (5 rol × bütün yad bölmələr təkrar yoxlanıldı); icazə keşi mutasiya nöqtələrində invalidasiya olunur; HSTS prod-da təsdiqlənməlidir |
| Responsiv | 74 | Mobil sidebar düzəldildi; cədvəllər 375 px-də hələ üfüqi sürüşmə tələb edir |
| Əlçatanlıq (a11y) | 62 | 70 sahəyə `aria-label`, `aria-busy` yüklənmə vəziyyəti, badge kontrastı; `aria-sort` və qalan label-siz sütunlar açıqdır |
| İstehsala hazırlıq | 76 | Bloklayan qüsur yoxdur; qalan şərtlər §9-da (3-cü şərt — dərs yükü qapıları — ARTIQ BAĞLANDI) |

---

## 3. Əhatə: sınanan rollar və modullar

**Rollar (22):** superadmin, rektor, prorektor, dekan, prodekan, kafedra müdiri (×2), proqram koordinatoru, müəllim, tələbə, qrup nümayəndəsi, məzun, RİM, tələbə xidmətləri, HR, tədris şöbəsi (rəis + əməkdaş), imtahan mərkəzi, İKT rəhbəri, korrektor, təşkilat sahibi, qonaq.

**Modullar:** accounts (kabinet qabığı, profil, şəxs kataloqu, rol idarəetməsi, RİM mərkəzi, idxal), registrar (jurnal, dərs qeydiyyatı, qruplar, hərəkətlər, imtahan balı, akademik qeydlər), syllabus (redaktor, autosave, təsdiq axını, kopyalama), applications (göndəriş, marşrut, emal, daxili qeydlər), workload (tapşırıq, dilim, bölgü, cədvəl), exams (sual bankı, kollokvium pəncərələri, imtahan mərkəzi), organizations (struktur ağacı, üzvlüklər), monitoring/ai_assistant (yalnız səthi).

**Metodika:** (1) hər rolla real giriş → sidebar-ın hər elementi açıldı, konsol/şəbəkə xətaları toplandı; (2) hər bölmədə əməllər (yarat/redaktə/sil/filtr/modal/yükləmə) mənfi girişlərlə sınandı (255+ simvol, qeyri-UUID, yad id, mənfi ədəd, JSON forma pozuntusu, ikiqat göndəriş, crafted POST); (3) in-process sorğu profili (`CaptureQueriesContext`) ilə N+1 axtarışı; (4) icazə matrisi: 14 hesab × menyuda olmayan bütün bölmələr.

---

## 4. Düzəldilən əsas problemlər (43)

### İcazə / təhlükəsizlik
- **P1-7 — yekun imtahan balı crafted POST ilə yazılırdı.** Jurnal səhifəsində müəllimə göstərilməyən `exam__<enr>` sahəsi POST-la göndəriləndə İmtahan Mərkəzinin `final_score.entry` səthi yan keçilirdi. İndi bal açarları həmin icazəni tələb edir; **bonus/rəy (U15) müəllimdə qalır** (auditin ilk düzəlişi bütöv əməli bağlamışdı — regresiya `test_final_extras` ilə tutuldu və dar qapıya çevrildi).
- **P1-5 — dekan öz fakültəsindən kənara org-səviyyəli rol verirdi** (legacy `manage-roles` yalnız səviyyə müqayisəsi edirdi). İndi rol-təyinatı axını ilə eyni qapı: `role.assign`/`org.manage_members` + struktur alt-ağacı.
- **P1-6 — naməlum rol adı → hesab «məzun» olurdu.** `resolve_membership_role` uyğun ad tapmayanda ən aşağı səviyyəli rolu (alumni, 5) qaytarırdı, mesaj isə «İmtahan Mərkəzi işçisi əlavə edildi» yazırdı. İndi dəqiq ad → yoxdursa fail-closed + aydın xəta.
- **P1-10 — xaric edilmiş tələbə sistemə girirdi.** Status dəyişikliyi `UserProfile.access_state`-ə sinxronlaşdırılmırdı; indi xaric/məzun → ARCHIVED (portal bağlayır), bərpa → ACTIVE.

### Funksional sınıqlar
- **P1-1 — tam səhifə açılan bölmələrdə bütün JS ölü idi.** `base.html`-də bölmə skriptləri `ems_ajax_init.js`-dən ƏVVƏL yüklənirdi → `EMSReady is not a function`; rol təyinatı modalı, bildiriş hədəf seçicisi işləmirdi (AJAX yolu ilə işlədiyi üçün əvvəlki auditlərdə görünməmişdi). Həll: `<head>`-də növbə stub-u + 32 skriptə `defer` + 3 qatlı test.
- **P1-2 — şəxs kartı (istifadəçi şikayəti).** Ada klik edəndə modal yalnız ad + link göstərirdi, halbuki backend tam JSON qaytarırdı. İndi ems_ui drawer: status, əlaqə, üzvlüklər, akademik/tədris sətirləri, əməllər; ESC bağlayır, fokus içəridə.
- **P1-4 / P2-13 — sillabus redaktorunu «kərpicləmək».** İxtiyari formalı JSON qaralamanı korlayır və redaktoru 500-ə salırdı; mətn sahələrində hədd yox idi (3 MB qəbul olunurdu). İndi forma normalizasiyası + `MAX_TEXT_CHARS/LIST/WEEKS` → 400.
- **P1-9 — müraciət «qara dəliyi».** Aidiyyəti örtən emalçısı olmayan ixtisasdan gələn müraciət heç kimin inbox-una düşmürdü. İndi əhatə açılır (şöbənin bütün rol daşıyıcıları görür + bildiriş), audit izində `coverage=fallback_unscoped`.
- **P2-10 — bağlı jurnala bal POST-u «uğurlu» görünürdü** («0 xana yazıldı» + yaşıl mesaj). İndi kilid → xəta, 0 xana → xəbərdarlıq.
- **P2-16 — qayıb işarəsi ilə bal birlikdə saxlanırdı** (q/b tələbədə 8 bal). **P2-17 — gələcək dərslər «keçirilmiş» sayılırdı** (2099-cu il daxil).
- **500-lər (13 ədəd):** dərs mövzusu 255+, `lesson_instructor=abc`, qeyri-UUID `chair`/`specialty`/`record_id`/`window_id`, `assignee=abc`, bank adı 255+, 150+ simvol ad idxalı, ikinci sillabus yaratma, naməlum hərəkət `kind`.

### Performans
- **P2-5 — imtahan balı siyahısı:** 463 → **129 sorğu**, 697 → 193 ms (hər tələbə üçün `compute_final_result` → `finals_batch.build`; əhatə sorğusu bir dəfə).
- **P2-3 — kafedra profili:** 425 → **67 sorğu** (müəllim başına 4 SUM → tək GROUP BY).
- **P2-19 — akademik qeydlər xülasəsi:** 5 dəqiqəlik TTL keş (ilk açılış hələ ağır — kök həll açıqdır).

### UX / kontrast (batch-4)
- Sidebar aktiv elementi **3.68:1 → 5.17:1**; köməkçi mətn **2.56:1 → 4.76:1** (82 fayl); yaşıl mətn **2.54:1 → 5.02:1** (token faylının öz qaydası tətbiq edildi). Tünd fonlu kontekstlərə (footer, login, kod redaktoru, xəta səhifələri) toxunulmadı.
- AZ interfeysdə «Default format» / «Default sual formatı …» → «Standart …» (4 dil kataloqu).
- Mobil (375 px) tam səhifə açılışında sidebar məzmunu örtürdü → ilkin vəziyyət `collapsed`.
- `<title>` bütün 645 ekranda eyni idi → indi bölmə adı ilə başlayır (AJAX swap-da da yenilənir).

---

## 5. Biznes məntiqi tapıntıları (rol × mərhələ)

| Tapıntı | Vəziyyət |
|---|---|
| Yekun imtahan balı yalnız İmtahan Mərkəzinin səthidir; bonus/rəy müəllimindir | AYDINLAŞDIRILDI + kodla tətbiq edildi |
| Dekan/koordinator öz struktur alt-ağacından kənara rol verə bilməz | TƏTBİQ EDİLDİ |
| Xaric/məzun statusu girişi bağlamalıdır | TƏTBİQ EDİLDİ |
| Dərs yükü diliminin təsdiqi koordinator vizası tələb etməlidirmi? | **AÇIQ — sahib qərarı** (tövsiyə: `workload.visa_required` org-konfiqi, defolt bəli) |
| 0 saatlıq və dublikat yük sətirləri göndərilib təsdiqlənə bilir | **AÇIQ** (readiness → `WorkloadDenied`) |
| Dərs tarixi dövrün `end_date`-ini keçə bilir (2099) | **AÇIQ** |
| Sillabus «kopyala» açılışsız paralel dosye yaradır | **AÇIQ — sahib qərarı** |
| Parol sıfırlaması səbəbsiz qəbul olunur (blok/silmə üçün səbəb məcburidir) | **AÇIQ** (tövsiyə: səbəb məcburi) |
| Məzun kabinetinin əhatəsi (nəticə/transkript bölmələri yoxdur, profil 403) | **AÇIQ — sahib qərarı** |
| «Cari tədris ili» iki mənbədən gəlir (dashboard 2025/2026 Yaz vs yük 2026/2027) | **AÇIQ — konfiq vahidləşməlidir** |

---

## 6. Performans mənzərəsi (in-process sorğu profili + brauzer ölçüsü)

| Səhifə | Əvvəl | Sonra | Status |
|---|---|---|---|
| `exam-score-entry` | 466 sorğu / 697 ms | 129 / 193 ms | ✅ |
| `chair-profile` | 425 sorğu / 368 ms | 67 | ✅ |
| `academic-records` xülasəsi | 7.8–9.5 s | keşdən sonra ani | ⚠️ qismən |
| jurnal (555 tələbə × 226 dərs) | **41.5 MB HTML / 6.3 s** | — | ❌ açıq (P1-8) |
| `analytics` | 2.8–8.2 s | — | ❌ açıq |
| `applications` | 80 sorğu / 38 dublikat | — | ❌ açıq |
| jurnal siyahısı (korrektor) | 3.4–4.2 s | — | ❌ açıq |

---

## 7. Təhlükəsizlik matrisi

- **Bölmə səviyyəsində məlumat sızması tapılmadı.** 14 hesab × menyuda olmayan bütün bölmələr sınandı; 75 «şübhə»nin 55-i sınaq hesabının `password_change_required` bayrağından (ilk-giriş səhifəsi qayıdırdı), 20-si isə `my-results`/`my-appeals`/`my-journal` bölmələrinin heyət üçün boş açılmasıdır (menyu↔capability uyğunsuzluğu, P3-5).
- **IDOR:** jurnal, sillabus, müraciət, şəxs kartı və yük sətirlərində yad `id` ilə çağırışlar 403/404 verir (fail-closed).
- **Başlıqlar:** CSP (`script-src 'self' 'nonce-…'`, `frame-ancestors 'none'`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` mövcuddur. Cookie: `sessionid` HttpOnly+Lax. **HSTS dev-də yoxdur — prod nginx-də təsdiqlənməlidir.**

---

## 8. Reqressiya nəticəsi

- Tam dəst (sqlite, `-m "not postgres"`): **7 465 keçdi / 7 düşdü**. Düşənlərin 6-sı `origin/Develop`-da da düşür (sqlite + `--no-migrations` artefaktı; CI Postgres-də keçir), 1-i auditin öz düzəlişindən yaranmışdı (`test_final_extras`) və dar qapıya çevrilərək bağlandı.
- Yekun təkrar (toxunulan 6 app: accounts, registrar, applications, syllabus, workload, exams): **4 242 keçdi / 5 düşdü — beşi də `origin/Develop`-da eyni şəkildə düşür** (baseline ilə müqayisə edildi), yəni auditin buraxdığı reqressiya **yoxdur**.
- Qapılar: `black` / `isort` / `flake8` ✅ · `check_module_size.py` ✅ · `module_deps.py` ✅ (audit zamanı yaranan `organizations↔registrar` dövrü `journal_scope` fasadı ilə aradan qaldırıldı) · `check_i18n_catalogs.py` ✅ (4 dil).
- Canlı təsdiq: düzəlişlərdən sonra rol-təyinatı və bildiriş bölmələri **0 konsol xətası**; şəxs kartı tam məzmunla açılır; sidebar aktiv fonu `rgb(37,99,235)`.

---

## 9. Qərar və şərtlər

### ŞƏRTLƏ HAZIR (READY WITH CONDITIONS)

İstehsalı bloklayan (P0) qüsur yoxdur; auditin tapdığı bütün icazə boşluqları və data korlayan hallar bağlanıb. Buraxılışdan əvvəl **5 şərt**:

1. **Jurnal miqyası (P1-8).** Ən böyük açılış 41.5 MB HTML / 6.3 s verir — real sessiyada brauzer donur. Dərs pəncərəsi üzrə səhifələmə tələb olunur.
2. **`academic-records` ilk açılışı (P2-19).** Keş sonrakı açılışları həll edir, İLK açılış hələ 13 s: profil göstərir ki, vaxt Python-dadır — 148 633 yazılış üçün `analytics._evaluate` (~4 s), 969 162 UUID obyekti (~2 s), 203 515 model instansiyası (~1.8 s). Həll: yazılışları model kimi yükləmədən (values/SQL aqreqatı) hesablamaq. *(Analitika bölməsi 06.09-da keşləndi: 7.69 s → 0.11 s.)*
3. ~~**Dərs yükü biznes qapıları (P2-35/36/37).**~~ ✅ **BAĞLANDI (06.09):** 0 saatlıq sətir göndərilmir, dublikat sətir yaradılmır, dekan təsdiqi koordinator vizası tələb edir (`workload.visa_required`, əhatə qaydası ilə).
4. **Legacy «Level …» psevdo-qrupları (P2-8).** 72 qrup + 2 «Xaric olunanlar» konteyneri statusa çevrilməli və ya «xidməti» kimi işarələnməlidir; əks halda dekan/RİM siyahılarında əsl akademik qrup kimi görünür.
5. **Prod başlıqları və a11y minimumu.** HSTS təsdiqlənməli; ən çox işlənən 5 formada (imtahan balı, rol təyinatı, tələbə idxalı, müraciət, yük bölgüsü) label-siz input-lar bağlanmalıdır.

**Tövsiyə edilən ardıcıllıq:** 4 (semestr məlumatı) → 1 (jurnal miqyası) → 2 → 5.

---

## 10. İkinci dalğa (06 sentyabr) — əlavə düzəlişlər

- **RİM əməkdaşı rolu** (`rim_staff`, səviyyə 60): akademik səthlərin oxusu + imtahan/QA əməlləri; rol vermə, parol/blok, tələbə idxalı və jurnal düzəlişi rəhbərdə qalır.
- **Kollokvium pəncərələri:** keçmiş bağlanış tarixi və K-sırası pozuntusu rədd olunur.
- **Qlobal tərcümə səhvi:** Django-nun `"This field is required."` msgid-i AZ kataloqda «Fayl seçilməyib.» idi — bütün formalarda hər boş məcburi sahə yanlış mesaj verirdi.
- **Performans:** icazə sorğularının deduplikasiyası (bütün bölmələr), müraciətlər kataloq keşi, analitika keşi.
- **Jurnal:** yapışqan başlıq sətri (555 tələbədə yoxlanıldı), ikiqat «Yadda saxla» qoruması, dərs tipi/saatı validasiyası.
- **A11y/UX:** 70 `aria-label`, badge kontrastı, yüklənmə skeleti, AI düyməsinin örtməsi.
- **Audit izi:** parol sıfırlamasında səbəb məcburi; RİM rədd səbəbləri dəqiq.

