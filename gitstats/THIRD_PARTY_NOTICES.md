# Third-Party Notices

This document lists third-party libraries bundled with GitStats.

## chart.umd.min.js

- **Name**: Chart.js
- **Version**: 4.4.7
- **Source**: https://www.jsdelivr.com/package/npm/chart.js
- **License**: MIT
- **Usage**: Interactive charts rendered in HTML reports (replaces Gnuplot)

To upgrade: download the UMD build from https://www.jsdelivr.com/package/npm/chart.js and replace this file.

## sortable.js

- **Name**: Sortable Table Script
- **Author**: Joost de Valk (based on kryogenix.org sorttable)
- **Source**: http://www.joostdevalk.nl/code/sortable-table/
- **License**: MIT
- **Usage**: Client-side table sorting in HTML reports
- **Modifications**: sort indicators are drawn by CSS from a `data-sort` attribute instead of
  `arrow-*.gif` images, and the sorted header cell gets `aria-sort`

## IBMPlexMono-*-Latin1.woff2

- **Name**: IBM Plex Mono (Regular, Medium, SemiBold, Bold; Latin-1 subsets)
- **Author**: IBM Corp. (Reserved Font Name "Plex")
- **Version**: @ibm/plex-mono 2.5.0 (`fonts/split/woff2/`)
- **Source**: https://github.com/IBM/plex, https://www.jsdelivr.com/package/npm/@ibm/plex-mono
- **License**: SIL Open Font License 1.1, full text in `IBMPlexMono-LICENSE.txt`
  (copied next to the fonts in every report)
- **Usage**: Monospace headings, labels and numbers in HTML reports (`@font-face` in `gitstats.css`)
- **Modifications**: none; files are the upstream subsets, unrenamed

To upgrade: replace the four `.woff2` files and the license from the same package path, and
update the `unicode-range` in `gitstats.css` from the package's `IBMPlexMono-*.css` if it changed.
