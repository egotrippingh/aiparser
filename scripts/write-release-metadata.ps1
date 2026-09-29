param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [Parameter(Mandatory = $true)][string]$Portable,
    [Parameter(Mandatory = $true)][string]$Version
)

$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'Version must have four numeric parts' }
function Artifact([string]$Path) {
    $file = Get-Item -LiteralPath $Path -ErrorAction Stop
    return @{ size_bytes = [int64]$file.Length; sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}
$output = Join-Path (Split-Path -Parent (Resolve-Path -LiteralPath $Installer)) 'agent-release.json'
@{version=$Version; installer=Artifact $Installer; portable=Artifact $Portable} | ConvertTo-Json -Compress | Set-Content -LiteralPath $output -Encoding utf8NoBOM
Write-Output $output
