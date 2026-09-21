# Bleed handling and two-sided artwork

The Artwork box offers three modes:

- **Keep bleed separated:** gutters must accommodate both adjacent bleeds.
- **Overlap bleed:** full artwork is placed at its original size. Where bleed
  overlaps, later placements paint over earlier placements.
- **Trim bleed at gutter midpoint:** each placement is clipped halfway through
  the adjoining gutters. Finished-card content is not scaled or cropped away.

Sheet-edge printing margins and machine gutter constraints still apply. The
engine reserves outer bleed space. Bleed is measured from PDF page dimensions
and centered finished dimensions; it does not prove artwork covers that space.

Select the front PDF and page, then choose **Back from same PDF** or **Back from
another PDF**. Each side has an independent page selector. A missing second page
is an error, not an instruction to silently repeat page one. **Front only** keeps
the original single-page workflow.

Back placement defaults to a left/right mirror of front positions. **Back: same
positions** is also available. The artwork itself is never mirrored. Verify the
printer's duplex feed orientation with a test sheet. Front and back must each
contain the specified finished-card dimensions; different available bleed is
supported by reserving the larger bleed on each axis and centering each source
without scaling.

The Front/Back selector beside Card/Sheet changes the preview only. Export emits
front first and back second at the same stock size in all three export modes.
Finishing positions follow the selected back alignment. Reader marks remain
anchored to the machine's sheet-edge conventions and are generated for each side.
Both source files are rechecked before publication and protected from overwrite.

Saved GW Bleed projects retain source paths, page selections, bleed mode and
back alignment. Trimposer INI files do not embed either PDF. Machine-programming
guidance remains based on the front sheet geometry.
