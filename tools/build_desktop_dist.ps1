# RoboMaster TT Desktop Packager Script
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DesktopDir = Join-Path $ProjectRoot "desktop"
$BuildDir = Join-Path $DesktopDir "build"
$DistDir = Join-Path $ProjectRoot "dist\RoboMasterTT"
$ExePath = Join-Path $BuildDir "Release\RoboMasterTT-Manager.exe"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  RoboMaster TT Native Desktop Packager" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Step 1: Ensure Release executable exists
if (-not (Test-Path $ExePath)) {
    Write-Host "[1/6] Building Release executable..." -ForegroundColor Yellow
    cmake -S $DesktopDir -B $BuildDir
    cmake --build $BuildDir --config Release
} else {
    Write-Host "[1/6] Release executable verified: $ExePath" -ForegroundColor Green
}

# Step 2: Initialize Dist directory
Write-Host "[2/6] Initializing dist directory: $DistDir" -ForegroundColor Yellow
if (Test-Path $DistDir) {
    Remove-Item -Path $DistDir -Recurse -Force
}
New-Item -ItemType Directory -Path $DistDir -Force | Out-Null

# Step 3: Copy executable and UI resources
Write-Host "[3/6] Copying RoboMasterTT-Manager.exe and resource..." -ForegroundColor Yellow
Copy-Item -Path $ExePath -Destination $DistDir -Force
Copy-Item -Path (Join-Path $DesktopDir "resource") -Destination (Join-Path $DistDir "resource") -Recurse -Force

# Step 4: Copy standalone Python 3.11 embedded runtime
Write-Host "[4/6] Copying embedded Python 3.11 runtime..." -ForegroundColor Yellow
$RuntimeSrc = Join-Path $ProjectRoot "runtime\python"
$RuntimeDst = Join-Path $DistDir "runtime\python"
New-Item -ItemType Directory -Path (Join-Path $DistDir "runtime") -Force | Out-Null
Copy-Item -Path $RuntimeSrc -Destination $RuntimeDst -Recurse -Force

# Configure python311._pth
$PthFile = Join-Path $RuntimeDst "python311._pth"
$PthContent = "python311.zip`n.`n..`n..\..`nimport site"
Set-Content -Path $PthFile -Value $PthContent -Encoding ASCII

# Step 5: Copy simulator core, scenes, web, tools
Write-Host "[5/6] Copying rmtt_sim, scenes, web, tools..." -ForegroundColor Yellow
Copy-Item -Path (Join-Path $ProjectRoot "rmtt_sim") -Destination (Join-Path $DistDir "rmtt_sim") -Recurse -Force
Copy-Item -Path (Join-Path $ProjectRoot "scenes") -Destination (Join-Path $DistDir "scenes") -Recurse -Force
Copy-Item -Path (Join-Path $ProjectRoot "web") -Destination (Join-Path $DistDir "web") -Recurse -Force

New-Item -ItemType Directory -Path (Join-Path $DistDir "tools") -Force | Out-Null
Copy-Item -Path (Join-Path $ProjectRoot "tools\setup_network.ps1") -Destination (Join-Path $DistDir "tools\setup_network.ps1") -Force
Copy-Item -Path (Join-Path $ProjectRoot "README.md") -Destination (Join-Path $DistDir "README.md") -Force
Copy-Item -Path (Join-Path $ProjectRoot "start.bat") -Destination (Join-Path $DistDir "start.bat") -Force

# Step 6: Verify package integrity
Write-Host "[6/6] Verifying distribution package integrity..." -ForegroundColor Yellow
$TestPython = Join-Path $RuntimeDst "python.exe"
$SelfTestOutput = & $TestPython -c "import sys; sys.path.insert(0, '.'); import rmtt_sim; print('rmtt_sim v' + rmtt_sim.__version__ + ' OK')"
Write-Host "  Self-test result: $SelfTestOutput" -ForegroundColor Green

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Package successful! Dist directory: $DistDir" -ForegroundColor Green
Write-Host "  Launch executable: $DistDir\RoboMasterTT-Manager.exe" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
