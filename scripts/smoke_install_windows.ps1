param(
    [Parameter(Mandatory = $true)]
    [string]$BundleDirectory
)

$ErrorActionPreference = "Stop"
$bundle = (Resolve-Path -LiteralPath $BundleDirectory).Path
$runnerTemp = (Resolve-Path -LiteralPath $env:RUNNER_TEMP).Path
$smokeRoot = Join-Path $runnerTemp ("breachwright-install-smoke-" + $env:GITHUB_RUN_ID)
$localRoot = Join-Path $smokeRoot "local"
$roamingRoot = Join-Path $smokeRoot "roaming"

New-Item -ItemType Directory -Force -Path $localRoot, $roamingRoot | Out-Null
$env:LOCALAPPDATA = $localRoot
$env:APPDATA = $roamingRoot
$env:BREACHWRIGHT_SKIP_SHORTCUTS = "1"
$env:BREACHWRIGHT_NONINTERACTIVE = "1"
$env:BREACHWRIGHT_CONFIRM_UNINSTALL = "1"
$env:BREACHWRIGHT_REMOVE_DATA = "0"

$installer = Join-Path $bundle "install-windows.bat"
$uninstaller = Join-Path $bundle "uninstall-windows.bat"
& cmd.exe /d /c "call `"$installer`""
if ($LASTEXITCODE -ne 0) {
    throw "Windows bundle installer failed with exit code $LASTEXITCODE"
}

$installDirectory = Join-Path $localRoot "Breachwright"
$dataDirectory = Join-Path $roamingRoot "Breachwright"
$cli = Join-Path $installDirectory "BreachwrightCLI.exe"
$expectedVersion = (Get-Content -LiteralPath (Join-Path $bundle "VERSION") -Raw).Trim()

if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) {
    throw "Installed CLI was not found"
}
foreach ($document in @("INSTALL.md", "docs\DATA_SAFETY.md")) {
    if (-not (Test-Path -LiteralPath (Join-Path $installDirectory $document) -PathType Leaf)) {
        throw "Installed documentation was not found: $document"
    }
}
$reportedVersion = (& $cli --version).Trim()
if ($reportedVersion -ne "Breachwright $expectedVersion") {
    throw "Installed CLI reported an unexpected version: $reportedVersion"
}

$marker = Join-Path $dataDirectory "preserved-marker"
Set-Content -LiteralPath $marker -Value "preserve" -NoNewline
& cmd.exe /d /c "call `"$uninstaller`""
if ($LASTEXITCODE -ne 0) {
    throw "Windows bundle uninstaller failed with exit code $LASTEXITCODE"
}

if (Test-Path -LiteralPath $installDirectory) {
    throw "Windows application files remained after uninstall"
}
if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
    throw "Windows uninstall did not preserve application data"
}

Write-Host "Windows bundle install, version, uninstall, and data preservation passed"
