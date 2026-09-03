/* REAL shipped collector + a scripted TEACHER EDIT before collecting.
   argv: [htmlFile, jsFile, outFile, editsJsonFile] */
const fs = require("fs");
const { JSDOM } = require("jsdom");

const [htmlFile, jsFile, outFile, editsFile] = process.argv.slice(2);
const dom = new JSDOM(
    `<!doctype html><html><body><div id="ems-root">${fs.readFileSync(htmlFile, "utf8")}</div></body></html>`,
    { runScripts: "outside-only" });
const { window } = dom;
window.eval(fs.readFileSync(jsFile, "utf8"));
const api = window.EMSSyllabusFields;
const root = window.document.getElementById("ems-root");

const edits = JSON.parse(fs.readFileSync(editsFile, "utf8"));
const log = [];

/* «Müəllim həftə sətrini boşaldır»: mövzu + hər üç saat sıfır. */
(edits.blankWeekRows || []).forEach(function (index) {
    const tr = root.querySelector("[data-syl-week-row='" + index + "']");
    if (!tr) { log.push("YOX: week row " + index); return; }
    tr.querySelector("[data-week='topic']").value = "";
    ["lecture", "seminar", "lab"].forEach(function (kind) {
        tr.querySelector("[data-week='" + kind + "']").value = "0";
    });
    const outcome = tr.querySelector("[data-week='outcome']");
    if (outcome) { outcome.value = ""; }
    log.push("bosaldildi: week " + index);
});

/* «Müəllim sərbəst iş yuvasını boşaldır» (Təmizlə düyməsinin etdiyi). */
(edits.blankSelfSlots || []).forEach(function (index) {
    const slot = root.querySelector("[data-syl-slot='" + index + "']");
    if (!slot) { log.push("YOX: slot " + index); return; }
    slot.querySelector("[data-selfwork-title]").value = "";
    log.push("bosaldildi: slot " + index);
});

const out = {};
["info", "desc", "out", "week", "method", "assess", "self", "lit"].forEach(function (id) {
    out[id] = api.collect(root, id);
});
fs.writeFileSync(outFile, JSON.stringify({ data: out, log: log }, null, 1), "utf8");
