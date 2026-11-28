"use strict";
const fs = require("fs");
const path = require("path");

function normalize(value) {
  return value.toLocaleLowerCase("az").replace(/\[[^\]]*\]/g, "").replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}
function seconds(clock) {
  const [h, m, s] = clock.replace(",", ".").split(":").map(Number);
  return h * 3600 + m * 60 + s;
}
function scenarios(root) {
  const result = new Map();
  for (const group of fs.readdirSync(root, {withFileTypes: true})) {
    if (!group.isDirectory()) continue;
    const folder = path.join(root, group.name);
    for (const file of fs.readdirSync(folder).filter(f => f.endsWith(".json"))) {
      const scene = JSON.parse(fs.readFileSync(path.join(folder, file), "utf8"));
      if (scene.name && scene.steps) result.set(scene.name, scene.steps);
    }
  }
  return result;
}
function chapters(meta, script, srt) {
  if (meta.chapters?.length) return meta.chapters;
  const cues = [...srt.replace(/\r/g, "").matchAll(/(\d{2}:\d{2}:\d{2},\d{3}) --> [^\n]+\n([^]*?)(?=\n\s*\n|$)/g)]
    .map(m => ({start: seconds(m[1]), text: m[2].replace(/\n/g, " ").trim()}));
  if (!cues.length) return [];
  const list = [{start: 0, title: meta.title}];
  let cursor = 0;
  for (const step of script || []) {
    const chapter = step.actions?.find(a => a.chapter)?.chapter;
    const card = step.actions?.find(a => a.card)?.card;
    const title = chapter || (card && card.title);
    if (!title || !step.say || step.id === "intro" || step.id === "outro") continue;
    const phrase = normalize(step.say).split(" ").slice(0, 5).join(" ");
    const index = cues.findIndex((cue, i) => i >= cursor && normalize(cue.text).startsWith(phrase));
    if (index < 0 || cues[index].start < 4) continue;
    cursor = index + 1;
    list.push({start: cues[index].start, title: title.replace(/^\d+\s*·\s*/, "")});
  }
  // Use the original spoken subtitle for any long interval without a scripted heading.
  const result = [];
  for (let i = 0; i < list.length; i++) {
    result.push(list[i]);
    const end = list[i + 1]?.start ?? meta.duration;
    for (const cue of cues) {
      if (cue.start < result.at(-1).start + (meta.duration < 90 ? 12 : 28) || cue.start + 7 > end) continue;
      result.push({start: cue.start, title: cue.text});
    }
  }
  return result;
}
module.exports = {chapters, scenarios};
