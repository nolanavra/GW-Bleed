# Finishing and installed accessories

The Layout settings area includes a Machine accessories tab. New setups assume
four strike positions on strike-capable machines and no rotary tools. Supercut
uses two automatic and two manual strike tools within that same four-tool total.
Operators can change the installed counts; supported capabilities still apply.
Counts do not establish physical machine validation or tool-spacing approval.

Finishing can be oriented at 0 or 90 degrees relative to the artwork. The engine
selects the matching artwork orientation to keep creases and cross perfs across
the feed, and strike/rotary perfs along it. Applying finishing opens Card view.
Repeated operations are checked against installed tool counts on the whole sheet.

The tent preset requires an entered end-flap size. Both end flaps use that size;
the remaining length is divided equally into sides A and B. Three creases divide
the four sections. Each centerline strike starts at an outer card edge and ends
halfway through its flap. Ticket and coupon presets default to strike perfs;
rotary perfs must be explicitly selected and installed.

New reader-capable setups enable barcode and machine L-mark generation. A valid
JJJQQ barcode payload is still required. Placement failures show a popup and block
PDF export until corrected. The L-mark defaults to 1 mm thickness and 5 mm arms;
its size is read-only. Ordinary marks default to .02 inch thickness, .2 inch
length, and zero gap, or .05 inch gap when both artwork bleed dimensions are zero.
The gap is derived automatically; mark sizes and positions are not editable.

Schema-5 jobs retain finishing orientation and installed accessory counts.
Schema-3/4 jobs remain readable. Legacy tooling is inferred on opening and is
labelled for operator confirmation; previously saved mark sizes remain readable.
