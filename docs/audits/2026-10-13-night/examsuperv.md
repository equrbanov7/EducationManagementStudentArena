# 2026-10-13 (gecə) — İmtahan nəzarəti: zallar, nəzarətçi növbəsi, canlı monitor, köçürmə əleyhinə

Sahibin tapşırığı: «canlı monitorinqi check et. zallar, zallara nəzarət, nəzarətçinin təyin
olunması, təyin olunandan sonra onun da müəyyən accessləri olması kabinetində, amma imtahan
sessiyası ya da gün bitəndə onun itməsi. tələbənin köçürmə ehtimalını aşağı salacaq nəzarət
sisteminin güclənməsi. performans və təhlükəsizlik problemlərinə bax.»

## 1. Tapılan əsas problemlər (dəyişiklikdən əvvəl)

| # | Problem | Təsir |
|---|---------|-------|
| P1 | Nəzarətçi zala `ExamRoom.invigilators` M2M ilə **daimi** təyin olunurdu. Zal monitoru, snapshot, tələbə şəkilləri, WS — hamısı imtahandan aylar sonra da açıq qalırdı. | Ən az səlahiyyət pozulur; «gün bitəndə itsin» tələbi ödənmirdi. |
| P2 | Kabinet bəndi (`user_supervises_final_sessions`) istənilən ləğv olunmamış KEÇMİŞ oturumu sayırdı → bənd daimi qalırdı. | Eyni. |
| P3 | Zal WS kanalı icazəni yalnız `connect`-də yoxlayırdı. | Açıq tab növbədən sonra da canlı hadisə alırdı. |
| P4 | Zal snapshot-u hər ekrandan 10 s-dən bir tam hesablanırdı (~10 sorğu + tənbəl yazılar); keş, ETag, gizli-tab pauzası, xəta geri-çəkilməsi, rate-limit yox idi; planşet hər 10 s 300 hücrəni yenidən çəkirdi. | Zal başına N ekran = N× yük. |
| P5 | Sual SIRASI yalnız «blok» yolunda qarışdırılırdı; «hamısı» (`random_question_count=0`) və bloksuz yolda sıra `_question_rank`-dan (az istifadə olunan → çətinlik) gəlirdi — yan-yana tələbələr demək olar eyni sırada görürdü. | Köçürmə ehtimalı. |
| P6 | Eyni cəhdin iki cihaz/iki tabda eyni anda açıq olması (midterm — cihaz bağlaması yalnız finaldadır) və cəhd ortasında IP dəyişməsi aşkarlanmırdı. | Köçürmə / kənar kömək. |
| P7 | Zal xəritəsində qalan vaxt və irəliləyiş (cavablanmış/cəmi) görünmürdü; yeni «şübhəli» tələbə üçün xəbərdarlıq yox idi; nəzarətçinin hadisə qeydi yazmaq imkanı yox idi. | UX / nəzarət keyfiyyəti. |
| P8 | Biletsiz (PIN) cəhdin «cihaz dəyişikliyi» təsdiqini zalın nəzarətçisi verə bilmirdi (yalnız bilet axını). | Nəzarətçi əməliyyatı yarımçıq. |

## 2. Dəyişikliklər

### Vaxtla məhdud nəzarətçi növbəsi (P1, P2, P3, P8)
* Yeni model `InvigilatorDuty` (`apps/exams/domain/final_center/duties.py`, miqrasiya **0075_invigilator_duty**,
  additiv + RLS siyasəti): zal, istifadəçi, `starts_at`/`ends_at`, qeyd, kim təyin edib, `revoked_at`.
* İcazə sorğu anında hesablanır (`services/final_center/duties.py::supervision_scope`), cron yoxdur:
  açılır `starts_at − 30 dəq`; bağlanır `ends_at + 15 dəq` (zalda canlı oturum yoxdursa), ən gec
  başlanğıc gününün sonu (Asia/Baku); ləğv → dərhal.
* Köhnə daimi M2M və oturum-səviyyəli `invigilator`/`staff` geriyə-uyğun saxlanılıb, amma artıq
  yalnız oturum canlı olanda (və ya bu gün başlayacaq hazır oturumun 30 dəq. ön pəncərəsində) işləyir.
* Bütün nəzarət səthləri eyni əhatədən keçir: `can_supervise_session`, `can_enter_supervision_surface`,
  `sessions_visible_to`, kabinet bəndi, zal siyahısı, zal monitoru/snapshot/pozuntu API, tələbə şəkli
  (`identity.can_view_student_photo`), cihaz dəyişikliyi, WS (`FinalExamRoomConsumer` ping/hadisədə
  dəqiqədə bir təkrar yoxlama → `access_expired` + bağlanma 4403).
* Rəhbər paneli (zal monitoru): «Nəzarətçi növbələri» — siyahı (Aktiv / HH:MM-da açılır / Bitib /
  Ləğv edilib), gün+saat formu, ləğv düyməsi (EMSConfirm). Yalnız `can_assign_invigilators`
  (mərkəz rəhbəri/superadmin); tələbə rollu üzv rədd olunur; keçmiş gün / 60 gündən irəli rədd;
  idempotent; hər yazı/ləğv `AuditLog` (`final_room_invigilator_duty_created|revoked`).
