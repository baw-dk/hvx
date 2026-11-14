/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
export function save(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Standalone SVG document from SVG markup (e.g. renderToStaticMarkup of a sticker). */
export function svgDocument(markup: string): string {
  const withNs = markup.includes("xmlns=") ? markup : markup.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
  return '<?xml version="1.0" encoding="UTF-8"?>\n' + withNs.replace(/ class="[^"]*"/, "");
}

export const svgBlob = (markup: string) => new Blob([svgDocument(markup)], { type: "image/svg+xml" });

export async function pngBlob(markup: string, scale = 4): Promise<Blob> {
  const url = URL.createObjectURL(svgBlob(markup));
  try {
    const img = new Image();
    img.decoding = "async";
    img.src = url;
    await img.decode();
    const vb = /viewBox="0 0 ([\d.]+) ([\d.]+)"/.exec(markup);
    const width = vb ? Number(vb[1]) : img.naturalWidth;
    const height = vb ? Number(vb[2]) : img.naturalHeight;
    const canvas = Object.assign(document.createElement("canvas"), { width: width * scale, height: height * scale });
    canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((resolve) => canvas.toBlob((b) => resolve(b!), "image/png"));
  } finally {
    URL.revokeObjectURL(url);
  }
}

export const slugify = (text: string) =>
  text.toLowerCase().replace(/æ/g, "ae").replace(/ø/g, "oe").replace(/å/g, "aa").normalize("NFKD")
    .replace(/[^\w\s-]/g, "").trim().replace(/[\s_]+/g, "-").slice(0, 60) || "tail-label";
