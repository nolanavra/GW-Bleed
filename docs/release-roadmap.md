# Enterprise release status

## Agreed direction
Apache-2.0 project code; permissive PDF stack; paid official distribution and
optional support; no activation/feature locks. Windows 11 x64 first. Store MSIX
and direct signed MSI. All six machines require physical validation before 1.0.

## Phase gates
| Phase | Local implementation | Evidence still required |
|---|---|---|
| 1 Foundation | Local Git baseline/tag, license/notice files, CI definition, dependency locks/inventory tooling | Public repository identity, branch protections, clean hosted CI, packaged Qt license review |
| 2 PDF migration | pypdf + PDFium backend, vector export, tests without old dependency | Independent broader print corpus, spot/overprint/RIP and appearance edge-case sign-off |
| 3 Open-source alpha | Worker entry point, source build/package tooling | Public reviewed source, successful standalone build, clean Windows install |
| 4 Machines | Validation templates and unchanged unverified status | All six physical machines, firmware/tool records, tolerances, measured sheets, official catalog approval |
| 5 Reliability/security | Atomic layout saves, worker deadlines/output limits, destination-change check, bounded input | Memory/isolation assessment, recovery UX, independent security audit, network-storage/termination tests |
| 6 Enterprise | Deployment requirements documented | Signed MSI/MSIX, managed policies, accessibility/hardware testing, admin acceptance |
| 7 Pilot | Evidence templates | Three sites, all six models, at least four weeks, incident log/sign-offs |
| 8 Release | Fail-closed readiness check and release checklist | Publisher account, signing, private security contact, support arrangements, Store certification |

No phase is declared externally certified by source-code changes. Do not mark a
machine approved from spreadsheet data alone or disable constraints to obtain a
passing layout. A blocked PDF fidelity gate stops production qualification.

## Rights record
2026-09-18: project owner identifies copyright holder as Graphic Whizard inc.
and confirms permission to redistribute supplied logos and machine specifications.
The hosted repository and private security reporting contact are not supplied.

## Source publication
The local baseline contains pre-migration dependencies. Publish a reviewed clean
snapshot/initial history after rights/secret scans; do not push internal history
blindly. Generated screenshots and customer/sample PDFs are excluded from the
source-release allowlist. Code licensing is not a license for third-party assets.

## Concurrent profile edits
The owner explicitly confirmed keeping max_side_trim_um=null on the first three
fixed-gutter profiles during this migration. No side-trim maximum is currently
modeled for those profiles; this is not physical validation. Boundary tests use
explicit synthetic 3 mm constraints so the engine rule remains covered.

## Verified local evidence — 2026-09-18

- Internal baseline: `internal-pre-migration-0.4.0`; 90 original tests passed against
  the replacement backend before removing the old dependency.
- Migrated test suite: 105 tests passed with no skips in a separately created
  Windows Python 3.13.0 environment installed from pinned local wheels.
- No PyMuPDF/fitz in that environment; the old package was also uninstalled from
  the working development environment. `pip check` passed there.
- Independent ReportLab fixtures, PDFium image/text inspection, and ZXing barcode
  decoding cover vector export and finishing. Additional checks cover all source
  rotations, UserUnit, form appearances, spot colors, overprint, output-intent
  metadata and optional-content defaults. This is not RIP/physical certification.
- Built the 0.5.0a1 Python wheel and installed it in the clean environment.
  Machine resources and the PDF worker ran successfully outside the checkout.
- Visually checked the migrated dark UI and a representative imposed PDF with
  registration marks, barcode and full-sheet finishing lines.
- Source scan, dependency inventory/notice copying, and source snapshot tooling ran.
- Standalone packaging dry-run completed, with a missing-dumpbin warning.
  Nuitka compilation, MSI/MSIX creation, signing and clean-machine installer tests
  have NOT completed. Current Python patch/security status also needs release review.

Logs and local artifacts are in build/. They are development evidence, not public
releases or independent sign-offs. No remote repository was created or published.
