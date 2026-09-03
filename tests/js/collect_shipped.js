/* ═══════════════════════════════════════════════════════════════════════════
   QAPI QOŞQUSU — GÖNDƏRİLƏN brauzer JS-ini ƏSL DOM-da İCRA EDİR
   ───────────────────────────────────────────────────────────────────────────
   Bu fayl `syllabus_editor_fields.js`-in TOPLAYICISINI təqlid ETMİR — onu
   OLDUĞU KİMİ, bir bayt dəyişmədən `window.eval` ilə icra edir və nəticəni
   Python test tərəfinə JSON kimi qaytarır.

   Niyə jsdom (təqlid deyil)
   =========================
   İtki sinfinin ÖZÜ brauzer semantikasıdır:

     * `<input>`-in «value sanitization algorithm»-i dəyərdən CR/LF-i SİLİR;
     * `<textarea>` sətir sonunu SAXLAYIR (və açılış teqindən sonrakı tək
       sətir sonunu parser atır);
     * `<select>`-də `selected` yoxdursa BİRİNCİ variant seçilmiş sayılır.

   Əvvəlki qapı (`editor_dom.py`) bu qaydaları ƏLLƏ modelə salmışdı və məhz
   orada sürüşdü: `<input>` sanitizasiyası modelə salınmadığı üçün test xam
   atributu oxuyub yaşıl qalırdı.  Yəni «emulyatoru emulyatorla yoxlamaq»
   səhvin ÖZÜDÜR.  jsdom həmin qaydaların spesifikasiyaya uyğun ƏSL
   tətbiqidir, ona görə burada heç nə modelə salınmır.

   Protokol
   ========
   stdin  ← JSON: { "html": "<render olunmuş panel HTML-i>",
                    "jsPath": "<göndərilən .js faylının mütləq yolu>",
                    "sections": ["info", "desc", …] }
   stdout → JSON: { "ok": true,
                    "api": ["collect", …],           (ixrac olunan açarlar)
                    "data": { "<section>": <payload> } }

   Xəta halında proses SIFIR OLMAYAN kodla çıxır və stderr-ə səbəbi yazır —
   Python tərəfi onu testin çökmə mesajına çevirir.  «Sükutla keçmək» yolu
   YOXDUR: `EMSSyllabusFields` yüklənməzsə və ya bölmə `null` qaytararsa
   qoşqu çökür.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const fs = require("fs");
const { JSDOM } = require("jsdom");

function fail(message) {
    process.stderr.write(message + "\n");
    process.exit(2);
}

function readStdin() {
    try {
        return fs.readFileSync(0, "utf8");
    } catch (err) {
        fail("stdin oxunmadı: " + err.message);
    }
}

const job = JSON.parse(readStdin());
if (!job.html || !job.jsPath || !Array.isArray(job.sections)) {
    fail("natamam iş tapşırığı: html / jsPath / sections tələb olunur");
}

const source = fs.readFileSync(job.jsPath, "utf8");

/* Redaktorun kökü — göndərilən JS `panel(el, id)` ilə buradan aşağı axtarır.
   `data-syllabus-editor` ATRIBUTU şablonun özündəki köklə eynidir. */
const dom = new JSDOM(
    "<!doctype html><html><body>" +
        "<div id=\"ems-root\" data-syllabus-editor data-readonly=\"0\">" +
        job.html +
        "</div></body></html>",
    { runScripts: "outside-only", url: "http://localhost/profile/" }
);

const { window } = dom;
window.eval(source);

const api = window.EMSSyllabusFields;
if (!api || typeof api.collect !== "function") {
    fail("göndərilən JS `window.EMSSyllabusFields.collect`-i qeydə almadı: " + job.jsPath);
}

const root = window.document.getElementById("ems-root");
const data = {};
job.sections.forEach(function (id) {
    const payload = api.collect(root, id);
    if (payload === null || payload === undefined) {
        fail("`collect(root, '" + id + "')` heç nə qaytarmadı — bölmə toplayıcısı yoxdur");
    }
    data[id] = payload;
});

process.stdout.write(
    JSON.stringify({ ok: true, api: Object.keys(api).sort(), data: data })
);
