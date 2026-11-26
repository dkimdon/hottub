// Converts the cut-out tub pictures (PNG, from ../../scripts/make_images.ps1)
// to WebP for the page: the same picture, transparency included, at about a
// tenth of the size.  Development only; sharp is a dev dependency.
//
//     node scripts/webp.mjs <folder of PNGs> <output folder>

import { readdirSync, statSync } from "node:fs";
import { basename, join } from "node:path";
import sharp from "sharp";

const [from, to] = process.argv.slice(2);
for (const file of readdirSync(from).filter((f) => f.endsWith(".png"))) {
  const out = join(to, basename(file, ".png") + ".webp");
  await sharp(join(from, file)).webp({ quality: 85, alphaQuality: 90, effort: 6 }).toFile(out);
  console.log(`${basename(out).padEnd(22)} ${statSync(out).size.toLocaleString().padStart(8)} bytes`);
}
