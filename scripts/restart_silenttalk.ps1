param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectDir,

    [Parameter(Mandatory = $true)]
    [string]$Pythonw
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectDirPath = [IO.Path]::GetFullPath($ProjectDir)
$pythonwPath = [IO.Path]::GetFullPath($Pythonw)
$appPath = Join-Path $projectDirPath "app.py"

if (-not (Test-Path -LiteralPath $pythonwPath)) {
    throw "pythonw.exe not found: $pythonwPath"
}
if (-not (Test-Path -LiteralPath $appPath)) {
    throw "app.py not found: $appPath"
}

function Test-SilentTalkProcess {
    param([object]$Process)

    if ($Process.Name -ine "pythonw.exe") {
        return $false
    }
    if ([string]::IsNullOrWhiteSpace([string]$Process.ExecutablePath)) {
        return $false
    }
    if ([string]::IsNullOrWhiteSpace([string]$Process.CommandLine)) {
        return $false
    }
    $commandLine = [string]$Process.CommandLine
    # Match the script argument immediately after the executable; a mention in
    # another application's arguments must not make that process a target.
    $absoluteApp = '(?i)^\s*(?:"[^"]+"|\S+)\s+"?' + [regex]::Escape($appPath) + '"?(?:\s|$)'
    return $commandLine -match $absoluteApp
}

$mutex = New-Object System.Threading.Mutex($false, "Local\SilentTalk.Restart")
$hasMutex = $false

try {
    try {
        $hasMutex = $mutex.WaitOne([TimeSpan]::FromSeconds(10))
    }
    catch [System.Threading.AbandonedMutexException] {
        $hasMutex = $true
    }

    if (-not $hasMutex) {
        throw "Another SilentTalk launcher is already restarting the app."
    }

    $targets = @(
        Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue |
            Where-Object { Test-SilentTalkProcess $_ }
    )
    $managedEdgeAI = $false
    try {
        $edgeStatus = Invoke-RestMethod -Uri "http://127.0.0.1:18087/status" -TimeoutSec 1
        $managedEdgeAI = ($null -ne $edgeStatus -and $edgeStatus.mode -in @("base", "character"))
    }
    catch {
        $managedEdgeAI = $false
    }
    if ($managedEdgeAI -and $edgeStatus.mode -eq "character") {
        # Keep the already-loaded character server alive while the replacement
        # desktop process starts and takes over its lease.
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:18087/handoff" -ContentType "application/json" -Body "{}" -TimeoutSec 2 | Out-Null
    }
    if ($targets.Count -gt 0) {
        Write-Host ("Stopping existing SilentTalk instance(s): " + (($targets.ProcessId) -join ", "))

        foreach ($target in $targets) {
            Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
        }

        $deadline = (Get-Date).AddSeconds(5)
        do {
            $alive = @(
                $targets |
                    Where-Object {
                        Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
                    }
            )

            if ($alive.Count -eq 0) {
                break
            }

            Start-Sleep -Milliseconds 100
        } while ((Get-Date) -lt $deadline)

        if ($alive.Count -gt 0) {
            throw "Timed out while stopping the previous SilentTalk instance."
        }
    }

    $newProcess = Start-Process -FilePath $pythonwPath -ArgumentList @(('"' + $appPath + '"'), "--character-mode") -WorkingDirectory $projectDirPath -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 2
    if ($newProcess.HasExited) {
        throw "SilentTalk exited immediately after launch (exit code $($newProcess.ExitCode))."
    }
    Write-Host "SilentTalk started. PID: $($newProcess.Id)"
}
finally {
    if ($hasMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
