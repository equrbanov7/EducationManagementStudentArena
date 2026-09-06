# Düzəliş planı — QA auditi 2026-09-05-dən sonra

Mənbə: `ISSUES.md` (44 açıq maddə) + `FINAL_REPORT.md` (5 buraxılış şərti).
Ardıcıllıq **təsirə** görədir: əvvəl semestrin başlamasına mane olanlar, sonra miqyas, sonra borc.

---

## Faza 0 — rol modeli (yeni tələb, 2026-09-06)
| # | İş | Fayl | Ölçü |
|---|---|---|---|
| 0.1 | **RİM əməkdaşı rolu** (`rim_staff`) — RİM rəhbəri (`ikt_rehber`, lvl 88) tək rol idi; şöbənin əməkdaşları üçün ayrıca, məhdud səlahiyyətli rol lazımdır | `default_roles_university.py`, `core/constants.py`, `core/roles.py`, miqrasiya + i18n | orta |
| 0.2 | Rol etiketləri AZ-a çevrilsin (`Teacher`, `Dean`, `Exam Center Staff` → AZ) — P3-2 | `default_roles_*`, kataloq | kiçik |

## Faza 1 — semestr başlamazdan əvvəl (biznes qapıları)
| # | İş | Problem | Ölçü |
|---|---|---|---|
| 1.1 | Yük sətri **0 saatla göndərilməsin** (readiness → `WorkloadDenied`) | P2-35 | kiçik |
| 1.2 | Eyni fənn+ixtisas+semestr+qrup ilə **dublikat sətir** bağlansın | P2-37 | kiçik |
| 1.3 | Dilim təsdiqi **koordinator vizası** tələb etsin (`workload.visa_required`, defolt bəli) | P2-36 | orta |
| 1.4 | Dərs tarixi **dövrün `end_date`-ini** keçməsin (RİM override qalsın) | P2-11 | kiçik |
| 1.5 | Kollokvium pəncərəsi: keçmiş tarix + K-sırası pozuntusu rədd edilsin | P3-21 | kiçik |
| 1.6 | Yük sətri validasiyası: xəta mesajı düzgün sahəni göstərsin; yay semestri «Payız» görünməsin | P3-20 | kiçik |

## Faza 2 — məlumat təmizliyi (semestr məlumatı yüklənməzdən əvvəl)
| # | İş | Problem | Ölçü |
|---|---|---|---|
| 2.1 | 72 «Level …» + 2 «Xaric olunanlar» psevdo-qrupu → statusa çevrilsin və ya «xidməti» işarələnsin | P2-8 | orta (data) |
| 2.2 | «Cari tədris ili» vahid mənbədən oxunsun (dashboard 2025/2026 Yaz vs yük 2026/2027) | UX-09 | orta |
| 2.3 | İxtisas ↔ kafedra bağı (kafedra müdiri tələbə siyahılarını boş görür) | P2-14 | orta (data) |

## Faza 3 — miqyas / performans
| # | İş | Problem | Ölçü |
|---|---|---|---|
| 3.1 | **Jurnal səhifələməsi** — 555×226 açılış 41.5 MB HTML verir; dərs pəncərəsi (məs. 4 həftə) + «hamısını göstər» | P1-8 | böyük |
| 3.2 | `academic-records` xülasəsi: SUM-lar SQL-ə (GROUP BY student), keş yalnız üst qat olsun | P2-19 / P2-4 | orta |
| 3.3 | `analytics` aqreqatları + keş | P2-2 | orta |
| 3.4 | `applications` N+1: `ApplicationUnit` 19× + `Membership` 16–26× → bir dəfə | P2-26 | kiçik |
| 3.5 | Jurnal siyahısı (korrektor) 3.4–4.2 s — COUNT FILTER + DISTINCT sorğuları | P2-18 | orta |
| 3.6 | Dərs modalında 554 müəllim + 159 otaq hər yükləmədə → axtarışlı/lazy select | P3-13 | kiçik |

## Faza 4 — a11y və UX borcu
| # | İş | Problem | Ölçü |
|---|---|---|---|
| 4.1 | **355 label-siz input** — əvvəl 5 ən çox işlənən forma (imtahan balı 32, rol təyinatı 17, tələbə-təşkilat 15, bildirişlər 11) | UX-18 | orta |
| 4.2 | `aria-sort` + klaviatura ilə sıralama bütün cədvəllərə (hazırda yalnız `ems_ui/_data_table`) | UX-17 | orta |
| 4.3 | Bootstrap `badge bg-warning/bg-info` ağ mətnlə 1.6–1.9:1 → tünd mətn / `ems-badge`-ə köçürmə | UX-05 | kiçik |
| 4.4 | Skeleton + `aria-busy` yükləmə vəziyyəti (kataloqlarda boş başlıq sətri görünür) | UX-11 | kiçik |
| 4.5 | Jurnal cədvəlində **yapışqan başlıq sətri** (555 sətirdə sütun kimliyi itir) | UX-06 | kiçik |
| 4.6 | AI köməkçi FAB cədvəlin «Əməllər» sütununu örtür → z-index/offset | UX-07 | kiçik |
| 4.7 | `alert()`/`confirm()` (138 çağırış) → ems toast/dialog; «Yadda saxla» ikiqat klik qoruması | UX-15 / P3-11 | orta |
| 4.8 | 234 inline `style=` → class (CSP `style-src-attr` borcunu bağlayır) | UX-19 | orta |

## Faza 5 — cilalama və qərar gözləyənlər
| # | İş | Problem |
|---|---|---|
| 5.1 | Menyu ↔ capability uyğunsuzluğu: heyət `my-results`/`my-journal`-ı URL ilə aça bilir | P3-5 |
| 5.2 | Parol sıfırlamasında **səbəb məcburi** olsun (blok/silmə kimi) | P2-15 |
| 5.3 | Məzun kabineti: nəticə/transkript bölmələri, `edit-profile` 403-ün həlli | P2-32 |
| 5.4 | Sillabus «kopyala» mövcud açılışın dosyesinə yazsın | P2-20 |
| 5.5 | RİM əməllərində səbəb kodları (hamısı `target_not_found`-a çevrilir) | P3-8 |
| 5.6 | Müraciətdə ikiqat göndəriş qoruması + fayl imzası yoxlaması | P3-18 / P3-17 |
| 5.7 | GET detalın statusu dəyişməsi (yan-təsirli GET) | P3-19 |
| 5.8 | Terminologiya və tarix formatının vahidləşməsi | UX-14 |
| 5.9 | Token miqrasiyası: 790 hex → `--ems-*` (faza-faza) | UX-03 |

## Prod şərtləri (koddan kənar)
- **HSTS** nginx-də təsdiqlənsin (dev-də yoxdur).
- Deploy öncəsi `pip-audit` qapısı (main-də canlı OSV bazası ilə yoxlanır).
