// Bütün out/*/meta.json → nömrələnmiş kitabxana qovluğu + index.html pleyer + İçindəkilər.md.
// İstifadə: node build-library.cjs ["~/Movies/WCU video dərslər"]
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { ROOT } = require("./lib/browser.cjs");

const { buildFaq } = require("./lib/faq-library.cjs");
const { chapters, scenarios } = require("./lib/chapters.cjs");
const scripts = scenarios(path.join(ROOT, "scenarios"));
const args = process.argv.slice(2);
const sourceModel = path.join(ROOT, "out", "faq-model.json");
const faqData = fs.existsSync(sourceModel) ? JSON.parse(fs.readFileSync(sourceModel, "utf8")) : {};
const roles = faqData.roles || {};
const roleArg = args.find(arg => arg.startsWith("--role="));
const packageRole = roleArg ? roleArg.slice("--role=".length) : (args.includes("--student") ? "telebe" : null);
if ((roleArg || packageRole) && (!Object.hasOwn(roles, packageRole) || packageRole === "all")) {
  throw new Error("Təlimat paketi üçün tanınmış rol seçin.");
}
const student = packageRole === "telebe";
const roleLabel = packageRole && roles[packageRole].label;
const defaultFolder = packageRole ? roleLabel.replaceAll("/", "-") + " video təlimatları" : "VideoTeqdimat";
const target = (args.find(arg => !arg.startsWith("--")) || path.join(os.homedir(), "Desktop", "RIM", defaultFolder)).replace(/^~/, os.homedir());
const marker = path.join(target, ".role-library");
if (packageRole && fs.existsSync(target) && fs.readdirSync(target).length) {
  const previous = fs.existsSync(marker) ? fs.readFileSync(marker, "utf8").trim() :
    (fs.existsSync(path.join(target, ".student-library")) ? "telebe" : "");
  if (previous !== packageRole) throw new Error("Bu rol üçün boş qovluğu və ya həmin rolun əvvəlki paketini seçin.");
}
if (!packageRole && (fs.existsSync(marker) || fs.existsSync(path.join(target, ".student-library")))) {
  throw new Error("RİM arxivini ayrıca qovluqda yaradın.");
}
const permittedIds = new Set(packageRole ? roles[packageRole].ids : []);
const ownTour = packageRole && "tour-" + packageRole.replaceAll("_", "-");
const safe = (s) => String(s).replace(/[:/\\?*"<>|]/g, " -").replace(/\s+/g, " ").trim();
const mmss = (sec) => {
  const seconds = Math.round(sec);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
};

function srtToVtt(srt) {
  return "WEBVTT\n\n" + srt.replace(/\r/g, "").replace(/(\d\d:\d\d:\d\d),(\d\d\d)/g, "$1.$2");
}

const AUDIENCES = ["Hamı üçün", "Tələbə üçün", "Müəllim üçün", "Laborant üçün", "Kafedra müdiri üçün", "Dekanlıq üçün", "Tyutor üçün", "İmtahan Mərkəzi üçün", "Tədris şöbəsi üçün", "Tələbə xidmətləri üçün", "Mühasib üçün", "HR üçün", "Monitorinq üçün", "Keyfiyyətə nəzarət üçün", "RİM üçün"];
const audRank = (m) => { const i = AUDIENCES.indexOf(m.audience || "Müəllim üçün"); return i < 0 ? 99 : i; };
const metas = fs.readdirSync(path.join(ROOT, "out"))
  .map((d) => path.join(ROOT, "out", d, "meta.json"))
  .filter((f) => fs.existsSync(f))
  .map((f) => JSON.parse(fs.readFileSync(f, "utf8")))
  .filter((m) => fs.existsSync(m.mp4))
  .filter(m => !packageRole || (m.name === ownTour && permittedIds.has(ownTour)) ||
    (m.name === "RIM-02-journal-watch" && permittedIds.has("section-journal-watch")) ||
    (student && m.audience === "Tələbə üçün" && !m.name.startsWith("tour-")) ||
    ["H00-03-ilk-giris", "H00-04-parol-berpasi"].includes(m.name))
  .sort((a, b) => audRank(a) - audRank(b) || String(a.order).localeCompare(String(b.order), undefined, { numeric: true }));

if (!metas.length) { console.error("out/ içində hazır video yoxdur"); process.exit(1); }
fs.mkdirSync(target, { recursive: true });
// Manifest: əvvəlki yığımın yaratdığı, indi out/-da olmayan (köhnəlmiş / silinmiş) videolar kitabxanadan silinir.
const manifestPath = path.join(target, ".kitabxana.json");
const prevFiles = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, "utf8")) : [];
const newFiles = [];

