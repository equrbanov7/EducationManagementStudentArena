/* REAL shipped collector, driven by jsdom over the REAL rendered editor DOM.
   argv: [htmlFile, jsFile, outFile] */
const fs = require("fs");
const { JSDOM } = require("jsdom");

const [htmlFile, jsFile, outFile] = process.argv.slice(2);
const html = fs.readFileSync(htmlFile, "utf8");
const dom = new JSDOM(`<!doctype html><html><body><div id="ems-root">${html}</div></body></html>`,
                      { runScripts: "outside-only" });
const { window } = dom;
window.eval(fs.readFileSync(jsFile, "utf8"));

const api = window.EMSSyllabusFields;
if (!api) { throw new Error("EMSSyllabusFields did not load"); }

const root = window.document.getElementById("ems-root");
const out = {};
["info", "desc", "out", "week", "method", "assess", "self", "lit"].forEach(function (id) {
    out[id] = api.collect(root, id);
});
fs.writeFileSync(outFile, JSON.stringify(out, null, 1), "utf8");
