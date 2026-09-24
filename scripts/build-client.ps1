param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://[^/]+')]
    [string]$AccountUrl,
    [string]$Output = 'aiparser-client.zip'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$outputPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path $Output))
$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$stage = Join-Path $tempRoot ('aiparser-client-' + [guid]::NewGuid().ToString('N'))
$archive = Join-Path $tempRoot ('aiparser-source-' + [guid]::NewGuid().ToString('N') + '.zip')

try {
    & git -C $root archive --format=zip "--output=$archive" HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Could not archive the latest commit' }

    New-Item -ItemType Directory -Path $stage | Out-Null
    Expand-Archive -LiteralPath $archive -DestinationPath $stage
    [System.IO.File]::WriteAllText((Join-Path $stage 'account-url.txt'),
        $AccountUrl.TrimEnd('/'), [System.Text.UTF8Encoding]::new($false))
    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $outputPath -Force
    Write-Output $outputPath
}
finally {
    # Remove only the two paths created above inside the system TEMP directory.
    if ($stage.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $stage)) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
    if ($archive.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $archive)) {
        Remove-Item -LiteralPath $archive -Force
    }
}
