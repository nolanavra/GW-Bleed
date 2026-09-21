# PDF migration evidence — development milestone

Date: 2026-09-18. Runtime: Windows x64 / CPython 3.13.0.

- All 90 original regression tests passed against the new runtime before the old
  PDF dependency was removed. Those export checks used the former independent
  PDF implementation to inspect the new output.
- Current suite: 105 tests, zero skips, passed in an isolated environment with
  no PyMuPDF/fitz installed. Final run: 64.683 seconds.
- Installed the built 0.5.0a1 wheel into that environment. Verified imports came
  from site-packages, bundled machine resources loaded, and the PDF worker ran
  with a temporary working directory outside the source checkout.
- Verified physical dimensions, stock clipping, both stock sizes, layout rotations,
  all source rotations, UserUnit, text/vector/image preservation, transparency,
  form appearances, explicit rejection of unsupported appearances, spot colors,
  overprint settings, output-intent metadata and hidden-layer defaults.
- Verified finishing lines and marks against engine coordinates and independently
  decoded exported barcodes with ZXing.
- Verified atomic-save failure cleanup, source protections, changed output-file
  preservation, worker abort, input limits, and imported approval downgrading.
- Visually inspected migrated UI and representative combined imposed PDF.

Evidence locations (local): build/migration-baseline.log,
build/clean-environment-tests.log, build/final-tests.log,
build/release-evidence/, build/project-wheel/, build/source-release/.

Limits: these checks are not a print-RIP certification, complete malicious-PDF
security assessment, Windows installer qualification, or physical machine trial.
The public/production release gate remains closed. Actual maximum memory limits,
full recovery UX, managed policies, accessibility qualification, signing, and
MSI/MSIX delivery remain future implementation work, not completed features.
