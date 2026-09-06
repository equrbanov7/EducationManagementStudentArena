# Heyət siyahısı → rol xəritəsi (2026-09-06)

**Mənbə:** sahibin göndərdiyi `Siyahı.xlsx` — 52 struktur bölməsi, **119 nəfər**.
**Alət:** `manage.py seed_staff_roster --file <fayl> --org <slug> [--apply]` (dry-run defolt).
**Tətbiq:** QA klonunda icra edildi — **47 yeni hesab**, **72 mövcud hesab yeniləndi**.
Real bazaya (`emsarena_db`) TOXUNULMAYIB; prod icrası sizin qərarınızdır.

Parollar (yalnız yeni hesablar, bir dəfə): `~/EMSArena-backups/qa-2026-09-05/staff_roster_credentials.csv`

**Giriş yoxlanıldı:** ilk 5 hesab birdəfəlik parolla klona daxil oldu (45–55 ms)
və hamısı düzgün şəkildə **ilk-giriş parol təyini** axınına düşdü — yəni parol
dəyişmədən sistemə keçə bilmirlər.

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

## 2. Sistemdə qarşılığı OLMAYAN vəzifələr (hələlik `member` + vəzifə mətni)

Sahibin göstərişi: «bəziləri yoxdursa elə rollar bizdə, onlar qalsın hələ».
Bu adamlar hesab alır, kabinetə girir, amma əlavə səlahiyyət ALMIR.

| Bölmə | Vəzifə | Nəfər |
|---|---|---:|
| Arxiv şöbəsi | Müdir | 1 |
| Beynəlxalq şöbə | Koorinator | 1 |
| Beynəlxalq şöbə | Müdir | 1 |
| Beynəlxalq şöbə | Mütəxəssis | 1 |
| Biznes və idarəetmə Məktəbi | Aparıcı mütəxəssis | 1 |
| Direktor | Baş dirketor | 1 |
| Direktor | İnkişaf üzrə direktor | 1 |
| Elm və İnnovasiyalar şöbəsi | Koorinator | 1 |
| Elm və İnnovasiyalar şöbəsi | Müdir | 1 |
| Elm və İnnovasiyalar şöbəsi | Mütəxəssis | 2 |
| Elmi Kitabxana | Kitabxanaçı | 4 |
| Elmi Kitabxana | Köməkçi | 1 |
| Elmi Kitabxana | Müdir müavini | 1 |
| Elmi nəşirlərlə iş şöbəsi | Müdir | 1 |
| Elmi nəşirlərlə iş şöbəsi | Sektor müdiri | 1 |
| Elmi tədbirlərin təşkili şöbəsi | Sektor müdiri | 1 |
| Keyfiyyətin təminatı Mərkəzi | Müdir əvəzi | 1 |
| Laborotoriya | Koorinator | 1 |
| Maliyyə və Mühasibat şöbəsi | Baş Mühasib | 1 |
| Maliyyə və Mühasibat şöbəsi | Mühasib | 4 |
| Monitorinq şöbəsi | Müdir | 1 |
| Nəşriyyat və çoxaltma mərkəzi | Dizayner | 1 |
| Nəşriyyat və çoxaltma mərkəzi | Müdir | 1 |
| Qəyyumlar şurası | Sədir | 1 |
| Strateji İnkişaf | Mütəxəssis | 1 |
| Tələbə və məzunların təcrübə və inkişaf mərkəzi | Mütəxəssis | 1 |
| Yüksək Texnologiyalar | Koorinator | 2 |
| İnformasiya Texnologiyaları mərkəzi | Müdir | 1 |
| İnformasiya Texnologiyaları mərkəzi | Mütəxəssis | 1 |
| Əcnəbi tələbələrlə iş şöbəsi | Müdir | 1 |
| Əcnəbi tələbələrlə iş şöbəsi | Mütəxəssis | 1 |

## 3. Qərar gözləyən üç hal

1. **«Baş direktor» / «İnkişaf üzrə direktor»** (Direktor bölməsi) — sistemdə `rector` var,
   amma «direktor»u avtomatik rektor saymaq idarəetmə qərarıdır: `rector` rolu `*` (bütün)
   səlahiyyətə malikdir. Təsdiq etsəniz bir sətirlik dəyişikliklə xəritəyə əlavə edirəm.
2. **«Qəyyumlar şurası / Sədr»** — sistemdə qəyyumlar şurası anlayışı yoxdur.
   Nəzarət səthi lazımdırsa ayrıca yalnız-oxu rol (analitika + audit) təklif edə bilərəm.
3. **İnzibati şöbə müdirləri** (Beynəlxalq şöbə, Arxiv, Kitabxana, Mühasibat, Monitorinq,
   Nəşriyyat, İT mərkəzi, Elm və İnnovasiyalar) — akademik iyerarxiyada qarşılığı yoxdur.
   İstəsəniz «şöbə müdiri» tipli ümumi rol (öz şöbəsinin heyətini görmək + hesabat) əlavə olunur.

## 4. Yol boyu düzəlmiş qüsurlar

- **`vice_dean` rolu ümumiyyətlə yox idi:** səviyyə cədvəlində (85) vardı, rol kataloqunda yox —
  yəni dekan müavininə rol vermək MÜMKÜN DEYİLDİ. Rol əlavə olundu (səviyyə 75: kafedra
  müdirindən yuxarı, dekandan aşağı) — dekanın oxu/gündəlik səthi, qərar açarları olmadan.
- **Türk «İ» tələsi:** «Rəqəmsal İnkişaf mərkəzi» kiçildikdə `i`+birləşən nöqtə verir və adi
  mətn müqayisəsi tutmurdu — RİM rəhbəri səhvən `member` kimi xəritələnirdi.
- **Yazı səhvləri:** «Azərbbaycan», «Magsturatura», «Baş dirketor», «Koorinator» — vahid
  uyğunlaşdırması simvol-səviyyəli oxşarlıqla (0.72 həddi) bunları tutur.