* Nəzarətçi kabineti: zal siyahısında «Nəzarət növbələriniz» zolağı (zal, aralıq, «çıxış HH:MM-da
  avtomatik bağlanır», «Zala daxil ol»); zal monitorunda eyni zolaq; növbə bitəndə snapshot 403 →
  polling dayanır, «Nəzarət növbəniz bitdi» bildirişi.
* Nəzarətçi qeydi: pozuntu modalında forma → `ProctoringLog(kind=invigilator_note, severity=info)`,
  risk xalına/sayğaca düşmür, xronologiyada «Nəzarətçi qeydi» kimi görünür (rate-limit 30/10 dəq).

### Monitor performansı (P4, P7)
* `services/final_center/snapshot_cache.py`: zal üzrə paylaşılan 3 s keş (yük ekran sayından asılı
  deyil) + zəif ETag (`server_now`, `remaining_seconds`, heartbeat `age` çıxarılmaqla) → dəyişiklik
  yoxdursa **304** (gövdəsiz). Öz əməlindən sonra `?fresh=1`; start/end/open-all keşi silir.
  (istifadəçi, zal) başına 40/dəq limit (429 + Retry-After).
* `room_live.js` (yeni): gizli tabda polling YOX, görünəndə dərhal; in-flight guard; xətada
  10→20→40→60 s; 304-də render yox; 403-də dayanma. `room_aggregate.js` nəqliyyatı ona verdi.
* Sətirlərə `deadline_at` (mütləq, ETag-sabit) + `answered`/`question_total` (TƏK aqreqat sorğu,
  `monitor_enrich.attempts_progress`); hücrədə «⏱ 12 dəq · 8/20», 30 s-dən bir yerində yenilənir.
* Yeni şübhəli → `aria-live="assertive"` elan + səhifə başlığında «(N!)».

### Köçürmə əleyhinə (P5, P6)
* `randomizer.generate_random_questions_for_attempt`: bütün yollarda yekun `random.shuffle` —
  hansı suallar seçildiyi dəyişmir, yalnız hər tələbənin SIRASI təsadüfidir (variant sırası onsuz da
  cəhd başına qarışdırılırdı).
* Heartbeat-ə səhifə id-si (`cid`, `proctor_signals.js`): server A→B→A növbələşməsini görəndə
  `concurrent_session` (high) yazır; reload səhv-müsbət vermir (köhnə səhifə susur). Cəhd ortasında
  IP dəyişəndə `ip_changed` (medium). Hər ikisi serverin öz müşahidəsidir, klient söndürə bilməz;
  avtomatik cəza yoxdur — risk xalına düşür, nəzarətçiyə göstərilir.
* Artıq mövcud olanlar (yoxlanıb, toxunulmayıb): kopyala/yapışdır/sağ klik/klaviatura bloku, tam
  ekran tələbi + siqnal, tab/blur, DevTools/əlavə monitor/genişlənmə/AI evristikaları, çap cəhdi,
  final cəhdinin cihaz bağlaması, risk həddi (flag_threshold).

## 3. Testlər
* Yeni: `apps/exams/tests/test_invigilator_duty_2026_10_13.py` (21 test: pəncərə statusları, ləğv,
  köhnə M2M yalnız canlı oturumda, IDOR — başqa zalın növbəsi, 403/200 keçidləri, zal siyahısı
  zolağı, ETag/304, rəhbər/işçi/müəllim/tələbə təyin qaydaları + audit, qeyd endpoint-i və risk,
  heartbeat növbələşməsi/IP, heartbeat API siqnalı, sual sırası qarışdırması),
  `test_room_ws_duty_expiry_2026_10_13.py` (açıq WS növbə ləğvindən sonra bağlanır).
* Yeni semantikaya uyğunlaşdırılıb: `test_final_center_cabinet` (köhnə oturum təyinatı yalnız canlı),
  `test_supervision_surface_gate`, `test_room_violations_api`, `test_final_center_flow` (panel URL-i).

## 4. Səhər yoxlanacaqlar / risklər
* **Davranış dəyişikliyi:** mövcud daimi zal nəzarətçiləri artıq yalnız zalda canlı imtahan olanda
  daxil ola bilir. İmtahan günündən əvvəl rəhbər zal monitorunda «Nəzarətçi növbələri»ndən növbə
  yazmalıdır (imtahan mərkəzinin öz çıxışı dəyişməyib; tələbənin imtahan axınına təsir yoxdur).
* Növbə saatları Bakı vaxtı ilə bir gün daxilindədir (gecə yarısını keçən növbə iki sətir tələb edir).
* PIN təkrar verilməsi PIN agentinin sahəsidir — nəzarətçi zal monitorunda mövcud bilet əməliyyatlarını
  (bərpa/çıxar/yenidən giriş) aktiv növbə ilə istifadə edir; burada PIN məntiqinə toxunulmayıb.
* i18n: `scripts/i18n_fill_examsuperv_2026_10_13.py` (az/en/ru/tr, 62 giriş).
