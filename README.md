# GW Bleed — 0.5 development alpha

A local Python desktop prototype for single-design rectangular repeat grids.
The calculation engine remains dependency-free. The optional desktop interface
uses PySide6, pypdf for vector PDF composition, and PDFium for preview and appearance flattening. Python 3.11+ is required; release testing uses Python 3.13 x64.

## Release status and licensing

Project-owned code: Apache-2.0, copyright Graphic Whizard inc. Dependencies and
branding have separate terms; see LICENSE, NOTICE and THIRD_PARTY_NOTICES.md.
Official distribution/support may be paid; no activation or feature gates exist.
This is an unvalidated development alpha. All six machines, security review,
enterprise installers and pilot evidence are required before version 1.0.
See [phase status](docs/release-roadmap.md) and [release checklist](docs/release-checklist.md).

For a pinned Windows development environment (use `requirements-windows-cp313.hashed.lock` with `--require-hashes` for reviewed Windows x64 Python 3.13 wheel hashes):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.lock
.\.venv\Scripts\python.exe tools/run_tests.py
.\.venv\Scripts\python.exe tools/dependency_inventory.py
```

Start with `python desktop.py`; worker mode is available in source and standalone
entry points. `tools/Build-Standalone.ps1` defines the development packaging path;
a compiled build and clean Windows installation must be verified before publishing.
`tools/release_gate.py` intentionally fails while external approvals are missing.

## Desktop

Double-click **Launch GW Bleed.bat**. The local `.venv` already contains the
desktop dependencies on this workstation. To set up a new checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[desktop]"
.\.venv\Scripts\python.exe -m gw_imposition.gui
```

Select a PDF, choose a source page, enter finished dimensions in inches,
select a machine and click **Calculate layout**. The desktop calculates
left/right bleed as (PDF width - finished width) / 2 and top/bottom bleed as
(PDF height - finished height) / 2, assuming centered trim. The displayed CropBox
dimensions include PDF page rotation; they do not prove artwork fills the bleed.
Negative differences are rejected. Unequal horizontal/vertical bleed is supported
and swaps axes when artwork rotates. Choose a row in the alternatives
table to inspect that layout. Scroll or use **Zoom + / Zoom −**, drag to pan, or
click **Fit**. Choose **Card** to inspect one piece with its trim/bleed boundaries,
or **Sheet** to inspect all placements. Card view uses the selected layout's
rotation; before calculation it shows the source orientation and entered trim.
Save layout JSON records the selected alternative and source path/page.
Changes to inputs invalidate old results, preventing stale exports.

**Load layout…** reopens a saved schema-3 or schema-4 JSON layout, restoring dimensions,
gutter, source page and the saved machine-profile snapshot. If the source PDF
has moved, a file picker lets you locate it. The app recalculates all geometry
and bleed using the current PDF, then restores the saved stock/rotation/grid
when still valid; otherwise it shows the new recommendation. Saved coordinates
are never used as authoritative results. Unsupported or malformed layouts show
an error. Schema-3/4 layouts and schema-1/2 machine snapshots remain supported.
Zero-gutter layouts require a supporting profile and zero bleed. Loaded profiles are labeled with their saved version.

