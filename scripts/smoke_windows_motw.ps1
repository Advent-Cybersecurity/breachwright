param(
    [Parameter(Mandatory = $true)]
    [string]$BundleDirectory,

    [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"
$bundle = (Resolve-Path -LiteralPath $BundleDirectory).Path
$runtimeDll = Join-Path $bundle "_internal\pythonnet\runtime\Python.Runtime.dll"
$desktopSmoke = Join-Path (Split-Path $PSScriptRoot -Parent) "scripts\smoke_desktop.py"

foreach ($required in @(
    $runtimeDll,
    (Join-Path $bundle "Breachwright.exe"),
    (Join-Path $bundle "Breachwright.exe.config"),
    (Join-Path $bundle "BreachwrightCLI.exe.config")
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Windows download-origin smoke test is missing: $required"
    }
}

$existingStream = Get-Item -LiteralPath $runtimeDll -Stream Zone.Identifier `
    -ErrorAction SilentlyContinue
$existingContent = if ($existingStream) {
    Get-Content -LiteralPath $runtimeDll -Stream Zone.Identifier -Raw
} else {
    $null
}

try {
    Set-Content -LiteralPath $runtimeDll -Stream Zone.Identifier -Value @"
[ZoneTransfer]
ZoneId=3
"@
    & $PythonExecutable $desktopSmoke (Join-Path $bundle "Breachwright.exe")
    if ($LASTEXITCODE -ne 0) {
        throw "Windows download-origin desktop smoke failed with exit code $LASTEXITCODE"
    }
} finally {
    if ($existingStream) {
        Set-Content -LiteralPath $runtimeDll -Stream Zone.Identifier `
            -Value $existingContent -NoNewline
    } else {
        Remove-Item -LiteralPath $runtimeDll -Stream Zone.Identifier `
            -ErrorAction SilentlyContinue
    }
}

Write-Host "Windows marked-download desktop smoke passed"
