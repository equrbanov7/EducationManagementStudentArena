# İmtahan sehrbazında reyestr qruplarının təyinatı

Müəllim kabinetində «İmtahanlarım» → «Yeni imtahan» / «Redaktə» sehrbazı (modal).
Sənəd 2026-09-14 vəziyyətini təsvir edir (commit `3b0721a5`, W4 `w4wizard`); qaydalar
koddan və testlərdən oxunub — mənbələr §8.

Sahibin qərarı (2026-09-07): **qrup reyestri əsasdır** (`OrgUnit`, tip `GROUP`, məs.
«634 ing»); köhnə imtahan kohortları (`exams.StudentGroup`) silinməyə gedir. 2026-09-14-ə
qədər sehrbaz yalnız kohortları tanıyırdı — real akademik qrup imtahana təyin edilə bilmirdi.
İndi `Exam.allowed_units` ilə reyestr qrupu birinci dərəcəli təyinat yoludur.

---

## 1. Sehrbazın addımları

| № | Addım | Alt-başlıq | Sahələr |
|---|---|---|---|
| 1 | **Əsaslar** | Ad, növ, kateqoriya | ad, təsvir, tip, kateqoriya (quiz / midterm / final / placement / practice), fənn |
| 2 | **Vaxt və suallar** | Tarix, müddət, sual sayı | başlama, bitmə, ümumi müddət (dəq), təsadüfi sual sayı, sual vaxtı, cəhd sayı |
| 3 | **Giriş** | Status, kim girə bilər | dərc statusu (yalnız oxunur), hamıya açıq, **Reyestr qrupları**, fərdi tələbələr, istisna tələbələr, (varsa) köhnə kohortlar |
| 4 | **Nəzarət** | Köçürməyə qarşı nəzarət | nəzarət rejimi parametrləri (istəyə görə) |

Server tərəfi 400 cavabında addım **0-dan başlayan** indekslə gəlir (`step: 1` = «Vaxt və
suallar», `step: 2` = «Giriş») — aşağıda insan sırası (1…4) yazılır, kod indeksi mötərizədə.

---

## 2. Reyestr qrupu seçicisi («Reyestr qrupları», addım 3)

**Kim namizəd olur.** Seçici `exams:group_search?kind=units` ilə axtarır; nəticə
imtahanın təşkilatının **aktiv** (`is_active=True`) **`GROUP`** tipli vahidləridir, etiket
«`Qrup adı — Valideyn vahid`» (məs. «634 ing — Dizayn»). Fakültə, kafedra və s. seçilə
bilməz.

**Əhatə.** Unit-scoped rol (dekan, kafedra müdiri — `exam.create` icazəsi alt-ağaca
bağlıdırsa) yalnız **öz alt-ağacının** qruplarını görür; org-wide rol və kurs-səviyyəli adi
müəllim bütün təşkilatı görür (test: dekan `?kind=units` ilə yalnız öz fakültəsinin qrupunu
alır).

**Addım-addım (yeni imtahan):**

1. «Yeni imtahan» → addım 1–2-ni doldurun → «Növbəti».
2. Addım 3-də «Reyestr qrupları» axtarışına qrup adının bir hissəsini yazın (məs. `634`),
   siyahıdan qrupu seçin — bir neçə qrup seçilə bilər.
3. Aşağıdakı «Tələbələr» siyahısında seçilən qrupların üzvləri işarələnir
   (`user_search?units=`); lazım gələrsə **istisna** tələbə qeyd edin (bax §6 məhdudiyyəti).
4. Sağ paneldə / təsdiq dialoqunda «Qruplar: …» və ümumi tələbə sayı görünür
   (`assigned_student_count?units=` — yalnız hüquqlu tələbələr sayılır).
5. «Yarat» → imtahan **qaralama** kimi yaranır. Suallar əlavə edildikdən sonra imtahan
   səhifəsindəki «Aktiv et» düyməsi ilə tələbələrə açılır.

Redaktədə seçili qruplar formada seçili gəlir; unit-scoped redaktor başqa fakültənin
əvvəlcədən təyin olunmuş qrupunu **görməsə də**, yadda saxlama onu silmir (görünməyən
qruplar qorunur).

---

## 3. Tələbə hansı halda imtahanı görür və başlaya bilər

Qrup üzvlüyü **tək mənbədən** oxunur: tələbənin cari akademik qeydi
(`StudentAcademicRecord.group`). Şərt (`apps/exams/domain/unit_assignment.py`):

