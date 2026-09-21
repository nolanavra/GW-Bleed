# Standalone internal alpha build

Prerequisites: Python 3.13.0 x64, Visual Studio 2022 Build Tools with the x64 C++
workload and Windows SDK, and PowerShell. The script fails if the expected runtime
or compiler is unavailable; it does not install system components automatically.

From the repository root:

```powershell
./tools/Build-Standalone.ps1 -PythonPath 'path/to/python.exe'
```

For a local build using the already downloaded wheelhouses:

```powershell
./tools/Build-Standalone.ps1 -Wheelhouse build/wheelhouse -BuildWheelhouse build/build-wheelhouse
```

Omitting PythonPath uses `.venv/Scripts/python.exe` only to bootstrap the build.
Dependencies install into `build/alpha-env`, separate from the working environment.
The build uses the hashed runtime and build-tool locks, then runs `pip check`.
Nuitka is built with the explicitly pinned setuptools/wheel backend and no build
isolation downloads. Optional Nuitka extras are not required for standalone mode.

Every invocation captures a new source snapshot under `build/alpha-runs`. Compilation
and testing use that snapshot, including uncommitted application changes. Do not
edit a captured snapshot; fix source and rerun. `-DryRun` validates/tests and prints
deployment commands but does not produce a ZIP.

The run folder contains regression results, source and distribution hashes,
toolchain details, deployment arguments, the Nuitka report, dependency notices,
worker smoke results, compiled GUI workflow results and screenshot, ZIP and checksum.
The GUI check exercises the packaged application's own PDF loader, page selection,
layout calculation, selected alternative, all three exports, and failed-load recovery.
Direct worker tests alone cannot qualify a package. Successful local packaging leaves
`clean-windows-acceptance.json` pending until the operator checklist is performed
on a fresh Windows VM. The release readiness record must remain development-only.

Runtime resources include the unchanged catalogued manuals. Nuitka's build-tool
license and runtime exception are included in the collected notices; inventory
does not claim a completed distribution license audit. Python/dependency security
versions require review before external distribution.

For an internal packaged-workflow diagnostic, use the bundled synthetic sample
and an absolute report path in a writable folder:

```powershell
& '.\GW-Bleed-Alpha.exe' --gw-check-workflow "$PWD\samples\sample-artwork.pdf" "$env:TEMP\gw-workflow.json"
```

This opens the actual GUI, exercises its controllers, writes a JSON result and a
screenshot, and closes. Exports use a temporary folder; the source is read-only.
The diagnostic uses test-mode application-data paths and does not change operator
paper profiles. It is an internal-alpha check, not clean-Windows acceptance.
