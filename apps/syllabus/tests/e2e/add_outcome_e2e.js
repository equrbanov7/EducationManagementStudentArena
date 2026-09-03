/* E2E sürücüsü: «+ Təlim nəticəsi əlavə et» düyməsi.
   argv: [htmlFile, fieldsJs, editorJs, textsJson, outFile]

   Serverin RENDER ETDİYİ panelləri jsdom-a qoyur, GÖNDƏRİLƏN iki .js faylını
   olduğu kimi icra edir, sonra düyməyə N dəfə klikləyib mətnləri yazır.
   Nəticə: redaktorun autosave gövdələri + son DOM vəziyyəti. */
const fs = require("fs");
const { JSDOM } = require("jsdom");
const [htmlFile, fieldsJs, editorJs, textsJson, outFile] = process.argv.slice(2);
const texts = JSON.parse(fs.readFileSync(textsJson, "utf8"));

const dom = new JSDOM(
  `<!doctype html><html><body><div data-syllabus-editor data-readonly="0"
      data-save-url="/save" data-action-url="/act" data-version="v" data-profile-url="/p">
      ${fs.readFileSync(htmlFile, "utf8")}</div></body></html>`,
  { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/profile/" }
);
const { window } = dom;

const saved = [];
window.EMSReady = function (fn) { fn(); };
window.EMSDelegate = {
  handlers: [],
  on: function (evt, sel, fn) { this.handlers.push([evt, sel, fn]); },
  fire: function (evt, node) {
    this.handlers.forEach(function (h) {
      if (h[0] !== evt) { return; }
      const match = node.closest(h[1].replace("[data-syllabus-editor] ", ""));
      if (match) { h[2]({ target: node }, match); }
    });
  },
};
window.EMSCore = {
  getCookie: function () { return "csrf"; },
  fetchJSON: function (url, opts) {
    saved.push(JSON.parse(JSON.stringify(opts.data)));
    return {
      then: function (cb) {
        cb({ revision: saved.length, completion: { percent: 0, sections: {}, issues: [] } });
        return this;
      },
      catch: function () { return this; },
    };
  },
};
/* Struktur-saxlamadan sonra real tətbiq fraqmenti serverdən yenidən yükləyir;
   burada məqsəd DÜYMƏNİN ÖZÜNÜ ölçmək olduğu üçün yükləmə no-op-dur. */
window.EMSProfileLoadSection = function () {};

window.eval(fs.readFileSync(fieldsJs, "utf8"));
window.eval(fs.readFileSync(editorJs, "utf8"));

const doc = window.document;
const root = doc.querySelector("[data-syllabus-editor]");
const box = root.querySelector("[data-syl-outcomes]");
const addBtn = root.querySelector("[data-syl-outcome-add]");
const rows = () => box.querySelectorAll("[data-syl-outcome]");

const report = { before: rows().length, addButtonFound: !!addBtn, steps: [] };

texts.forEach(function (text, i) {
  window.EMSDelegate.fire("click", addBtn);
  const all = rows();
  const input = all.length ? all[all.length - 1].querySelector("[data-outcome]") : null;
  const step = { index: i + 1, rowCount: all.length, tag: input ? input.tagName.toLowerCase() : null };
  if (input) {
    input.value = text;
    window.EMSDelegate.fire("input", input);
  }
  report.steps.push(step);
});

/* Debounce (800 ms) bitsin ki, son yazının autosave gövdəsi də düşsün. */
setTimeout(function () {
  report.after = rows().length;
  report.tags = Array.prototype.map.call(box.querySelectorAll("[data-syl-outcome-tag]"), (n) => n.textContent);
  report.placeholders = Array.prototype.map.call(
    box.querySelectorAll("[data-outcome]"), (n) => n.getAttribute("placeholder")
  );
  report.ariaLabels = Array.prototype.map.call(
    box.querySelectorAll("[data-outcome]"), (n) => n.getAttribute("aria-label")
  );
  report.collected = window.EMSSyllabusFields.collect(root, "out");
  report.payloads = saved;
  report.lastOutPayload = saved.filter((p) => p.section === "out").pop() || null;
  fs.writeFileSync(outFile, JSON.stringify(report, null, 2), "utf8");
}, 1200);