if (student) fs.writeFileSync(path.join(target, ".student-library"), "Tələbə\n");
if (packageRole) fs.writeFileSync(marker, packageRole + "\n");
const lessons = [];
for (const m of metas) {
  const audience = m.audience || "Müəllim üçün";
  const dir = path.join(target, safe(audience), safe(m.section));
  fs.mkdirSync(dir, { recursive: true });
  const base = safe(`${m.order} ${m.title}`);
  fs.copyFileSync(m.mp4, path.join(dir, base + ".mp4"));
  for (const ext of [".mp4", ".srt", ".vtt"]) newFiles.push(path.relative(target, path.join(dir, base + ext)));
  const srt = fs.readFileSync(m.srt, "utf8");
  fs.writeFileSync(path.join(dir, base + ".srt"), srt);
  const vtt = srtToVtt(srt);
  fs.writeFileSync(path.join(dir, base + ".vtt"), vtt);
  const role = m.name.startsWith("tour-") ? m.name.slice(5).replaceAll("-", "_") : "";
  const visible = new Set(roles[packageRole || role]?.ids || []);
  const markers = (faqData.media?.[m.name]?.chapters || chapters(m, scripts.get(m.name), srt)).map(ch => {
    const result = {...ch};
    if (!visible.has(result.guide)) delete result.guide;
    if (result.related) result.related = result.related.filter(item => visible.has(item.key));
    return result;
  });
  lessons.push({
    id: m.name, role, chapters: markers, order: m.order, section: m.section, audience, title: m.title, summary: m.summary || "",
    duration: m.duration, shortGuide: m.shortGuide === true || (m.duration <= 90 && !/^00(?:\.| )/.test(m.order) && !m.order.endsWith(".00")),
    src: [safe(audience), safe(m.section), base + ".mp4"].map(part => encodeURIComponent(part).replace(/\(/g, "%28").replace(/\)/g, "%29")).join("/"), vtt,
  });
}

const hasFaq = buildFaq(ROOT, target, packageRole, new Map(lessons.map(l => [l.id, l.src])));

// İçindəkilər
const total = lessons.reduce((n, l) => n + l.duration, 0);
let md = `# WCU video dərslər — İçindəkilər\n\n${lessons.length} dərs · ümumi ${mmss(total)}\n\n`;
const shortGuides = lessons.filter((lesson) => lesson.shortGuide);
if (shortGuides.length) {
  md += "\n## Qısa praktik dərslər\n\n";
  for (const lesson of shortGuides) {
    md += `- ${lesson.audience} · [${lesson.title}](${lesson.src}) · ${mmss(lesson.duration)}\n`;
  }
}
let lastSection = "", lastAud = "";
for (const l of lessons) {
  if (l.audience !== lastAud) { md += `\n# ${l.audience}\n`; lastAud = l.audience; lastSection = ""; }
  if (l.section !== lastSection) { md += `\n## ${l.section}\n\n| № | Dərs | Müddət | Nə öyrədir |\n|---|---|---|---|\n`; lastSection = l.section; }
  md += `| ${l.order} | [${l.title}](${l.src}) | ${mmss(l.duration)} | ${l.summary.replace(/\|/g, "/")} |\n`;
}
md += `\nPleyer: qovluqdakı \`index.html\` faylını brauzerdə açın (internet lazım deyil).\n`;
fs.writeFileSync(path.join(target, "İçindəkilər.md"), md);

