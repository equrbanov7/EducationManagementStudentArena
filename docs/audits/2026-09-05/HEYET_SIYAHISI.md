# Heyət siyahısı → rol xəritəsi (2026-09-06)

**Mənbə:** sahibin göndərdiyi `Siyahı.xlsx` — 52 struktur bölməsi, **119 nəfər**.
**Alət:** `manage.py seed_staff_roster --file <fayl> --org <slug> [--apply]` (dry-run defolt).
**Tətbiq:** QA klonunda icra edildi — **47 yeni hesab**, **72 mövcud hesab yeniləndi**.
Real bazaya (`emsarena_db`) TOXUNULMAYIB; prod icrası sizin qərarınızdır.

## 0. 2026-09-06 yeniləmə — 3 qərar tətbiq olundu

Bölmə 3-dəki üç sual sahib tərəfindən cavablandı və xəritəyə köçürüldü
(`apps/accounts/services/staff_roster.py`, testlər `test_staff_roster.py`).
Yeni rollar (`trustee`, `admin_unit_head`) `apps/organizations/default_roles_oversight.py`-da
təyin olunub, miqrasiya `0045_seed_oversight_roles` ilə əkilib.

| Qərar | Qayda | Nəticə |
|---|---|---|
| «Baş direktor» | `POSITION_ROLE_RULES`-a əlavə (+ siyahıdakı yazı səhvi «Baş dirketor») → `rector` | 1 nəfər (Nuriyeva Düriya Seyid) |
| «Qəyyumlar şurası» bölməsi | Bölmə-səviyyəli qayda (Prorektor ilə EYNİ naxış) → `trustee` | 1 nəfər (Bağırov Hüseynqulu Seyid, Sədr) |
| Qarşılıqsız bölmədə «Müdir» | `UNIT_HEAD_ROLE_RULES`-da uyğunluq yoxdursa artıq `member` yox, `admin_unit_head` | 9 nəfər |

QA klonunda (`emsarena_rehearsal_a0d170000901`, `myedu-univ`) yenidən tətbiq edildi
(`--apply`, idempotent — **0 yeni hesab, 119 mövcud hesab yeniləndi**, dublikat yaranmadı).

**Əvvəl → sonra (119 nəfərdən):**

| | Rola xəritələnən | `member` qalıq |
|---|---:|---:|
| Əvvəl (bu sənədin ilk versiyası) | 80 | 39 |
| Sonra (2026-09-06 yeniləmə) | **91** | **28** |

## 0b. TƏHLÜKƏSİZLİK TAPINTISI — ad-uyğunluğu səhv hesaba rol yapışdırırdı

Rolları tətbiq edəndən sonra klonu yoxlayanda ortaya çıxdı: alət mövcud hesabı
**yalnız ad + soyad** ilə tapırdı. Klonda **463 eyni ad-soyad qrupu (1 047 hesab)**
var. Nəticə: **21 heyət rolu səhv hesaba yapışmışdı** — o cümlədən

* `vice_rector` → `myedu.student.8088` (TƏLƏBƏ hesabı; əsl işçi hesabı
  `myedu.worker.522`, `nigar.babayeva@wcu.edu.az` boş qalmışdı),
* `dean`, `student_services`, `exam_center_staff`, `rim_staff`, `tutor`,
  `lab_assistant` → müxtəlif tələbə hesabları.

Prod-da eyni qaçış **tələbəyə prorektor/dekan səlahiyyəti** verərdi.

**Düzəliş (fail-closed, `seed_staff_roster`):**

1. Eyni ad-soyad birdən çox HESABA uyğun gəlirsə, əvvəlcə tələbə/məzun/valideyn
   hesabları kənarlaşdırılır; heyət hesabı BİRDİRSƏ seçim birmənalıdır.
2. Yenə də bir neçə heyət hesabı qalırsa → **atlanır** və hesabatda göstərilir.
3. ~~Ad siyahının özündə təkrarlanırsa (məs. «Vəliyeva Fəridə Rəsul» iki bölmədə)
   → atlanır.~~ 2026-09-06 (bax bölmə 0c): sahib qərarı ilə **hər sətrə ayrıca
   yeni hesab yaradılır** (atlanmır).
