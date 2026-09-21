# GW Bleed internal Windows alpha

This unsigned portable build is for controlled internal testing, not production.
Machine profiles, manual aliases, crease calibration and Trimposer interchange
remain unverified. Do not disable Windows security controls to run it. Report a
security-policy block to the project owner.

Extract the entire ZIP into a new folder and launch **GW-Bleed-Alpha.exe**.
Keep the DLLs and resource folders with it. Python, Qt and developer tools are not
required. For an update, extract into a different folder; do not overwrite a
running build. Removing an old application folder does not remove your documents
or stock profiles. User stock profiles remain in the existing per-user Windows
application-data location, under GW Bleed (`paper-stocks.json`).

Open the synthetic PDFs and JSON jobs in `samples`. They contain generated test
artwork only. Saved JSON uses relative PDF paths, so keep the samples together.
Use Save As to write test results to your Documents folder. A PDF viewer is needed
to open bundled manuals; lack of a viewer must give a useful error.

## Clean Windows acceptance (must be performed, not inferred)

Record Windows edition/build, display scale, user privilege, ZIP SHA-256 and
About/build identity. Use a fresh Windows 11 x64 VM without Python, Qt, compilers
or the source checkout. Disconnect networking after transferring the ZIP.

- Launch from Explorer and another working directory as a standard user.
- Open both source pages; switch Card/Sheet view, alternatives, overlays and theme.
- Select a stock; edit gsm, measured thickness and all four printing margins.
- Export all three PDF modes. Check sheet dimensions, artwork, both L-mark arms,
  ordinary registration marks, finishing and barcode. Keep samples of the output.
- Save/reopen a project, open the machine guide, and save a supported Trimposer INI
  job from the plain sample. INI barcode/unsupported finishing remains unavailable.
- Open a bundled manual through the default viewer, or verify the missing-viewer error.
- Test spaces and Unicode in paths, 100% and 150% scaling, and light/dark themes.
- Test a corrupt/missing PDF, cancellation and an unwritable destination. Existing
  source/output files must survive and the application must remain responsive.
- Extract another copy beside this one and verify user stock settings persist.
- Confirm preview/export create no stray application windows or console flashes.
- Remove the old extracted folder and verify customer documents remain intact.

For defects, record build identity, steps, expected/actual result and screenshots.
Share generated examples where possible; do not attach customer artwork without
permission. Report findings to the project owner through the existing internal
channel. No public support address or response-time promise is implied.

Fill in `clean-windows-acceptance.json` alongside the build evidence. Its initial
status is **pending**. Developer-machine worker tests do not satisfy this gate.
