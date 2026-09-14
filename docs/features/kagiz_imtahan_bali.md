# Kağız imtahan balının sistemə daxil edilməsi

Kabinet bölməsi: **«İmtahan balının daxil edilməsi»** (`?section=exam-score-entry`,
yan paneldə «İmtahan mərkəzi» qrupu). Sənəd 2026-09-14 vəziyyətini təsvir edir
(commit-lər `6340394b`, `b7acc5e2`, `deda4b73`, `408c8e52`); bütün qaydalar koddan və
testlərdən oxunub — mənbələr sonda (§11).

Sahibin qərarı (2026-08): yazılı və praktiki imtahan **kağız üzərində** keçir, sistemdən
getmir. Balları sonradan İmtahan Mərkəzi bu bölmədən köçürür. Sahibin 2026-09-14 qaydası:
*«hər sualdan max 10, imtahandan max 50, yekun bal 100-dən çox ola bilməz; apellyasiyadan
sonra dəyişən nəticələr izlənsin»* — hamısı **server tərəfdə məcburidir** (JS yalnız
rahatlıq üçündür).

---

## 1. Kim görür / kim yaza bilər

Bölmə **`final_score.entry`** icazəsi ilə açılır. Bu açar qəsdən `exam.*` wildcard-ına
daxil deyil — rol şablonunda ayrıca verilir.

| Rol | Mənbə | Əhatə |
|---|---|---|
| İmtahan Mərkəzi rəhbəri (`exam_center_head`) | defolt rol şablonu | bütün təşkilat |
| Rektor (`rector`) | `*` (bütün icazələr) | bütün təşkilat |
| RİM rəhbəri (`ikt_rehber`) | sahibin qərarı 2026-09-14, miqrasiya `organizations.0052` | bütün təşkilat |
| Superadmin | bypass | istənilən təşkilat (bölmə başında «Təşkilat» seçicisi) |
| Dekan / kafedra müdiri | yalnız icazə redaktorundan **açıq** verilərsə | yalnız öz struktur alt-ağacının qrupları (fail-closed) |

Müəllim bu bölməni görmür, POST edə bilmir və CSV ixracını da ala bilmir (hamısı 403).
Unit-scoped aktor əhatədən kənar açılışa yazmağa cəhd edəndə server
«Bu açılış sizin struktur əhatənizdə deyil.» ilə dayandırır.

**Jurnal kilidi bu yolu bloklamır**: jurnal semestr sonunda bağlanır, imtahan ondan sonra
keçir; kilidli açılışda bölmə «bal yenə yazılır» izahı göstərir.

---

## 2. Tipik iş axını (qısa)

**A. Kağız protokoldan balların ilk köçürülməsi**

1. Tədris ili / semestr → (istəyə görə müəllim) → **qrup** → **fənn** seçin.
2. «Vərəq məlumatları» kartını doldurun: imtahan növü, tarix, yoxlayan, nəzarətçi,
   protokol №, sual sayı, bir sualın maksimumu; skanı əlavə edin (ilk köçürmədə opsional).
3. Hər tələbə üçün S1…Sn seçicilərini (və ya sual sayı 0-dırsa «Bal» sahəsini) doldurun —
   cəm və hərf canlı görünür.
4. «Balları yadda saxla» → təsdiq dialoqu (ad · giriş · imtahan · yekun · hərf) → «Təsdiq et».
5. Nəticə mesajı: neçə sətir yazıldı / ötürüldü / rədd olundu; rədd olunanlar tələbə adı
   ilə sadalanır.

**B. Artıq yazılmış balın dəyişdirilməsi (apellyasiya / düzəliş)**

1. Eyni siyahıda balı dəyişin (dəyişən sətir sarı işarələnir, «Dəyişdirilib» KPI-ı artır).
2. «Balları yadda saxla» → dialoqda **dəyişikliyin növü** (Sənədli dəyişiklik /
   Apellyasiya nəticəsi) + **səbəb** + **qeyd** doldurun; vərəq kartında **skan** seçin
   (dialoq «✓ / ✗» statusunu göstərir). Üçü də olmadan dialoq göndərmir.
