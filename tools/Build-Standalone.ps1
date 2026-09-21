param([switch]$DryRun, [string]$PythonPath, [string]$Wheelhouse, [string]$BuildWheelhouse)
$ErrorActionPreference='Stop'
$projectRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (!$PythonPath) { $PythonPath=Join-Path $projectRoot '.venv/Scripts/python.exe' }
$PythonPath=(Resolve-Path $PythonPath).Path
function Checked([string]$Program, [string[]]$Arguments) {
  & $Program @Arguments
  if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Program $Arguments" }
}
$runtime=& $PythonPath -c 'import sys,struct; print(sys.version_info[:3],struct.calcsize(chr(80))*8)'
if ($runtime -ne '(3, 13, 0) 64') { throw 'Internal alpha requires recorded Python 3.13.0 x64.' }
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
if (!(Test-Path $vswhere)) { throw 'Install Visual Studio 2022 Build Tools with the x64 C++ workload and Windows SDK.' }
$vs=& $vswhere -latest -products '*' -version '[17.0,18.0)' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json | ConvertFrom-Json
if (!$vs) { throw 'Visual Studio 2022 MSVC x64 tools are missing; no compiler fallback is permitted.' }
$toolset=Get-ChildItem (Join-Path $vs.installationPath 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$compilerBin=Join-Path $toolset.FullName 'bin/Hostx64/x64'
if (!(Test-Path (Join-Path $compilerBin 'dumpbin.exe'))) { throw 'MSVC dumpbin is missing.' }
$env:PATH=$compilerBin+';'+$env:PATH
$devCmd=Join-Path $vs.installationPath 'Common7/Tools/VsDevCmd.bat'
$devCommand='"'+$devCmd+'" -arch=x64 -host_arch=x64 >nul && set'
$vcEnvironment=& cmd.exe /d /c $devCommand
if ($LASTEXITCODE -ne 0) { throw 'Unable to initialize the MSVC/Windows SDK environment.' }
foreach ($entry in $vcEnvironment) {
  if ($entry -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1],$matches[2],'Process') }
}
if (!$env:WindowsSDKVersion -or !$env:INCLUDE -or !$env:LIB) { throw 'MSVC environment did not supply Windows SDK headers/libraries.' }
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$run=Join-Path $projectRoot "build/alpha-runs/$stamp"
New-Item -ItemType Directory -Path $run -Force | Out-Null
Start-Transcript -Path (Join-Path $run 'build.log') | Out-Null
Push-Location $projectRoot
try {
  Checked $PythonPath @('tools/alpha_build.py','snapshot',$run)
  $source=Join-Path $run 'source'
  $vs | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $run 'compiler-installation.json')
  @('cl.exe','link.exe') | ForEach-Object {
    $compilerFile=Get-Item (Join-Path $compilerBin $_)
    [PSCustomObject]@{name=$compilerFile.Name;version=$compilerFile.VersionInfo.FileVersion;sha256=(Get-FileHash $compilerFile.FullName -Algorithm SHA256).Hash}
  } | ConvertTo-Json | Set-Content (Join-Path $run 'compiler-binaries.json')
  Get-ChildItem 'C:/Program Files (x86)/Windows Kits/10/Include' -Directory | Select-Object Name | ConvertTo-Json | Set-Content (Join-Path $run 'windows-sdks.json')
  $envPath=Join-Path $projectRoot 'build/alpha-env'
  if (!(Test-Path (Join-Path $envPath 'Scripts/python.exe'))) { Checked $PythonPath @('-m','venv',$envPath) }
  $python=Join-Path $envPath 'Scripts/python.exe'
  $env:PIP_CACHE_DIR=Join-Path $projectRoot 'build/pip-cache'
  $env:NUITKA_CACHE_DIR=Join-Path $projectRoot 'build/nuitka-cache'
  $env:VIRTUAL_ENV=$envPath
  $install=@('-m','pip','install','--disable-pip-version-check','--require-hashes','-r',(Join-Path $source 'requirements-windows-cp313.hashed.lock'))
  if ($Wheelhouse) { $install+=@('--no-index','--find-links',(Resolve-Path $Wheelhouse).Path) }
  Checked $python $install
  $bootstrap=Join-Path $run 'build-backend.hashed.lock'
  Get-Content (Join-Path $source 'requirements-build.hashed.lock') | Where-Object { $_ -notmatch '^Nuitka==' } | Set-Content $bootstrap
  $backend=@('-m','pip','install','--disable-pip-version-check','--require-hashes','-r',$bootstrap)
  if ($BuildWheelhouse) { $backend+=@('--no-index','--find-links',(Resolve-Path $BuildWheelhouse).Path) }
  Checked $python $backend
  $buildInstall=@('-m','pip','install','--disable-pip-version-check','--no-build-isolation','--require-hashes','-r',(Join-Path $source 'requirements-build.hashed.lock'))
  if ($BuildWheelhouse) { $buildInstall+=@('--no-index','--no-build-isolation','--find-links',(Resolve-Path $BuildWheelhouse).Path) }
  Checked $python $buildInstall
  Checked $python @('-m','pip','check')
  Set-Location $source
  Checked $python @('tools/build_helpers.py',$env:NUITKA_CACHE_DIR,(Join-Path $run 'native-build-helpers.json'))
  New-Item -ItemType Directory -Path build -Force | Out-Null
  Checked $python @('tools/source_scan.py')
  Checked $python @('tools/alpha_build.py','tests',$run)
  Checked $python @('tools/dependency_inventory.py')
  Checked $python @('tools/dependency_inventory.py','--lock','requirements-build.lock','--output','build/release-evidence/build-tool-notices')
  Checked $python @('tools/alpha_build.py','prepare',$run)
  $deploy=@('-c','pysidedeploy.spec','--mode','standalone','--nuitka-version=4.1.1','--extra-ignore-dirs=build,tests,docs,tools,release,.github,sample','--keep-deployment-files','--force')
  if ($DryRun) { $deploy+='--dry-run' }
  $deploy | ConvertTo-Json | Set-Content (Join-Path $run 'deployment-arguments.json')
  Checked (Join-Path $envPath 'Scripts/pyside6-deploy.exe') $deploy
  if (!$DryRun) {
    Checked $python @('tools/alpha_build.py','assemble',$run)
    Checked $python @('tools/packaged_smoke.py',$run)
    Checked $python @('tools/alpha_build.py','archive',$run)
    Checked $python @('tools/alpha_build.py','verify_zip',$run)
  }
  Write-Output "Build evidence: $run. Clean-Windows acceptance remains pending."
} finally { Pop-Location; Stop-Transcript | Out-Null }
