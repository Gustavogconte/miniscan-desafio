// Copia o OpenCV.js (~11 MB) de node_modules para public/vendor, onde o Web Worker
// do recorte ao vivo o carrega. O arquivo não vai para o Git: é gerado no install/build.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const raiz = join(dirname(fileURLToPath(import.meta.url)), "..");
const origem = join(raiz, "node_modules", "@techstark", "opencv-js", "dist", "opencv.js");
const destino = join(raiz, "public", "vendor", "opencv-4.12.0.js");

if (!existsSync(origem)) {
  console.error("OpenCV.js não encontrado. Rode npm install.");
  process.exit(1);
}
mkdirSync(dirname(destino), { recursive: true });
copyFileSync(origem, destino);
console.log("OpenCV.js copiado para public/vendor/");