3. «Təsdiq et». Sonradan bu sətir «Dəyişən nəticələr» görünüşündə və tələbənin tarixçə
   çekmecəsində görünür.

**C. Fayldan (XLSX/CSV) yükləmə**

1. Tab «Fayldan yüklə» → **Şablon** endirin (siyahı ilə doldurulmuş gəlir).
2. Faylı doldurub yükləyin → **Yoxla** (quru icra): hər sətrin vəziyyəti göstərilir.
3. Dəyişən sətir varsa səbəb + qeyd + skan verin → **Tətbiq et**.

---

## 3. Seçim axını (Seç → Yoxla → Yaz)

1. **Tədris ili → Semestr** — defolt cari semestr (jurnal bağlama bölməsi ilə eyni
   heuristika).
2. **Müəllim** (opsional, «Bütün müəllimlər») — seçiləndə qrup və fənn siyahısı həmin
   müəllimin açılışlarına daralır.
3. **Qrup** — bu dövrdə aktiv açılışı olan qruplar (axtarışlı seçici). Qrupsuz açılışlar
   bu siyahıda yoxdur; onlar köhnə **fənn-əvvəl** sırada (`?ese_mode=subject`) «(qrupsuz
   açılış)» kimi görünür. Qrup-əvvəl sıra defoltdur.
4. **Fənn** — qrupun açılışları «`KOD — Fənn adı · Müəllim`» etiketi ilə.
5. Açılış seçilən kimi: KPI kartları (Tələbə / Bal yazılıb / Gözləyir / Orta imtahan balı
   / Dəyişdirilib), **vərəq məlumatları** kartı, tələbə siyahısı, vərəq tarixçəsi, idxal tabı.

Siyahı üstündə **tələbə axtarışı** (ad · istifadəçi adı · FİN · tələbə №) və **vəziyyət
çipləri** (hamısı · boş · yazılıb · dəyişdirilib) var — hamısı yaddaşda süzülür, sorğu
sayı siyahı ölçüsündən asılı deyil (test: 5 tələbə = 60 tələbə = eyni sorğu sayı).
Süzülüb görünməyən sətir formada da yoxdur → yadda saxlama ona toxunmur. Vərəq
tarixçəsində «hamısı · yazılı · praktiki» növ çipləri var.

Siyahıya **yalnız statusu `enrolled` olan qeydiyyatlar** düşür.

---

## 4. Vərəq (köçürmə partiyası) məlumatları

Hər «Balları yadda saxla» bir **köçürmə vərəqi** (`ExamScoreSheet`) yaradır; bütün yazılan
sətirlər ona bağlanır. Formanın ilkin dəyərləri sonuncu vərəqdən gəlir (eyni protokolu bir
neçə oturuşda köçürəndə metadata təkrar yazılmır).

| Sahə | Qayda |
|---|---|
| **İmtahan növü** | `yazılı` (defolt) və ya `praktiki`; başqa dəyər → «İmtahan növü yazılı və ya praktiki olmalıdır.» Vərəq səviyyəsindədir — bir protokol bir növ imtahandır. Köhnə vərəqlər «yazılı» sayılır. |
| **İmtahan tarixi** | opsional; `YYYY-MM-DD` və ya `DD.MM.YYYY`; yanlış format → «İmtahan tarixi düzgün formatda deyil.» |
| **Yoxlayan müəllim** | təşkilatın müəllimlərindən seçilir (axtarışlı seçici); boş → açılışın müəllimi. Seçilən şəxs təşkilatın **aktiv üzvü** olmalıdır, əks halda «Seçilmiş şəxs bu təşkilatın aktiv üzvü deyil.» Ad snapshot kimi də saxlanır (müəllim sonradan çıxsa vərəq tarixi qalır). |
| **Nəzarətçi** | opsional; eyni seçici və eyni üzvlük yoxlaması. |
| **Protokol / vərəq №** | mətn, ≤ 64 simvol (artığı kəsilir). |
| **Sual sayı** | `0…10`; boş → **5**. `0` = tək yekun bal rejimi (sual sahələri yoxdur). `> 10` → «Sual sayı 0 ilə 10 arasında olmalıdır.» |
| **Bir sualın maksimumu** | `1…10`; boş → **10**. Sahibin qaydası: tavan 10-dan yuxarı qaldırıla bilməz («Bir sualın maksimum balı 1 ilə 10 arasında olmalıdır.»); aşağı ola bilər (10 sual × 5 = 50). |
| **Qeyd** | opsional. |
| **Skan edilmiş protokol / vərəq** | PDF və ya şəkil (`.pdf .jpg .jpeg .png .webp .heic .heif`), ≤ 10 MB. İlk daxiletmədə opsional; **artıq yazılmış balı dəyişəndə məcburi** (§7). Yanlış fayl bütün partiyanı dayandırır — heç bir bal yazılmır. |