Use the **Theme** selector in the header to switch between **Dark** and **Light**
at any time. The app starts in Dark mode; the choice applies to the current session.
Switching themes preserves the job, selected layout, preview layers and zoom/pan.
Dark uses charcoal panels and light text; Light uses pale panels and navy text.
The header displays the
supplied Graphic Whizard SVG transparently, preserving its original colors.
Interface accents match
its navy blue (#004B7F) and green (#B3D485); cut/slitter overlays retain their
distinct red/purple meanings.

The preview repeats the selected PDF page over each placement including bleed,
respecting PDF page rotation and layout rotation. **Show PDF in preview** is checked
by default; uncheck it for geometry only. Cuts and slitters remain visible above
the artwork. Independent **Cuts**, **Slitters**, **Bleed**, and **Machine bounds**
checkboxes are enabled by default. Toggles preserve zoom, pan and selected layout;
changing view or selecting another layout fits the view automatically. Machine
bounds apply to Sheet view only. Placement details report rotation, oriented
bleed and distances from the outer bleed to all four sheet edges, in inches.
Raster rendering is limited to 1,600 pixels on the longest edge;
it is for preview only and is never used as production export artwork.

## PDF export

Select a valid layout and click **Export PDF…**. Choose **Artwork only** (default),
**Finishing lines only**, or **Artwork with finishing lines**, then choose a
destination. Each export contains one page at the stock's physical dimensions.
Artwork is placed from the original PDF content at its original scale, including
the selected CropBox and source/layout rotations. Fonts, images and vectors are
retained rather than rasterizing the sheet. Annotation/widget appearances are
flattened into page content. No color conversion or PDF/X certification is applied.

Cuts/slitters are solid black 0.25-point lines spanning the whole sheet. Bleed
guides, machine shading, arrows and branding are excluded. Preview visibility,
view mode and theme have no effect on PDF exports. MediaBox, CropBox, TrimBox,
BleedBox and ArtBox match the selected stock dimensions. A page-level clipping
path also prevents any content or stroke from painting outside that stock. Print at actual size (100%), not fit-to-page.

Exports run in a separate process with the job controls temporarily locked.
**Cancel** stops the worker and discards the staging file. The app verifies output
and checks that the source has not changed before atomically replacing the chosen
destination. A source PDF cannot be overwritten. Failures preserve existing output
files and job inputs. Dummy-profile exports are for testing until real profiles
and physical print/finish trials have been approved.
PDF inspection and rendering run in an isolated background process. Loading
status is visible and calculation waits for a valid source. Switching pages or
files discards obsolete results. The cache retains at most eight pages / 32 MiB
of PNG data for the current source. Its key includes resolved path, modification
time and file size; changing a source clears the cache and invalidates results.
The app checks for source changes every second and before calculation/JSON save.
Unreadable, missing, corrupt or encrypted files show an error while preserving
entered dimensions; select the file again to retry. No PDF data is uploaded.
Password-protected PDFs are rejected; PDFs are limited to 1,000 pages for inspection.
The desktop currently uses inch inputs and bundled machines; the CLI additionally
supports millimetres, custom profiles and explicit shared-cut mode.

Run all tests, including desktop integration checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Qt/PDF implementation references: [Qt graphics view](https://doc.qt.io/qtforpython-6/overviews/qtwidgets-graphicsview.html)
and [pypdf page transformations](https://pypdf.readthedocs.io/en/stable/user/cropping-and-transforming.html).

## Run

From this folder in PowerShell:

```powershell
python -m gw_imposition --width 3.5 --height 2 --bleed 0.125
python -m gw_imposition --width 3.5 --height 2 --bleed 0.125 --output layout.json
python -m gw_imposition --width 85 --height 55 --units mm --bleed 3
python -m gw_imposition --width 3.5 --height 2 --machine demo_scc_2
python -m gw_imposition --width 3.5 --height 2 --machine demo_scc_3
python -m unittest discover -s tests -v
```

Tests also run with pytest if installed (`python -m pytest`). No installation is
needed to run from the repository. `--help` lists options. CLI exit codes: 0 for
valid layouts, 1 for no layout, 2 for invalid inputs or file errors.

## Included

- Immutable job, stock, machine, placement and result models.
- Decimal-to-integer unit conversion, rounded to nearest micrometre (half up).
- Versioned JSON profiles with press and finisher margins.
- Both card rotations with short-edge sheet feeding only (12-inch or 13-inch edge).
- All row/column combinations within geometry and configured grid limits.
- Stable maximum-yield ranking, alternatives and rule-specific exclusions.
- Trim placements, bleed regions, unique cut coordinates, pieces per sheet and waste.
- JSON result export including job inputs and complete profile snapshot.
- Synthetic regression, boundary, CLI, and geometry-invariant tests.

## Geometry contract

All model/JSON dimensions are integer micrometres. One inch = 25,400 um.
The sheet origin is top-left in feed coordinates; x runs across the feed and y
runs away from the lead edge. Short-edge feed makes the shorter stock dimension
the across-feed width. All sheets feed on that edge: 12 inches for 12 x 18 stock,
13 inches for 13 x 19 stock. Long-edge feeding is rejected when loading profiles;
`feed_edges` must be `["short"]`. Artwork may still rotate 90 degrees within the
fixed sheet orientation. Margins are already expressed in this coordinate system.
The usable area intersects press and finisher exclusions by taking the maximum
margin on each edge. Layouts center the grid including outer bleed horizontally
on the sheet, with left/right empty margins equal to within one micrometre.
The grid's bottom bleed edge sits at the bottom usable boundary (sheet height
minus the larger press/finisher trailing margin). A candidate that violates any
machine margin is rejected, not shifted horizontally off center.

Width and height mean finished trim. Bleed is symmetric on opposite edges but
may differ between axes. `bleed_um` is left/right and `bleed_y_um` is top/bottom
before artwork rotation; omitted `bleed_y_um` uses `bleed_um` for CLI compatibility.
Gutter is the distance between neighboring trim edges, not extra space beyond
their bleeds. Non-shared layouts require a positive gutter >= twice the larger bleed.
Required grid width = columns * trim width + (columns - 1) * gutter + 2 * horizontal bleed;
height follows the same rule with vertical bleed. This avoids double-counting internal bleed.
PDF-to-trim half differences round outward to a whole micrometre.

If gutter is omitted, the CLI picks the smallest allowed positive setting that
accommodates the bleed. Machine settings lie on minimum + n * increment.
Shared cuts require `--shared-cut`, explicit profile support, zero bleed and zero
gutter; only then is the normal gutter range bypassed. No artwork-based shared
bleed inference is attempted.

Each candidate represents exactly one sheet. Piece quantity is calculated as
rows * columns from the sheet size, finished size, bleed, gutter and machine
constraints. There is no order quantity or overs input, or run-length calculation.
Waste area is whole-sheet area minus finished trim area (including bleed, margins
and gaps as waste). It is not the unused area outside the grid.
Result JSON uses schema version 4; new machine profiles use schema version 2 (legacy version 1 still loads).

Ranking: pieces per sheet descending, stock dimensions ascending (width then height),
stock ID, then rotation and grid identity. The UI uses this same ordering. Unavailable stock
is excluded. This is a maximum-yield policy, not a minimum-cost optimizer.

All trim operations run across the entire sheet: vertical lines are **slitters**
from y=0 to sheet height; horizontal **cuts** run from x=0 to sheet width.
JSON includes `slitter_x_um`, `cut_y_um`, and explicit `slitters` / `cuts` endpoints.
The diagram draws purple slitters and red cuts across the whole sheet.
These coordinates are not executable machine commands,
tool sequences or production drawing marks. Profiles currently constrain margins,
gutters, feed direction and grid sizes only. Grid-limit rejections summarize the
excluded larger grids rather than listing every excluded row/column combination.
Search is bounded to 50,000 candidates / 1,000,000 total placements and fails
explicitly rather than returning a partial recommendation.

## Machine profiles and remaining discovery

All machines have a maximum of **3 columns across the sheet**. Profiles may set a
lower limit, but values above 3 are rejected. Artwork rotation does not change
which axis counts as columns.

Six spreadsheet-defined machines are selectable: **PT 33SC**, **PT 331SCC**,
**PT 331SCC AIR**, **PT 335SCC B Multi**, **PT 8336SCC Multi** (default), and
**PT 9375SCC Supercut**. See the **Machine specs** tab for source values and
provisional settings. CLI IDs are `pt_33sc`, `pt_331scc`, `pt_331scc_air`,
`pt_335scc_b_multi`, `pt_8336scc_multi`, and `pt_9375scc_supercut`.
Use `--machine` or `--profile path-to-profile.json`; they are mutually exclusive.

The profiles enforce input paper limits, minimum finished dimensions in feed
coordinates, six slitters, and supported finishing operations. Linear perforating
maps to rotary perf. Strike-perf support on the 8336/9375 requires the optional
attachment. Profiles remain unverified because the workbook omits setup margins
and detailed tooling constraints. Weight, speed, sensor and crease-tool details
are retained as reference specifications, not automatically checked job inputs.

Fixed-gutter models accept interchangeable **0 mm or 5–15 mm middle gutters**
per the user's clarification. Enter gutter `0` for shared cuts only with zero
PDF bleed. The current owner-approved development profiles have no enforced side-trim
maximum (`max_side_trim_um=null`). The engine still supports an explicit maximum,
including the previous 3 mm setting, when a validated configuration supplies it.
Nonzero gutters need room for both adjacent bleeds. Variable models retain the
provisional 0.125–1 inch range until verified travel limits are supplied.

Existing press margins (0.5-inch lead and 0.25-inch on the other edges) remain
provisional; they are not workbook specifications. Fixed-gutter machines have
zero minimum finisher side margins. If a custom profile imposes a 3 mm maximum,
the provisional 6.35 mm press margins conflict and the engine rejects the layout.
Finisher lead/trail margins and variable-machine margins remain provisional. Only the existing
12x18/13x19 stock is offered. The 40-inch hand-fed reference has an inconsistent
104 cm conversion in the workbook; it is preserved as reference, not enabled.

Machine profile schema 2 adds source cells, a workbook hash and capabilities.
Saved schema-1 machine snapshots and the original demo JSON fixtures still load;
the dummy profiles are no longer listed as production models. The existing
24-piece regression remains a geometry test, not a physical machine approval.

Copy the sample JSON and use `--profile path-to-your-profile.json`. Keep profiles
unverified until production staff have confirmed their settings. Update profile
versions whenever constraints change. See [the discovery worksheet](docs/phase-one-discovery.md).

Still required before production use: actual machine dimensions and tolerances,
tool/lane/position rules, permitted feed/stock combinations, finishing pass logic,
press/RIP output requirements, and an approved physical golden-job corpus.
The `approved` label is descriptive metadata, not automatic certification.

Next phases add setup reports, actual machine-rule validation, physical pilot
testing and standalone Windows packaging.
Folds, duplex, arbitrary nesting and automatic machine programming
are not implemented. Selected PDFs are inspected locally and never modified.

## Creases and perforations

Use the **Finishing** tab in the right column to add operations on the finished card, in inches.
The engine repeats these across each layout. Crease and cross-perf positions are
measured from the card top; strike and rotary positions from the card left.
Strike start/end distances are measured from the card top.

Creases and cross perfs span the sheet parallel to its leading edge and cannot
coexist. Rotary perfs span the full sheet length. Strike perfs have partial-length
segments, with at most four distinct tool positions across the imposed sheet.
Coverage above 60% of sheet length at any strike tool produces a solenoid-burnout
warning; overlapping segments count only once. This is a warning, not a block.

Finishing directions are tied to the unrotated card. Layout rotations that would
put an operation in an unsupported direction are excluded. Adding finishing can
therefore change the recommended arrangement and pieces per sheet.

The preview has a finishing overlay toggle. Card view shows the first card's
finishing after calculation. Layout notes list sheet coordinates and warnings.
PDF line/combined exports include black 0.25-point guides: solid cuts/slitters,
dash-dot creases, and dashed perforations. Artwork-only exports omit finishing guides; enabled registration marks are included independently.
Saved schema-4 layouts preserve finishing; schema-3 layouts still load with none.
Actual machine positioning, tool spacing and programming still require validation.

### Common finishing presets

The right column has **Stock layouts**, **Finishing**, and **Registration marks** tabs. Finishing stays
inside the main window. Choose a preset, review its card diagram and positions,
then click **Apply finishing** to replace the job's finishing and recalculate the
sheet. Editing a preset is a draft until applied; save/export use the applied job.

- **Half fold:** one center crease.
- **Accordion fold:** equal thirds, with two creases.
- **Letter fold:** two equal main panels and one shorter tuck panel. The default
  allowance is 1/16 inch, adjustable; choose top or bottom for the tuck panel.
- **Gate fold:** creases at one-quarter and three-quarters of card height.
- **Ticket stub:** a 2-inch strip by default, with adjustable size. Choose the
  right edge for rotary perf or bottom edge for cross perf.
- **Coupons:** a 2-column by 3-row grid within each finished card by default.
  Rows use cross perfs; columns use full-sheet rotary perfs. Counts are editable.
- **Tent fold + strike perf:** a center crease plus two strike segments on the
  vertical centerline, top-to-center and center-to-bottom. These join across the
  card but leave inter-card gaps on the sheet; both lengths count toward coverage
  at the same tool position. Either half alone can also be selected.
- **Advanced — custom settings:** editable operation rows with position, and
  start/end distances enabled only for strike perfs. Switching from a preset
  copies its draft positions into the advanced editor for adjustment.

Crease preset fractions refer to finished card height before rotation. Presets
refresh when card dimensions change; apply again to update the job. Saved layouts
preserve exact applied operations and reopen under Advanced (or No finishing),
without a schema change. Strike-coverage warnings also appear in the Finishing tab.

### Registration marks

The **Registration marks** tab generates solid-black rectangles for the selected
layout on every machine, using that profile's printable press margins. Defaults
are **0.02 inch thick × 0.125 inch long**, with zero gap from the outer artwork
bleed boundary. Thickness, length and gap are adjustable.

Marks are outside the artwork grid in gutter/waste space. Cut marks sit at its
left/right sides; slitter marks sit above/below it. One rectangle edge lies
exactly on the cut/slitter coordinate, and thickness extends only toward the
gutter, never across the cut into finished artwork. Internal gutter strips are
limited to half the gutter so opposite boundaries remain distinguishable. Shared
cuts with zero gutter receive no gutter mark.

Marks are shortened to printable space or omitted when no space remains. The
tab and export dialog report these cases. With the current provisional margins, the
artwork meets the printable trailing boundary, so bottom marks are omitted.
Marks never reposition the layout or expand the PDF page.

**Include registration marks in exported PDFs** is on for new jobs and adds
marks to all three export modes. **Show registration marks in sheet preview**
is a separate visibility control and does not affect export. Settings update
immediately and are captured when export starts. Saved schema-4 layouts preserve
them in optional registration metadata; older saved layouts without that field
load with marks disabled, preserving their prior output behavior.


### Barcodes

The Registration marks tab shows barcode controls only for profiles with a
barcode reader: PT 8336SCC Multi and PT 9375SCC Supercut in the supplied spreadsheet.
Enable generation, enter a value (leading zeros are preserved), and choose Code 128
or Code 39. Code 128 includes its required checksum; Code 39 uses no optional checksum.
The spreadsheet does not specify the reader format, job-value protocol or scan position;
confirm these on the machine before using barcodes for job recognition.

Barcodes are vector rectangles in all three PDF export modes. Automatic placement
uses clear printable waste above the artwork; manual positions are measured from
the sheet's top-left corner and include the blank quiet zone. The app reserves ten
narrow-bar widths on each side and rejects overlap with artwork, marks, finishing
lines or printable margins. If a barcode cannot fit, export is disabled until its
settings or the layout are corrected. Placement geometry is unchanged.

Barcode settings are saved with registration settings. Switching to a machine
without a reader disables barcode generation. Card view omits sheet barcodes;
hiding preview layers does not alter PDF output. Install the updated desktop
extras to obtain python-barcode; test extras include an independent barcode decoder.


## PDF migration and limits

The current runtime and tests do not import PyMuPDF. pypdf normalizes physical
page coordinates (including CropBox, rotation and UserUnit); PDFium renders
previews and flattens supported appearances. Vector artwork is reused as a Form
XObject. Visible annotations/forms without supported appearances fail explicitly;
flatten those documents in the source application first. No whole-page raster
fallback is used. PDF/X, color conversion and RIP fidelity certification remain
outside current claims.

Limits: 256 MiB source, 1,000 pages, 14,400-point physical page sides, 1,600-pixel
preview, 30-second preview worker and 120-second export worker. JSON layout reads
are bounded at 16 MiB and profile files at 1 MiB. Limits may reject complex valid
files. Process isolation is not an OS security sandbox. Memory controls, recovery
UX and independent security review are not yet complete.

Layout writes use a same-directory temporary file and replacement. Export checks
whether the destination changed after export started; changed destinations are
preserved and require another export decision. Network filesystem durability and
remaining race windows require enterprise qualification.

The owner confirmed retaining the current fixed-profile side-limit override:
`max_side_trim_um=null` on the first three profiles. This means no side maximum
is currently enforced there, regardless of older reference notes. Profiles remain
unverified. Imported `approved` flags are downgraded to unverified until an
authenticated validated catalog exists.
