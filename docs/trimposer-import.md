# Load a Trimposer layout

Load the artwork PDF and enter its finished-card dimensions. Choose **Load
Trimposer job (.ini)…**. The selected machine and printing margins are used to
validate the imported sheet; the INI supplies sheet size, slitters, cuts, creases
and supported strike-perf positions. No equipment connection is made.

Card slots must match the current finished dimensions. The importer tries both
artwork orientations, keeps the original coordinates, and never scales artwork.
It rejects bleed overlapping adjacent artwork or extending beyond printing
margins, unsupported machine bounds, and unrecognized/unsupported operations.
The established six-slot slitter format is supported, including unused middle
zero slots. Irregular or ambiguous layouts are rejected instead of guessed.

Imported finishing replaces current card finishing. Registration and barcode
generation use GW Bleed controls, not the INI's reader settings. Review these
before output. The sheet size is displayed above the preview. **Use automatic
layout** exits fixed-coordinate mode. GW Bleed saves retain the imported INI
snapshot; reopening, recalculating and exporting revalidate the fixed geometry.
A failed import leaves the current layout unchanged. Binary jobs are unsupported.

# Quantity and preview controls

Enter total cards and a machine job number in Layout settings. Required sheets
are rounded up using the selected layout's pieces per sheet. Generated Code 39
contains the three-digit job number followed by the two-digit sheet count.
Barcode output is blocked above 99 sheets; no quantity is silently truncated.
Quantity does not change single-sheet placement geometry.

Barcode placement is automatic and mark sizes are not editable. **Flip
orientation** above Apply finishing alternates between 0 and 90 degrees relative
to artwork. **Rotate view** turns only the displayed card/sheet; PDF output,
machine measurements and finishing remain unchanged.