Vərəq başqa açılışa/tenanta aid ola bilməz — üç qatda yoxlanır (servis
`assert_sheet_matches`, model `clean()`, PostgreSQL trigger
`registrar_exam_score_entry_sheet_guard`, miqrasiya `registrar.0073`).

---

## 5. Bal daxil etmə qaydaları

Siyahıda hər tələbə üçün **S1…Sn** sual seçiciləri (0…maksimum) və ümumi «Bal» sahəsi var.
JS canlı cəm və hərf göstərir, amma **server avtoritetdir** — formadan gələn bütün
dəyərlər `record_exam_score` servisində yenidən yoxlanır.

| Qayda | Server mesajı / nəticə |
|---|---|
| Tələbənin hər hansı S xanası doludursa imtahan balı **sualların cəmidir**; «Bal» sahəsi nəzərə alınmır. | server hesablayır |
| Hər sual balı tam ədəd, `0 … bir sualın maksimumu` | «S3 balı 0 ilə 10 arasında olmalıdır.» / «S3 balı tam ədəd olmalıdır.» |
| Qismən doldurulmuş sətirdə boş sual `0` sayılır (cavabsız sual). Boş (—) və 0 fərqlidir: bütün xanalar boş = toxunma. | |
| Sual sayı vərəqin sual sayından çox ola bilməz (JS artıq xanaları söndürür; gəlsə də rədd). | «Sual sayı vərəqin sual sayından (5) çox ola bilməz.» |
| Cəm **imtahan balının tavanını** aşa bilməz. Tavan sabit 50 deyil — açılışın qiymətləndirmə sxemindən gəlir: `100 − giriş balı tavanı` (defolt giriş 50 → imtahan 50). | «Sualların cəmi (55) imtahan balının tavanını (50) aşır.» |
| Sual sayı 0 olan vərəqə sual balı göndərilsə rədd. | «Bu vərəq tək yekun bal rejimindədir — sual balı qəbul olunmur.» |
| Tək bal rejimində «Bal» tam ədəd `0…tavan`. | «Bal 0 ilə 50 arasında olmalıdır.» |
| **Giriş + imtahan ≤ 100** — tavanlar bunu onsuz da örtsə də açıq yoxlanır. | «Giriş balı (60) + imtahan balı (45) 100-dən çox ola bilməz.» |
| Bütün sahələr boş → sətir **toxunulmur** (kütləvi silinmə riski yoxdur). | ötürüldü |
| Eyni bal təkrar yazılırsa → **idempotent**: nə yeni sətir, nə audit. Eyni cəm, amma fərqli sual bölgüsü → bu **dəyişiklikdir** (kağız qeydi dəyişir): tarixçə sətri yazılır, yekun bal toxunulmur. | |
| Qeydiyyat artıq aktiv deyilsə (köçürülüb / ləğv olunub) sətir yazılmır. | «Bu qeydiyyat aktiv deyil — bal yazılmadı.» |
| Hər sətir öz savepoint-ində yazılır: bir sətrin rədd olunması digərlərini dayandırmır; xətalar tələbə adı ilə mesajlarda göstərilir. | |

