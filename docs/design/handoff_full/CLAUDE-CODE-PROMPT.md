Bu layihəyə `design_handoff_full/` qovluğu əlavə edilib — EMS Arena-nın 22 ekranının hazır dizaynı.

ADDIM 1. `design_handoff_full/README.md` faylını TAM oxu (uzundur, atlamadan oxu).
ADDIM 2. `design_handoff_full/design/` içindəki `.dc.html` fayllarını oxu. Vizual baxış üçün `design_handoff_full/index.html` faylını brauzerdə aç — 22 ekranı yanaşı göstərir.
ADDIM 3. Kod yazmadan əvvəl mənə plan ver: hansı app/model/view/template/URL fayllarını yaradacaqsan və hansı ardıcıllıqla (README §9-dakı mərhələlərə uyğun).

Bunlar REFERANS DİZAYNLARDIR — production kod deyil. `.dc.html` faylları React əsaslı prototipdir və `support.js` runtime-ı ilə işləyir. Bu runtime-ı və prototipləri layihəyə KÖÇÜRMƏ. Vəzifən: bu ekranları EMS Arena-nın mövcud Django + template + `static/css/design-tokens.css` mühitində, mövcud pattern-lərlə piksel dəqiqliyində yenidən qurmaqdır. Prototipdəki hardcoded massivlər (`ROWS`, `DEPS`, `PLAN`, `CAT`, `TICKETS` …) real queryset-lərin yerinə duran nümunə datadır.

MƏCBURİ QAYDALAR:
1. README §2-dəki token qaydası. Rəngləri hardcode ETMƏ, yeni rəng icad ETMƏ, mövcud tokenləri dəyişmə — yalnız §2-də verilən əlavə bloku əlavə et.
2. Bütün mətnlər (copy) Azərbaycan dilindədir və YEKUNDUR — hərfi götür, tərcümə etmə, yenidən yazma.
3. Status enum-larının `key`, `label` və rəng cütləri README-dəki cədvəllərlə eyni olmalıdır.
4. README §8-dəki backend acceptance qaydaları pozulmamalıdır (xüsusən: təsdiqlənmiş sillabus/plan immutable-dır, silmə yoxdur — arxivləmə var, səbəb məcburi olan əməllər, scope qaydası).
5. README §7-dəki accessibility tələbləri pozulmamalıdır.
6. Layout-u öz mülahizənlə dəyişmə. Ölçü, boşluq, radius, rəng dəyərlərini prototipdən götür.

Sual yaranarsa uydurma — README §10-dakı açıq qərarlar siyahısına bax, orada da yoxsa məndən soruş.
