# Trimposer job saving

Select a current layout and choose **Save Trimposer job (.ini)…**. The suggested
filename is `MachineParameterFile_<job number>.ini`. The job number (000–999)
comes from Layout settings and is retained in saved projects. Speed grade is
always 4, without a prompt. Crease level is mapped automatically from the selected
paper's physical thickness: minimum machine thickness maps to 1 and maximum to 5,
with half-up rounding between them. When the mapping is unavailable, level 2 is
used as the project owner's requested placeholder and labelled in the interface.
Measured paper thickness is still required for INI export. A thickness outside
known machine limits remains an error rather than using the placeholder.

The writer uses the observed `[MANULE_JOB_PARA]` section, exact field spelling,
ASCII text, CRLF line endings, and millimetre-valued dimensions. The unit flag is
1, matching the supplied inch-display examples whose INI values remain in mm.
It exports the selected alternative, not an independently calculated placement.
Geometry is revalidated before serialization. Saves use a verified temporary
file followed by atomic replacement.

Supported fields cover sheet dimensions/thickness, single-sheet count, job name,
cuts, six slitter slots, creases, dedicated registration offsets, and up to four
strike tools with separate start/end segments. Outer slit entries occupy slots
0 and 5, following the supplied examples; unused inner positions remain zero.
Review that ordering against the target Trimposer version and machine.

Cross/rotary-perf position fields and barcode job-selection semantics are not
established by the supplied sample set. Such jobs are blocked from this export
rather than silently losing requested operations. Non-ASCII names and names
longer than 31 characters are also blocked pending encoding verification.
Unused reverse-crease/fold/sniper flags are off. Secondary crease level is 1,
as in the supplied examples; reverse creasing is off.

This is an **unverified offline exchange writer**. Check the saved job inside
Trimposer before machine use. Matching the observed file structure does not
establish full application or firmware compatibility. No program is sent to
equipment by saving the file.

Use **Save GW Bleed project…** to preserve artwork references, profile snapshots,
preview/export settings, and editable layout inputs. Trimposer INI is not a
replacement for that full project data and cannot yet be reopened by GW Bleed.

Per the project owner's direction, `.bin` generation and transfer are reserved
for a future machine-communication feature. This release does not produce
binary machine programs. Resolve remaining binary fields and integrity checks
and complete equipment validation before implementing that feature.