Hədəf `FinalGrade.exam_score` (`finals.set_exam_score` ilə); audit izində mənbə
«imtahan mərkəzi · əl ilə».

---

## 6. Təsdiq dialoqu

«Balları yadda saxla» **birbaşa göndərmir** — dialoq açır (Enter / kənar submit bloklanır;
yalnız dialoqun «Təsdiq et» düyməsi POST edir, ikiqat göndəriş kilidlənir).

- Xətalı (qırmızı) sətir varsa dialoq açılmır, ilk xətalı sahə fokuslanır; yazılacaq sətir
  yoxdursa «dəyişiklik yoxdur» mesajı.
- Başlıqda: imtahan növü, tarix, yoxlayan; xülasə: tələbə sayı, yazılacaq sətir, dəyişən
  sətir (xəbərdarlıq rəngi), toxunulmayan sətir.
- Cədvəl: hər yazılacaq tələbə üçün **ad · giriş balı · imtahan balı · yekun · hərf**.
  Hərf **təşkilatın öz şkalası** ilə hesablanır (`grading_scale.bands_for`, `json_script`
  ilə gəlir — uydurma hədd yoxdur). Kəsilmə qaydası server ilə eynidir: yekun ≥ keçid
  həddi (sxem defoltu 51) **və** imtahan ≥ minimum imtahan balı (sxem defoltu 17) **və**
  tələbə davamiyyətdən kəsilməyib; əks halda **F qırmızı** nişan, başlıqda «N tələbə
  kəsilir (F)».
- **Dəyişən sətir varsa** dialoqda əlavə blok: **dəyişikliyin növü** + **səbəb** + **qeyd**;
  vərəq kartında **skan** seçilməlidir («✓ / ✗» statusu). Üçü də olmadan dialoq POST etmir.

---

## 7. Artıq yazılmış balın dəyişdirilməsi (təqdimat)

İlk daxiletmə sərbəstdir. **Sonrakı dəyişiklik** — `apps/registrar/corrections.py` ilə eyni
müqavilə — üç şeyin hamısını tələb edir; biri çatmırsa sətir rədd olunur:

| Tələb | Seçimlər / qayda | Server mesajı |
|---|---|---|
| Səbəb | Tibbi arayış · Rəsmi icazə / ezamiyyət · Daxiletmə xətası · Apellyasiya qərarı · Digər (qeydə bax) | «Balı dəyişmək üçün səbəb seçilməlidir.» |
| Qeyd | boş ola bilməz | «Balı dəyişmək üçün izahat qeydi məcburidir.» |
| Sənəd | sətrin öz faylı **və ya** vərəqin skanı (bir protokol bütün dəyişiklikləri əsaslandırır) | «Balı dəyişmək üçün təsdiqedici sənəd əlavə olunmalıdır.» |
| Dəyişikliyin növü | **Sənədli dəyişiklik** (`correction`) və ya **Apellyasiya nəticəsi** (`appeal`); naməlum → `correction`. İlkin daxiletmədə həmişə «İlk daxiletmə». | |

Səbəb/qeyd/növ dialoqda bir dəfə verilir və hər dəyişən sətrə tətbiq olunur. Sətirlər
append-only `ExamScoreEntry` jurnalındadır — yaradıldıqdan sonra dəyişdirilmir, silinmir.

---

## 8. «Dəyişən nəticələr» görünüşü

Bölmə başında «Dəyişən nəticələr» keçidi (`?ese_view=changes`). Tenantın bütün
`kind != initial` sətirləri (sənədli düzəliş + apellyasiya nəticəsi), ən yenidən köhnəyə,
**50-lik səhifələmə**. Əhatə siyahı ilə eynidir (unit-scoped aktor yalnız öz alt-ağacını
görür; müəllim üçün bölmə paneli ümumiyyətlə render olunmur). Sorğu sayı sətir sayından
asılı deyil (test: 2 = 40).

Filtrlər: qrup · fənn · müəllim · növ (hamısı / sənədli dəyişiklik / apellyasiya nəticəsi)
· imtahan növü çipləri (hamısı / yazılı / praktiki) · tarixdən / tarixədək · tələbə axtarışı.

