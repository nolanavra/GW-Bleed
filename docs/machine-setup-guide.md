# Machine setup guide

Calculate and select a layout, then choose **Machine setup guide…** next to
Save layout / Load layout / Export PDF. The guide supports PT 331SCC AIR,
PT 335SCC B Multi, PT 8336SCC Multi, and PT 9375SCC Supercut. PT 33SC and
PT 331SCC do not yet have supplied screen workflows.

The guide replaces the layout work area inside the main window. **Back to
layout view** in the main header restores the layout without closing the application.
Job name is entered in **Layout settings**. Thickness comes from the selected
paper profile. Crease depth is calculated linearly from the machine's physical
minimum thickness (1) to maximum thickness (5), rounded half-up to an integer.
Out-of-range thickness is rejected. Unknown physical limits use the owner's
placeholder depth 2, labelled in the guide and INI summary; paper weight in GSM
is not converted to caliper. The embedded guide has no input form,
leaving more vertical room for the machine screen. Next opens
the strike-perf table even when no strike operations are planned; unused pairs
show zero. The crease reference likewise shows unused fields when no crease or
cross-perf positions are planned.

The **Paper stock** tab provides a stock-profile dropdown plus New/Edit controls.
Profiles contain sheet dimensions and measured thickness. Selecting one updates
the machine-setup thickness and recalculates using that sheet size. Machine
limits still apply, including short-edge feed and three columns maximum.
**Automatic** retains the machine's available sizes. The supplied size templates
have no assumed thickness; enter a measured thickness when editing them.
Custom profiles are stored in the user's application-data folder and the selected
profile is embedded in saved jobs. **Advanced view** reveals the alternative
layout chart; otherwise the selected stock's recommended layout is used.

Enable **Generate dedicated machine registration mark** in Registration marks
to populate the two page cells below crease depth. The first is distance from
the leading paper edge to the mark's top edge; the second is distance from the
right paper edge to the mark's right edge. Reader-equipped machines use two
perpendicular rectangles, at least 5 mm long and 0.4 mm thick, wholly inside
the 3–20 mm top-right corner region. It is omitted with a warning if it cannot
fit without overlapping other content or printable margins. Disabled/unavailable
marks show no numeric guide position. See [machine reader artwork](machine-reader-marks.md)
for barcode and L-mark dimensions and coordinate conventions.

Enter measured thickness in the paper profile and optionally name the job in
Layout settings. Crease depth is derived from that thickness and the machine's
physical limits, never from the PDF. Save the layout JSON to retain the paper
profile and job name. Legacy depth values are readable but are not reused as
automatic depths. Acknowledgements are never saved.

Use the step list or Previous/Next step buttons. Category buttons open read-only
numbered entries; Home/Return show the parameter overview. On the strike table,
select a column header to see that tool's entry screen. Keyboard users can Tab to
controls, use arrows in tables and the step list, and press Space on buttons.
The highlighted cell's explanation appears below the screen as well as in its
tooltip. The keypad is a visual reference; use the real machine to enter values.

The guide uses the selected alternative. Slitters and sideways perf positions
are measured from the right paper edge. Cuts, crease/cross-perf positions, and
strike starts/ends are measured from the leading edge. Values use decimal
half-up rounding to three decimal inches. Precision collisions block step
confirmation; the guide does not change geometry to accommodate them.

Strike columns are assigned rightmost first. Supercut tools 1–2 have automatic
sideways fields; remaining strike tools require physical positioning. Segments
remain separate, including touching segments. A zero start is valid. Only a
zero/zero pair represents an unused segment. Rotary perfs appear only in
physical tooling instructions and the final diagram, never program entries.

**Entered on machine** records an operator acknowledgement, not equipment
verification. Changing setup settings clears acknowledgements. Source, job,
machine, and layout changes invalidate the entire open guide; close and reopen
it from the new calculation. Preview/theme controls do not affect the values.
The guide has no machine communications and does not change PDF export,
barcodes, profiles, or layout ranking.

## Validation boundary

The drawings are references based on supplied screens and confirmed measurement
conventions. Machine entry capacities, firmware pagination, adjustments, feeder,
Test, and Run behavior remain unverified. Scrolling is application navigation,
not an instruction to use an unconfirmed firmware page. Follow the machine
manual and approved site procedures for installation, testing, and running.

An operator must compare a generated guide with each real machine/firmware
configuration before the workflow is validated. Record stock, configuration,
each entered value, results, and reviewer in the existing physical-validation
records. This feature does not satisfy the enterprise physical release gate.

## Engineering

`machine_guide.py` is a Qt-free immutable conversion layer. `machine_guide_ui.py`
renders those values. Production engine coordinates remain the only geometry
source. `machine_setup` is an optional additive saved-layout section; readers
that do not request it retain the existing six-value `read_layout` interface.
Regression coverage is in `tests/test_machine_guide.py`.