4. ~~Tapılan yeganə hesab TƏLƏBƏ hesabıdırsa → atlanır.~~ 2026-09-06 (bax bölmə 0c):
   sahib qərarı ilə **tələbə hesabına toxunulmadan YENİ heyət hesabı yaradılır**
   (laborant işləyən magistr ola bilər, ad toqquşması da ola bilər — insan sonra
   əl ilə birləşdirə bilər; sistem bunu bilə bilməz).
5. Django tələsi: `.values_list("user_id").distinct()` `Membership.Meta.ordering`
   sahəsini DISTINCT-ə əlavə edir və bir adamın bir neçə üzvlüyü «fərqli hesab»
   kimi görünürdü — `.order_by()` ilə sıfırlanır.

Testlər: `apps/accounts/tests/test_staff_roster_command.py` (4 test).

**Klon təmizləndi:** 21 + 9 səhv üzvlük silindi, `staff_position` sıfırlandı,
sonra siyahı yenidən tətbiq olundu.

| | Nəticə |
|---|---|
| Tətbiq olundu | **103 nəfər** |
| Əl ilə həll gözləyir | **16 nəfər** (7 eyniadlı heyət hesabı + 9 «yalnız tələbə hesabı») |
| Səhv hesaba düşən rol | **0** |

⚠️ **Prod icrasından əvvəl** həmin 16 nəfər üçün FİN və ya rəsmi e-poçt ilə
dəqiqləşdirmə lazımdır — alət onları qəsdən atlayır.

Yeni say `rector` +1 (cəm 1), `trustee` +1 (yeni, cəm 1), `admin_unit_head` +9 (yeni, cəm 9) —
əlavə 11 nəfər `member`-dən çıxdı (39 − 11 = 28).

⚠️ **Qeydə dəyər tapıntı (yeni qayda ilə əlaqəsi yoxdur, mövcud oxşar-ad məhdudiyyəti):**
siyahıda EYNİ tam adla (Vəliyeva Fəridə Rəsul) İKİ sətir var — «Arxiv şöbəsi / Müdir»
və «Filologiya və tərcümə məktəbi / Müavin». `seed_staff_roster` mövcud hesabı YALNIZ
ad/soyada görə tapır (bölməni nəzərə almır), ona görə hər iki sətir EYNİ hesaba
üzvlük yazır (bu, `admin_unit_head` əlavəsindən ƏVVƏL də «member + vice_dean» kimi
mövcud idi — yeni qayda onu sadəcə görünən etdi, yaratmadı). Tək belə hal tapıldı
(119 nəfərdən). Bu iki sətir eyni şəxsdirsə problem yoxdur; fərqli şəxslərdirsə
`staff_roster.py`-ın ad-uyğunlaşdırması bölməni də nəzərə almalıdır — ayrıca qərar
lazımdır, bu sənədin əhatəsindən kənardır.

Parollar (yalnız yeni hesablar, bir dəfə): `~/EMSArena-backups/qa-2026-09-05/staff_roster_credentials.csv`

**Giriş yoxlanıldı:** ilk 5 hesab birdəfəlik parolla klona daxil oldu (45–55 ms)
və hamısı düzgün şəkildə **ilk-giriş parol təyini** axınına düşdü — yəni parol
dəyişmədən sistemə keçə bilmirlər.

## 0c. 2026-09-06 (davam) — sahib qərarı: «yeni ola bilər, yoxdusa yarat»

Yuxarıdakı fail-closed siyahısının 3-cü və 4-cü bəndləri sahib tərəfindən
yenidən nəzərdən keçirildi: *«bəziləri yeni ola bilər, ona görə nəzərə al,
yoxdusa hesabını yarat»*. Nəticə — `seed_staff_roster` / `staff_roster.classify_match`:

| Hal | Əvvəl (0b) | İndi |
|---|---|---|
| (a) Ad siyahının özündə təkrarlanır (məs. Vəliyeva Fəridə Rəsul) | atlanır | hər sətrə AYRICA YENİ hesab (mövcud uyğunluq İSTİFADƏ OLUNMUR — hansının hansı olduğu bilinmir) |
| (b) Bazada BİRDƏN ÇOX HEYƏT hesabı adaşdır | atlanır | **DƏYİŞMƏDİ** — yeganə həqiqi fail-closed hal (səhv seçim mövcud işçinin hesabını korlaya bilər) |
| (c) Tapılan yeganə uyğunluq TƏLƏBƏ/məzun hesabıdır | atlanır | həmin hesaba TOXUNULMUR, YENİ HEYƏT hesabı yaradılır; hesabatda «adaş tapıldı» qeydi ilə işarələnir ki, insan sonra eyni şəxsdirsə əl ilə birləşdirsin |