Sütunlar: Tarix · Tələbə · Fənn / qrup · İmtahan növü · Köhnə → yeni · Növ · Səbəb · Kim ·
Sənəd · (tarixçə düyməsi).

**CSV ixracı** (`accounts:exam_score_changes_export`, fayl
`imtahan-bali/deyisen-neticeler.csv`) eyni filtrlərlə — «gördüyün cədvəl = endirdiyin
fayl»; bir çağırışda ≤ 5 000 sətir; hüceyrələr `core.export_safety.safe_csv_writer` ilə
formula-neytrallaşdırılır. Sütunlar: Tarix, Tələbə, Tələbə №, FİN, Fənn, Qrup, Müəllim,
İmtahan növü, Köhnə bal, Yeni bal, Sual balları, Növ, Səbəb, Qeyd, Kim, Protokol №, Sənəd.
İxrac da `final_score.entry` qapısındadır.

---

## 9. Fayldan yükləmə (XLSX / CSV, S1…Sn)

Tab «Fayldan yüklə»: **Şablon → Yoxla (quru icra) → Tətbiq et**. Fayl serverdə saxlanılmır
(tətbiq eyni faylı yenidən göndərir).

- **Şablon** (XLSX və ya CSV) siyahı ilə doldurulmuş gəlir: Tələbə № · FİN · Ad Soyad · Qrup ·
  Cari bal · İmtahan növü · Bal (0–50) · S1 … Sn (0–max). XLSX-də hüceyrə validasiyası var.
  Şablon vərəq kartındakı sual sayı / bir sualın maksimumu / növü ilə endirilir
  (`?question_count=&question_max=&exam_kind=`; parametrsiz — sonuncu vərəqin şəbəkəsi) —
  2026-09-14 dalğa 6 (`1ffa623b`).
- **Fayl limitləri**: `.xlsx .xlsm .csv`, ≤ 5 MB, ≤ 1 000 sətir, ≤ 64 sütun; sütun sırası
  sərbəstdir, başlıqlar tanınır («Tələbə №/username/login», «FİN», «Ad Soyad»,
  «Bal/İmtahan balı», «S1 / S 1 / Sual 1 / Q1 / Question 1» …). XLSX-də `Ballar` vərəqi,
  yoxdursa birinci vərəq; XLSX zip-bomb yoxlamasından keçir (≤ 20 MB açılmış).
- **Tələbə tanınması**: Tələbə № (istifadəçi adı / institusional id) və ya FİN; ikisi də
  varsa eyni tələbəyə aid olmalıdır («Tələbə № və FİN fərqli tələbələrə aiddir.»); heç biri
  yoxdursa Ad Soyad ilə — yalnız tək uyğunluq qəbul edilir («Eyni adlı bir neçə tələbə var —
  Tələbə № və ya FİN yazın.»). Faylda təkrarlanan tələbə → «Bu tələbə faylda təkrarlanır.»
- Sətirdə S xanası doludursa bal **S-lərin cəmidir**, «Bal» sütunu nəzərə alınmır; «Bal»
  sütunu artıq məcburi deyil.
- **Quru icra** heç nə yazmır; hər sətrin vəziyyəti: yeni · dəyişir · eyni bal · boş · xəta.
  Dəyişən sətir varsa tətbiqdə **səbəb + qeyd + skan** üçü də tələb olunur, əks halda bütün
  tətbiq 400 ilə dayanır («Yazılmış balı dəyişən sətirlər var — səbəb, qeyd və skan edilmiş
  sənəd tələb olunur.») — yarımçıq partiya yaranmır.
- Quru icra planı vərəq kartındakı şəbəkə ilə qurulur — ön baxış və tətbiq eyni yoxlamadan keçir (2026-09-14, `1ffa623b`).
  tətbiqdə servis vərəqin öz şəbəkəsi ilə yenidən yoxlayır — uyğunsuzluq sətir xətası kimi
  görünür (bax §10).
