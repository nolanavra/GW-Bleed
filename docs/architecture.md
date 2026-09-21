# Architecture and invariants

The engine calculates integer-micrometre geometry and is independent of PDF/UI
libraries. Qt owns interactions and preview state. Workers receive immutable
inputs and return bounded messages. PDF services inspect, render, compose to a
staging file, and verify before the controller publishes with os.replace.

`pdf_backend` owns pypdf/PDFium normalization. Displayed dimensions are the
intersection of CropBox and MediaBox, respecting Rotate and UserUnit. Pages are
normalized to physical points with origin zero. Existing appearances are
flattened by PDFium; visible annotations without supported appearances fail
explicitly. JavaScript is not executed. A Form XObject reuses vector artwork;
engine rectangles drive physical-scale placements. Sheet clipping and all
page boxes use stock dimensions. Preview PNGs never enter the export path.

`desktop_entry` selects GUI versus PDF/export worker before Qt application
startup. Source execution uses module entry; standalone execution uses explicit
--gw-worker modes. `storage_io` performs bounded JSON reads and atomic saves.

Saved schema 3/4 layouts and profile schema 1/2 remain readable. Derived saved
coordinates are untrusted; calculation runs again. Three-column maximum,
single-sheet quantities, short-edge feeding, bottom alignment and horizontal
centering remain unchanged. All profiles remain physically unverified.
