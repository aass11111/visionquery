# Native Windows setup for the backend (NVIDIA GPU, no Docker):
#   powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
# Installs Python 3.11 and ffmpeg with winget if missing (no admin rights needed), creates
# %USERPROFILE%\.venvs\visionquery and installs
# PyTorch (CUDA 12.4 wheels, ~2.5 GB) plus backend\requirements.txt. Safe to re-run.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Step($msg) { Write-Output "`n=== $msg  [$(Get-Date -Format HH:mm:ss)]" }
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE)" } }

$py = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
if (-not (Test-Path $py)) {
    Step 'Installing Python 3.11 (winget)'
    # Per-user install without the py launcher: the launcher is what makes the installer ask for admin (UAC).
    winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity `
        --override '/quiet InstallAllUsers=0 Include_launcher=0 InstallLauncherAllUsers=0 PrependPath=0 Include_test=0'
    if (-not (Test-Path $py)) { throw "Python not found at $py after install" }
}
Write-Output "python: $(& $py --version)"

$ffLinks = "$env:LOCALAPPDATA\Microsoft\WinGet\Links\ffmpeg.exe"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -and -not (Test-Path $ffLinks)) {
    Step 'Installing ffmpeg (winget)'
    winget install -e --id Gyan.FFmpeg.Essentials --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
}
Write-Output "ffmpeg: $(Test-Path $ffLinks)"

# Outside the project on purpose: PyTorch has deep file paths and a long project path breaks the
# 260-character Windows path limit (WinError 206). Override with $env:VQ_VENV.
$venv = if ($env:VQ_VENV) { $env:VQ_VENV } else { Join-Path $HOME '.venvs\visionquery' }
$vpy = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $vpy)) {
    Step "Creating $venv"
    & $py -m venv $venv; Check 'venv'
}
# Patient pip for slow or flaky connections (the bundled pip is recent enough; no self-upgrade).
$pipArgs = @('install', '--progress-bar', 'off', '--retries', '10', '--timeout', '120')

# Big PyPI wheels pre-downloaded in parallel by scripts\fetch_wheels.py (numpy, scipy, opencv...):
# install them first so pip only has the small remainder left to fetch.
$pypiWheels = @(Get-ChildItem (Join-Path $env:TEMP 'vq-wheels\pypi') -Filter '*.whl' -ErrorAction SilentlyContinue)
if ($pypiWheels.Count) {
    Step "Installing $($pypiWheels.Count) pre-downloaded PyPI wheels"
    & $vpy -m pip @pipArgs --no-deps ($pypiWheels | ForEach-Object FullName)
    Check 'pre-downloaded wheels install'
}

Step 'Installing PyTorch 2.5.1 + CUDA 12.4 (~2.5 GB)'
# Wheels verified by scripts\fetch-torch-wheels.sh are installed by path (their small dependencies
# come from PyPI); otherwise pip downloads them from the PyTorch index.
$wheels = Join-Path $env:TEMP 'vq-wheels'
$local = @(Get-ChildItem $wheels -Filter '*.whl' -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^torch(vision)?-' })
if ($local.Count -eq 2) {
    & $vpy -m pip @pipArgs ($local | ForEach-Object FullName)
} else {
    & $vpy -m pip @pipArgs torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
}
Check 'torch install'

Step 'Installing backend requirements'
& $vpy -m pip @pipArgs -r (Join-Path $root 'backend\requirements.txt')
Check 'requirements install'

Step 'Checking the GPU'
& $vpy -c "import torch; print('torch', torch.__version__, '| cuda', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no GPU')"
Check 'torch check'
Write-Output 'SETUP_DONE'
