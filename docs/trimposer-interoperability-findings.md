# Trimposer interoperability: initial static findings

Inspected 2026-09-19. Scope: job storage, exported binary format, and machine
communication clues. No supplied executable or installer was executed, no machine
connection was attempted, and no licensing controls were changed. Proprietary
binaries, images, jobs, and machine settings have not been copied into the app.
These findings are not an implementation or production compatibility claim.

## Evidence examined

- Installed `SCCJobManagementSystem.exe` and its PE import table.
- `data/Version.ini`: reports 2.07. Supplied installer is named 2.06; they should
  not be assumed identical.
- 19 `MachineParameterFile_<number>.ini` job files.
- `data/Export.bin`: 8,756 bytes, matching all 19 job numbers and names.
- `MachineLimitParameterFile.ini`, localization strings, and machine-status log.

## Saved jobs: established structure

INI jobs use section `[MANULE_JOB_PARA]` (spelling intentional). They contain
job number/name, unit selection, sheet dimensions and thickness, operation-enable
flags, registration offsets, speed grade, crease level, and operation arrays.
The examined INI dimensional values are consistent with millimetres, including
jobs with `m_UnitType=1`; that flag does not imply their stored numbers are inches.

Examples of fields: `m_Paper_Width`, `m_Paper_Height`, `m_Paper_Thickness`,
`m_CutNum`, `m_p_CutPos_Arry[i]`, `m_SlitNum`, `m_p_SlitPos_Arry[i]`,
`m_CreaseNum`, `m_p_CreasePos_Arry[i]`, `m_Locator_Offset_Hor`, and
`m_Locator_Offset_Ver`.

Partial vertical perforation has a tool-position array, per-tool segment counts,
and a flattened endpoint array. The Coupons sample uses blocks starting at
indices 0, 50, 100, 150. Each block contains alternating start/end positions.
Do not infer identical machine firmware capacities from this desktop storage.

## Export.bin: strongly supported layout

The sample begins `55 AA 13 00` followed by 12 zero bytes. A 16-byte header plus
19 records of 460 bytes accounts for the entire file. Header bytes 2–3 are
consistent with a little-endian record count of 19, but another export is needed
to establish header semantics and whether reserved bytes can vary.

Offsets below are relative to the start of each record. Numerical fields match
unsigned little-endian 16-bit words. Measured positions in this particular export
are consistent with thousandths of an inch, not micrometres or millimetres.

| Offset | Interpretation | Evidence / limitation |
|---:|---|---|
| 0 | Job number | All 19 records match INI job numbers |
| 2–33 | Job name slot, apparently 32 bytes | ASCII names match; non-ASCII encoding untested |
| 34 | Likely unit selector | Observed value 1; semantics not proven |
| 36 | Sheet length | All 19 match INI length converted to 0.001 in |
| 38 | Sheet width | All 19 match converted INI width |
| 40 | Stock thickness | All 19 match converted INI thickness within rounding |
| 42 | Crease level | Consistent with samples; controlled variation needed |
| 44 | Horizontal registration offset | 11 samples with corresponding INI key match |
| 46 | Vertical registration offset | 11 samples with corresponding INI key match |
| 48–59 | Six slitter-position words | 114 comparisons, maximum difference 0.213 thousandths inch |
| 60–63 | Unresolved | Do not populate speculatively |
| 64–127 | 32-word cut-position region | 89 populated comparisons, max difference 0.465 thousandths inch |
| 128–191 | 32-word crease-position region | 44 populated comparisons, max difference 0.426 thousandths inch |
| 192, 256, 320, 384 | Probable four 64-byte strike endpoint blocks | Coupons endpoints match all four blocks; full corpus validation pending |
| 448–457 | Unresolved | Do not populate speculatively |
| 458–459 | Variable trailing word | Possible integrity field; algorithm unknown |

Common reflected CRC-16 polynomial A001 with initial values FFFF and 0000,
covering the first 458 record bytes, matched none of the 19 trailing words.
This rules out only those exact hypotheses, not CRCs in general.

Zeros can occupy intermediate slitter slots in the saved data. An importer must
retain slot order and raw values until their semantics are verified; it must not
automatically pack nonzero entries into different slots.

## Communication: clues, not yet a protocol

The executable imports Winsock by ordinal. Resolving these against the local
Windows `ws2_32.dll` export table identifies `socket`, `sendto`, `recvfrom`,
`setsockopt`, `inet_addr`, byte-order conversion functions, `WSAStartup`, and
`WSACleanup`. This is consistent with datagram networking, but it does not prove
that these calls carry machine commands or establish the socket type, port,
packet framing, acknowledgements, discovery, or retries.

USB functions include SetupDi device-interface enumeration, `HidD_GetAttributes`,
`HidP_GetCaps`, `HidD_GetFeature`, and `HidD_SetFeature`. The UI includes USB
Connection/USB Status strings, but also USB encryption-card error strings.
Some HID code may therefore serve a licensing device. Do not equate HID imports
with the machine interface without tracing their callers or capturing activity.

The log records connected/unconnected states and specific machine conditions,
including empty paper, open waste-bin door, and full card collector. It confirms
that status reporting exists, but contains no packet capture or transport mapping.

## Best next experiments

1. Export a tiny baseline job and separate copies changing only job name, unit
   selection, one cut, one slit, one crease, and each strike tool's position or
   endpoint. Include an export in millimetre display mode. Keep the corresponding
   INI files. Compare header, reserved words, and trailing word changes.
2. Confirm which installed machine/model/firmware produced the supplied data and
   whether the PC connection is USB, Ethernet, or both; identify any separate
   licensing dongle.
3. With the real software operated normally, obtain a passive capture of connect,
   status polling, and sending one harmless test job on an idle machine. A network
   capture or USB capture must be chosen after confirming the actual interface.
   Do not replay guessed commands or run production equipment from this analysis.
4. First build an offline diagnostic decoder and validate it against these
   controlled examples. A machine-writing exporter must wait for checksums,
   unit behavior, reserved fields, and tool ordering to be established.
5. Implement communications separately from the production layout engine only
   after protocol and machine-specific validation. Keep proprietary implementation
   code and licensing mechanisms out of GW Bleed.

The current evidence supports a useful offline import investigation now. It does
not yet support a reliable machine-program writer or a machine connection driver.
