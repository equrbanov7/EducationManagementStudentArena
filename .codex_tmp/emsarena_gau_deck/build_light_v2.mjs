import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const source = "/Users/elvin/Desktop/EMSArena_GAU_Teqdimat_Elvin_Qurbanov.pptx";
const output = "/Users/elvin/Desktop/EMSArena_GAU_Teqdimat_Isiqli_GAU_Rengleri.pptx";
const qaDir = "/Users/elvin/Desktop/Programming Folders/EMSArena/EMSArena/.codex_tmp/emsarena_gau_deck/light-v2";

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

async function main() {
  await fs.mkdir(qaDir, { recursive: true });
  const presentation = await PresentationFile.importPptx(await FileBlob.load(source));

  const sectionSlides = new Set([0, 5, 8, 12, 17, 24]);
  for (const [index, slide] of presentation.slides.items.entries()) {
    slide.background.fill = sectionSlides.has(index) ? "#397F79" : "#F8FCFB";
  }

  const closing = presentation.slides.getItem(24);
  const contact = closing.shapes.items.find((shape) => shape.text?.toString?.().includes("Əlaqə:"));
  if (!contact) throw new Error("Əlaqə sətri tapılmadı.");
  contact.text.replace(
    "Əlaqə: ad, soyad · e-poçt · telefon",
    "Elvin Qurbanov · 050 838 37 464 · elvingurbanov@list.ru",
  );

  for (const [index, slide] of presentation.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    await writeBlob(path.join(qaDir, `${stem}.png`), await presentation.export({ slide, format: "png", scale: 1 }));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(qaDir, `${stem}.layout.json`), await layout.text());
  }
  await writeBlob(path.join(qaDir, "montage.webp"), await presentation.export({ format: "webp", montage: true, scale: 1 }));
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(output);
  console.log(output);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