Dry-run/apply hesabatı indi **üç ayrı say** göstərir: `Yaradılacaq` / `yenilənəcək` /
`çox mənalı (atlanır)`; `çox mənalı` bölməsi bazadakı namizəd `username`/e-poçtları
sadalayır ki, (b) halı saniyələr içində əl ilə həll edilə bilsin.

**QA klonunda (`emsarena_rehearsal_a0d170000901`) yenidən icra edildi:**

| | Əvvəl (0b) | Sonra (0c, bu dəyişiklikdən sonra) |
|---|---:|---:|
| Yaradılacaq (yeni hesab) | 0 (16 atlanırdı) | **13** (11 tələbə-adaş + 2 fayl-daxili adaş) |
| Yenilənəcək (mövcud) | 103 | **103** |
| Çox mənalı (atlanır) | 16 (7 heyət-adaş + 9 tələbə-adaş) | **3** (yalnız heyət-heyət adaşlığı) |

Qalan 3 nəfər (dəyişməyib, hələ də əl ilə həll gözləyir): Bağırov Rəşad Hüseynqulu
(Prorektor), Novruzov Nurlan Rasim (Rəqəmsal İnkişaf mərkəzi), Əliyeva Fidan Mahir
(Siyasi və ictimai elmlər məktəbi/Dekan) — hər üçü üçün hesabat İKİ namizəd
`myedu.worker.*` username/e-poçtunu göstərir.

### (a) halının idempotentliyi — düzəldildi

İlk yanaşmada fayl-daxili adaşlıq **hər** `--apply` icrasında yeni hesab
yaradırdı (mövcud uyğunluq qəsdən yoxlanmadığı üçün) — yəni faylı iki dəfə
tətbiq etmək «Vəliyeva Fəridə Rəsul» cütlüyü üçün dublikat açırdı. İndi sətrin
ÖZ hesabı tanınır:

1. bölmə sistemdə varsa — üzvlüyün `scope_unit`-i açardır;
2. bölmənin qarşılığı yoxdursa (siyahıdakı 23 bölmə belədir) — profil üzərindəki
   **vəzifə mətni** ayırd edir («Müdir» vs «Müavin»).

Namizəd birdən çoxdursa yenə də yeni hesab yaradılır (təxmin etmirik).
Klonda təsdiqləndi: əvvəlki qaçışların qoyduğu 2 dublikat silindikdən sonra
təkrar quru icra **«Yaradılacaq: 0 · yenilənəcək: 116 · çox mənalı: 3»** verir —
yəni komanda artıq təkrar-təhlükəsizdir. Test: `test_repeating_the_run_does_not_
duplicate_namesake_accounts`.

Testlər: `apps/accounts/tests/test_staff_roster_command.py` (5 test — yeni: tələbə-adaş
halında yeni hesab + toxunulmamış tələbə, fayl-daxili adaşlıq → 2 fərqli username,
heyət-heyət adaşlığı hələ də rədd edilir) və `apps/accounts/tests/test_staff_roster.py`
(`ClassifyMatchTest`, DB-siz qərar məntiqi).

Yeni hesabların birdəfəlik parolları: `/tmp/staff_roster_credentials_2026-09-06.csv`
(yalnız bu klon icrası üçün, məxfi saxlanılıb, sənədə köçürülməyib).

---

## 1. Xəritələnən vəzifələr

