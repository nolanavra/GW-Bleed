# Security policy

This is a development alpha, not a production-certified release. Supported
production versions have not yet been established. Version 1.0 policy: maintain
the current stable release and previous minor for a six-month transition.

Do not put sensitive artwork or exploit details in public issues. A private
reporting address or hosted-repository advisory channel must be configured and
verified before publication. Until then, publication is blocked. Notify the
project owner privately through an existing agreed contact.

Processing is local; there is no telemetry, account, activation or upload service.
PDF workers are separate processes, NOT a security sandbox. Source size, page
size, page count, worker time and output limits reduce resource abuse; native
parser security and OS memory/process isolation remain explicit release gates.

Triage security and silent-output/data-loss defects before cosmetic issues.
Review dependency advisories monthly and before releases. Independently assess
PDF parsing, saved-input handling, packaging and update trust before version 1.0.
