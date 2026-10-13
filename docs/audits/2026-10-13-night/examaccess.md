# Gecə auditi 2026-10-13 — `examaccess`: final/midterm giriş zənciri

Sahibin sözü: «imtahanı check elə. midterm və final … qrupa ya da fərdi imtahan təyin etmə, pin kodun
görünməsi, onu götürüb imtahanı başlatma … ancaq universitet şəbəkəsinə qoşulu olarkən … MAC ünvan …
yeni pin … olduğu yerdən davam … köhnə pin etibarsızlığı … bir gündə ancaq 1 fəndən … performans və
təhlükəsizlik».

## Axının xəritəsi (yoxlanılıb)

| Növ | Giriş yolu | PIN |
|---|---|---|
| **Final** | `/exams/final/` (zal kompüteri, MAC/IP) → qaydalar modalı → gözləmə otağı → nəzarətçinin «Başlat»-ı → `begin` → take | Kabinetdəki fərdi `ExamStudentPin` **və ya** imtahan mərkəzinin bilet PIN-i (birdəfəlik) |
| **Midterm** | Kabinet → «Təyin olunmuş imtahanlar» modalı → PIN → `exam_code_check` → take | Kabinetdəki fərdi `ExamStudentPin` |

`start_exam` final/midterm üçün kodsuz HEÇ VAXT başlamır (`can_user_start(code=None)` → «kod tələb olunur»),
`exam_code_check` finalı rədd edir (yalnız mərkəz axını). R1 (GET ilə start) artıq bağlı idi (EXAMQA R1,
2026-10-01: yeni cəhd yalnız POST+CSRF və ya imzalı niyyət tokeni; tokensiz GET → təsdiq səhifəsi) —
yenidən yoxlanıldı, dəyişiklik lazım olmadı.

PIN görünməsi (sahibin 2026-07 qərarı, dəyişdirilmədi): fərdi PIN tələbənin kabinetində DƏRHAL görünür;
imtahan mərkəzi PIN axtarışında (audit olunur) görür; bilet PIN-i yalnız mərkəzə/nəzarətçiyə. Təhlükəsizlik
PIN-in gizliliyinə yox, PIN + zal kompüteri (MAC/IP) + **universitet şəbəkəsi** + cihaz bağlantısının
birləşməsinə əsaslanır.

## Tələblər üzrə nəticə

1. **Təyinat (qrup/alt qrup/fərdi)** — DÜZƏLDİLDİ. Ana qrupa təyin olunmuş final/midterm alt qrup
   tələbəsinə görünür/başlana bilir, amma PIN provizionu (`get_exam_assigned_user_ids`) alt qrupları
   genişləndirmirdi → alt qrup tələbəsinin PIN-i YOX idi, imtahana girə bilmirdi. İndi
   `student_pins._assigned_student_ids` giriş siyasəti ilə eyni mənbəni (`unit_assigned_student_ids`)
   birləşdirir. Əlavə: təyinatdan SONRA qrupa köçən tələbə üçün siqnal işləmir — kabinet PIN sətri
   yoxdursa onu yaradır (`student_visible_pin(..., provision_missing=True)`).
2. **PIN ilə start** — YOXLANILDI (server tərəfi): PIN-siz start mümkün deyil; R1 bağlı.
3. **Yalnız universitet şəbəkəsi** — YENİ. `EXAM_FINAL_INTERNAL_ONLY` (prod defolt `True`, compose
   pass-through, `NETWORK_ZONE_ENFORCED`-dən asılı deyil). Zona `core/network_zone.py` (nginx
   `X-EMS-Zone` yalnız `NETWORK_ZONE_TRUST_HEADER` ilə, əks halda `INTERNAL_NETWORKS`). Tətbiq: `/exams/final/`
   (giriş, gözləmə, imtina, begin, state), `start_exam`, `exam_code_check` (PIN yoxlamasından ƏVVƏL),
   take səhifəsi, autosave/finish (kilid altında), `question-seen`, kodlaşdırma, heartbeat/siqnal/hadisə/status.
   Rədd: aydın 403 səhifəsi (`exam_network_blocked.html`) və ya JSON `network_blocked`; audit (dəqiqədə bir).
   Müəllifin sınaq cəhdi azaddır; bitmiş cəhdin nəticəsinə baxış açıqdır.