| Şərt | Nəticə |
|---|---|
| Qeyd `is_active=True` **və** `status = enrolled` | tələbə hüquqludur |
| Qeyd qeyri-aktivdir (`is_active=False`) | görmür, başlaya bilmir |
| Status `expelled`, akademik məzuniyyət və s. (`enrolled` deyil) | görmür, başlaya bilmir |
| Başqa qrupun tələbəsi | görmür |
| Başqa təşkilatın tələbəsi | görmür (RLS + filtr) |

`Membership.scope_unit` **mənbə deyil** (klon bazasında 7 799 qeyd qrupla, üzvlük vahidi
cəmi 1 sətirdə dolu idi).

Eyni şərti **bütün oxuyanlar** işlədir ki, «siyahıda görünür, amma başlaya bilmir»
uyğunsuzluğu olmasın:

- giriş siyasəti — `Exam.can_user_see` / `can_user_start` (`_user_in_allowed_groups`
  kohort **və ya** reyestr qrupu) və servis `access_policy.can_user_access_exam`;
- tələbənin «Təyin olunmuş imtahanlar» siyahısı və kabinet «Təyin olunmuş tapşırıqlar»
  sayğacı (`accounts.queries.assignments.get_assigned_exams_for_user`);
- toplu siyahı (`StudentExamListBatch`) — sorğu sayı imtahan sayından asılı deyil
  (test: 1 imtahan = 3 imtahan);
- bildiriş alıcıları və PIN provizionu (`notifications.get_exam_assigned_user_ids`);
- dublikat (`duplicate_exam`) — `allowed_units` kopyalanır (suallar kopyalanmır — bu
  dizayndır, toast xəbərdarlıq verir).

Giriş siyasətinin sırası (`can_user_see`): müəllif → aktiv/arxiv deyil → **istisna siyahısı**
(hamıya açıq imtahanda da işləyir) → hamıya açıq → fərdi tələbə → qrup (kohort **və ya**
reyestr) → kurs → giriş kodu. Yəni «hamıya açıq» seçilibsə qrup seçimi nəzərə alınmır.

---

## 4. PIN provizionu (final / midterm)

Kateqoriya **`final`** və ya **`midterm`** olan imtahanda hər təyin olunmuş tələbəyə fərdi
`ExamStudentPin` yaradılır (`provision_exam_student_pins`, idempotent). Reyestr qrupu
əlavə/çıxarılanda `allowed_units` M2M siqnalı (`exams/signals.py`) provizionu yenidən
işə salır:

- qrupun **hüquqlu** (aktiv + `enrolled`) tələbələrinə PIN yaranır; xaric olunmuş tələbəyə
  yaranmır (test);
- artıq təyin olunmayan tələbənin PIN-i silinir;
- kateqoriya final/midterm deyilsə mövcud PIN-lər təmizlənir.

**Məlum boşluq:** tələbə **qrup dəyişəndə** (`StudentAcademicRecord.group` transferi) PIN-lər
avtomatik yenilənmir — imtahan yenidən saxlananda / provizion yenidən çağırılanda düzəlir
(registrar tərəfində siqnal W5 `w5left` işində).

---

## 5. Köhnə kohortlar («Köhnə kohortlar» bloku)

`exams.StudentGroup` seçicisi yalnız **təşkilatda belə qrup varsa** (və ya imtahanda
əvvəldən seçilibsə) göstərilir — tam en, solğun, «Reyestr qrupları»ndan aşağıda. Yeni
təşkilatda / kohortsuz bazada blok ümumiyyətlə render olunmur (test: redaktə formasında
`name="allowed_groups"` yoxdur). Kohort üzvlüyü giriş siyasətində hələ də tanınır (geri
uyğunluq); yeni təyinat üçün reyestr qrupunu işlədin.

---

## 6. Validasiya qaydaları

### Addım 2 («Vaxt və suallar») — klient tərəfi (`exam_wizard.js`)

Xəta **addımın öz sahəsində** göstərilir, sahə fokuslanır, «Növbəti» keçmir:

| Qayda | Mesaj |
|---|---|
| bitmə ≤ başlama | «Bitmə vaxtı başlama vaxtından sonra olmalıdır.» |
| müddət ≤ 0 | «Müddət 0-dan böyük olmalıdır.» |
| müddət > (bitmə − başlama) | «Müddət imtahan pəncərəsindən (N dəq) uzun ola bilməz.» |
| sual sayı mənfi / kəsr | «Sual sayı mənfi ola bilməz (0 = bütün suallar).» |

`0` sual sayı **qəsdən keçir** — server semantikası «0 = bütün aktiv suallar».

