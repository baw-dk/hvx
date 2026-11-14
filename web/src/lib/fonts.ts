/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
// Fonts embedded in the sticker SVG, so a downloaded SVG or PNG renders the same anywhere.
import sg700 from "@fontsource/space-grotesk/files/space-grotesk-latin-700-normal.woff2?inline";
import sg500 from "@fontsource/space-grotesk/files/space-grotesk-latin-500-normal.woff2?inline";
import in400 from "@fontsource/inter/files/inter-latin-400-normal.woff2?inline";
import in500 from "@fontsource/inter/files/inter-latin-500-normal.woff2?inline";
import in600 from "@fontsource/inter/files/inter-latin-600-normal.woff2?inline";
import jb500 from "@fontsource/jetbrains-mono/files/jetbrains-mono-latin-500-normal.woff2?inline";

const face = (family: string, weight: number, src: string) =>
  `@font-face{font-family:"${family}";font-weight:${weight};font-style:normal;src:url(${src}) format("woff2");}`;

export function stickerFontFaces(): string {
  return [
    face("Space Grotesk", 700, sg700), face("Space Grotesk", 500, sg500),
    face("Inter", 400, in400), face("Inter", 500, in500), face("Inter", 600, in600),
    face("JetBrains Mono", 500, jb500),
  ].join("");
}