| Rol | Say | Kimlər (nümunə) |
|---|---:|---|
| `lab_assistant` | 21 | Poladova Ülkər Eldəniz (Nəşriyyat və çoxaltma mərkəzi), Qocayeva Cavahir Ehtibar (Laborotoriya), Əliyeva Əfsanə Cəbrayıl (Arxiv şöbəsi) … +18 |
| `chair_head` | 17 | Abbasov Rasim Cavan (Ümumi İqtisadiyyat kafedrası), Salayev Elxan Adil (Maliyyə Mühasibat uçotu və Audit kafedrası), Mustafayeva Gülnisa Əlisəfa (Turizm və otelçilik Kafedrası) … +14 |
| `tutor` | 12 | Məhərrəmli Tamam Əfqan (İqtisadiyyat Məktəbi), Kərimova Şəlalə İbrahim (Biznes və idarəetmə Məktəbi), Abışova Səbinə Sahil (Biznes və idarəetmə Məktəbi) … +9 |
| `dean` | 7 | Həsənova Afaq İsrafil (İqtisadiyyat Məktəbi), Mirzəyev Natiq Sərhad (Biznes və idarəetmə Məktəbi), Quliyeva Nailə Məmmədağa (Yüksək Texnologiyalar) … +4 |
| `vice_rector` | 5 | Bağırov Rəşad Hüseynqulu (Prorektor), Sadıxbəyova  Sevda Rafiq (Prorektor), Babayeva Nigar Mais (Prorektor) … +2 |
| `exam_center_staff` | 4 | Maqamedova Aida (Imtahan Mərkəzi), Əhmədova Nərgiz Nazim (Imtahan Mərkəzi), Hüseynli Sara Şamil (Imtahan Mərkəzi) … +1 |
| `teaching_office_staff` | 3 | Qəbərova Günel Tapdıq (Tədrisin Təşkili və idarə olunması), Nəsirova Süleymanova Aytən (Tədrisin Təşkili və idarə olunması), Daşdanova Solmaz Rizvan (Tədrisin Təşkili və idarə olunması) |
| `rim_staff` | 3 | Qurbanov Elvin Şahin (Rəqəmsal İnkişaf mərkəzi), Novruzov Nurlan Rasim (Rəqəmsal İnkişaf mərkəzi), Babyev Miryusif Alim (Rəqəmsal İnkişaf mərkəzi) |
| `student_services` | 3 | Sadıqov Samir Nizami (Tələbə dəstək Mərkəzi), Əliyeva Xəyalə Niyazi (Dövlət Nümunəli sənədlər və tələbələrlə iş şöbəsi), Mövsümova Aliyə Hüseyn (Dövlət Nümunəli sənədlər və tələbələrlə iş şöbəsi) |
| `vice_dean` | 2 | Qədiyeva Ülkər Rauf (Ekologiya Məktəbi), Vəliyeva Fəridə Rəsul (Filologiya və tərcümə məktəbi) |
| `hr` | 1 | Novruzova Zümrüd Qafar (İnsan Resusları şöbəsi) |
| `ikt_rehber` | 1 | İmaməliyev Kamran Səməd (Rəqəmsal İnkişaf mərkəzi) |
| `exam_center_head` | 1 | Quliyeva Ləman Ağasəlim (Imtahan Mərkəzi) |
| `rector` | 1 | Nuriyeva Düriya Seyid (Direktor, «Baş dirketor») — 2026-09-06 sahib qərarı |
| `trustee` | 1 | Bağırov Hüseynqulu Seyid (Qəyyumlar şurası, Sədr) — 2026-09-06 sahib qərarı |
| `admin_unit_head` | 9 | Şəfiyeva Şəlalə (Elm və İnnovasiyalar şöbəsi), Cəbrayılzadə Arzu (Beynəlxalq şöbə), Orucəliyev Orxan (İnformasiya Texnologiyaları mərkəzi) … +6 — 2026-09-06 sahib qərarı |

## 2. Sistemdə qarşılığı OLMAYAN vəzifələr (hələlik `member` + vəzifə mətni)

Sahibin göstərişi: «bəziləri yoxdursa elə rollar bizdə, onlar qalsın hələ».
Bu adamlar hesab alır, kabinetə girir, amma əlavə səlahiyyət ALMIR.

2026-09-06 yeniləməsindən sonra qalan **28** nəfər (əvvəlki 39-dan 11-i bölmə 0-dakı
üç qərarla çıxdı — bax silinən sətirlərin qeydi cədvəldən sonra).

