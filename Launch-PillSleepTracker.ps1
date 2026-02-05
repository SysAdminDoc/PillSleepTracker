#Requires -Version 5.1
<#
.SYNOPSIS
    PillSleepTracker Pro Launcher
.DESCRIPTION
    Detects Python, installs dependencies, and launches PillSleepTracker Pro
    without leaving a console window open.
#>

$ErrorActionPreference = 'SilentlyContinue'
$Host.UI.RawUI.WindowTitle = "PillSleepTracker Pro - Launcher"

Write-Host ""
Write-Host "  PillSleepTracker Pro - Launcher" -ForegroundColor Cyan
Write-Host "  ================================" -ForegroundColor DarkCyan
Write-Host ""

# -- Locate Python --
$pythonExe = $null
$pythonwExe = $null

foreach ($cmd in @('pythonw', 'python', 'python3')) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
        if ($cmd -eq 'pythonw') { $pythonwExe = $found.Source }
        if (-not $pythonExe -and $cmd -ne 'pythonw') { $pythonExe = $found.Source }
        if (-not $pythonwExe -and $cmd -eq 'pythonw') { $pythonwExe = $found.Source }
    }
}

# Check common paths
if (-not $pythonExe) {
    $searchPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "C:\Python313\python.exe",
        "C:\Python312\python.exe"
    )
    foreach ($p in $searchPaths) {
        if (Test-Path $p) {
            $pythonExe = $p
            $pythonwExe = $p -replace 'python\.exe$', 'pythonw.exe'
            if (-not (Test-Path $pythonwExe)) { $pythonwExe = $null }
            break
        }
    }
}

if (-not $pythonExe) {
    Write-Host "  [ERROR] Python not found." -ForegroundColor Red
    Write-Host "  Install Python 3.8+ from https://python.org" -ForegroundColor Yellow
    Write-Host "  Ensure 'Add to PATH' is checked during install." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "  Press Enter to exit"
    exit 1
}

$pyVer = & $pythonExe --version 2>&1
Write-Host "  [OK] $pyVer" -ForegroundColor Green

# -- Install dependencies --
Write-Host "  Checking dependencies..." -ForegroundColor Gray

$packages = @('customtkinter', 'matplotlib', 'Pillow', 'pystray')
$pipArgs = @('-m', 'pip', 'install', '--upgrade', '-q') + $packages

& $pythonExe $pipArgs 2>$null
if ($LASTEXITCODE -ne 0) {
    & $pythonExe @('-m', 'pip', 'install', '--user', '-q') $packages 2>$null
}

Write-Host "  [OK] Dependencies ready." -ForegroundColor Green

# -- Launch --
$scriptPath = Join-Path $PSScriptRoot "PillSleepTracker.py"
if (-not (Test-Path $scriptPath)) {
    Write-Host "  [ERROR] PillSleepTracker.py not found in:" -ForegroundColor Red
    Write-Host "  $PSScriptRoot" -ForegroundColor Yellow
    Read-Host "  Press Enter to exit"
    exit 1
}

Write-Host "  Launching PillSleepTracker Pro..." -ForegroundColor Cyan
Write-Host ""

# Prefer pythonw (no console window)
$launcher = if ($pythonwExe -and (Test-Path $pythonwExe)) { $pythonwExe } else { $pythonExe }

Start-Process -FilePath $launcher -ArgumentList "`"$scriptPath`"" -WindowStyle Hidden
