const fs = require("fs");
const path = require("path");

const candidates = [
  "pdfjs-dist/build/pdf.worker.min.mjs",
  "pdfjs-dist/legacy/build/pdf.worker.min.mjs",
];

const publicDir = path.join(__dirname, "..", "public");
fs.mkdirSync(publicDir, { recursive: true });

for (const relative of candidates) {
  const source = path.join(__dirname, "..", "node_modules", relative);
  if (fs.existsSync(source)) {
    fs.copyFileSync(source, path.join(publicDir, "pdf.worker.min.mjs"));
    process.exit(0);
  }
}

console.warn("pdf.worker.min.mjs was not found; the PDF pane will report a load error until react-pdf is installed.");
