"use strict";

const fs = require("fs");
const path = require("path");
const {createHash} = require("crypto");

const masterNames = {
  "laborant-journal": "L01-01-laborant-jurnal",
  "laborant-department": "L01-02-laborant-kafedra",
  "laborant-components": "L01-03-laborant-komponentler",
  "faq-video-editor": "RIM-FAQ-video-redaktor",
  "journal-watch": "RIM-02-journal-watch",
};

function identical(a, b) {
  if (fs.statSync(a).size !== fs.statSync(b).size) return false;
  const hash = file => createHash("sha256").update(fs.readFileSync(file)).digest("hex");
  return hash(a) === hash(b);
}

function buildFaq(root, target, role, lessonPaths) {
  const modelPath = path.join(root, "out", "faq-model.json");
  const page = path.join(target, "FAQ.html");
  if (!fs.existsSync(modelPath)) return fs.existsSync(page);

  const model = JSON.parse(fs.readFileSync(modelPath, "utf8"));
  if (role) {
    const visible = new Set(model.roles[role].ids);
    model.roles = {[role]:model.roles[role]};
    model.guides = model.guides.filter(g => visible.has(g.key));
    const videos = new Set(model.guides.map(g => g.video));
    model.media = Object.fromEntries(Object.entries(model.media).filter(([name]) => videos.has(name)));
    for (const guide of model.guides) {
      if (!lessonPaths.has(guide.long)) {delete guide.long; delete guide.longStart;}
    }
    for (const media of Object.values(model.media)) {
      for (const chapter of media.chapters) {
        if (!visible.has(chapter.guide)) delete chapter.guide;
        if (chapter.related) chapter.related = chapter.related.filter(row => visible.has(row.key));
      }
    }
  }
  const source = path.resolve(root, "../../apps/accounts/guide_media");
  const output = path.join(target, "FAQ media");
  fs.mkdirSync(output, {recursive: true});
  const copies = new Set();
  for (const [name, media] of Object.entries(model.media)) {
    const filename = name + ".mp4";
    const shipped = path.join(source, filename);
    const lesson = lessonPaths.get(masterNames[name] || name);
    if (lesson && identical(shipped, path.join(target, decodeURIComponent(lesson)))) {
      media.path = lesson;
    } else {
      copies.add(filename);
      fs.copyFileSync(shipped, path.join(output, filename));
      media.path = "FAQ%20media/" + filename;
    }
    media.vtt = fs.readFileSync(path.join(source, name + ".vtt"), "utf8");
  }
  const manifest = path.join(target, role === "telebe" ? ".student-faq-media.json" : ".faq-media.json");
  const previous = fs.existsSync(manifest) ? JSON.parse(fs.readFileSync(manifest, "utf8")) : [];
  for (const entry of fs.readdirSync(output)) {
    if (copies.has(entry)) continue;
    const installed = path.join(output, entry);
    if (previous.includes(entry)) fs.unlinkSync(installed);
    else if (role) throw new Error("Rol paketində tanınmayan fayl: " + entry);
  }
  fs.writeFileSync(manifest, JSON.stringify([...copies]));

  const template = fs.readFileSync(path.join(root, "lib", "faq-offline.html"), "utf8");
  const data = JSON.stringify(model).replace(/</g, "\\u003c");
  fs.writeFileSync(page, template.replace("__MODEL__", () => data));
  return true;
}

module.exports = {buildFaq};
