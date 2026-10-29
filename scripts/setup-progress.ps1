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

while ($true) {
    $now = Get-Date
    # While scripts\fetch-torch-wheels.sh runs, measure the PyTorch files themselves: exact, and
    # unaffected by other downloads on this PC. Otherwise fall back to all bytes received.
    $wheelFiles = Get-ChildItem $wheels -File -ErrorAction SilentlyContinue
    if ($wheelFiles) {
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
    $fetchLog = Join-Path (Split-Path -Parent $Log) 'torch-download.log'
    if ($wheelFiles -and -not ("$text" -match 'Installing PyTorch')) {
        $step = 'Downloading PyTorch in 8 parallel parts'
        if ((Test-Path $fetchLog) -and ((Get-Content $fetchLog -Raw) -match 'WHEELS_DONE')) { $step = 'PyTorch downloaded and verified' }
    }
    $done = "$text" -match 'SETUP_DONE'
    $failed = "$text" -match 'failed \(exit|Exception|ERROR:'

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
