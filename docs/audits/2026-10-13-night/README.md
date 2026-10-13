# Gecə dalğası 2026-10-13 — səhər xülasəsi

Sahib (gecə): «imtahanı check elə … bunların hamısını et», «alman dili əlavə et», «starostaya yenidən bax,
Qrupum yerinə Starosta», «səhərə kimi dayanmadan işlə, diaqnostikadan sonra deploy et». Altı agent ayrı
worktree-lərdə işlədi; nəticələr Develop-a birləşdirildi (hər biri ayrıca merge commit-i), sonra tam test +
CI + `exam_activity_probe` → deploy. Hər mövzunun ətraflı hesabatı bu qovluqdadır.

| Mövzu | Nə edildi | Hesabat |
|---|---|---|
| İmtahana giriş | Final/midterm YALNIZ universitet şəbəkəsindən (`EXAM_FINAL_INTERNAL_ONLY`, prod-da açıq); alt qrup tələbələrinə PIN; kompüter dəyişəndə yeni PIN → eyni cəhd, cavablar və vaxt qalır, köhnə PIN və köhnə tab dərhal etibarsız (bypass bağlandı); gündə 1 final (kilidlə, ikinci şans istisnası audit olunur); start yalnız POST. | [examaccess.md](examaccess.md) |
| Nəzarət | Nəzarətçi NÖVBƏSİ (`InvigilatorDuty`): giriş növbədən 30 dəq əvvəl açılır, imtahan/gün bitəndə avtomatik bağlanır (WS də); canlı monitor keşi + ETag (5 ekran = 1 hesablama), qalan vaxt / cavablanan sual; sual sırası hər cəhddə qarışdırılır; iki cihaz/tab və IP dəyişməsi siqnalı; yeni şübhəli elanı. | [examsuperv.md](examsuperv.md) |
| Tələbə şəkli | Test imtahanında sağda kimlik kartı (160×200 şəkil, ad, qrup, nömrə); şəkil yoxdursa baş hərflər + «vəsiqəni göstərin»; tənbəl şəkil yükləmə, 304, SVG rədd. | [examphoto.md](examphoto.md) |
| Apellyasiya | «Açar səhvdir — hamı üçün düzəlt» (heç kimin balı azalmır, jurnala append-only düzəliş, bildiriş); 3 təqvim günü (Bakı vaxtı ilə son günün sonuna qədər), evdən də; son tarix UI-da; dekan/koordinator üçün cəhd + apellyasiya tarixçəsi. | [appeals.md](appeals.md) |
| Starosta | «Qrupum» → «Starosta»: fənlər, seçmə fənlər (kim hansını götürür), başqa qrupla birləşmiş dərslər / alt qruplar, cədvəl, imtahanlar, elanlar; təyinat yalnız qrup reyestrindən (tək starosta, qrupun tələbəsi, audit + bildiriş). | [starosta.md](starosta.md) |
| Alman dili | `de` «Deutsch» — dil seçicisində, bütün kataloqlar (19 179 + 797 mətn) tərcümə olunub; canlı imtahan, AI, icazə redaktoru. | [german.md](german.md) |

## Səhər sizin edəcəkləriniz

1. **Starosta təmiri (prod):** köhnə üsulla təyin olunmuş starostalar bölməni görmür — əvvəlcə
   `manage.py repair_group_leads --org qku` (yalnız siyahı), baxın, sonra `--apply`.
2. **Nəzarətçi növbələri:** imtahan günündən əvvəl imtahan mərkəzi rəhbəri zal monitorunda «Nəzarətçi növbələri»
   əlavə etsin. Köhnə daimi təyinatlar yalnız zalda canlı imtahan olanda işləyir.
3. **Şəbəkə qaydası:** final/midterm artıq evdən açılmır (403 səhifəsi). Lazım olsa söndürmək:
   `EXAM_FINAL_INTERNAL_ONLY=False` + restart. Apellyasiya evdən işləyir.
4. **Kompüter dəyişməsi:** nəzarətçi «Yenidən giriş» → yeni PIN verir; köhnə kabinet PIN-i o cəhd üçün işləmir.
5. **Qərar gözləyən sual:** açar düzəlişi hər tələbəyə +1 verir (sizin «qəbul → +1» qaydanız). 1-dən çox ballıq
   suallarda tam bal verilsin?
6. **Profil şəkli olmayan tələbələr** imtahan kartında baş hərflə görünür — nəzarətçi vəsiqəni yoxlamalıdır.
7. **Alman terminləri:** Kafedra → «Lehrstuhl», Kollokvium → «Zwischenprüfung», Apellyasiya → «Einspruch»,
   Payız semestri → «Herbstsemester» — dəyişmək istəsəniz deyin.
