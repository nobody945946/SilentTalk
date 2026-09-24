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

function Test-LegacySilentTalkProcess {
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
    if ($Process.CommandLine -notmatch '(?i)(^|[\s"])app\.py([\s"]|$)') {
        return $false
    }

    try {
        $exePath = [IO.Path]::GetFullPath([string]$Process.ExecutablePath)
        $scriptsDir = Split-Path $exePath -Parent
        if ((Split-Path $scriptsDir -Leaf) -ine "Scripts") {
            return $false
        }

        $venvDir = Split-Path $scriptsDir -Parent
        if ((Split-Path $venvDir -Leaf) -ine ".venv") {
            return $false
        }

        $rootDir = Split-Path $venvDir -Parent
        return (
            (Test-Path -LiteralPath (Join-Path $rootDir "app.py")) -and
            (Test-Path -LiteralPath (Join-Path $rootDir "config.toml")) -and
            (Test-Path -LiteralPath (Join-Path $rootDir "silenttalk\__init__.py"))
        )
    }
    catch {
        return $false
    }
}

function Test-SilentTalkProcess {
    param([object]$Process)

    if ($Process.Name -ine "pythonw.exe") {
        return $false
    }

    $commandLine = [string]$Process.CommandLine
    if (-not [string]::IsNullOrWhiteSpace($commandLine) -and $commandLine.Contains("--silenttalk-desktop")) {
        return $true
    }

    # Migration path for releases before the explicit desktop marker existed.
    return Test-LegacySilentTalkProcess $Process
}

function Test-SilentTalkCopilotProcess {
    param([object]$Process)

    if ($Process.Name -ine "llama-server.exe") {
        return $false
    }
    $commandLine = [string]$Process.CommandLine
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }
    return (
        $commandLine.Contains("Qwen3-0.6B.Q4_K_M.gguf") -and
        $commandLine -match '(?i)(--port|-p)\s+18088'
    )
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
    $copilotTargets = @(
        Get-CimInstance Win32_Process -Filter "Name='llama-server.exe'" -ErrorAction SilentlyContinue |
            Where-Object { Test-SilentTalkCopilotProcess $_ }
    )
    $targets = @($targets + $copilotTargets)

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

    $newProcess = Start-Process -FilePath $pythonwPath -ArgumentList @("app.py", "--silenttalk-desktop") -WorkingDirectory $projectDirPath -PassThru

    Start-Sleep -Milliseconds 250
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