- Tətbiq endpoint-i istifadəçi başına rate-limitlidir (`SCORE_WRITE_RATE_LIMIT`, defolt
  `120/1m`; dolanda 429 + `Retry-After`). Siyahı formasının POST-u bu limitə tabe deyil.

---

## 10. Tarixçə çekmecəsi, vərəq tarixçəsi, audit, statistika

- Siyahıda hər tələbənin **tarixçə** düyməsi çekmecə açır: bütün daxiletmələri (tarix, növ,
  köhnə → yeni, S1…Sn bölgüsü, səbəb, qeyd, kim, sənəd / vərəq skanı, protokol №, imtahan
  tarixi, yoxlayan) + tələbənin bu fənn üzrə imtahan cəhdləri güzgüsü.
- **Vərəq tarixçəsi** paneli: açılışın son 20 vərəqi (mənbə əl ilə / fayl idxalı, növ,
  tarix, yoxlayan, nəzarətçi, protokol, `yazıldı / ötürüldü / rədd` sayğacları, skan).
  Heç nə yazılmayan, heç nə rədd olunmayan və skanı olmayan vərəq **silinir** (tarixçə boş
  partiyalarla dolmasın).
- **Audit**: hər yazılan sətir üçün `registrar.exam_score_entry` (köhnə → yeni,
  `question_scores`); hər vərəq üçün bir `registrar.exam_score_sheet` xülasəsi (açılış,
  tarix, protokol, sayğaclar).
- **İmtahan Mərkəzi statistikası** bölməsində kağız imtahan KPI-ları növ üzrə (vərəq sayı,
  daxiletmə, dəyişiklik, tələbə sayı, orta imtahan balı — hər qeydiyyatın sonuncu daxiletməsi).

**Məlum açıq məqamlar:** yoxdur — şablon endirmə və quru icra boşluqları 2026-09-14 dalğa 6-da
bağlandı (`1ffa623b`).

---

## 11. Mənbələr

| Nə | Fayl |
|---|---|
| Yazı servisi (tək yazı yolu, idempotentlik, təqdimat) | `apps/registrar/exam_score_entry.py` |
| Sual balları validasiyası | `apps/registrar/exam_score_questions.py` |
| Vərəq (partiya), qrup-əvvəl oxu, yoxlayan/nəzarətçi | `apps/registrar/exam_score_sheets.py` |
| Siyahı, tarixçə sətri, filtrlər, şkala | `apps/registrar/exam_score_roster.py` |
| «Dəyişən nəticələr», CSV, KPI | `apps/registrar/exam_score_changes.py` |
| Fayl idxalı (şablon / plan / tətbiq), oxuyucu, zip qoruması | `apps/registrar/exam_score_import.py`, `exam_score_import_reader.py`, `exam_score_import_safety.py` |
| Model (append-only sətir, vərəq, sabitlər) | `apps/registrar/models/exam_score_entry.py` |
| Bölmə view-ları | `apps/accounts/views/exam_score_entry.py`, `exam_score_import.py`, `exam_score_entry_changes.py`, `apps/accounts/views/profile/_sections/exam_score_*.py` |
| JS (canlı cəm, təsdiq dialoqu) | `apps/accounts/static/accounts/js/exam_score_entry.js`, `exam_score_entry_confirm.js` |
| Rollar / icazə | `apps/organizations/default_roles_university.py`, `apps/organizations/permissions.py`, miqrasiya `organizations/0052_rim_final_score_entry.py` |
| Rate-limit | `core/write_rate_limit.py`, `config/settings/components/admin_ratelimit.py` |
| Testlər | `apps/registrar/tests/test_w2_exam_score_questions.py` (30: validasiya matrisi, servis, idxal, dəyişənlər, şkala, tavan 10), `apps/accounts/tests/test_w2_exam_score_entry_section.py` (25: bölmə, POST, çiplər, CSV, RİM, sorğu büdcəsi, təsdiq dialoqu markup-ı), `test_exam_score_entry.py`, `test_exam_score_import.py`, `test_exam_score_sheet_invariants.py` |
