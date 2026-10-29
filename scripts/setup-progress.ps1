# Live progress bar for scripts\setup-windows.ps1 (run it in a second terminal):
#   powershell -ExecutionPolicy Bypass -File scripts\setup-progress.ps1
# Progress = bytes this PC has received since the bar started / the expected download size,
# plus the current step from setup-windows.log. Close with Ctrl+C at any time; setup keeps going.
param(
    [string]$Log = (Join-Path (Split-Path -Parent $PSScriptRoot) 'setup-windows.log'),
    [double]$TotalGB = 2.85  # Python ~25 MB + ffmpeg ~100 MB + PyTorch ~2.5 GB + requirements ~200 MB
)

function Get-ReceivedBytes {
    $sum = 0
    foreach ($nic in [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
        if ($nic.OperationalStatus -eq 'Up' -and $nic.NetworkInterfaceType -ne 'Loopback') {
            $sum += $nic.GetIPv4Statistics().BytesReceived
        }
    }
    return [double]$sum
}

function Format-Size([double]$b) {
    if ($b -ge 1GB) { return '{0:N2} GB' -f ($b / 1GB) }
    return '{0:N0} MB' -f ($b / 1MB)
}

$full = [char]0x2588
$empty = [char]0x2591
$total = $TotalGB * 1GB
$start = Get-ReceivedBytes
$t0 = Get-Date
$samples = New-Object System.Collections.Generic.Queue[object]
$width = 40

$wheels = Join-Path $env:TEMP 'vq-wheels'
$wheelTotal = 2400MB  # torch (~2394 MB) + torchvision (~6 MB)
$packagesTotal = 140MB  # PyTorch's small dependencies + backend\requirements.txt
$projectDir = Split-Path -Parent $Log
$fetchLog = Join-Path $projectDir 'torch-download.log'
$attemptsLog = Join-Path $projectDir 'setup-attempts.log'
$pkgStart = $null
$staleAt = $null
$modelsSeen = 0
$modelsAt = 0
$venv = if ($env:VQ_VENV) { $env:VQ_VENV } else { Join-Path $HOME '.venvs\visionquery' }
$sitePackages = Join-Path $venv 'Lib\site-packages'
$venvTotal = 5.0GB
$lastSize = $null
$lastSizeAt = Get-Date

while ($true) {
    $now = Get-Date
    $fetchDone = (Test-Path $fetchLog) -and ((Get-Content $fetchLog -Raw -ErrorAction SilentlyContinue) -match 'WHEELS_DONE')
    # Phase 1, PyTorch download: measure the wheel files themselves (exact, unaffected by other
    # downloads on this PC). Phase 2, pip packages: bytes received since that phase started.
    $wheelFiles = Get-ChildItem $wheels -File -ErrorAction SilentlyContinue
    # scripts\fetch_wheels.py (parallel PyPI download) reports its own exact progress.
    $pypiFile = Join-Path $projectDir 'fetch-wheels.json'
    $pypi = $null
    if (Test-Path $pypiFile) {
        try { $pypi = Get-Content $pypiFile -Raw | ConvertFrom-Json } catch { $pypi = $null }
    }
    $logNow = if (Test-Path $Log) { Get-Content $Log -Raw -ErrorAction SilentlyContinue } else { '' }
    $lastStep = [regex]::Matches("$logNow", '(?m)^=== (.+?)\s+\[')
    $lastStep = if ($lastStep.Count) { $lastStep[$lastStep.Count - 1].Groups[1].Value } else { '' }
    $pypiActive = $pypi -and -not $pypi.finished -and $pypi.total -gt 0
    $installing = -not $pypiActive -and $lastStep -match '^Installing (PyTorch|backend|\d+ pre-downloaded)' -and "$logNow" -notmatch 'SETUP_DONE'
    # Model weights (scripts\fetch_models.py) log "progress N/T MB" every 15 s; fill the gaps
    # between log lines with the bytes this PC received since the last one.
    $modelsLog = Join-Path $projectDir 'fetch-models.log'
    $models = $null
    if (Test-Path $modelsLog) {
        $mtext = Get-Content $modelsLog -Raw -ErrorAction SilentlyContinue
        $mp = [regex]::Matches("$mtext", 'progress (\d+)/(\d+) MB')
        if ($mp.Count -and "$mtext" -notmatch 'MODELS_DONE|FAILED') {
            $models = @{ got = [double]$mp[$mp.Count - 1].Groups[1].Value * 1MB; total = [double]$mp[$mp.Count - 1].Groups[2].Value * 1MB }
            if ($mp.Count -ne $modelsSeen) { $modelsSeen = $mp.Count; $modelsAt = Get-ReceivedBytes }
        }
    }
    if ($models) {
        $total = $models.total
        $got = [math]::Min($total, $models.got + ((Get-ReceivedBytes) - $modelsAt))
        $installing = $false
        $pypiActive = $false
    } elseif ($installing) {
        # Install phase: the environment grows to ~5 GB (PyTorch alone unpacks to ~4.3 GB).
        # Sizing thousands of files is slow, so refresh it every 3 seconds.
        $total = $venvTotal
        if ($null -eq $lastSize -or ($now - $lastSizeAt).TotalSeconds -ge 3) {
            $lastSize = [double]((Get-ChildItem $sitePackages -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum)
            $lastSizeAt = $now
        }
        $got = [math]::Min($total * 0.99, $lastSize)
    } elseif ($pypi -and -not $pypi.finished -and $pypi.total -gt 0) {
        $total = [double]$pypi.total
        $got = [double]$pypi.got
        # If the downloader stopped refreshing the file, keep counting with the network bytes.
        if (((Get-Date) - (Get-Item $pypiFile).LastWriteTime).TotalSeconds -gt 5) {
            if ($null -eq $staleAt) { $staleAt = Get-ReceivedBytes }
            $got += (Get-ReceivedBytes) - $staleAt
        } else { $staleAt = $null }
        $got = [math]::Min($total, $got)
    } elseif ($fetchDone) {
        if ($null -eq $pkgStart) { $pkgStart = Get-ReceivedBytes; $samples.Clear() }
        $total = $packagesTotal
        $got = [math]::Min($total, [math]::Max(0, (Get-ReceivedBytes) - $pkgStart))
    } elseif ($wheelFiles) {
        $total = $wheelTotal
        # Directory listings report stale sizes for files still open for writing on NTFS, so open
        # each file (shared) and ask the handle for its real length.
        $got = 0.0
        foreach ($f in $wheelFiles) {
            try {
                $fs = [System.IO.File]::Open($f.FullName, 'Open', 'Read', 'ReadWrite, Delete')
                $got += $fs.Length
                $fs.Dispose()
            } catch { $got += $f.Length }
        }
        if ($got -gt $total) { $got = $total }  # parts and the joined file briefly coexist
    } else {
        $total = $TotalGB * 1GB
        $got = [math]::Max(0, (Get-ReceivedBytes) - $start)
    }
    $samples.Enqueue(@($now, $got))
    while ($samples.Count -gt 10) { [void]$samples.Dequeue() }
    $first = $samples.Peek()
    $dt = ($now - $first[0]).TotalSeconds
    $speed = if ($dt -gt 0) { ($got - $first[1]) / $dt } else { 0 }

    $text = if (Test-Path $Log) { Get-Content $Log -Raw -ErrorAction SilentlyContinue } else { '' }
    $steps = [regex]::Matches("$text", '(?m)^=== (.+?)\s+\[')
    $step = if ($steps.Count) { $steps[$steps.Count - 1].Groups[1].Value } else { 'Waiting for setup to start' }
    $attempts = if (Test-Path $attemptsLog) { Get-Content $attemptsLog -Raw -ErrorAction SilentlyContinue } else { '' }
    if ($models) {
        $step = 'Downloading model weights: YOLO-World, SAM 2, CLIP (12 connections)'
        $done = $false
    } elseif ($installing) {
        $step = "$lastStep (unpacking into the environment)"
    } elseif ($pypi -and -not $pypi.finished -and $pypi.total -gt 0) {
        $step = "Downloading $($pypi.files) big Python packages over 12 connections"
    } elseif ($fetchDone) {
        # Show the package pip is fetching right now, e.g. "sympy (6.2 MB)".
        $dl = [regex]::Matches("$text", '(?m)^\s*Downloading (\S+?)(?:-\d[^\s]*)?\.(?:whl|tar\.gz)\s*(\([^)]*\))?')
        $real = @($dl | Where-Object { $_.Groups[2].Success })
        if ($real.Count) { $step = "pip: $($real[-1].Groups[1].Value) $($real[-1].Groups[2].Value)" }
        $tries = [regex]::Matches("$attempts", 'setup attempt (\d+)')
        if ($tries.Count -gt 1) { $step += "  (attempt $($tries[-1].Groups[1].Value))" }
    } elseif ($wheelFiles -and -not ("$text" -match 'Installing PyTorch')) {
        $step = 'Downloading PyTorch in 8 parallel parts'
    }
    $done = -not $models -and (("$text" -match 'SETUP_DONE') -or ("$attempts" -match 'SETUP_DONE'))
    # One failed pip attempt is retried by setup-until-done.sh; only giving up is final.
    $failed = "$attempts" -match 'GAVE_UP'

    $pct = if ($done) { 100 } else { [math]::Min(99, [math]::Floor($got / $total * 100)) }
    $n = [math]::Floor($pct / 100 * $width)
    $bar = ([string]$full * $n) + ([string]$empty * ($width - $n))
    # Below ~50 KB/s nothing big is downloading (installer running or waiting), so an ETA would be nonsense.
    $eta = if ($speed -gt 50KB -and -not $done) {
        $left = [timespan]::FromSeconds([math]::Max(0, ($total - $got) / $speed))
        '{0:hh\:mm\:ss}' -f $left
    } else { '--:--:--' }
    $elapsed = '{0:hh\:mm\:ss}' -f ($now - $t0)

    Clear-Host
    Write-Host ''
    Write-Host '  VisionQuery setup' -ForegroundColor Magenta
    Write-Host ''
    $color = if ($failed) { 'Red' } elseif ($done) { 'Green' } else { 'Cyan' }
    Write-Host ("  [{0}] {1,3}%" -f $bar, $pct) -ForegroundColor $color
    Write-Host ''
    Write-Host ("  Step       {0}" -f $step)
    Write-Host ("  Received   {0} / ~{1}" -f (Format-Size $got), (Format-Size $total))
    Write-Host ("  Speed      {0:N2} MB/s" -f ($speed / 1MB))
    Write-Host ("  Remaining  {0}    Elapsed {1}" -f $eta, $elapsed)
    Write-Host ''
    if (Get-Process consent -ErrorAction SilentlyContinue) {
        Write-Host '  ! Windows is asking for permission (UAC). Find the shield icon in the taskbar and click Yes.' -ForegroundColor Yellow
        Write-Host ''
    }
    if ($failed) {
        Write-Host '  Setup reported an error - see setup-windows.log' -ForegroundColor Red
        break
    }
    if ($done) {
        Write-Host '  Done! PyTorch and all packages are installed.' -ForegroundColor Green
        break
    }
    Write-Host '  Ctrl+C closes this bar; the setup keeps running.' -ForegroundColor DarkGray
    Start-Sleep -Seconds 1
}
