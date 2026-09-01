/* REGRESSİYA: `<textarea>` çevirməsi redaktorun ÖZ davranışını pozdumu?
   argv: [htmlFile, fieldsJs, editorJs, outFile] */
const fs = require("fs");
const { JSDOM } = require("jsdom");
const [htmlFile, fieldsJs, editorJs, outFile] = process.argv.slice(2);

const dom = new JSDOM(
  `<!doctype html><html><body><div data-syllabus-editor data-readonly="0"
      data-save-url="/save" data-action-url="/act" data-version="v" data-profile-url="/p">
      ${fs.readFileSync(htmlFile, "utf8")}</div></body></html>`,
  { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/profile/" });
const { window } = dom;

/* EMS qlobal qatının minimal, DAVRANIŞI SAXLAYAN stub-ları. */
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
    return { then: function (cb) { cb({ revision: 1, completion: { percent: 0, sections: {}, issues: [] } }); return this; },
             catch: function () { return this; } };
  },
};
window.EMSProfileLoadSection = function () {};

window.eval(fs.readFileSync(fieldsJs, "utf8"));
window.eval(fs.readFileSync(editorJs, "utf8"));

const doc = window.document;
const root = doc.querySelector("[data-syllabus-editor]");
const report = {};

/* 1. Formada Enter göndərmə riski varmı? */
report.formCount = doc.querySelectorAll("form").length;

/* 2. `addOutcome` — TEXTAREA klonu BOŞ gəlirmi? (defaultValue tələsi) */
const box = root.querySelector("[data-syl-outcomes]");
report.outcomesBefore = box.querySelectorAll("[data-syl-outcome]").length;
window.EMSDelegate.fire("click", root.querySelector("[data-syl-outcome-add]"));
const rows = box.querySelectorAll("[data-syl-outcome]");
report.outcomesAfter = rows.length;
const clone = rows.length ? rows[rows.length - 1].querySelector("[data-outcome]") : null;
report.cloneTag = clone ? clone.tagName.toLowerCase() : null;
report.cloneValue = clone ? clone.value : null;
report.cloneDefaultValue = clone ? clone.defaultValue : null;
report.cloneCollected = window.EMSSyllabusFields.collect(root, "out").outcomes;

/* 3. TN etiketləri yenidən nömrələndimi? */
report.tags = Array.prototype.map.call(box.querySelectorAll("[data-syl-outcome-tag]"),
                                       function (n) { return n.textContent; });

/* 4. Yazma → autosave zənciri `<textarea>`-da işləyirmi? */
const first = box.querySelector("[data-outcome]");
if (first) { first.value = "yeni sətir A\nyeni sətir B";
window.EMSDelegate.fire("input", first);
report.sectionOfTextarea = window.EMSSyllabusFields.sectionOf(first); }

/* 5. `[data-syl-clear]` textarea-nı boşalda bilirmi? */
const clearBtn = root.querySelector("[data-syl-clear]");
if (clearBtn) {
  const slot = root.querySelector("[data-syl-slot='" + clearBtn.getAttribute("data-syl-clear") + "']");
  report.slotTitleBefore = slot.querySelector("[data-selfwork-title]").value.slice(0, 30);
  window.EMSDelegate.fire("click", clearBtn);
  report.slotTitleAfter = slot.querySelector("[data-selfwork-title]").value;
}

/* 6. Sıfır nəticəli panel: «əlavə et» işləyirmi? */
const empty = new JSDOM(`<!doctype html><html><body><div data-syllabus-editor data-readonly="0">
  <article data-syl-panel="out"><div class="syl-outcomes" data-syl-outcomes data-min="3"></div>
  <button data-syl-outcome-add></button></article></div></body></html>`,
  { runScripts: "outside-only" });
report.emptyPanelSampleFound =
  !!empty.window.document.querySelector("[data-syl-outcomes] [data-syl-outcome]");

report.autosavePayloads = saved.length;
fs.writeFileSync(outFile, JSON.stringify(report, null, 1), "utf8");