4. **MAC** — YOXLANILDI. Normallaşdırılmış müqayisə, ARP agenti əlçatmaz/qeyd yoxdursa fail-closed,
   timeout 0,5 s. Məhdudiyyət: MAC yalnız eyni L2 seqmentdə görünür və saxtalaşdırıla bilər — qarşısı
   switch port-security / 802.1X ilədir (şəbəkə tərəfi, sahib/İKT). Uğursuz MAC → nəzarətçi yeni PIN/zal
   kompüteri qeydi ilə bərpa edir.
5. **Kompüter dəyişməsi / yeni PIN / köhnə PIN** — DÜZƏLDİLDİ. Boşluq: kabinet PIN-i ilə başqa qeydli
   kompüterdən giriş cəhdin `room_computer`-ini köçürürdü, cihaz qapısı isə bunu «eyni zal kompüteri»
   sayırdı → nəzarətçisiz kompüter dəyişmək mümkün idi və yeni PIN veriləndən sonra köhnə PIN işləyirdi.
   İndi (`services/final_center/reentry.py`): davam edən cəhd üçün kabinet PIN-i yalnız EYNİ kompüter/
   brauzerdən (və ya «cihaz dəyişikliyi» təsdiqi ilə) keçir; nəzarətçi yeni PIN veribsə köhnə PIN
   etibarsızdır; rədd audit olunur, köhnə kompüterin qanuni sessiyası toxunulmaz qalır. Yeni PIN → eyni
   cəhd, eyni cavablar, taymer sıfırlanmır, cəhd yeni kompüterə bağlanır; köhnə tab növbəti
   autosave/status/heartbeat-də dayanır. Cihaz «təsdiqi» indi hər köçürmədə sərf olunur.
6. **Gündə bir final** — DÜZƏLDİLDİ. Qayda (2026-07: gündə bir rəsmi = final/midterm, eyni anda bir
   imtahan; istisna — imtahan mərkəzinin «ikinci şans» qrantı, audit olunur) var idi, amma bilet axını
   (`begin_attempt_for_ticket`) onu çağırmırdı və yoxlama kilidsiz idi (iki fərqli imtahanın paralel
   startı). İndi hər yeni rəsmi cəhd `auth_user` sətir kilidi altında qaydanı yenidən yoxlayır
   (`services/official_start.py`); gözləmə otağına girişdə erkən mesaj. Gün sərhədi Asia/Baku. Midterm
   2026-07 qaydasına görə final ilə eyni limiti paylaşır (dəyişdirilmədi).
7. **Performans / təhlükəsizlik** — PIN axtarışında N+1 (imtahan başına PIN sorğusu) aradan qaldırıldı;
   şəbəkə qapısı DB sorğusuz; gün qaydası kilidi yalnız yeni rəsmi cəhddə. IDOR: cəhd endpoint-ləri
   `user=request.user` ilə süzülür; rate limit: IP+istifadəçi (bilet), istifadəçi (fərdi PIN, kod yolu),
   bilet lockout — yerindədir.

## Sabah yoxlanmalı

* Prod `.env`-də `EXAM_FINAL_INTERNAL_ONLY` təyin edilməyibsə defolt `True`-dur — zal kompüterləri
  daxili zonada olmalıdır (nginx `geo`: 10/8, 172.16/12, 192.168/16). Kənardan midterm verə bilən tələbə
  artıq olmayacaq (sahibin tələbi). Söndürmək: `EXAM_FINAL_INTERNAL_ONLY=False` + app restart.
* Kompüter dəyişən tələbə üçün prosedur: nəzarətçi monitorda «Yenidən giriş» → yeni PIN.
* Testlər: `apps/exams/tests/test_examaccess_2026_10_13.py`.
