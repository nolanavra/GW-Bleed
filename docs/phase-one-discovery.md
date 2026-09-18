# Phase-one production discovery worksheet

Status: implementation prototype started; production rule discovery remains open.
Confirmed feed rule: all sheets are short-edge fed, on the 12-inch edge for
12 x 18 stock or the 13-inch edge for 13 x 19 stock. No long-edge feeding.
Do not treat the bundled demonstration values as measurements.
Confirmed quantity rule: calculate pieces fitting on one sheet only. No user
quantity, overs, or number-of-sheets inputs/calculations.
Confirmed column rule: a maximum of 3 columns across the sheet for all machines.
Three dummy machine profiles are available with identical placeholder settings.

| Required input | Value / evidence |
| --- | --- |
| Production owner and machine operator | TBD |
| Press model / RIP / version | TBD |
| SCC model / firmware / Smart Input version | TBD |
| Supported stocks, dimensions and feed edges | 12 x 18 on 12-inch edge; 13 x 19 on 13-inch edge; additional stocks TBD |
| Press printable area per feed direction | TBD |
| SCC lead / trail / left / right constraints | TBD |
| Gutter minimum, maximum, increment and increment origin | TBD |
| Shared-cut permission and artwork conditions | TBD |
| Lane limits, slit/cut tooling and permitted positions | TBD |
| Setting precision and physical registration tolerance | TBD |
| Bleed requirements and permitted correction policies | TBD |
| Ranking preference | Maximum pieces per single sheet; tie-break preferences TBD |
| Golden-job inputs and independently approved outputs | TBD |

For each golden job record finished size, bleed, trim-to-trim gutter,
stock, feed edge, artwork rotation, rows, columns, lead/side cuts, expected pieces
per sheet, machine settings, measured result, reviewer and approval date.

Include exact fits, just-too-large pieces, the fixed short-edge feed, both artwork rotations, asymmetric
margins, unavailable stocks, no-fit jobs and each actual machine boundary.
Current automated tests use synthetic fixtures. Physical trials and approved
machine-rule cases are a separate acceptance gate.
