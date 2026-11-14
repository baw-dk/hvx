/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
// Tailwind CSS 4 runs as its own PostCSS plugin and adds vendor prefixes itself.
module.exports = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
}
