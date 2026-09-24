param(
    [Parameter(Mandatory = $true)]
    [string]$AccountUrl,
    [switch]$SkipFrontendBuild,
    [switch]$TestBrowser
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$distRoot = Join-Path $root 'dist'
$buildRoot = Join-Path $root 'build'
$stage = Join-Path $buildRoot ('desktop-' + [guid]::NewGuid().ToString('N'))
$stageFull = [System.IO.Path]::GetFullPath($stage)
$buildFull = [System.IO.Path]::GetFullPath($buildRoot).TrimEnd('\') + '\'
$distFull = [System.IO.Path]::GetFullPath($distRoot).TrimEnd('\') + '\'

if (-not $stageFull.StartsWith($buildFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build stage must stay inside the project build directory'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create .venv and install requirements.txt and scripts/requirements-build.txt first'
}
$accountUrl = $AccountUrl.TrimEnd('/')
if ($accountUrl -notmatch '^https://[^/]+$' -and
    $accountUrl -notmatch '^http://(127\.0\.0\.1|localhost):[0-9]+$') {
    throw 'AccountUrl must be an HTTPS origin or a local test origin'
}

New-Item -ItemType Directory -Path $stage -Force | Out-Null
New-Item -ItemType Directory -Path $distRoot -Force | Out-Null

try {
    if (-not $SkipFrontendBuild) {
        if (-not (Test-Path -LiteralPath (Join-Path $root 'frontend\node_modules'))) {
            Push-Location (Join-Path $root 'frontend')
            try { & npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' } }
            finally { Pop-Location }
        }
        Push-Location (Join-Path $root 'frontend')
        try { & npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' } }
        finally { Pop-Location }
    }

    & $python -m PyInstaller --noconfirm --clean `
        --distpath (Join-Path $stage 'dist') `
        --workpath (Join-Path $stage 'work') `
        (Join-Path $root 'desktop.spec')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }

    $bundle = Join-Path $stage 'dist\AI-Mentions'
    if (-not (Test-Path -LiteralPath (Join-Path $bundle 'AI-Mentions.exe'))) {
        throw 'AI-Mentions.exe was not created'
    }
    [System.IO.File]::WriteAllText((Join-Path $bundle 'account-url.txt'),
        $accountUrl, [System.Text.UTF8Encoding]::new($false))

    $exePath = Join-Path $bundle 'AI-Mentions.exe'
    $probeArgs = @('--self-test')
    if ($TestBrowser) { $probeArgs += '--self-test-browser' }
    $probe = Start-Process -FilePath $exePath -ArgumentList $probeArgs -PassThru -WindowStyle Hidden
    if (-not $probe.WaitForExit(120000)) {
        Stop-Process -Id $probe.Id -Force
        throw 'EXE self-test did not finish within 120 seconds'
    }
    $probe.Refresh()
    if ($probe.ExitCode -ne 0) { throw 'EXE self-test failed; check %LOCALAPPDATA%\AIParser\startup-error.log' }

    # The self-test creates a fresh local database. It must never ship in the archive.
    $testData = Join-Path $bundle 'data'
    $testDataFull = [System.IO.Path]::GetFullPath($testData)
    $bundleFull = [System.IO.Path]::GetFullPath($bundle).TrimEnd('\') + '\'
    if (-not $bundleFull.StartsWith($stageFull.TrimEnd('\') + '\',
        [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Built bundle must stay inside the build stage'
    }
    if ($testDataFull.StartsWith($bundleFull, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $testData)) {
        Remove-Item -LiteralPath $testData -Recurse -Force
    }

    $releaseName = 'AI-Mentions-Windows-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    $releaseDir = Join-Path $distRoot $releaseName
    $releaseFull = [System.IO.Path]::GetFullPath($releaseDir)
    if (-not $releaseFull.StartsWith($distFull, [System.StringComparison]::OrdinalIgnoreCase) -or
        (Test-Path -LiteralPath $releaseDir)) {
        throw 'Release path is outside dist or already exists'
    }
    Move-Item -LiteralPath $bundle -Destination $releaseDir
    $archive = Join-Path $distRoot ($releaseName + '.zip')
    Compress-Archive -Path (Join-Path $releaseDir '*') -DestinationPath $archive

    Write-Output "EXE: $(Join-Path $releaseDir 'AI-Mentions.exe')"
    Write-Output "ZIP: $archive"
}
finally {
    if ($stageFull.StartsWith($buildFull, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $stage)) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
