import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const source = "/Users/elvin/Desktop/Programming Folders/EMSArena/EMSArena/.codex_tmp/emsarena_gau_30/template-starter.pptx";
const output = "/Users/elvin/Desktop/EMSArena_GAU_30_Slayd_Vizual_Teqdimat.pptx";
const qaDir = "/Users/elvin/Desktop/Programming Folders/EMSArena/EMSArena/.codex_tmp/emsarena_gau_30/final";

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

async function main() {
  await fs.mkdir(qaDir, { recursive: true });
  const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
  for (const [index, slide] of presentation.slides.items.entries()) {
    slide.background.fill = index === 0 ? "#397F79" : "#F8FCFB";
    const sourceBlock = "[Sources]\n- İstifadəçi tərəfindən təqdim edilmiş EMS-Arena-Imtahan-Sistemi-GAU.pptx; sistem ekran görüntüləri və məhsul məlumatları.";
    slide.speakerNotes.textFrame.setText(sourceBlock);
    slide.speakerNotes.setVisible(true);
  }

  const cover = presentation.slides.getItem(0);
  const prepared = cover.shapes.items.find((shape) => shape.text?.toString?.().includes("Hazırladı:"));
  const screenshotClaim = cover.shapes.items.find((shape) => shape.text?.toString?.().includes("Bütün ekran görüntüləri"));
  if (prepared) prepared.text.replace("Hazırladı:  Elvin Qurbanov", "Hazırladı: Elvin Qurbanov");
  if (screenshotClaim) screenshotClaim.text.replace(
    "Bütün ekran görüntüləri işlək sistemdən — demo mühitində çəkilib",
    "Əlaqə: 050 838 37 464 · elvingurbanov@list.ru",
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

main().catch((error) => { console.error(error); process.exitCode = 1; });
