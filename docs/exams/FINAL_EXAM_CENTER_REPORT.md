# Final İmtahan Mərkəzi — Yekun Hesabat

**Tarix:** 2026-07-06 · **Sahə:** Final imtahan girişi, İmtahan Mərkəzi, İmtahan Zalı və Real-Vaxt Nəzarət Sistemi

---

## 1. İlkin arxitektura qiymətləndirməsi

Mövcud sistemdə artıq güclü təməl var idi və yeni funksionallıq ondan **ayrılmadan** quruldu:

| Mövcud komponent | Vəziyyət | Qərar |
|---|---|---|
| `Exam` (`exam_type_extended="final"`) | Final kateqoriyası + mərkəz siyasəti (`access_policy.py`) mövcud | OLDUĞU KİMİ istifadə |
| `ExamAttempt` | Dublikat-start DB constraint-ləri, server-tərəfli timer, autosave | OLDUĞU KİMİ istifadə |
| Supervision (`ExamSupervisionConfig`, `SupervisionIncident`, `services/supervision/`) | Anti-cheat + lock/resume/stop axını | OLDUĞU KİMİ istifadə (çıxarma/dayandırma bunun üstündən keçir) |
| `ExamSupervisionConsumer` + Channels/Redis | Attempt-səviyyəli WS kanalı | Pattern təkrarlanaraq 2 yeni consumer əlavə edildi |
| `/exams/final/` səhifəsi + IP/CIDR gate (`exam_center_gate.py`) | Var | Genişləndirildi (bilet kartları) |
| `exam_center` rolu + `is_exam_center_user` | Var | Direktor səviyyəsi kimi istifadə |
| `core.audit.log_action`, notifications fasadı | Var | OLDUĞU KİMİ istifadə |
| RLS (organizations 0003/0007/0012 pattern-i) | Var | 3 yeni cədvələ eyni pattern tətbiq edildi |

Çatışmayan hissələr: zal/oturum/bilet modelləri, PIN sistemi, gözləmə otağı, sinxron start, otaq monitoru, hesabatlar — hamısı yeni qurulub.

## 2. Yenidən istifadə olunan mövcud funksionallıq

