param(
    [string]$Compiler
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv and install release dependencies first' }
New-Item -ItemType Directory -Force -Path (Join-Path $root 'build') | Out-Null

function Invoke-Release([string]$Name, [scriptblock]$Command) {
    $log = Join-Path $root ("build\{0}.log" -f $Name)
    & $Command 2>&1 | Tee-Object -FilePath $log
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (see $log)" }
}

Push-Location $root
try {
    Invoke-Release 'agent-npm-ci' { & npm.cmd ci --prefix frontend }
    Invoke-Release 'agent-npm-test' { & npm.cmd test --prefix frontend }
    Invoke-Release 'agent-npm-build' { & npm.cmd run build --prefix frontend }
    Invoke-Release 'agent-python-tests' { & $python -m pytest tests/test_updates.py tests/test_update_admission.py tests/test_agent_publication.py tests/test_desktop_login.py -q }

    $browserOutput = & $python scripts/prepare-browser.py 2>&1
    $browserOutput | Tee-Object -FilePath (Join-Path $root 'build\agent-browser.log')
    if ($LASTEXITCODE -ne 0) { throw 'prepare-browser failed' }
    $browserLine = @($browserOutput | Where-Object { $_ -match '^BROWSER: ' }) | Select-Object -Last 1
    if (-not $browserLine) { throw 'prepare-browser did not report BROWSER path' }
    $browser = $browserLine.ToString().Substring('BROWSER: '.Length)
    if (-not (Test-Path -LiteralPath $browser)) { throw 'Reported browser path does not exist' }

    $exeOutput = & pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/build-exe.ps1 -AccountUrl https://airate.tech -SkipFrontendBuild 2>&1
    $exeOutput | Tee-Object -FilePath (Join-Path $root 'build\agent-exe.log')
    if ($LASTEXITCODE -ne 0) { throw 'build-exe failed' }
    $exeLine = @($exeOutput | Where-Object { $_ -match '^EXE: ' }) | Select-Object -Last 1
    if (-not $exeLine) { throw 'build-exe did not report EXE path' }
    $bundle = Split-Path -Parent $exeLine.ToString().Substring('EXE: '.Length)
    if (-not (Test-Path -LiteralPath $bundle)) { throw 'Reported bundle path does not exist' }

    $installerArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/build-installer.ps1', '-BundleDir', $bundle, '-BrowserDir', $browser)
    if ($Compiler) { $installerArgs += @('-Compiler', $Compiler) }
    Invoke-Release 'agent-installer' { & pwsh @installerArgs }
    Invoke-Release 'agent-installer-smoke' { & $python -X utf8 scripts/test-installer.py --installer dist/AIRate-Setup-latest.exe --bundle $bundle --browser $browser }
    Invoke-Release 'agent-release-metadata' { & $python -c "import runpy; from pathlib import Path; m=runpy.run_path('scripts/publish-agent.py'); print(m['validate_release'](Path('dist')))" }
}
finally {
    Pop-Location
}
