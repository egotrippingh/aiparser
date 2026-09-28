param(
    [Parameter(Mandatory = $true)][string]$BundleDir,
    [Parameter(Mandatory = $true)][string]$BrowserDir,
    [Parameter(Mandatory = $true)][ValidatePattern('^\d+\.\d+\.\d+\.\d+$')][string]$Version,
    [string]$Compiler
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bundle = (Resolve-Path -LiteralPath $BundleDir).Path
$browser = (Resolve-Path -LiteralPath $BrowserDir).Path
foreach ($file in @('camoufox.exe', 'properties.json', 'version.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $browser $file))) {
        throw "Incomplete browser bundle: missing $file"
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $bundle 'AI-Mentions.exe'))) {
    throw 'Build a verified bundle using scripts/build-exe.ps1 first'
}
if ((Test-Path -LiteralPath (Join-Path $bundle 'data')) -or
    (Get-ChildItem -LiteralPath $bundle -Force -Filter '.env*')) {
    throw 'The installer source contains user data or environment files'
}
if (-not $Compiler) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    )
    $Compiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $Compiler) { throw 'Install Inno Setup 6.7.3 (winget install --id JRSoftware.InnoSetup --version 6.7.3 --exact)' }
$dist = Join-Path $root 'dist'
& $Compiler "/DBundleDir=$bundle" "/DBrowserDir=$browser" "/DAppVersion=$Version" "/DOutputPath=$dist" (Join-Path $PSScriptRoot 'airate-installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
$installer = Join-Path $dist "AIRate-Setup-$Version.exe"
$temporary = Join-Path $dist ('AIRate-Setup-' + [guid]::NewGuid().ToString('N') + '.tmp')
Copy-Item -LiteralPath $installer -Destination $temporary
Move-Item -LiteralPath $temporary -Destination (Join-Path $dist 'AIRate-Setup-latest.exe') -Force
Get-FileHash -LiteralPath $installer -Algorithm SHA256
Write-Output "INSTALLER: $installer"