- **Attempt yaradılması:** `_create_attempt_or_get_active` + `generate_random_questions_for_attempt` (dublikat-start DB qorunması daxil).
- **Dil variantları:** `available_language_options`, `get_active_variant` — gate-dəki dil seçimi mövcud çoxdilli infrastruktura bağlanır.
- **Tələbə çıxarma/dayandırma:** `teacher_stop_attempt` / `teacher_lock_attempt` (SupervisionIncident + tələbə WS bildirişi pulsuz gəlir).
- **IP gate:** `final_exam_access_allowed` bütün yeni tələbə səhifələrində.
- **Audit:** `core.audit.log_action`; **Bildirişlər:** `apps.notifications.public.create_notification_for_users`.
- **Take-exam səhifəsi:** final attempt açılan kimi mövcud `take_exam` axını (supervision, autosave, timer, final chrome-suz rejim) işləyir.
- **Dizayn sistemi:** mövcud tokenlər (brand #2C5BFF, pill/badge/table pattern-ləri), `partials/_pagination.html`.

## 3. Refaktor edilən mövcud funksionallıq

- `apps/exams/views/student/lists.py::_render_exam_list` — `extra_context` parametri (geri-uyğun; final səhifəsi bilet kartlarını ötürür).
- `apps/exams/consumers.py` — tək fayl 3 consumer-lə yenidən təşkil olundu (mövcud `ExamSupervisionConsumer` DAVRANIŞI dəyişmədi).
- `student_exam_list.html` — şərti include (yalnız final səhifəsində görünür).

## 4. Yeni / dəyişdirilən modellər

**Yeni** — [apps/exams/domain/final_center.py](apps/exams/domain/final_center.py):

1. **`ExamRoom`** — org-scoped fiziki zal: ad, kod (org daxilində unikal), bina, mərtəbə, tutum, kompüter sayı, status.
2. **`ExamRoomSession`** — bir imtahanın bir zalda oturumu: state machine (`prepared → entry_open → active → ended`, + `cancelled`), nəzarətçi FK, heyət M2M, planlaşdırılan/rəsmi vaxtlar, `started_by/ended_by`, start anındakı qoşulu tələbə sayı (tarixi snapshot).
3. **`FinalExamTicket`** — tələbə təyinatı: PIN (hash + Fernet-şifrəli nüsxə), status machine (`assigned → waiting → ready → active → completed`, + `removed/absent`, re-admit), yer nömrəsi, seçilmiş dil, bütün həyat dövrü timestamp-ləri, çıxarılma qeydi (kim/nə vaxt/səbəb), reconnect sayı.

Dəyişdirilən modellər YOXDUR — `Exam`/`ExamAttempt` toxunulmaz qaldı (geri-uyğunluq: mövcud imtahan axınları dəyişmir).

## 5. Yeni route / view / servis / consumer / frontend

**Servis paketi** — [apps/exams/services/final_center/](apps/exams/services/final_center/) (fasad `__init__.py`, AGENTS §5):
`pins.py` (PIN kriptosu), `entry.py` (giriş validasiyası + rate limit), `sessions.py` (otaq həyat dövrü), `tickets.py` (bilet keçidləri, təyinat, çıxarma), `presence.py` (Redis presence), `events.py` (WS yayımı), `monitor.py` (snapshot), `reports.py` (filtrlər), `permissions.py` (obyekt-səviyyəli icazələr).

**Tələbə axını** — [apps/exams/views/student/final_center.py](apps/exams/views/student/final_center.py):
- `GET|POST /exams/final/` — AYRICA PIN giriş səhifəsi (imtahan siyahısı YOX; tələbə hansı imtahanın PIN-ini yazırsa o imtahana daxil olur). Uğurlu PIN yoxlaması → PRG → HƏMİN səhifədə imtahan-öncəsi məlumat/qaydalar **modalı** (dil seçimi + qaydalar təsdiqi). Modaldakı `action=confirm` → gözləmə otağı; `action=back` → çıxış.
- `GET /exams/final/waiting/<ticket>/` — gözləmə otağı
- `POST .../cancel/` — imtina (cəhd yanmır), `POST .../begin/` — attempt açılışı, `GET .../state/` — fallback poll

**İmtahan mərkəzi** — [apps/exams/views/exam_center/](apps/exams/views/exam_center/) (F-plan rol qovluğu):
- `/exams/center/rooms/` (+create/edit), `/exams/center/sessions/` (+create/detail/assign)
- `/exams/center/sessions/<id>/monitor/` + `api/snapshot/` + `open-entry|start|end|cancel`
- `/exams/center/sessions/<id>/tickets/<tid>/remove|pin|seat|readmit`
- `/exams/center/reports/` (+CSV export)

**WS consumer-lər** — [apps/exams/consumers.py](apps/exams/consumers.py), [routing.py](apps/exams/routing.py):
- `ws/exams/final/room/<session>/` (`FinalExamRoomConsumer`) — heyət monitoru (oxu kanalı)
- `ws/exams/final/wait/<ticket>/` (`FinalExamWaitConsumer`) — tələbə presence + start eventi

**Frontend:** yeni template-lər — `student/final_entry.html` (PIN login + imtahan-öncəsi modal), `student/final_waiting.html`, `exam_center/{room_list,room_form,session_list,session_form,session_detail,session_monitor,reports}.html`; CSS `exams/css/final_center/{student,center,monitor}.css`; JS `exams/js/final_center/{waiting_room,room_monitor,confirm_forms}.js`. Hamısı ≤600 sətir (AGENTS §1).

> **Yenilənmə (2026-07-06):** ilkin dizaynda `/exams/final/` final imtahan siyahısı + bilet/PIN kartları idi, gate isə ayrıca səhifə (`final_gate.html`) idi. İstifadəçi tələbi ilə `/exams/final/` **ayrıca PIN giriş səhifəsinə** çevrildi (siyahı və kartlar silindi), gate isə həmin səhifədə açılan **modala** köçürüldü. Silinən fayllar: `final_gate.html`, `partials/_final_tickets.html`, `css/final_center/tickets.css`; silinən view/URL: `final_exam_list`, `final_exam_gate` (+ `final/entry/`, `final/gate/` yolları). PIN artıq tələbə panelində göstərilmir — imtahan mərkəzi tərəfindən paylanır (bildiriş + panel).

## 6. Migrasiyalar

- `exams/0030_examroom_examroomsession_finalexamticket_and_more.py` — 3 yeni cədvəl (əlavə-yalnız, mövcud dataya toxunmur, geri qaytarıla bilir).
- `organizations/0015_rls_final_center.py` — 3 cədvələ RLS siyasəti (0012 pattern-i: `DROP POLICY IF EXISTS + CREATE`, qeyri-Postgres-də no-op, reverse mövcuddur).
- Tam `migrate` sıfırdan sqlite-da yoxlanılıb; `makemigrations --check` təmizdir.

## 7. İndekslər və constraint-lər

- `uniq_exam_room_code_per_org`; `examroom_org_active_name_idx`.
- `uniq_active_session_per_room` (partial: `state='active'`) — bir zalda eyni anda bir aktiv oturum; `room_session_end_after_start` (CHECK); org/state/exam/room/invigilator üzrə 4 kompozit indeks.
- Bilet: `uniq_ticket_per_session_student`, `uniq_ticket_per_exam_student` (bir tələbə — bir imtahan — bir bilet), `uniq_seat_per_session` (partial); `session+status`, `student+status`, `org+created` indeksləri.
- Vaxt toqquşmaları (zal cədvəli, tələbənin paralel oturumu) servis qatında sorğu ilə yoxlanır (`validate_session_plan`, `assign_students`).

## 8. WebSocket event strukturu

Kompakt sxem — tam payload YAYILMIR:

| Qrup | Event nümunələri |
|---|---|
| `final_room_{sid}` (heyət) | `student_connected/disconnected/reconnected`, `student_waiting/ready/started/completed/removed/suspended`, `entry_opened`, `room_started`, `room_ended` — hamısı `{event, ticket_id?}` formasında |
| `final_room_students_{sid}` | `room_started {started_at, server_now}`, `room_ended`, `session_cancelled` |
| `final_ticket_{tid}` | `removed {action}` |

Monitor JS eventi "dəyişiklik siqnalı" kimi qəbul edir və **debounce olunmuş** snapshot fetch-i edir; tələbə JS `room_started` alanda 0–2.5s təsadüfi gecikmə ilə `begin` POST-u göndərir (yük yayılması). Sual seti WS ilə heç vaxt göndərilmir.

## 9. State machine-lər

**Oturum:** `prepared → entry_open → active → ended`; `prepared|entry_open → cancelled`. Keçidlər `ROOM_SESSION_TRANSITIONS`-da; hamısı şərti UPDATE (idempotent).
**Bilet:** `assigned → waiting ⇄ ready → active → completed`; `waiting → assigned` (tələbə imtinası); `* → removed` (səbəblə); `removed → assigned` (re-admit + yeni PIN); oturum bitəndə başlamayanlar → `absent`. Yanlış keçid backend-də rədd olunur (`transition_ticket` → False / xəta).

## 10. Rol və icazə matrisi

| Əməliyyat | Tələbə | Nəzarətçi/Heyət (təyinatlı) | İmtahan mərkəzi | Superadmin |
|---|---|---|---|---|
| PIN girişi / gözləmə otağı (öz bileti) | ✅ | — | — | — |
| Zal/oturum yaratmaq, tələbə təyin etmək | ❌ | ❌ (403 test edilib) | ✅ | ✅ |
| PIN yaratmaq/yeniləmək/görmək | ❌ | ❌ | ✅ (baxış audit olunur) | ✅ |
| Monitor + snapshot | ❌ (WS 4403 test edilib) | ✅ yalnız öz oturumu | ✅ hamısı (öz org-u) | ✅ |
| Giriş açmaq / start / son / tələbə çıxarmaq | ❌ | ✅ öz oturumu | ✅ | ✅ |
| Vaxt pəncərəsindən kənar start (override) | ❌ | ❌ | ✅ (audit-ə yazılır) | ✅ |
| Re-admit / oturum ləğvi / hesabat + CSV | ❌ | ❌ | ✅ | ✅ |

Tenant sərhədi hər səviyyədə: view-lər org-scoped queryset-lə (`404`), WS `user_is_org_member` ilə (qlobal `exam_center` bayrağı başqa org-a KEÇMİR — test var), DB-də RLS.

## 11. Təhlükəsizlik təkmilləşdirmələri

- **PIN:** `secrets` ilə generasiya (default 8 rəqəm), saxlanma salted hash (`make_password`), göstərmə üçün Fernet-şifrəli nüsxə (oturum bitəndə/ləğvdə silinir); vaxt limiti; 5 uğursuz cəhddən sonra 10 dəq kilid; regenerasiya köhnəni ləğv edir; PIN heç vaxt URL/log/audit metadata-ya düşmür; staff baxışı audit olunur.
- **Giriş:** IP + istifadəçi adı üzrə dəqiqəlik rate limit; generik xəta (istifadəçi adı/PIN fərqləndirilmir); mövcud olmayan istifadəçidə də hash yoxlaması (timing bərabərləşdirmə — user enumeration testi var); sessiya rotasiyası (`login()`); CSRF bütün POST-larda.
- **WS:** hər iki consumer-də autentifikasiya + obyekt icazəsi + tenant üzvlüyü; tələbə monitor kanalına qoşula bilmir; inbound mesajlar throttle olunur (3s); idarəedici əməliyyatlar WS-də YOX, CSRF-li HTTP-dədir.
- **IDOR:** bilet sahibliyi + `final_exam_ticket_id` sessiya təsdiqi; cross-tenant oturum 404 (test var).
- **Server-authoritative vaxt:** start/son yalnız server timestamp-i; brauzer saatına etibar yoxdur; otaq deadline-ı `maybe_auto_end` ilə lazy tətbiq olunur.

## 12–13. Performans və sorğu optimallaşdırmaları

- Heartbeat-lər DB-yə yazılmır — Redis cache TTL açarları (`finpr:{sid}:{tid}`, TTL 90s); `last_seen_at` DB-yə maksimum 120 saniyədə bir yazılır.
- Monitor snapshot: 1 ticket sorğusu (`select_related student, attempt`) + `cache.get_many` presence — N+1 yoxdur; siyahı sayğacları tək sorğuda annotate olunur.
- Sinxron start: yüngül broadcast + müştəri tərəfdə jitter-li `begin` → sual yüklənməsi mövcud attempt xidmətindəki actor-lock/capacity-gate-lərdən keçir.
- WS reconnect: eksponensial backoff + jitter (max 30s); fallback polling yalnız WS qopanda (30s intervalla).
- Otaq sonu: attempt-lər `select_for_update` ilə yekunlaşır (tələbənin paralel submit-i ilə yarış attempt sətir lock-u ilə həll olunur — take_exam POST-u da eyni lock-u istifadə edir).
- Hesabatlar: server-side filtr + `Paginator` + CSV `iterator(chunk_size=500)` (yaddaşa tam yüklənmə yoxdur).

## 14. UX/UI

- Tələbə: chrome-suz imtahan zalı rejimi (mövcud final konvensiyası ilə eyni blok-suppress pattern-i), status mesajları `aria-live`, klaviatura fokus halqaları, `prefers-reduced-motion` dəstəyi.
- Nəzarətçi: stat kartları, axtarış/status filtri, canlı bağlantı göstəricisi, start/son/çıxarma üçün fakt-cədvəlli təsdiq modalları (Esc bağlayır), status pill-ləri rəng + mətn ilə (yalnız rəngə güvənilmir).
- Mövcud dizayn tokenləri və qb-səhifə pattern-ləri təkrar istifadə olunub; bütün yeni CSS/JS ayrıca fayllardadır (CSP-safe, inline skript yoxdur).

## 15–16. Test əhatəsi və yük testi

**60 yeni test — hamısı keçir; tam exams paketi: 512 passed, 2 skipped (reqressiya yoxdur):**
- [test_final_center_pins.py](apps/exams/tests/test_final_center_pins.py) (16): PIN generasiya/hash/doğrulama/kilid/vaxt/regenerasiya/ləğv; görünürlük pəncərəsi; state machine (yanlış keçid, terminal status, stale-status yarışı, unikal bilet).
- [test_final_center_flow.py](apps/exams/tests/test_final_center_flow.py) (37): giriş (yanlış PIN, user enumeration, başqasının PIN-i, bağlı oturum), gate/gözləmə/imtina, idempotent start/son, override, sinxron start + begin (HTTP daxil), otaq sonu (attempt submit + absent + PIN wipe), çıxarma/dayandırma, tutum/toqquşma, icazə + cross-tenant (403/404), bütün mərkəz səhifələrinin render smoke-ları, tələbə bilet kartı + PIN görünürlüyü.
- [test_final_center_consumers.py](apps/exams/tests/test_final_center_consumers.py) (7): WS autorizasiyası (tələbə/anonim/başqa org rədd; sahib/heyət qəbul; removed bilet rədd).

**k6:** [k6/final-exam-center-test.js](k6/final-exam-center-test.js) — PIN giriş → gate → gözləmə → state poll → begin ssenarisi (threshold-larla). Yük NƏTİCƏLƏRİ hələ ÖLÇÜLMƏYİB — real mühitdə işlədilməlidir; performans iddiası irəli sürülmür.

**Brauzer yoxlaması:** dev serverdə `/exams/final/entry/` renderi və yanlış giriş axını (generik xəta) vizual təsdiqlənib.

## 17. Məlum məhdudiyyətlər

1. Naviqasiya inteqrasiyası minimal — mərkəz səhifələri `/exams/center/sessions/` URL-i ilə açılır; profil SPA-ya menyu bəndi əlavə edilməyib (aşağıda tövsiyə).
2. `ExamRoomComputer` (kompüter-səviyyəli inventar) ayrıca model kimi qurulmayıb — `computer_count` + yer nömrəsi ilə əhatə olunur.
3. PIN çatdırılması hazırda panel + bildiriş (PIN-siz) ilədir; e-poçt/SMS çatdırılması qoşulmayıb.
4. Postgres-RLS testləri sqlite dövrəsində görünmür (yaddaş qeydinə əsasən) — RLS migrasiyası real Postgres konteynerində yoxlanmalıdır.
5. Heyət üçün ayrıca qlobal rol yaradılmayıb — heyət oturum-təyinatlıdır (mərkəzləşdirilmiş RBAC qaydasına uyğun şüurlu qərar).
6. `apps/exams/static/exams/js/testQuestionBank.js` (613 sətir) — bu işdən ƏVVƏL mövcud olan modul-ölçü pozuntusu; ayrıca task çipi yaradılıb.

## 18. Deploy addımları

1. `python manage.py migrate` (exams 0030 + organizations 0015; RLS yalnız Postgres-də tətbiq olunur).
2. `python manage.py collectstatic` (yeni CSS/JS).
3. Daphne restart: `./scripts/restart-daphne.sh` (orphan-proses tələsinə görə).
4. İstəyə görə env: `FINAL_EXAM_PIN_LENGTH`, `FINAL_EXAM_PIN_MAX_FAILURES`, `FINAL_EXAM_PIN_LOCK_MINUTES`, `FINAL_EXAM_ENTRY_RATE_PER_MINUTE`, `FINAL_EXAM_PIN_VISIBILITY_MINUTES`, `FINAL_EXAM_PIN_EXPIRY_GRACE_MINUTES`, `FINAL_EXAM_ALLOWED_IPS` (zal IP-ləri).
5. Çoxlu instans üçün əlavə heç nə lazım deyil — presence/rate-limit Redis cache-də, WS fan-out channels_redis-dədir.

## 19. Rollback addımları

1. `python manage.py migrate organizations 0014` (RLS siyasətləri DROP olunur — reverse mövcuddur).
2. `python manage.py migrate exams 0029` (3 cədvəl silinir; mövcud imtahan datasına toxunulmur).
3. Kod revert — mövcud modellər/axınlar dəyişmədiyi üçün geri-uyğunluq riski minimum: `Exam`/`ExamAttempt`-də sahə dəyişikliyi YOXDUR.

## 20. Tövsiyə olunan gələcək təkmilləşdirmələr

1. Profil SPA-ya "İmtahan mərkəzi" bölməsi (oturumlar + monitor linkləri).
2. PIN paylanması üçün çap görünüşü (zal siyahısı PDF) və Celery ilə e-poçt çatdırılması.
3. `ExamRoomComputer` inventarı + yerlərin avtomatik təyinatı.
4. Oturum deadline-ı üçün Celery beat sweep (hazırda lazy `maybe_auto_end` kifayətdir, amma heç kim səhifə açmasa gecikə bilər).
5. k6 ssenarisinin real imtahan dövründən əvvəl staging-də icrası + WS bağlantı-həcmi testi.
6. Monitorda supervision pozuntu lentinin (SupervisionIncident feed) inline göstərilməsi.
