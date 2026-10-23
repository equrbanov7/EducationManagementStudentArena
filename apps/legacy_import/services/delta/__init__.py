"""Köhnə sistemin (myedu) cutover-dən SONRAKI dəyişikliklərinin (DELTA) yeni sistemə köçürülməsi.

Niyə ayrıca boru (repetisiya deyil)
-----------------------------------
``legacy_import_rehearse`` BÜTÖV, atılabilən hədəfə yazan run-dur (ledger açarları run-a bağlıdır,
fərqli hash ``legacy_entity_identity_conflict`` verir). Cutover-dən sonra isə yeni sistemdə canlı iş
gedir: müəllimlər jurnal yazır, RİM tələbə qəbul edir, tədris şöbəsi dərs yükü paylayır. Delta ona
görə İKİ addımdır:

1. ``legacy_delta_extract`` (lokal, MariaDB-yə çıxışı olan maşında) — yeni snapshot-dan və cutover
   snapshot-u (baza) ilə fərqdən **paket** (JSON.gz) qurur. Paketdə şəxsi məlumat var (ad, FİN) —
   0600 yazılır, serverə yalnız ŞİFRƏLİ release asset kimi gedir (``prod-data-ops`` naxışı).
2. ``legacy_delta_apply`` (hədəfdə) — paketi mövcud data ilə TUTUŞDURUR və yalnız ÇATIŞMAYANI yazır.

Qaydalar (sahibin «tövsiyə olunan variant» qaydası, 2026-10-23)
--------------------------------------------------------------
* **Yeni sistem qalibdir**: mövcud bal/dərs/müəllim/sillabus/yekun ÜZƏRİNƏ YAZILMIR — yalnız boş
  doldurulur; fərqlər «konflikt» kimi sayılır və hesabata düşür.
* Dry-run DEFAULT; yazı ``--apply`` ilə; markersiz (prod) bazada ``--i-know-this-is-production``.
* İdempotent: hər yazı təbii açarla (``get_or_create`` semantikası) — ikinci qaçış 0 yazı verir.
* Çatışmayan müəllim → FİN-siz hesab (``teacher_roster`` / ``intake.create`` yolu), tələbə → RİM-in
  ``create_account`` yolu (parolsuz; birdəfəlik parolu RİM verir). Bildiriş/e-poçt GETMİR.
* Köçürülən sillabus açılışa ``APPROVED`` (``approval_source=migration``) — müəllimə iş yaranmır.
* Hesabat yalnız SAYLARDIR; adlar yalnız ``--names-out`` faylına (0600) yazılır.
"""