// Pleyer (tək fayl; VTT-lər JSON kimi daxildir, çünki file:// altında yanındakı .vtt bloklanır)
const data = JSON.stringify(lessons).replace(/</g, "\\u003c");
const html = `<!doctype html>
<html lang="az"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WCU — video dərslər</title>
<style>
:root{--bg:#f8fafc;--panel:#fff;--text:#0f172a;--muted:#64748b;--line:#e2e8f0;--brand:#2563eb;--active:#eff6ff}
@media (prefers-color-scheme:dark){:root{--bg:#0b1220;--panel:#111a2e;--text:#e2e8f0;--muted:#94a3b8;--line:#1e293b;--brand:#60a5fa;--active:#172554}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:18px 24px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:baseline}
header h1{font-size:19px;margin:0}header span{color:var(--muted);font-size:14px}
main{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:20px;padding:20px 24px;max-width:1500px;margin:auto}
@media (max-width:900px){main{grid-template-columns:1fr}}
video{width:100%;border-radius:12px;background:#000;aspect-ratio:1366/768}
.meta h2{margin:14px 0 4px;font-size:20px}.meta .sec{color:var(--brand);font-weight:600;font-size:13px;text-transform:uppercase;letter-spacing:.06em}
.meta p{color:var(--muted);margin:6px 0 14px}
.nav{display:flex;gap:10px}.nav button{border:1px solid var(--line);background:var(--panel);color:var(--text);padding:9px 16px;border-radius:9px;cursor:pointer;font:inherit}
.nav button:disabled{opacity:.4;cursor:default}
aside{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:8px;align-self:start;max-height:calc(100vh - 110px);overflow:auto}
aside h3{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:12px 10px 6px}
aside button{display:grid;grid-template-columns:44px 1fr auto;gap:8px;width:100%;text-align:left;border:0;background:none;color:var(--text);padding:9px 10px;border-radius:8px;cursor:pointer;font:inherit}
aside button:hover{background:var(--active)}aside button.on{background:var(--active);outline:2px solid var(--brand)}
aside h2.aud{font-size:14px;margin:14px 10px 2px;color:var(--brand)}aside .n{color:var(--muted);font-variant-numeric:tabular-nums}aside .d{color:var(--muted);font-size:13px}
aside label{display:grid;gap:3px;margin:8px;font-size:13px}aside input,aside select{font:inherit;color:inherit;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:8px}#chapters{display:grid;gap:4px;padding:8px 0}#chapters button,#pager button{font:inherit;cursor:pointer;color:var(--brand);background:var(--panel);border:1px solid var(--line);border-radius:5px;padding:6px;text-align:start}#pager{display:flex;gap:4px;flex-wrap:wrap}#pager button{width:auto}#pager [aria-current]{background:var(--active);font-weight:700}.meta details{margin:8px 0 16px}aside>a{display:block;padding:8px;color:var(--brand)}
</style></head><body>
<header><h1>${packageRole ? roleLabel + " üçün video dərslər" : "WCU — video dərslər"}</h1><span>${lessons.length} dərs · ${mmss(total)}</span></header>
<main><section><video id="v" controls preload="none" playsinline></video>
<div class="meta"><div class="sec" id="sec"></div><h2 id="ttl"></h2><p id="sum"></p>
<details><summary>Videoda mövzuya keç</summary><input id="chapter-query" type="search" aria-label="Videoda bölmə və ya tab axtar" placeholder="Videoda bölmə və ya tab axtar" hidden><div id="chapters"></div></details><div class="nav"><button id="prev">← Əvvəlki</button><button id="next">Növbəti →</button></div></div></section>
<aside>${hasFaq ? '<a href="FAQ.html">Ən çox verilən suallar →</a>' : ""}<label>Dərs axtar<input type="search" id="query"></label><label ${packageRole ? "hidden" : ""}>Rol<select id="audience"><option value="">Bütün rollar</option></select></label><div id="list"></div><nav id="pager" aria-label="Dərs səhifələri"></nav></aside></main>
<script id="lessons" type="application/json">${data}</script>
<script>
${fs.readFileSync(path.join(ROOT, "lib/library-player.js"), "utf8")}
</script></body></html>`;
fs.writeFileSync(path.join(target, "index.html"), html);
console.log(`${lessons.length} dərs, ${mmss(total)} → ${target}`);

for (const rel of prevFiles) {
  if (newFiles.includes(rel)) continue;
  const abs = path.join(target, rel);
  if (fs.existsSync(abs)) { fs.unlinkSync(abs); console.log("silindi (köhnə):", rel); }
  try { const d = path.dirname(abs); if (fs.readdirSync(d).length === 0) fs.rmdirSync(d); } catch (e) {}
}
fs.writeFileSync(manifestPath, JSON.stringify(newFiles, null, 1));