| Bölmə | Vəzifə | Nəfər |
|---|---|---:|
| Beynəlxalq şöbə | Koorinator | 1 |
| Beynəlxalq şöbə | Mütəxəssis | 1 |
| Biznes və idarəetmə Məktəbi | Aparıcı mütəxəssis | 1 |
| Direktor | İnkişaf üzrə direktor | 1 |
| Elm və İnnovasiyalar şöbəsi | Koorinator | 1 |
| Elm və İnnovasiyalar şöbəsi | Mütəxəssis | 2 |
| Elmi Kitabxana | Kitabxanaçı | 4 |
| Elmi Kitabxana | Köməkçi | 1 |
| Elmi Kitabxana | Müdir müavini | 1 |
| Elmi nəşirlərlə iş şöbəsi | Sektor müdiri | 1 |
| Elmi tədbirlərin təşkili şöbəsi | Sektor müdiri | 1 |
| Laborotoriya | Koorinator | 1 |
| Maliyyə və Mühasibat şöbəsi | Baş Mühasib | 1 |
| Maliyyə və Mühasibat şöbəsi | Mühasib | 4 |
| Nəşriyyat və çoxaltma mərkəzi | Dizayner | 1 |
| Strateji İnkişaf | Mütəxəssis | 1 |
| Tələbə və məzunların təcrübə və inkişaf mərkəzi | Mütəxəssis | 1 |
| Yüksək Texnologiyalar | Koorinator | 2 |
| İnformasiya Texnologiyaları mərkəzi | Mütəxəssis | 1 |
| Əcnəbi tələbələrlə iş şöbəsi | Mütəxəssis | 1 |

**Bu 3 qərarla çıxan 11 sətir** (2026-09-06-dan əvvəl bu cədvəldə idi, indi
yuxarıdakı `rector`/`trustee`/`admin_unit_head` sətirlərinə köçüb): Arxiv şöbəsi/Müdir,
Beynəlxalq şöbə/Müdir, Direktor/Baş dirketor, Elm və İnnovasiyalar şöbəsi/Müdir,
Elmi nəşirlərlə iş şöbəsi/Müdir, Keyfiyyətin təminatı Mərkəzi/Müdir əvəzi,
Monitorinq şöbəsi/Müdir, Nəşriyyat və çoxaltma mərkəzi/Müdir, Qəyyumlar şurası/Sədir,
İnformasiya Texnologiyaları mərkəzi/Müdir, Əcnəbi tələbələrlə iş şöbəsi/Müdir.

## 3. Qərar gözləyən üç hal — HƏLL OLUNDU (2026-09-06, bax bölmə 0)

1. ~~**«Baş direktor» / «İnkişaf üzrə direktor»**~~ — sahib təsdiqi: «Baş direktor» → `rector`
   (eyni səviyyə). «İnkişaf üzrə direktor» AYRICA qərara düşməyib, `member` olaraq qalır.
2. ~~**«Qəyyumlar şurası / Sədr»**~~ — sahib qərarı: yeni `trustee` rolu (səviyyə 78,
   yalnız-oxu — analitika + audit, bax `default_roles_oversight.py`).
3. ~~**İnzibati şöbə müdirləri**~~ — sahib qərarı: yeni `admin_unit_head` rolu (səviyyə 65,
   UNIT əhatəli — öz vahidinin oxu səthi + şəxs kataloqu).

## 4. Yol boyu düzəlmiş qüsurlar

- **`vice_dean` rolu ümumiyyətlə yox idi:** səviyyə cədvəlində (85) vardı, rol kataloqunda yox —
  yəni dekan müavininə rol vermək MÜMKÜN DEYİLDİ. Rol əlavə olundu (səviyyə 75: kafedra
  müdirindən yuxarı, dekandan aşağı) — dekanın oxu/gündəlik səthi, qərar açarları olmadan.
- **Türk «İ» tələsi:** «Rəqəmsal İnkişaf mərkəzi» kiçildikdə `i`+birləşən nöqtə verir və adi
  mətn müqayisəsi tutmurdu — RİM rəhbəri səhvən `member` kimi xəritələnirdi.
- **Yazı səhvləri:** «Azərbbaycan», «Magsturatura», «Baş dirketor», «Koorinator» — vahid
  uyğunlaşdırması simvol-səviyyəli oxşarlıqla (0.72 həddi) bunları tutur.
