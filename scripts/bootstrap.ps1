[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$PythonVersion = "3.13.14"
$PythonSha256 = "c54d9b9bbb8a36e6489363ddd01139707fd781d72f1f9e90c7ec65d0061368e0"
$NodeVersion = "24.18.0"
$NodeSha256 = "0ae68406b42d7725661da979b1403ec9926da205c6770827f33aac9d8f26e821"

$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$ToolsDir = Join-Path $Root ".tools"
$DownloadsDir = Join-Path $ToolsDir "downloads"
$PythonDir = Join-Path $ToolsDir "python"
$NodeDir = Join-Path $ToolsDir "node"
$PythonExe = Join-Path $PythonDir "python.exe"
$NodeExe = Join-Path $NodeDir "node.exe"
$NpmCmd = Join-Path $NodeDir "npm.cmd"

function Get-VerifiedDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256
    )

    if (-not (Test-Path -LiteralPath $Destination)) {
        Write-Host "Downloading $Url"
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination
    }

    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedSha256) {
        Remove-Item -LiteralPath $Destination -Force
        throw "SHA-256 verification failed for $Destination"
    }
}

if ($env:PROCESSOR_ARCHITECTURE -ne "AMD64") {
    throw "This bootstrap currently supports 64-bit Windows on x64 processors."
}

New-Item -ItemType Directory -Force -Path $DownloadsDir | Out-Null

if (-not (Test-Path -LiteralPath $PythonExe)) {
    $pythonInstaller = Join-Path $DownloadsDir "python-$PythonVersion-amd64.exe"
    Get-VerifiedDownload `
        -Url "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe" `
        -Destination $pythonInstaller `
        -ExpectedSha256 $PythonSha256

    Write-Host "Installing project-local Python $PythonVersion..."
    $arguments = @(
        "/quiet",
        "InstallAllUsers=0",
        "TargetDir=`"$PythonDir`"",
        "Include_doc=0",
        "Include_debug=0",
        "Include_dev=0",
        "Include_launcher=0",
        "Include_test=0",
        "Include_tcltk=0",
        "Include_pip=1",
        "AssociateFiles=0",
        "Shortcuts=0",
        "PrependPath=0"
    )
    $process = Start-Process -FilePath $pythonInstaller -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $PythonExe)) {
        throw "Python installer failed with exit code $($process.ExitCode)."
    }
}

if (-not (Test-Path -LiteralPath $NodeExe)) {
    $nodeArchiveName = "node-v$NodeVersion-win-x64.zip"
    $nodeArchive = Join-Path $DownloadsDir $nodeArchiveName
    $nodeExtracted = Join-Path $ToolsDir "node-v$NodeVersion-win-x64"
    Get-VerifiedDownload `
        -Url "https://nodejs.org/dist/v$NodeVersion/$nodeArchiveName" `
        -Destination $nodeArchive `
        -ExpectedSha256 $NodeSha256

    Write-Host "Installing project-local Node.js $NodeVersion..."
    if (Test-Path -LiteralPath $nodeExtracted) {
        Remove-Item -LiteralPath $nodeExtracted -Recurse -Force
    }
    if (Test-Path -LiteralPath $NodeDir) {
        Remove-Item -LiteralPath $NodeDir -Recurse -Force
    }
    Expand-Archive -LiteralPath $nodeArchive -DestinationPath $ToolsDir -Force
    Move-Item -LiteralPath $nodeExtracted -Destination $NodeDir
}

Write-Host "Installing Python dependencies..."
& $PythonExe -m pip install --disable-pip-version-check --no-warn-script-location -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Python dependency installation failed."
}

Write-Host "Installing frontend dependencies..."
Push-Location (Join-Path $Root "frontend")
try {
    & $NpmCmd ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend dependency installation failed."
    }
}
finally {
    Pop-Location
}

Write-Host "Runtime setup complete."
& $PythonExe --version
& $NodeExe --version
