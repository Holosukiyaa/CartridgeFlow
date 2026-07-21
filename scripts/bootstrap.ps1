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
$RuntimesDir = Join-Path $ToolsDir "runtimes"
$DownloadsDir = Join-Path $ToolsDir "downloads"
$PythonDir = Join-Path $RuntimesDir "python"
$NodeDir = Join-Path $RuntimesDir "node"
$LegacyPythonDir = Join-Path $ToolsDir "python"
$LegacyNodeDir = Join-Path $ToolsDir "node"
$PythonExe = Join-Path $PythonDir "python.exe"
$NodeExe = Join-Path $NodeDir "node.exe"
$NpmCmd = Join-Path $NodeDir "npm.cmd"

function Test-CompatiblePython {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string]$ExpectedVersion
    )

    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        return $false
    }

    try {
        $identity = @(& $Executable -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}|{64 if sys.maxsize > 2**32 else 32}')" 2>$null)
        return $LASTEXITCODE -eq 0 -and $identity.Count -gt 0 -and $identity[0].Trim() -eq "$ExpectedVersion|64"
    }
    catch {
        return $false
    }
}

function Find-CompatibleRegisteredPython {
    param([Parameter(Mandatory = $true)][string]$ExpectedVersion)

    $parts = $ExpectedVersion.Split(".")
    $majorMinor = "$($parts[0]).$($parts[1])"
    $registryPaths = @(
        "Registry::HKEY_CURRENT_USER\Software\Python\PythonCore\$majorMinor\InstallPath",
        "Registry::HKEY_LOCAL_MACHINE\Software\Python\PythonCore\$majorMinor\InstallPath",
        "Registry::HKEY_LOCAL_MACHINE\Software\WOW6432Node\Python\PythonCore\$majorMinor\InstallPath"
    )

    foreach ($registryPath in $registryPaths) {
        try {
            $registration = Get-ItemProperty -LiteralPath $registryPath -ErrorAction Stop
            $candidates = @($registration.ExecutablePath, $registration."(default)")
            foreach ($candidate in $candidates) {
                if (-not $candidate) {
                    continue
                }
                $candidateExe = if ([System.IO.Path]::GetExtension([string]$candidate) -eq ".exe") {
                    [string]$candidate
                }
                else {
                    Join-Path ([string]$candidate) "python.exe"
                }
                if ((Test-CompatiblePython -Executable $candidateExe -ExpectedVersion $ExpectedVersion) -and
                    ([System.IO.Path]::GetFullPath($candidateExe) -ne [System.IO.Path]::GetFullPath($PythonExe))) {
                    return [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($candidateExe))
                }
            }
        }
        catch {
            continue
        }
    }
    return $null
}

function Assert-ProjectLocalToolPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $toolsRoot = [System.IO.Path]::GetFullPath($ToolsDir).TrimEnd('\') + '\'
    $resolved = [System.IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith($toolsRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a path outside the project tools directory: $resolved"
    }
}

function Copy-CleanPythonRuntime {
    param(
        [Parameter(Mandatory = $true)][string]$SourceDir,
        [Parameter(Mandatory = $true)][string]$DestinationDir
    )

    Assert-ProjectLocalToolPath -Path $DestinationDir
    if (Test-Path -LiteralPath $DestinationDir) {
        Remove-Item -LiteralPath $DestinationDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    Get-ChildItem -Force -LiteralPath $SourceDir | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $DestinationDir -Recurse -Force
    }

    foreach ($relativePath in @("Lib\site-packages", "Scripts")) {
        $copiedPath = Join-Path $DestinationDir $relativePath
        Assert-ProjectLocalToolPath -Path $copiedPath
        if (Test-Path -LiteralPath $copiedPath) {
            Remove-Item -LiteralPath $copiedPath -Recurse -Force
        }
    }

    if (-not (Test-CompatiblePython -Executable $PythonExe -ExpectedVersion $PythonVersion)) {
        throw "The copied Python runtime is not the required 64-bit Python $PythonVersion."
    }

    Write-Host "Initializing pip in the copied project-local Python runtime..."
    & $PythonExe -m ensurepip --upgrade --default-pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to initialize pip in the copied Python runtime."
    }
}

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
New-Item -ItemType Directory -Force -Path $RuntimesDir | Out-Null

foreach ($runtime in @(
    @{ Name = "Python"; Legacy = $LegacyPythonDir; Current = $PythonDir },
    @{ Name = "Node.js"; Legacy = $LegacyNodeDir; Current = $NodeDir }
)) {
    if ((Test-Path -LiteralPath $runtime.Legacy) -and -not (Test-Path -LiteralPath $runtime.Current)) {
        Write-Host "Migrating project-local $($runtime.Name) into .tools\runtimes..."
        Move-Item -LiteralPath $runtime.Legacy -Destination $runtime.Current
    }
}

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
    if ($process.ExitCode -ne 0) {
        throw "Python installer failed with exit code $($process.ExitCode)."
    }
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        $registeredPython = Find-CompatibleRegisteredPython -ExpectedVersion $PythonVersion
        if (-not $registeredPython) {
            throw "Python installer returned exit code 0 but did not create $PythonExe, and no compatible registered Python could be used as a local runtime source."
        }
        Write-Host "Python $PythonVersion is already registered at $registeredPython"
        Write-Host "Creating an isolated project-local copy..."
        Copy-CleanPythonRuntime -SourceDir $registeredPython -DestinationDir $PythonDir
    }
    if (-not (Test-CompatiblePython -Executable $PythonExe -ExpectedVersion $PythonVersion)) {
        throw "Project-local Python verification failed for $PythonExe"
    }
}

if (-not (Test-CompatiblePython -Executable $PythonExe -ExpectedVersion $PythonVersion)) {
    throw "Project-local Python must be 64-bit Python ${PythonVersion}: $PythonExe"
}

$PipPackageDir = Join-Path $PythonDir "Lib\site-packages\pip"
if (-not (Test-Path -LiteralPath $PipPackageDir -PathType Container)) {
    Write-Host "Project-local pip is missing; initializing it now..."
    & $PythonExe -m ensurepip --upgrade --default-pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to initialize project-local pip."
    }
}

if (-not (Test-Path -LiteralPath $NodeExe)) {
    $nodeArchiveName = "node-v$NodeVersion-win-x64.zip"
    $nodeArchive = Join-Path $DownloadsDir $nodeArchiveName
    $nodeExtracted = Join-Path $RuntimesDir "node-v$NodeVersion-win-x64"
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
    Expand-Archive -LiteralPath $nodeArchive -DestinationPath $RuntimesDir -Force
    Move-Item -LiteralPath $nodeExtracted -Destination $NodeDir
}

Write-Host "Installing Python dependencies..."
& $PythonExe -m pip install --disable-pip-version-check --no-warn-script-location -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Python dependency installation failed."
}

Write-Host "Installing frontend dependencies..."
Push-Location (Join-Path $Root "src\frontend")
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