### Server tərəfi (400 JSON: `{"success": false, "step": N, "field": "…", "html": …}`)

Sehrbaz `step`/`field` ilə xətanın olduğu addıma keçib sahəni fokuslayır (əvvəl həmişə
1-ci addıma qayıdırdı):

| Hal | `step` (kod) | `field` | Nəticə |
|---|---|---|---|
| bitmə < başlama (`end_after_start`) | 1 | `end_datetime` | addım 2 |
| başqa tenantın qrupu | 2 | `allowed_units` | «Seçilmiş qrup(lar) bu təşkilatda tapılmadı və ya əhatənizdən kənardır.» — imtahan yaranmır |
| dekanın əhatəsindən kənar qrup | 2 | `allowed_units` | eyni mesaj (mövcudluq sızmır) |
| arxiv qrup / GROUP olmayan vahid / yanlış UUID («not-a-uuid») | 2 | `allowed_units` | eyni mesaj; **bütün** qrup seçimi rədd edilir |
| `enable_paint` yazılı olmayan imtahanda | 2 | `enable_paint` | addım 3 |

Reyestr qrupu id-ləri **forma sahəsi deyil** — view qatında (`unit_assignment.py`)
namizəd dəstinə görə yoxlanır və `form.save_m2m()`-dən sonra yazılır. Boş seçim = qrupsuz
imtahan (fərdi tələbə / hamıya açıq / kurs ilə də təyin oluna bilər).

### Məlum məhdudiyyət (2026-09-14)

`ExamForm.clean()` **istisna tələbələr** (`excluded_users`) siyahısını yalnız kohort
üzvləri ilə süzür — reyestr qrupu ilə təyinatda istisna işarəsi **saxlanmaya bilər**.
W5 `w5left` işində; o vaxta qədər istisna lazım olan tələbəni fərdi olaraq yoxlayın.

Eyni səbəbdən reyestr qrupu hələ bu yerlərdə **görünmür** (kohort id-li süzgəclər):
imtahan mərkəzi statistikası (qrup/fakültə filtri), apellyasiya statistikası, «Yenidən
şans» bölməsinin qrup filtri, müəllim nəticələrində qrup filtri — W5 `w5left` işində.

---

## 7. Yanaşı dəyişikliklər (eyni commit)

- «Aktiv et» POST-dan sonra yönləndirmə `?from_section=my-exams&return_to=…`
  parametrlərini saxlayır — kabinetdəki «Geri» kabinetə qayıdır.
- «Dublikat et»: uğur toast-u + **xəbərdarlıq** toast-u — suallar kopyalanmır (mənbədə
  N sual qaldı / mənbə boş idi); «Yenidən şans ver» → «Tələbəyə əlavə cəhd verildi.»
- İmtahan detal səhifəsində «Qruplar (reyestr)» info-kartı; kabinet kartında «Qruplara
  açıq» sayğacı reyestr qruplarını da sayır.

---

## 8. Mənbələr

| Nə | Fayl |
|---|---|
| Üzvlük şərti (tək mənbə) | `apps/exams/domain/unit_assignment.py` |
| Giriş siyasəti | `apps/exams/domain/access_policy.py`, `apps/exams/services/access_policy.py` |
| Sehrbaz view qatı: namizədlər, validasiya, addım/sahə xəritəsi | `apps/exams/views/teacher/exams/unit_assignment.py`, `list_detail.py`, `lookups.py` |
| Şablon / JS | `apps/exams/templates/exams/teacher/partials/_create_exam_modal_form.html`, `apps/exams/static/exams/js/exam_wizard.js`, `exam_create_edit_modal/**` |
| Model / miqrasiya | `Exam.allowed_units` — `apps/exams/migrations/0068_exam_allowed_units.py`, RLS `0069_rls_exam_allowed_units.py` |
| PIN provizionu | `apps/exams/services/student_pins.py`, `apps/exams/signals.py` |
| Siyahılar / sayğaclar | `apps/exams/services/student_list_batch.py`, `apps/exams/views/student/lists.py`, `apps/accounts/queries/assignments.py`, `apps/notifications/services/events.py` |
| Testlər (23) | `apps/exams/tests/test_w4_wizard_units.py` — giriş siyasəti (qrup / xaric / qeyri-aktiv / yad tenant), siyahılar, batch sorğu sayı, alıcılar / PIN, dublikat, sehrbaz POST (uğur, yad tenant 400 `step=2`, zibil id, bitmə < başlama `step=1`), redaktə render + kohort bloku gizli, lookup əhatəsi, «Aktiv et» redirect, toast-lar, detal səhifəsi |
