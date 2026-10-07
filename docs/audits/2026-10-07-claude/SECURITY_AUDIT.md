# Təhlükəsizlik auditi — 2026-10-07 (Claude, 5 paralel istiqamət + bug ovu)

Hər tapıntı üçün əvvəl uğursuz olan test yazılıb, sonra düzəldilib. Hamısı canlıya çıxıb
(main a00649d7, 2026-10-07 səhər). Əvvəlki auditlərdə (2026-09-13, 2026-09-28, 2026-10-05) bağlanmış
maddələr təkrar sayılmır.

## Düzəldilənlər

| Sev | Sahə | Problem | Test |
|---|---|---|---|
| **P1** | Apellyasiya | Apellyasiya səhifəsi URL-də `from_section`/`return_to` olmayanda tam cavab açarını göstərirdi (midterm həmişə, final 3 günlük apellyasiya pəncərəsi boyunca); nəticəsi gizli imtahanda sual üzrə doğru/yanlış görünürdü | `apps/appeals/tests/test_secaudit_2026_10_07_answer_key.py` |
| **P1*** | Rollar | `grant_role` istənilən platforma istifadəçisini aktiv təşkilata üzv edə bilirdi (sonra RİM parol/email dəyişə bilərdi) | `apps/accounts/tests/test_secaudit_2026_10_07_tenancy.py` |
| **P1/P2*** | RİM | «başqa təşkilatdakı rütbə» yoxlaması RLS-ə görə prod-da həmişə 0 görürdü; blok/sil/email dəyişmə onu çağırmırdı | eyni fayl |
| P2 | Şəbəkə zonası | LAN-da başlanmış superadmin view-as sessiyası kənardan tam yazma ilə işləyirdi (zona `request.user`-ə baxırdı) | `test_secaudit_2026_10_07_zone.py` |
| P2 | Login | Unicode-ekvivalent istifadəçi adları (NFKC) ayrı limit vedrəsi alırdı → hesab üzrə brute-force limiti yan keçilirdi | `test_secaudit_2026_10_07_login_bucket.py` |
| P2 | Sual idxalı | PDF/şəkil «bomb»u: nəhəng MediaBox köhnə OCR yolunda ≥300 DPI-də ~10 GB pixmap; Pillow 178 MP | `test_secaudit_2026_10_07_upload_bombs.py` |
| P2 | Bildirişlər | `unit_<id>`/`role_<key>_<org>` hədəfləri başqa təşkilata göndərə bilirdi | `NotificationStructureTargetsStayInActiveOrgTest` |
| P2 | Müraciətlər | Daxili qeydin faylları müraciət edənə görünür/endirilirdi (`/media/` daxil) | `apps/applications/tests/test_secaudit_2026_10_07.py` |
| P2 | Nəticələr | Yazılı midterm/finalın «ideal cavabı» yoxlanmadan görünürdü | `test_secaudit_2026_10_07_exam_integrity.py` |
| P2 | Statistika | Tələbə statistikası + CSV gizli nəticəli imtahanların ballarını göstərirdi | `test_secaudit_2026_10_07_statistics_visibility.py` |
| P2 | AI köməkçi | İmtahan zamanı başqa tabdan işləyirdi (sual yapışdırmaq) | `apps/ai_assistant/test_secaudit_2026_10_07_exam_lock.py` |
| P2 | Workflow | `seed-database.yml` inputları birbaşa `run:`-a düşürdü (prod runner-də shell injection) | `tests/test_infra_secaudit_2026_10_07.py` |
| P2 | Infra | IPv6 `80:80` bağlantısı 172.18.0.1-dən gəlib «daxili» sayılırdı (zona + /metrics/ /health/ bypass); X-Forwarded-Host müştəridən ötürülürdü | eyni |
| P3 | Final mərkəzi | Arxivlənmiş hesab bir sorğu ərzində PIN ilə autentifikasiya olunurdu | `test_secaudit_2026_10_07_final_entry.py` |
| P3 | İmtahan | `question-seen` vaxt bitəndən sonra / nəzarət kilidində məzmun verirdi; tələbə öz nəzarət tarixçəsinə sistem hadisəsi yaza bilirdi | `test_secaudit_2026_10_07_exam_integrity.py` |
| P3 | İdxal | xlsx dekompressiya bombası (intake, dərs yükü) | `core/tests/test_secaudit_2026_10_07_ooxml_expansion.py` |
| P3 | Yönləndirmə | Bildiriş `next`, export xətası (Referer), admin 2FA `next` — açıq yönləndirmə | `test_secaudit_2026_10_07_open_redirect.py` |
| P3 | Jurnal bağlama | Başqa fakültənin bildirişini öz bölməsinə köçürmək | `test_secaudit_2026_10_07_journal_close.py` |
| P3 | Fənn qovluğu | İKT rəhbəri başqa təşkilatın fayllarına çıxış (yalnız RLS saxlayırdı) | `apps/subject_folder/tests/test_secaudit_2026_10_07.py` |
| P3 | Endirmələr | Content-Type brauzerin iddiasından; kurs modallarında self-XSS; iCal CR injection; hesabat fayl adı | `core/tests/test_download_types.py` və s. |
| P3 | Kod icrası | Docker konteyneri root, capability-lərlə; timeout-da konteyner silinmirdi | `test_coding_sandbox_docker_2026_10_07.py` |
| Gigiyena | Infra | Workflow `permissions`, Action-lar SHA-ya pin, `no-new-privileges`, Prometheus lifecycle bağlandı, `.env`/`.env.bak.*` 600 | infra testləri |

\* P1 yalnız çox-təşkilatlı rejimdə; QKU tək təşkilatdır.

Əlavə: `bypass_rls` inventarı yeniləndi (198 çağırış / 97 fayl, hamısı təsnif olunub) — yeni təsnifatsız
fayl CI-da (`core/tests/test_secaudit_2026_10_07_rls_bypass_inventory.py`) yıxılır. CVE: `pip-audit` /
`npm audit` — 0.

## Sahib qərarı / server əməliyyatı tələb edənlər
- Hostda 11 gözləyən apt təhlükəsizlik yeniləməsi — gecə tətbiq olunmalı (`prod-host-maint.yml`).
- `EMS_DB_ROLE_ENFORCE=error` (app DB rolunun RLS-ə tabe olduğunu prod-audit təsdiqləyəndən sonra).
- postgres/pgbouncer exporter-lərinə ayrıca `pg_monitor` rolu; promtail `docker.sock` üçün socket-proxy; Redis ACL.
- GitHub `production` environment-ə tələb olunan reviewer + yalnız main.
- Off-site backup (köhnə AD-01).
- Dizayn riskləri (dəyişdirilmədi): hall kompüteri qeydiyyatsız təşkilatda final cəhdi istənilən cihazdan davam edə bilər; yazılı sualın vaxtlı məzmunu səhifə mənbəyindədir; WebSocket consumer-ləri admin-2FA/zona middleware-dən keçmir (hazırda yalnız oxu).
