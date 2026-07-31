import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const buildDir = "/Users/elvin/Desktop/Programming Folders/EMSArena/EMSArena/.codex_tmp/emsarena_gau_deck";
const source = path.join(buildDir, "template-starter.pptx");
const output = "/Users/elvin/Desktop/EMSArena_GAU_Teqdimat_Elvin_Qurbanov.pptx";
const previewDir = path.join(buildDir, "final-preview");
const layoutDir = path.join(buildDir, "final-layout", "final");

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

async function main() {
  await fs.mkdir(previewDir, { recursive: true });
  await fs.mkdir(layoutDir, { recursive: true });

  const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
  const slide1 = presentation.slides.getItem(0);
  const labelShape = slide1.shapes.items.find((shape) => shape.text?.toString?.().includes("Funksional icmal"));
  const dateShape = slide1.shapes.items.find((shape) => shape.text?.toString?.().includes("İyul 2026"));
  const versionShape = slide1.shapes.items.find((shape) => shape.text?.toString?.().includes("Versiya 1.0"));
  if (!labelShape || !dateShape || !versionShape) throw new Error("Açılış slaydındakı redaktə hədəfləri tapılmadı.");
  labelShape.text.replace("Funksional icmal", "Elvin Qurbanov");
  dateShape.text.replace("İyul 2026", "Hazırladı");
  versionShape.text.replace("Versiya 1.0", "Avqust 2026");

  for (const [index, slide] of presentation.slides.items.entries()) {
    const notes = slide.speakerNotes;
    const existing = notes.textFrame?.toString?.()?.trim?.() || "";
    const sourceBlock = "[Sources]\n- İstifadəçi tərəfindən təqdim edilmiş EMSArena və GAU təqdimat materialları; sistem ekran görüntüləri və məhsul məlumatları.";
    notes.textFrame.setText([existing, sourceBlock].filter(Boolean).join("\n\n"));
    notes.setVisible(true);

    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    await writeBlob(path.join(previewDir, `${stem}.png`), await presentation.export({ slide, format: "png", scale: 1 }));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(layoutDir, `${stem}.layout.json`), await layout.text());
  }

  await writeBlob(path.join(buildDir, "final-montage.webp"), await presentation.export({ format: "webp", montage: true, scale: 1 }));
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(output);

  const inspect = await presentation.inspect({ kind: "slide,textbox,shape,image,notes", maxChars: 50000 });
  await fs.writeFile(path.join(buildDir, "final-inspect.ndjson"), inspect.ndjson);
  console.log(output);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
