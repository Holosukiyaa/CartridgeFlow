[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

function Resolve-RequiredCommand {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "$Name is required but was not found in PATH. Install it on the host machine and retry."
    }
    return $command.Source
}

$Python = Resolve-RequiredCommand "python"
$Node = Resolve-RequiredCommand "node"
$Npm = Resolve-RequiredCommand "npm.cmd"

Write-Host "Using host runtimes:"
& $Python --version
& $Node --version

Write-Host "Installing Python dependencies..."
& $Python -m pip install --disable-pip-version-check --retries 3 --timeout 60 -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Python dependency installation failed."
}

foreach ($frontend in @("src\creator-studio", "src\developer-console")) {
    Write-Host "Installing $frontend dependencies..."
    Push-Location (Join-Path $Root $frontend)
    try {
        & $Npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) {
            throw "$frontend dependency installation failed."
        }
    }
    finally {
        Pop-Location
    }
}

Write-Host "CartridgeFlow dependencies are ready."
