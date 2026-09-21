# Deployment contract (not yet certified)

Official binaries are paid distribution/support; community builds have identical
features and require no activation. Initial supported platform is Windows 11 x64.
Normal operation must work without elevation and without network access.

Build two artifacts from one reviewed revision: Store MSIX and signed direct MSI.
Paid Store apps cannot be assumed deployable through Intune Store integration;
enterprise customers use the independently managed direct channel.

MSI requirements: silent install/uninstall, stable upgrade identity, documented
product/version detection and exit codes, upgrade testing and preserved user
documents. Admins control direct-channel deployment; do not promise Store version
pinning or automatic downgrade. No custom self-updater in this alpha.

Managed policy, accessibility certification, signing identities, Store package
identity and actual installer artifacts remain release blockers. Do not invent
publisher IDs/certificates or claim an unsigned build is trusted by Windows.
