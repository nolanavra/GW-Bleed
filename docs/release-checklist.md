# Release checklist

- [ ] License/assets/module review complete; exact wheel/native notices bundled.
- [ ] Public source and private security reporting contacts verified.
- [ ] Clean Windows locked install, zero skipped required tests, independent PDF QA.
- [ ] No old PDF engine in runtime, tests, package or build environment.
- [ ] Source/build manifest and dependency inventory linked to artifact hash.
- [ ] All six machine configurations physically approved with measured evidence.
- [ ] Recovery/failure, security, accessibility and IT deployment checks approved.
- [ ] Three-site/four-week pilot approved; no unresolved critical/high defects.
- [ ] Signing identities, Store identity, privacy/support pages confirmed.
- [ ] Signed installer upgrade/uninstall and standard-user tests pass.
- [ ] Applicable Store certification passes; paid support terms are staffed.
- [ ] Release notes and known limitations accurately describe supported behavior.

Run tools/release_gate.py. A passing unit suite alone cannot authorize 1.0.
